from pynput import keyboard
from PyQt6.QtCore import QObject, pyqtSignal


class HotkeyManager(QObject):
    """Manages global keyboard shortcuts using pynput.

    Listens for Ctrl+Shift+<key> combinations and emits Qt signals.
    Signals are thread-safe (auto-queued to the main thread).
    """
    toggle_triggered = pyqtSignal()
    discard_triggered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._toggle_key = "k"
        self._discard_key = "x"
        self._enabled = True
        self._shift = False
        self._alt = False
        self._listener = None

    # -- public API --

    def start(self):
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    def set_toggle_key(self, key: str):
        self._toggle_key = key.lower()

    def set_discard_key(self, key: str):
        self._discard_key = key.lower()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    @property
    def toggle_key(self):
        return self._toggle_key

    @property
    def discard_key(self):
        return self._discard_key

    @property
    def enabled(self):
        return self._enabled

    # -- listener callbacks (run in pynput thread) --

    def _on_press(self, key):
        if not self._enabled:
            return
        if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            self._shift = True
            return
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
            self._alt = True
            return

        if not (self._shift and self._alt):
            return

        # Resolve virtual key code
        vk = getattr(key, "vk", None)
        if vk is None:
            char = getattr(key, "char", None)
            if char:
                vk = ord(char.upper())
        if vk is None:
            return

        if vk == ord(self._toggle_key.upper()):
            self.toggle_triggered.emit()
        elif vk == ord(self._discard_key.upper()):
            self.discard_triggered.emit()

    def _on_release(self, key):
        if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            self._shift = False
        elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
            self._alt = False
