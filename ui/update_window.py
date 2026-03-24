"""Update progress window — shown during auto-update download + install."""

from PyQt6.QtCore import Qt, QRectF, QTimer, pyqtProperty, QPropertyAnimation
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPainterPath
from PyQt6.QtWidgets import QWidget, QApplication


class UpdateWindow(QWidget):
    """Frameless overlay window that shows update download progress."""

    WIDTH = 320
    HEIGHT = 120
    RADIUS = 16
    SHADOW = 12

    def __init__(self, bg_color: QColor, parent=None):
        super().__init__(parent)
        self._bg_color = QColor(bg_color)
        self._title = "Aggiornamento in corso"
        self._status = "Download..."
        self._progress = 0
        self._opacity = 0.0
        self._pulse_phase = 0.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        total_w = self.WIDTH + 2 * self.SHADOW
        total_h = self.HEIGHT + 2 * self.SHADOW
        self.setFixedSize(total_w, total_h)

        self._fade_anim = None

        # Pulse timer for the progress bar glow
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick_pulse)
        self._pulse_timer.start(30)

    # -- animated properties --

    @pyqtProperty(float)
    def windowOpacity_(self):
        return self._opacity

    @windowOpacity_.setter
    def windowOpacity_(self, v):
        self._opacity = v
        self.update()

    # -- public API --

    def show_update(self, tag: str):
        self._title = f"Aggiornamento a {tag}"
        self._status = "Download..."
        self._progress = 0
        self._center_on_screen()
        self.show()
        self._fade_in()

    def set_progress(self, percent: int):
        self._progress = min(100, max(0, percent))
        self._status = f"Download {self._progress}%"
        self.update()

    def set_installing(self):
        self._progress = 100
        self._status = "Installazione..."
        self.update()

    def dismiss(self):
        if self._fade_anim:
            self._fade_anim.stop()
        anim = QPropertyAnimation(self, b"windowOpacity_")
        anim.setDuration(300)
        anim.setStartValue(self._opacity)
        anim.setEndValue(0.0)
        anim.finished.connect(self.hide)
        self._fade_anim = anim
        anim.start()

    def set_bg_color(self, color: QColor):
        self._bg_color = QColor(color)

    # -- internals --

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)

    def _fade_in(self):
        if self._fade_anim:
            self._fade_anim.stop()
        anim = QPropertyAnimation(self, b"windowOpacity_")
        anim.setDuration(300)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        self._fade_anim = anim
        anim.start()

    def _tick_pulse(self):
        self._pulse_phase += 0.05
        if self.isVisible() and self._opacity > 0.01:
            self.update()

    # -- painting --

    def paintEvent(self, event):
        if self._opacity <= 0.01:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)

        m = self.SHADOW
        rect = QRectF(m, m, self.WIDTH, self.HEIGHT)
        r = self.RADIUS

        # Shadow
        for i in range(m, 0, -2):
            alpha = max(0, 18 - i * 2)
            p.setBrush(QBrush(QColor(0, 0, 0, alpha)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect.adjusted(-i, -i, i, i), r + i, r + i)

        # Background
        bg = QColor(self._bg_color)
        bg.setAlpha(245)
        p.setBrush(QBrush(bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, r, r)

        # Border
        pen = QPen(QColor(255, 255, 255, 40))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, r, r)

        # Title
        title_rect = QRectF(rect.left() + 20, rect.top() + 16, rect.width() - 40, 24)
        font = QFont("Segoe UI", 12)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 200))
        p.drawText(title_rect,
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self._title)

        # Status text
        status_rect = QRectF(rect.left() + 20, rect.top() + 44, rect.width() - 40, 18)
        font2 = QFont("Segoe UI", 9)
        p.setFont(font2)
        p.setPen(QColor(255, 255, 255, 130))
        p.drawText(status_rect,
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self._status)

        # Progress bar background
        bar_x = rect.left() + 20
        bar_y = rect.top() + 72
        bar_w = rect.width() - 40
        bar_h = 6
        bar_rect = QRectF(bar_x, bar_y, bar_w, bar_h)
        bar_r = bar_h / 2

        p.setBrush(QBrush(QColor(255, 255, 255, 20)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(bar_rect, bar_r, bar_r)

        # Progress bar fill
        if self._progress > 0:
            fill_w = bar_w * self._progress / 100
            fill_rect = QRectF(bar_x, bar_y, fill_w, bar_h)

            # Clip to rounded rect
            clip = QPainterPath()
            clip.addRoundedRect(bar_rect, bar_r, bar_r)
            p.setClipPath(clip)

            # Green gradient fill
            p.setBrush(QBrush(QColor(50, 200, 100, 220)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(fill_rect)

            # Subtle glow on the fill
            import math
            glow_alpha = int(30 + 20 * math.sin(self._pulse_phase))
            p.setBrush(QBrush(QColor(50, 200, 100, glow_alpha)))
            p.drawRect(fill_rect)

            p.setClipping(False)

        # Percentage text
        pct_rect = QRectF(bar_x, bar_y + 12, bar_w, 16)
        font3 = QFont("Segoe UI", 8)
        p.setFont(font3)
        p.setPen(QColor(255, 255, 255, 90))
        p.drawText(pct_rect,
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   f"{self._progress}%")

        p.end()
