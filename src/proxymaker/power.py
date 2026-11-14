"""Energie: Rechner waehrend des Renderns wach halten, danach Ruhezustand
oder Herunterfahren (Windows und macOS)."""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# Windows: SetThreadExecutionState-Flags
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


class KeepAwake:
    """Verhindert den automatischen Ruhezustand. Der Bildschirm darf trotzdem
    ausgehen. Unter Windows gilt der Zustand fuer den aufrufenden Thread -
    start() und stop() deshalb immer aus dem GUI-Thread aufrufen."""

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self.active = False

    def start(self) -> None:
        if self.active:
            return
        try:
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(
                    _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
            elif sys.platform == "darwin":
                # -i: kein Ruhezustand bei Untaetigkeit; -w: endet mit der App
                self._proc = subprocess.Popen(
                    ["caffeinate", "-i", "-w", str(os.getpid())],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
            self.active = True
        except Exception:
            self.active = False

    def stop(self) -> None:
        if not self.active:
            return
        try:
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
            elif self._proc:
                self._proc.terminate()
                self._proc = None
        except Exception:
            pass
        self.active = False


def _run(cmd: list[str]) -> None:
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)


def sleep_computer() -> None:
    if sys.platform == "win32":
        import ctypes
        # Hinweis: Ist der Ruhezustand (Hibernate) aktiv, geht Windows hier in
        # den Ruhezustand statt in den Energiesparmodus.
        ctypes.windll.powrprof.SetSuspendState(0, 0, 0)
    elif sys.platform == "darwin":
        _run(["pmset", "sleepnow"])
    else:
        _run(["systemctl", "suspend"])


def shutdown_computer() -> None:
    if sys.platform == "win32":
        _run(["shutdown", "/s", "/t", "0"])
    elif sys.platform == "darwin":
        # Beim ersten Mal fragt macOS nach der Erlaubnis, "System Events" zu steuern
        _run(["osascript", "-e", 'tell application "System Events" to shut down'])
    else:
        _run(["systemctl", "poweroff"])
