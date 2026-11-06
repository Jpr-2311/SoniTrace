"""Binary RIFF/WAVE and RF64 parser.

The parser walks the chunk list itself instead of trusting a decoder, because a
decoder silently tolerates exactly the inconsistencies that are forensically relevant
(trailing bytes, truncated chunks, duplicated ``data`` chunks, header fields that do
not agree with each other).

References
----------
* IBM & Microsoft, "Multimedia Programming Interface and Data Specifications 1.0"
  (1991) - RIFF and WAVE ``fmt ``/``data``/``fact``/``LIST`` chunks.
* Microsoft, "WAVEFORMATEXTENSIBLE" documentation - extensible format and sub-format GUIDs.
* EBU Tech 3285 - Broadcast Wave Format (``bext`` chunk, CodingHistory).
* EBU Tech 3306 - RF64 (``ds64`` chunk, 64-bit sizes).
"""

from __future__ import annotations

import struct
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..errors import MalformedFileError, UnsupportedFormatError
from .common import StructuralIssue

MAX_META_CHUNK_BYTES = 16 * 1024 * 1024
MAX_CHUNKS = 10000

FORMAT_TAGS = {
    0x0001: "PCM",
    0x0002: "Microsoft ADPCM",
    0x0003: "IEEE float",
    0x0006: "A-law",
    0x0007: "mu-law",
    0x0011: "IMA ADPCM",
    0x0050: "MPEG audio",
    0x0055: "MPEG Layer 3",
    0xFFFE: "WAVE_FORMAT_EXTENSIBLE",
}
_GUID_TAIL = bytes.fromhex("000000001000800000aa00389b71")

INFO_FIELDS = {
    "INAM": "title",
    "IART": "artist",
    "ICMT": "comment",
    "ICRD": "creation_date",
    "ISFT": "software",
    "IENG": "engineer",
    "ITCH": "technician",
    "ICOP": "copyright",
    "IPRD": "product",
    "ISRC": "source",
    "IGNR": "genre",
    "IKEY": "keywords",
    "ISBJ": "subject",
}


@dataclass
class ChunkInfo:
    chunk_id: str
    offset: int
    size: int
    available: int


@dataclass
class WavFormat:
    format_tag: int
    format_name: str
    channels: int
    sample_rate: int
    byte_rate: int
    block_align: int
    bits_per_sample: int
    cb_size: int | None = None
    valid_bits: int | None = None
    channel_mask: int | None = None
    subformat_tag: int | None = None

    @property
    def effective_tag(self) -> int:
        if self.format_tag == 0xFFFE and self.subformat_tag is not None:
            return self.subformat_tag
        return self.format_tag


@dataclass
class WavStructure:
    file_size: int
    riff_id: str
    riff_size: int
    form_type: str
    chunks: list[ChunkInfo] = field(default_factory=list)
    fmt: WavFormat | None = None
    data_offset: int | None = None
    data_size: int | None = None
    data_size_declared: int | None = None
    fact_samples: int | None = None
    ds64: dict | None = None
    info: dict[str, str] = field(default_factory=dict)
    bext: dict | None = None
    issues: list[StructuralIssue] = field(default_factory=list)

    @property
    def frame_count(self) -> int | None:
        if self.fmt and self.fmt.block_align and self.data_size is not None:
            return self.data_size // self.fmt.block_align
        return None

    @property
    def declared_duration(self) -> float | None:
        n = self.frame_count
        if n is None or not self.fmt or not self.fmt.sample_rate:
            return None
        return n / self.fmt.sample_rate

    def to_dict(self) -> dict:
        d = {
            "file_size": self.file_size,
            "riff_id": self.riff_id,
            "riff_size_declared": self.riff_size,
            "form_type": self.form_type,
            "chunks": [asdict(c) for c in self.chunks],
            "fmt": asdict(self.fmt) if self.fmt else None,
            "data_offset": self.data_offset,
            "data_size_available": self.data_size,
            "data_size_declared": self.data_size_declared,
            "frame_count": self.frame_count,
            "declared_duration_s": self.declared_duration,
            "fact_samples": self.fact_samples,
            "ds64": self.ds64,
            "info": self.info,
            "bext": self.bext,
        }
        if self.fmt:
            d["fmt"]["format_description"] = FORMAT_TAGS.get(self.fmt.effective_tag, "unknown")
        return d


