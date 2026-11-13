"""Where bundled files live: inside the frozen app (PyInstaller) or the repo root."""
import sys
from pathlib import Path

# Frozen app: PyInstaller unpacks everything to sys._MEIPASS.
# Development (python -m proxymaker): <repo>/src/proxymaker/paths.py -> <repo>
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
