"""Proxy Maker - GUI (PySide6), Deutsch / English."""
from __future__ import annotations

import sys
import threading
from collections import deque
from pathlib import Path

from PySide6.QtCore import (
    QLocale, QPoint, QPointF, QRectF, QSettings, QSize, Qt, QThread, QTimer, QUrl,
    Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QDesktopServices, QFont, QFontMetrics, QGradient,
    QGuiApplication, QIcon,
    QLinearGradient, QPainter,
    QMovie, QPainterPath, QPen, QPixmap, QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QFileDialog, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QRadioButton, QScrollArea, QProgressBar, QPushButton, QSizePolicy, QSpinBox,
    QStackedLayout, QVBoxLayout, QWidget,
)

from . import __version__, accel, braw, monitor, redline, taskbar, updater
from . import core, diskcheck, power, watch
from .paths import ROOT

# ---------------------------------------------------------------- Branding
APP_NAME = "Proxy Maker"
APP_VERSION = __version__
CONTACT = "hello@steeptwo.com"
ACCENT = "#3d8bfd"      # Akzentfarbe im Terminal
RAINBOW_DARKEN = 0.5    # 0.5 = Regenbogen um 50 % abgedunkelt
RAINBOW_PERIOD = 540    # Breite eines Farbdurchlaufs in Pixel
RAINBOW_SPEED = 18      # Pixel pro Sekunde nach rechts
BACKGROUND = "#1c1d21"
PANEL = "#111214"
TEXT = "#e8e8ea"
LOGO_HEIGHT = 44        # Hoehe des Logos im Kopfbereich (Pixel)
MIN_PRESETS = [(640, 360), (960, 540), (1280, 720), (1920, 1080)]
CODEC_NAMES = {  # Anzeige im Menue (Schluessel siehe proxy_core.CODECS)
    "prores": "Apple ProRes 422 Proxy",
    "dnxhr": "Avid DNxHR LB",
    "cineform": "GoPro CineForm (Low)",
    "h264": "H.264",
}
CODEC_SHORT = {"prores": "ProRes", "dnxhr": "DNxHR", "cineform": "CineForm", "h264": "H.264"}
# Grafiken: assets/logo.png (Kopfbereich) und assets/icon.png (App-Icon)
# --------------------------------------------------------------------------

# ------------------------------------------------------------------ Themes
# Das Terminal und das About-Fenster bleiben in allen Themes dunkel.
THEMES = {
    "rainbow": dict(
        rainbow=True, bg=BACKGROUND, text="white", hint="rgba(255,255,255,200)",
        accent="white", panel="rgba(0,0,0,110)", ctrl="rgba(0,0,0,150)",
        btn="rgba(0,0,0,130)", btn_hover="rgba(0,0,0,180)", btn_text="white",
        btn_dis="rgba(0,0,0,130)", btn_dis_text="rgba(255,255,255,90)",
        start="rgba(255,255,255,40)", start_hover="rgba(255,255,255,70)",
        start_text="white", start_dis="rgba(0,0,0,100)",
        drop_bg="rgba(0,0,0,90)", drop_border="rgba(255,255,255,140)",
        drop_hover="white", bar_bg="rgba(0,0,0,150)", chunk="rgba(255,255,255,90)",
        list_bg="rgba(0,0,0,120)", sel="rgba(255,255,255,60)",
        popup_bg="#1c1d21", popup_sel="#3a3c44", help_border="rgba(255,255,255,160)",
        graph_bg=(0, 0, 0, 140), graph_text=(255, 255, 255, 220),
        graph_colors=("#7fd6ff", "#ffb86b", "#9be28a", "#d6a2ff", "#ffe27a"),
        term_bg=PANEL, term_text="#b9bbc2", term_accent=ACCENT, term_handle="#3a3c44",
    ),
}


