from pynput import keyboard
from PyQt6.QtCore import QObject, pyqtSignal

# Map of special key names to pynput Key objects
SPECIAL_KEYS = {
    "PAUSE": keyboard.Key.pause,
    "SCROLL_LOCK": keyboard.Key.scroll_lock,
    "INSERT": keyboard.Key.insert,
    "HOME": keyboard.Key.home,
    "END": keyboard.Key.end,
    "PAGE_UP": keyboard.Key.page_up,
    "PAGE_DOWN": keyboard.Key.page_down,
    "NUM_LOCK": keyboard.Key.num_lock,
    "CAPS_LOCK": keyboard.Key.caps_lock,
    "F1": keyboard.Key.f1, "F2": keyboard.Key.f2, "F3": keyboard.Key.f3,
    "F4": keyboard.Key.f4, "F5": keyboard.Key.f5, "F6": keyboard.Key.f6,
    "F7": keyboard.Key.f7, "F8": keyboard.Key.f8, "F9": keyboard.Key.f9,
    "F10": keyboard.Key.f10, "F11": keyboard.Key.f11, "F12": keyboard.Key.f12,
}

# Reverse map: pynput Key object -> display name
KEY_TO_NAME = {v: k for k, v in SPECIAL_KEYS.items()}


class HotkeyManager(QObject):
    toggle_triggered = pyqtSignal()
    stop_triggered = pyqtSignal()     # for hold mode: key released
    discard_triggered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._toggle_key = "u"
        self._discard_key = "i"
        self._hold_record_key = "PAUSE"
        self._hold_discard_key = "SCROLL_LOCK"
        self._enabled = True
        self._mode = "toggle"  # "toggle" or "hold"
        self._shift = False
        self._alt = False
        self._holding = False
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

    def set_hold_record_key(self, key: str):
        self._hold_record_key = key.upper()

    def set_hold_discard_key(self, key: str):
        self._hold_discard_key = key.upper()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def set_mode(self, mode: str):
        self._mode = mode
        self._holding = False

    @property
    def toggle_key(self):
        return self._toggle_key

    @property
    def discard_key(self):
        return self._discard_key

    @property
    def enabled(self):
        return self._enabled

    @property
    def mode(self):
        return self._mode

    # -- internal --

    def _match_special(self, key, name: str) -> bool:
        target = SPECIAL_KEYS.get(name.upper())
        return target is not None and key == target

    def _on_press(self, key):
        if not self._enabled:
            return

        if self._mode == "hold":
            self._on_press_hold(key)
        else:
            self._on_press_toggle(key)

    def _on_release(self, key):
        if self._mode == "hold":
            self._on_release_hold(key)
        else:
            self._on_release_toggle(key)

    # -- toggle mode --

    def _on_press_toggle(self, key):
        if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            self._shift = True
            return
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
            self._alt = True
            return

        if not (self._shift and self._alt):
            return

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

    def _on_release_toggle(self, key):
        if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            self._shift = False
        elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
            self._alt = False

    # -- hold mode --

    def _on_press_hold(self, key):
        if self._match_special(key, self._hold_record_key):
            if not self._holding:
                self._holding = True
                self.toggle_triggered.emit()
            return

        if self._holding and self._match_special(key, self._hold_discard_key):
            self._holding = False
            self.discard_triggered.emit()

    def _on_release_hold(self, key):
        if self._match_special(key, self._hold_record_key):
            if self._holding:
                self._holding = False
                self.stop_triggered.emit()
