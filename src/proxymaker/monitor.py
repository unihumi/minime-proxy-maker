"""CPU- und GPU-Auslastung fuer die kleinen Graphen in Proxy Maker.

CPU:  psutil (macOS + Windows)
GPU:  Windows - Leistungsindikatoren "GPU Engine" ueber PDH (wie im Task-Manager:
              hoechste Auslastung ueber alle Engine-Typen, z.B. 3D, Video Decode)
      macOS   - IOAccelerator "Device Utilization %" ueber ioreg (ohne Admin-Rechte)
Liefert -1, wenn ein Wert nicht verfuegbar ist.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from collections import defaultdict
from typing import Optional

from PySide6.QtCore import QThread, Signal

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class _WinGpu:
    PDH_FMT_DOUBLE = 0x00000200
    PDH_FMT_NOCAP100 = 0x00008000
    PDH_MORE_DATA = 0x800007D2

    def __init__(self):
        import ctypes as C
        from ctypes import wintypes as W

        self.C, self.W = C, W

        class _U(C.Union):
            _fields_ = [("longValue", C.c_long), ("doubleValue", C.c_double),
                        ("largeValue", C.c_longlong), ("AnsiStringValue", C.c_char_p),
                        ("WideStringValue", C.c_wchar_p)]

        class Value(C.Structure):
            _fields_ = [("CStatus", W.DWORD), ("u", _U)]

        class Item(C.Structure):
            _fields_ = [("szName", C.c_wchar_p), ("FmtValue", Value)]

        self.Item = Item
        self.pdh = C.WinDLL("pdh")
        for fn in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData",
                   "PdhGetFormattedCounterArrayW"):
            getattr(self.pdh, fn).restype = W.DWORD
        self.query = C.c_void_p()
        self.counter = C.c_void_p()
        if self.pdh.PdhOpenQueryW(None, None, C.byref(self.query)) != 0:
            raise OSError("PdhOpenQuery")
        # Englischer Name -> funktioniert auch auf deutschem Windows
        if self.pdh.PdhAddEnglishCounterW(
                self.query, r"\GPU Engine(*)\Utilization Percentage", None,
                C.byref(self.counter)) != 0:
            raise OSError("PdhAddEnglishCounter")
        self.pdh.PdhCollectQueryData(self.query)

    def read(self) -> float:
        C, W = self.C, self.W
        if self.pdh.PdhCollectQueryData(self.query) != 0:
            return -1
        fmt = self.PDH_FMT_DOUBLE | self.PDH_FMT_NOCAP100
        size, count = W.DWORD(0), W.DWORD(0)
        r = self.pdh.PdhGetFormattedCounterArrayW(self.counter, fmt, C.byref(size),
                                                  C.byref(count), None)
        if r != self.PDH_MORE_DATA or size.value == 0:
            return 0.0
        buf = (C.c_byte * size.value)()
        if self.pdh.PdhGetFormattedCounterArrayW(self.counter, fmt, C.byref(size),
                                                 C.byref(count), buf) != 0:
            return -1
        items = C.cast(buf, C.POINTER(self.Item))
        per_type: dict[str, float] = defaultdict(float)
        for i in range(count.value):
            it = items[i]
            if it.FmtValue.CStatus not in (0, 1):  # PDH_CSTATUS_VALID_DATA / NEW_DATA
                continue
            name = it.szName or ""
            etype = name.rsplit("engtype_", 1)[-1] if "engtype_" in name else "other"
            per_type[etype] += it.FmtValue.u.doubleValue
        return min(100.0, max(per_type.values(), default=0.0))


class _WinSum:
    """Summe eines Windows-Leistungsindikators ueber alle Instanzen (PDH,
    englische Namen -> sprachunabhaengig). Wie im Task-Manager."""

    def __init__(self, paths: list[str]):
        import ctypes as C
        from ctypes import wintypes as W

        self.C, self.W = C, W
        self.pdh = C.WinDLL("pdh")
        for fn in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData",
                   "PdhGetFormattedCounterArrayW"):
            getattr(self.pdh, fn).restype = W.DWORD

        class _U(C.Union):
            _fields_ = [("longValue", C.c_long), ("doubleValue", C.c_double),
                        ("largeValue", C.c_longlong), ("AnsiStringValue", C.c_char_p),
                        ("WideStringValue", C.c_wchar_p)]

        class Value(C.Structure):
            _fields_ = [("CStatus", W.DWORD), ("u", _U)]

        class Item(C.Structure):
            _fields_ = [("szName", C.c_wchar_p), ("FmtValue", Value)]

        self.Item = Item
        self.query = C.c_void_p()
        if self.pdh.PdhOpenQueryW(None, None, C.byref(self.query)) != 0:
            raise OSError("PdhOpenQuery")
        self.counters = []
        for p in paths:
            c = C.c_void_p()
            # fehlende Kategorien (z.B. RDMA) werden einfach uebersprungen
            if self.pdh.PdhAddEnglishCounterW(self.query, p, None, C.byref(c)) == 0:
                self.counters.append(c)
        if not self.counters:
            raise OSError("keine Zaehler")
        self.pdh.PdhCollectQueryData(self.query)

    def read(self) -> float:
        C, W = self.C, self.W
        if self.pdh.PdhCollectQueryData(self.query) != 0:
            return -1
        total = 0.0
        for c in self.counters:
            size, count = W.DWORD(0), W.DWORD(0)
            r = self.pdh.PdhGetFormattedCounterArrayW(c, 0x8200, C.byref(size),
                                                      C.byref(count), None)
            if r != 0x800007D2 or size.value == 0:
                continue
            buf = (C.c_byte * size.value)()
            if self.pdh.PdhGetFormattedCounterArrayW(c, 0x8200, C.byref(size),
                                                     C.byref(count), buf) != 0:
                continue
            items = C.cast(buf, C.POINTER(self.Item))
            for i in range(count.value):
                if items[i].FmtValue.CStatus in (0, 1):
                    total += items[i].FmtValue.u.doubleValue
        return total


class _MacGpu:
    _RE = re.compile(r'"Device Utilization %"\s*=\s*(\d+)')

    def read(self) -> float:
        try:
            out = subprocess.run(
                ["/usr/sbin/ioreg", "-r", "-d", "1", "-w", "0", "-c", "IOAccelerator"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3,
            ).stdout.decode("utf-8", "replace")
        except Exception:
            return -1
        vals = [int(v) for v in self._RE.findall(out)]
        return float(max(vals)) if vals else -1


def _make_gpu():
    try:
        if sys.platform == "win32":
            return _WinGpu()
        if sys.platform == "darwin":
            return _MacGpu()
    except Exception:
        pass
    return None


NETFS = {"smbfs", "nfs", "afpfs", "webdav", "cifs", "ftp", "fuse.sshfs", "osxfuse"}


def resolve_disk(path: str) -> tuple[Optional[str], str, bool]:
    """Datei -> (psutil-Schluessel der physischen Disk oder None, Anzeigename,
    Netzlaufwerk?). None als Schluessel = Summe aller Disks anzeigen."""
    try:
        if sys.platform == "win32":
            return _resolve_win(path)
        if sys.platform == "darwin":
            return _resolve_mac(path)
    except Exception:
        pass
    return None, "", False


def _resolve_win(path: str) -> tuple[Optional[str], str, bool]:
    import ctypes as C
    from ctypes import wintypes as W

    p = os.path.abspath(path)
    if p.startswith("\\\\") and not p.startswith("\\\\?\\"):
        return None, "", True                      # UNC-Pfad \\server\share
    drive = os.path.splitdrive(p)[0]               # "D:"
    if len(drive) != 2:
        return None, "", False
    k32 = C.WinDLL("kernel32", use_last_error=True)
    if k32.GetDriveTypeW(drive + "\\") == 4:       # DRIVE_REMOTE
        return None, drive, True
    k32.CreateFileW.restype = C.c_void_p
    k32.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p,
                                W.DWORD, W.DWORD, C.c_void_p]
    k32.DeviceIoControl.argtypes = [C.c_void_p, W.DWORD, C.c_void_p, W.DWORD,
                                    C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p]
    k32.CloseHandle.argtypes = [C.c_void_p]
    h = k32.CreateFileW("\\\\.\\" + drive, 0, 3, None, 3, 0, None)
    if h is None or h == C.c_void_p(-1).value:
        return None, drive, False

    class DevNum(C.Structure):
        _fields_ = [("DeviceType", W.DWORD), ("DeviceNumber", W.DWORD),
                    ("PartitionNumber", W.DWORD)]

    dn, ret = DevNum(), W.DWORD(0)
    ok = k32.DeviceIoControl(h, 0x2D1080, None, 0, C.byref(dn), C.sizeof(dn),
                             C.byref(ret), None)   # IOCTL_STORAGE_GET_DEVICE_NUMBER
    k32.CloseHandle(h)
    return (f"PhysicalDrive{dn.DeviceNumber}" if ok else None), drive, False


def _resolve_mac(path: str) -> tuple[Optional[str], str, bool]:
    import plistlib

    real = os.path.realpath(path)
    best = None
    for part in psutil.disk_partitions(all=True):
        mp = part.mountpoint
        if real == mp or real.startswith(mp.rstrip("/") + "/"):
            if best is None or len(mp) > len(best.mountpoint):
                best = part
    if best is None:
        return None, "", False
    label = os.path.basename(best.mountpoint.rstrip("/")) or "System"
    if best.fstype.lower() in NETFS or best.device.startswith("//"):
        return None, label, True
    m = re.match(r"/dev/(disk\d+)", best.device)
    if not m:
        return None, label, False
    whole = m.group(1)
    keys = set(psutil.disk_io_counters(perdisk=True).keys())
    if whole in keys:
        return whole, label, False
    # APFS: Volume liegt auf einem "synthesized" Container -> physische Disk suchen
    try:
        out = subprocess.run(["/usr/sbin/diskutil", "info", "-plist", best.device],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=5).stdout
        info = plistlib.loads(out)
        stores = [d.get("APFSPhysicalStore", "") for d in info.get("APFSPhysicalStores", [])]
        for cand in stores + [info.get("ParentWholeDisk", "")]:
            m2 = re.match(r"(disk\d+)", cand or "")
            if m2 and m2.group(1) in keys:
                return m2.group(1), label, False
    except Exception:
        pass
    return None, label, False


class UsageSampler(QThread):
    # dict: cpu %, gpu %, rx/tx MB/s, disk MB/s (-1 = n/a), disk_label, disk_net
    sample = Signal(object)

    def __init__(self, interval: float = 1.0):
        super().__init__()
        self.interval = interval
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._path: Optional[str] = None

    def stop(self):
        self._stop.set()

    def set_path(self, path: Optional[str]):
        """Datei, die gerade bearbeitet wird (None = Leerlauf)."""
        with self._lock:
            self._path = path

    @staticmethod
    def _net_bytes() -> Optional[tuple[int, int]]:
        try:
            n = psutil.net_io_counters()
            return n.bytes_recv, n.bytes_sent
        except Exception:
            return None

    @staticmethod
    def _make_win_net():
        """Windows: dieselben Zaehler wie Task-Manager/Ressourcenmonitor, plus
        RDMA (SMB Direct umgeht die normalen Netzwerkzaehler)."""
        if sys.platform != "win32":
            return None
        try:
            rx = _WinSum([r"\Network Interface(*)\Bytes Received/sec",
                          r"\RDMA Activity(*)\RDMA Inbound Bytes/sec"])
            tx = _WinSum([r"\Network Interface(*)\Bytes Sent/sec",
                          r"\RDMA Activity(*)\RDMA Outbound Bytes/sec"])
            return rx, tx
        except Exception:
            return None

    @staticmethod
    def _disk_all() -> dict:
        try:
            return {k: v.read_bytes + v.write_bytes
                    for k, v in (psutil.disk_io_counters(perdisk=True) or {}).items()}
        except Exception:
            return {}

    def run(self):
        import time

        gpu = _make_gpu()
        if psutil:
            psutil.cpu_percent(None)  # erster Aufruf initialisiert nur
        prev_t = time.monotonic()
        win_net = self._make_win_net()
        prev_net = self._net_bytes() if psutil else None
        prev_disk = self._disk_all() if psutil else {}
        cache: dict[str, tuple] = {}
        while not self._stop.wait(self.interval):
            now = time.monotonic()
            dt = max(0.05, now - prev_t)
            prev_t = now
            cpu = psutil.cpu_percent(None) if psutil else -1.0
            g = -1.0
            if gpu:
                try:
                    g = float(gpu.read())
                except Exception:
                    g = -1.0
            rx = tx = disk = -1.0
            key, label, is_net = None, "", False
            if win_net:
                try:
                    rx, tx = win_net[0].read() / 1e6, win_net[1].read() / 1e6
                except Exception:
                    rx = tx = -1.0
            elif psutil:
                cur_net = self._net_bytes()
                if cur_net is not None and prev_net is not None:
                    rx = max(0, cur_net[0] - prev_net[0]) / dt / 1e6
                    tx = max(0, cur_net[1] - prev_net[1]) / dt / 1e6
                prev_net = cur_net
            if psutil:
                with self._lock:
                    path = self._path
                if path:
                    folder = os.path.dirname(path)
                    if folder not in cache:
                        cache[folder] = resolve_disk(path)
                    key, label, is_net = cache[folder]
                cur_disk = self._disk_all()
                if cur_disk:
                    keys = [key] if key in cur_disk else list(cur_disk)
                    delta = sum(max(0, cur_disk[k] - prev_disk.get(k, cur_disk[k]))
                                for k in keys)
                    disk = delta / dt / 1e6
                prev_disk = cur_disk
            self.sample.emit({"cpu": float(cpu), "gpu": g, "rx": rx, "tx": tx,
                              "disk": disk,
                              "disk_label": label, "disk_net": is_net})