def _mix(c1: str, c2: str, t: float = 0.5) -> str:
    """Mischt zwei Hex-Farben (t = Anteil von c1)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * t + y * (1 - t)):02x}" for x, y in zip(a, b))


def _rgb(c: str, alpha: int = 255) -> tuple[int, int, int, int]:
    return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16), alpha)


def _darker(c: str, f: float = 0.95) -> str:
    return "#" + "".join(f"{round(int(c[i:i + 2], 16) * f):02x}" for i in (1, 3, 5))


def _solid_theme(bg: str, text: str, accent: str, on_accent: str,
                 panel: str, ctrl: str, list_bg: str, bar_bg: str,
                 term_bg: str, term_text: str, graph_colors: tuple) -> dict:
    """Hell/Dunkel. Aktive Buttons = volle Akzentfarbe,
    ausgegraute = 50 % Akzent + Hintergrund."""
    dis = _mix(accent, bg, 0.5)
    return dict(
        rainbow=False, bg=bg, text=text, hint=_mix(text, bg, 0.7), accent=accent,
        panel=panel, ctrl=ctrl,
        btn=accent, btn_hover=_mix(accent, text, 0.85), btn_text=on_accent,
        btn_dis=dis, btn_dis_text=_mix(on_accent, dis, 0.55),
        start=accent, start_hover=_mix(accent, text, 0.85), start_text=on_accent,
        start_dis=dis,
        drop_bg=panel, drop_border=accent, drop_hover=_mix(accent, text, 0.7),
        bar_bg=bar_bg, chunk=accent,
        list_bg=list_bg, sel=_mix(accent, list_bg, 0.3),
        popup_bg=ctrl, popup_sel=_mix(accent, ctrl, 0.3), help_border=accent,
        graph_bg=_rgb(list_bg), graph_text=_rgb(text, 230),
        graph_colors=graph_colors,
        term_bg=term_bg, term_text=term_text, term_accent=accent,
        term_handle=_mix(accent, term_bg, 0.4),
    )


# Dunkel: wie zuvor, Akzent sehr helles Mintgruen
THEMES["dark"] = _solid_theme(
    bg="#1c1d21", text="#e8e8ea", accent="#b8f5d6", on_accent="#1c1d21",
    panel="#26282e", ctrl="#32343c", list_bg="#17181b", bar_bg="#111214",
    term_bg="#111214", term_text="#b9bbc2",
    graph_colors=("#b8f5d6", "#7fd6ff", "#ffb86b", "#d6a2ff", "#7fd6ff"))
# Hell: farblos, alles 5 % dunkler als zuvor, Akzent Petrol
_d = _darker
THEMES["light"] = _solid_theme(
    bg=_d("#f2f3f5"), text="#1d1e22", accent="#1f6f78", on_accent="#ffffff",
    panel=_d("#ffffff"), ctrl=_d("#e4e6ea"), list_bg=_d("#f7f8fa"),
    bar_bg=_d("#dcdfe5"), term_bg=_d("#fbfbfc"), term_text="#1d1e22",
    graph_colors=("#1f6f78", "#1f6fb8", "#c9731a", "#7a3fc0", "#1f6fb8"))
THEMES = {k: THEMES[k] for k in ("rainbow", "light", "dark")}  # Reihenfolge im Menue
# Kopf-Icons (Theme, Sprache, Einstellungen, Hilfe): ohne Umrandung, dafuer mit
# Schlagschatten: (Deckkraft, Weichheit) je Theme. Auf Hell enger und kraeftiger,
# damit sich das helle Zahnrad-Emoji vom hellen Hintergrund abhebt.
THEMES["rainbow"]["icon_shadow"] = (190, 12)
THEMES["dark"]["icon_shadow"] = (190, 12)
THEMES["light"]["icon_shadow"] = (235, 6)
T = THEMES["rainbow"]  # aktuelles Theme (wird von apply_theme gesetzt)


# ------------------------------------------------------------- Uebersetzung
STRINGS = {
    "de": {
        "subtitle": "1:4 · 1:2 · 1:1 · Unterordner „Proxy“",
        "codec_label": "Codec:",
        "codec_h264": "H.264 (leicht abspielbar)",
        "min_label": "Mindestauflösung:",
        "custom_item": "Benutzerdefiniert …",
        "width": "Breite ",
        "height": "Höhe ",
        "hint": (
            "Proxies werden auf die eingestellte Größe verkleinert (1:4, 1:2 "
            "oder 1:1), aber nie unter diese Werte. Breite und Höhe gelten dabei "
            "unabhängig voneinander als Untergrenze: Das Seitenverhältnis des "
            "Originals bleibt immer erhalten, egal ob 16:9, Cinemascope, 4:3 "
            "oder Hochformat. Beispiel bei 960 × 540: Ein 2,39:1-Clip wird "
            "1290 × 540, ein Hochkant-Clip 960 × 1706. Kleineres Material wird "
            "nicht hochskaliert. Die Auswahl gilt für alle Dateien, die ab "
            "jetzt hinzugefügt werden – ebenso der Codec."
        ),
        "drop": "Ordner oder Videodateien\nhier hineinziehen",
        "btn_files": "Dateien wählen …",
        "btn_dir": "Ordner wählen …",
        "btn_cancel": "Abbrechen",
        "ready": "Bereit",
        "counts": "{done} von {total} Dateien erledigt · noch {left}",
        "status": "Zuletzt  : {last}\nAktuell  : {cur}\nNächste  : {nxt}",
        "pick_files": "Videodateien wählen",
        "pick_dir": "Ordner wählen",
        "tag_skip": "[übersprungen]",
        "tag_enc": "[encodiere]",
        "tag_done": "[fertig]",
        "tag_err": "[FEHLER]",
        "tag_cancel": "[abgebrochen]",
        "skip_exists": "Proxy existiert bereits",
        "skip_novideo": "keine Videospur",
        "added": "{n} Datei(en) zur Warteschlange hinzugefügt "
                 "({codec}, Mindestauflösung {w}x{h}).",
        "no_files": "Keine Videodateien gefunden.",
        "cancel_req": "Abbruch angefordert …",
        "finished": "Fertig: {c} erstellt, {s} übersprungen, {f} Fehler.\n",
        "ffmpeg_missing": "FEHLER: FFmpeg wurde nicht gefunden.",
        "ffmpeg_info": "FFmpeg {ver} · {path}",
        "rl_locate": "REDline suchen (Teil von REDCINE-X PRO)",
        "rl_found": "REDline gefunden: {path}",
        "rl_missing": "REDline nicht gefunden. Für .R3D-Dateien wird "
                      "REDCINE-X PRO von RED benötigt (kostenlos).",
        "rl_noprores": "Diese REDline-Version bietet keinen ProRes-Export. "
                       "Bitte REDCINE-X PRO aktualisieren.",
        "r3d_meta": "R3D-Metadaten konnten nicht gelesen werden",
        "braw_missing": "Blackmagic-RAW-Unterstützung ist in diesem Build nicht "
                        "enthalten (BRAW-SDK fehlte beim Bauen).",
        "braw_found": "Blackmagic RAW: aktiv",
        "about_tip": "Über Proxy Maker",
        "about_title": "Über Proxy Maker",
        "about_version": "Version {v}",
        "about_body": (
            "Erstellt Proxy-Dateien, damit sich hochauflösendes Material "
            "flüssig schneiden lässt. Ursprünglich geschrieben für "
            "<b>DaVinci Resolve</b>: Die Proxies landen direkt im Unterordner "
            "„Proxy“ neben ihren Quelldateien, sodass Resolve sie beim Import "
            "automatisch verknüpft.<br><br>"
            "Standardformat ist <b>Apple ProRes 422 Proxy</b>; alternativ "
            "Avid DNxHR LB, GoPro CineForm oder ein leicht abspielbares H.264."
        ),
        "about_formats": (
            "<b>Unterstützte Quellformate:</b><br>"
            "• RED <b>R3D</b> (über REDline, falls installiert)<br>"
            "• Blackmagic <b>BRAW</b><br>"
            "• Apple <b>ProRes RAW</b> mit automatischem Weißabgleich<br>"
            "• alles, was FFmpeg lesen kann – z. B. Sony XAVC, H.264/H.265, "
            "ProRes, DNx"
        ),
        "about_author": "Geschrieben von Claude (KI von Anthropic) "
                        "in Zusammenarbeit mit STEEPTWO.",
        "about_contact": "Kontakt",
        "about_license": (
            "<b>Lizenz:</b> MIT – frei für jeden Zweck nutzbar, auch "
            "kommerziell. Ändern und Weitergeben ausdrücklich erlaubt. "
            "Ohne Gewähr."
        ),
        "about_thirdparty": "Enthält FFmpeg (ffmpeg.org, GPL) und "
                            "Qt for Python (LGPL).",
        "about_close": "Schließen",
        "update_auto": "Automatisch nach Updates suchen",
        "update_now": "Jetzt prüfen",
        "update_checking": "Suche …",
        "update_current": "Proxy Maker ist auf dem neuesten Stand.",
        "update_failed": "Prüfung nicht möglich (keine Verbindung?).",
        "update_title": "Update verfügbar",
        "update_question": "Neue Version verfügbar. Jetzt herunterladen?\n\n"
                           "Installiert: {cur}\nNeu: {new}",
        "update_yes": "Herunterladen",
        "update_no": "Später",
        "settings_tip": "Einstellungen",
        "settings_title": "Einstellungen",
        "set_codec": "Standardformat",
        "set_codec_hint": "Gilt für neu hinzugefügte Dateien. In der Warteschlange "
                          "lässt sich jede Datei weiterhin einzeln umstellen.",
        "set_dest": "Speicherort der Proxies",
        "set_dest_beside": "Neben den Quelldateien (Ordner „Proxy“)",
        "set_dest_central": "Alles an einem Ort:",
        "set_dest_info": "• Neben den Quelldateien: Die Proxies landen im Unterordner "
                         "„Proxy“ – DaVinci Resolve verknüpft sie beim Import "
                         "automatisch.\n• Alles an einem Ort: Alle Proxies kommen in "
                         "einen Ordner, die Ordnerstruktur der Quellen wird dort "
                         "nachgebaut. Verknüpfen in Resolve mit „Link Proxy Media…“, "
                         "in Premiere mit „Proxy → Attach Proxies…“.",
        "set_dest_hint": "Verknüpfen: Resolve „Link Proxy Media…“ · "
                         "Premiere „Proxy → Attach Proxies…“",
        "set_dest_locked": "Während des Renderns nicht änderbar.",
        "set_browse": "Auswählen…",
        "set_watch": "Überwachte Ordner",
        "set_watch_on": "Diese Ordner überwachen",
        "set_watch_hint": "Wird alle 10 Sekunden geprüft, inklusive Unterordner. "
                          "Dateien kommen erst dazu, wenn sie 30 Sekunden lang "
                          "unverändert waren (fertig kopiert). Ändert sich eine Datei "
                          "danach noch, wird ihr Proxy neu erstellt. Nur solange "
                          "Proxy Maker geöffnet ist.",
        "set_add": "Hinzufügen…",
        "set_remove": "Entfernen",
        "set_power": "Beim Rendern",
        "set_awake": "Computer wach halten",
        "set_power_info": "• Computer wach halten: verhindert den Energiesparmodus, "
                          "solange gerendert wird (der Bildschirm darf trotzdem "
                          "ausgehen).\n• Wenn fertig: Energiesparmodus oder "
                          "Herunterfahren nach einem 60-Sekunden-Countdown, der sich "
                          "abbrechen lässt. Gilt nur für diese Sitzung und ist nicht "
                          "verfügbar, solange Ordner überwacht werden.",
        "set_update_auto": "Automatisch prüfen",
        "set_update_info": "Beim Start fragt Proxy Maker bei GitHub nach, ob es eine "
                           "neuere Version gibt, und bietet dann die Download-Seite "
                           "an. Es wird nichts automatisch heruntergeladen.",
        "set_after": "Wenn fertig:",
        "after_none": "Nichts tun",
        "after_sleep": "Energiesparmodus",
        "after_shutdown": "Herunterfahren",
        "set_after_hint": "Gilt nur für diese Sitzung. Nicht verfügbar, solange "
                          "Ordner überwacht werden.",
        "set_updates": "Updates",
        "watching": "Überwache {n} Ordner",
        "watching_missing": "Überwache {n} Ordner · {m} nicht erreichbar",
        "watch_unreachable": "Nicht erreichbar:",
        "watch_reachable": "Werden überwacht:",
        "watch_lost": "Überwachter Ordner nicht erreichbar: {path}",
        "watch_back": "Überwachter Ordner wieder erreichbar: {path}",
        "watch_added": "Überwachter Ordner: {n} neue Datei(en) hinzugefügt.",
        "watch_redo": "Quelldatei hat sich geändert – Proxy wird neu erstellt",
        "watch_tip": "So funktioniert die Ordnerüberwachung:\n"
                     "• Alle 10 Sekunden wird nach neuen Dateien gesucht "
                     "(inklusive Unterordner).\n"
                     "• Eine neue Datei kommt erst in die Warteschlange, wenn sie "
                     "30 Sekunden lang unverändert war – so werden Dateien, die "
                     "noch kopiert werden, nicht zu früh verarbeitet.\n"
                     "• Ändert sich eine Datei danach noch (z.B. weil ein Kopiervorgang "
                     "pausiert hatte), wird ihr Proxy gelöscht und neu erstellt.\n"
                     "• Bereits vorhandene Proxies werden nie angefasst.\n"
                     "• Nur solange Proxy Maker geöffnet ist.",
        "disk_checking": "Prüfe Speicherplatz …",
        "disk_title": "Zu wenig Speicherplatz?",
        "disk_question": "Die Proxies brauchen voraussichtlich mehr Platz, als frei "
                         "ist:\n\n{lines}\n\nDas ist eine Schätzung. Trotzdem starten?",
        "disk_line": "{loc}: benötigt ca. {need}, frei {free}",
        "disk_start": "Trotzdem starten",
        "disk_cancel": "Abbrechen",
        "disk_not_started": "Nicht gestartet – zu wenig Speicherplatz: {lines}",
        "disk_full": "Zu wenig Speicherplatz am Ziel",
        "after_title": "Rendern abgeschlossen",
        "after_sleep_in": "Der Computer wechselt in {s} s in den Energiesparmodus.",
        "after_shutdown_in": "Der Computer fährt in {s} s herunter.",
        "after_now": "Jetzt",
        "after_abort": "Abbrechen",
        "after_failed": "Energiesparmodus/Herunterfahren fehlgeschlagen: {err}",
        "queue_title": "Warteschlange",
        "queue_empty": "Noch leer – Dateien oder Ordner links hineinziehen",
        "btn_start": "▶  Start",
        "btn_remove": "Entfernen",
        "btn_clear": "Leeren",
        "btn_add": "Hinzufügen",
        "queued": "{n} Datei(en) in die Warteschlange gelegt "
                  "({codec}, Mindestauflösung {w}x{h}). Mit „Start“ geht es los.",
        "already_queued": "Bereits in der Warteschlange – nichts Neues hinzugefügt.",
        "removed": "{n} Datei(en) aus der Warteschlange entfernt.",
        "idle": "Bereit",
        "empty_hint": "Dateien oder Ordner hineinziehen",
        "or": "oder",
        "info_tip": "Proxies werden in {scale} gerendert (änderbar in den "
                    "Einstellungen ⚙), aber nie kleiner als die Mindestauflösung – "
                    "Breite und Höhe gelten einzeln. Das Seitenverhältnis bleibt "
                    "immer erhalten, kleineres Material wird nicht hochskaliert.\n\n"
                    "Die Mindestauflösung gilt für alle Dateien, die danach "
                    "hinzugefügt werden. Das Format kann man pro Datei in der "
                    "Liste noch ändern.",
        "scale_4": "Viertelauflösung (1:4)",
        "scale_2": "halber Auflösung (1:2)",
        "scale_1": "voller Auflösung (1:1)",
        "set_scale": "Proxy-Größe",
        "set_scale_4": "1:4 – Viertelauflösung (Standard)",
        "set_scale_2": "1:2 – halbe Auflösung",
        "set_scale_1": "1:1 – volle Auflösung (keine Verkleinerung)",
        "set_scale_hint": "Gilt ab dem nächsten Renderstart für alle Dateien. Die "
                          "Mindestauflösung im Hauptfenster gilt weiterhin; bei 1:1 "
                          "hat sie keine Wirkung.",
        "add_tip": "Dateien oder Ordner hinzufügen",
        "add_files": "Dateien …",
        "add_dir": "Ordner …",
        "st_wait": "wartet",
        "st_done": "✓ fertig",
        "st_skip": "übersprungen",
        "st_err": "Fehler",
        "st_cancel": "abgebrochen",
        "remove_tip": "Aus der Liste entfernen",
        "log_toggle": "Log",
        "perf_low": "Schonend",
        "perf_high": "Maximal",
        "perf_tip": "Schonend: Proxy Maker läuft mit niedriger Priorität, Resolve "
                    "und andere Programme haben Vorrang.\nMaximal: volle Leistung "
                    "für Proxy Maker.\n\nEs laufen immer bis zu 4 Dateien "
                    "gleichzeitig, Grafikkarte und Hardware-Encoder werden genutzt, "
                    "wo möglich.",
        "active": "aktiv",
        "accel_info": "Beschleunigung",
        "cpu_retry": "neuer Versuch nur mit CPU",
        "theme_rainbow": "Regenbogen",
        "theme_light": "Hell",
        "theme_dark": "Dunkel",
        "theme_tip": "Farbschema",
        "net_drive": "Netzlaufwerk",
        "local_file": "Lokale Datei",
        "g_net": "Netz",
    },
    "en": {
        "subtitle": "1:4 · 1:2 · 1:1 · “Proxy” subfolder",
        "codec_label": "Codec:",
        "codec_h264": "H.264 (easy playback)",
        "min_label": "Minimum resolution:",
        "custom_item": "Custom …",
        "width": "Width ",
        "height": "Height ",
        "hint": (
            "Proxies are scaled down to the chosen size (1:4, 1:2 or 1:1), "
            "but never below these values. Width and height are each treated "
            "as a separate lower limit, so the source aspect ratio is always "
            "preserved – 16:9, scope, 4:3 or vertical alike. Example at "
            "960 × 540: a 2.39:1 clip becomes 1290 × 540, a vertical clip "
            "960 × 1706. Smaller footage is never upscaled. The setting "
            "applies to all files added from now on – as does the codec."
        ),
        "drop": "Drop folders or\nvideo files here",
        "btn_files": "Choose files …",
        "btn_dir": "Choose folder …",
        "btn_cancel": "Cancel",
        "ready": "Ready",
        "counts": "{done} of {total} files done · {left} remaining",
        "status": "Last     : {last}\nCurrent  : {cur}\nNext     : {nxt}",
        "pick_files": "Choose video files",
        "pick_dir": "Choose folder",
        "tag_skip": "[skipped]",
        "tag_enc": "[encoding]",
        "tag_done": "[done]",
        "tag_err": "[ERROR]",
        "tag_cancel": "[cancelled]",
        "skip_exists": "proxy already exists",
        "skip_novideo": "no video stream",
        "added": "{n} file(s) added to the queue ({codec}, minimum resolution {w}x{h}).",
        "no_files": "No video files found.",
        "cancel_req": "Cancelling …",
        "finished": "Done: {c} created, {s} skipped, {f} errors.\n",
        "ffmpeg_missing": "ERROR: FFmpeg was not found.",
        "ffmpeg_info": "FFmpeg {ver} · {path}",
        "rl_locate": "Locate REDline (part of REDCINE-X PRO)",
        "rl_found": "REDline found: {path}",
        "rl_missing": "REDline not found. .R3D files require RED's free "
                      "REDCINE-X PRO.",
        "rl_noprores": "This REDline version has no ProRes export. "
                       "Please update REDCINE-X PRO.",
        "r3d_meta": "could not read R3D metadata",
        "braw_missing": "Blackmagic RAW support is not included in this build "
                        "(the BRAW SDK was missing at build time).",
        "braw_found": "Blackmagic RAW: enabled",
        "about_tip": "About Proxy Maker",
        "about_title": "About Proxy Maker",
        "about_version": "Version {v}",
        "about_body": (
            "Creates proxy files so that high-resolution footage edits "
            "smoothly. Originally written for <b>DaVinci Resolve</b>: proxies "
            "are placed directly in a “Proxy” subfolder next to their source "
            "files, so Resolve links them automatically on import.<br><br>"
            "Default output is <b>Apple ProRes 422 Proxy</b>; alternatively "
            "Avid DNxHR LB, GoPro CineForm or an easy-to-play H.264."
        ),
        "about_formats": (
            "<b>Supported source formats:</b><br>"
            "• RED <b>R3D</b> (via REDline, if installed)<br>"
            "• Blackmagic <b>BRAW</b><br>"
            "• Apple <b>ProRes RAW</b> with automatic white balance<br>"
            "• everything FFmpeg can read – e.g. Sony XAVC, H.264/H.265, "
            "ProRes, DNx"
        ),
        "about_author": "Written by Claude (AI by Anthropic) "
                        "in collaboration with STEEPTWO.",
        "about_contact": "Contact",
        "about_license": (
            "<b>License:</b> MIT – free to use for any purpose, including "
            "commercial use. Modifying and redistributing are explicitly "
            "allowed. No warranty."
        ),
        "about_thirdparty": "Includes FFmpeg (ffmpeg.org, GPL) and "
                            "Qt for Python (LGPL).",
        "about_close": "Close",
        "update_auto": "Check for updates automatically",
        "update_now": "Check now",
        "update_checking": "Checking …",
        "update_current": "Proxy Maker is up to date.",
        "update_failed": "Could not check (no connection?).",
        "update_title": "Update available",
        "update_question": "New version available. Do you want to download?\n\n"
                           "Installed: {cur}\nNew: {new}",
        "update_yes": "Download",
        "update_no": "Later",
        "settings_tip": "Settings",
        "settings_title": "Settings",
        "set_codec": "Default format",
        "set_codec_hint": "Used for newly added files. Each file in the queue can "
                          "still be changed individually.",
        "set_dest": "Proxy location",
        "set_dest_beside": "Next to the source files (“Proxy” folder)",
        "set_dest_central": "All in one location:",
        "set_dest_info": "• Next to the source files: proxies go into a “Proxy” "
                         "subfolder – DaVinci Resolve links them automatically on "
                         "import.\n• All in one location: all proxies go into one "
                         "folder, with the source folder structure recreated there. "
                         "To link: Resolve “Link Proxy Media…”, Premiere “Proxy → "
                         "Attach Proxies…”.",
        "set_dest_hint": "To link: Resolve “Link Proxy Media…” · "
                         "Premiere “Proxy → Attach Proxies…”",
        "set_dest_locked": "Can't be changed while rendering.",
        "set_browse": "Choose…",
        "set_watch": "Watch folders",
        "set_watch_on": "Watch these folders",
        "set_watch_hint": "Checked every 10 seconds, including subfolders. Files are "
                          "only added once they have been unchanged for 30 seconds "
                          "(finished copying). If a file still changes afterwards, "
                          "its proxy is re-created. Only while Proxy Maker is open.",
        "set_add": "Add…",
        "set_remove": "Remove",
        "set_power": "While rendering",
        "set_awake": "Keep computer awake",
        "set_power_info": "• Keep computer awake: prevents sleep while rendering "
                          "(the screen may still turn off).\n• When finished: sleep "
                          "or shut down after a 60-second countdown that can be "
                          "cancelled. Applies to this session only and isn't "
                          "available while watch folders are active.",
        "set_update_auto": "Check automatically",
        "set_update_info": "At startup Proxy Maker asks GitHub whether a newer "
                           "version exists and then offers the download page. "
                           "Nothing is downloaded automatically.",
        "set_after": "When finished:",
        "after_none": "Do nothing",
        "after_sleep": "Sleep",
        "after_shutdown": "Shut down",
        "set_after_hint": "Applies to this session only. Not available while "
                          "watch folders are active.",
        "set_updates": "Updates",
        "watching": "Watching {n} folder(s)",
        "watching_missing": "Watching {n} folder(s) · {m} not reachable",
        "watch_unreachable": "Not reachable:",
        "watch_reachable": "Being watched:",
        "watch_lost": "Watch folder not reachable: {path}",
        "watch_back": "Watch folder reachable again: {path}",
        "watch_added": "Watch folder: {n} new file(s) added.",
        "watch_redo": "source file changed – proxy will be re-created",
        "watch_tip": "How watch folders work:\n"
                     "• Every 10 seconds the folders are checked for new files "
                     "(including subfolders).\n"
                     "• A new file is only queued once it has been unchanged for "
                     "30 seconds – so files that are still being copied aren't "
                     "processed too early.\n"
                     "• If a file still changes afterwards (e.g. a paused copy "
                     "resumed), its proxy is deleted and re-created.\n"
                     "• Proxies that already existed are never touched.\n"
                     "• Only while Proxy Maker is open.",
        "disk_checking": "Checking disk space …",
        "disk_title": "Not enough disk space?",
        "disk_question": "The proxies will probably need more space than is "
                         "free:\n\n{lines}\n\nThis is an estimate. Start anyway?",
        "disk_line": "{loc}: needs about {need}, free {free}",
        "disk_start": "Start anyway",
        "disk_cancel": "Cancel",
        "disk_not_started": "Not started – not enough disk space: {lines}",
        "disk_full": "Not enough disk space at the destination",
        "after_title": "Rendering finished",
        "after_sleep_in": "The computer will go to sleep in {s} s.",
        "after_shutdown_in": "The computer will shut down in {s} s.",
        "after_now": "Now",
        "after_abort": "Cancel",
        "after_failed": "Sleep/shut down failed: {err}",
        "queue_title": "Queue",
        "queue_empty": "Empty – drop files or folders on the left",
        "btn_start": "▶  Start",
        "btn_remove": "Remove",
        "btn_clear": "Clear",
        "btn_add": "Add",
        "queued": "{n} file(s) added to the queue ({codec}, minimum resolution "
                  "{w}x{h}). Press “Start” to begin.",
        "already_queued": "Already in the queue – nothing new added.",
        "removed": "{n} file(s) removed from the queue.",
        "idle": "Ready",
        "empty_hint": "Drop files or folders here",
        "or": "or",
        "info_tip": "Proxies are rendered at {scale} (change in Settings ⚙), but "
                    "never smaller than the minimum resolution – width and height "
                    "count separately. The aspect ratio is always preserved and "
                    "smaller footage is never upscaled.\n\nThe minimum resolution "
                    "applies to all files added afterwards. The format can still "
                    "be changed per file in the list.",
        "scale_4": "quarter resolution (1:4)",
        "scale_2": "half resolution (1:2)",
        "scale_1": "full resolution (1:1)",
        "set_scale": "Proxy size",
        "set_scale_4": "1:4 – quarter resolution (default)",
        "set_scale_2": "1:2 – half resolution",
        "set_scale_1": "1:1 – full resolution (no downscaling)",
        "set_scale_hint": "Applies to all files from the next render start. The "
                          "minimum resolution in the main window still applies; "
                          "at 1:1 it has no effect.",
        "add_tip": "Add files or folders",
        "add_files": "Files …",
        "add_dir": "Folder …",
        "st_wait": "waiting",
        "st_done": "✓ done",
        "st_skip": "skipped",
        "st_err": "error",
        "st_cancel": "cancelled",
        "remove_tip": "Remove from list",
        "log_toggle": "Log",
        "perf_low": "Gentle",
        "perf_high": "Maximum",
        "perf_tip": "Gentle: Proxy Maker runs at low priority, Resolve and other "
                    "apps come first.\nMaximum: full power for Proxy Maker.\n\n"
                    "Up to 4 files are always processed at once; the graphics card "
                    "and hardware encoders are used where possible.",
        "active": "active",
        "accel_info": "Acceleration",
        "cpu_retry": "retrying with CPU only",
        "theme_rainbow": "Rainbow",
        "theme_light": "Light",
        "theme_dark": "Dark",
        "theme_tip": "Color theme",
        "net_drive": "Network drive",
        "local_file": "Local file",
        "g_net": "Net",
    },
}
LANG = "de"


def tr(key: str, **kw) -> str:
    text = STRINGS.get(LANG, STRINGS["en"]).get(key) or STRINGS["en"][key]
    return text.format(**kw) if kw else text


def logline(tag: str, name: str, extra: str = "") -> str:
    return f"{tr(tag):<15}{name}" + (f" – {extra}" if extra else "")
# --------------------------------------------------------------------------


def settings() -> QSettings:
    return QSettings("STEEPTWO", APP_NAME)


def asset(name: str) -> Path:
    return ROOT / "assets" / name


def setting_bool(key: str, default: bool) -> bool:
    v = settings().value(key, "true" if default else "false")
    return str(v).lower() in ("true", "1")


def set_setting_bool(key: str, on: bool) -> None:
    settings().setValue(key, "true" if on else "false")


def updates_enabled() -> bool:
    return setting_bool("check_updates", True)


def watch_dirs() -> list[str]:
    import json
    try:
        val = json.loads(str(settings().value("watch_dirs", "[]")))
        return [str(d) for d in val] if isinstance(val, list) else []
    except ValueError:
        return []


def set_watch_dirs(dirs: list[str]) -> None:
    import json
    settings().setValue("watch_dirs", json.dumps(dirs))


def scale_setting() -> int:
    """Proxy-Groesse als Teiler: 4 = 1:4, 2 = 1:2, 1 = 1:1."""
    try:
        v = int(settings().value("scale", core.DEFAULT_SCALE))
    except (TypeError, ValueError):
        v = core.DEFAULT_SCALE
    return v if v in core.SCALES else core.DEFAULT_SCALE


def output_root() -> str | None:
    """None = Proxy-Ordner neben der Quelle."""
    if str(settings().value("out_mode", "beside")) != "central":
        return None
    root = str(settings().value("out_root", "") or "")
    return root or None


def ask_update(parent, tag: str, url: str) -> bool:
    """Asks whether to download the new version; opens its release page on yes."""
    box = QMessageBox(QMessageBox.Question, tr("update_title"),
                      tr("update_question", cur=APP_VERSION, new=tag.lstrip("vV")),
                      parent=parent)
    yes = box.addButton(tr("update_yes"), QMessageBox.AcceptRole)
    box.addButton(tr("update_no"), QMessageBox.RejectRole)
    box.setDefaultButton(yes)
    box.exec()
    if box.clickedButton() is yes:
        QDesktopServices.openUrl(QUrl(url))
        return True
    return False


def wrap_tip(text: str) -> str:
    """Rich-Text-Tooltip -> Qt bricht um und haelt die maximale Breite ein."""
    import html
    return "<qt>" + html.escape(text).replace("\n", "<br>") + "</qt>"


def theme_preview_icon(key: str, w: int = 30, h: int = 16) -> QIcon:
    """Kleine Vorschau eines Themes: Hintergrund + Akzentstreifen."""
    th = THEMES[key]
    scale = 3
    pm = QPixmap(w * scale, h * scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(scale, scale)
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, w, h, 3.5, 3.5)
    p.setClipPath(clip)
    if th["rainbow"]:
        g = QLinearGradient(0, h, w, 0)
        for i in range(7):
            g.setColorAt(i / 6, QColor.fromHsvF((i % 6) / 6, 1.0, 0.75))
        p.fillRect(0, 0, w, h, g)
    else:
        p.fillRect(0, 0, w, h, QColor(th["bg"]))
        p.fillRect(0, 0, w, h * 0.4, QColor(th["panel"]))
        p.fillRect(w * 0.55, h * 0.58, w * 0.33, h * 0.24, QColor(th["accent"]))
    p.end()
    return QIcon(pm)


def system_theme() -> str:
    """Hell/Dunkel wie im Betriebssystem eingestellt."""
    app = QGuiApplication.instance()
    try:
        scheme = app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
        if scheme == Qt.ColorScheme.Light:
            return "light"
    except Exception:
        pass
    try:  # Fallback: Helligkeit der Systempalette
        return "dark" if app.palette().window().color().lightness() < 128 else "light"
    except Exception:
        return "dark"


def flag_icon(code: str, w: int = 30, h: int = 20) -> QIcon:
    """Zeichnet die Flagge selbst - Flaggen-Emojis fehlen unter Windows."""
    scale = 3  # scharf auf Retina/HiDPI
    pm = QPixmap(w * scale, h * scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(scale, scale)
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, w, h, 2.5, 2.5)
    p.setClipPath(clip)
    if code == "de":
        for i, col in enumerate(("#000000", "#DD0000", "#FFCE00")):
            p.fillRect(0, i * h / 3, w, h / 3 + 0.5, QColor(col))
    else:  # Union Jack (vereinfacht)
        p.fillRect(0, 0, w, h, QColor("#012169"))
        for col, width in (("#FFFFFF", h * 0.30), ("#C8102E", h * 0.11)):
            p.setPen(QPen(QColor(col), width))
            p.drawLine(0, 0, w, h)
            p.drawLine(0, h, w, 0)
        for col, t in (("#FFFFFF", h / 3), ("#C8102E", h / 5)):
            p.fillRect(0, (h - t) / 2, w, t, QColor(col))
            p.fillRect((w - t) / 2, 0, t, h, QColor(col))
    p.end()
    return QIcon(pm)


MAX_PARALLEL = 4  # Dateien gleichzeitig
MAX_RAW = 2       # davon hoechstens so viele R3D/BRAW (Speicher, GPU)


class Worker(QThread):
    counts = Signal(int, int)             # erledigt, gesamt
    item_progress = Signal(str, float)    # Pfad, 0..1
    log = Signal(str)
    started_item = Signal(str)            # Pfad der Datei, die jetzt beginnt
    item_done = Signal(str, str)          # Pfad, Ergebnis: done/skip/error/cancel
    finished_all = Signal(int, int, int)  # erstellt, uebersprungen, fehler

    def __init__(self, ffmpeg: str):
        super().__init__()
        self.ffmpeg = ffmpeg
        self.redline: str | None = None
        self.braw = braw.find()
        # (Datei, Mindestaufloesung, Codec)
        self.pending: deque[tuple[Path, tuple[int, int], str]] = deque()
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.raw_slots = threading.Semaphore(MAX_RAW)
        self.reserved: set[Path] = set()   # Proxy-Ziele, die gerade entstehen
        self.done = self.total = 0
        self.created = self.skipped = self.failed = 0

    def add(self, items: list[tuple[Path, tuple[int, int], str]]) -> int:
        with self.lock:
            known = {it[0] for it in self.pending}
            new = [it for it in items if it[0] not in known]
            self.pending.extend(new)
            self.total += len(new)
        self.counts.emit(self.done, self.total)
        return len(new)

    def set_codec(self, path: Path, codec: str) -> None:
        with self.lock:
            self.pending = deque((p, m, codec if p == path else c)
                                 for p, m, c in self.pending)

    def remove(self, paths: set[Path]) -> None:
        with self.lock:
            keep = deque(it for it in self.pending if it[0] not in paths)
            self.total -= len(self.pending) - len(keep)
            self.pending = keep
        self.counts.emit(self.done, self.total)

    def stop(self):
        self.cancel.set()

    # ------------------------------------------------------------ Encoder
    def _hw_note(self, codec: str, cpu_only: bool) -> str:
        if cpu_only:
            return " · CPU"
        hw = accel.hw_encoder(self.ffmpeg, codec)
        return f" · {hw[1]}" if hw else ""

    def _encode_r3d(self, src, min_size, codec, progress, cpu_only) -> bool:
        if not self.redline:
            raise RuntimeError(tr("rl_missing"))
        fmt = redline.prores_format(self.redline)
        if fmt is None:
            raise RuntimeError(tr("rl_noprores"))
        info = redline.probe(self.redline, src)
        if info is None:
            raise RuntimeError(tr("r3d_meta"))
        w, h = core.output_size(info.width, info.height, min_size, codec)
        self.log.emit(logline("tag_enc", src.name,
                              f"{info.width}x{info.height} → {w}x{h} "
                              f"{CODEC_SHORT[codec]} (REDline){self._hw_note(codec, cpu_only)}"))
        redline.encode(self.redline, fmt, src, info, min_size, progress,
                       self.cancel.is_set, self.ffmpeg,
                       on_log=lambda t: self.log.emit(f"{'':15}{src.name}: {t}"),
                       codec=codec, cpu_only=cpu_only)
        return True

    def _encode_braw(self, src, min_size, codec, progress, cpu_only) -> bool:
        if not self.braw:
            raise RuntimeError(tr("braw_missing"))
        info, scale = braw.plan(self.braw, src, min_size)
        w, h = core.output_size(info.width, info.height, min_size, codec)
        self.log.emit(logline("tag_enc", src.name,
                              f"{info.width}x{info.height} → {w}x{h} "
                              f"{CODEC_SHORT[codec]} (BRAW){self._hw_note(codec, cpu_only)}"))
        braw.encode(self.braw, self.ffmpeg, src, min_size, progress,
                    self.cancel.is_set, (info, scale), codec=codec, cpu_only=cpu_only)
        return True

    def _encode_ffmpeg(self, src, min_size, codec, progress, cpu_only) -> bool:
        info = core.probe(self.ffmpeg, src)
        if info is None:
            self.log.emit(logline("tag_skip", src.name, tr("skip_novideo")))
            return False
        w, h = core.output_size(info.width, info.height, min_size, codec)
        gpu_dec = "" if cpu_only or not accel.hwaccel_args(info.vcodec) else " · GPU-Dec"
        self.log.emit(logline("tag_enc", src.name,
                              f"{info.width}x{info.height} → {w}x{h} "
                              f"{CODEC_SHORT[codec]}{self._hw_note(codec, cpu_only)}{gpu_dec}"))
        core.encode(self.ffmpeg, src, info, progress, self.cancel.is_set,
                    min_size, codec=codec, cpu_only=cpu_only)
        return True

    def _process(self, src: Path, min_size, codec) -> str:
        """Eine Datei; bei Fehler mit Hardware-Beschleunigung ein zweiter
        Versuch rein auf der CPU."""
        dst = core.proxy_path(src)
        with self.lock:
            busy = dst in self.reserved
            if not busy:
                self.reserved.add(dst)
        if busy or dst.exists():
            self.log.emit(logline("tag_skip", src.name, tr("skip_exists")))
            if not busy:
                with self.lock:
                    self.reserved.discard(dst)
            return "skip"
        enc = (self._encode_r3d if core.is_r3d(src) else
               self._encode_braw if core.is_braw(src) else self._encode_ffmpeg)
        progress = lambda f, p=str(src): self.item_progress.emit(p, f)
        raw = core.is_r3d(src) or core.is_braw(src)
        if raw:
            while not self.raw_slots.acquire(timeout=0.2):
                if self.cancel.is_set():
                    raise core.Cancelled()
        try:
            if diskcheck.nearly_full(dst):  # Notbremse, auch fuer spaeter Hinzugefuegtes
                raise RuntimeError(tr("disk_full"))
            try:
                ok = enc(src, min_size, codec, progress, False)
            except core.Cancelled:
                raise
            except Exception as exc:
                if self.cancel.is_set():
                    raise core.Cancelled()
                self.log.emit(logline("tag_err", src.name, f"{exc} → {tr('cpu_retry')}"))
                ok = enc(src, min_size, codec, progress, True)
            if ok:
                self.log.emit(logline("tag_done", src.name))
            return "done" if ok else "skip"
        finally:
            if raw:
                self.raw_slots.release()
            with self.lock:
                self.reserved.discard(dst)

    def _loop(self):
        while not self.cancel.is_set():
            with self.lock:
                if not self.pending:
                    return
                src, min_size, codec = self.pending.popleft()
            self.started_item.emit(str(src))
            try:
                result = self._process(src, min_size, codec)
            except core.Cancelled:
                self.log.emit(logline("tag_cancel", src.name))
                self.item_done.emit(str(src), "cancel")
                return
            except Exception as exc:  # eine defekte Datei stoppt nicht alles
                result = "error"
                self.log.emit(logline("tag_err", src.name, str(exc)))
            with self.lock:
                if result == "done":
                    self.created += 1
                elif result == "skip":
                    self.skipped += 1
                else:
                    self.failed += 1
                self.done += 1
                done, total = self.done, self.total
            self.item_done.emit(str(src), result)
            self.counts.emit(done, total)

    def run(self):
        hw = accel.describe(self.ffmpeg)  # einmalig pruefen (dauert ein paar Sekunden)
        self.log.emit(f"{tr('accel_info')}: {hw}")
        threads = [threading.Thread(target=self._loop, daemon=True)
                   for _ in range(MAX_PARALLEL)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if self.cancel.is_set():
            with self.lock:
                self.pending.clear()
        self.finished_all.emit(self.created, self.skipped, self.failed)


class RainbowBackground(QWidget):
    """Diagonaler Regenbogen, der langsam von links nach rechts wandert."""

    TICK_MS = 40

    def __init__(self):
        super().__init__()
        self._off = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self.TICK_MS)

    def _tick(self):
        if not T["rainbow"]:
            return
        self._off = (self._off + RAINBOW_SPEED * self.TICK_MS / 1000) % RAINBOW_PERIOD
        self.update()

    def paintEvent(self, e):
        if not T["rainbow"]:
            QPainter(self).fillRect(self.rect(), QColor(T["bg"]))
            return
        half = RAINBOW_PERIOD / 2
        grad = QLinearGradient(self._off, 0, self._off + half, -half)
        grad.setSpread(QGradient.RepeatSpread)
        for i in range(7):
            grad.setColorAt(i / 6, QColor.fromHsvF((i % 6) / 6, 1.0, 1.0 - RAINBOW_DARKEN))
        QPainter(self).fillRect(self.rect(), grad)


def _rate(v: float) -> str:
    if v < 0:
        return "n/a"
    if v >= 1000:
        return f"{v / 1000:.1f} GB/s"
    return f"{v:.1f} MB/s" if v < 10 else f"{v:.0f} MB/s"


class UsageGraph(QWidget):
    """Schmaler Verlaufsgraph (letzte 60 Sekunden) mit Titel und Wert(en).

    unit "%"    -> feste Skala 0..100
    unit "MB/s" -> Skala passt sich dem hoechsten Wert im Fenster an
    dual=True   -> zwei Linien (Download ↓ gefuellt, Upload ↑ als Linie)
    Bewegt sich nur, solange gerendert wird (siehe MainWindow._usage).
    """

    def __init__(self, title: str, color_index: int, unit: str = "%",
                 dual: bool = False):
        super().__init__()
        self.title = title
        self.color_index = color_index
        self.unit = unit
        self.dual = dual
        self.values: deque[float] = deque(maxlen=60)
        self.values2: deque[float] = deque(maxlen=60)
        self.current: float | None = None   # None = noch nichts gemessen
        self.current2: float | None = None
        self.note: str | None = None        # z.B. "Netzlaufwerk" -> ausgegraut
        self.setFixedSize(150 if dual else 104, 32)

    def set_title(self, title: str):
        if title != self.title:
            self.title = title
            self.update()

    def set_note(self, note: str | None):
        if note != self.note:
            self.note = note
            self.update()

    def reset(self):
        self.values.clear()
        self.values2.clear()
        self.current = self.current2 = None
        self.update()

    def push(self, v: float, v2: float | None = None):
        self.current = v
        self.values.append(max(0.0, v))
        if self.dual:
            self.current2 = v2 if v2 is not None else -1
            self.values2.append(max(0.0, self.current2))
        self.update()

    def _segments(self) -> list[tuple[str, QColor]]:
        c1 = QColor(T["graph_colors"][self.color_index])
        if self.current is None:
            return [("–", None)]
        if self.dual:
            c2 = QColor(T["graph_colors"][4])
            return [(f"↓ {_rate(self.current)}", c1),
                    (f"  ↑ {_rate(self.current2 if self.current2 is not None else -1)}", c2)]
        if self.current < 0:
            return [("n/a", None)]
        if self.unit == "%":
            return [(f"{self.current:.0f} %", None)]
        return [(_rate(self.current), None)]

    def _plot(self, p: QPainter, plot: QRectF, values, color: QColor,
              top: float, filled: bool):
        if len(values) < 2:
            return
        n = values.maxlen or 60
        step = plot.width() / (n - 1)
        x0 = plot.right() - step * (len(values) - 1)
        pts = [QPointF(x0 + i * step, plot.bottom() - plot.height() * min(v, top) / top)
               for i, v in enumerate(values)]
        if filled:
            fill = QColor(color)
            fill.setAlpha(70)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawPolygon(QPolygonF([QPointF(pts[0].x(), plot.bottom()), *pts,
                                     QPointF(pts[-1].x(), plot.bottom())]))
        p.setPen(QPen(color, 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF(pts))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        text = QColor(*T["graph_text"])
        if self.note:
            text.setAlpha(110)

        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() * 0.75))
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetrics(f)

        # Wert(e) rechtsbuendig, bei Doppel-Graph jeweils in Linienfarbe
        segs = [] if self.note else self._segments()
        widths = [fm.horizontalAdvance(t) for t, _ in segs]
        x = r.width() - 2 - sum(widths)
        for (t, col), w in zip(segs, widths):
            p.setPen(col if col is not None else text)
            p.drawText(QRectF(x, 0, w + 2, 13), Qt.AlignLeft | Qt.AlignVCenter, t)
            x += w
        p.setPen(text)
        room = int(r.width() - 8 - sum(widths))
        p.drawText(QRectF(2, 0, max(0, room), 13), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(self.title, Qt.ElideRight, max(0, room)))

        plot = QRectF(2, 14, r.width() - 4, r.height() - 15)
        if self.note:
            p.drawText(plot, Qt.AlignCenter, self.note)
        else:
            if self.unit == "%":
                top = 100.0
            else:
                peak = max([*self.values, *self.values2, 0.0])
                top = max(1.0, peak * 1.15)
            self._plot(p, plot, self.values,
                       QColor(T["graph_colors"][self.color_index]), top, True)
            if self.dual:
                self._plot(p, plot, self.values2, QColor(T["graph_colors"][4]), top, False)
        p.end()


ELLIPSIS = "……"  # zwei Auslassungszeichen, damit die Kuerzung deutlich ist


def elide_middle(text: str, fm: QFontMetrics, width: int) -> str:
    """Anfang + "……" + Ende, so dass der Text genau in width passt."""
    if width <= 0:
        return ""
    if fm.horizontalAdvance(text) <= width:
        return text
    lo, hi = 0, len(text)  # Anzahl behaltener Zeichen (binaere Suche)
    while lo < hi:
        n = (lo + hi + 1) // 2
        cand = text[:(n + 1) // 2] + ELLIPSIS + text[len(text) - n // 2:]
        if fm.horizontalAdvance(cand) <= width:
            lo = n
        else:
            hi = n - 1
    n = lo
    return text[:(n + 1) // 2] + ELLIPSIS + text[len(text) - n // 2:] if n else ELLIPSIS


class MiddleElideLabel(QLabel):
    """Zeigt Anfang und Ende des Textes, passt sich der Breite an."""

    def __init__(self, text: str = ""):
        super().__init__()
        self.full = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(40)
        self._apply()

    def setFullText(self, text: str):
        self.full = text
        self._apply()

    def _apply(self):
        full = getattr(self, "full", None)  # kann vor __init__-Ende aufgerufen werden
        if full is not None:
            super().setText(elide_middle(full, self.fontMetrics(), self.width()))

    def resizeEvent(self, e):
        self._apply()
        super().resizeEvent(e)

    def changeEvent(self, e):  # Schrift kann per Stylesheet wechseln
        super().changeEvent(e)
        self._apply()


class LogFrame(QFrame):
    """Log-Fenster mit optionaler Animation (assets/log_animation.gif),
    links unten angedockt, 30 % Deckkraft, nur im Regenbogen-Theme."""

    SCALE = 0.5  # Pixelgrafik: ganzzahliges Verhaeltnis bleibt scharf

    def __init__(self):
        super().__init__()
        self.setObjectName("term")
        self.anim: QLabel | None = None
        self.movie: QMovie | None = None
        path = asset("log_animation.gif")
        if path.exists():
            self.movie = QMovie(str(path))
            self.movie.jumpToFrame(0)
            size = self.movie.currentImage().size()
            if size.width() > 0:
                self.movie.setScaledSize(QSize(int(size.width() * self.SCALE),
                                               int(size.height() * self.SCALE)))
            self.anim = QLabel(self)
            self.anim.setObjectName("logAnim")
            self.anim.setMovie(self.movie)
            self.anim.setAttribute(Qt.WA_TransparentForMouseEvents)
            fx = QGraphicsOpacityEffect(self.anim)
            fx.setOpacity(0.30)
            self.anim.setGraphicsEffect(fx)
            self.anim.hide()

    def set_enabled_anim(self, on: bool):
        if not self.anim:
            return
        self.anim.setVisible(on)
        if on:
            self.movie.start()
            self._place()
            self.anim.raise_()
        else:
            self.movie.stop()

    def _place(self):
        if self.anim:
            self.anim.adjustSize()
            self.anim.move(0, self.height() - self.anim.height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()


class InfoIcon(QLabel):
    """ⓘ mit eigenem Info-Fenster: schmal, rechts oberhalb des Symbols."""

    def __init__(self):
        super().__init__("ⓘ")
        self.setObjectName("info")
        self.popup = QLabel(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.popup.setObjectName("infoPop")
        self.popup.setWordWrap(True)
        self.popup.setFixedWidth(320)
        self.text = ""

    def set_text(self, text: str):
        self.text = text
        self.popup.setText(text)

    def enterEvent(self, e):
        self.popup.adjustSize()
        top_right = self.mapToGlobal(QPoint(self.width(), 0))
        x, y = top_right.x() + 4, top_right.y() - self.popup.height() - 4
        win = self.window()
        win_right = win.mapToGlobal(QPoint(win.width(), 0)).x() - 8
        win_top = win.mapToGlobal(QPoint(0, 0)).y()
        x = min(x, win_right - self.popup.width())
        if y < win_top:  # oben kein Platz -> unterhalb
            y = self.mapToGlobal(QPoint(0, self.height())).y() + 4
        self.popup.move(x, y)
        self.popup.show()

    def leaveEvent(self, e):
        self.popup.hide()


class PulseDot(QWidget):
    """Statuspunkt der Ordnerueberwachung: gruen mit pulsierender Aura, solange
    ueberwacht wird; bernsteinfarben und ruhig, wenn ein Ordner nicht
    erreichbar ist."""

    SIZE = 18          # Widget inkl. Aura (px)
    CORE = 3.5         # Radius des Punkts
    PERIOD_MS = 2000   # ein Atemzug
    TICK_MS = 50       # ~20 Bilder/s - nur dieses kleine Rechteck wird neu gezeichnet
    GREEN = QColor("#3ddc84")
    AMBER = QColor("#f5a524")

    def __init__(self):
        super().__init__()
        self.setFixedSize(self.SIZE, self.SIZE)
        self.warn = False
        self._t = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def set_warn(self, warn: bool):
        self.warn = warn
        self._sync()
        self.update()

    def showEvent(self, e):
        self._sync()
        super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop()  # unsichtbar -> keine Rechenzeit
        super().hideEvent(e)

    def _sync(self):
        if self.isVisible() and not self.warn:
            if not self._timer.isActive():
                self._timer.start(self.TICK_MS)
        else:
            self._timer.stop()

    def _tick(self):
        self._t = (self._t + self.TICK_MS) % self.PERIOD_MS
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        color = QColor(self.AMBER if self.warn else self.GREEN)
        if not self.warn:
            # Aura: waechst nach aussen und blendet dabei aus
            ph = self._t / self.PERIOD_MS
            r = self.CORE + ph * (self.SIZE / 2 - self.CORE - 0.5)
            aura = QColor(color)
            aura.setAlphaF(0.75 * (1 - ph) ** 1.5)
            p.setPen(Qt.NoPen)
            p.setBrush(aura)
            p.drawEllipse(c, r, r)
        # duenner dunkler Rand, damit der Punkt auch auf dem Regenbogen sichtbar ist
        p.setPen(QPen(QColor(0, 0, 0, 110), 1.0))
        p.setBrush(color)
        p.drawEllipse(c, self.CORE, self.CORE)
        p.end()


class StatusBar(QFrame):
    """Statuszeile, deren Hintergrund sich als Gesamtfortschritt fuellt."""

    def __init__(self):
        super().__init__()
        self.setObjectName("statusBar")
        self.progress = 0.0

    def set_progress(self, v: float):
        self.progress = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        p.setClipPath(path)
        p.fillRect(r, QColor(T["term_bg"]))
        if self.progress > 0:
            fill = QColor(T["term_accent"])
            fill.setAlpha(55)
            p.fillRect(QRectF(0, 0, r.width() * self.progress, r.height()), fill)
            edge = QColor(T["term_accent"])
            p.fillRect(QRectF(r.width() * self.progress - 2, 0, 2, r.height()), edge)
        p.end()


class QueueArea(QFrame):
    """Warteschlange und Ablageflaeche in einem. Leer: nur der Hinweis."""
    dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("queueArea")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.stack = QStackedLayout()
        # Seite 0: leer
        empty = QWidget()
        empty.setObjectName("emptyPage")
        el = QVBoxLayout(empty)
        el.addStretch()
        self.empty_label = QLabel()
        self.empty_label.setObjectName("emptyHint")
        self.empty_label.setAlignment(Qt.AlignCenter)
        el.addWidget(self.empty_label)
        links = QHBoxLayout()
        links.addStretch()
        self.link_files = QPushButton()
        self.link_or = QLabel()
        self.link_or.setObjectName("emptyOr")
        self.link_dir = QPushButton()
        for b in (self.link_files, self.link_dir):
            b.setObjectName("link")
            b.setCursor(Qt.PointingHandCursor)
        links.addWidget(self.link_files)
        links.addWidget(self.link_or)
        links.addWidget(self.link_dir)
        links.addStretch()
        el.addLayout(links)
        el.addStretch()
        self.stack.addWidget(empty)
        # Seite 1: Liste
        self.list = QListWidget()
        self.list.setObjectName("queueList")
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.list.setFocusPolicy(Qt.NoFocus)
        self.stack.addWidget(self.list)
        outer.addLayout(self.stack, 1)

        # unten rechts: "Hinzufuegen" (auch bei voller Liste)
        foot = QHBoxLayout()
        foot.setContentsMargins(8, 0, 10, 10)
        foot.addStretch()
        self.b_add = QPushButton()
        self.b_add.setObjectName("add")
        self.b_add.setCursor(Qt.PointingHandCursor)
        foot.addWidget(self.b_add)
        outer.addLayout(foot)
        self.setMinimumHeight(220)

    def show_list(self, has_items: bool):
        self.stack.setCurrentIndex(1 if has_items else 0)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self.setProperty("hover", True)
            self.style().polish(self)
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.setProperty("hover", False)
        self.style().polish(self)

    def dropEvent(self, e):
        self.dragLeaveEvent(e)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.dropped.emit(paths)
        e.acceptProposedAction()


class QueueRow(QWidget):
    """Zeile: Dateiname | Codec | Fortschritt/Status | ×"""

    def __init__(self, path: Path, ms: tuple[int, int], codec: str):
        super().__init__()
        self.setObjectName("queueRow")
        hl = QHBoxLayout(self)
        hl.setContentsMargins(10, 3, 6, 3)
        hl.setSpacing(10)
        self.name = MiddleElideLabel(path.name)
        self.name.setObjectName("queueName")
        self.name.setToolTip(wrap_tip(f"{path}\nmin {ms[0]}×{ms[1]}"))
        hl.addWidget(self.name, 1)
        self.combo = QComboBox()
        self.combo.setObjectName("queueCodec")
        for key in CODEC_NAMES:
            self.combo.addItem(CODEC_SHORT[key], key)
        self.combo.setCurrentIndex(max(0, self.combo.findData(codec)))
        hl.addWidget(self.combo)
        self.bar = QProgressBar()
        self.bar.setObjectName("rowBar")
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedSize(70, 5)
        self.bar.hide()
        hl.addWidget(self.bar)
        self.status = QLabel()
        self.status.setObjectName("rowStatus")
        self.status.setFixedWidth(84)
        self.status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hl.addWidget(self.status)
        self.x = QPushButton("×")
        self.x.setObjectName("rowX")
        self.x.setFixedSize(20, 20)
        self.x.setCursor(Qt.PointingHandCursor)
        hl.addWidget(self.x)
        self.state = "wait"

    def set_state(self, state: str, frac: float = 0.0):
        self.state = state
        running = state == "run"
        self.bar.setVisible(running)
        self.combo.setEnabled(state in ("wait", "error", "cancel"))
        self.x.setEnabled(not running)
        if running:
            self.bar.setValue(int(frac * 1000))
            self.status.setText(f"{int(frac * 100)} %")
        else:
            self.status.setText(tr({"wait": "st_wait", "done": "st_done", "skip": "st_skip",
                                    "error": "st_err", "cancel": "st_cancel"}[state]))
        self.status.setProperty("state", state)
        self.status.style().polish(self.status)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("about")
        self.setWindowTitle(tr("about_title"))
        self.setModal(True)
        self.setFixedWidth(440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 18)
        lay.setSpacing(10)

        head = QHBoxLayout()
        if asset("icon.png").exists():
            ic = QLabel()
            ic.setPixmap(QPixmap(str(asset("icon.png"))).scaledToHeight(
                48, Qt.SmoothTransformation))
            head.addWidget(ic)
        names = QVBoxLayout()
        t = QLabel(APP_NAME)
        t.setObjectName("aboutName")
        v = QLabel(tr("about_version", v=APP_VERSION))
        v.setObjectName("aboutVersion")
        names.addWidget(t)
        names.addWidget(v)
        head.addLayout(names)
        head.addStretch()
        lay.addLayout(head)

        def para(html: str, name: str = "aboutText") -> QLabel:
            lab = QLabel(html)
            lab.setObjectName(name)
            lab.setWordWrap(True)
            lab.setTextFormat(Qt.RichText)
            lab.setOpenExternalLinks(True)
            lay.addWidget(lab)
            return lab

        para(tr("about_body"))
        para(tr("about_formats"))
        para(tr("about_author"))
        para(f"<b>{tr('about_contact')}:</b> "
             f"<a href='mailto:{CONTACT}' style='color:{ACCENT}'>{CONTACT}</a>")
        para(tr("about_license"))
        para(tr("about_thirdparty"), "aboutSmall")

        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton(tr("about_close"))
        close.clicked.connect(self.accept)
        close.setDefault(True)
        row.addWidget(close)
        lay.addLayout(row)


class DiskCheck(QThread):
    """Schaetzt im Hintergrund den Platzbedarf (probt dafuer jede Datei)."""
    result = Signal(list)  # [diskcheck.Shortage]

    def __init__(self, ffmpeg: str, items, parent=None):
        super().__init__(parent)
        self.ffmpeg, self.items = ffmpeg, list(items)
        self._cancel = threading.Event()

    def stop(self):
        self._cancel.set()

    def run(self):
        try:
            res = diskcheck.check(self.ffmpeg, self.items, self._cancel.is_set)
        except Exception:
            res = []  # Pruefung ist nur ein Hinweis - nie das Starten blockieren
        self.result.emit(res)


class SettingsDialog(QDialog):
    """Einstellungen: Standardformat, Speicherort, Ueberwachte Ordner,
    Energie und Updates. Aenderungen gelten sofort."""

    def __init__(self, main: "MainWindow"):
        super().__init__(main)
        self.main = main
        self.setObjectName("settings")
        self.setWindowTitle(tr("settings_title"))
        self.setModal(True)
        self.setMinimumWidth(540)
        # Inhalt scrollt, falls der Bildschirm kleiner ist als das Fenster
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("setBody")
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(22, 14, 22, 10)
        lay.setSpacing(8)
        st = settings()

        busy = main.busy()

        def heading(key: str, info: str | None = None):
            """Ueberschrift + ⓘ: die Erklaerung steht im Info-Fenster, nicht im Dialog."""
            row = QHBoxLayout()
            row.setSpacing(4)
            row.setContentsMargins(0, 8, 0, 0)
            lab = QLabel(tr(key))
            lab.setObjectName("setHead")
            row.addWidget(lab)
            if info:
                icon = InfoIcon()
                icon.set_text(info)
                row.addWidget(icon)
            row.addStretch()
            lay.addLayout(row)

        def note(text: str) -> QLabel:
            """Nur fuer kurze Statusmeldungen, die gerade relevant sind."""
            lab = QLabel(text)
            lab.setObjectName("aboutSmall")
            lab.setWordWrap(True)
            lay.addWidget(lab)
            return lab

        # ---- Standardformat
        heading("set_codec", tr("set_codec_hint"))
        self.codec = QComboBox()
        for key, name in CODEC_NAMES.items():
            self.codec.addItem(tr("codec_h264") if key == "h264" else name, key)
        self.codec.setCurrentIndex(max(0, self.codec.findData(main.codec())))
        self.codec.currentIndexChanged.connect(
            lambda i: settings().setValue("codec", self.codec.itemData(i)))
        lay.addWidget(self.codec)

        # ---- Proxy-Groesse
        heading("set_scale", tr("set_scale_hint"))
        self.scale = QComboBox()
        for d in core.SCALES:
            self.scale.addItem(tr(f"set_scale_{d}"), d)
        self.scale.setCurrentIndex(max(0, self.scale.findData(scale_setting())))
        self.scale.currentIndexChanged.connect(self._scale_changed)
        self.scale.setEnabled(not busy)
        lay.addWidget(self.scale)

        # ---- Speicherort
        heading("set_dest", tr("set_dest_info"))
        self.r_beside = QRadioButton(tr("set_dest_beside"))
        self.r_central = QRadioButton(tr("set_dest_central"))
        grp = QButtonGroup(self)
        grp.addButton(self.r_beside)
        grp.addButton(self.r_central)
        lay.addWidget(self.r_beside)
        drow = QHBoxLayout()
        self.root_edit = QLineEdit(str(st.value("out_root", "") or ""))
        self.root_edit.setReadOnly(True)
        self.b_root = QPushButton(tr("set_browse"))
        self.b_root.clicked.connect(self._pick_root)
        drow.addWidget(self.r_central)
        drow.addWidget(self.root_edit, 1)
        drow.addWidget(self.b_root)
        lay.addLayout(drow)
        central = output_root() is not None
        (self.r_central if central else self.r_beside).setChecked(True)
        self.r_central.toggled.connect(self._dest_changed)
        for w in (self.r_beside, self.r_central, self.b_root):
            w.setEnabled(not busy)
        if busy:  # Groesse und Speicherort sind waehrend des Renderns gesperrt
            note(tr("set_dest_locked"))
        self._sync_dest()

        # ---- Ueberwachte Ordner
        heading("set_watch", tr("watch_tip"))
        self.watch_on = QCheckBox(tr("set_watch_on"))
        self.watch_on.setChecked(setting_bool("watch_on", False))
        self.watch_on.toggled.connect(self._watch_toggled)
        lay.addWidget(self.watch_on)
        wrow = QHBoxLayout()
        self.watch_list = QListWidget()
        self.watch_list.setObjectName("watchList")
        self.watch_list.setFixedHeight(64)
        self.watch_list.addItems(watch_dirs())
        wrow.addWidget(self.watch_list, 1)
        wbtns = QVBoxLayout()
        wbtns.setSpacing(6)
        b_add = QPushButton(tr("set_add"))
        b_add.clicked.connect(self._add_watch)
        b_rem = QPushButton(tr("set_remove"))
        b_rem.clicked.connect(self._remove_watch)
        wbtns.addWidget(b_add)
        wbtns.addWidget(b_rem)
        wbtns.addStretch()
        wrow.addLayout(wbtns)
        lay.addLayout(wrow)

        # ---- Energie
        heading("set_power", tr("set_power_info"))
        arow = QHBoxLayout()
        self.awake = QCheckBox(tr("set_awake"))
        self.awake.setChecked(setting_bool("keep_awake", True))
        self.awake.toggled.connect(self._awake_toggled)
        arow.addWidget(self.awake)
        arow.addSpacing(24)
        arow.addWidget(QLabel(tr("set_after")))
        self.after = QComboBox()
        for key in ("none", "sleep", "shutdown"):
            self.after.addItem(tr("after_" + key), key)
        self.after.setCurrentIndex(max(0, self.after.findData(main.after_action)))
        self.after.currentIndexChanged.connect(self._after_changed)
        arow.addWidget(self.after)
        arow.addStretch()
        lay.addLayout(arow)
        self._sync_after()

        # ---- Updates
        heading("set_updates", tr("set_update_info"))
        urow = QHBoxLayout()
        self.auto = QCheckBox(tr("set_update_auto"))
        self.auto.setChecked(updates_enabled())
        self.auto.toggled.connect(lambda on: set_setting_bool("check_updates", on))
        urow.addWidget(self.auto)
        urow.addSpacing(24)
        self.check_btn = QPushButton(tr("update_now"))
        self.check_btn.clicked.connect(self._check_now)
        self.update_state = QLabel("")
        self.update_state.setObjectName("aboutSmall")
        urow.addWidget(self.check_btn)
        urow.addWidget(self.update_state, 1)
        lay.addLayout(urow)
        self._checker = None

        # Schliessen-Knopf bleibt unten sichtbar, auch wenn der Inhalt scrollt
        row = QHBoxLayout()
        row.setContentsMargins(22, 8, 22, 14)
        row.addStretch()
        close = QPushButton(tr("about_close"))
        close.clicked.connect(self.accept)
        close.setDefault(True)
        row.addWidget(close)
        outer.addLayout(row)

        # hoechstens 90 % der Bildschirmhoehe
        screen = QGuiApplication.primaryScreen()
        want = body.sizeHint().height() + 60
        if screen:
            want = min(want, int(screen.availableGeometry().height() * 0.9))
        self.resize(max(self.minimumWidth(), body.sizeHint().width() + 20), want)

    # ---- Proxy-Groesse
    def _scale_changed(self, i: int):
        settings().setValue("scale", int(self.scale.itemData(i)))
        self.main.apply_scale()

    # ---- Speicherort
    def _sync_dest(self):
        central = self.r_central.isChecked()
        self.root_edit.setEnabled(central)
        self.b_root.setEnabled(central and not self.main.busy())

    def _pick_root(self) -> bool:
        d = QFileDialog.getExistingDirectory(self, tr("set_dest_central"),
                                             self.root_edit.text())
        if not d:
            return False
        d = str(Path(d))  # Windows: E:\Proxies statt E:/Proxies
        self.root_edit.setText(d)
        settings().setValue("out_root", d)
        self.main.apply_output()
        return True

    def _dest_changed(self, central: bool):
        if central and not self.root_edit.text() and not self._pick_root():
            self.r_beside.setChecked(True)  # kein Ordner gewaehlt -> zurueck
            return
        settings().setValue("out_mode", "central" if central else "beside")
        self._sync_dest()
        self.main.apply_output()

    # ---- Ueberwachte Ordner
    def _dirs(self) -> list[str]:
        return [self.watch_list.item(i).text() for i in range(self.watch_list.count())]

    def _add_watch(self):
        d = QFileDialog.getExistingDirectory(self, tr("set_watch"))
        d = str(Path(d)) if d else ""
        if d and d not in self._dirs():
            self.watch_list.addItem(d)
            set_watch_dirs(self._dirs())
            self.main.apply_watch()

    def _remove_watch(self):
        for it in self.watch_list.selectedItems():
            self.watch_list.takeItem(self.watch_list.row(it))
        set_watch_dirs(self._dirs())
        self.main.apply_watch()

    def _watch_toggled(self, on: bool):
        set_setting_bool("watch_on", on)
        self.main.apply_watch()
        self._sync_after()

    # ---- Energie
    def _awake_toggled(self, on: bool):
        set_setting_bool("keep_awake", on)
        self.main.apply_keep_awake()

    def _after_changed(self, i: int):
        self.main.after_action = self.after.itemData(i)

    def _sync_after(self):
        watching = self.main.watching()
        if watching:
            self.after.setCurrentIndex(0)
        self.after.setEnabled(not watching)

    # ---- Updates
    def _check_now(self):
        self.check_btn.setEnabled(False)
        self.update_state.setText(tr("update_checking"))
        self._checker = updater.UpdateChecker(APP_VERSION, self)
        self._checker.result.connect(self._checked)
        self._checker.start()

    def _checked(self, ok: bool, newer: bool, tag: str, url: str):
        self.check_btn.setEnabled(True)
        if not ok:
            self.update_state.setText(tr("update_failed"))
        elif newer:
            self.update_state.setText("")
            ask_update(self, tag, url)
        else:
            self.update_state.setText(tr("update_current"))

    def done(self, r):
        if self._checker and self._checker.isRunning():
            self._checker.wait(8000)  # Thread nicht mitten im Request zerstoeren
        super().done(r)


def system_language() -> str:
    """Anzeigesprache des Betriebssystems (nicht das Regionsformat)."""
    langs = QLocale.system().uiLanguages() or [QLocale.system().name()]
    return "de" if langs[0].lower().startswith("de") else "en"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(720, 540)
        self.ffmpeg = core.find_ffmpeg()
        self.redline_path: str | None = None
        self.worker: Worker | None = None
        self.keep_awake = power.KeepAwake()
        self.after_action = "none"  # nur fuer diese Sitzung: none/sleep/shutdown
        self.watcher: watch.FolderWatcher | None = None
        self._disk: DiskCheck | None = None
        self._checking = False      # Speicherplatz wird gerade geprueft
        self._redo: set[str] = set()  # Quelle aenderte sich waehrend des Renderns
        self.rows: dict[str, tuple[QListWidgetItem, QueueRow]] = {}
        self._current: str | None = None
        self._fracs: dict[str, float] = {}  # laufende Dateien -> Fortschritt
        self._had_error = False
        self._cancelled = False
        self.taskbar = taskbar.TaskbarProgress(
            self, QIcon(str(asset("icon.png"))) if asset("icon.png").exists() else QIcon())
        self._done = self._total = 0
        self._frac = 0.0
        self._status = ("–", "–", "–")
        self.theme_key = "rainbow"

        root = RainbowBackground()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(20, 16, 20, 14)
        lay.setSpacing(10)

        # ---- Kopf: Logo, Titel | Theme, Sprache, Hilfe
        head = QHBoxLayout()
        head.setSpacing(8)
        if asset("logo.png").exists():
            logo = QLabel()
            logo.setPixmap(QPixmap(str(asset("logo.png"))).scaledToHeight(
                34, Qt.SmoothTransformation))
            head.addWidget(logo)
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch()
        self.b_theme = QPushButton()
        self.b_theme.setObjectName("themeBtn")
        self.b_theme.setIconSize(QSize(30, 16))
        self.b_theme.setFixedSize(42, 28)
        self.b_theme.setCursor(Qt.PointingHandCursor)
        self.b_theme.clicked.connect(self.cycle_theme)
        head.addWidget(self.b_theme)
        self.b_lang = QPushButton()
        self.b_lang.setObjectName("flag")
        self.b_lang.setIconSize(QSize(26, 17))
        self.b_lang.setCursor(Qt.PointingHandCursor)
        self.b_lang.clicked.connect(self.toggle_language)
        head.addWidget(self.b_lang)
        self.b_settings = QPushButton("⚙")
        self.b_settings.setObjectName("icon")
        self.b_settings.setFixedSize(28, 28)
        self.b_settings.setCursor(Qt.PointingHandCursor)
        self.b_settings.clicked.connect(lambda: SettingsDialog(self).exec())
        head.addWidget(self.b_settings)
        self.b_help = QPushButton("?")
        self.b_help.setObjectName("icon")
        self.b_help.setFixedSize(28, 28)
        self.b_help.setCursor(Qt.PointingHandCursor)
        self.b_help.clicked.connect(lambda: AboutDialog(self).exec())
        head.addWidget(self.b_help)
        lay.addLayout(head)
        # Schlagschatten fuer die Kopf-Icons (Deckkraft je Theme, siehe apply_theme)
        self._icon_shadows = []
        for b in (self.b_theme, self.b_lang, self.b_settings, self.b_help):
            fx = QGraphicsDropShadowEffect(b)
            fx.setBlurRadius(12)
            fx.setOffset(0, 1.5)
            fx.setColor(QColor(0, 0, 0, 190))
            b.setGraphicsEffect(fx)
            self._icon_shadows.append(fx)

        # ---- eine schlanke Optionszeile
        row = QHBoxLayout()
        row.setSpacing(8)
        self.min_combo = QComboBox()
        for w, h in MIN_PRESETS:
            self.min_combo.addItem(f"min {w} × {h}", (w, h))
        self.min_combo.addItem("", None)
        row.addWidget(self.min_combo)
        self.custom_w = QSpinBox()
        self.custom_h = QSpinBox()
        for sb, val in ((self.custom_w, 960), (self.custom_h, 540)):
            sb.setRange(16, 8192)
            sb.setSingleStep(2)
            sb.setValue(val)
            sb.setSuffix(" px")
        row.addWidget(self.custom_w)
        row.addWidget(self.custom_h)
        self.info = InfoIcon()
        row.addWidget(self.info)
        row.addStretch()
        self.b_perf = QPushButton()
        self.b_perf.setObjectName("perf")
        self.b_perf.setCheckable(True)
        self.b_perf.setCursor(Qt.PointingHandCursor)
        self.b_perf.toggled.connect(self._perf_changed)
        row.addWidget(self.b_perf)
        lay.addLayout(row)

        # ---- Warteschlange = Ablageflaeche
        self.area = QueueArea()
        self.area.dropped.connect(self.add_paths)
        self.queue = self.area.list
        add_menu = QMenu(self)
        self.act_files = add_menu.addAction("", self.pick_files)
        self.act_dir = add_menu.addAction("", self.pick_dir)
        self.area.b_add.setMenu(add_menu)
        self.area.link_files.clicked.connect(self.pick_files)
        self.area.link_dir.clicked.connect(self.pick_dir)
        lay.addWidget(self.area, 1)

        # ---- Start/Abbrechen | Graphen (nur waehrend des Renderns)
        ctl = QHBoxLayout()
        ctl.setSpacing(14)
        self.b_go = QPushButton()
        self.b_go.setObjectName("start")
        self.b_go.setCursor(Qt.PointingHandCursor)
        self.b_go.clicked.connect(self.start_or_stop)
        ctl.addWidget(self.b_go)
        self.b_clear = QPushButton()
        self.b_clear.setObjectName("link")
        self.b_clear.setCursor(Qt.PointingHandCursor)
        self.b_clear.clicked.connect(self.clear_queue)
        ctl.addWidget(self.b_clear)
        ctl.addStretch()
        self.cpu_graph = UsageGraph("CPU", 0)
        self.gpu_graph = UsageGraph("GPU", 1)
        self.net_graph = UsageGraph("Net", 2, "MB/s", dual=True)
        self.disk_graph = UsageGraph("Disk", 3, "MB/s")
        self.graphs = (self.cpu_graph, self.gpu_graph, self.net_graph, self.disk_graph)
        for g in self.graphs:
            ctl.addWidget(g)
            g.hide()
        lay.addLayout(ctl)

        # ---- Statuszeile mit Spinner + einklappbares Log
        st_row = QHBoxLayout()
        st_row.setContentsMargins(12, 6, 8, 6)
        st_row.setSpacing(8)
        self.footer = QLabel()
        self.footer.setObjectName("footer")
        self.footer.setTextFormat(Qt.PlainText)
        self.footer.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        st_row.addWidget(self.footer, 1)
        self.watch_dot = PulseDot()
        self.watch_dot.hide()
        st_row.addWidget(self.watch_dot)
        self.watch_label = QLabel()
        self.watch_label.setObjectName("footer")
        self.watch_label.hide()
        st_row.addWidget(self.watch_label)
        self._watch_missing: list[str] = []  # ueberwachte Ordner, die fehlen
        self.total_label = QLabel()
        self.total_label.setObjectName("footer")
        st_row.addWidget(self.total_label)
        self.spinner = QLabel(" ")
        self.spinner.setObjectName("spinner")
        self.spinner.setFixedWidth(14)
        self.spinner.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        st_row.addWidget(self.spinner)
        self.b_log = QPushButton()
        self.b_log.setObjectName("link")
        self.b_log.setCheckable(True)
        self.b_log.setCursor(Qt.PointingHandCursor)
        self.b_log.toggled.connect(self.show_log)
        st_row.addWidget(self.b_log)
        self.status_bar = StatusBar()
        self.status_bar.setLayout(st_row)
        lay.addWidget(self.status_bar)

        self.term = LogFrame()
        tl = QVBoxLayout(self.term)
        tl.setContentsMargins(12, 8, 12, 8)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setMaximumBlockCount(2000)
        self.logbox.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.logbox.setMinimumHeight(160)
        tl.addWidget(self.logbox)
        self.term.hide()
        lay.addWidget(self.term)

        self._spin_i = 0
        self.spin_timer = QTimer(self)
        self.spin_timer.timeout.connect(self._spin)
        self.sampler = monitor.UsageSampler(1.0)
        self.sampler.sample.connect(self._usage)
        self.sampler.start()

        # ---- Einstellungen
        global LANG
        st = settings()
        LANG = system_language()  # Start in Systemsprache, Flagge nur pro Sitzung
        self.custom_w.setValue(int(st.value("custom_w", 960)))
        self.custom_h.setValue(int(st.value("custom_h", 540)))
        idx = int(st.value("min_index", 1))  # Standard: 960 x 540
        if 0 <= idx < self.min_combo.count():
            self.min_combo.setCurrentIndex(idx)
        self.min_combo.currentIndexChanged.connect(self._min_changed)
        self.custom_w.valueChanged.connect(self._save_min_setting)
        self.custom_h.valueChanged.connect(self._save_min_setting)
        self._min_changed()
        self.b_perf.setChecked(str(st.value("perf", "low")) == "normal")
        accel.set_mode("normal" if self.b_perf.isChecked() else "low")
        # Start immer passend zum Hell/Dunkel-Modus des Betriebssystems
        self.apply_theme(system_theme(), save=False)
        self.retranslate()
        self._refresh_area()

        # Update-Pruefung im Hintergrund (abschaltbar in den Einstellungen)
        self._update_checker = None
        if updates_enabled():
            QTimer.singleShot(1500, self._start_update_check)

        if not self.ffmpeg:
            self.log(tr("ffmpeg_missing"))
            self.area.setEnabled(False)
        else:
            core.APP_INFO.update(name=APP_NAME, version=APP_VERSION,
                                 ffmpeg=core.ffmpeg_version(self.ffmpeg))
            self.log(tr("ffmpeg_info", ver=core.APP_INFO["ffmpeg"], path=self.ffmpeg))
            self.log(tr("braw_found") if braw.find() else tr("braw_missing"))

        # Speicherort, Proxy-Groesse, Ueberwachte Ordner, Energie
        self.apply_output()
        self.apply_scale()
        self.apply_watch()

    # ---------------------------------------------------- Sprache / Theme
    def set_language(self, code: str):
        global LANG
        LANG = code
        self.retranslate()

    def toggle_language(self):
        self.set_language("en" if LANG == "de" else "de")

    def cycle_theme(self):
        keys = list(THEMES)
        self.apply_theme(keys[(keys.index(self.theme_key) + 1) % len(keys)], save=False)
        self.retranslate()

    def apply_theme(self, key: str, save: bool = True):
        global T
        self.theme_key = key if key in THEMES else "rainbow"
        T = THEMES[self.theme_key]
        QApplication.instance().setStyleSheet(make_style())
        alpha, blur = T["icon_shadow"]
        for fx in self._icon_shadows:
            fx.setColor(QColor(0, 0, 0, alpha))
            fx.setBlurRadius(blur)
        if save:
            settings().setValue("theme", self.theme_key)
        self.centralWidget().update()
        for g in self.graphs:
            g.update()
        self.term.set_enabled_anim(T["rainbow"])

    def retranslate(self):
        other = "en" if LANG == "de" else "de"
        self.b_lang.setIcon(flag_icon(other, 26, 17))
        self.b_lang.setToolTip("English" if other == "en" else "Deutsch")
        keys = list(THEMES)
        nxt = keys[(keys.index(self.theme_key) + 1) % len(keys)]
        self.b_theme.setIcon(theme_preview_icon(nxt))
        self.b_theme.setToolTip(f"{tr('theme_tip')} → {tr('theme_' + nxt)}")
        self.b_help.setToolTip(tr("about_tip"))
        self.b_settings.setToolTip(tr("settings_tip"))
        self.min_combo.setItemText(self.min_combo.count() - 1, tr("custom_item"))
        self._update_watch_label()
        self.custom_w.setPrefix(tr("width"))
        self.custom_h.setPrefix(tr("height"))
        self.info.set_text(tr("info_tip", scale=tr(f"scale_{scale_setting()}")))
        self.area.empty_label.setText(tr("empty_hint"))
        self.area.link_files.setText(tr("add_files"))
        self.area.link_dir.setText(tr("add_dir"))
        self.area.link_or.setText(tr("or"))
        self.area.b_add.setText(tr("btn_add"))
        self.area.b_add.setToolTip(tr("add_tip"))
        self.act_files.setText(tr("add_files"))
        self.act_dir.setText(tr("add_dir"))
        self.b_clear.setText(tr("btn_clear"))
        self.b_perf.setText(("⚡ " + tr("perf_high")) if self.b_perf.isChecked()
                            else ("🌿 " + tr("perf_low")))
        self.b_perf.setToolTip(wrap_tip(tr("perf_tip")))
        self.b_log.setText(("▾ " if self.b_log.isChecked() else "▸ ") + tr("log_toggle"))
        self.net_graph.set_title(tr("g_net"))
        for p, (_item, row) in self.rows.items():
            row.set_state(row.state, self._fracs.get(p, 0.0) if row.state == "run" else 0.0)
            row.x.setToolTip(tr("remove_tip"))
        self._update_buttons()
        self._update_footer()

    # ------------------------------------------------------ Mindestaufloesung
    def min_size(self) -> tuple[int, int]:
        data = self.min_combo.currentData()
        if data:
            return tuple(data)
        # gerade Werte, weil die Codecs gerade Pixelmasse brauchen
        return (self.custom_w.value() // 2 * 2, self.custom_h.value() // 2 * 2)

    def codec(self) -> str:
        c = str(settings().value("codec", core.DEFAULT_CODEC))
        return c if c in CODEC_NAMES else core.DEFAULT_CODEC

    # ------------------------------------------- Speicherort / Ordner / Energie
    def busy(self) -> bool:
        return self.running() or self._checking

    def apply_output(self):
        if not self.busy():  # Ziel bleibt waehrend des Renderns fest
            core.set_output_root(output_root())

    def apply_scale(self):
        if not self.busy():  # Groesse bleibt waehrend des Renderns fest
            core.set_scale(scale_setting())
        self.info.set_text(tr("info_tip", scale=tr(f"scale_{scale_setting()}")))

    def watching(self) -> bool:
        return setting_bool("watch_on", False) and bool(watch_dirs())

    def apply_watch(self):
        if not self.ffmpeg:
            return
        if self.watching():
            if self.watcher is None:
                self.watcher = watch.FolderWatcher(watch_dirs(), self)
                self.watcher.found.connect(self._watch_found)
                self.watcher.status.connect(self._watch_status)
                self.watcher.start()
            else:
                self.watcher.set_folders(watch_dirs())
            self.after_action = "none"  # wartet ja immer auf weitere Dateien
        elif self.watcher is not None:
            self.watcher.stop()
            self.watcher.wait(3000)
            self.watcher = None
            self._watch_missing = []
        self._update_watch_label()

    def _update_watch_label(self):
        on = self.watching()
        self.watch_label.setVisible(on)
        self.watch_dot.setVisible(on)
        if not on:
            return
        dirs = watch_dirs()
        missing = [d for d in self._watch_missing if d in dirs]
        self.watch_dot.set_warn(bool(missing))
        if missing:
            self.watch_label.setText(tr("watching_missing", n=len(dirs), m=len(missing)))
            head = tr("watch_unreachable") + "\n" + "\n".join(missing)
            ok = [d for d in dirs if d not in missing]
            if ok:
                head += "\n\n" + tr("watch_reachable") + "\n" + "\n".join(ok)
        else:
            self.watch_label.setText(tr("watching", n=len(dirs)))
            head = "\n".join(dirs)
        tip = wrap_tip(head + "\n\n" + tr("watch_tip"))
        self.watch_label.setToolTip(tip)
        self.watch_dot.setToolTip(tip)

    def _watch_status(self, missing: list):
        if missing != self._watch_missing:
            for d in missing:
                if d not in self._watch_missing:
                    self.log(tr("watch_lost", path=d))
            for d in self._watch_missing:
                if d not in missing:
                    self.log(tr("watch_back", path=d))
        self._watch_missing = list(missing)
        self._update_watch_label()

    def _watch_found(self, items: list):
        fresh = []
        for f, b, rerender in items:
            src = Path(f)
            if rerender:
                # Quelle hat sich nach dem Einreihen geaendert (z.B. Kopie hatte
                # nur pausiert): unseren Proxy verwerfen und neu rendern
                self.log(f"{'':15}{src.name} – {tr('watch_redo')}")
                state = self.rows[f][1].state if f in self.rows else None
                if state == "wait":
                    continue  # hat noch nicht angefangen - rendert ohnehin den neuen Stand
                if state == "run":
                    self._redo.add(f)  # nach dem Ende verwerfen und neu einreihen
                    continue
                self._discard_proxy(src)
            fresh.append((src, Path(b)))
        new = self._enqueue(fresh, quiet=True) if fresh else 0
        if new:
            self.log(tr("watch_added", n=new))
            if not self.busy():
                self.begin(auto=True)

    def _discard_proxy(self, src: Path):
        try:
            core.proxy_path(src).unlink(missing_ok=True)
        except OSError as exc:
            self.log(logline("tag_err", src.name, str(exc)))

    def apply_keep_awake(self):
        if self.running() and setting_bool("keep_awake", True):
            self.keep_awake.start()
        else:
            self.keep_awake.stop()

    def _perf_changed(self, on: bool):
        accel.set_mode("normal" if on else "low")
        settings().setValue("perf", "normal" if on else "low")
        self.retranslate()

    def _min_changed(self, *_):
        custom = self.min_combo.currentData() is None
        self.custom_w.setVisible(custom)
        self.custom_h.setVisible(custom)
        self._save_min_setting()

    def _save_min_setting(self, *_):
        st = settings()
        st.setValue("min_index", self.min_combo.currentIndex())
        st.setValue("custom_w", self.custom_w.value())
        st.setValue("custom_h", self.custom_h.value())

    # -------------------------------------------------------------- REDline
    def ensure_redline(self) -> str | None:
        if self.redline_path:
            return self.redline_path
        st = settings()
        path = redline.find_redline(str(st.value("redline_path", "")) or None)
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, tr("rl_locate"))
            if path and Path(path).suffix.lower() == ".app":
                path = str(Path(path) / "Contents" / "MacOS" / "REDline")
            path = path if path and Path(path).is_file() else None
        if path:
            st.setValue("redline_path", path)
            self.log(tr("rl_found", path=path))
        else:
            self.log(tr("rl_missing"))
        self.redline_path = path
        return path

    # ------------------------------------------------------- Warteschlange
    def running(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, tr("pick_files"))
        if files:
            self.add_paths(files)

    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, tr("pick_dir"))
        if d:
            self.add_paths([d])

    def queued_paths(self) -> list[str]:
        """Dateien, die noch warten oder gerade laufen."""
        return [p for p, (_i, r) in self.rows.items() if r.state in ("wait", "run")]

    def add_paths(self, paths: list[str]):
        if not self.ffmpeg:
            return
        found = core.collect_with_base(paths)
        if not found:
            self.log(tr("no_files"))
            return
        self._enqueue(found)

    def _enqueue(self, found: list[tuple[Path, Path]], quiet: bool = False) -> int:
        """Dateien (mit Basisordner) einreihen. Rueckgabe: Anzahl neuer Dateien."""
        files = [f for f, _b in found]
        if any(core.is_r3d(f) for f in files):
            self.ensure_redline()
        ms, codec = self.min_size(), self.codec()
        active = set(self.queued_paths())
        new = [f for f in files if str(f) not in active]
        if not new:
            if not quiet:
                self.log(tr("already_queued"))
            return 0
        new_set = set(new)
        for f, base in found:
            if f in new_set:  # laufende Dateien behalten ihr Ziel
                core.remember_base(f, base)
        for f in new:
            if str(f) in self.rows:  # alter fertiger/fehlerhafter Eintrag
                self._take_row(str(f))
            self._add_row(f, ms, codec)
        if self.running():
            self.worker.redline = self.redline_path
            self.worker.add([(f, ms, codec) for f in new])
            self.log(tr("added", n=len(new), w=ms[0], h=ms[1], codec=CODEC_SHORT[codec]))
        else:
            self.log(tr("queued", n=len(new), w=ms[0], h=ms[1], codec=CODEC_SHORT[codec]))
        self._refresh_area()
        return len(new)

    def _add_row(self, f: Path, ms: tuple[int, int], codec: str):
        it = QListWidgetItem()
        it.setData(Qt.UserRole, (str(f), ms, codec))
        row = QueueRow(f, ms, codec)
        row.set_state("wait")
        row.x.setToolTip(tr("remove_tip"))
        row.combo.currentIndexChanged.connect(
            lambda i, p=str(f), c=row.combo: self._row_codec_changed(p, c.itemData(i)))
        row.x.clicked.connect(lambda _=False, p=str(f): self._remove_paths([p]))
        self.queue.addItem(it)
        it.setSizeHint(row.sizeHint())
        self.queue.setItemWidget(it, row)
        self.rows[str(f)] = (it, row)

    def _take_row(self, path: str):
        it, _row = self.rows.pop(path)
        self.queue.takeItem(self.queue.row(it))

    def _row_codec_changed(self, path: str, codec: str):
        it, _row = self.rows[path]
        p, ms, _old = it.data(Qt.UserRole)
        it.setData(Qt.UserRole, (p, ms, codec))
        if self.running():  # Datei wartet noch -> laufendem Durchgang mitteilen
            self.worker.set_codec(Path(p), codec)

    def _remove_paths(self, paths: list[str]):
        paths = [p for p in paths if p in self.rows and self.rows[p][1].state != "run"]
        if not paths:
            return
        if self.running():
            self.worker.remove({Path(p) for p in paths})
        for p in paths:
            self._take_row(p)
        self._refresh_area()

    def clear_queue(self):
        self._remove_paths(list(self.rows))

    def start_or_stop(self):
        if self._checking:
            return
        if self.running():
            self.log(tr("cancel_req"))
            self._cancelled = True
            self.worker.stop()
            return
        self.begin(auto=False)

    def _start_items(self, auto: bool, mark: bool = False) -> list:
        """Startbare Eintraege. Automatisch (Ordnerueberwachung) nur wartende -
        fehlerhafte oder abgebrochene Dateien werden nicht endlos wiederholt."""
        states = ("wait",) if auto else ("wait", "error", "cancel")
        items = []
        for p, (it, row) in self.rows.items():
            if row.state in states:
                if mark:
                    row.set_state("wait")
                _p, ms, codec = it.data(Qt.UserRole)
                items.append((Path(p), tuple(ms), codec))
        return items

    def begin(self, auto: bool):
        """Erst Speicherplatz pruefen (im Hintergrund), dann rendern."""
        items = self._start_items(auto)
        if not items:
            return
        self.apply_output()
        self.apply_scale()
        self._checking = True
        self._update_buttons()
        self._update_footer()
        self._disk = DiskCheck(self.ffmpeg, items, self)
        self._disk.result.connect(lambda res, a=auto: self._disk_checked(res, a))
        self._disk.start()

    def _disk_checked(self, shortages: list, auto: bool):
        self._disk.wait(2000)
        self._disk = None
        self._checking = False
        self._update_buttons()
        self._update_footer()
        if shortages:
            lines = "\n".join(tr("disk_line", loc=s.location,
                                 need=diskcheck.human(s.need),
                                 free=diskcheck.human(s.free)) for s in shortages)
            if auto:  # niemand da, der gefragt werden koennte
                self.log(tr("disk_not_started", lines=lines.replace("\n", " · ")))
                return
            box = QMessageBox(QMessageBox.Warning, tr("disk_title"),
                              tr("disk_question", lines=lines), parent=self)
            go = box.addButton(tr("disk_start"), QMessageBox.AcceptRole)
            no = box.addButton(tr("disk_cancel"), QMessageBox.RejectRole)
            box.setDefaultButton(no)
            box.exec()
            if box.clickedButton() is not go:
                return
        items = self._start_items(auto, mark=True)  # Liste kann sich geaendert haben
        if items:
            self._start_worker(items)

    def _start_worker(self, items: list):
        self.worker = Worker(self.ffmpeg)
        self.worker.counts.connect(self.set_counts)
        self.worker.item_progress.connect(self._item_progress)
        self.worker.log.connect(self.log)
        self.worker.started_item.connect(self._item_started)
        self.worker.item_done.connect(self._item_done)
        self.worker.finished_all.connect(self.finished)
        self.worker.redline = self.redline_path
        self.worker.add(items)
        for g in self.graphs:
            g.reset()
            g.show()
        self.status_bar.set_progress(0)
        self._had_error = self._cancelled = False
        self.taskbar.set(0.0, "normal")
        self.worker.start()
        self.apply_keep_awake()
        self._spin_i = 0
        self.spin_timer.start(140)
        self._update_buttons()

    def _item_started(self, path: str):
        self.sampler.set_path(path)
        self._current = path
        self._fracs[path] = 0.0
        if path in self.rows:
            self.rows[path][1].set_state("run", 0.0)
            self.queue.scrollToItem(self.rows[path][0])

    def _item_done(self, path: str, result: str):
        if path in self._redo:  # Quelle hat sich waehrend des Renderns geaendert
            self._redo.discard(path)
            if result == "done":
                self._discard_proxy(Path(path))
            QTimer.singleShot(0, lambda p=path: self._requeue(p))
        self._fracs.pop(path, None)
        if self._fracs:
            self.sampler.set_path(next(reversed(self._fracs)))
        if path not in self.rows:
            return
        self.rows[path][1].set_state(result)
        if result in ("done", "skip"):  # kurz stehen lassen, dann ausblenden
            QTimer.singleShot(2500, lambda p=path: self._fade_out(p))
        if result == "error":
            self._had_error = True
        if result == "error" and not self.b_log.isChecked():
            self.b_log.setChecked(True)  # bei Fehlern das Log zeigen

    def _requeue(self, path: str):
        src = Path(path)
        base = core._BASES.get(path, src.parent.parent)
        if self._enqueue([(src, base)], quiet=True) and not self.busy():
            self.begin(auto=True)

    def _fade_out(self, path: str):
        if path in self.rows and self.rows[path][1].state in ("done", "skip"):
            self._take_row(path)
            self._refresh_area()

    def _refresh_area(self):
        self.area.show_list(bool(self.rows))
        self._update_buttons()

    def _update_buttons(self):
        run = self.running()
        startable = any(r.state in ("wait", "error", "cancel") for _i, r in self.rows.values())
        self.b_go.setText(f"■  {tr('btn_cancel')}" if run else tr("btn_start"))
        self.b_go.setProperty("stop", run)
        self.b_go.style().polish(self.b_go)
        self.b_go.setEnabled((run or startable) and not self._checking)
        self.b_clear.setVisible(bool(self.rows))

    # -------------------------------------------------------------- Anzeige
    def show_log(self, on: bool):
        self.term.setVisible(on)
        self.b_log.setText(("▾ " if on else "▸ ") + tr("log_toggle"))

    def set_status(self, last: str, cur: str, nxt: str):
        self._status = (last, cur, nxt)

    def set_counts(self, done: int, total: int, keep_frac: bool = False):
        self._done, self._total = done, total
        if not keep_frac:
            self._frac = 0.0
        self._update_bar()

    def _item_progress(self, path: str, frac: float):
        if path in self._fracs:
            self._fracs[path] = frac
        if path in self.rows and self.rows[path][1].state == "run":
            self.rows[path][1].set_state("run", frac)
        self._update_bar()

    def _update_bar(self):
        run = sum(self._fracs.values())
        pos = min(self._done + run, self._total) / self._total if self._total else 0
        self.status_bar.set_progress(pos)
        if self.running():
            self.taskbar.set(pos, "error" if self._had_error else "normal")
        self._update_footer()

    def finished(self, created: int, skipped: int, failed: int):
        self.spin_timer.stop()
        self.log(tr("finished", c=created, s=skipped, f=failed))
        QTimer.singleShot(0, self._after_finish)  # Thread ist dann sicher beendet

    def _after_finish(self):
        self.worker.wait(2000)
        # Taskleiste/Dock: gelb nach Abbruch, rot bei Fehlern, sonst ausblenden
        if self._cancelled:
            self.taskbar.set(self.status_bar.progress or 0.0, "paused")
        elif self._had_error:
            self.taskbar.set(1.0, "error")
        else:
            self.taskbar.clear()
        # Aufmerksamkeit: Dock-Symbol huepft (Mac) / Taskleiste blinkt (Windows)
        if not self.isActiveWindow():
            QApplication.alert(self, 0)
        self.sampler.set_path(None)
        self._current = None
        self._fracs.clear()
        self.status_bar.set_progress(0)
        for g in self.graphs:
            g.hide()
        self._update_buttons()
        self._update_footer()
        self.keep_awake.stop()
        if self.after_action != "none" and not self._cancelled and not self.watching():
            action, self.after_action = self.after_action, "none"  # nur einmal
            QTimer.singleShot(0, lambda a=action: self._after_countdown(a))

    AFTER_SECONDS = 60

    def _after_countdown(self, action: str):
        """Countdown mit Abbrechen-Knopf, dann Energiesparmodus/Herunterfahren."""
        key = "after_sleep_in" if action == "sleep" else "after_shutdown_in"
        left = [self.AFTER_SECONDS]
        fire = [False]
        box = QMessageBox(QMessageBox.Information, tr("after_title"),
                          tr(key, s=left[0]), parent=self)
        now = box.addButton(tr("after_now"), QMessageBox.AcceptRole)
        abort = box.addButton(tr("after_abort"), QMessageBox.RejectRole)
        box.setDefaultButton(abort)
        timer = QTimer(box)

        def tick():
            left[0] -= 1
            if left[0] <= 0:
                timer.stop()
                fire[0] = True
                box.done(0)
            else:
                box.setText(tr(key, s=left[0]))

        timer.timeout.connect(tick)
        timer.start(1000)
        box.exec()
        timer.stop()
        if not (fire[0] or box.clickedButton() is now):
            return
        try:
            (power.sleep_computer if action == "sleep" else power.shutdown_computer)()
        except Exception as exc:
            self.log(tr("after_failed", err=exc))

    SPIN ="-/|\\"  # waagerecht, diagonal, senkrecht, gespiegelt diagonal

    def _spin(self):
        self._spin_i = (self._spin_i + 1) % len(self.SPIN)
        self._update_footer()

    def _update_footer(self):
        if self.running():
            running = list(self._fracs.items())
            if not running:
                self.footer.setText("> …")
            elif len(running) == 1:
                p, f = running[0]
                self.footer.setText(f"> {Path(p).name}   {int(f * 100):>3} %")
            else:
                self.footer.setText(f"> {len(running)} {tr('active')} · " + " · ".join(
                    f"{Path(p).stem[:18]} {int(f * 100)}%" for p, f in running))
            if self._total:
                pos = min(self._done + sum(self._fracs.values()), self._total) / self._total
                self.total_label.setText(
                    f"{self._done}/{self._total} · {int(pos * 100)} %")
            self.spinner.setText(self.SPIN[self._spin_i])
        elif self._checking:
            self.footer.setText(f"> {tr('disk_checking')}")
            self.total_label.setText("")
            self.spinner.setText(" ")
        else:
            self.footer.setText(f"> {tr('idle')}")
            self.total_label.setText("")
            self.spinner.setText(" ")

    def _usage(self, d: dict):
        if not self.running():  # Graphen bewegen sich nur waehrend des Renderns
            return
        self.cpu_graph.push(d["cpu"])
        self.gpu_graph.push(d["gpu"])
        local = bool(self._fracs) and not d["disk_net"]
        self.net_graph.set_note(tr("local_file") if local else None)
        self.net_graph.push(d["rx"], d["tx"])
        label = d["disk_label"]
        self.disk_graph.set_title(f"Disk {label}" if label else "Disk")
        self.disk_graph.set_note(tr("net_drive") if d["disk_net"] else None)
        self.disk_graph.push(d["disk"])

    def log(self, text: str):
        self.logbox.appendPlainText(text)

    def changeEvent(self, e):
        super().changeEvent(e)
        if (e.type() == e.Type.ActivationChange and self.isActiveWindow()
                and not self.running() and (self._had_error or self._cancelled)):
            self.taskbar.clear()
            self._had_error = self._cancelled = False

    def _start_update_check(self):
        self._update_checker = updater.UpdateChecker(APP_VERSION, self)
        self._update_checker.result.connect(self._update_checked)
        self._update_checker.start()

    def _update_checked(self, ok: bool, newer: bool, tag: str, url: str):
        if not (ok and newer):
            return  # offline or up to date: stay silent
        st = settings()
        if str(st.value("update_dismissed", "")) == tag:
            return  # user already said "later" for this version
        if not ask_update(self, tag, url):
            st.setValue("update_dismissed", tag)

    def closeEvent(self, e):
        if self._update_checker and self._update_checker.isRunning():
            self._update_checker.wait(8000)
        if self.watcher is not None:
            self.watcher.stop()
            self.watcher.wait(5000)
        if self._disk is not None:
            self._disk.stop()
            self._disk.wait(5000)
        self.keep_awake.stop()
        self.sampler.stop()
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)
        self.sampler.wait(2000)
        e.accept()


def make_style() -> str:
    t = T
    mono = '"SF Mono", Menlo, Consolas, "Courier New", monospace'
    return f"""
