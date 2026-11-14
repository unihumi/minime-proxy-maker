#!/bin/bash
# Baut "Proxy Maker <Version>.app" (Apple Silicon) mit der neuesten FFmpeg-Version
# und - falls das Blackmagic RAW SDK installiert ist - mit BRAW-Unterstuetzung.
# Ergebnis: dist/Proxy Maker <Version>.app (Version aus src/proxymaker/__init__.py)
# Always work from the repository root (this script lives in scripts/)
cd "$(dirname "$0")/.." || exit 1
set -e

FFMPEG_URL="https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip"

# FFmpeg wird nur geladen, wenn es noch nicht da ist.
# Aktualisieren: Ordner "ffbin" loeschen oder  bash scripts/build_mac.command update
[ "$1" = "update" ] && rm -rf ffbin
rm -rf build_tmp brawlib
mkdir -p build_tmp
if [ -x ffbin/ffmpeg ]; then
  echo "== FFmpeg bereits vorhanden (kein Download) =="
else
  echo "== Lade aktuelle FFmpeg-Version (macOS arm64) =="
  mkdir -p ffbin
  curl -fL --retry 3 -o build_tmp/ffmpeg.zip "$FFMPEG_URL"
  unzip -o -q build_tmp/ffmpeg.zip -d build_tmp
  FF=$(find build_tmp -type f -name ffmpeg | head -n 1)
  [ -n "$FF" ] || { echo "FFmpeg nicht im Download gefunden"; exit 1; }
  cp "$FF" ffbin/ffmpeg
  chmod +x ffbin/ffmpeg
  xattr -c ffbin/ffmpeg 2>/dev/null || true
  codesign -v ffbin/ffmpeg 2>/dev/null || codesign --force -s - ffbin/ffmpeg
fi
echo "Eingebaut: $(./ffbin/ffmpeg -hide_banner -version | head -n 1)"

echo "== Blackmagic RAW (optional) =="
BRAW_SDK=""
for d in "braw_sdk/Mac" "braw_sdk" \
         "/Applications/Blackmagic RAW/Blackmagic RAW SDK/Mac"; do
  if [ -f "$d/Include/BlackmagicRawAPI.h" ]; then BRAW_SDK="$d"; break; fi
done
if [ -n "$BRAW_SDK" ]; then
  if ! xcrun --find clang++ >/dev/null 2>&1; then
    echo "Xcode-Kommandozeilenwerkzeuge fehlen. Bitte einmal ausfuehren:"
    echo "  xcode-select --install"
    echo "und den Build danach erneut starten."
    exit 1
  fi
  echo "SDK gefunden: $BRAW_SDK"
  mkdir -p brawlib
  ditto "$BRAW_SDK/Libraries" brawlib
  xcrun clang++ -std=c++17 -O2 -I "$BRAW_SDK/Include" \
    native/brawpipe/brawpipe.cpp "$BRAW_SDK/Include/BlackmagicRawAPIDispatch.cpp" \
    -framework CoreFoundation -o brawlib/brawpipe
  echo "BRAW-Unterstuetzung wird eingebaut."
else
  echo "Kein Blackmagic RAW SDK gefunden - App wird ohne BRAW gebaut."
fi

echo "== Python-Umgebung =="
python3 -m venv .venv-build
source .venv-build/bin/activate
pip install --upgrade pip
pip install -r requirements.txt pyinstaller pillow

# Versionsnummer gehoert in den Dateinamen, z.B. "Proxy Maker 1.0.2.app"
VER=$(python3 -c "import sys; sys.path.insert(0, 'src'); from proxymaker import __version__; print(__version__)")
[ -n "$VER" ] || { echo "Version nicht gefunden"; exit 1; }
echo "Version: $VER"

ICON=""
[ -f assets/icon.png ] && ICON="--icon=assets/icon.png"

echo "== Baue App =="
pyinstaller --noconfirm --clean --windowed \
  --name "Proxy Maker" \
  --add-data "assets:assets" \
  --add-binary "ffbin/ffmpeg:ffbin" \
  --paths src \
  $ICON \
  src/proxymaker/__main__.py

# Nur der Dateiname bekommt die Version - der Name im Menue bleibt "Proxy Maker"
APP="dist/Proxy Maker $VER.app"
rm -rf "$APP"
mv "dist/Proxy Maker.app" "$APP"
if [ -d brawlib ]; then
  # Framework mit Symlinks unveraendert ins Bundle kopieren, dann neu signieren
  ditto brawlib "$APP/Contents/Resources/brawlib"
  codesign --force -s - "$APP"
fi

rm -rf build_tmp
echo
echo "Fertig: $(pwd)/$APP"
[ -z "$CI" ] && open dist
exit 0
