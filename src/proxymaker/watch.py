"""Ueberwachte Ordner: neue Videodateien automatisch einreihen.

Es wird alle paar Sekunden gescannt (inkl. Unterordner) statt auf
Dateisystem-Ereignisse zu warten - die sind auf Netzlaufwerken unzuverlaessig.
Eine Datei gilt erst als fertig kopiert, wenn Groesse und Aenderungszeit
STABLE_CHECKS Scans lang unveraendert bleiben (ca. 30 s) und sie sich unter
Windows oeffnen laesst. Jede Datei wird pro Sitzung nur einmal gemeldet,
solange sie sich nicht aendert - eine fehlerhafte Datei wird also nicht
endlos wiederholt.

Aendert sich eine bereits gemeldete Datei spaeter doch noch (z.B. weil ein
Kopiervorgang nur pausiert hatte), wird sie erneut gemeldet - mit
rerender=True. Die App loescht dann den eigenen, vermutlich zu kurzen Proxy
und rendert neu.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from . import core

INTERVAL = 10       # Sekunden zwischen zwei Scans
STABLE_CHECKS = 3   # so oft hintereinander unveraendert -> fertig kopiert (~30 s)


def _signature(p: Path):
    st = p.stat()
    return (st.st_size, st.st_mtime_ns)


def _readable(p: Path) -> bool:
    """Windows sperrt Dateien oft, solange sie noch kopiert werden."""
    if sys.platform != "win32":
        return True
    try:
        with open(p, "rb"):
            return True
    except OSError:
        return False


class FolderWatcher(QThread):
    found = Signal(list)   # [(Datei, Basisordner, rerender)] - Pfade als Strings
    status = Signal(list)  # nicht erreichbare Ordner (nach jedem Scan, leer = alle da)

    def __init__(self, folders: list[str], parent=None):
        super().__init__(parent)
        self._folders = list(folders)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._seen: dict[str, tuple] = {}     # Datei -> (Stand, wie oft unveraendert)
        self._emitted: dict[str, tuple] = {}  # von uns eingereiht (mit Stand)
        self._foreign: dict[str, tuple] = {}  # Proxy gab es schon - nie anfassen

    def set_folders(self, folders: list[str]) -> None:
        with self._lock:
            self._folders = list(folders)

    def stop(self) -> None:
        self._stop.set()

    def scan_once(self) -> list[tuple[str, str, bool]]:
        with self._lock:
            folders = list(self._folders)
        ready: list[tuple[str, str, bool]] = []
        missing: list[str] = []
        for folder in folders:
            if self._stop.is_set():
                break
            if not Path(folder).is_dir():
                missing.append(folder)  # z.B. Netzlaufwerk getrennt, Karte entfernt
                continue
            for f, base in core.collect_with_base([folder]):
                key = str(f)
                try:
                    sig = _signature(f)
                except OSError:
                    continue
                if self._emitted.get(key) == sig or self._foreign.get(key) == sig:
                    continue  # schon erledigt und seitdem unveraendert
                prev, count = self._seen.get(key, (None, 0))
                count = count + 1 if prev == sig else 0
                self._seen[key] = (sig, count)
                if count < STABLE_CHECKS:
                    continue  # neu, waechst noch oder noch nicht lange genug ruhig
                if not _readable(f):
                    continue
                core.remember_base(f, base)
                # nach dem Einreihen geaendert -> unser Proxy ist evtl. zu kurz
                rerender = key in self._emitted
                if not rerender and core.proxy_path(f).exists():
                    self._foreign[key] = sig  # Proxy gab es schon - nicht unserer
                    continue
                self._emitted[key] = sig
                ready.append((key, str(base), rerender))
        self.missing = missing
        return ready

    missing: list[str] = []  # Ergebnis des letzten Scans

    def run(self):
        while not self._stop.is_set():
            try:
                ready = self.scan_once()
            except Exception:
                ready = []
            if self._stop.is_set():
                break
            self.status.emit(list(self.missing))
            if ready:
                self.found.emit(ready)
            self._stop.wait(INTERVAL)