QWidget {{ color: {t['text']}; font-size: 13px; }}
QMainWindow {{ background: {t['bg']}; }}
QLabel {{ background: transparent; }}
QToolTip {{ background: #1c1d21; color: #e8e8ea; border: 1px solid #4a4c55; padding: 6px;
    max-width: 360px; }}
#title {{ font-size: 19px; font-weight: 600; color: {t['text']}; }}

/* Kopf-Icons */
QPushButton#icon {{ background: transparent; color: {t['text']};
    border: none; border-radius: 14px; padding: 0;
    font-size: 17px; font-weight: 700; }}
QPushButton#icon:hover {{ background: {t['panel']}; }}
QPushButton#flag {{ background: transparent; border: none; padding: 2px; }}
QPushButton#flag:hover {{ background: {t['panel']}; border-radius: 4px; }}

/* Optionszeile */
QComboBox, QSpinBox {{ background: {t['ctrl']}; color: {t['text']}; border: none;
    border-radius: 6px; padding: 5px 10px; }}
QComboBox QAbstractItemView {{ background: {t['popup_bg']}; color: {t['text']};
    selection-background-color: {t['popup_sel']}; selection-color: {t['text']};
    border: none; outline: none; }}
#info {{ color: {t['hint']}; font-size: 16px; padding: 0 4px; }}
#infoPop {{ background: #1c1d21; color: #e8e8ea; border: 1px solid #4a4c55;
    border-radius: 6px; padding: 8px 10px; font-size: 12px; }}
