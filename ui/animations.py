from PyQt6.QtCore import QPropertyAnimation


def create_success_flash(target) -> QPropertyAnimation:
    """Success animation: drives successGlowOpacity 0→255 linearly.

    The paint code interprets this as a sweep progress, not a flat alpha.
    """
    anim = QPropertyAnimation(target, b"successGlowOpacity")
    anim.setDuration(1400)
    anim.setStartValue(0)
    anim.setEndValue(255)
    return anim


def create_error_flash(target) -> QPropertyAnimation:
    anim = QPropertyAnimation(target, b"errorFlashOpacity")
    anim.setDuration(600)
    anim.setKeyValueAt(0.0, 0)
    anim.setKeyValueAt(0.3, 200)
    anim.setKeyValueAt(1.0, 0)
    return anim
