"""Progress in the Windows taskbar button and on the macOS Dock icon.

Windows: native ITaskbarList3 (green = running, red = error, yellow = paused),
         called directly via ctypes - no extra packages.
macOS:   the app redraws its own Dock icon with a progress bar at the bottom
         (Qt sets the application icon image).
Other platforms: no-op.
"""
from __future__ import annotations

import sys
import uuid
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication

STATES = ("normal", "error", "paused")


class _WinTaskbar:
    TBPF = {"none": 0, "normal": 2, "error": 4, "paused": 8}

    def __init__(self, hwnd: int):
        import ctypes as C
        from ctypes import wintypes as W

        class GUID(C.Structure):
            _fields_ = [("Data1", W.DWORD), ("Data2", W.WORD), ("Data3", W.WORD),
                        ("Data4", C.c_ubyte * 8)]

        def guid(s: str) -> GUID:
            u = uuid.UUID(s)
            g = GUID(u.time_low, u.time_mid, u.time_hi_version)
            for i, b in enumerate(u.bytes[8:]):
                g.Data4[i] = b
            return g

        self.C, self.hwnd = C, W.HWND(hwnd)
        ole32 = C.WinDLL("ole32")
        ole32.CoInitialize(None)  # already initialised by Qt -> harmless
        clsid = guid("56FDF344-FD6D-11d0-958A-006097C9A090")  # CLSID_TaskbarList
        iid = guid("EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF")    # IID_ITaskbarList3
        self.ptr = C.c_void_p()
        hr = ole32.CoCreateInstance(C.byref(clsid), None, 1, C.byref(iid),
                                    C.byref(self.ptr))
        if hr != 0 or not self.ptr:
            raise OSError("ITaskbarList3 not available")
        vtbl = C.cast(self.ptr, C.POINTER(C.POINTER(C.c_void_p))).contents

        def method(index, *argtypes):
            return C.WINFUNCTYPE(C.c_long, C.c_void_p, *argtypes)(vtbl[index])

        method(3)(self.ptr)  # HrInit
        self._value = method(9, W.HWND, C.c_ulonglong, C.c_ulonglong)  # SetProgressValue
        self._state = method(10, W.HWND, C.c_int)                       # SetProgressState

    def set(self, frac: float, state: str) -> None:
        self._state(self.ptr, self.hwnd, self.TBPF.get(state, 2))
        self._value(self.ptr, self.hwnd, int(max(0.0, min(1.0, frac)) * 1000), 1000)

    def clear(self) -> None:
        self._state(self.ptr, self.hwnd, self.TBPF["none"])


class _MacDock:
    COLORS = {"normal": "#ffffff", "error": "#ff5a52", "paused": "#ffc93c"}

    def __init__(self, base: QIcon):
        self.base = base
        self._last: Optional[tuple] = None

    def _render(self, frac: float, state: str) -> QIcon:
        size = 512
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        self.base.paint(p, 0, 0, size, size)
        # rounded bar near the bottom, like the Downloads stack in the Dock
        track = QRectF(size * 0.14, size * 0.80, size * 0.72, size * 0.075)
        path = QPainterPath()
        path.addRoundedRect(track, track.height() / 2, track.height() / 2)
        p.fillPath(path, QColor(0, 0, 0, 170))
        inner = track.adjusted(4, 4, -4, -4)
        fill = QRectF(inner.left(), inner.top(),
                      max(inner.height(), inner.width() * frac), inner.height())
        fpath = QPainterPath()
        fpath.addRoundedRect(fill, fill.height() / 2, fill.height() / 2)
        p.fillPath(fpath, QColor(self.COLORS.get(state, "#ffffff")))
        p.end()
        return QIcon(pm)

    def set(self, frac: float, state: str) -> None:
        key = (int(frac * 100), state)  # redraw only when the percentage changes
        if key != self._last:
            self._last = key
            QApplication.setWindowIcon(self._render(frac, state))

    def clear(self) -> None:
        self._last = None
        QApplication.setWindowIcon(self.base)


class TaskbarProgress:
    """Created lazily, because Windows needs a real window handle."""

    def __init__(self, window, base_icon: QIcon):
        self.window = window
        self.base_icon = base_icon
        self.impl = None
        self._tried = False

    def _get(self):
        if not self._tried:
            self._tried = True
            try:
                if sys.platform == "win32":
                    self.impl = _WinTaskbar(int(self.window.winId()))
                elif sys.platform == "darwin" and not self.base_icon.isNull():
                    self.impl = _MacDock(self.base_icon)
            except Exception:
                self.impl = None
        return self.impl

    def set(self, frac: float, state: str = "normal") -> None:
        impl = self._get()
        if impl:
            try:
                impl.set(frac, state)
            except Exception:
                pass

    def clear(self) -> None:
        impl = self._get()
        if impl:
            try:
                impl.clear()
            except Exception:
                pass