QPushButton#perf {{ background: transparent; color: {t['hint']};
    border: 1.5px solid {t['help_border']}; border-radius: 7px; padding: 4px 12px; }}
QPushButton#perf:checked {{ background: {t['start']}; color: {t['start_text']};
    border-color: {t['start']}; font-weight: 600; }}
QPushButton#perf:hover {{ border-color: {t['text']}; }}
QPushButton#themeBtn {{ background: transparent; border: none;
    border-radius: 7px; padding: 0; }}
QPushButton#themeBtn:hover {{ background: {t['panel']}; }}

/* Warteschlange = Ablageflaeche */
#queueArea {{ background: {t['panel']}; border: 2px dashed {t['drop_border']};
    border-radius: 12px; }}
#queueArea[hover="true"] {{ border-color: {t['drop_hover']}; }}
#emptyPage {{ background: transparent; }}
#emptyHint {{ font-size: 16px; color: {t['text']}; }}
#emptyOr {{ color: {t['hint']}; }}
#queueList {{ background: transparent; border: none; padding: 6px 4px; }}
#queueList::item {{ background: transparent; border: none; padding: 0; }}
#queueRow, #queueName {{ background: transparent; }}
#queueName {{ font-family: {mono}; font-size: 12px; }}
#rowStatus {{ color: {t['hint']}; font-size: 12px; }}
#rowStatus[state="run"], #rowStatus[state="done"] {{ color: {t['term_accent']}; }}
#rowStatus[state="error"] {{ color: #ff6b6b; font-weight: 600; }}
QComboBox#queueCodec {{ padding: 1px 8px; font-size: 12px; min-width: 64px; }}
QPushButton#rowX {{ background: transparent; color: {t['hint']}; border: none;
    padding: 0; font-size: 15px; }}