def _cstr(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("latin-1", "replace").strip()


def _parse_fmt(payload: bytes, issues: list[StructuralIssue]) -> WavFormat | None:
    if len(payload) < 16:
        issues.append(StructuralIssue("fmt_too_short", "high", f"fmt chunk is {len(payload)} bytes; at least 16 are required."))
        return None
    tag, ch, sr, br, ba, bps = struct.unpack("<HHIIHH", payload[:16])
    fmt = WavFormat(tag, FORMAT_TAGS.get(tag, f"unknown (0x{tag:04X})"), ch, sr, br, ba, bps)
    if len(payload) >= 18:
        fmt.cb_size = struct.unpack("<H", payload[16:18])[0]
    if tag == 0xFFFE:
        if len(payload) >= 40:
            fmt.valid_bits, fmt.channel_mask = struct.unpack("<HI", payload[18:24])
            guid = payload[24:40]
            if guid[2:] == _GUID_TAIL:
                fmt.subformat_tag = struct.unpack("<H", guid[:2])[0]
            else:
                issues.append(StructuralIssue("unknown_subformat_guid", "low", "WAVE_FORMAT_EXTENSIBLE uses a non-standard sub-format GUID.", {"guid": guid.hex()}))
        else:
            issues.append(StructuralIssue("extensible_too_short", "medium", "WAVE_FORMAT_EXTENSIBLE declared but the fmt chunk is shorter than 40 bytes."))
    return fmt


def _validate_fmt(fmt: WavFormat, issues: list[StructuralIssue]) -> None:
    if fmt.channels == 0:
        issues.append(StructuralIssue("zero_channels", "high", "fmt chunk declares 0 channels."))
    if fmt.sample_rate == 0:
        issues.append(StructuralIssue("zero_sample_rate", "high", "fmt chunk declares a sample rate of 0 Hz."))
    tag = fmt.effective_tag
    if tag in (1, 3) and fmt.channels:
        expected_align = fmt.channels * ((fmt.bits_per_sample + 7) // 8)
        if fmt.block_align != expected_align:
            issues.append(StructuralIssue(
                "block_align_mismatch", "medium",
                f"nBlockAlign is {fmt.block_align}; channels x bytes-per-sample gives {expected_align}.",
                {"declared": fmt.block_align, "expected": expected_align}))
        if fmt.byte_rate != fmt.sample_rate * fmt.block_align:
            issues.append(StructuralIssue(
                "byte_rate_mismatch", "medium",
                f"nAvgBytesPerSec is {fmt.byte_rate}; sample rate x block align gives {fmt.sample_rate * fmt.block_align}.",
                {"declared": fmt.byte_rate, "expected": fmt.sample_rate * fmt.block_align}))
        if tag == 1 and fmt.bits_per_sample not in (8, 16, 24, 32):
            issues.append(StructuralIssue("unusual_bit_depth", "low", f"Integer PCM with {fmt.bits_per_sample} bits per sample is unusual."))
        if tag == 3 and fmt.bits_per_sample not in (32, 64):
            issues.append(StructuralIssue("float_bit_depth", "medium", f"IEEE float declared with {fmt.bits_per_sample} bits per sample."))
    if fmt.valid_bits is not None and fmt.valid_bits > fmt.bits_per_sample:
        issues.append(StructuralIssue("valid_bits_exceed_container", "medium", "wValidBitsPerSample exceeds the container sample size."))


def _parse_info(payload: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    pos = 0
    while pos + 8 <= len(payload):
        sid = payload[pos : pos + 4].decode("latin-1", "replace")
        size = struct.unpack("<I", payload[pos + 4 : pos + 8])[0]
        value = _cstr(payload[pos + 8 : pos + 8 + size])
        out[INFO_FIELDS.get(sid, sid)] = value
        pos += 8 + size + (size & 1)
    return out


def _parse_bext(payload: bytes) -> dict:
    """Broadcast Wave ``bext`` chunk (EBU Tech 3285, versions 0-2)."""
    if len(payload) < 348:
        return {"error": f"bext chunk too short ({len(payload)} bytes)"}
    d = {
        "description": _cstr(payload[0:256]),
        "originator": _cstr(payload[256:288]),
        "originator_reference": _cstr(payload[288:320]),
        "origination_date": _cstr(payload[320:330]),
        "origination_time": _cstr(payload[330:338]),
        "time_reference_samples": struct.unpack("<Q", payload[338:346])[0],
        "version": struct.unpack("<H", payload[346:348])[0],
    }
    if len(payload) >= 412:
        d["umid"] = payload[348:412].hex().rstrip("0") or None
    if len(payload) > 602:
        d["coding_history"] = _cstr(payload[602:])
    return d


def parse_wav(path: str | Path) -> WavStructure:
    p = Path(path)
    size = p.stat().st_size
    with open(p, "rb") as f:
        head = f.read(12)
        if len(head) < 12:
            raise MalformedFileError("File is too short to be a RIFF/WAVE file (fewer than 12 bytes).")
        riff_id = head[0:4].decode("latin-1", "replace")
        if riff_id == "RIFX":
            raise UnsupportedFormatError("Big-endian RIFX files are not supported.")
        if riff_id not in ("RIFF", "RF64"):
            raise MalformedFileError(f"Not a RIFF file (magic bytes {head[:4]!r}).")
        riff_size = struct.unpack("<I", head[4:8])[0]
        form = head[8:12].decode("latin-1", "replace")
        if form != "WAVE":
            raise MalformedFileError(f"RIFF form type is {form!r}; expected 'WAVE'.")

        st = WavStructure(file_size=size, riff_id=riff_id, riff_size=riff_size, form_type=form)
        issues = st.issues
        seen: Counter = Counter()
        order: list[str] = []
        pos = 12
        prev_odd = False
        while pos + 8 <= size and len(st.chunks) < MAX_CHUNKS:
            f.seek(pos)
            hdr = f.read(8)
            cid_raw = hdr[:4]
            if not all(32 <= b < 127 for b in cid_raw):
                # writers that forget the RIFF pad byte after an odd-sized chunk misalign the list
                if prev_odd:
                    f.seek(pos - 1)
                    alt = f.read(8)
                    if all(32 <= b < 127 for b in alt[:4]):
                        issues.append(StructuralIssue("missing_pad_byte", "low", f"Odd-sized chunk before offset {pos} is not followed by the mandatory pad byte."))
                        pos -= 1
                        hdr = alt
                        cid_raw = hdr[:4]
                if not all(32 <= b < 127 for b in cid_raw):
                    issues.append(StructuralIssue(
                        "invalid_chunk_id", "medium",
                        f"Bytes at offset {pos} are not a valid chunk header; chunk parsing stopped.",
                        {"offset": pos, "bytes": cid_raw.hex(), "unparsed_bytes": size - pos}))
                    break
            cid = cid_raw.decode("ascii")
            csize = struct.unpack("<I", hdr[4:8])[0]
            payload_off = pos + 8
            if cid == "data" and riff_id == "RF64" and csize == 0xFFFFFFFF and st.ds64:
                csize = st.ds64["data_size"]
            available = max(0, min(csize, size - payload_off))
            st.chunks.append(ChunkInfo(cid, pos, csize, available))
            seen[cid] += 1
            order.append(cid)
            if available < csize:
                issues.append(StructuralIssue(
                    "truncated_chunk", "medium",
                    f"Chunk '{cid}' declares {csize} bytes but only {available} are present before end of file.",
                    {"chunk": cid, "declared": csize, "available": available}))
            payload = b""
            if cid != "data" and available <= MAX_META_CHUNK_BYTES:
                payload = f.read(available)
            if cid == "fmt " and st.fmt is None:
                st.fmt = _parse_fmt(payload, issues)
            elif cid == "data" and st.data_offset is None:
                st.data_offset, st.data_size, st.data_size_declared = payload_off, available, csize
            elif cid == "fact" and len(payload) >= 4:
                st.fact_samples = struct.unpack("<I", payload[:4])[0]
            elif cid == "LIST" and payload[:4] == b"INFO":
                st.info.update(_parse_info(payload[4:]))
            elif cid == "bext":
                st.bext = _parse_bext(payload)
            elif cid == "ds64" and len(payload) >= 24:
                rs, ds, sc = struct.unpack("<QQQ", payload[:24])
                st.ds64 = {"riff_size": rs, "data_size": ds, "sample_count": sc}
            prev_odd = bool(csize & 1)
            pos = payload_off + csize + (csize & 1)

    _post_checks(st, seen, order)
    return st


def _post_checks(st: WavStructure, seen: Counter, order: list[str]) -> None:
    issues = st.issues
    size = st.file_size
    if st.riff_id == "RIFF":
        riff_end = st.riff_size + 8
        if st.riff_size in (0, 0xFFFFFFFF) or (st.riff_size == 0xFFFFFFFF - 8):
            issues.append(StructuralIssue(
                "unfinalized_riff_size", "low",
                "RIFF size field holds a placeholder value; the writer never finalised the header.",
                {"declared": st.riff_size}))
        elif riff_end < size:
            issues.append(StructuralIssue(
                "trailing_data", "medium",
                f"{size - riff_end} bytes follow the end of the RIFF structure declared in the header.",
                {"riff_end": riff_end, "file_size": size, "trailing_bytes": size - riff_end}))
        elif riff_end > size:
            issues.append(StructuralIssue(
                "riff_size_exceeds_file", "medium",
                f"RIFF header declares {riff_end} bytes but the file has {size}; the file appears truncated.",
                {"riff_end": riff_end, "file_size": size}))
    if st.fmt is None:
        issues.append(StructuralIssue("missing_fmt", "high", "No usable 'fmt ' chunk was found."))
    else:
        _validate_fmt(st.fmt, issues)
    if st.data_offset is None:
        issues.append(StructuralIssue("missing_data", "high", "No 'data' chunk was found."))
    for cid in ("fmt ", "data"):
        if seen[cid] > 1:
            issues.append(StructuralIssue(
                f"multiple_{cid.strip()}_chunks", "high",
                f"The file contains {seen[cid]} '{cid}' chunks; standard writers produce exactly one.",
                {"count": seen[cid]}))
    if "fmt " in order and "data" in order and order.index("fmt ") > order.index("data"):
        issues.append(StructuralIssue("fmt_after_data", "low", "The 'fmt ' chunk appears after the 'data' chunk (non-standard ordering)."))
    if st.data_size_declared in (0xFFFFFFFF,) or (st.data_size_declared == 0 and st.data_size == 0 and size > 100):
        issues.append(StructuralIssue("unfinalized_data_size", "low", "The data chunk size is a placeholder; the writer never finalised it."))
    if st.fmt and st.fmt.block_align and st.data_size is not None and st.data_size % st.fmt.block_align:
        issues.append(StructuralIssue(
            "partial_sample_frame", "low",
            f"Data size {st.data_size} is not a multiple of the block alignment {st.fmt.block_align}; the last sample frame is incomplete.",
            {"remainder_bytes": st.data_size % st.fmt.block_align}))
    if st.fact_samples is not None and st.fmt and st.fmt.effective_tag == 1:
        frames = st.frame_count
        if frames is not None and st.fact_samples != frames:
            issues.append(StructuralIssue(
                "fact_mismatch", "low",
                f"'fact' chunk declares {st.fact_samples} sample frames; the data chunk holds {frames}.",
                {"fact": st.fact_samples, "data_frames": frames}))
    known = {"fmt ", "data", "fact", "LIST", "bext", "ds64", "JUNK", "junk", "PAD ", "cue ", "smpl", "inst", "id3 ", "ID3 ", "iXML", "axml", "acid", "PEAK", "regn", "umid", "_PMX", "minf", "elm1"}
    unknown = sorted({c.chunk_id for c in st.chunks} - known)
    if unknown:
        issues.append(StructuralIssue("unrecognised_chunks", "info", f"Chunks not interpreted by this parser: {', '.join(unknown)}.", {"chunks": unknown}))
