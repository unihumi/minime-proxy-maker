"""Leistung: Hardware-Beschleunigung und Prozessprioritaet.

- Hardware-Encoder werden beim ersten Gebrauch mit einem Mini-Test-Encode
  geprueft (funktioniert nur, was der Rechner wirklich kann) und gemerkt.
  * macOS (Apple Silicon): ProRes ueber die ProRes-Einheit (prores_videotoolbox),
    H.264 ueber VideoToolbox
  * Windows: H.264 ueber NVENC (NVIDIA), Quick Sync (Intel) oder AMF (AMD)
  * ProRes, DNxHR und CineForm haben unter Windows keinen Hardware-Encoder
- Decodieren: "-hwaccel auto" fuer H.264/HEVC (und ProRes auf dem Mac).
  FFmpeg faellt selbst auf die CPU zurueck, wenn die GPU ein Format
  (z.B. 4:2:2 10 Bit) nicht kann.
- Prioritaet "low" (Schonend) / "normal" (Maximal) fuer alle Encoder-Prozesse.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import weakref
from typing import Optional

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# --------------------------------------------------------------- Prioritaet
_mode = "low"
_procs: "weakref.WeakSet[subprocess.Popen]" = weakref.WeakSet()
_plock = threading.Lock()


def _apply(proc: subprocess.Popen) -> None:
    if not psutil or proc.poll() is not None:
        return
    try:
        p = psutil.Process(proc.pid)
        if sys.platform == "win32":
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if _mode == "low"
                   else psutil.NORMAL_PRIORITY_CLASS)
        else:
            # Hinweis: Unter macOS kann ein Prozess ohne Admin-Rechte nicht
            # zurueck auf "normal" - gilt dann fuer die naechsten Dateien.
            p.nice(10 if _mode == "low" else 0)
    except Exception:
        pass


def register(proc: subprocess.Popen) -> subprocess.Popen:
    """Jeden gestarteten Encoder/Decoder hier anmelden."""
    with _plock:
        _procs.add(proc)
    _apply(proc)
    return proc


def set_mode(mode: str) -> None:
    global _mode
    _mode = "normal" if mode == "normal" else "low"
    with _plock:
        procs = list(_procs)
    for p in procs:
        _apply(p)


def mode() -> str:
    return _mode


# ---------------------------------------------------------- Hardware-Encoder
_cache: dict[str, Optional[list[str]]] = {}
_clock = threading.Lock()


def _works(ffmpeg: str, args: list[str]) -> bool:
    try:
        r = subprocess.run(
            [ffmpeg, "-v", "error", "-f", "lavfi", "-i",
             "testsrc2=s=320x180:r=25", "-frames:v", "5", *args, "-f", "null", "-"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def _candidates(codec: str) -> list[list[str]]:
    if codec == "prores" and sys.platform == "darwin":
        return [["-c:v", "prores_videotoolbox", "-profile:v", prof, "-pix_fmt", pix]
                for pix in ("p210le", "nv12") for prof in ("proxy", "0")]
    if codec == "h264":
        if sys.platform == "darwin":
            return [["-c:v", "h264_videotoolbox", "-q:v", "55", "-g", "12",
                     "-pix_fmt", "yuv420p"],
                    ["-c:v", "h264_videotoolbox", "-b:v", "8M", "-g", "12",
                     "-pix_fmt", "yuv420p"]]
        return [
            ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "23",
             "-b:v", "0", "-g", "12", "-bf", "0", "-profile:v", "high",
             "-pix_fmt", "yuv420p"],
            ["-c:v", "h264_qsv", "-global_quality", "23", "-g", "12", "-bf", "0",
             "-pix_fmt", "nv12"],
            ["-c:v", "h264_amf", "-rc", "cqp", "-qp_i", "22", "-qp_p", "24",
             "-g", "12", "-bf", "0", "-pix_fmt", "nv12"],
        ]
    return []


def hw_encoder(ffmpeg: str, codec: str) -> Optional[list[str]]:
    """Funktionierende Hardware-Encoder-Argumente fuer diesen Codec oder None."""
    with _clock:
        if codec not in _cache:
            _cache[codec] = next((a for a in _candidates(codec) if _works(ffmpeg, a)),
                                 None)
        return _cache[codec]


HWACCEL_CODECS = {"h264", "hevc"} | ({"prores"} if sys.platform == "darwin" else set())


def hwaccel_args(vcodec: str) -> list[str]:
    return ["-hwaccel", "auto"] if vcodec in HWACCEL_CODECS else []


def describe(ffmpeg: str) -> str:
    """Kurzbeschreibung fuer das Log, z.B. 'ProRes: CPU · H.264: h264_nvenc'."""
    parts = []
    for codec, label in (("prores", "ProRes"), ("h264", "H.264")):
        hw = hw_encoder(ffmpeg, codec)
        parts.append(f"{label}: {hw[1] if hw else 'CPU'}")
    return " · ".join(parts) + " · Decoder: GPU (auto)"
