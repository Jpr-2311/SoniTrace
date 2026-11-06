import struct

import numpy as np
import pytest
import soundfile as sf

from conftest import SR, fmt_payload, make_signal, needs_ffmpeg, riff_bytes, write_wav
from sonictrace.errors import MalformedFileError
from sonictrace.parsers.codec_inspector import inspect_flac, inspect_mp3, inspect_ogg, inspect_structure, parse_mpeg_header
from sonictrace.parsers.wav_parser import parse_wav
from sonictrace.utils.tools import run_tool
from sonictrace.utils.validation import sniff_file


def codes(st):
    return {i.code for i in st.issues}


def test_wav_chunks_info_and_consistency(tmp_path):
    info = b"INFO" + b"ISFT" + struct.pack("<I", 14) + b"Lavf60.16.100\x00"
    data = np.arange(100, dtype="<i2").tobytes()
    p = tmp_path / "a.wav"
    p.write_bytes(riff_bytes([(b"fmt ", fmt_payload()), (b"LIST", info), (b"data", data)]))
    st = parse_wav(p)
    assert [c.chunk_id for c in st.chunks] == ["fmt ", "LIST", "data"]
    assert st.fmt.sample_rate == 8000 and st.fmt.bits_per_sample == 16
    assert st.info["software"] == "Lavf60.16.100"
    assert st.frame_count == 100
    assert not [i for i in st.issues if i.severity in ("medium", "high")]


def test_wav_trailing_data_and_bad_byte_rate(tmp_path):
    bad_fmt = struct.pack("<HHIIHH", 1, 1, 8000, 9999, 2, 16)
    p = tmp_path / "b.wav"
    p.write_bytes(riff_bytes([(b"fmt ", bad_fmt), (b"data", b"\x00\x01" * 50)]) + b"APPENDEDJUNK")
    c = codes(parse_wav(p))
    assert "trailing_data" in c and "byte_rate_mismatch" in c


def test_wav_truncated_and_multiple_data(tmp_path):
    p = tmp_path / "c.wav"
    raw = riff_bytes([(b"fmt ", fmt_payload()), (b"data", b"\x00" * 400), (b"data", b"\x00" * 40)])
    p.write_bytes(raw[:-20])
    c = codes(parse_wav(p))
    assert "multiple_data_chunks" in c
    assert "truncated_chunk" in c or "riff_size_exceeds_file" in c


def test_wav_missing_fmt_and_bext(tmp_path):
    bext = bytearray(602)
    bext[0:11] = b"Field notes"
    bext[256:263] = b"RecorderX"[:7]
    bext += b"A=PCM,F=48000,W=24,M=mono\r\n"
    p = tmp_path / "d.wav"
    p.write_bytes(riff_bytes([(b"bext", bytes(bext)), (b"data", b"\x00" * 10)]))
    st = parse_wav(p)
    assert "missing_fmt" in codes(st)
    assert st.bext["description"] == "Field notes"
    assert "A=PCM" in st.bext["coding_history"]


def test_not_riff_raises(tmp_path):
    p = tmp_path / "x.wav"
    p.write_bytes(b"NOTAWAVEFILE" * 3)
    with pytest.raises(MalformedFileError):
        parse_wav(p)


def test_mpeg_header_decoding():
    h = parse_mpeg_header(bytes([0xFF, 0xFB, 0x90, 0x64]))  # MPEG-1 L3 128 kbps 44.1 kHz
    assert h["version"] == "1" and h["layer"] == 3 and h["bitrate"] == 128 and h["sample_rate"] == 44100
    assert h["length"] == 417
    assert parse_mpeg_header(b"\x00\x00\x00\x00") is None


def test_sniff_by_content_not_extension(tmp_path):
    p = tmp_path / "audio.mp3"
    sf.write(str(p), make_signal(duration=0.5), SR, subtype="PCM_16", format="WAV")
    assert sniff_file(p) == "wav"


@needs_ffmpeg
def test_mp3_lame_tag_and_concatenation(tmp_path):
    w = write_wav(tmp_path / "s.wav", make_signal(duration=2.0))
    m = tmp_path / "s.mp3"
    run_tool(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(w), "-codec:a", "libmp3lame", "-b:a", "64k", str(m)])
    rep = inspect_mp3(m)
    assert rep.details["sample_rate"] == 44100 and rep.details["frames"] > 50
    assert rep.details["vbr_header"] is not None and "encoder_delay" in rep.details["vbr_header"]
    assert not [i for i in rep.issues if i.severity == "high"]
    cat = tmp_path / "cat.mp3"
    cat.write_bytes(m.read_bytes() + m.read_bytes())  # byte-level concatenation
    c = codes(inspect_mp3(cat))
    assert "midstream_vbr_header" in c or "sync_gap" in c


def test_flac_md5_verification(tmp_path):
    p = tmp_path / "a.flac"
    sf.write(str(p), make_signal(duration=1.0), SR, subtype="PCM_16", format="FLAC")
    rep = inspect_flac(p)
    assert rep.details["streaminfo"]["sample_rate"] == SR
    assert rep.details["md5_verification"] in ("match", "not_available")
    raw = bytearray(p.read_bytes())
    pos = rep.details["audio_offset"] + 2000
    raw[pos] ^= 0xFF
    q = tmp_path / "tampered.flac"
    q.write_bytes(bytes(raw))
    rep2 = inspect_flac(q)
    if rep.details["md5_verification"] == "match":
        assert rep2.details["md5_verification"] in ("mismatch", "not_performed") or "md5_decode_failed" in codes(rep2)


def test_ogg_crc_detects_byte_change(tmp_path):
    p = tmp_path / "a.ogg"
    sf.write(str(p), make_signal(duration=1.0).astype(np.float32) / 32768, SR, format="OGG", subtype="VORBIS")
    rep = inspect_ogg(p)
    assert "ogg_crc_mismatch" not in codes(rep)
    raw = bytearray(p.read_bytes())
    raw[len(raw) // 2] ^= 0x55
    q = tmp_path / "b.ogg"
    q.write_bytes(bytes(raw))
    assert "ogg_crc_mismatch" in codes(inspect_ogg(q))


def test_dispatch_unknown_container(tmp_path):
    p = tmp_path / "u.bin"
    p.write_bytes(b"\x01\x02\x03" * 100)
    rep = inspect_structure(p, sniff_file(p))
    assert rep.container == "unknown" and "unknown_container" in codes(rep)
