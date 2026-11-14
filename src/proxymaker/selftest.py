"""Built-in self test:  "MiniMe.Proxy.Maker.<version>.exe" --selftest [report.txt]

Checks that a build is complete and working: bundled files, FFmpeg, a real
render with every codec, the BRAW helper (if bundled) and that the windows can
be created. Never touches the user's settings or media. The report is written
to a text file (the Windows build has no console); the exit code is 0 when
everything passed and 1 otherwise.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

from . import __version__

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class _Report:
    def __init__(self, path: Path):
        self.path = path
        self.failed = 0
        self.lines: list[str] = []

    def add(self, ok: bool, name: str, detail: str = "") -> None:
        self.failed += 0 if ok else 1
        self.lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
        self.flush()

    def note(self, text: str) -> None:
        self.lines.append(f"       {text}")
        self.flush()

    def flush(self) -> None:
        try:
            self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        except OSError:
            pass


def _check(rep: _Report, name: str, fn) -> None:
    try:
        detail = fn()
        rep.add(True, name, detail or "")
    except Exception as exc:  # noqa: BLE001 - jeder Fehler ist ein Testergebnis
        rep.add(False, name, f"{type(exc).__name__}: {exc}")
        rep.note(traceback.format_exc().strip().splitlines()[-2].strip())


def run(report_path: str | None = None) -> int:
    path = Path(report_path) if report_path else Path(tempfile.gettempdir()) / "proxymaker_selftest.txt"
    rep = _Report(path)
    rep.lines.append(f"MiniMe - Proxy Maker {__version__} self test - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    rep.lines.append(f"frozen={bool(getattr(sys, 'frozen', False))}  platform={sys.platform}  "
                     f"python={sys.version.split()[0]}")
    rep.flush()

    from . import braw, core
    from .paths import ROOT

    work = Path(tempfile.mkdtemp(prefix="proxymaker_selftest_"))
    state: dict = {}

    def assets():
        for n in ("icon.png", "logo.png"):
            if not (ROOT / "assets" / n).is_file():
                raise RuntimeError(f"assets/{n} missing")
        return "icon.png, logo.png"
    _check(rep, "bundled assets", assets)

    def ffmpeg():
        exe = core.find_ffmpeg()
        if not exe:
            raise RuntimeError("ffmpeg not found")
        bundled = (ROOT / "ffbin").resolve() in Path(exe).resolve().parents
        if getattr(sys, "frozen", False) and not bundled:
            raise RuntimeError(f"not the bundled FFmpeg: {exe}")
        state["ffmpeg"] = exe
        return f"{core.ffmpeg_version(exe)} ({'bundled' if bundled else 'PATH'})"
    _check(rep, "FFmpeg", ffmpeg)

    def make_clip():
        clip = work / "Shoot" / "Day1" / "selftest.mp4"
        clip.parent.mkdir(parents=True)
        r = subprocess.run(
            [state["ffmpeg"], "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=25:d=2",
             "-f", "lavfi", "-i", "sine=d=2", "-shortest", "-c:v", "libx264", "-c:a", "aac",
             str(clip)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, creationflags=_NO_WINDOW, timeout=120)
        if r.returncode != 0 or not clip.exists():
            raise RuntimeError(r.stdout.decode("utf-8", "replace")[-200:])
        state["clip"] = clip
        return "1920x1080, 2 s"
    if "ffmpeg" in state:
        _check(rep, "create test clip", make_clip)

    # Jeder Codec: wirklich rendern und das Ergebnis pruefen
    if "clip" in state:
        info = core.probe(state["ffmpeg"], state["clip"])
        for codec in core.CODECS:
            def render(codec=codec):
                dst = work / f"out_{codec}" / "selftest.mov"
                core.encode(state["ffmpeg"], state["clip"], info, min_size=(960, 540),
                            dst=dst, codec=codec, cpu_only=True)
                out = core.probe(state["ffmpeg"], dst)
                if out is None or abs(out.duration - info.duration) > 0.2:
                    raise RuntimeError("output missing or wrong duration")
                if len(out.audio_codecs) != len(info.audio_codecs):
                    raise RuntimeError("audio tracks lost")
                if abs(out.fps - info.fps) > 0.01:
                    raise RuntimeError(f"fps {out.fps} != {info.fps}")
                return f"{out.width}x{out.height} {out.fps:g} fps, {dst.stat().st_size // 1024} KB"
            _check(rep, f"render {codec}", render)

        # Proxy-Groessen 1:4, 1:2, 1:1 (kleine Mindestaufloesung, damit sie nicht greift)
        def scales():
            want = {4: (480, 270), 2: (960, 540), 1: (1920, 1080)}
            got = []
            try:
                for d, size in want.items():
                    core.set_scale(d)
                    dst = work / f"scale_{d}" / "selftest.mov"
                    core.encode(state["ffmpeg"], state["clip"], info, min_size=(320, 180),
                                dst=dst, codec="prores", cpu_only=True)
                    out = core.probe(state["ffmpeg"], dst)
                    if out is None or (out.width, out.height) != size:
                        raise RuntimeError(f"1:{d} gave {out and (out.width, out.height)}, "
                                           f"expected {size}")
                    got.append(f"1:{d} {size[0]}x{size[1]}")
            finally:
                core.set_scale(core.DEFAULT_SCALE)
            return ", ".join(got)
        _check(rep, "proxy sizes", scales)

    def brawcheck():
        tool = braw.find()
        if not tool:
            raise RuntimeError("BRAW helper (brawpipe) not bundled")
        r = subprocess.run([tool[0]], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, creationflags=_NO_WINDOW, timeout=30)
        text = r.stdout.decode("utf-8", "replace")
        if "usage" not in text.lower():  # z.B. Exitcode 0xC0000135 = DLL fehlt
            raise RuntimeError(f"brawpipe did not start (exit code {r.returncode:#x})")
        return "brawpipe starts, libraries load (no sample .braw clip to decode)"
    _check(rep, "BRAW helper", brawcheck)

    def windows():
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from . import app as appmod
        # nie die echten Einstellungen des Nutzers anfassen
        ini = work / "settings.ini"
        appmod.settings = lambda: QSettings(str(ini), QSettings.IniFormat)
        qa = QApplication.instance() or QApplication([])
        qa.setStyleSheet(appmod.make_style())
        win = appmod.MainWindow()
        appmod.AboutDialog(win).close()
        appmod.SettingsDialog(win).close()
        win.close()
        return "main window, About, Settings"
    _check(rep, "windows", windows)

    try:
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    except Exception:
        pass
    rep.lines.append("")
    rep.lines.append("RESULT: " + ("ALL PASSED" if rep.failed == 0 else f"{rep.failed} FAILED"))
    rep.flush()
    return 0 if rep.failed == 0 else 1
