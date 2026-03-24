import os
import sys
import tempfile
import winreg
from datetime import datetime, timedelta, date

import pyperclip
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, pyqtSignal, pyqtProperty, QRectF,
)
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QPixmap, QFont, QLinearGradient,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QCheckBox,
    QScrollArea, QFrame, QGraphicsOpacityEffect,
)
import qtawesome as qta

from utils.config import (
    save_api_key, load_history, load_shortcuts, save_shortcuts,
    load_post_processing, save_post_processing,
    load_paste_sound, save_paste_sound,
    load_start_minimized, save_start_minimized,
    load_auto_update, save_auto_update,
)
from core.updater import (
    APP_VERSION, GITHUB_REPO, UpdateChecker, UpdateDownloader,
    apply_update_and_restart,
)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

IT_TZ = ZoneInfo("Europe/Rome")

ICON_COLOR = QColor(255, 255, 255, 140)


def _create_check_icon_path():
    pm = QPixmap(14, 14)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(255, 255, 255, 220))
    pen.setWidthF(2.0)
    p.setPen(pen)
    p.drawLine(3, 7, 6, 10)
    p.drawLine(6, 10, 11, 4)
    p.end()
    path = os.path.join(tempfile.gettempdir(), "whisper_check.png")
    pm.save(path)
    return path.replace("\\", "/")


THEME_COLORS = {
    "Midnight":  QColor(20, 20, 30),
    "Viola":     QColor(26, 16, 36),
    "Bordeaux":  QColor(34, 16, 22),
    "Ambra":     QColor(28, 22, 14),
    "Ardesia":   QColor(24, 24, 24),
    "Foresta":   QColor(16, 28, 20),
    "Oceano":    QColor(16, 24, 32),
}
THEME_ORDER = ["Midnight", "Viola", "Bordeaux", "Ambra", "Ardesia", "Foresta", "Oceano"]

THEME_PREVIEW = {
    "Midnight":  QColor(50, 50, 85),
    "Viola":     QColor(70, 40, 100),
    "Bordeaux":  QColor(100, 35, 55),
    "Ambra":     QColor(90, 70, 35),
    "Ardesia":   QColor(65, 65, 65),
    "Foresta":   QColor(35, 80, 50),
    "Oceano":    QColor(35, 65, 95),
}


# ------------------------------------------------------------------ #
#  Cost chart widget
# ------------------------------------------------------------------ #