QPushButton#rowX:hover {{ color: {t['text']}; }}
QPushButton#rowX:disabled {{ background: transparent; color: transparent; }}
#rowBar {{ background: {t['bar_bg']}; border: none; border-radius: 2px; }}
#rowBar::chunk {{ background: {t['chunk']}; border-radius: 2px; }}
#totalBar {{ background: transparent; border: none; border-radius: 0; }}
#totalBar::chunk {{ background: {t['chunk']}; }}
QPushButton#add {{ background: {t['start']}; color: {t['start_text']}; border: none;
    border-radius: 8px; padding: 6px 16px; font-weight: 600; }}
QPushButton#add::menu-indicator {{ image: none; width: 0; }}
QPushButton#add:hover {{ background: {t['start_hover']}; }}

/* Buttons */
QPushButton {{ background: {t['btn']}; color: {t['btn_text']}; border: none;
    border-radius: 6px; padding: 7px 14px; }}
QPushButton:hover {{ background: {t['btn_hover']}; }}
QPushButton:disabled {{ background: {t['btn_dis']}; color: {t['btn_dis_text']}; }}
QPushButton#start {{ background: {t['start']}; color: {t['start_text']};
    font-weight: 700; padding: 8px 22px; border-radius: 8px; }}
QPushButton#start:hover {{ background: {t['start_hover']}; }}
QPushButton#start:disabled {{ background: {t['start_dis']}; color: {t['btn_dis_text']}; }}
QPushButton#link {{ background: transparent; color: {t['hint']}; border: none;
    padding: 2px 4px; text-decoration: underline; }}
