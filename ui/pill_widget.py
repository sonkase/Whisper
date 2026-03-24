import ctypes
import ctypes.wintypes
import os
import time
from utils.sound import play_ding, play_error

import pyperclip
import pyautogui
from PyQt6.QtCore import Qt, QRectF, QPoint, QTimer
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QIcon, QAction,
)
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QApplication,
    QSystemTrayIcon, QMenu,
)

from core.recorder import AudioRecorder
from core.transcriber import TranscriberWorker
from core.post_processor import PostProcessorWorker
from ui.settings_panel import SettingsPanel
from ui.compact_pill import CompactPill
from ui.toast_widget import ToastWidget
from ui.update_window import UpdateWindow
from utils.config import (
    load_theme, save_theme, save_transcription, load_shortcuts,
    load_post_processing, load_paste_sound, load_start_minimized,
    load_auto_update,
)
from utils.hotkeys import HotkeyManager
from core.updater import (UpdateChecker, UpdateDownloader,
                          apply_update_and_restart, APP_VERSION, GITHUB_REPO)

THEME_COLORS = {
    "Midnight":  QColor(20, 20, 30),
    "Viola":     QColor(26, 16, 36),
    "Bordeaux":  QColor(34, 16, 22),
    "Ambra":     QColor(28, 22, 14),
    "Ardesia":   QColor(24, 24, 24),
    "Foresta":   QColor(16, 28, 20),
    "Oceano":    QColor(16, 24, 32),
}


