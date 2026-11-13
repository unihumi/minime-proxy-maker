"""Proxy Maker - Encoding-Logik (ohne GUI).

Erzeugt ProRes-Proxy-Dateien in Viertelaufloesung in einem Unterordner
"Proxy" neben der jeweiligen Quelldatei.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from . import accel
from .paths import ROOT

PROXY_DIRNAME = "Proxy"
DEFAULT_MIN = (960, 540)  # Standard-Mindestbreite/-hoehe (einzeln geprueft)

# Nur diese Container werden ueberhaupt angefasst; danach prueft FFmpeg,
# ob wirklich eine Videospur enthalten ist.
VIDEO_EXT = {
    ".mp4", ".mov", ".mxf", ".m4v", ".mts", ".m2ts", ".m2t", ".ts", ".avi",
    ".mkv", ".webm", ".mpg", ".mpeg", ".wmv", ".3gp", ".dv", ".vob", ".insv",
    ".r3d",   # RED - wird ueber REDline encodiert, siehe redline.py
    ".braw",  # Blackmagic RAW - ueber brawpipe, siehe braw.py
}

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _bundle_dir() -> Path:
    return ROOT


def find_ffmpeg() -> Optional[str]:
    """Mitgeliefertes FFmpeg (Ordner ffbin, beim Build geladen), sonst PATH."""
    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    bundled = _bundle_dir() / "ffbin" / exe
    if bundled.is_file():
        return str(bundled)
    return shutil.which("ffmpeg")


def ffmpeg_version(ffmpeg: str) -> str:
    try:
        out = subprocess.run(
            [ffmpeg, "-hide_banner", "-version"], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=_NO_WINDOW, timeout=20,
        ).stdout.decode("utf-8", "replace")
        first = out.splitlines()[0] if out else ""
        m = re.search(r"version\s+(\S+)", first)
        return m.group(1) if m else first.strip()
    except Exception:
        return "?"


def _is_candidate(p: Path) -> bool:
    return (
        p.suffix.lower() in VIDEO_EXT
        and not p.name.startswith(".")  # u.a. macOS-"._"-Dateien auf Karten
    )


_RE_SEGMENT = re.compile(r"^(.*)_(\d{3})$")


def _is_r3d_followup_segment(p: Path) -> bool:
    """RED teilt lange Clips in _001.R3D, _002.R3D ... - nur _001 verarbeiten."""
    if p.suffix.lower() != ".r3d":
        return False
    m = _RE_SEGMENT.match(p.stem)
    if not m or int(m.group(2)) == 1:
        return False
    return (p.parent / f"{m.group(1)}_001{p.suffix}").exists()


def is_r3d(p: Path) -> bool:
    return p.suffix.lower() == ".r3d"


def is_braw(p: Path) -> bool:
    return p.suffix.lower() == ".braw"


def collect(paths: Iterable[str | os.PathLike]) -> list[Path]:
    """Dateien/Ordner -> sortierte Liste moeglicher Videodateien."""
    found: dict[str, Path] = {}
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for root, dirs, files in os.walk(p):
                # vorhandene Proxy-Ordner und versteckte Ordner auslassen
                dirs[:] = sorted(
                    d for d in dirs
                    if d.lower() != PROXY_DIRNAME.lower() and not d.startswith(".")
                )
                for name in sorted(files):
                    f = Path(root) / name
                    if _is_candidate(f):
                        found.setdefault(str(f), f)
        elif p.is_file() and _is_candidate(p):
            found.setdefault(str(p), p)
    return [f for f in found.values() if not _is_r3d_followup_segment(f)]


def proxy_path(src: Path) -> Path:
    return src.parent / PROXY_DIRNAME / (src.stem + ".mov")


@dataclass
class MediaInfo:
    width: int
    height: int
    duration: float  # Sekunden, 0 wenn unbekannt
    timecode: Optional[str]
    vcodec: str = ""                                     # z.B. "h264", "prores_raw"
    color: tuple = ("", "", "")                          # (Matrix, Primaries, Transfer) der Quelle
    audio_codecs: list = field(default_factory=list)     # je Tonspur, in Reihenfolge
    wb: Optional[tuple] = None                           # (R, B)-Verstaerkung, nur RAW


_RE_VIDEO = re.compile(r"Stream #\d+:\d+.*?: Video: .*?\b(\d{2,5})x(\d{2,5})\b")
_RE_VCODEC = re.compile(r"Stream #\d+:\d+.*?: Video: (\w+)")
_RE_ACODEC = re.compile(r"Stream #\d+:\d+.*?: Audio: (\w+)")
# z.B. "yuv420p10le(tv, bt2020nc/bt2020/arib-std-b67, progressive)" oder "(tv, bt709)"
_RE_COLOR = re.compile(r"\((?:tv|pc)(?:,\s*([\w-]+)(?:/([\w-]+)/([\w-]+))?)?")
_RE_DUR = re.compile(r"Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)")
_RE_TC = re.compile(r"timecode\s*:\s*(\d\d:\d\d:\d\d[:;]\d\d)")


def probe(ffmpeg: str, src: Path) -> Optional[MediaInfo]:
    """Liest Aufloesung/Dauer/Timecode. None = keine Videodatei."""
    try:
        out = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(src)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, creationflags=_NO_WINDOW, timeout=120,
        ).stdout.decode("utf-8", "replace")
    except Exception:
        return None
    size = None
    color = ("", "", "")
    vcodec = ""
    acodecs: list[str] = []
    for line in out.splitlines():
        if "attached pic" in line:
            continue  # Cover-Bild einer Audiodatei
        a = _RE_ACODEC.search(line)
        if a:
            acodecs.append(a.group(1))
            continue
        m = _RE_VIDEO.search(line)
        if m and size is None:
            size = (int(m.group(1)), int(m.group(2)))
            v = _RE_VCODEC.search(line)
            vcodec = v.group(1) if v else ""
            c = _RE_COLOR.search(line)
            if c and c.group(1) and c.group(1) != "progressive":
                mat = c.group(1)
                color = (mat, c.group(2) or mat, c.group(3) or mat)
    if not size:
        return None
    dur = 0.0
    m = _RE_DUR.search(out)
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = _RE_TC.search(out)
    return MediaInfo(size[0], size[1], dur, m.group(1) if m else None,
                     vcodec, color, acodecs)


# Tonspuren, die bit-genau ins MOV kopiert werden koennen; alles andere -> PCM 24 Bit
AUDIO_COPY = {
    "pcm_s16le", "pcm_s16be", "pcm_s24le", "pcm_s24be", "pcm_s32le", "pcm_s32be",
    "pcm_f32le", "pcm_f32be", "pcm_f64le", "pcm_f64be", "pcm_s8", "pcm_u8",
    "aac", "alac",
}


def audio_args(codecs: list[str]) -> list[str]:
    """Pro Tonspur: kopieren, wenn MOV es aufnehmen kann, sonst PCM 24 Bit.
    Alle Spuren aktiv und unabhaengig (eigene Gruppe) - wie bei Resolve."""
    args: list[str] = []
    for i, c in enumerate(codecs):
        args += [f"-c:a:{i}", "copy" if c in AUDIO_COPY else "pcm_s24le"]
    if codecs:
        args += ["-disposition:a", "default"]
    return args


# RAW-Codecs, die FFmpeg ohne Kamera-Weissabgleich entwickelt
RAW_WB_CODECS = {"prores_raw"}


# Farbkennzeichnung: Werte der Quelle uebernehmen (BT.2020, HLG, PQ ...);
# fehlt eine Angabe, BT.709 wie bei Resolve (sonst raten Player bei < 720p BT.601)
COLOR_TAGS = ["-colorspace", "bt709", "-color_primaries", "bt709",
              "-color_trc", "bt709", "-color_range", "tv"]
_MATRIX_OK = {"bt709", "bt2020nc", "bt2020c", "smpte170m", "bt470bg", "smpte240m", "fcc"}
_PRIM_OK = {"bt709", "bt2020", "smpte170m", "bt470bg", "bt470m", "smpte240m",
            "smpte431", "smpte432", "film"}
_TRC_OK = {"bt709", "smpte2084", "arib-std-b67", "bt2020-10", "bt2020-12",
           "smpte170m", "gamma22", "gamma28", "linear", "iec61966-2-1"}
# FFmpeg meldet manche Gamma-Kurven unter anderem Namen, als es beim Schreiben erwartet
_TRC_ALIAS = {"bt470bg": "gamma28", "bt470m": "gamma22"}


def color_setup(info: Optional["MediaInfo"]) -> tuple[str, list[str]]:
    """-> (Matrix fuer die YUV-Umrechnung, Kennzeichnungs-Argumente)."""
    mat, prim, trc = info.color if info else ("", "", "")
    mat = mat if mat in _MATRIX_OK else "bt709"
    prim = prim if prim in _PRIM_OK else "bt709"
    trc = _TRC_ALIAS.get(trc, trc)
    trc = trc if trc in _TRC_OK else "bt709"
    scale_mat = {"bt2020nc": "bt2020", "bt2020c": "bt2020", "bt470bg": "bt470bg",
                 "smpte170m": "smpte170m", "smpte240m": "smpte240m",
                 "fcc": "fcc"}.get(mat, "bt709")
    tags = ["-colorspace", mat, "-color_primaries", prim, "-color_trc", trc,
            "-color_range", "tv"]
    return scale_mat, tags


APP_INFO = {"name": "Proxy Maker", "version": "", "ffmpeg": ""}  # setzt die App


def proxy_metadata(src: Path, codec: str, min_size: tuple[int, int],
                   decoder: str = "FFmpeg", extra: Optional[dict] = None,
                   encoder: Optional[str] = None) -> list[str]:
    """Herkunfts-Infos fuer den Proxy (als QuickTime-Metadaten lesbar,
    z.B. in MediaInfo oder ffprobe)."""
    import datetime

    enc = encoder or CODECS.get(codec, CODECS[DEFAULT_CODEC])[1]
    app = f"{APP_INFO['name']} {APP_INFO['version']}".strip()
    ff = APP_INFO["ffmpeg"] or "?"
    meta = {
        "comment": f"Proxy created with {app} · FFmpeg {ff} · {enc} · "
                   f"decoded with {decoder} · source: {src.name}",
        "com.steeptwo.proxymaker.app": app,
        "com.steeptwo.proxymaker.ffmpeg": ff,
        "com.steeptwo.proxymaker.encoder": enc,
        "com.steeptwo.proxymaker.decoder": decoder,
        "com.steeptwo.proxymaker.source": src.name,
        "com.steeptwo.proxymaker.min_resolution": f"{min_size[0]}x{min_size[1]}",
        "com.steeptwo.proxymaker.created": datetime.datetime.now()
                                            .astimezone().isoformat(timespec="seconds"),
    }
    meta.update(extra or {})
    args = ["-movflags", "use_metadata_tags"]
    for k, v in meta.items():
        args += ["-metadata", f"{k}={v}"]
    return args


def codec_pix_fmt(codec: str, args: Optional[list[str]] = None) -> str:
    args = args or CODECS.get(codec, CODECS[DEFAULT_CODEC])
    return args[args.index("-pix_fmt") + 1]


def codec_args(ffmpeg: str, codec: str, cpu_only: bool = False) -> list[str]:
    """Hardware-Encoder, wenn vorhanden und erlaubt, sonst CPU-Encoder."""
    if not cpu_only:
        hw = accel.hw_encoder(ffmpeg, codec)
        if hw:
            return hw
    return CODECS.get(codec, CODECS[DEFAULT_CODEC])


def measure_wb(ffmpeg: str, src: Path, duration: float) -> Optional[tuple]:
    """Automatischer Weissabgleich (Gray World) fuer RAW-Material ohne
    angewendete Kamera-Farbparameter: misst an mehreren Stellen den
    mittleren R/G/B-Wert und gleicht R und B an G an."""
    import array

    sums = [0.0, 0.0, 0.0]
    n = 0
    times = [duration * f for f in (0.1, 0.5, 0.9)] if duration > 1 else [0]
    for t in times:
        try:
            raw = subprocess.run(
                [ffmpeg, "-v", "error", "-ss", f"{t:.3f}", "-i", str(src),
                 "-frames:v", "1", "-vf", "scale=96:54,format=rgb48le",
                 "-f", "rawvideo", "-"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW, timeout=120,
            ).stdout
        except Exception:
            continue
        px = array.array("H")
        px.frombytes(raw[: len(raw) // 2 * 2])
        if sys.byteorder == "big":
            px.byteswap()
        for i in range(0, len(px) - 2, 3):
            r, g, b = px[i], px[i + 1], px[i + 2]
            # ignorieren: komplett ausgebrannte und insgesamt fast schwarze Pixel
            if min(r, g, b) > 64000 or r + g + b < 3000:
                continue
            sums[0] += r
            sums[1] += g
            sums[2] += b
            n += 1
    if n < 50 or sums[0] <= 0 or sums[2] <= 0:
        return None
    gr = max(0.25, min(4.0, sums[1] / sums[0]))
    gb = max(0.25, min(4.0, sums[1] / sums[2]))
    return gr, gb


def scale_factor(width: int, height: int,
                 min_size: tuple[int, int] = DEFAULT_MIN) -> float:
    """1/4 der Quelle; Breite >= min_w UND Hoehe >= min_h; nie hochskalieren.

    Das Seitenverhaeltnis bleibt immer erhalten: Es wird so weit
    verkleinert, wie es beide Mindestwerte zulassen.
    """
    min_w, min_h = min_size
    return min(1.0, max(0.25, min_w / width, min_h / height))


def target_size(width: int, height: int,
                min_size: tuple[int, int] = DEFAULT_MIN) -> tuple[int, int]:
    f = scale_factor(width, height, min_size)
    return (round(width * f / 2) * 2, round(height * f / 2) * 2)


# Proxy-Codecs. Container ist immer .mov, Ton immer PCM 24 Bit.
CODECS: dict[str, list[str]] = {
    # Apple ProRes 422 Proxy (Standard)
    "prores": ["-c:v", "prores_ks", "-profile:v", "0", "-vendor", "apl0",
               "-pix_fmt", "yuv422p10le"],
    # Avid DNxHR LB (Low Bandwidth), 8 Bit 4:2:2
    "dnxhr": ["-c:v", "dnxhd", "-profile:v", "dnxhr_lb", "-pix_fmt", "yuv422p"],
    # GoPro CineForm, niedrigste Qualitaetsstufe (Breite muss durch 16 teilbar sein)
    "cineform": ["-c:v", "cfhd", "-quality", "low", "-pix_fmt", "yuv422p10le"],
    # H.264 leicht abzuspielen: kein CABAC/Deblocking (fastdecode), kurze GOP fuers Scrubben
    "h264": ["-c:v", "libx264", "-preset", "veryfast", "-tune", "fastdecode",
             "-crf", "23", "-g", "12", "-pix_fmt", "yuv420p"],
}
DEFAULT_CODEC = "prores"


def fit_codec(size: tuple[int, int], codec: str) -> tuple[int, int]:
    """Codec-Vorgaben an die Pixelmasse: CineForm braucht Breite % 16 == 0."""
    w, h = size
    if codec == "cineform":
        w = max(16, round(w / 16) * 16)
    return w, h


def output_size(width: int, height: int, min_size: tuple[int, int] = DEFAULT_MIN,
                codec: str = DEFAULT_CODEC) -> tuple[int, int]:
    return fit_codec(target_size(width, height, min_size), codec)


def build_cmd(ffmpeg: str, src: Path, dst_tmp: Path, info: MediaInfo,
              min_size: tuple[int, int] = DEFAULT_MIN,
              target: Optional[tuple[int, int]] = None,
              codec: str = DEFAULT_CODEC, source: Optional[Path] = None,
              decoder: str = "FFmpeg", cpu_only: bool = False) -> list[str]:
    # target: feste Zielgroesse (z.B. bei der Zwischendatei aus REDline)
    w, h = (fit_codec(target, codec) if target
            else output_size(info.width, info.height, min_size, codec))
    vargs = codec_args(ffmpeg, codec, cpu_only)
    pix = codec_pix_fmt(codec, vargs)
    inargs = [] if cpu_only or info.wb else accel.hwaccel_args(info.vcodec)
    mat, tags = color_setup(info)
    if info.wb:  # RAW (z.B. ProRes RAW): erst entwickeln, dann Weissabgleich
        # colorchannelmixer erlaubt max. Faktor 2 -> in zwei gleiche Schritte teilen
        r, b = info.wb[0] ** 0.5, info.wb[1] ** 0.5
        mix = f"colorchannelmixer=rr={r:.4f}:bb={b:.4f}"
        vf = (f"scale={w}:{h}:flags=bicubic,format=rgb48le,{mix},{mix},"
              f"scale=out_color_matrix={mat}:out_range=tv,format={pix},setsar=1")
    else:
        vf = (f"scale={w}:{h}:flags=bicubic:out_color_matrix={mat}:out_range=tv,"
              f"format={pix},setsar=1")
    extra = {"com.steeptwo.proxymaker.white_balance":
             f"auto (R x{info.wb[0]:.3f}, B x{info.wb[1]:.3f})"} if info.wb else None
    cmd = [
        ffmpeg, "-hide_banner", "-nostdin", "-y", *inargs, "-i", str(src),
        "-map", "0:v:0", "-map", "0:a?",        # 1. Videospur + alle Tonspuren
        "-vf", vf,
        *vargs,
        *tags,
        *audio_args(info.audio_codecs),
        "-map_metadata", "0",
        *proxy_metadata(source or src, codec, min_size, decoder, extra,
                        encoder=vargs[1] + (" + GPU-Decoder" if inargs else "")),
    ]
    if info.timecode:
        cmd += ["-timecode", info.timecode]
    cmd += ["-progress", "pipe:1", "-nostats", "-f", "mov", str(dst_tmp)]
    return cmd


class Cancelled(Exception):
    pass


def encode(
    ffmpeg: str,
    src: Path,
    info: MediaInfo,
    on_progress: Callable[[float], None] = lambda f: None,
    is_cancelled: Callable[[], bool] = lambda: False,
    min_size: tuple[int, int] = DEFAULT_MIN,
    dst: Optional[Path] = None,
    target: Optional[tuple[int, int]] = None,
    codec: str = DEFAULT_CODEC,
    source: Optional[Path] = None,
    decoder: str = "FFmpeg",
    cpu_only: bool = False,
) -> Path:
    """Encodiert src -> Proxy/<name>.mov. Wirft RuntimeError bei Fehlern."""
    dst = dst or proxy_path(src)
    dst.parent.mkdir(exist_ok=True)
    if info.vcodec in RAW_WB_CODECS and info.wb is None:
        info.wb = measure_wb(ffmpeg, src, info.duration)
    tmp = dst.with_name(dst.name + ".partial")
    proc = accel.register(subprocess.Popen(
        build_cmd(ffmpeg, src, tmp, info, min_size, target, codec, source, decoder,
                  cpu_only),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, creationflags=_NO_WINDOW,
    ))
    tail: list[str] = []
    try:
        for raw in proc.stdout:  # type: ignore[union-attr]
            if is_cancelled():
                proc.terminate()
                break
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith(("out_time_us=", "out_time_ms=")):
                try:
                    secs = int(line.split("=", 1)[1]) / 1_000_000
                    if info.duration > 0:
                        on_progress(max(0.0, min(1.0, secs / info.duration)))
                except ValueError:
                    pass
            elif "=" not in line or " " in line:
                tail.append(line)
                del tail[:-8]
        code = proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    if is_cancelled():
        tmp.unlink(missing_ok=True)
        raise Cancelled()
    if code != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("\n".join(tail[-4:]) or f"FFmpeg-Fehler {code}")
    os.replace(tmp, dst)
    on_progress(1.0)
    return dst