QPushButton#link:hover {{ color: {t['text']}; }}
QPushButton#link:checked {{ color: {t['text']}; }}
QMenu {{ background: {t['popup_bg']}; color: {t['text']}; border: none; padding: 4px; }}
QMenu::item {{ padding: 5px 18px; }}
QMenu::item:selected {{ background: {t['popup_sel']}; }}

/* Statuszeile + Log */
#statusBar {{ background: transparent; }}
#footer, #spinner {{ color: {t['term_accent']}; font-family: {mono}; font-size: 12px; }}
#spinner {{ font-weight: 700; }}
#statusBar QPushButton#link {{ color: {t['term_text']}; }}
#term {{ background: {t['term_bg']}; border-radius: 8px; }}
#term QPlainTextEdit {{ background: {t['term_bg']}; color: {t['term_text']}; border: none;
    font-family: {mono}; font-size: 12px; }}
#term QScrollBar {{ background: {t['term_bg']}; border: none; }}
#term QScrollBar:vertical {{ width: 10px; }}
#term QScrollBar:horizontal {{ height: 10px; }}
#term QScrollBar::handle {{ background: {t['term_handle']}; border-radius: 4px;
    min-height: 24px; min-width: 24px; }}
#term QScrollBar::add-line, #term QScrollBar::sub-line {{ width: 0; height: 0; }}
#term QScrollBar::add-page, #term QScrollBar::sub-page {{ background: {t['term_bg']}; }}

