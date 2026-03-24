import ctypes
import ctypes.wintypes
import math
import os
import time
from utils.sound import play_ding, play_error

import pyperclip
import pyautogui
import qtawesome as qta
from PyQt6.QtCore import (
    Qt, QRectF, QPoint, QTimer, pyqtProperty, QTime, QEvent,
)
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont,
    QLinearGradient, QPainterPath, QIcon, QAction,
)
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QToolTip, QApplication,
    QSystemTrayIcon, QMenu,
)

from core.recorder import AudioRecorder
from core.transcriber import TranscriberWorker
from core.post_processor import PostProcessorWorker
from ui.settings_panel import SettingsPanel
from ui.compact_pill import CompactPill
from ui.toast_widget import ToastWidget
from ui.animations import (
    create_success_flash,
    create_error_flash,
)
from utils.config import (
    load_theme, save_theme, save_transcription, load_shortcuts,
    load_post_processing, load_paste_sound, load_start_minimized,
    load_github_repo, load_auto_update,
)
from utils.hotkeys import HotkeyManager
from core.updater import UpdateChecker

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
    SHADOW_MARGIN = 20
    PILL_WIDTH = 280
    PILL_HEIGHT = 80
    HEADER_HEIGHT = 30
    NUM_BARS = 5
    WAVEFORM_MAX_SAMPLES = 200

    # Panel is wider than the pill, centered below it
    PANEL_WIDTH = 440
    PANEL_SPACE = 870


    def __init__(self, api_key: str = ""):
        super().__init__()
        self._api_key = api_key
        self._state = "idle"
        self._theme_name = load_theme()
        self._bg_color = THEME_COLORS.get(self._theme_name, THEME_COLORS["Midnight"])

        self._press_pos = None
        self._press_time = None
        self._is_dragging = False
        self._drag_offset = QPoint()

        self._bg_glow_opacity = 0
        self._error_flash_opacity = 0
        self._success_glow_opacity = 0
        self._startup_glow_opacity = 0

        self._recorder = None
        self._transcriber = None
        self._post_processor = None
        self._previous_hwnd = None
        self._recording_duration = 0.0

        self._settings_open = False

        self._active_anim = None
        self._glow_anim = None
        self._flash_anim = None

        self._waveform_history = []
        self._current_amplitude = 0.0
        self._recording_start = 0.0
        self._idle_phase = 0.0

        self._last_external_hwnd = None
        self._our_hwnd = None

        # Computed positions
        m = self.SHADOW_MARGIN
        self._window_w = self.PANEL_WIDTH + 2 * m
        self._pill_x = m + (self.PANEL_WIDTH - self.PILL_WIDTH) // 2

        self._init_window()
        self._create_buttons()
        self._create_trash_button()
        self._create_settings_panel()
        self._center_on_screen()
        self._start_focus_tracker()

        self._compact_pill = CompactPill(self._bg_color)
        self._compact_mode = False  # True when recording via hotkey while minimized
        self._toast = ToastWidget(self._bg_color)

        self._init_hotkeys()
        self._init_tray_icon()
        self._init_topmost_enforcer()

        self._paint_timer = QTimer(self)
        self._paint_timer.timeout.connect(self._tick)
        self._paint_timer.start(16)

    # ------------------------------------------------------------------ #
    #  Animated properties
    # ------------------------------------------------------------------ #

    @pyqtProperty(int)
    def bgGlowOpacity(self):
        return self._bg_glow_opacity

    @bgGlowOpacity.setter
    def bgGlowOpacity(self, v):
        self._bg_glow_opacity = v
        self.update()

    @pyqtProperty(int)
    def errorFlashOpacity(self):
        return self._error_flash_opacity

    @errorFlashOpacity.setter
    def errorFlashOpacity(self, v):
        self._error_flash_opacity = v
        self.update()

    @pyqtProperty(int)
    def successGlowOpacity(self):
        return self._success_glow_opacity

    @successGlowOpacity.setter
    def successGlowOpacity(self, v):
        self._success_glow_opacity = v
        self.update()

    @pyqtProperty(int)
    def startupGlowOpacity(self):
        return self._startup_glow_opacity

    @startupGlowOpacity.setter
    def startupGlowOpacity(self, v):
        self._startup_glow_opacity = v
        self.update()

    # ------------------------------------------------------------------ #
    #  Setup
    # ------------------------------------------------------------------ #

    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        m = self.SHADOW_MARGIN
        total_h = self.PILL_HEIGHT + 2 * m + self.PANEL_SPACE
        self.setFixedSize(self._window_w, total_h)

    def _create_buttons(self):
        btn_size = 24
        px = self._pill_x
        right_edge = px + self.PILL_WIDTH - 8
        top = self.SHADOW_MARGIN + 3

        # Close
        self._close_btn = QPushButton("\u2715", self)
        self._close_btn.setFixedSize(btn_size, btn_size)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
                color: rgba(255,255,255,0.6);
                font-size: 16px; font-weight: 900;
            }
            QPushButton:hover { color: rgba(255,100,100,0.95); }
        """)
        self._close_btn.move(right_edge - btn_size, top)
        self._close_btn.clicked.connect(self.hide)

        # Settings
        self._gear_btn = QPushButton("\u2630", self)
        self._gear_btn.setFixedSize(btn_size, btn_size)
        self._gear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gear_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
                color: rgba(255,255,255,0.45);
                font-size: 16px; font-weight: 900;
            }
            QPushButton:hover { color: rgba(255,255,255,0.85); }
        """)
        self._gear_btn.move(right_edge - 2 * btn_size - 2, top)
        self._gear_btn.clicked.connect(self._toggle_settings)

    def _create_trash_button(self):
        self._trash_btn = QPushButton(self)
        self._trash_btn.setIcon(qta.icon('fa5s.trash-alt', color='#ff6464'))
        self._trash_btn.setFixedSize(26, 26)
        self._trash_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._trash_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
            }
            QPushButton:hover {
                background: rgba(255,80,80,0.18);
                border-radius: 13px;
            }
        """)
        content_center_y = (self.SHADOW_MARGIN + self.HEADER_HEIGHT
                            + (self.PILL_HEIGHT - self.HEADER_HEIGHT) // 2)
        self._trash_btn.move(self._pill_x + 10, content_center_y - 13)
        self._trash_btn.clicked.connect(self._discard_recording)
        self._trash_btn.hide()

    def _create_settings_panel(self):
        m = self.SHADOW_MARGIN
        self._settings_panel = SettingsPanel(self, theme_name=self._theme_name)
        self._settings_panel.move(m, m + self.PILL_HEIGHT + 6)
        self._settings_panel.setFixedWidth(self.PANEL_WIDTH)
        if self._api_key:
            self._settings_panel.set_api_key(self._api_key)
        self._settings_panel.api_key_saved.connect(self._on_api_key_saved)
        self._settings_panel.theme_changed.connect(self._on_theme_changed)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.width()) // 2
            self.move(x, 60)

    def _run_startup_glow(self):
        from PyQt6.QtCore import QPropertyAnimation
        anim = QPropertyAnimation(self, b"startupGlowOpacity")
        anim.setDuration(1800)
        anim.setKeyValueAt(0.0, 0)
        anim.setKeyValueAt(0.15, 140)
        anim.setKeyValueAt(0.5, 80)
        anim.setKeyValueAt(1.0, 0)
        self._startup_anim = anim
        anim.start()

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
        """)

        self._tray_show_action = QAction("Mostra", self)
        self._tray_show_action.triggered.connect(self._tray_toggle_window)
        tray_menu.addAction(self._tray_show_action)

        tray_menu.addSeparator()

        quit_action = QAction("Esci", self)
        quit_action.triggered.connect(self._quit_app)
        tray_menu.addAction(quit_action)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    # ------------------------------------------------------------------ #
    #  Always-on-top enforcer (Windows API)
    # ------------------------------------------------------------------ #

    def _init_topmost_enforcer(self):
        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._enforce_topmost)
        self._topmost_timer.start(5000)

    def _enforce_topmost(self):
        user32 = ctypes.windll.user32
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010
        HWND_TOPMOST = -1
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE

        # Enforce on main pill (if visible and not minimized)
        if self.isVisible() and not self.isMinimized() and self._our_hwnd:
            user32.SetWindowPos(self._our_hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)

        # Enforce on compact pill (if visible)
        if self._compact_pill.isVisible():
            compact_hwnd = int(self._compact_pill.winId())
            if compact_hwnd:
                user32.SetWindowPos(compact_hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._tray_toggle_window()

    def _tray_toggle_window(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal()
            self.activateWindow()

    def _update_tray_text(self):
        if self.isVisible() and not self.isMinimized():
            self._tray_show_action.setText("Nascondi")
        else:
            self._tray_show_action.setText("Mostra")

    def _quit_app(self):
        self._tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        # Hide to tray instead of quitting
        event.ignore()
        self.hide()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() != QEvent.Type.WindowStateChange:
            return

        if hasattr(self, '_tray_icon'):
            self._update_tray_text()

        if self.isMinimized():
            # Minimized: if recording/transcribing, show compact pill
            if self._state == "recording":
                self._compact_mode = True
                self._compact_pill.set_bg_color(self._bg_color)
                self._compact_pill.start_recording()
                self._compact_pill._recording_start = self._recording_start
                self._compact_pill._waveform_history = list(self._waveform_history)
                self._compact_pill._current_amplitude = self._current_amplitude
                if self._recorder:
                    self._recorder.amplitude.connect(self._compact_pill.on_amplitude)
                self._trash_btn.hide()
            elif self._state == "transcribing" and not self._compact_mode:
                self._compact_mode = True
                self._compact_pill.set_bg_color(self._bg_color)
                self._compact_pill.start_recording()
                self._compact_pill.enter_transcribing()
        else:
            # Restored: hide compact pill, show normal UI
            if self._compact_mode:
                self._compact_pill.stop()
                self._compact_mode = False
                if self._recorder:
                    try:
                        self._recorder.amplitude.disconnect(self._compact_pill.on_amplitude)
                    except TypeError:
                        pass
                if self._state == "recording":
                    self._trash_btn.show()
                self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._our_hwnd = int(self.winId())
        if hasattr(self, '_tray_icon'):
            self._update_tray_text()
        # One-time startup glow to help locate the pill
        if not hasattr(self, '_startup_done'):
            self._startup_done = True
            self._run_startup_glow()
            # Auto-check for updates silently
            self._auto_check_update()

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, '_tray_icon'):
            self._update_tray_text()

    # ------------------------------------------------------------------ #
    #  Auto-update check at startup
    # ------------------------------------------------------------------ #

    def _auto_check_update(self):
        repo = load_github_repo()
        if not repo or not load_auto_update():
            return
        self._startup_update_checker = UpdateChecker(repo, self)
        self._startup_update_checker.update_available.connect(
            self._on_startup_update_available)
        self._startup_update_checker.start()

    def _on_startup_update_available(self, tag, download_url, notes):
        if hasattr(self, '_tray_icon') and self._tray_icon.isVisible():
            self._tray_icon.showMessage(
                "Aggiornamento disponibile",
                f"Whisper {tag} è disponibile. Apri le impostazioni per aggiornare.",
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )

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
            if self.isMinimized() or not self.isVisible():
                self._start_compact_recording()
            else:
                self._toggle_recording()
        elif self._state == "recording":
            if self._compact_mode:
                self._stop_compact_recording()
            else:
                self._toggle_recording()

    def _on_hotkey_stop(self):
        if self._state != "recording":
            return
        if self._compact_mode:
            self._stop_compact_recording()
        else:
            self._toggle_recording()

    def _on_hotkey_discard(self):
        if self._state != "recording":
            return
        if self._compact_mode:
            self._compact_pill.stop()
            self._compact_mode = False
        self._discard_recording()

    def _start_compact_recording(self):
        self._compact_mode = True
        self._state = "recording"
        self._waveform_history = []
        self._current_amplitude = 0.0
        self._recording_start = time.time()

        self._start_bg_pulse(25)

        self._recorder = AudioRecorder(self)
        self._recorder.finished.connect(self._on_recording_finished)
        self._recorder.error.connect(self._on_error)
        self._recorder.amplitude.connect(self._on_amplitude)
        self._recorder.amplitude.connect(self._compact_pill.on_amplitude)
        self._recorder.start()

        self._compact_pill.set_bg_color(self._bg_color)
        self._compact_pill.start_recording()

    def _stop_compact_recording(self):
        self._compact_pill.enter_transcribing()
        # compact_mode stays True — pill remains visible
        self._state = "transcribing"
        self._recording_duration = time.time() - self._recording_start
        self._stop_bg_pulse()

        if self._recorder:
            self._recorder.stop_recording()

    # ------------------------------------------------------------------ #
    #  Tick (~60fps)
    # ------------------------------------------------------------------ #

    def _tick(self):
        if self._state == "idle":
            self._idle_phase += 0.025
        self.update()

    # ------------------------------------------------------------------ #
    #  Painting
    # ------------------------------------------------------------------ #

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        px = self._pill_x
        m = self.SHADOW_MARGIN
        pill = QRectF(px, m, self.PILL_WIDTH, self.PILL_HEIGHT)
        radius = 18

        # Startup glow (outer halo)
        if self._startup_glow_opacity > 0:
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(1, 18):
                a = max(0, self._startup_glow_opacity - i * 12)
                if a <= 0:
                    break
                spread = i * 1.8
                p.setBrush(QBrush(QColor(90, 150, 255, a)))
                p.drawRoundedRect(
                    pill.adjusted(-spread, -spread, spread, spread),
                    radius + spread, radius + spread)

        # Drop shadow
        for i in range(m, 0, -2):
            alpha = max(0, 22 - i * 2)
            p.setBrush(QBrush(QColor(0, 0, 0, alpha)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(pill.adjusted(-i, -i, i, i), radius + i, radius + i)

        # Pill body
        bg = QColor(self._bg_color)
        bg.setAlpha(217)
        p.setBrush(QBrush(bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(pill, radius, radius)

        # Background glow fill
        if self._bg_glow_opacity > 0:
            if self._state == "recording":
                glow_color = QColor(255, 60, 60, self._bg_glow_opacity)
            elif self._state == "transcribing":
                glow_color = QColor(80, 120, 255, self._bg_glow_opacity)
            else:
                glow_color = QColor(255, 255, 255, self._bg_glow_opacity)
            p.setBrush(QBrush(glow_color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(pill, radius, radius)

        # Inner edge glow during transcribing
        if self._state == "transcribing":
            self._paint_inner_glow(p, pill, radius)

        # Success sweep glow
        if self._success_glow_opacity > 0:
            self._paint_success_sweep(p, pill, radius)

        # White border
        border_pen = QPen(QColor(255, 255, 255, 45))
        border_pen.setWidthF(1.2)
        p.setPen(border_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(pill, radius, radius)

        # Error flash
        if self._error_flash_opacity > 0:
            err_pen = QPen(QColor(255, 50, 50, self._error_flash_opacity))
            err_pen.setWidthF(2.0)
            p.setPen(err_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(pill, radius, radius)

        # --- Clip to pill and draw content ---
        p.save()
        p.setClipRect(pill.toRect())

        header_rect = QRectF(pill.left() + 16, pill.top() + 2, 120, self.HEADER_HEIGHT)
        title_font = QFont("Segoe UI", 10)
        title_font.setWeight(QFont.Weight.Bold)
        p.setFont(title_font)
        p.setPen(QColor(255, 255, 255, 140))
        p.drawText(header_rect,
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   "Whisper")

        content_top = pill.top() + self.HEADER_HEIGHT
        content_rect = QRectF(
            pill.left(), content_top,
            pill.width(), pill.height() - self.HEADER_HEIGHT)

        if self._state == "idle":
            self._draw_idle(p, content_rect)
        elif self._state == "recording":
            self._draw_recording(p, content_rect)
        elif self._state == "transcribing":
            self._draw_transcribing(p, content_rect)
        elif self._state == "success":
            self._draw_success(p, content_rect)

        p.restore()
        p.end()

    # ---- inner glow (transcribing) ----

    def _paint_inner_glow(self, p: QPainter, pill: QRectF, radius: float):
        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(pill, radius, radius)
        p.setClipPath(clip)
        p.setPen(Qt.PenStyle.NoPen)

        pulse = 0.5 + 0.5 * math.sin(time.time() * 2.5)
        base_alpha = int(55 + 40 * pulse)
        br, bg, bb = 45, 90, 220
        depth = 28.0

        # Left
        g = QLinearGradient(pill.left(), 0, pill.left() + depth, 0)
        g.setColorAt(0, QColor(br, bg, bb, base_alpha))
        g.setColorAt(1, QColor(br, bg, bb, 0))
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(pill.left(), pill.top(), depth, pill.height()))

        # Right
        g = QLinearGradient(pill.right(), 0, pill.right() - depth, 0)
        g.setColorAt(0, QColor(br, bg, bb, base_alpha))
        g.setColorAt(1, QColor(br, bg, bb, 0))
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(pill.right() - depth, pill.top(), depth, pill.height()))

        # Top
        g = QLinearGradient(0, pill.top(), 0, pill.top() + depth)
        g.setColorAt(0, QColor(br, bg, bb, base_alpha))
        g.setColorAt(1, QColor(br, bg, bb, 0))
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(pill.left(), pill.top(), pill.width(), depth))

        # Bottom
        g = QLinearGradient(0, pill.bottom(), 0, pill.bottom() - depth)
        g.setColorAt(0, QColor(br, bg, bb, base_alpha))
        g.setColorAt(1, QColor(br, bg, bb, 0))
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(pill.left(), pill.bottom() - depth, pill.width(), depth))

        p.restore()

    def _paint_success_sweep(self, p: QPainter, pill: QRectF, radius: float):
        """Animated green gradient sweep left→right, then fade out."""
        progress = self._success_glow_opacity / 255.0  # 0.0 → 1.0

        # Phase 1 (0–0.5): sweep moves left to right, fading in
        # Phase 2 (0.5–1.0): sweep at right edge, whole thing fades out
        if progress < 0.5:
            t = progress / 0.5
            sweep = t
            alpha = int(120 * min(1.0, t / 0.2))
        else:
            t = (progress - 0.5) / 0.5
            sweep = 1.0
            alpha = int(120 * (1.0 - t))

        if alpha <= 0:
            return

        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(pill, radius, radius)
        p.setClipPath(clip)
        p.setPen(Qt.PenStyle.NoPen)

        # Sweeping highlight gradient
        g = QLinearGradient(pill.left(), 0, pill.right(), 0)
        spread = 0.25
        center = sweep
        g.setColorAt(0, QColor(50, 200, 100, 0))
        g.setColorAt(max(0.0, center - spread), QColor(50, 200, 100, 0))
        g.setColorAt(min(1.0, center), QColor(50, 200, 100, alpha))
        g.setColorAt(min(1.0, center + 0.01), QColor(50, 200, 100, alpha))
        g.setColorAt(min(1.0, center + spread), QColor(50, 200, 100, 0))
        if center + spread < 1.0:
            g.setColorAt(1.0, QColor(50, 200, 100, 0))
        p.setBrush(QBrush(g))
        p.drawRect(pill)

        p.restore()

        # Green border glow
        border_alpha = int(alpha * 0.7)
        if border_alpha > 0:
            pen = QPen(QColor(50, 200, 100, border_alpha))
            pen.setWidthF(1.5)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(pill, radius, radius)

    # ---- state drawings ----

    def _draw_idle(self, p: QPainter, rect: QRectF):
        cy = rect.center().y()
        cx = rect.center().x()
        w = 60
        left = cx - w / 2

        p.setPen(Qt.PenStyle.NoPen)
        num = 5
        spacing = w / (num - 1)
        for i in range(num):
            phase = self._idle_phase + i * 0.6
            h = 3 + 4 * abs(math.sin(phase))
            x = left + i * spacing
            bar = QRectF(x - 1.5, cy - h / 2, 3, h)
            alpha = 120 + int(40 * abs(math.sin(phase)))
            p.setBrush(QBrush(QColor(180, 180, 195, alpha)))
            p.drawRoundedRect(bar, 1.5, 1.5)

    def _draw_recording(self, p: QPainter, rect: QRectF):
        cy = rect.center().y()

        elapsed = time.time() - self._recording_start
        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        timer_text = f"{mins}:{secs:02d}"

        font = QFont("Segoe UI", 11)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor(255, 100, 100, 220))
        timer_rect = QRectF(rect.left() + 43, rect.top(), 48, rect.height())
        p.drawText(timer_rect,
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   timer_text)

        waveform_left = rect.left() + 91
        waveform_right = rect.right() - 18
        samples = self._waveform_history[-int((waveform_right - waveform_left) / 3):] \
            if self._waveform_history else []

        bar_w = 2.0
        gap = 1.0
        max_h = rect.height() * 0.75

        for i, amp in enumerate(reversed(samples)):
            x = waveform_right - (i + 1) * (bar_w + gap)
            if x < waveform_left:
                break
            h = max(2, amp * max_h)
            bar_rect = QRectF(x, cy - h / 2, bar_w, h)
            fade = max(80, 255 - i * 2)
            p.setBrush(QBrush(QColor(255, 90, 90, fade)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(bar_rect, 1, 1)

    def _draw_transcribing(self, p: QPainter, rect: QRectF):
        cy = rect.center().y()
        cx = rect.center().x()
        w = 60
        left = cx - w / 2

        p.setPen(Qt.PenStyle.NoPen)
        num = 5
        spacing = w / (num - 1)
        phase = time.time() * 3.5
        for i in range(num):
            p_i = phase + i * 0.8
            h = 3 + 8 * abs(math.sin(p_i))
            x = left + i * spacing
            bar = QRectF(x - 1.5, cy - h / 2, 3, h)
            alpha = 140 + int(60 * abs(math.sin(p_i)))
            p.setBrush(QBrush(QColor(130, 150, 255, alpha)))
            p.drawRoundedRect(bar, 1.5, 1.5)

    def _draw_success(self, p: QPainter, rect: QRectF):
        pass

    # ------------------------------------------------------------------ #
    #  Mouse handling
    # ------------------------------------------------------------------ #

    def _is_on_controls(self, pos: QPoint) -> bool:
        for btn in (self._close_btn, self._gear_btn, self._trash_btn):
            if btn.geometry().contains(pos):
                return True
        return False

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pill_rect = QRectF(
            self._pill_x, self.SHADOW_MARGIN,
            self.PILL_WIDTH, self.PILL_HEIGHT,
        ).toRect()
        if pill_rect.contains(event.pos()) and not self._is_on_controls(event.pos()):
            self._press_pos = event.globalPosition().toPoint()
            self._press_time = QTime.currentTime()
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
        if self._press_pos is not None and not self._is_dragging:
            self._toggle_recording()
        self._press_pos = None
        self._is_dragging = False

    # ------------------------------------------------------------------ #
    #  Voice-reactive waveform
    # ------------------------------------------------------------------ #

    def _on_amplitude(self, levels: list):
        if self._state != "recording":
            return
        avg = sum(levels) / len(levels) if levels else 0.0
        self._current_amplitude += (avg - self._current_amplitude) * 0.5
        self._waveform_history.append(self._current_amplitude)
        if len(self._waveform_history) > self.WAVEFORM_MAX_SAMPLES:
            self._waveform_history = self._waveform_history[-self.WAVEFORM_MAX_SAMPLES:]

    # ------------------------------------------------------------------ #
    #  State machine
    # ------------------------------------------------------------------ #

    def _toggle_recording(self):
        if self._state == "idle":
            if not self._api_key:
                QToolTip.showText(
                    self.mapToGlobal(QPoint(self.PILL_WIDTH // 2, 0)),
                    "Imposta la chiave API nelle impostazioni",
                )
                return
            self._previous_hwnd = self._last_external_hwnd
            self._state = "recording"
            self._waveform_history = []
            self._current_amplitude = 0.0
            self._recording_start = time.time()
            self._trash_btn.show()

            self._start_bg_pulse(25)

            self._recorder = AudioRecorder(self)
            self._recorder.finished.connect(self._on_recording_finished)
            self._recorder.error.connect(self._on_error)
            self._recorder.amplitude.connect(self._on_amplitude)
            self._recorder.start()
            self.update()

        elif self._state == "recording":
            self._state = "transcribing"
            self._recording_duration = time.time() - self._recording_start
            self._trash_btn.hide()
            self._stop_bg_pulse()
            self._start_bg_pulse(30)

            if self._recorder:
                self._recorder.stop_recording()
            self.update()

    def _discard_recording(self):
        if self._state != "recording":
            return
        self._trash_btn.hide()
        self._stop_bg_pulse()
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
        self._stop_bg_pulse()
        pyperclip.copy(text)

        # Save to history
        save_transcription(text, self._recording_duration)
        if self._settings_open:
            self._settings_panel.refresh_data()

        self._state = "success"
        self.update()

        if self._compact_mode:
            self._compact_pill.enter_success()
            self._compact_pill.closed.connect(self._finish_compact_success)
        else:
            self._flash_anim = create_success_flash(self)
            self._flash_anim.finished.connect(self._finish_success)
            self._flash_anim.start()

        self._paste_to_previous_window()

    def _finish_success(self):
        self._flash_anim = None
        self._reset_to_idle()

    def _finish_compact_success(self):
        try:
            self._compact_pill.closed.disconnect(self._finish_compact_success)
        except TypeError:
            pass
        if self._state == "error":
            return
        self._compact_pill.hide()
        self._toast.dismiss()
        self._compact_mode = False
        self._reset_to_idle()

    def _on_error(self, message: str):
        self._stop_bg_pulse()
        if self._compact_mode:
            self._compact_pill.stop()
            self._compact_mode = False
        self._reset_to_idle()
        self._flash_anim = create_error_flash(self)
        self._flash_anim.start()
        QToolTip.showText(
            self.mapToGlobal(QPoint(self.PILL_WIDTH // 2, 0)),
            message,
        )

    def _finish_error(self):
        if self._state != "error":
            return
        if self._compact_mode:
            self._compact_pill.hide()
            self._compact_mode = False
        self._toast.dismiss()
        self._reset_to_idle()

    def _reset_to_idle(self):
        self._state = "idle"
        self._idle_phase = 0.0
        if self._compact_mode:
            self._compact_pill.stop()
            self._compact_mode = False
        self.update()

    # ------------------------------------------------------------------ #
    #  Background glow pulsing
    # ------------------------------------------------------------------ #

    def _start_bg_pulse(self, max_alpha):
        self._pulse_max = max_alpha
        self._pulse_phase = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick_pulse)
        self._pulse_timer.start(30)

    def _tick_pulse(self):
        self._pulse_phase += 0.08
        val = int(self._pulse_max * (0.5 + 0.5 * math.sin(self._pulse_phase)))
        self._bg_glow_opacity = val

    def _stop_bg_pulse(self):
        if hasattr(self, '_pulse_timer') and self._pulse_timer:
            self._pulse_timer.stop()
            self._pulse_timer = None
        self._bg_glow_opacity = 0

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
        error_duration = 2000
        if self._compact_mode:
            self._toast.show_message(
                "Incolla non riuscito \u2014 testo negli appunti",
                duration_ms=error_duration,
                avoid_widget=self._compact_pill,
            )
        else:
            pill_bottom_global = self.mapToGlobal(
                QPoint(self._pill_x, self.SHADOW_MARGIN + self.PILL_HEIGHT + 6))
            self._toast.show_message(
                "Incolla non riuscito \u2014 testo negli appunti",
                duration_ms=error_duration,
                anchor_point=pill_bottom_global,
            )
        QTimer.singleShot(error_duration + 500, self._finish_error)

    # ------------------------------------------------------------------ #
    #  Settings
    # ------------------------------------------------------------------ #

    def _toggle_settings(self):
        self._settings_open = not self._settings_open
        if self._settings_open:
            self._settings_panel.slide_open()
        else:
            self._settings_panel.slide_close()
        self.update()

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


