"""Binary inspectors for MP3, FLAC, Ogg, MP4/M4A, ADTS-AAC and AIFF, plus the dispatcher.

References
----------
* ISO/IEC 11172-3 and ISO/IEC 13818-3 - MPEG-1/2 audio frame header layout.
* LAME project, "Mp3 Info Tag rev 1 specifications" - Xing/Info header and LAME tag
  (encoder string, lowpass, encoder delay/padding).
* ID3v2.3/ID3v2.4 informal standards (id3.org) - tag header, syncsafe sizes, text frames.
* Xiph.Org, FLAC format specification (RFC 9639) - STREAMINFO, VORBIS_COMMENT, MD5 of PCM.
* RFC 3533 (Ogg encapsulation), Vorbis I specification, RFC 7845 (Ogg Opus).
* ISO/IEC 14496-12 - ISO base media file format boxes (ftyp/moov/mvhd/mdhd/stsd/ilst).
"""

from __future__ import annotations

import hashlib
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from ..errors import MalformedFileError
from ..utils.validation import syncsafe
from .common import StructuralIssue, StructureReport
from .wav_parser import parse_wav

# ----------------------------------------------------------------------------- MP3
_MPEG_VERSION = {0b00: "2.5", 0b10: "2", 0b11: "1"}
_LAYER = {0b01: 3, 0b10: 2, 0b11: 1}
_BITRATES = {
    ("1", 1): [0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
    ("1", 2): [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
    ("1", 3): [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    ("2", 1): [0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256],
    ("2", 2): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
    ("2", 3): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_SAMPLE_RATES = {"1": [44100, 48000, 32000], "2": [22050, 24000, 16000], "2.5": [11025, 12000, 8000]}
_CHANNEL_MODES = {0: "stereo", 1: "joint stereo", 2: "dual channel", 3: "mono"}


def parse_mpeg_header(b: bytes) -> dict | None:
    """Decode a 4-byte MPEG audio frame header; return None if it is not a valid header."""
    if len(b) < 4:
        return None
    h = int.from_bytes(b[:4], "big")
    if (h >> 21) & 0x7FF != 0x7FF:
        return None
    vbits, lbits = (h >> 19) & 3, (h >> 17) & 3
    br_idx, sr_idx = (h >> 12) & 0xF, (h >> 10) & 3
    if vbits == 1 or lbits == 0 or br_idx in (0, 15) or sr_idx == 3:
        return None
    version, layer = _MPEG_VERSION[vbits], _LAYER[lbits]
    table_version = "1" if version == "1" else "2"
    bitrate = _BITRATES[(table_version, layer)][br_idx]
    sr = _SAMPLE_RATES[version][sr_idx]
    padding = (h >> 9) & 1
    mode = (h >> 6) & 3
    if layer == 1:
        samples = 384
        length = (12 * bitrate * 1000 // sr + padding) * 4
    else:
        samples = 1152 if (layer == 2 or version == "1") else 576
        length = samples // 8 * bitrate * 1000 // sr + padding
    return {
        "version": version, "layer": layer, "crc": ((h >> 16) & 1) == 0, "bitrate": bitrate,
        "sample_rate": sr, "padding": padding, "mode": mode, "length": length, "samples": samples,
    }


def _valid_chain(data: bytes, pos: int, end: int, count: int) -> bool:
    for _ in range(count):
        h = parse_mpeg_header(data[pos : pos + 4])
        if h is None or h["length"] < 24:
            return False
        pos += h["length"]
        if pos == end:
            return True
        if pos > end:
            return False
    return True


def _find_sync(data: bytes, start: int, end: int, chain: int = 3) -> int | None:
    pos = start
    while True:
        pos = data.find(b"\xff", pos, end)
        if pos < 0 or pos + 4 > end:
            return None
        if _valid_chain(data, pos, end, chain):
            return pos
        pos += 1


def _decode_id3_text(payload: bytes) -> str:
    if not payload:
        return ""
    codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(payload[0], "latin-1")
    return payload[1:].decode(codec, "replace").replace("\x00", " ").strip()


def _parse_id3v2(data: bytes) -> tuple[int, dict, str | None]:
    if data[:3] != b"ID3" or len(data) < 10:
        return 0, {}, None
    major, flags = data[3], data[5]
    size = syncsafe(data[6:10])
    end = 10 + size + (10 if flags & 0x10 else 0)
    tags: dict[str, str] = {}
    pos = 10
    limit = min(10 + size, len(data))
    if flags & 0x40 and major in (3, 4):
        ext = syncsafe(data[10:14]) if major == 4 else int.from_bytes(data[10:14], "big") + 4
        pos += ext
    id_len, hdr_len = (3, 6) if major == 2 else (4, 10)
    while pos + hdr_len <= limit:
        fid = data[pos : pos + id_len]
        if not fid.isalnum():
            break
        if major == 2:
            fsize = int.from_bytes(data[pos + 3 : pos + 6], "big")
        elif major == 4:
            fsize = syncsafe(data[pos + 4 : pos + 8])
        else:
            fsize = int.from_bytes(data[pos + 4 : pos + 8], "big")
        payload = data[pos + hdr_len : pos + hdr_len + fsize]
        key = fid.decode("latin-1")
        if key.startswith("T") and key not in ("TXXX", "TXX"):
            tags[key] = _decode_id3_text(payload)
        elif key in ("COMM", "COM") and len(payload) > 4:
            tags[key] = _decode_id3_text(payload[:1] + payload[4:])
        pos += hdr_len + max(fsize, 0)
        if fsize <= 0:
            break
    return end, tags, f"2.{major}"


def _parse_vbr_tag(data: bytes, off: int, h: dict) -> dict | None:
    mono = h["mode"] == 3
    side = (17 if mono else 32) if h["version"] == "1" else (9 if mono else 17)
    x = off + 4 + (2 if h["crc"] else 0) + side
    tag = data[x : x + 4]
    if tag in (b"Xing", b"Info"):
        flags = int.from_bytes(data[x + 4 : x + 8], "big")
        p = x + 8
        out: dict = {"type": tag.decode(), "offset": off}
        if flags & 1:
            out["frames"] = int.from_bytes(data[p : p + 4], "big"); p += 4
        if flags & 2:
            out["bytes"] = int.from_bytes(data[p : p + 4], "big"); p += 4
        if flags & 4:
            p += 100
        if flags & 8:
            out["quality"] = int.from_bytes(data[p : p + 4], "big"); p += 4
        enc = data[p : p + 9]
        if len(enc) == 9 and all(32 <= c < 127 for c in enc[:4]):
            d = data[p + 21 : p + 24]
            out["encoder"] = enc.decode("latin-1").strip("\x00 ")
            out["vbr_method"] = data[p + 9] & 0x0F
            out["lowpass_hz"] = data[p + 10] * 100
            if len(d) == 3:
                out["encoder_delay"] = (d[0] << 4) | (d[1] >> 4)
                out["encoder_padding"] = ((d[1] & 0x0F) << 8) | d[2]
        return out
    if data[off + 36 : off + 40] == b"VBRI":
        p = off + 36
        return {"type": "VBRI", "offset": off,
                "bytes": int.from_bytes(data[p + 10 : p + 14], "big"),
                "frames": int.from_bytes(data[p + 14 : p + 18], "big")}
    return None


def inspect_mp3(path: Path) -> StructureReport:
    data = path.read_bytes()
    rep = StructureReport("mp3", "sonictrace.mpeg_audio")
    issues = rep.issues
    start, tags, id3ver = _parse_id3v2(data)
    rep.tags.update(tags)
    end = len(data)
    id3v1 = None
    if end >= 128 and data[end - 128 : end - 125] == b"TAG":
        raw = data[end - 128 :]
        id3v1 = {"title": raw[3:33].split(b"\0")[0].decode("latin-1", "replace").strip(),
                 "artist": raw[33:63].split(b"\0")[0].decode("latin-1", "replace").strip()}
        end -= 128
    if data[max(0, end - 32) : end - 24] == b"APETAGEX":
        issues.append(StructuralIssue("ape_tag", "info", "An APEv2 tag is present at the end of the stream."))
    first = _find_sync(data, start, end)
    if first is None:
        raise MalformedFileError("No valid chain of MPEG audio frame headers was found.")
    if first > start:
        issues.append(StructuralIssue("leading_junk", "low", f"{first - start} non-frame bytes precede the first audio frame.", {"bytes": first - start}))

    bitrates, rates, versions, layers, modes, lengths = [], [], [], [], [], []
    gaps: list[dict] = []
    vbr_tags: list[tuple[int, dict]] = []
    pos, idx, samples_per_frame = first, 0, None
    while pos + 4 <= end:
        h = parse_mpeg_header(data[pos : pos + 4])
        if h is None or h["length"] < 24:
            nxt = _find_sync(data, pos + 1, end, chain=2)
            if nxt is None:
                if end - pos > 0:
                    issues.append(StructuralIssue("trailing_junk", "low", f"{end - pos} bytes after the last valid frame are not audio frames.", {"offset": pos, "bytes": end - pos}))
                break
            chunk = data[pos:nxt]
            gaps.append({"offset": pos, "bytes": nxt - pos, "contains_id3": b"ID3" in chunk, "contains_tag": b"TAG" in chunk})
            pos = nxt
            continue
        tag = _parse_vbr_tag(data, pos, h)
        if tag:
            vbr_tags.append((idx, tag))
        bitrates.append(h["bitrate"]); rates.append(h["sample_rate"]); versions.append(h["version"])
        layers.append(h["layer"]); modes.append(h["mode"]); lengths.append(h["length"])
        samples_per_frame = h["samples"]
        pos += h["length"]
        idx += 1

    n_frames = len(bitrates)
    head_tag = vbr_tags[0][1] if vbr_tags and vbr_tags[0][0] == 0 else None
    audio_brs = bitrates[1:] if head_tag else bitrates
    sr = rates[0]
    total_samples = (n_frames - (1 if head_tag else 0)) * (samples_per_frame or 1152)
    details = {
        "id3v2_version": id3ver, "id3v1": id3v1, "first_frame_offset": first, "frames": n_frames,
        "mpeg_version": versions[0], "layer": layers[0], "sample_rate": sr,
        "channel_mode": _CHANNEL_MODES[modes[0]], "samples_per_frame": samples_per_frame,
        "bitrate_kbps_min": int(min(audio_brs)) if audio_brs else None,
        "bitrate_kbps_max": int(max(audio_brs)) if audio_brs else None,
        "bitrate_kbps_mean": round(float(np.mean(audio_brs)), 2) if audio_brs else None,
        "bitrate_mode": "CBR" if audio_brs and len(set(audio_brs)) == 1 else "VBR",
        "duration_from_frames_s": round(total_samples / sr, 4),
        "vbr_header": head_tag, "sync_gaps": gaps[:50], "sync_gap_count": len(gaps),
    }
    rep.details = details
    if head_tag and head_tag.get("encoder"):
        rep.signatures.append(head_tag["encoder"])
    for k in ("TSSE", "TENC", "TSS", "TEN"):
        if tags.get(k):
            rep.signatures.append(tags[k])

    if len(set(rates)) > 1:
        issues.append(StructuralIssue("sample_rate_change", "high", f"Frame sample rate changes within the stream: {sorted(set(rates))} Hz.", {"rates": sorted(set(rates))}))
    if len(set(versions)) > 1 or len(set(layers)) > 1:
        issues.append(StructuralIssue("mpeg_version_change", "high", "MPEG version or layer changes within the stream.", {"versions": sorted(set(versions)), "layers": sorted(set(layers))}))
    if len({m == 3 for m in modes}) > 1:
        issues.append(StructuralIssue("channel_count_change", "high", "The stream switches between mono and multi-channel frames."))
    if head_tag and head_tag["type"] == "Info" and len(set(audio_brs)) > 1:
        issues.append(StructuralIssue("cbr_declared_bitrate_varies", "medium", "An 'Info' (CBR) header is present but frame bitrates vary.", {"bitrates": sorted(set(audio_brs))}))
    mid = [(i, t) for i, t in vbr_tags if i > 0]
    if mid:
        issues.append(StructuralIssue(
            "midstream_vbr_header", "high",
            f"{len(mid)} Xing/Info/VBRI header frame(s) found inside the stream (frame index {mid[0][0]}). Encoders write this header only in the first frame.",
            {"frame_indices": [i for i, _ in mid][:20], "encoders": sorted({t.get('encoder', '') for _, t in mid})}))
    for g in gaps[:20]:
        sev = "high" if (g["contains_id3"] or g["contains_tag"]) else "medium"
        what = "an embedded ID3/TAG block" if sev == "high" else "non-frame bytes"
        issues.append(StructuralIssue("sync_gap", sev, f"Frame synchronisation lost at byte {g['offset']}: {g['bytes']} bytes of {what} between frames.", g))
    if head_tag and "frames" in head_tag:
        counted = n_frames - 1
        if abs(head_tag["frames"] - counted) > 1:
            issues.append(StructuralIssue(
                "vbr_frame_count_mismatch", "medium",
                f"{head_tag['type']} header declares {head_tag['frames']} frames; {counted} audio frames were counted.",
                {"declared": head_tag["frames"], "counted": counted}))
    return rep


# ----------------------------------------------------------------------------- FLAC
def _flac_pcm_md5(path: Path, bps: int) -> str | None:
    """MD5 of the decoded PCM exactly as defined by STREAMINFO (interleaved, little-endian, signed)."""
    import soundfile as sf

    if bps not in (8, 16, 24, 32):
        return None
    m = hashlib.md5()
    dtype = "int16" if bps <= 16 else "int32"
    with sf.SoundFile(str(path)) as snd:
        for block in snd.blocks(blocksize=65536, dtype=dtype, always_2d=True):
            if bps == 8:
                arr = (block >> 8).astype("<i1")
            elif bps == 16:
                arr = block.astype("<i2")
            elif bps == 24:
                arr = np.ascontiguousarray((block >> 8).astype("<i4")).view(np.uint8).reshape(-1, 4)[:, :3]
            else:
                arr = block.astype("<i4")
            m.update(np.ascontiguousarray(arr).tobytes())
    return m.hexdigest()


def inspect_flac(path: Path, verify_md5: bool = True) -> StructureReport:
    rep = StructureReport("flac", "sonictrace.flac")
    issues = rep.issues
    blocks = []
    with open(path, "rb") as f:
        head = f.read(10)
        offset = 0
        if head[:3] == b"ID3":
            offset = 10 + syncsafe(head[6:10])
            issues.append(StructuralIssue("id3_before_flac", "low", "An ID3v2 tag precedes the 'fLaC' marker (non-standard for FLAC)."))
        f.seek(offset)
        if f.read(4) != b"fLaC":
            raise MalformedFileError("Missing 'fLaC' stream marker.")
        streaminfo = None
        last = False
        while not last:
            hdr = f.read(4)
            if len(hdr) < 4:
                issues.append(StructuralIssue("truncated_metadata", "high", "File ends inside the FLAC metadata block list."))
                break
            last = bool(hdr[0] & 0x80)
            btype = hdr[0] & 0x7F
            length = int.from_bytes(hdr[1:4], "big")
            payload = f.read(length) if length <= 16 * 1024 * 1024 else b""
            blocks.append({"type": btype, "length": length})
            if btype == 0 and len(payload) >= 34:
                v = int.from_bytes(payload[10:18], "big")
                streaminfo = {
                    "min_blocksize": int.from_bytes(payload[0:2], "big"),
                    "max_blocksize": int.from_bytes(payload[2:4], "big"),
                    "min_framesize": int.from_bytes(payload[4:7], "big"),
                    "max_framesize": int.from_bytes(payload[7:10], "big"),
                    "sample_rate": v >> 44,
                    "channels": ((v >> 41) & 7) + 1,
                    "bits_per_sample": ((v >> 36) & 31) + 1,
                    "total_samples": v & ((1 << 36) - 1),
                    "md5": payload[18:34].hex(),
                }
            elif btype == 4 and len(payload) >= 8:
                vlen = struct.unpack("<I", payload[:4])[0]
                vendor = payload[4 : 4 + vlen].decode("utf-8", "replace")
                rep.signatures.append(vendor)
                p = 4 + vlen
                n = struct.unpack("<I", payload[p : p + 4])[0] if p + 4 <= len(payload) else 0
                p += 4
                for _ in range(min(n, 1000)):
                    if p + 4 > len(payload):
                        break
                    clen = struct.unpack("<I", payload[p : p + 4])[0]
                    text = payload[p + 4 : p + 4 + clen].decode("utf-8", "replace")
                    p += 4 + clen
                    if "=" in text:
                        k, val = text.split("=", 1)
                        rep.tags[k.upper()] = val
                rep.tags["VENDOR"] = vendor
        audio_offset = f.tell()
        sync = f.read(2)
    if streaminfo is None:
        raise MalformedFileError("FLAC STREAMINFO block missing or truncated.")
    if len(sync) == 2 and not (sync[0] == 0xFF and (sync[1] & 0xFE) == 0xF8):
        issues.append(StructuralIssue("bad_first_frame_sync", "medium", f"No FLAC frame sync code at the first audio frame offset ({audio_offset})."))
    rep.details = {"streaminfo": streaminfo, "metadata_blocks": blocks, "audio_offset": audio_offset,
                   "declared_duration_s": streaminfo["total_samples"] / streaminfo["sample_rate"] if streaminfo["sample_rate"] else None}
    md5 = streaminfo["md5"]
    if md5 == "0" * 32:
        issues.append(StructuralIssue("md5_unset", "info", "STREAMINFO MD5 signature is unset (all zeros); audio integrity cannot be verified from the file itself."))
        rep.details["md5_verification"] = "not_available"
    elif verify_md5:
        try:
            computed = _flac_pcm_md5(path, streaminfo["bits_per_sample"])
        except Exception as exc:  # decoder failure is itself evidence of damage
            computed = None
            issues.append(StructuralIssue("md5_decode_failed", "medium", f"Audio could not be fully decoded for MD5 verification: {exc}"))
        rep.details["md5_computed"] = computed
        if computed is None:
            rep.details["md5_verification"] = "not_performed"
        elif computed == md5:
            rep.details["md5_verification"] = "match"
        else:
            rep.details["md5_verification"] = "mismatch"
            issues.append(StructuralIssue(
                "md5_mismatch", "high",
                "MD5 of the decoded audio does not match the STREAMINFO MD5 written by the encoder: the audio frames changed after encoding (or the encoder was faulty).",
                {"declared": md5, "computed": computed}))
    return rep


# ----------------------------------------------------------------------------- Ogg
def _crc_table() -> list[int]:
    table = []
    for i in range(256):
        r = i << 24
        for _ in range(8):
            r = ((r << 1) ^ 0x04C11DB7) if r & 0x80000000 else (r << 1)
            r &= 0xFFFFFFFF
        table.append(r)
    return table


_OGG_CRC = _crc_table()


def ogg_crc(page: bytes) -> int:
    crc = 0
    for b in page:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ _OGG_CRC[((crc >> 24) & 0xFF) ^ b]
    return crc


def inspect_ogg(path: Path, crc_budget_bytes: int = 20 * 1024 * 1024) -> StructureReport:
    data = path.read_bytes()
    rep = StructureReport("ogg", "sonictrace.ogg")
    issues = rep.issues
    pos, pages, crc_checked, crc_bad = 0, 0, 0, []
    streams: dict[int, dict] = {}
    eos_seen = False
    while pos + 27 <= len(data):
        if data[pos : pos + 4] != b"OggS":
            nxt = data.find(b"OggS", pos + 1)
            issues.append(StructuralIssue("ogg_capture_gap", "medium", f"{(nxt if nxt > 0 else len(data)) - pos} bytes between Ogg pages at offset {pos} are not page data.", {"offset": pos}))
            if nxt < 0:
                break
            pos = nxt
            continue
        _ver, htype, granule, serial, seq, crc, nseg = struct.unpack_from("<BBqIIIB", data, pos + 4)
        seg = data[pos + 27 : pos + 27 + nseg]
        body_start = pos + 27 + nseg
        page_end = body_start + sum(seg)
        if page_end > len(data):
            issues.append(StructuralIssue("ogg_truncated_page", "medium", f"The last Ogg page (offset {pos}) is truncated."))
            break
        if crc_checked < crc_budget_bytes:
            page = bytearray(data[pos:page_end])
            page[22:26] = b"\x00\x00\x00\x00"
            if ogg_crc(bytes(page)) != crc:
                crc_bad.append(pos)
            crc_checked += page_end - pos
        st = streams.get(serial)
        body = data[body_start:page_end]
        if st is None:
            if not htype & 0x02:
                issues.append(StructuralIssue("ogg_missing_bos", "medium", f"Stream {serial:#x} starts without a beginning-of-stream page."))
            if eos_seen:
                issues.append(StructuralIssue("ogg_chained_stream", "medium", f"A new logical stream ({serial:#x}) begins after another stream ended: chained (concatenated) Ogg file."))
            st = streams[serial] = {"pages": 0, "last_seq": None, "last_granule": None, "codec": None}
            if body.startswith(b"\x01vorbis") and len(body) >= 16:
                st["codec"] = "vorbis"
                st["channels"] = body[11]
                st["sample_rate"] = struct.unpack("<I", body[12:16])[0]
            elif body.startswith(b"OpusHead") and len(body) >= 16:
                st["codec"] = "opus"
                st["channels"] = body[9]
                st["pre_skip"] = struct.unpack("<H", body[10:12])[0]
                st["input_sample_rate"] = struct.unpack("<I", body[12:16])[0]
                st["sample_rate"] = 48000
            elif body.startswith(b"\x7fFLAC"):
                st["codec"] = "flac"
        elif st["pages"] == 1:
            for magic in (b"\x03vorbis", b"OpusTags"):
                if body.startswith(magic) and len(body) >= len(magic) + 4:
                    vlen = struct.unpack("<I", body[len(magic) : len(magic) + 4])[0]
                    vendor = body[len(magic) + 4 : len(magic) + 4 + vlen].decode("utf-8", "replace")
                    st["vendor"] = vendor
                    rep.signatures.append(vendor)
        if st["last_seq"] is not None and seq != st["last_seq"] + 1:
            issues.append(StructuralIssue("ogg_sequence_gap", "medium", f"Page sequence jumps from {st['last_seq']} to {seq} in stream {serial:#x}: pages are missing or reordered.", {"offset": pos}))
        if granule != -1 and st["last_granule"] is not None and granule < st["last_granule"]:
            issues.append(StructuralIssue("ogg_granule_regression", "medium", f"Granule position decreases at offset {pos}.", {"offset": pos}))
        st["last_seq"] = seq
        if granule != -1:
            st["last_granule"] = granule
        st["pages"] += 1
        if htype & 0x04:
            eos_seen = True
        pos = page_end
        pages += 1
    if crc_bad:
        issues.append(StructuralIssue("ogg_crc_mismatch", "high", f"{len(crc_bad)} Ogg page(s) fail CRC-32 verification: bytes changed after the page was written.", {"offsets": crc_bad[:20]}))
    for st in streams.values():
        if st.get("last_granule") is not None and st.get("sample_rate"):
            st["duration_s"] = (st["last_granule"] - st.get("pre_skip", 0)) / st["sample_rate"]
    rep.details = {"pages": pages, "streams": {f"{k:#x}": v for k, v in streams.items()}, "crc_checked_bytes": crc_checked}
    return rep


# ----------------------------------------------------------------------------- MP4
_MP4_CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"udta", b"edts", b"dinf", b"ilst", b"mvex"}
_EPOCH_1904 = datetime(1904, 1, 1, tzinfo=timezone.utc)


def _mp4_time(v: int) -> str | None:
    if v == 0:
        return None
    try:
        return (_EPOCH_1904 + timedelta(seconds=v)).isoformat()
    except OverflowError:
        return f"invalid({v})"


def inspect_mp4(path: Path) -> StructureReport:
    rep = StructureReport("mp4", "sonictrace.isobmff")
    issues = rep.issues
    size = path.stat().st_size
    boxes: list[dict] = []
    info: dict = {"tracks": []}

    def walk(f, start: int, end: int, depth: int) -> None:
        pos = start
        while pos + 8 <= end and len(boxes) < 5000:
            f.seek(pos)
            hdr = f.read(8)
            bsize, btype = struct.unpack(">I4s", hdr)
            hlen = 8
            if bsize == 1:
                bsize = struct.unpack(">Q", f.read(8))[0]
                hlen = 16
            elif bsize == 0:
                bsize = end - pos
            if bsize < hlen or pos + bsize > end:
                issues.append(StructuralIssue("mp4_bad_box", "medium", f"Box {btype!r} at offset {pos} has an invalid size ({bsize}).", {"offset": pos}))
                return
            name = btype.decode("latin-1")
            boxes.append({"depth": depth, "type": name, "offset": pos, "size": bsize})
            body_off = pos + hlen
            if btype in _MP4_CONTAINERS:
                walk(f, body_off, pos + bsize, depth + 1)
            elif btype == b"meta":
                walk(f, body_off + 4, pos + bsize, depth + 1)
            elif btype in (b"mvhd", b"mdhd"):
                f.seek(body_off)
                body = f.read(min(bsize - hlen, 64))
                ver = body[0]
                if ver == 1 and len(body) >= 32:
                    c, m, ts, du = struct.unpack(">QQIQ", body[4:32])
                else:
                    c, m, ts, du = struct.unpack(">IIII", body[4:20])
                entry = {"box": name, "creation_time": _mp4_time(c), "modification_time": _mp4_time(m),
                         "creation_raw": c, "modification_raw": m, "timescale": ts,
                         "duration_s": du / ts if ts else None}
                if btype == b"mvhd":
                    info["movie_header"] = entry
                else:
                    info["tracks"].append(entry)
            elif btype == b"stsd":
                f.seek(body_off + 8)
                ent = f.read(8)
                if len(ent) == 8:
                    info.setdefault("codecs", []).append(ent[4:8].decode("latin-1"))
            elif btype[:1] == b"\xa9" or btype in (b"aART", b"desc"):
                f.seek(body_off)
                body = f.read(min(bsize - hlen, 65536))
                if body[4:8] == b"data":
                    dlen = struct.unpack(">I", body[:4])[0]
                    value = body[16:dlen].decode("utf-8", "replace")
                    rep.tags[name] = value
                    if btype == b"\xa9too":
                        rep.signatures.append(value)
            elif btype == b"ftyp":
                f.seek(body_off)
                body = f.read(min(bsize - hlen, 256))
                info["major_brand"] = body[:4].decode("latin-1")
                info["compatible_brands"] = [body[i : i + 4].decode("latin-1") for i in range(8, len(body) - 3, 4)]
            pos += bsize

    with open(path, "rb") as f:
        walk(f, 0, size, 0)
    top = [b["type"] for b in boxes if b["depth"] == 0]
    if "moov" not in top and "moof" not in top:
        issues.append(StructuralIssue("mp4_missing_moov", "high", "No 'moov' box: the file has no playable index."))
    if top.count("moov") > 1:
        issues.append(StructuralIssue("mp4_multiple_moov", "high", "More than one top-level 'moov' box."))
    if top.count("mdat") > 1:
        issues.append(StructuralIssue("mp4_multiple_mdat", "low", "More than one top-level 'mdat' box."))
    mv = info.get("movie_header")
    if mv:
        c, m = mv["creation_raw"], mv["modification_raw"]
        if c == 0:
            issues.append(StructuralIssue("mp4_creation_unset", "info", "Movie creation time is zero (not set by the writer, typical of FFmpeg defaults)."))
        elif m and m < c:
            issues.append(StructuralIssue("mp4_time_order", "medium", "Movie modification time is earlier than its creation time.", {"creation": mv["creation_time"], "modification": mv["modification_time"]}))
        elif m and m != c:
            issues.append(StructuralIssue("mp4_modified_after_creation", "info", "Modification time differs from creation time (file rewritten after creation).", {"creation": mv["creation_time"], "modification": mv["modification_time"]}))
    info["top_level_boxes"] = top
    info["box_count"] = len(boxes)
    rep.details = info
    return rep


# ----------------------------------------------------------------------------- ADTS / AIFF
_ADTS_RATES = [96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350]


def inspect_adts(path: Path) -> StructureReport:
    data = path.read_bytes()
    rep = StructureReport("aac_adts", "sonictrace.adts")
    pos, frames, rates, chans, gaps = 0, 0, set(), set(), 0
    while pos + 7 <= len(data):
        if not (data[pos] == 0xFF and (data[pos + 1] & 0xF6) == 0xF0):
            nxt = data.find(b"\xff", pos + 1)
            gaps += 1
            if nxt < 0:
                break
            pos = nxt
            continue
        sr_idx = (data[pos + 2] >> 2) & 0xF
        ch = ((data[pos + 2] & 1) << 2) | (data[pos + 3] >> 6)
        flen = ((data[pos + 3] & 3) << 11) | (data[pos + 4] << 3) | (data[pos + 5] >> 5)
        if flen < 7 or sr_idx >= len(_ADTS_RATES):
            pos += 1
            gaps += 1
            continue
        rates.add(_ADTS_RATES[sr_idx]); chans.add(ch)
        frames += 1
        pos += flen
    if len(rates) > 1:
        rep.issues.append(StructuralIssue("adts_rate_change", "high", f"ADTS sample rate changes within the stream: {sorted(rates)}."))
    if len(chans) > 1:
        rep.issues.append(StructuralIssue("adts_channel_change", "high", f"ADTS channel configuration changes within the stream: {sorted(chans)}."))
    if gaps:
        rep.issues.append(StructuralIssue("adts_sync_gap", "medium", f"{gaps} synchronisation losses between ADTS frames."))
    rep.details = {"frames": frames, "sample_rates": sorted(rates), "channel_configs": sorted(chans)}
    return rep


def _ieee_extended(b: bytes) -> float:
    exp = int.from_bytes(b[0:2], "big") & 0x7FFF
    mant = int.from_bytes(b[2:10], "big")
    return 0.0 if exp == 0 and mant == 0 else mant * 2.0 ** (exp - 16383 - 63)


def inspect_aiff(path: Path) -> StructureReport:
    rep = StructureReport("aiff", "sonictrace.aiff")
    size = path.stat().st_size
    chunks = []
    with open(path, "rb") as f:
        head = f.read(12)
        form_size = struct.unpack(">I", head[4:8])[0]
        pos = 12
        while pos + 8 <= size:
            f.seek(pos)
            cid, csize = struct.unpack(">4sI", f.read(8))
            chunks.append({"id": cid.decode("latin-1"), "offset": pos, "size": csize})
            if cid == b"COMM":
                body = f.read(18)
                ch, frames, bits = struct.unpack(">hIh", body[:8])
                rep.details["comm"] = {"channels": ch, "frames": frames, "bits": bits, "sample_rate": _ieee_extended(body[8:18])}
            pos += 8 + csize + (csize & 1)
    if form_size + 8 != size:
        rep.issues.append(StructuralIssue("aiff_size_mismatch", "medium", f"FORM size declares {form_size + 8} bytes; file has {size}."))
    rep.details["chunks"] = chunks
    return rep


# ----------------------------------------------------------------------------- dispatcher
def _wav_report(path: Path) -> StructureReport:
    st = parse_wav(path)
    rep = StructureReport("wav", "sonictrace.riff_wave", details=st.to_dict(), issues=st.issues)
    sw = st.info.get("software")
    if sw:
        rep.signatures.append(sw)
    if st.bext:
        if st.bext.get("coding_history"):
            rep.signatures.append(st.bext["coding_history"])
        if st.bext.get("originator"):
            rep.signatures.append(st.bext["originator"])
    rep.tags.update({f"INFO:{k}": v for k, v in st.info.items()})
    return rep


def inspect_structure(path: str | Path, container: str) -> StructureReport:
    """Run the binary inspector that matches the sniffed container."""
    p = Path(path)
    handlers = {
        "wav": _wav_report,
        "mp3": inspect_mp3,
        "flac": inspect_flac,
        "ogg": inspect_ogg,
        "mp4": inspect_mp4,
        "aac_adts": inspect_adts,
        "aiff": inspect_aiff,
    }
    handler = handlers.get(container)
    if handler is None:
        rep = StructureReport(container, "none")
        rep.issues.append(StructuralIssue("unknown_container", "medium", "The file's magic bytes do not match any supported container."))
        return rep
    return handler(p)
