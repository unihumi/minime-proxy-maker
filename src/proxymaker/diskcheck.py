"""Speicherplatz: Groesse der Proxies schaetzen und mit dem freien Platz am
Ziel vergleichen. Funktioniert auch mit Netzlaufwerken (Windows: Laufwerks-
buchstaben und \\\\server\\freigabe, macOS: eingebundene SMB/NFS-Freigaben).
NAS-Geraete melden manchmal den Platz des ganzen Volumes und ignorieren
Benutzerquoten - die Pruefung ist deshalb nur eine Warnung."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from . import core

# Ungefaehre Videobitrate in Mbit/s bei 1920x1080 und 29,97 fps
_MBPS_1080P30 = {"prores": 45.0, "dnxhr": 45.0, "cineform": 80.0, "h264": 25.0}
_AUDIO_MBPS = 2.4        # je Tonspur (PCM 24 Bit, Stereo, 48 kHz)
_RAW_RATIO = 0.25        # R3D/BRAW: Proxy ~ hoechstens ein Viertel der Quelle
_UNKNOWN_RATIO = 0.5     # Dauer unbekannt: grob die halbe Quellgroesse
_MARGIN = 1.15           # 15 % Reserve
_MIN_FREE = 512 * 1024 * 1024  # darunter bricht eine Datei sofort ab


@dataclass
class Shortage:
    location: str  # Ordner/Laufwerk, auf dem der Platz fehlt
    need: int      # geschaetzter Bedarf in Byte
    free: int      # frei in Byte


def existing_dir(path: Path) -> Path:
    """Naechster existierender Ordner (das Proxy-Ziel gibt es oft noch nicht)."""
    p = path
    while not p.exists() and p.parent != p:
        p = p.parent
    return p


def free_bytes(path: Path) -> Optional[int]:
    try:
        return shutil.disk_usage(existing_dir(path)).free
    except OSError:
        return None


def _volume(path: Path) -> tuple:
    d = existing_dir(path)
    try:
        dev = os.stat(d).st_dev
    except OSError:
        dev = None
    return (dev, d.anchor)


def estimate_one(ffmpeg: str, src: Path, min_size: tuple[int, int], codec: str) -> int:
    try:
        size = src.stat().st_size
    except OSError:
        return 0
    if core.is_r3d(src) or core.is_braw(src):
        # 1:4 -> 25 %, 1:2 -> 50 %, 1:1 -> 100 % der Quellgroesse (grosszuegig)
        return int(size * min(1.0, _RAW_RATIO * 4 / core.SCALE["divisor"]))
    info = core.probe(ffmpeg, src)
    if info is None:
        return 0  # keine Videodatei, wird uebersprungen
    if info.duration <= 0:
        return int(size * _UNKNOWN_RATIO)
    w, h = core.output_size(info.width, info.height, min_size, codec)
    fps = info.fps if info.fps > 0 else 30.0
    video = _MBPS_1080P30.get(codec, 45.0) * (w * h) / (1920 * 1080) * fps / 29.97
    audio = _AUDIO_MBPS * len(info.audio_codecs)
    return int((video + audio) * 1_000_000 / 8 * info.duration)


def check(ffmpeg: str, items: Iterable[tuple[Path, tuple[int, int], str]],
          cancelled: Callable[[], bool] = lambda: False) -> list[Shortage]:
    """Fehlt irgendwo Platz? Leere Liste = alles gut (oder nicht pruefbar)."""
    need: dict[tuple, int] = {}
    where: dict[tuple, Path] = {}
    for src, min_size, codec in items:
        if cancelled():
            return []
        dst = core.proxy_path(src)
        if dst.exists():
            continue  # wird uebersprungen
        key = _volume(dst.parent)
        need[key] = need.get(key, 0) + estimate_one(ffmpeg, src, min_size, codec)
        where.setdefault(key, dst.parent)
    out = []
    for key, n in need.items():
        n = int(n * _MARGIN)
        free = free_bytes(where[key])
        if free is not None and n > free:
            out.append(Shortage(str(existing_dir(where[key])), n, free))
    return out


def nearly_full(dst: Path) -> bool:
    """Notbremse vor jeder einzelnen Datei (auch fuer spaeter hinzugefuegte)."""
    free = free_bytes(dst.parent)
    return free is not None and free < _MIN_FREE


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1000
    return f"{n:.1f} TB"
