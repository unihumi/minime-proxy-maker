"""Blackmagic RAW (.braw) ueber das Hilfsprogramm brawpipe (Blackmagic RAW SDK).

brawpipe entwickelt die Frames direkt in reduzierter Aufloesung mit den
Kamera-Metadaten und reicht sie als RGB 16 Bit an FFmpeg weiter, das daraus
wie gewohnt ProRes 422 Proxy macht.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import accel
from . import core
from .paths import ROOT

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_EXE = "brawpipe.exe" if sys.platform == "win32" else "brawpipe"


def _candidates() -> list[Path]:
    base = ROOT
    exe_dir = Path(sys.executable).resolve().parent
    return [
        base / "brawlib",
        exe_dir.parent / "Resources" / "brawlib",   # macOS .app
        exe_dir / "brawlib",
    ]


def find() -> Optional[tuple[str, str]]:
    """(Pfad zu brawpipe, Bibliotheksordner) oder None."""
    for d in _candidates():
        exe = d / _EXE
        if exe.is_file():
            return str(exe), str(d)
    return None


@dataclass
class BrawInfo:
    width: int
    height: int
    fps: float
    frames: int
    timecode: Optional[str]
    audio_channels: int
    scaled_width: int
    scaled_height: int


def _decode_scale(f: float) -> int:
    """Kleinste Decode-Stufe, die noch mindestens die Zielgroesse liefert."""
    for s in (8, 4, 2):
        if 1 / s >= f - 1e-6:
            return s
    return 1


def _fps_arg(fps: float) -> str:
    for nominal in (24, 30, 48, 60, 120):
        ntsc = nominal * 1000 / 1001
        if abs(fps - ntsc) < 0.005:
            return f"{nominal * 1000}/1001"
    return f"{fps:.6f}".rstrip("0").rstrip(".")


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, creationflags=_NO_WINDOW,
                          timeout=timeout)


def probe(tool: tuple[str, str], src: Path, scale: int) -> BrawInfo:
    exe, lib = tool
    r = _run([exe, "info", lib, str(src), str(scale)], timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()
                           or f"brawpipe info: Exit-Code {r.returncode}")
    kv = {}
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    try:
        w, h = int(kv["width"]), int(kv["height"])
        return BrawInfo(
            width=w, height=h, fps=float(kv["fps"]), frames=int(kv["frames"]),
            timecode=kv.get("timecode") or None,
            audio_channels=int(kv.get("audio_channels", 0) or 0),
            scaled_width=int(kv.get("scaled_width", 0) or 0) or w // scale,
            scaled_height=int(kv.get("scaled_height", 0) or 0) or h // scale,
        )
    except (KeyError, ValueError):
        raise RuntimeError("BRAW-Metadaten unvollstaendig: " + ", ".join(kv))


def plan(tool: tuple[str, str], src: Path, min_size: tuple[int, int]) -> tuple[BrawInfo, int]:
    """Liest den Clip und waehlt die passende Decode-Stufe."""
    info = probe(tool, src, 8)  # schnell: Achtel-Aufloesung genuegt fuer Metadaten
    f = core.scale_factor(info.width, info.height, min_size)
    scale = _decode_scale(f)
    if scale != 8:
        info = probe(tool, src, scale)
    return info, scale


def encode(
    tool: tuple[str, str],
    ffmpeg: str,
    src: Path,
    min_size: tuple[int, int],
    on_progress: Callable[[float], None] = lambda f: None,
    is_cancelled: Callable[[], bool] = lambda: False,
    info_scale: Optional[tuple[BrawInfo, int]] = None,
    codec: str = core.DEFAULT_CODEC,
    cpu_only: bool = False,
) -> Path:
    exe, lib = tool
    info, scale = info_scale or plan(tool, src, min_size)
    w, h = core.output_size(info.width, info.height, min_size, codec)
    dst = core.proxy_path(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".partial")
    workdir = Path(tempfile.mkdtemp(prefix="proxymaker_braw_"))
    try:
        # 1) Ton als WAV (falls vorhanden)
        wav = None
        if info.audio_channels > 0:
            wav = workdir / "audio.wav"
            r = _run([exe, "audio", lib, str(src), str(wav)], timeout=3600)
            if r.returncode != 0 or not wav.exists() or wav.stat().st_size <= 44:
                wav = None

        # 2) Bild: brawpipe -> FFmpeg (ProRes 422 Proxy)
        vargs = core.codec_args(ffmpeg, codec, cpu_only)
        vf = (f"scale={w}:{h}:flags=bicubic:out_color_matrix=bt709:out_range=tv,"
              f"format={core.codec_pix_fmt(codec, vargs)},setsar=1")
        cmd = [
            ffmpeg, "-hide_banner", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb48le",
            "-s", f"{info.scaled_width}x{info.scaled_height}",
            "-framerate", _fps_arg(info.fps), "-i", "pipe:0",
        ]
        if wav:
            cmd += ["-i", str(wav)]
        cmd += ["-map", "0:v:0"]
        if wav:
            # WAV aus dem SDK -> bit-genau kopieren, Spur aktiv wie bei Resolve
            cmd += ["-map", "1:a:0", "-c:a", "copy", "-disposition:a", "default"]
        cmd += [
            "-vf", vf,
            *vargs,
            *core.COLOR_TAGS,
            *core.proxy_metadata(src, codec, min_size, "Blackmagic RAW SDK",
                                 encoder=vargs[1]),
        ]
        if info.timecode:
            cmd += ["-timecode", info.timecode]
        cmd += ["-progress", "pipe:1", "-nostats", "-f", "mov", str(tmp)]

        dec = accel.register(subprocess.Popen(
            [exe, "video", lib, str(src), str(scale)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, creationflags=_NO_WINDOW,
        ))
        enc = accel.register(subprocess.Popen(
            cmd, stdin=dec.stdout, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, creationflags=_NO_WINDOW,
        ))
        dec.stdout.close()  # type: ignore[union-attr]  # nur FFmpeg liest
        dec_err: list[bytes] = []
        t = threading.Thread(target=lambda: dec_err.append(dec.stderr.read()),  # type: ignore[union-attr]
                             daemon=True)
        t.start()

        duration = info.frames / info.fps if info.fps else 0
        tail: list[str] = []
        for raw in enc.stdout:  # type: ignore[union-attr]
            if is_cancelled():
                dec.kill()
                enc.kill()
                break
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("out_time_us="):
                try:
                    secs = int(line.split("=", 1)[1]) / 1_000_000
                    if duration > 0:
                        on_progress(max(0.0, min(0.999, secs / duration)))
                except ValueError:
                    pass
            elif "=" not in line or " " in line:
                tail.append(line)
                del tail[:-6]
        enc_code = enc.wait()
        dec_code = dec.wait()
        t.join(timeout=5)

        if is_cancelled():
            tmp.unlink(missing_ok=True)
            raise core.Cancelled()
        if dec_code != 0 or enc_code != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            tmp.unlink(missing_ok=True)
            msg = b"".join(dec_err).decode("utf-8", "replace").strip()
            raise RuntimeError(msg or "\n".join(tail[-3:])
                               or f"BRAW-Fehler (Decoder {dec_code}, FFmpeg {enc_code})")
        os.replace(tmp, dst)
        on_progress(1.0)
        return dst
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
