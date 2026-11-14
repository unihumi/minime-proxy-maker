# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.3] – unreleased

### Changed
- **New name: MiniMe – Proxy Maker** (previously "Proxy Maker"). Window title,
  About window, texts and file name (`MiniMe.Proxy.Maker.1.0.3.exe` /
  `.app`) use the new name. Settings from earlier versions are kept, and
  existing proxies still link in DaVinci Resolve as before.
- **New app icon:** a big and a small film frame with googly eyes looking at
  each other (the proxy as a "mini me" of the original). Replaces the STEEPTWO
  logo in the app, taskbar/Dock and README.
- **Dark and Light themes in the logo's colours:** Dark is navy with cyan
  accents, Light is a pale blue-grey with navy text and a deeper blue accent.
  The About and Settings windows use the same navy tones.
- Rounder corners throughout (drop-down lists now have a slim arrow instead
  of the square Windows arrow box), a film-strip style border around the drop area,
  and disabled buttons that are easier to read.
- The empty drop area has the logo's googly eyes (50 % opacity). They follow
  the mouse pointer and blink now and then.

## [1.0.2] – 2026-11-14

### Added
- **Settings window** (⚙ button) for the options below, so the main window
  stays simple.
- **Proxy size:** 1:4 (quarter resolution, default), 1:2 (half) or 1:1
  (full), chosen in Settings. The minimum resolution still applies. The chosen
  size is stored in the proxy's metadata.
- **Proxy location:** next to the source files (`Proxy` folder, linked
  automatically by DaVinci Resolve) or all in one location, with the source
  folder structure recreated there.
- **Watch folders:** new video files in chosen folders (including subfolders)
  are queued and rendered automatically once they have been unchanged for
  about 30 seconds (finished copying). If a source file changes after its
  proxy was started (e.g. a paused copy resumed), that proxy is deleted and
  re-created. Proxies that existed before are never touched. A pulsing green
  dot in the status bar shows that watching is active; it turns amber (and the
  log says so) if a watched folder can't be reached, e.g. a disconnected
  network drive.
- **Disk space check** before rendering, with a warning if the proxies will
  probably not fit (also on network drives). Each file is additionally skipped
  with an error if less than 512 MB are left at the destination.
- **Keep the computer awake** while rendering (on by default).
- **When finished:** do nothing, sleep or shut down, with a 60-second
  countdown that can be cancelled. Applies to the current session only.
- **Update notification:** the app checks GitHub for a newer release at
  startup and asks whether to open the download page. Can be switched off or
  run manually in Settings. Nothing is downloaded automatically.
- About window now lists the supported source formats (R3D, BRAW, ProRes RAW,
  everything FFmpeg can read).

- Hidden `--selftest` option that checks a build (bundled files, FFmpeg, a
  real render with every codec, BRAW helper, windows) and writes a report.

### Changed
- The app's file name includes the version, e.g. `Proxy Maker 1.0.2.exe` /
  `Proxy Maker 1.0.2.app`.
- The default proxy format moved from the main window to Settings. Each file
  in the queue can still be switched individually.

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
