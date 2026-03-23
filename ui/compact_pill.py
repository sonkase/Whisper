import math
import time

from PyQt6.QtCore import Qt, QRectF, QTimer, pyqtSignal, pyqtProperty, QPropertyAnimation
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QLinearGradient, QPainterPath
from PyQt6.QtWidgets import QWidget, QApplication


class CompactPill(QWidget):
    """Minimal recording indicator shown near the taskbar when app is minimised.

    States: recording → transcribing → success → hidden
    """

    WIDTH = 180
    HEIGHT = 44
    RADIUS = 14
    MARGIN = 10
    WAVEFORM_MAX = 100

    closed = pyqtSignal()  # emitted when success animation ends

    def __init__(self, bg_color: QColor, parent=None):
        super().__init__(parent)
        self._bg_color = QColor(bg_color)
        self._state = "idle"  # idle | recording | transcribing | success
        self._recording_start = 0.0
        self._recording_elapsed = 0.0
        self._waveform_history: list[float] = []
        self._current_amplitude = 0.0
        self._pulse_phase = 0.0
        self._glow_opacity = 0
        self._success_glow_opacity = 0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        m = self.MARGIN
        self.setFixedSize(self.WIDTH + 2 * m, self.HEIGHT + 2 * m)

        self._paint_timer = QTimer(self)
        self._paint_timer.timeout.connect(self.update)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick_pulse)

        self._success_anim = None

    # ------------------------------------------------------------------ #
    #  Animated property for success glow
    # ------------------------------------------------------------------ #

    @pyqtProperty(int)
    def successGlowOpacity(self):
        return self._success_glow_opacity

    @successGlowOpacity.setter
    def successGlowOpacity(self, v):
        self._success_glow_opacity = v
        self.update()

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def start_recording(self):
        self._state = "recording"
        self._recording_start = time.time()
        self._recording_elapsed = 0.0
        self._waveform_history = []
        self._current_amplitude = 0.0
        self._pulse_phase = 0.0
        self._glow_opacity = 0
        self._success_glow_opacity = 0
        self._position_on_screen()
        self.show()
        self._paint_timer.start(16)
        self._pulse_timer.start(30)

    def enter_transcribing(self):
        """Switch to transcribing state (loading animation)."""
        self._state = "transcribing"
        self._recording_elapsed = time.time() - self._recording_start
        self._pulse_phase = 0.0

    def enter_success(self):
        """Flash green then auto-hide."""
        self._state = "success"
        self._pulse_timer.stop()
        self._glow_opacity = 0

        anim = QPropertyAnimation(self, b"successGlowOpacity")
        anim.setDuration(1400)
        anim.setStartValue(0)
        anim.setEndValue(255)
        anim.finished.connect(self._on_success_done)
        self._success_anim = anim
        anim.start()

    def stop(self):
        """Immediately hide (e.g. discard or error)."""
        self._state = "idle"
        self._paint_timer.stop()
        self._pulse_timer.stop()
        if self._success_anim:
            self._success_anim.stop()
            self._success_anim = None
        self.hide()

    def set_bg_color(self, color: QColor):
        self._bg_color = QColor(color)

    def on_amplitude(self, levels: list):
        if self._state != "recording":
            return
        avg = sum(levels) / len(levels) if levels else 0.0
        self._current_amplitude += (avg - self._current_amplitude) * 0.5
        self._waveform_history.append(self._current_amplitude)
        if len(self._waveform_history) > self.WAVEFORM_MAX:
            self._waveform_history = self._waveform_history[-self.WAVEFORM_MAX:]

    # ------------------------------------------------------------------ #
    #  Internals
    # ------------------------------------------------------------------ #

    def _position_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + geo.height() - self.height() - 8
            self.move(x, y)

    def _tick_pulse(self):
        self._pulse_phase += 0.08
        if self._state == "recording":
            self._glow_opacity = int(20 * (0.5 + 0.5 * math.sin(self._pulse_phase)))
        elif self._state == "transcribing":
            self._glow_opacity = int(25 * (0.5 + 0.5 * math.sin(self._pulse_phase)))

    def _on_success_done(self):
        self._success_anim = None
        self._paint_timer.stop()
        self.hide()
        self._state = "idle"
        self.closed.emit()

    # ------------------------------------------------------------------ #
    #  Painting
    # ------------------------------------------------------------------ #

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        m = self.MARGIN
        pill = QRectF(m, m, self.WIDTH, self.HEIGHT)
        r = self.RADIUS

        # Drop shadow
        for i in range(m, 0, -2):
            alpha = max(0, 18 - i * 2)
            p.setBrush(QBrush(QColor(0, 0, 0, alpha)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(pill.adjusted(-i, -i, i, i), r + i, r + i)

        # Background
        bg = QColor(self._bg_color)
        bg.setAlpha(230)
        p.setBrush(QBrush(bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(pill, r, r)

        # State glow fill
        if self._glow_opacity > 0:
            if self._state == "recording":
                glow = QColor(255, 60, 60, self._glow_opacity)
            elif self._state == "transcribing":
                glow = QColor(80, 120, 255, self._glow_opacity)
            else:
                glow = QColor(255, 255, 255, self._glow_opacity)
            p.setBrush(QBrush(glow))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(pill, r, r)

        # Inner edge glow during transcribing
        if self._state == "transcribing":
            self._paint_inner_glow(p, pill, r)

        # Success sweep glow
        if self._success_glow_opacity > 0:
            self._paint_success_sweep(p, pill, r)

        # Border
        pen = QPen(QColor(255, 255, 255, 40))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(pill, r, r)

        # ---- content (clipped) ----
        p.save()
        p.setClipRect(pill.toRect())

        if self._state == "recording":
            self._paint_recording(p, pill)
        elif self._state == "transcribing":
            self._paint_transcribing(p, pill)
        elif self._state == "success":
            pass  # just the green glow, no content

        p.restore()
        p.end()

    def _paint_inner_glow(self, p: QPainter, pill: QRectF, radius: float):
        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(pill, radius, radius)
        p.setClipPath(clip)
        p.setPen(Qt.PenStyle.NoPen)

        pulse = 0.5 + 0.5 * math.sin(time.time() * 2.5)
        base_alpha = int(45 + 30 * pulse)
        br, bg, bb = 45, 90, 220
        depth = 18.0

        for start_x, end_x, start_y, end_y, rect in [
            (pill.left(), pill.left() + depth, 0, 0,
             QRectF(pill.left(), pill.top(), depth, pill.height())),
            (pill.right(), pill.right() - depth, 0, 0,
             QRectF(pill.right() - depth, pill.top(), depth, pill.height())),
            (0, 0, pill.top(), pill.top() + depth,
             QRectF(pill.left(), pill.top(), pill.width(), depth)),
            (0, 0, pill.bottom(), pill.bottom() - depth,
             QRectF(pill.left(), pill.bottom() - depth, pill.width(), depth)),
        ]:
            if start_x != end_x:
                g = QLinearGradient(start_x, 0, end_x, 0)
            else:
                g = QLinearGradient(0, start_y, 0, end_y)
            g.setColorAt(0, QColor(br, bg, bb, base_alpha))
            g.setColorAt(1, QColor(br, bg, bb, 0))
            p.setBrush(QBrush(g))
            p.drawRect(rect)

        p.restore()

    def _paint_success_sweep(self, p: QPainter, pill: QRectF, radius: float):
        progress = self._success_glow_opacity / 255.0

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

        border_alpha = int(alpha * 0.7)
        if border_alpha > 0:
            pen = QPen(QColor(50, 200, 100, border_alpha))
            pen.setWidthF(1.5)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(pill, radius, radius)

    def _paint_recording(self, p: QPainter, pill: QRectF):
        cy = pill.center().y()

        # Timer text
        elapsed = time.time() - self._recording_start
        mins = int(elapsed) // 60
        secs = int(elapsed) % 60

        font = QFont("Segoe UI", 11)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor(255, 100, 100, 220))
        timer_rect = QRectF(pill.left() + 16, pill.top(), 50, pill.height())
        p.drawText(
            timer_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            f"{mins}:{secs:02d}",
        )

        # Waveform
        wave_left = pill.left() + 66
        wave_right = pill.right() - 14
        max_bars = int((wave_right - wave_left) / 3)
        samples = self._waveform_history[-max_bars:] if self._waveform_history else []

        bar_w = 2.0
        gap = 1.0
        max_h = pill.height() * 0.6

        p.setPen(Qt.PenStyle.NoPen)
        for i, amp in enumerate(reversed(samples)):
            x = wave_right - (i + 1) * (bar_w + gap)
            if x < wave_left:
                break
            h = max(2, amp * max_h)
            p.setBrush(QBrush(QColor(255, 90, 90, max(80, 255 - i * 2))))
            p.drawRoundedRect(QRectF(x, cy - h / 2, bar_w, h), 1, 1)

    def _paint_transcribing(self, p: QPainter, pill: QRectF):
        cy = pill.center().y()
        cx = pill.center().x()
        w = 50
        left = cx - w / 2

        p.setPen(Qt.PenStyle.NoPen)
        num = 5
        spacing = w / (num - 1)
        phase = time.time() * 3.5
        for i in range(num):
            pi = phase + i * 0.8
            h = 3 + 8 * abs(math.sin(pi))
            x = left + i * spacing
            bar = QRectF(x - 1.5, cy - h / 2, 3, h)
            alpha = 140 + int(60 * abs(math.sin(pi)))
            p.setBrush(QBrush(QColor(130, 150, 255, alpha)))
            p.drawRoundedRect(bar, 1.5, 1.5)