class PillWidget(QWidget):
    """Main controller — settings window + hotkey-driven recording via compact pill."""

    SHADOW = 16
    TITLE_H = 36
    PANEL_W = 440

    def __init__(self, api_key: str = ""):
        super().__init__()
        self._api_key = api_key
        self._state = "idle"
        self._theme_name = load_theme()
        self._bg_color = THEME_COLORS.get(self._theme_name, THEME_COLORS["Midnight"])

        self._press_pos = None
        self._is_dragging = False
        self._drag_offset = QPoint()

        self._recorder = None
        self._transcriber = None
        self._post_processor = None
        self._previous_hwnd = None
        self._recording_duration = 0.0
        self._recording_start = 0.0

        self._last_external_hwnd = None
        self._our_hwnd = None

        self._init_window()
        self._create_buttons()
        self._create_settings_panel()
        self._center_on_screen()

        self._compact_pill = CompactPill(self._bg_color)
        self._toast = ToastWidget(self._bg_color)

        self._init_hotkeys()
        self._init_tray_icon()
        self._init_topmost_enforcer()
        self._start_focus_tracker()

        # Startup toast — let user know the app is running in tray (green glow)
        self._startup_toast = ToastWidget(
            self._bg_color, glow_color=QColor(50, 200, 100))
        QTimer.singleShot(800, lambda: self._startup_toast.show_message(
            f"Whisper v{APP_VERSION} è in esecuzione", 3000))

        # Auto-update check (works even when starting minimized in tray)
        self._startup_done = True
        QTimer.singleShot(2000, self._auto_check_update)

    # ------------------------------------------------------------------ #
    #  Window setup
    # ------------------------------------------------------------------ #

    def _init_window(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        m = self.SHADOW
        self._win_w = self.PANEL_W + 2 * m

    def _create_buttons(self):
        m = self.SHADOW
        sz = 24
        right = m + self.PANEL_W - 8
        top = m + 6

        self._close_btn = QPushButton("\u2715", self)
        self._close_btn.setFixedSize(sz, sz)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
                color: rgba(255,255,255,0.6);
                font-size: 16px; font-weight: 900;
            }
            QPushButton:hover { color: rgba(255,100,100,0.95); }
        """)
        self._close_btn.move(right - sz, top)
        self._close_btn.clicked.connect(self.hide)

    def _create_settings_panel(self):
        m = self.SHADOW
        self._settings_panel = SettingsPanel(
            self, theme_name=self._theme_name, embedded=True)
        self._settings_panel.move(m, m + self.TITLE_H)
        self._settings_panel.setFixedWidth(self.PANEL_W)
        if self._api_key:
            self._settings_panel.set_api_key(self._api_key)
        self._settings_panel.api_key_saved.connect(self._on_api_key_saved)
        self._settings_panel.theme_changed.connect(self._on_theme_changed)

        self._settings_panel.show_embedded()

        total_h = self.TITLE_H + self._settings_panel.TARGET_HEIGHT + 2 * m
        self.setFixedSize(self._win_w, total_h)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.width()) // 2
            y = (geo.height() - self.height()) // 2
            self.move(x, y)

    # ------------------------------------------------------------------ #
    #  Painting
    # ------------------------------------------------------------------ #

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        m = self.SHADOW
        rect = QRectF(m, m, self.PANEL_W, self.height() - 2 * m)
        radius = 14

        # Drop shadow
        for i in range(m, 0, -2):
            a = max(0, 18 - i * 2)
            p.setBrush(QBrush(QColor(0, 0, 0, a)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect.adjusted(-i, -i, i, i), radius + i, radius + i)

        # Background
        bg = QColor(self._bg_color)
        bg.setAlpha(240)
        p.setBrush(QBrush(bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, radius, radius)

        # Border
        pen = QPen(QColor(255, 255, 255, 40))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, radius, radius)

        # Title
        title_rect = QRectF(rect.left() + 16, rect.top() + 2, 200, self.TITLE_H)
        font = QFont("Segoe UI", 11)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 160))
        p.drawText(title_rect,
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   f"Whisper v{APP_VERSION}")
        p.end()

    # ------------------------------------------------------------------ #
    #  Mouse handling (drag on title bar)
    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        m = self.SHADOW
        title = QRectF(m, m, self.PANEL_W, self.TITLE_H).toRect()
        if title.contains(event.pos()) and not self._close_btn.geometry().contains(event.pos()):
            self._press_pos = event.globalPosition().toPoint()
            self._is_dragging = False
            event.accept()

    def mouseMoveEvent(self, event):
        if self._press_pos is None:
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        delta = event.globalPosition().toPoint() - self._press_pos
        if not self._is_dragging and (abs(delta.x()) > 5 or abs(delta.y()) > 5):
            self._is_dragging = True
            self._drag_offset = self._press_pos - self.frameGeometry().topLeft()
        if self._is_dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._press_pos = None
        self._is_dragging = False

    # ------------------------------------------------------------------ #
    #  System tray icon
    # ------------------------------------------------------------------ #

    def _init_tray_icon(self):
        self._tray_icon = QSystemTrayIcon(self)
        app_icon = QApplication.instance().windowIcon()
        if not app_icon.isNull():
            self._tray_icon.setIcon(app_icon)
        else:
            self._tray_icon.setIcon(QIcon())
        self._tray_icon.setToolTip("Whisper")

        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu {
                background: #1e1e2e; color: #e0e0e0;
                border: 1px solid rgba(255,255,255,0.15);
                padding: 4px;
            }
            QMenu::item { padding: 6px 24px; }
            QMenu::item:selected { background: rgba(80,140,255,0.3); }
            QMenu::item:disabled { color: rgba(255,255,255,0.35); }
        """)

        version_action = QAction(f"Whisper v{APP_VERSION}", self)
        version_action.setEnabled(False)
        tray_menu.addAction(version_action)

        tray_menu.addSeparator()

        self._tray_show_action = QAction("Impostazioni", self)
        self._tray_show_action.triggered.connect(self._tray_toggle_window)
        tray_menu.addAction(self._tray_show_action)

        tray_menu.addSeparator()

        quit_action = QAction("Esci", self)
        quit_action.triggered.connect(self._quit_app)
        tray_menu.addAction(quit_action)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._tray_toggle_window()

    def _tray_toggle_window(self):
        if self.isVisible():
            self.hide()
        else:
            self.showNormal()
            self.activateWindow()

    def _update_tray_text(self):
        if self.isVisible():
            self._tray_show_action.setText("Nascondi")
        else:
            self._tray_show_action.setText("Impostazioni")

    def _quit_app(self):
        self._tray_icon.hide()
        QApplication.quit()

    # ------------------------------------------------------------------ #
    #  Always-on-top enforcer (compact pill only)
    # ------------------------------------------------------------------ #

    def _init_topmost_enforcer(self):
        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._enforce_topmost)
        self._topmost_timer.start(5000)

    def _enforce_topmost(self):
        if self._compact_pill.isVisible():
            user32 = ctypes.windll.user32
            hwnd = int(self._compact_pill.winId())
            if hwnd:
                user32.SetWindowPos(
                    hwnd, -1, 0, 0, 0, 0,
                    0x0002 | 0x0001 | 0x0010)  # NOMOVE | NOSIZE | NOACTIVATE

    # ------------------------------------------------------------------ #
    #  Events
    # ------------------------------------------------------------------ #

    def showEvent(self, event):
        super().showEvent(event)
        self._our_hwnd = int(self.winId())
        if hasattr(self, '_tray_icon'):
            self._update_tray_text()
        self._settings_panel.refresh_data()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, '_tray_icon'):
            self._update_tray_text()

    # ------------------------------------------------------------------ #
    #  Auto-update check at startup
    # ------------------------------------------------------------------ #

    def _auto_check_update(self):
        if not GITHUB_REPO or not load_auto_update():
            return
        self._startup_update_checker = UpdateChecker(GITHUB_REPO, self)
        self._startup_update_checker.update_available.connect(
            self._on_startup_update_available)
        self._startup_update_checker.start()

    def _on_startup_update_available(self, tag, download_url, notes):
        # Show update progress window
        self._update_window = UpdateWindow(self._bg_color)
        self._update_window.show_update(tag)

        # Auto-download and install
        self._auto_downloader = UpdateDownloader(download_url, self)
        self._auto_downloader.progress.connect(self._on_auto_download_progress)
        self._auto_downloader.finished.connect(
            lambda path: self._on_auto_download_finished(path, tag))
        self._auto_downloader.error.connect(self._on_auto_download_error)
        self._auto_downloader.start()

    def _on_auto_download_progress(self, percent):
        if hasattr(self, '_update_window'):
            self._update_window.set_progress(percent)

    def _on_auto_download_finished(self, temp_path, tag):
        if hasattr(self, '_update_window'):
            self._update_window.set_installing()
        apply_update_and_restart(temp_path)

    def _on_auto_download_error(self, message):
        if hasattr(self, '_update_window'):
            self._update_window.dismiss()
        if hasattr(self, '_tray_icon') and self._tray_icon.isVisible():
            self._tray_icon.showMessage(
                "Aggiornamento fallito",
                message,
                QSystemTrayIcon.MessageIcon.Warning,
                5000,
            )

    # ------------------------------------------------------------------ #
    #  Focus tracker
    # ------------------------------------------------------------------ #

    def _start_focus_tracker(self):
        self._focus_timer = QTimer(self)
        self._focus_timer.timeout.connect(self._track_foreground)
        self._focus_timer.start(300)

    def _track_foreground(self):
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd and hwnd != self._our_hwnd:
            self._last_external_hwnd = hwnd

    # ------------------------------------------------------------------ #
    #  Global hotkeys
    # ------------------------------------------------------------------ #

    def _init_hotkeys(self):
        shortcuts = load_shortcuts()
        self._hotkey_mgr = HotkeyManager(self)
        self._apply_shortcuts(shortcuts)
        self._hotkey_mgr.toggle_triggered.connect(self._on_hotkey_toggle)
        self._hotkey_mgr.stop_triggered.connect(self._on_hotkey_stop)
        self._hotkey_mgr.discard_triggered.connect(self._on_hotkey_discard)
        self._hotkey_mgr.start()

        self._settings_panel.shortcuts_changed.connect(self._on_shortcuts_changed)

    def _apply_shortcuts(self, shortcuts: dict):
        self._hotkey_mgr.set_toggle_key(shortcuts.get("toggle_key", "U"))
        self._hotkey_mgr.set_discard_key(shortcuts.get("discard_key", "I"))
        self._hotkey_mgr.set_hold_record_key(shortcuts.get("hold_record_key", "PAUSE"))
        self._hotkey_mgr.set_hold_discard_key(shortcuts.get("hold_discard_key", "SCROLL_LOCK"))
        self._hotkey_mgr.set_mode(shortcuts.get("mode", "toggle"))
        self._hotkey_mgr.set_enabled(shortcuts.get("enabled", True))

    def _on_shortcuts_changed(self, shortcuts: dict):
        self._apply_shortcuts(shortcuts)

    def _on_hotkey_toggle(self):
        if self._state in ("transcribing", "success", "error"):
            return
        if self._state == "idle":
            if not self._api_key:
                return
            self._previous_hwnd = self._last_external_hwnd
            self._start_compact_recording()
        elif self._state == "recording":
            self._stop_compact_recording()

    def _on_hotkey_stop(self):
        if self._state != "recording":
            return
        self._stop_compact_recording()

    def _on_hotkey_discard(self):
        if self._state != "recording":
            return
        self._compact_pill.stop()
        self._discard_recording()

    # ------------------------------------------------------------------ #
    #  Compact recording
    # ------------------------------------------------------------------ #

    def _start_compact_recording(self):
        self._state = "recording"
        self._recording_start = time.time()

        self._recorder = AudioRecorder(self)
        self._recorder.finished.connect(self._on_recording_finished)
        self._recorder.error.connect(self._on_error)
        self._recorder.amplitude.connect(self._compact_pill.on_amplitude)
        self._recorder.start()

        self._compact_pill.set_bg_color(self._bg_color)
        self._compact_pill.start_recording()

    def _stop_compact_recording(self):
        self._compact_pill.enter_transcribing()
        self._state = "transcribing"
        self._recording_duration = time.time() - self._recording_start
        if self._recorder:
            self._recorder.stop_recording()

    # ------------------------------------------------------------------ #
    #  State machine
    # ------------------------------------------------------------------ #

    def _discard_recording(self):
        if self._state != "recording":
            return
        if self._recorder:
            try:
                self._recorder.finished.disconnect(self._on_recording_finished)
            except TypeError:
                pass
            self._recorder.stop_recording()
            self._recorder = None
        self._reset_to_idle()

    def _on_recording_finished(self, wav_path: str):
        self._transcriber = TranscriberWorker(wav_path, self._api_key, self)
        self._transcriber.finished.connect(self._on_transcription_done)
        self._transcriber.error.connect(self._on_error)
        self._transcriber.start()

    def _on_transcription_done(self, text: str):
        if load_post_processing():
            self._raw_transcription = text
            self._post_processor = PostProcessorWorker(text, self._api_key, self)
            self._post_processor.finished.connect(self._on_post_processing_done)
            self._post_processor.error.connect(self._on_post_processing_error)
            self._post_processor.start()
        else:
            self._deliver_result(text)

    def _on_post_processing_done(self, text: str):
        self._deliver_result(text)

    def _on_post_processing_error(self, message: str):
        self._deliver_result(self._raw_transcription)

    def _deliver_result(self, text: str):
        pyperclip.copy(text)
        save_transcription(text, self._recording_duration)
        if self.isVisible():
            self._settings_panel.refresh_data()

        self._state = "success"
        self._compact_pill.enter_success()
        self._compact_pill.closed.connect(self._finish_compact_success)
        self._paste_to_previous_window()

    def _finish_compact_success(self):
        try:
            self._compact_pill.closed.disconnect(self._finish_compact_success)
        except TypeError:
            pass
        if self._state == "error":
            return
        self._compact_pill.hide()
        self._toast.dismiss()
        self._reset_to_idle()

    def _on_error(self, message: str):
        self._compact_pill.stop()
        if hasattr(self, '_tray_icon') and self._tray_icon.isVisible():
            self._tray_icon.showMessage(
                "Errore", message,
                QSystemTrayIcon.MessageIcon.Warning, 3000)
        self._reset_to_idle()

    def _reset_to_idle(self):
        self._state = "idle"

    # ------------------------------------------------------------------ #
    #  Paste to previous window
    # ------------------------------------------------------------------ #

    def _paste_to_previous_window(self):
        if not self._previous_hwnd:
            self._show_clipboard_toast()
            return
        hwnd = self._previous_hwnd
        self._previous_hwnd = None
        QTimer.singleShot(100, lambda: self._do_paste(hwnd))

    def _do_paste(self, hwnd):
        try:
            user32 = ctypes.windll.user32
            if not user32.IsWindow(hwnd):
                self._show_clipboard_toast()
                return
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)
            current_thread = user32.GetCurrentThreadId()
            target_thread = user32.GetWindowThreadProcessId(hwnd, None)
            if current_thread != target_thread:
                user32.AttachThreadInput(current_thread, target_thread, True)
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)
                user32.AttachThreadInput(current_thread, target_thread, False)
            else:
                user32.SetForegroundWindow(hwnd)
            self._paste_target_hwnd = hwnd
            QTimer.singleShot(100, self._execute_paste)
        except Exception:
            try:
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                self._paste_target_hwnd = hwnd
                QTimer.singleShot(100, self._execute_paste)
            except Exception:
                self._show_clipboard_toast()

    def _execute_paste(self):
        user32 = ctypes.windll.user32
        fg = user32.GetForegroundWindow()
        if fg != self._paste_target_hwnd:
            self._show_clipboard_toast()
            return
        pyautogui.hotkey('ctrl', 'v')
        if load_paste_sound():
            play_ding()

    def _show_clipboard_toast(self):
        if load_paste_sound():
            play_error()
        self._state = "error"
        self._toast.set_bg_color(self._bg_color)
        self._toast.show_message(
            "Incolla non riuscito \u2014 testo negli appunti",
            duration_ms=2000,
            avoid_widget=self._compact_pill,
        )
        QTimer.singleShot(2500, self._finish_error)

    def _finish_error(self):
        if self._state != "error":
            return
        self._compact_pill.hide()
        self._toast.dismiss()
        self._reset_to_idle()

    # ------------------------------------------------------------------ #
    #  Settings callbacks
    # ------------------------------------------------------------------ #

    def _on_api_key_saved(self, key: str):
        self._api_key = key

    def _on_theme_changed(self, name: str):
        self._theme_name = name
        self._bg_color = THEME_COLORS.get(name, THEME_COLORS["Midnight"])
        save_theme(name)
        self._compact_pill.set_bg_color(self._bg_color)
        self._toast.set_bg_color(self._bg_color)
        self._settings_panel.update()
        self.update()
