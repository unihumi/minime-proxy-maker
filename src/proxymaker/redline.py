"""R3D-Unterstuetzung ueber RED REDline (Teil von REDCINE-X PRO, kostenlos).

FFmpeg kann REDCODE RAW nicht decodieren. Fuer .R3D-Dateien ruft Proxy Maker
deshalb REDline auf, das direkt ProRes 422 Proxy schreibt.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import accel
from . import core

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
PRORES_PROXY = 3  # --PRcodec 3 = Apple ProRes 422 Proxy


def find_redline(saved: Optional[str] = None) -> Optional[str]:
    cands: list[str] = []
    if saved:
        cands.append(saved)
    for name in ("REDline", "redline", "REDline.exe"):
        w = shutil.which(name)
        if w:
            cands.append(w)
    if sys.platform == "darwin":
        for pat in (
            "/Applications/REDCINE-X*/*.app/Contents/MacOS/REDline",
            "/Applications/REDCINE-X*/REDline",
            "/Applications/*.app/Contents/MacOS/REDline",
            "/usr/local/bin/REDline",
        ):
            cands += sorted(glob.glob(pat), reverse=True)
    elif sys.platform == "win32":
        for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
            base = os.environ.get(env)
            if base:
                for pat in ("RED*\\REDline.exe", "RED*\\*\\REDline.exe"):
                    cands += sorted(glob.glob(os.path.join(base, pat)), reverse=True)
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def _run(cmd: list[str], timeout: int = 120) -> str:
    try:
        return subprocess.run(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, creationflags=_NO_WINDOW, timeout=timeout,
        ).stdout.decode("utf-8", "replace")
    except Exception:
        return ""


_fmt_cache: dict[str, Optional[int]] = {}
_gpu_cache: dict[str, list[str]] = {}


def gpu_args(redline: str) -> list[str]:
    """Liest aus der REDline-Hilfe die Option fuer GPU-Entwicklung
    (CUDA unter Windows, Metal auf dem Mac, sonst OpenCL)."""
    if redline in _gpu_cache:
        return _gpu_cache[redline]
    helptext = _run([redline]) + "\n" + _run([redline, "--help"])
    args: list[str] = []
    m = re.search(r"(--gpuPlatform)\b", helptext)
    if m:
        block = helptext[m.start(): m.start() + 600]
        nxt = re.search(r"\n\s*--(?!gpuPlatform)\w", block)
        block = block[: nxt.start()] if nxt else block
        found = {name.lower(): num for num, name in
                 re.findall(r"(\d+)\s*[=:]\s*(CUDA|Metal|OpenCL)", block, re.I)}
        found.update({name.lower(): num for name, num in
                      re.findall(r"(CUDA|Metal|OpenCL)\s*[=:]\s*(\d+)", block, re.I)})
        order = (["metal", "opencl"] if sys.platform == "darwin"
                 else ["cuda", "opencl"])
        for name in order:
            if name in found:
                args = ["--gpuPlatform", found[name]]
                break
    _gpu_cache[redline] = args
    return args


def prores_format(redline: str) -> Optional[int]:
    """Liest aus der REDline-Hilfe die --format-Nummer fuer Apple ProRes."""
    if redline in _fmt_cache:
        return _fmt_cache[redline]
    helptext = _run([redline]) + "\n" + _run([redline, "--help"])
    num: Optional[int] = None
    for m in re.finditer(r"--format\b", helptext):
        block = helptext[m.start(): m.start() + 900]
        nxt = re.search(r"\n\s*--(?!format)\w", block)
        if nxt:
            block = block[: nxt.start()]
        hit = (re.search(r"(?:Apple\s*)?ProRes\s*[=:]\s*(\d+)", block, re.I)
               or re.search(r"(\d+)\s*[=:]\s*(?:Apple\s*)?ProRes", block, re.I))
        if hit:
            num = int(hit.group(1))
            break
    if num is None and "PRcodec" in helptext:
        num = 201  # bekannter Wert aktueller REDline-Versionen
    _fmt_cache[redline] = num
    return num


@dataclass
class R3DInfo:
    width: int
    height: int
    frames: int  # 0 = unbekannt


def probe(redline: str, src: Path) -> Optional[R3DInfo]:
    out = _run([redline, "--i", str(src), "--printMeta", "1"])
    w = re.search(r"(?im)^\s*(?:frame\s*)?width\s*[:=]\s*(\d+)", out)
    h = re.search(r"(?im)^\s*(?:frame\s*)?height\s*[:=]\s*(\d+)", out)
    if w and h:
        width, height = int(w.group(1)), int(h.group(1))
    else:
        r = re.search(r"(?i)resolution\s*[:=]\s*(\d{3,5})\s*x\s*(\d{3,5})", out)
        if not r:
            return None
        width, height = int(r.group(1)), int(r.group(2))
    f = re.search(r"(?im)^\s*(?:total\s*)?frames?(?:\s*count)?\s*[:=]\s*(\d+)", out)
    return R3DInfo(width, height, int(f.group(1)) if f else 0)


_RE_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
# REDline (Windows) meldet z.B. "Export Job frame complete. 140 0.992908"
_RE_JOB = re.compile(r"frame complete\.?\s+\d+\s+([01](?:\.\d+)?)\b", re.I)
_RE_OF = re.compile(r"(\d+)\s*(?:of|/)\s*(\d+)", re.I)
_RE_FRAME = re.compile(r"frame\D{0,3}(\d+)", re.I)


def _progress(line: str, frames: int) -> Optional[float]:
    m = _RE_JOB.search(line)
    if m:
        return float(m.group(1))
    line = re.sub(r"^\[[\d-]+\]\s*(?:<\w+>\s*)?", "", line)  # Zeitstempel weg
    m = _RE_PCT.search(line)
    if m:
        return float(m.group(1)) / 100
    m = _RE_OF.search(line)
    if m and int(m.group(2)) > 0:
        return int(m.group(1)) / int(m.group(2))
    if frames:
        m = _RE_FRAME.search(line)
        if m:
            return int(m.group(1)) / frames
    return None


VIDEO_OUT_EXT = {".mov", ".mxf", ".mp4"}


def _find_output(tmpdir: Path, src: Path, started: float) -> Optional[Path]:
    """Sucht die REDline-Ausgabe: zuerst im Temp-Ordner, dann an Orten,
    an die REDline sie stattdessen geschrieben haben koennte."""
    cands = [p for p in tmpdir.rglob("*")
             if p.is_file() and p.suffix.lower() in VIDEO_OUT_EXT]
    if not cands:
        for d in {src.parent, Path.cwd(), tmpdir.parent}:
            try:
                for p in d.iterdir():
                    if (p.is_file() and p.suffix.lower() in VIDEO_OUT_EXT
                            and p.stem.startswith(src.stem)
                            and p.stat().st_mtime >= started - 2):
                        cands.append(p)
            except OSError:
                pass
    cands = [p for p in cands if p.stat().st_size > 0]
    return max(cands, key=lambda p: p.stat().st_size) if cands else None


def _run_redline(cmd, tmpdir, src, frames, on_progress, is_cancelled):
    """Startet REDline; liefert (Ausgabedatei oder None, Exit-Code, letzte Zeilen)."""
    import time

    shutil.rmtree(tmpdir, ignore_errors=True)
    tmpdir.mkdir(parents=True)
    started = time.time()
    proc = accel.register(subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, creationflags=_NO_WINDOW))
    tail: list[str] = []
    buf = b""
    best = 0.0
    try:
        while True:
            if is_cancelled():
                proc.terminate()
                break
            chunk = proc.stdout.read1(4096)  # type: ignore[union-attr]
            if not chunk:
                break
            buf += chunk
            parts = re.split(rb"[\r\n]", buf)
            buf = parts.pop()
            for raw in parts:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                tail.append(line)
                del tail[:-12]
                p = _progress(line, frames)
                if p is not None and p > best:
                    best = min(p, 0.999)
                    on_progress(best * 0.85)
        code = proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    if is_cancelled():
        raise core.Cancelled()
    return _find_output(tmpdir, src, started), code, tail


def encode(
    redline: str,
    fmt: int,
    src: Path,
    info: R3DInfo,
    min_size: tuple[int, int],
    on_progress: Callable[[float], None] = lambda f: None,
    is_cancelled: Callable[[], bool] = lambda: False,
    ffmpeg: Optional[str] = None,
    on_log: Callable[[str], None] = lambda s: None,
    codec: str = core.DEFAULT_CODEC,
    cpu_only: bool = False,
) -> Path:
    """Zwei Schritte:
    1. REDline entwickelt das R3D als ProRes-Zwischendatei (halbe/volle Aufl.).
    2. FFmpeg skaliert exakt auf die Zielgroesse und schreibt ProRes Proxy.

    Manche Clips tragen einen Frame Guide (z.B. 9:16) in den Metadaten, auf
    den REDline dann zuschneidet. Deshalb wird das volle Sensorbild explizit
    angefordert und das Seitenverhaeltnis der Zwischendatei geprueft; passt
    es nicht, folgt ein weiterer Versuch mit anderen Optionen.
    """
    if not ffmpeg:
        raise RuntimeError("FFmpeg fehlt")
    dst = core.proxy_path(src)
    W, H = info.width, info.height
    w, h = core.output_size(W, H, min_size, codec)
    f = core.scale_factor(W, H, min_size)
    res = 2 if f <= 0.5001 else 1  # 2 = "half high" (gute Qualitaet)
    tmpdir = dst.parent / f".partial_{src.stem}"
    gpu = [] if cpu_only else gpu_args(redline)
    base = [redline, "--i", str(src), "--outDir", str(tmpdir), "--o", src.stem,
            "--format", str(fmt), "--PRcodec", "2", "--res", str(res), *gpu]
    full = ["--cropX", "0", "--cropY", "0", "--cropW", str(W), "--cropH", str(H)]
    fit = ["--resizeX", str(W // res // 2 * 2), "--resizeY", str(H // res // 2 * 2),
           "--fit", "3"]
    attempts = [
        ("Metadaten + volles Bild", base + ["--useMeta"] + full),
        ("Metadaten + volles Bild + feste Groesse", base + ["--useMeta"] + full + fit),
        ("ohne Clip-Metadaten", base),
    ]
    want = W / H
    report: list[str] = []
    try:
        for n, (label, cmd) in enumerate(attempts, 1):
            out, code, tail = _run_redline(cmd, tmpdir, src, info.frames,
                                           on_progress, is_cancelled)
            mid = core.probe(ffmpeg, out) if out else None
            if mid is None:
                report.append(f"Versuch {n} ({label}): keine Ausgabe, Exit-Code {code}"
                              + (f" – {tail[-1]}" if tail else ""))
                continue
            got = mid.width / mid.height
            if abs(got - want) / want > 0.02:
                msg = (f"Versuch {n} ({label}): REDline lieferte "
                       f"{mid.width}x{mid.height} statt Seitenverhaeltnis {W}x{H}")
                report.append(msg)
                on_log(msg + " – neuer Versuch")
                continue
            on_log(f"REDline{' (GPU)' if gpu else ''} → {mid.width}x{mid.height}, "
                   f"FFmpeg → {w}x{h}" + (f"  [{label}]" if n > 1 else ""))
            core.encode(ffmpeg, out, mid,
                        lambda p: on_progress(0.85 + 0.15 * p), is_cancelled,
                        dst=dst, target=(w, h), codec=codec, source=src,
                        decoder="REDline (REDCINE-X PRO)" + (" GPU" if gpu else ""),
                        cpu_only=cpu_only)
            on_progress(1.0)
            return dst
        raise RuntimeError(
            "REDline lieferte kein Bild im richtigen Seitenverhaeltnis.\n"
            + "\n".join(report)
            + "\nBefehl: " + subprocess.list2cmdline(attempts[0][1]))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
