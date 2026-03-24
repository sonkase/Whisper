import os
import sys
import threading
import ctypes

_VOLUME = 20  # percentage 0-100

_BASE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASSETS = os.path.join(_BASE, "assets")
_NOTIFY_FILE = os.path.join(_ASSETS, "notify.mp3")
_ERROR_FILE = os.path.join(_ASSETS, "error.mp3")

_mci = ctypes.windll.winmm.mciSendStringW


def _send_mci(command: str):
    buf = ctypes.create_unicode_buffer(256)
    _mci(command, buf, 256, 0)
    return buf.value


def set_volume(percent: int):
    global _VOLUME
    _VOLUME = max(0, min(100, percent))


_ERROR_VOLUME = 14  # percentage 0-100 (30% lower than notify)


def _play_sound(filepath: str, alias: str, volume: int = None):
    vol = volume if volume is not None else _VOLUME

    def _play():
        try:
            _send_mci(f"close {alias}")
            _send_mci(f'open "{filepath}" type mpegvideo alias {alias}')
            mci_vol = int(vol * 10)
            _send_mci(f"setaudio {alias} volume to {mci_vol}")
            _send_mci(f"play {alias}")
        except Exception:
            pass

    threading.Thread(target=_play, daemon=True).start()


def play_ding():
    _play_sound(_NOTIFY_FILE, "whisper_notify")


def play_error():
    _play_sound(_ERROR_FILE, "whisper_error", _ERROR_VOLUME)
