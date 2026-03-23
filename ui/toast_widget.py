from PyQt6.QtCore import (
    Qt, QRectF, QTimer, QPropertyAnimation, QPoint, pyqtProperty,
)
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont
from PyQt6.QtWidgets import QWidget, QApplication


class ToastWidget(QWidget):
    """Small notification toast that appears near a reference widget."""

    HEIGHT = 36
    RADIUS = 10
    MARGIN = 8

    def __init__(self, bg_color: QColor, parent=None):
        super().__init__(parent)
        self._bg_color = QColor(bg_color)
        self._text = ""
        self._opacity = 0.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._fade_anim = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

    # -- animated property --

    @pyqtProperty(float)
    def toastOpacity(self):
        return self._opacity

    @toastOpacity.setter
    def toastOpacity(self, v):
        self._opacity = v
        self.update()

    # -- public API --

    def show_message(self, text: str, duration_ms: int = 3000,
                     avoid_widget: QWidget = None,
                     anchor_point: QPoint = None):
        """Show toast message.

        avoid_widget: position toast above this widget (for compact pill).
        anchor_point: position toast below this global point (for main pill).
        """
        self._text = text

        # Size based on text width
        font = QFont("Segoe UI", 10)
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(text) + 40
        m = self.MARGIN
        self.setFixedSize(text_w + 2 * m, self.HEIGHT + 2 * m)

        self._position(avoid_widget, anchor_point)
        self.show()
        self._fade_in()
        self._hide_timer.start(duration_ms)

    def dismiss(self):
        """Immediately hide without animation."""
        self._hide_timer.stop()
        if self._fade_anim:
            self._fade_anim.stop()
            self._fade_anim = None
        self._opacity = 0.0
        self.hide()

    def set_bg_color(self, color: QColor):
        self._bg_color = QColor(color)

    # -- internals --

    def _position(self, avoid_widget: QWidget = None,
                  anchor_point: QPoint = None):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2

        if avoid_widget and avoid_widget.isVisible():
            # Above the avoid widget with gap
            y = avoid_widget.y() - self.height() - 2
        elif anchor_point is not None:
            # Below the anchor point
            x = anchor_point.x() - self.width() // 2 + 140
            y = anchor_point.y()
        else:
            # Default: near bottom of screen
            y = geo.y() + geo.height() - self.height() - 12

        self.move(x, y)

    def _fade_in(self):
        if self._fade_anim:
            self._fade_anim.stop()
        anim = QPropertyAnimation(self, b"toastOpacity")
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        self._fade_anim = anim
        anim.start()

    def _fade_out(self):
        if self._fade_anim:
            self._fade_anim.stop()
        anim = QPropertyAnimation(self, b"toastOpacity")
        anim.setDuration(400)
        anim.setStartValue(self._opacity)
        anim.setEndValue(0.0)
        anim.finished.connect(self.hide)
        self._fade_anim = anim
        anim.start()

    # -- painting --

    def paintEvent(self, event):
        if self._opacity <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)

        m = self.MARGIN
        rect = QRectF(m, m, self.width() - 2 * m, self.HEIGHT)
        r = self.RADIUS

        # Subtle shadow
        for i in range(m, 0, -2):
            alpha = max(0, 14 - i * 2)
            p.setBrush(QBrush(QColor(0, 0, 0, alpha)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect.adjusted(-i, -i, i, i), r + i, r + i)

        # Background
        bg = QColor(self._bg_color)
        bg.setAlpha(235)
        p.setBrush(QBrush(bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, r, r)

        # Border
        pen = QPen(QColor(255, 255, 255, 35))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, r, r)

        # Text
        font = QFont("Segoe UI", 10)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 200))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._text)

        p.end()
