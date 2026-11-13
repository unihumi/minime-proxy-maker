# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.1] – 2026-11-12

### Added
- Windows: render progress in the taskbar button (green while running,
  red after an error, yellow after cancelling).
- macOS: progress bar drawn onto the Dock icon, in the style of the
  Downloads stack.
- The app icon bounces (macOS) or flashes (Windows) when the queue has
  finished and Proxy Maker is not the active window.
- Repository restructured for GitHub: `src/` package layout, build scripts in
  `scripts/`, native BRAW helper in `native/`, CI workflow, English README.

### Changed
- The “Gentle” priority mode now uses the 🌿 icon (⚡ remains for “Maximum”).
- Version number is defined once in `src/proxymaker/__init__.py`.

## [1.0.0] – 2026

### Added
- First release: drag-and-drop queue that creates DaVinci Resolve–ready proxies
  in a `Proxy` subfolder next to the source files.
- Quarter resolution with a selectable minimum size; aspect ratio preserved,
  no upscaling.
- Codecs: ProRes 422 Proxy (default), DNxHR LB, CineForm, light H.264 –
  globally and per queue row; always MOV.
- Audio kept bit-exact (PCM/AAC/ALAC copied, others to 24-bit PCM); timecode,
  frame rate, file name and colour tags preserved for automatic linking.
- RAW: RED R3D via REDline, Blackmagic RAW via the official SDK, ProRes RAW
  with automatic white balance.
- Four parallel encodes, hardware decoding/encoding where available,
  Gentle/Maximum priority switch.
- Rainbow / Light / Dark themes, German and English UI, live CPU/GPU/network/disk
  graphs while rendering, collapsible log.
