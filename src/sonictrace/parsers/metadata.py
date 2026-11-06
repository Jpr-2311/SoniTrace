"""Technical metadata extraction (FFprobe when available) and software-signature classification."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ..utils.tools import find_tool, run_tool
from ..utils.validation import CONTAINER_NAMES, EXTENSION_CONTAINERS
from .common import StructureReport

SOFTWARE_PATTERNS = [
    (r"\bLav[fc]\d|\bffmpeg|\blibav", "FFmpeg (libavformat/libavcodec)", "transcoder"),
    (r"\bLAME", "LAME MP3 encoder", "codec"),
    (r"libFLAC", "libFLAC reference encoder", "codec"),
    (r"libVorbis|Xiph\.Org", "libvorbis", "codec"),
    (r"libopus|opusenc", "libopus", "codec"),
    (r"Audacity", "Audacity", "editor"),
    (r"Audition", "Adobe Audition", "editor"),
    (r"Sound ?Forge", "Sound Forge", "editor"),
    (r"Pro ?Tools", "Pro Tools", "editor"),
    (r"REAPER", "REAPER", "editor"),
    (r"GarageBand", "GarageBand", "editor"),
    (r"Logic", "Logic Pro", "editor"),
    (r"Wavelab|WaveLab", "WaveLab", "editor"),
    (r"iTunes", "iTunes/Apple encoder", "codec"),
    (r"\bSoX\b|\bsox\b", "SoX", "transcoder"),
    (r"libsndfile", "libsndfile", "library"),
]


def probe_ffprobe(path: str | Path) -> dict:
    """Run FFprobe in JSON mode. Never raises for probe failures; failure is reported as data."""
    if find_tool("ffprobe") is None:
        return {"available": False}
    res = run_tool(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], timeout=120)
    if res.returncode != 0:
        return {"available": True, "ok": False, "error": res.stderr.decode("utf-8", "replace").strip()[-600:]}
    try:
        data = json.loads(res.stdout.decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError as exc:
        return {"available": True, "ok": False, "error": f"unparseable ffprobe output: {exc}"}
    data["available"] = True
    data["ok"] = True
    return data


def classify_signatures(signatures: list[str]) -> list[dict]:
    out, seen = [], set()
    for sig in signatures:
        if not sig:
            continue
        for pattern, product, category in SOFTWARE_PATTERNS:
            if re.search(pattern, sig) and (product, sig) not in seen:
                seen.add((product, sig))
                out.append({"signature": sig[:200], "product": product, "category": category})
        if not any(re.search(p, sig) for p, _, _ in SOFTWARE_PATTERNS) and (None, sig) not in seen:
            seen.add((None, sig))
            out.append({"signature": sig[:200], "product": None, "category": "unclassified"})
    return out


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def build_metadata(path: Path, container: str, structure: StructureReport, ffprobe: dict) -> dict:
    st = path.stat()
    ext = path.suffix.lower()
    meta: dict = {
        "identity": {
            "file_name": path.name,
            "path": str(path),
            "size_bytes": st.st_size,
            "extension": ext,
            "container_from_content": container,
            "container_description": CONTAINER_NAMES.get(container, container),
            "container_from_extension": EXTENSION_CONTAINERS.get(ext),
            "filesystem_modified_utc": _iso(st.st_mtime),
            "filesystem_changed_or_created_utc": _iso(st.st_ctime),
        },
        "ffprobe": {"available": ffprobe.get("available", False), "ok": ffprobe.get("ok", False)},
        "technical": {},
        "tags": dict(structure.tags),
    }
    if ffprobe.get("ok"):
        fmt = ffprobe.get("format", {})
        streams = [s for s in ffprobe.get("streams", []) if s.get("codec_type") == "audio"]
        meta["ffprobe"]["format_name"] = fmt.get("format_name")
        meta["ffprobe"]["format_long_name"] = fmt.get("format_long_name")
        meta["ffprobe"]["audio_streams"] = len(streams)
        meta["ffprobe"]["total_streams"] = len(ffprobe.get("streams", []))
        if streams:
            s = streams[0]
            meta["technical"] = {
                "codec_name": s.get("codec_name"),
                "codec_long_name": s.get("codec_long_name"),
                "sample_rate": int(s["sample_rate"]) if s.get("sample_rate") else None,
                "channels": s.get("channels"),
                "channel_layout": s.get("channel_layout"),
                "sample_fmt": s.get("sample_fmt"),
                "bits_per_sample": s.get("bits_per_sample"),
                "bits_per_raw_sample": s.get("bits_per_raw_sample"),
                "stream_bit_rate": int(s["bit_rate"]) if s.get("bit_rate", "").isdigit() else None,
                "stream_duration_s": float(s["duration"]) if s.get("duration") else None,
                "format_bit_rate": int(fmt["bit_rate"]) if str(fmt.get("bit_rate", "")).isdigit() else None,
                "format_duration_s": float(fmt["duration"]) if fmt.get("duration") else None,
            }
            for k, v in (s.get("tags") or {}).items():
                meta["tags"].setdefault(f"stream:{k}", v)
        for k, v in (fmt.get("tags") or {}).items():
            meta["tags"].setdefault(f"format:{k}", v)
    elif ffprobe.get("available"):
        meta["ffprobe"]["error"] = ffprobe.get("error")

    sigs = list(structure.signatures)
    for k, v in meta["tags"].items():
        if k.split(":")[-1].lower() in ("encoder", "encoded_by", "software", "tsse", "tenc", "vendor", "©too"):
            sigs.append(str(v))
    meta["software_signatures"] = classify_signatures(sigs)
    return meta