/* About bleibt dunkel */
QDialog#about {{ background: {PANEL}; }}
QDialog#about QLabel {{ color: {TEXT}; }}
#aboutName {{ font-size: 20px; font-weight: 600; color: white; }}
#aboutVersion {{ color: {ACCENT}; font-family: {mono}; }}
#aboutText {{ font-size: 13px; }}
#aboutSmall {{ color: #8b8d94; font-size: 11px; }}
QDialog#about QPushButton {{ background: #2c2e35; color: white; }}
QDialog#about QPushButton:hover {{ background: #383a43; }}

/* Einstellungen: ebenfalls immer dunkel */
QDialog#settings, QDialog#settings #setBody {{ background: {PANEL}; }}
QDialog#settings QScrollArea {{ background: {PANEL}; border: none; }}
QDialog#settings QScrollBar:vertical {{ background: {PANEL}; width: 10px; border: none; }}
QDialog#settings QScrollBar::handle:vertical {{ background: #3a3d46; border-radius: 4px;
    min-height: 24px; }}
QDialog#settings QScrollBar::add-line, QDialog#settings QScrollBar::sub-line {{
    width: 0; height: 0; }}
QDialog#settings QLabel, QDialog#settings QCheckBox,
QDialog#settings QRadioButton {{ color: {TEXT}; }}
QDialog#settings #setHead {{ color: white; font-weight: 600; }}
QDialog#settings #info {{ color: #8b8d94; font-size: 14px; padding: 0 2px; }}
QDialog#settings QComboBox, QDialog#settings QLineEdit {{ background: #2c2e35;
    color: {TEXT}; border: none; border-radius: 6px; padding: 5px 10px; }}
