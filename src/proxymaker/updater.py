"""Update check: asks GitHub for the latest release of MiniMe.

Only notifies - nothing is downloaded or installed by the app itself.
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Optional

from PySide6.QtCore import QThread, Signal

REPO = "unihumi/minime-proxy-maker"  # renamed from unihumi/proxymaker (GitHub redirects the old name)
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
TIMEOUT = 6  # seconds


def parse_version(text: str) -> Optional[tuple[int, ...]]:
    """'v1.0.2' -> (1, 0, 2). Suffixes such as '-beta' are ignored."""
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)", text or "")
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def is_newer(latest: str, current: str) -> bool:
    a, b = parse_version(latest), parse_version(current)
    if not a or not b:
        return False
    n = max(len(a), len(b))  # 1.0 == 1.0.0
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def fetch_latest() -> tuple[str, str]:
    """Returns (tag, release page URL). Raises on network or parse errors."""
    req = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "MiniMe-update-check",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = json.load(r)
    tag = str(data.get("tag_name") or "")
    url = str(data.get("html_url") or "")
    if not url.startswith(f"https://github.com/{REPO}/"):
        url = RELEASES_URL  # never trust a foreign link from the response
    return tag, url


class UpdateChecker(QThread):
    """Runs the check in the background; the UI never blocks.

    result(ok, newer, tag, url): ok is False if the check failed (offline etc.).
    """
    result = Signal(bool, bool, str, str)

    def __init__(self, current_version: str, parent=None):
        super().__init__(parent)
        self.current = current_version

    def run(self):
        try:
            tag, url = fetch_latest()
        except Exception:
            self.result.emit(False, False, "", "")
            return
        self.result.emit(True, is_newer(tag, self.current), tag, url)