class CostChartWidget(QWidget):

    FILTERS = [
        ("7gg", 7),
        ("30gg", 30),
        ("3 mesi", 90),
        ("1 anno", 365),
        ("Totale", 0),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = {}
        self._filter_days = 7
        self.setMinimumHeight(140)
        self.setMaximumHeight(155)

    def set_data(self, history: list):
        self._data = {}
        for entry in history:
            try:
                ts = datetime.fromisoformat(entry["timestamp"])
                day = ts.date().isoformat()
                self._data[day] = self._data.get(day, 0) + entry.get("cost", 0)
            except (KeyError, ValueError):
                continue
        self.update()

    def set_filter(self, days: int):
        self._filter_days = days
        self.update()

    def get_period_total(self) -> float:
        if not self._data:
            return 0.0
        today = datetime.now(IT_TZ).date()
        if self._filter_days > 0:
            start = today - timedelta(days=self._filter_days - 1)
        else:
            all_dates = sorted(self._data.keys())
            start = date.fromisoformat(all_dates[0]) if all_dates else today
        total = 0.0
        for i in range((today - start).days + 1):
            d = start + timedelta(days=i)
            total += self._data.get(d.isoformat(), 0)
        return total

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self._data:
            p.setPen(QColor(255, 255, 255, 60))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Nessun dato disponibile")
            p.end()
            return

        today = datetime.now(IT_TZ).date()
        if self._filter_days > 0:
            start_date = today - timedelta(days=self._filter_days - 1)
        else:
            all_dates = sorted(self._data.keys())
            start_date = date.fromisoformat(all_dates[0]) if all_dates else today

        days_range = (today - start_date).days + 1
        daily = [(start_date + timedelta(days=i),
                  self._data.get((start_date + timedelta(days=i)).isoformat(), 0))
                 for i in range(days_range)]

        if not daily:
            p.end()
            return

        ml, mr, mt, mb = 48, 10, 6, 22
        cw = self.width() - ml - mr
        ch = self.height() - mt - mb
        max_cost = max((c for _, c in daily), default=0) or 0.001

        p.setFont(QFont("Segoe UI", 8))
        for i in range(5):
            y_val = max_cost * (4 - i) / 4
            y_pos = mt + ch * i / 4
            p.setPen(QColor(255, 255, 255, 80))
            p.drawText(QRectF(0, y_pos - 8, ml - 4, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"${y_val:.4f}")
            p.setPen(QPen(QColor(255, 255, 255, 15)))
            p.drawLine(int(ml), int(y_pos), int(self.width() - mr), int(y_pos))

        num = len(daily)
        bar_total = cw / max(num, 1)
        bar_w = max(2, min(bar_total * 0.7, 18))
        gap = (bar_total - bar_w) / 2

        p.setPen(Qt.PenStyle.NoPen)
        for i, (d, cost) in enumerate(daily):
            if cost <= 0:
                continue
            x = ml + i * bar_total + gap
            bh = (cost / max_cost) * ch
            y = mt + ch - bh
            grad = QLinearGradient(x, y, x, mt + ch)
            grad.setColorAt(0, QColor(80, 150, 255, 210))
            grad.setColorAt(1, QColor(40, 80, 200, 130))
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(x, y, bar_w, bh), 2, 2)

        p.setPen(QColor(255, 255, 255, 70))
        p.setFont(QFont("Segoe UI", 8))
        step = max(1, num // 7)
        for i in range(0, num, step):
            d = daily[i][0]
            x = ml + i * bar_total + gap
            p.drawText(QRectF(x - 14, mt + ch + 2, 38, 16),
                       Qt.AlignmentFlag.AlignCenter, f"{d.day}/{d.month}")
        p.end()


# ------------------------------------------------------------------ #
#  Settings panel
# ------------------------------------------------------------------ #

class KeyCaptureButton(QPushButton):
    """Button that captures a single letter key when clicked."""
    key_captured = pyqtSignal(str)

    def __init__(self, key: str, parent=None):
        super().__init__(key.upper(), parent)
        self._listening = False
        self._current_key = key.upper()
        self.setFixedSize(30, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style(False)
        self.clicked.connect(self._start_listening)

    def _apply_style(self, active: bool):
        if active:
            self.setStyleSheet("""
                QPushButton {
                    background: rgba(80,140,255,0.3);
                    border: 1px solid rgba(80,140,255,0.6);
                    border-radius: 4px;
                    color: rgba(255,255,255,0.95);
                    font-size: 12px; font-weight: bold;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.10);
                    border: 1px solid rgba(255,255,255,0.18);
                    border-radius: 4px;
                    color: rgba(255,255,255,0.85);
                    font-size: 12px; font-weight: bold;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,0.16);
                    border: 1px solid rgba(255,255,255,0.30);
                }
            """)

    def _start_listening(self):
        self._listening = True
        self.setText("\u2026")
        self._apply_style(True)
        self.setFocus()

    def set_key(self, key: str):
        self._current_key = key.upper()
        self._listening = False
        self.setText(self._current_key)
        self._apply_style(False)

    def keyPressEvent(self, event):
        if self._listening:
            text = event.text().upper()
            if text.isalpha() and len(text) == 1:
                self._current_key = text
                self._listening = False
                self.setText(text)
                self._apply_style(False)
                self.clearFocus()
                self.key_captured.emit(text)
                return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        if self._listening:
            self._listening = False
            self.setText(self._current_key)
            self._apply_style(False)
        super().focusOutEvent(event)


SPECIAL_KEY_LABELS = {
    "PAUSE": "Pause", "SCROLL_LOCK": "Scroll Lock",
    "INSERT": "Insert", "HOME": "Home", "END": "End",
    "PAGE_UP": "Page Up", "PAGE_DOWN": "Page Down",
    "NUM_LOCK": "Num Lock", "CAPS_LOCK": "Caps Lock",
    "F1": "F1", "F2": "F2", "F3": "F3", "F4": "F4",
    "F5": "F5", "F6": "F6", "F7": "F7", "F8": "F8",
    "F9": "F9", "F10": "F10", "F11": "F11", "F12": "F12",
}

# Qt key code -> internal name
QT_SPECIAL_MAP = {
    Qt.Key.Key_Pause: "PAUSE", Qt.Key.Key_ScrollLock: "SCROLL_LOCK",
    Qt.Key.Key_Insert: "INSERT", Qt.Key.Key_Home: "HOME",
    Qt.Key.Key_End: "END", Qt.Key.Key_PageUp: "PAGE_UP",
    Qt.Key.Key_PageDown: "PAGE_DOWN", Qt.Key.Key_NumLock: "NUM_LOCK",
    Qt.Key.Key_CapsLock: "CAPS_LOCK",
    Qt.Key.Key_F1: "F1", Qt.Key.Key_F2: "F2", Qt.Key.Key_F3: "F3",
    Qt.Key.Key_F4: "F4", Qt.Key.Key_F5: "F5", Qt.Key.Key_F6: "F6",
    Qt.Key.Key_F7: "F7", Qt.Key.Key_F8: "F8", Qt.Key.Key_F9: "F9",
    Qt.Key.Key_F10: "F10", Qt.Key.Key_F11: "F11", Qt.Key.Key_F12: "F12",
}


class SpecialKeyCaptureButton(QPushButton):
    """Button that captures a special key (Pause, Scroll Lock, F-keys, etc.)."""
    key_captured = pyqtSignal(str)

    def __init__(self, key: str, parent=None):
        label = SPECIAL_KEY_LABELS.get(key.upper(), key)
        super().__init__(label, parent)
        self._listening = False
        self._current_key = key.upper()
        self.setFixedHeight(26)
        self.setMinimumWidth(80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style(False)
        self.clicked.connect(self._start_listening)

    def _apply_style(self, active: bool):
        if active:
            self.setStyleSheet("""
                QPushButton {
                    background: rgba(80,140,255,0.3);
                    border: 1px solid rgba(80,140,255,0.6);
                    border-radius: 4px;
                    color: rgba(255,255,255,0.95);
                    font-size: 11px; font-weight: bold;
                    padding: 0 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.10);
                    border: 1px solid rgba(255,255,255,0.18);
                    border-radius: 4px;
                    color: rgba(255,255,255,0.85);
                    font-size: 11px; font-weight: bold;
                    padding: 0 8px;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,0.16);
                    border: 1px solid rgba(255,255,255,0.30);
                }
            """)

    def _start_listening(self):
        self._listening = True
        self.setText("\u2026")
        self._apply_style(True)
        self.setFocus()

    def set_key(self, key: str):
        self._current_key = key.upper()
        self._listening = False
        self.setText(SPECIAL_KEY_LABELS.get(self._current_key, self._current_key))
        self._apply_style(False)

    def keyPressEvent(self, event):
        if self._listening:
            qt_key = event.key()
            name = QT_SPECIAL_MAP.get(qt_key)
            if name:
                self._current_key = name
                self._listening = False
                self.setText(SPECIAL_KEY_LABELS.get(name, name))
                self._apply_style(False)
                self.clearFocus()
                self.key_captured.emit(name)
                return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        if self._listening:
            self._listening = False
            self.setText(SPECIAL_KEY_LABELS.get(self._current_key, self._current_key))
            self._apply_style(False)
        super().focusOutEvent(event)


class SettingsPanel(QWidget):
    api_key_saved = pyqtSignal(str)
    theme_changed = pyqtSignal(str)
    shortcuts_changed = pyqtSignal(dict)

    TARGET_HEIGHT = 720
    MESSAGE_HEIGHT = 720

    def __init__(self, parent: QWidget, theme_name: str = "Midnight",
                 embedded: bool = False):
        super().__init__(parent)
        self._panel_height = 0
        self._anim = None
        self._fade_anim = None
        self._current_theme = theme_name
        self._embedded = embedded
        self._in_message_view = False
        self._full_history = []
        self.setFixedHeight(0)
        self._build_ui()

    @pyqtProperty(int)
    def panelHeight(self):
        return self._panel_height

    @panelHeight.setter
    def panelHeight(self, v):
        self._panel_height = v
        self.setFixedHeight(v)
        self.update()

    # ------------------------------------------------------------------ #
    #  UI construction
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ==================== MENU VIEW ====================
        self._menu_container = QWidget()
        ml = QVBoxLayout(self._menu_container)
        ml.setContentsMargins(16, 12, 16, 12)
        ml.setSpacing(7)

        # API Key
        label = QLabel("Chiave API OpenAI")
        label.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 13px;")
        ml.addWidget(label)

        key_layout = QHBoxLayout()
        key_layout.setSpacing(6)
        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("sk-...")
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 6px; color: #e0e0e0;
                padding: 7px 10px; font-size: 13px;
            }
            QLineEdit:focus { border: 1px solid rgba(255,255,255,0.3); }
        """)
        self._eye_btn = QPushButton("Mostra", self)
        self._eye_btn.setFixedSize(56, 30)
        self._eye_btn.setCheckable(True)
        self._eye_btn.toggled.connect(self._toggle_echo)
        self._eye_btn.setStyleSheet("""
            QPushButton { background: transparent; border: none;
                color: rgba(255,255,255,0.4); font-size: 11px; }
            QPushButton:hover { color: rgba(255,255,255,0.7); }
            QPushButton:checked { color: rgba(255,255,255,0.7); }
        """)
        key_layout.addWidget(self._key_input)
        key_layout.addWidget(self._eye_btn)
        ml.addLayout(key_layout)
        self._key_input.textChanged.connect(self._auto_save_key)

        # Theme (single row)
        theme_label = QLabel("Tema")
        theme_label.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 13px;")
        ml.addWidget(theme_label)
        theme_row = QHBoxLayout()
        theme_row.setSpacing(8)
        self._theme_btns = {}
        for name in THEME_ORDER:
            btn = QPushButton(self)
            btn.setFixedSize(24, 24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(name)
            is_sel = name == self._current_theme
            btn.setStyleSheet(self._theme_btn_style(THEME_PREVIEW[name], is_sel))
            btn.clicked.connect(lambda ch, n=name: self._select_theme(n))
            theme_row.addWidget(btn)
            self._theme_btns[name] = btn
        theme_row.addStretch()
        ml.addLayout(theme_row)

        # Options grid (2 columns)
        check_img = _create_check_icon_path()
        cb_style = f"""
            QCheckBox {{ color: rgba(255,255,255,0.6); font-size: 12px; spacing: 6px; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid rgba(255,255,255,0.3);
                border-radius: 3px; background: rgba(255,255,255,0.06);
            }}
            QCheckBox::indicator:checked {{
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.5);
                image: url({check_img});
            }}
            QCheckBox::indicator:hover {{ border: 1px solid rgba(255,255,255,0.5); }}
        """

        from PyQt6.QtWidgets import QGridLayout
        opts_grid = QGridLayout()
        opts_grid.setSpacing(4)
        opts_grid.setColumnStretch(0, 1)
        opts_grid.setColumnStretch(1, 1)

        self._autostart_cb = QCheckBox("Avvio con Windows")
        self._autostart_cb.setChecked(self._is_autostart_enabled())
        self._autostart_cb.setStyleSheet(cb_style)
        self._autostart_cb.toggled.connect(self._toggle_autostart)
        opts_grid.addWidget(self._autostart_cb, 0, 0)

        self._pp_cb = QCheckBox("Correggi testo con AI")
        self._pp_cb.setChecked(load_post_processing())
        self._pp_cb.setStyleSheet(cb_style)
        self._pp_cb.toggled.connect(save_post_processing)
        opts_grid.addWidget(self._pp_cb, 0, 1)

        self._start_min_cb = QCheckBox("Avvia minimizzata")
        self._start_min_cb.setChecked(load_start_minimized())
        self._start_min_cb.setStyleSheet(cb_style)
        self._start_min_cb.toggled.connect(save_start_minimized)
        opts_grid.addWidget(self._start_min_cb, 1, 0)

        self._sound_cb = QCheckBox("Suono dopo incolla")
        self._sound_cb.setChecked(load_paste_sound())
        self._sound_cb.setStyleSheet(cb_style)
        self._sound_cb.toggled.connect(save_paste_sound)
        opts_grid.addWidget(self._sound_cb, 1, 1)

        self._autoupdate_cb = QCheckBox("Aggiornamento auto")
        self._autoupdate_cb.setChecked(load_auto_update())
        self._autoupdate_cb.setStyleSheet(cb_style)
        self._autoupdate_cb.toggled.connect(save_auto_update)
        opts_grid.addWidget(self._autoupdate_cb, 2, 0)

        ml.addLayout(opts_grid)

        # Separator
        ml.addSpacing(4)
        ml.addWidget(self._sep())

        # Update section
        self._build_update_section(ml)

        ml.addSpacing(4)
        ml.addWidget(self._sep())

        # Shortcuts section
        self._build_shortcuts_section(ml)

        ml.addSpacing(4)
        ml.addWidget(self._sep())

        # Cost chart
        cost_label = QLabel("Costi API")
        cost_label.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 13px;")
        ml.addWidget(cost_label)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)
        self._filter_btns = []
        for i, (name, days) in enumerate(CostChartWidget.FILTERS):
            btn = QPushButton(name)
            btn.setFixedHeight(24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._filter_btn_style(days == 7))
            btn.clicked.connect(
                lambda ch, d=days, idx=i: self._set_chart_filter(d, idx))
            filter_row.addWidget(btn)
            self._filter_btns.append(btn)
        filter_row.addStretch()
        self._total_label = QLabel("$0.0000")
        self._total_label.setStyleSheet(
            "color: rgba(255,255,255,0.55); font-size: 12px; font-weight: bold;")
        filter_row.addWidget(self._total_label)
        ml.addLayout(filter_row)

        self._chart = CostChartWidget(self)
        ml.addWidget(self._chart)

        ml.addWidget(self._sep())

        # History
        hist_header = QHBoxLayout()
        hist_header.setSpacing(8)
        hist_label = QLabel("Cronologia")
        hist_label.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 13px;")
        hist_header.addWidget(hist_label)
        hist_header.addStretch()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Cerca...")
        self._search_input.setFixedWidth(160)
        self._search_input.setFixedHeight(24)
        self._search_input.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 4px;
                color: rgba(255,255,255,0.85);
                font-size: 11px;
                padding: 0 8px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(80,140,255,0.5);
            }
        """)
        self._search_input.textChanged.connect(self._on_search_changed)
        hist_header.addWidget(self._search_input)
        ml.addLayout(hist_header)

        self._history_scroll = QScrollArea()
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setMaximumHeight(180)
        self._history_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._history_scroll.setStyleSheet(self._scroll_style())
        self._history_content = QWidget()
        self._history_content.setStyleSheet("background: transparent;")
        self._history_layout = QVBoxLayout(self._history_content)
        self._history_layout.setContentsMargins(0, 0, 4, 0)
        self._history_layout.setSpacing(5)
        self._history_layout.addStretch()
        self._history_scroll.setWidget(self._history_content)
        ml.addWidget(self._history_scroll, 1)

        root.addWidget(self._menu_container)

        # ==================== MESSAGE VIEW ====================
        self._message_container = QWidget()
        self._message_container.hide()
        mg = QVBoxLayout(self._message_container)
        mg.setContentsMargins(16, 12, 16, 12)
        mg.setSpacing(10)

        # Header: back + title + copy
        msg_header = QHBoxLayout()
        msg_header.setSpacing(8)

        self._back_btn = QPushButton()
        self._back_btn.setIcon(qta.icon('fa5s.arrow-left', color=ICON_COLOR))
        self._back_btn.setFixedSize(28, 28)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setToolTip("Indietro")
        self._back_btn.setStyleSheet("""
            QPushButton { background: transparent; border: none; }
            QPushButton:hover { background: rgba(255,255,255,0.1); border-radius: 6px; }
        """)
        self._back_btn.clicked.connect(self._close_message)
        msg_header.addWidget(self._back_btn)

        self._msg_title = QLabel("Trascrizione")
        self._msg_title.setStyleSheet(
            "color: rgba(255,255,255,0.55); font-size: 13px;")
        msg_header.addWidget(self._msg_title)
        msg_header.addStretch()

        self._msg_copy_btn = QPushButton()
        self._msg_copy_btn.setIcon(qta.icon('fa5s.copy', color=ICON_COLOR))
        self._msg_copy_btn.setFixedSize(28, 28)
        self._msg_copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._msg_copy_btn.setToolTip("Copia")
        self._msg_copy_btn.setStyleSheet("""
            QPushButton { background: transparent; border: none; }
            QPushButton:hover { background: rgba(255,255,255,0.1); border-radius: 6px; }
        """)
        msg_header.addWidget(self._msg_copy_btn)
        mg.addLayout(msg_header)

        mg.addWidget(self._sep())

        # Message text scroll
        self._msg_scroll = QScrollArea()
        self._msg_scroll.setWidgetResizable(True)
        self._msg_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._msg_scroll.setStyleSheet(self._scroll_style())

        self._msg_text_widget = QWidget()
        self._msg_text_widget.setStyleSheet("background: transparent;")
        msg_text_layout = QVBoxLayout(self._msg_text_widget)
        msg_text_layout.setContentsMargins(0, 0, 6, 0)

        self._msg_text_label = QLabel()
        self._msg_text_label.setWordWrap(True)
        self._msg_text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._msg_text_label.setStyleSheet(
            "color: rgba(255,255,255,0.85); font-size: 14px; "
            "line-height: 1.5; background: transparent;")
        msg_text_layout.addWidget(self._msg_text_label)
        msg_text_layout.addStretch()

        self._msg_scroll.setWidget(self._msg_text_widget)
        mg.addWidget(self._msg_scroll, 1)

        root.addWidget(self._message_container)

    # ---- helpers ----

    def _sep(self) -> QFrame:
        s = QFrame()
        s.setFixedHeight(1)
        s.setStyleSheet("background: rgba(255,255,255,0.08);")
        return s

    def _scroll_style(self) -> str:
        return """
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: rgba(255,255,255,0.03);
                width: 6px; border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.18);
                border-radius: 3px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """

    # ------------------------------------------------------------------ #
    #  Painting
    # ------------------------------------------------------------------ #

    def paintEvent(self, event):
        if self._embedded or self._panel_height <= 1:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(THEME_COLORS.get(self._current_theme, THEME_COLORS["Midnight"]))
        bg.setAlpha(235)
        p.setBrush(QBrush(bg))
        p.setPen(QPen(QColor(255, 255, 255, 45), 1.0))
        p.drawRoundedRect(self.rect(), 12, 12)
        p.end()

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def set_api_key(self, key: str):
        self._key_input.setText(key)

    def show_embedded(self):
        """Display at full height without animation (embedded mode)."""
        self._panel_height = self.TARGET_HEIGHT
        self.setFixedHeight(self.TARGET_HEIGHT)
        self.show()

    def slide_open(self):
        self.refresh_data()
        target = self.MESSAGE_HEIGHT if self._in_message_view else self.TARGET_HEIGHT
        self._run_anim(0, target, QEasingCurve.Type.OutCubic)

    def slide_close(self):
        if self._in_message_view:
            self._instant_close_message()
        self._run_anim(self._panel_height, 0, QEasingCurve.Type.InCubic)

    def refresh_data(self):
        self._full_history = load_history()
        self._chart.set_data(self._full_history)
        self._update_total()
        self._apply_search_filter()

    def _on_search_changed(self, text: str):
        self._apply_search_filter()

    def _apply_search_filter(self):
        query = self._search_input.text().strip().lower()
        if query:
            filtered = [e for e in self._full_history
                        if query in e.get("text", "").lower()]
        else:
            filtered = self._full_history
        self._populate_history(filtered)

    # ------------------------------------------------------------------ #
    #  Message view transitions
    # ------------------------------------------------------------------ #

    def _open_message(self, text: str, timestamp_str: str = ""):
        if self._in_message_view:
            return
        self._in_message_view = True
        self._msg_text_label.setText(text)
        self._msg_copy_btn.clicked.disconnect() if self._msg_copy_btn.receivers(
            self._msg_copy_btn.clicked) > 0 else None
        try:
            self._msg_copy_btn.clicked.disconnect()
        except TypeError:
            pass
        self._msg_copy_btn.clicked.connect(lambda: pyperclip.copy(text))

        if timestamp_str:
            self._msg_title.setText(f"Trascrizione \u00b7 {timestamp_str}")
        else:
            self._msg_title.setText("Trascrizione")

        # Fade out menu
        effect = QGraphicsOpacityEffect(self._menu_container)
        self._menu_container.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(150)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self._finish_open_message)
        self._fade_anim = anim
        anim.start()

    def _finish_open_message(self):
        self._menu_container.setGraphicsEffect(None)
        self._menu_container.hide()
        self._message_container.show()

        # Fade in message
        effect = QGraphicsOpacityEffect(self._message_container)
        self._message_container.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.finished.connect(
            lambda: self._message_container.setGraphicsEffect(None))
        self._fade_anim = anim
        anim.start()

    def _close_message(self):
        if not self._in_message_view:
            return
        self._in_message_view = False

        # Fade out message
        effect = QGraphicsOpacityEffect(self._message_container)
        self._message_container.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(150)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self._finish_close_message)
        self._fade_anim = anim
        anim.start()

    def _finish_close_message(self):
        self._message_container.setGraphicsEffect(None)
        self._message_container.hide()
        self._menu_container.show()

        effect = QGraphicsOpacityEffect(self._menu_container)
        self._menu_container.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.finished.connect(
            lambda: self._menu_container.setGraphicsEffect(None))
        self._fade_anim = anim
        anim.start()

    def _instant_close_message(self):
        """Reset to menu view without animation (used when closing panel)."""
        self._in_message_view = False
        self._message_container.setGraphicsEffect(None)
        self._message_container.hide()
        self._menu_container.setGraphicsEffect(None)
        self._menu_container.show()

    # ------------------------------------------------------------------ #
    #  Animation
    # ------------------------------------------------------------------ #

    def _run_anim(self, start: int, end: int, curve):
        if self._anim:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b"panelHeight")
        self._anim.setDuration(250)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setEasingCurve(curve)
        self._anim.start()

    # ------------------------------------------------------------------ #
    #  Key visibility
    # ------------------------------------------------------------------ #

    def _toggle_echo(self, checked: bool):
        if checked:
            self._key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self._eye_btn.setText("Nascondi")
        else:
            self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self._eye_btn.setText("Mostra")

    # ------------------------------------------------------------------ #
    #  Theme
    # ------------------------------------------------------------------ #

    def _theme_btn_style(self, color: QColor, selected: bool) -> str:
        r, g, b = color.red(), color.green(), color.blue()
        border = "2px solid rgba(255,255,255,0.8)" if selected else "2px solid transparent"
        return f"""
            QPushButton {{
                background: rgb({r},{g},{b});
                border: {border}; border-radius: 12px;
            }}
            QPushButton:hover {{ border: 2px solid rgba(255,255,255,0.5); }}
        """

    def _select_theme(self, name: str):
        self._current_theme = name
        for n, btn in self._theme_btns.items():
            btn.setStyleSheet(self._theme_btn_style(THEME_PREVIEW[n], n == name))
        self.theme_changed.emit(name)

    # ------------------------------------------------------------------ #
    #  Auto-save key
    # ------------------------------------------------------------------ #

    def _auto_save_key(self):
        key = self._key_input.text().strip()
        if key:
            save_api_key(key)
            self.api_key_saved.emit(key)

    # ------------------------------------------------------------------ #
    #  Auto-update
    # ------------------------------------------------------------------ #

    def _build_update_section(self, layout):
        update_label = QLabel(f"Aggiornamento  ·  v{APP_VERSION}")
        update_label.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 13px;")
        layout.addWidget(update_label)
        self._version_label = update_label

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._check_update_btn = QPushButton("Controlla aggiornamenti")
        self._check_update_btn.setFixedHeight(28)
        self._check_update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._check_update_btn.setStyleSheet("""
            QPushButton {
                background: rgba(80,140,255,0.2);
                border: 1px solid rgba(80,140,255,0.35);
                border-radius: 4px;
                color: rgba(255,255,255,0.85);
                font-size: 11px; padding: 0 12px;
            }
            QPushButton:hover {
                background: rgba(80,140,255,0.35);
                border: 1px solid rgba(80,140,255,0.5);
            }
            QPushButton:disabled {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.08);
                color: rgba(255,255,255,0.3);
            }
        """)
        self._check_update_btn.clicked.connect(self._check_for_updates)
        btn_row.addWidget(self._check_update_btn)

        self._update_status = QLabel("")
        self._update_status.setStyleSheet(
            "color: rgba(255,255,255,0.5); font-size: 11px;")
        btn_row.addWidget(self._update_status, 1)
        layout.addLayout(btn_row)

        # Download + install button (hidden by default)
        self._install_row = QHBoxLayout()
        self._install_row.setSpacing(8)

        self._install_btn = QPushButton("Scarica e installa")
        self._install_btn.setFixedHeight(28)
        self._install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._install_btn.setStyleSheet("""
            QPushButton {
                background: rgba(50,200,100,0.2);
                border: 1px solid rgba(50,200,100,0.4);
                border-radius: 4px;
                color: rgba(255,255,255,0.9);
                font-size: 11px; padding: 0 12px;
            }
            QPushButton:hover {
                background: rgba(50,200,100,0.35);
                border: 1px solid rgba(50,200,100,0.55);
            }
            QPushButton:disabled {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.08);
                color: rgba(255,255,255,0.3);
            }
        """)
        self._install_btn.clicked.connect(self._download_and_install)
        self._install_btn.hide()
        self._install_row.addWidget(self._install_btn)

        self._progress_label = QLabel("")
        self._progress_label.setStyleSheet(
            "color: rgba(255,255,255,0.5); font-size: 11px;")
        self._install_row.addWidget(self._progress_label, 1)
        layout.addLayout(self._install_row)

        self._update_checker = None
        self._update_downloader = None
        self._pending_download_url = ""
        self._pending_tag = ""

    def _check_for_updates(self):
        self._check_update_btn.setEnabled(False)
        self._update_status.setText("Controllo in corso...")
        self._update_status.setStyleSheet(
            "color: rgba(255,255,255,0.5); font-size: 11px;")
        self._install_btn.hide()

        self._update_checker = UpdateChecker(GITHUB_REPO, self)
        self._update_checker.update_available.connect(self._on_update_available)
        self._update_checker.no_update.connect(self._on_no_update)
        self._update_checker.error.connect(self._on_update_error)
        self._update_checker.start()

    def _on_update_available(self, tag, download_url, notes):
        self._check_update_btn.setEnabled(True)
        self._update_status.setText(f"Disponibile {tag}")
        self._update_status.setStyleSheet(
            "color: rgba(50,200,100,0.9); font-size: 11px;")
        self._pending_download_url = download_url
        self._pending_tag = tag
        self._install_btn.setText(f"Scarica e installa {tag}")
        self._install_btn.show()

    def _on_no_update(self):
        self._check_update_btn.setEnabled(True)
        self._update_status.setText("Sei aggiornato!")
        self._update_status.setStyleSheet(
            "color: rgba(50,200,100,0.9); font-size: 11px;")

    def _on_update_error(self, message):
        self._check_update_btn.setEnabled(True)
        self._update_status.setText(message)
        self._update_status.setStyleSheet(
            "color: rgba(255,100,100,0.8); font-size: 11px;")

    def _download_and_install(self):
        if not self._pending_download_url:
            return
        self._install_btn.setEnabled(False)
        self._progress_label.setText("Download 0%...")

        self._update_downloader = UpdateDownloader(
            self._pending_download_url, self)
        self._update_downloader.progress.connect(self._on_download_progress)
        self._update_downloader.finished.connect(self._on_download_finished)
        self._update_downloader.error.connect(self._on_download_error)
        self._update_downloader.start()

    def _on_download_progress(self, percent):
        self._progress_label.setText(f"Download {percent}%...")

    def _on_download_finished(self, temp_path):
        self._progress_label.setText("Installazione...")
        success = apply_update_and_restart(temp_path)
        if not success:
            self._progress_label.setText(
                "Aggiornamento manuale: non in modalità .exe")
            self._progress_label.setStyleSheet(
                "color: rgba(255,180,80,0.8); font-size: 11px;")
            self._install_btn.setEnabled(True)

    def _on_download_error(self, message):
        self._progress_label.setText(f"Errore: {message}")
        self._progress_label.setStyleSheet(
            "color: rgba(255,100,100,0.8); font-size: 11px;")
        self._install_btn.setEnabled(True)

    # ------------------------------------------------------------------ #
    #  Shortcuts
    # ------------------------------------------------------------------ #

    def _build_shortcuts_section(self, layout):
        shortcuts = load_shortcuts()

        sc_label = QLabel("Scorciatoie")
        sc_label.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 13px;")
        layout.addWidget(sc_label)

        check_img = _create_check_icon_path()
        self._shortcuts_cb = QCheckBox("Abilita scorciatoie globali")
        self._shortcuts_cb.setChecked(shortcuts.get("enabled", True))
        self._shortcuts_cb.setStyleSheet(f"""
            QCheckBox {{ color: rgba(255,255,255,0.6); font-size: 12px; spacing: 6px; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid rgba(255,255,255,0.3);
                border-radius: 3px; background: rgba(255,255,255,0.06);
            }}
            QCheckBox::indicator:checked {{
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.5);
                image: url({check_img});
            }}
            QCheckBox::indicator:hover {{ border: 1px solid rgba(255,255,255,0.5); }}
        """)
        self._shortcuts_cb.toggled.connect(self._on_shortcut_change)
        layout.addWidget(self._shortcuts_cb)

        # Mode selector: Toggle / Hold
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        ml_label = QLabel("Modalità")
        ml_label.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 12px;")
        mode_row.addWidget(ml_label)
        mode_row.addStretch()

        current_mode = shortcuts.get("mode", "toggle")

        self._mode_toggle_btn = QPushButton("Attiva / Disattiva")
        self._mode_toggle_btn.setFixedHeight(26)
        self._mode_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mode_toggle_btn.clicked.connect(lambda: self._set_shortcut_mode("toggle"))
        mode_row.addWidget(self._mode_toggle_btn)

        self._mode_hold_btn = QPushButton("Tieni premuto")
        self._mode_hold_btn.setFixedHeight(26)
        self._mode_hold_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mode_hold_btn.clicked.connect(lambda: self._set_shortcut_mode("hold"))
        mode_row.addWidget(self._mode_hold_btn)

        layout.addLayout(mode_row)

        mod_style = "color: rgba(255,255,255,0.45); font-size: 11px;"
        label_style = "color: rgba(255,255,255,0.7); font-size: 12px;"

        # --- Toggle mode rows ---
        self._toggle_rows_widget = QWidget()
        toggle_layout = QVBoxLayout(self._toggle_rows_widget)
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.setSpacing(4)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(6)
        tl = QLabel("Registra / Ferma")
        tl.setStyleSheet(label_style)
        toggle_row.addWidget(tl)
        toggle_row.addStretch()
        tm = QLabel("Shift + Alt +")
        tm.setStyleSheet(mod_style)
        toggle_row.addWidget(tm)
        self._toggle_key_btn = KeyCaptureButton(
            shortcuts.get("toggle_key", "U"), self)
        self._toggle_key_btn.key_captured.connect(self._on_shortcut_change)
        toggle_row.addWidget(self._toggle_key_btn)
        toggle_layout.addLayout(toggle_row)

        discard_row = QHBoxLayout()
        discard_row.setSpacing(6)
        dl = QLabel("Elimina registrazione")
        dl.setStyleSheet(label_style)
        discard_row.addWidget(dl)
        discard_row.addStretch()
        dm = QLabel("Shift + Alt +")
        dm.setStyleSheet(mod_style)
        discard_row.addWidget(dm)
        self._discard_key_btn = KeyCaptureButton(
            shortcuts.get("discard_key", "I"), self)
        self._discard_key_btn.key_captured.connect(self._on_shortcut_change)
        discard_row.addWidget(self._discard_key_btn)
        toggle_layout.addLayout(discard_row)

        layout.addWidget(self._toggle_rows_widget)

        # --- Hold mode rows ---
        self._hold_rows_widget = QWidget()
        hold_layout = QVBoxLayout(self._hold_rows_widget)
        hold_layout.setContentsMargins(0, 0, 0, 0)
        hold_layout.setSpacing(4)

        hold_rec_row = QHBoxLayout()
        hold_rec_row.setSpacing(6)
        hrl = QLabel("Tieni premuto per registrare")
        hrl.setStyleSheet(label_style)
        hold_rec_row.addWidget(hrl)
        hold_rec_row.addStretch()
        self._hold_record_btn = SpecialKeyCaptureButton(
            shortcuts.get("hold_record_key", "PAUSE"), self)
        self._hold_record_btn.key_captured.connect(self._on_shortcut_change)
        hold_rec_row.addWidget(self._hold_record_btn)
        hold_layout.addLayout(hold_rec_row)

        hold_dis_row = QHBoxLayout()
        hold_dis_row.setSpacing(6)
        hdl = QLabel("Elimina registrazione")
        hdl.setStyleSheet(label_style)
        hold_dis_row.addWidget(hdl)
        hold_dis_row.addStretch()
        self._hold_discard_btn = SpecialKeyCaptureButton(
            shortcuts.get("hold_discard_key", "SCROLL_LOCK"), self)
        self._hold_discard_btn.key_captured.connect(self._on_shortcut_change)
        hold_dis_row.addWidget(self._hold_discard_btn)
        hold_layout.addLayout(hold_dis_row)

        layout.addWidget(self._hold_rows_widget)

        self._current_mode = current_mode
        self._apply_mode_ui(current_mode)

    def _mode_btn_style(self, active: bool) -> str:
        if active:
            return """
                QPushButton {
                    background: rgba(80,140,255,0.25);
                    border: 1px solid rgba(80,140,255,0.45);
                    border-radius: 4px;
                    color: rgba(255,255,255,0.9);
                    font-size: 11px; padding: 2px 10px;
                }
            """
        return """
            QPushButton {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 4px;
                color: rgba(255,255,255,0.55);
                font-size: 11px; padding: 2px 10px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.12);
                color: rgba(255,255,255,0.85);
            }
        """

    def _apply_mode_ui(self, mode: str):
        self._mode_toggle_btn.setStyleSheet(self._mode_btn_style(mode == "toggle"))
        self._mode_hold_btn.setStyleSheet(self._mode_btn_style(mode == "hold"))
        self._toggle_rows_widget.setVisible(mode == "toggle")
        self._hold_rows_widget.setVisible(mode == "hold")

    def _set_shortcut_mode(self, mode: str):
        self._current_mode = mode
        self._apply_mode_ui(mode)
        self._on_shortcut_change()

    def _on_shortcut_change(self, _=None):
        shortcuts = {
            "enabled": self._shortcuts_cb.isChecked(),
            "mode": self._current_mode,
            "toggle_key": self._toggle_key_btn._current_key,
            "discard_key": self._discard_key_btn._current_key,
            "hold_record_key": self._hold_record_btn._current_key,
            "hold_discard_key": self._hold_discard_btn._current_key,
        }
        save_shortcuts(shortcuts)
        self.shortcuts_changed.emit(shortcuts)

    # ------------------------------------------------------------------ #
    #  Chart filter + total
    # ------------------------------------------------------------------ #

    def _filter_btn_style(self, active: bool) -> str:
        if active:
            return """
                QPushButton {
                    background: rgba(80,140,255,0.25);
                    border: 1px solid rgba(80,140,255,0.45);
                    border-radius: 4px;
                    color: rgba(255,255,255,0.9);
                    font-size: 11px; padding: 2px 8px;
                }
            """
        return """
            QPushButton {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 4px;
                color: rgba(255,255,255,0.55);
                font-size: 11px; padding: 2px 8px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.12);
                color: rgba(255,255,255,0.85);
            }
        """

    def _set_chart_filter(self, days: int, btn_idx: int):
        self._chart.set_filter(days)
        for i, btn in enumerate(self._filter_btns):
            btn.setStyleSheet(self._filter_btn_style(i == btn_idx))
        self._update_total()

    def _update_total(self):
        self._total_label.setText(f"${self._chart.get_period_total():.4f}")

    # ------------------------------------------------------------------ #
    #  History list
    # ------------------------------------------------------------------ #

    def _populate_history(self, history: list):
        while self._history_layout.count() > 1:
            item = self._history_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for entry in reversed(history[-100:]):
            widget = self._create_history_item(entry)
            self._history_layout.insertWidget(
                self._history_layout.count() - 1, widget)

    def _create_history_item(self, entry: dict) -> QWidget:
        full_text = entry.get("text", "")
        item = QWidget()
        item.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.035);
                border-radius: 6px;
            }
        """)
        lay = QVBoxLayout(item)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(6)
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            time_str = ts.strftime("%d/%m/%Y %H:%M")
        except (KeyError, ValueError):
            time_str = "?"
        dur = entry.get("duration", 0)
        meta_lbl = QLabel(f"{time_str}  \u00b7  {dur:.0f}s")
        meta_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.45); font-size: 11px; background: transparent;")
        top.addWidget(meta_lbl)
        top.addStretch()

        copy_btn = QPushButton()
        copy_btn.setIcon(qta.icon('fa5s.copy', color=ICON_COLOR))
        copy_btn.setFixedSize(24, 24)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setToolTip("Copia")
        copy_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; }"
            "QPushButton:hover { background: rgba(255,255,255,0.1); border-radius: 4px; }")
        copy_btn.clicked.connect(lambda ch, t=full_text: pyperclip.copy(t))
        top.addWidget(copy_btn)

        open_btn = QPushButton()
        open_btn.setIcon(qta.icon('fa5s.expand', color=ICON_COLOR))
        open_btn.setFixedSize(24, 24)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setToolTip("Apri")
        open_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; }"
            "QPushButton:hover { background: rgba(255,255,255,0.1); border-radius: 4px; }")
        open_btn.clicked.connect(
            lambda ch, t=full_text, ts=time_str: self._open_message(t, ts))
        top.addWidget(open_btn)
        lay.addLayout(top)

        text = full_text
        if len(text) > 120:
            text = text[:120] + "..."
        txt_lbl = QLabel(text)
        txt_lbl.setWordWrap(True)
        txt_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.75); font-size: 13px; background: transparent;")
        lay.addWidget(txt_lbl)
        return item

    # ------------------------------------------------------------------ #
    #  Auto-start (Windows Registry)
    # ------------------------------------------------------------------ #

    _REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    _APP_NAME = "WhisperFloat"

    def _get_exe_path(self) -> str:
        if getattr(sys, 'frozen', False):
            return sys.executable
        script = os.path.abspath(sys.argv[0])
        return f'"{sys.executable}" "{script}"'

    def _is_autostart_enabled(self) -> bool:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self._REG_KEY, 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, self._APP_NAME)
            winreg.CloseKey(key)
            return True
        except (FileNotFoundError, OSError):
            return False

    def _toggle_autostart(self, enabled: bool):
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self._REG_KEY, 0, winreg.KEY_SET_VALUE)
            if enabled:
                winreg.SetValueEx(
                    key, self._APP_NAME, 0, winreg.REG_SZ, self._get_exe_path())
            else:
                try:
                    winreg.DeleteValue(key, self._APP_NAME)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except OSError:
            self._autostart_cb.setChecked(not enabled)