QDialog#settings QLineEdit:disabled {{ color: #6b6d74; }}
QDialog#settings QComboBox QAbstractItemView {{ background: #2c2e35; color: {TEXT};
    selection-background-color: #3a3d46; border: none; outline: none; }}
QDialog#settings QListWidget {{ background: #1c1d21; color: {TEXT}; border: none;
    border-radius: 6px; font-family: {mono}; font-size: 12px; }}
QDialog#settings QListWidget::item:selected {{ background: #3a3d46; color: white; }}
QDialog#settings QPushButton {{ background: #2c2e35; color: white; }}
QDialog#settings QPushButton:hover {{ background: #383a43; }}
QDialog#settings QPushButton:disabled {{ color: #6b6d74; }}
QDialog#settings QComboBox:disabled, QDialog#settings QCheckBox:disabled,
QDialog#settings QRadioButton:disabled {{ color: #6b6d74; }}
"""


def main():
    if "--selftest" in sys.argv:  # Build pruefen, ohne Fenster zu zeigen
        from . import selftest
        i = sys.argv.index("--selftest")
        sys.exit(selftest.run(sys.argv[i + 1] if len(sys.argv) > i + 1 else None))
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    if asset("icon.png").exists():
        app.setWindowIcon(QIcon(str(asset("icon.png"))))
    app.setStyleSheet(make_style())
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
