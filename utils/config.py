import os
import sys
import json
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

IT_TZ = ZoneInfo("Europe/Rome")
WHISPER_COST_PER_MINUTE = 0.006


def _config_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~")
    folder = os.path.join(base, "Whisper")
    os.makedirs(folder, exist_ok=True)
    return folder


def _config_path() -> str:
    return os.path.join(_config_dir(), "config.json")


def _history_path() -> str:
    return os.path.join(_config_dir(), "history.json")


def _read_config() -> dict:
    path = _config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_config(data: dict):
    path = _config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_api_key() -> str:
    cfg = _read_config()
    return cfg.get("openai_api_key", "")


def save_api_key(key: str):
    cfg = _read_config()
    cfg["openai_api_key"] = key
    _write_config(cfg)


def load_theme() -> str:
    cfg = _read_config()
    return cfg.get("theme", "Midnight")


def save_theme(name: str):
    cfg = _read_config()
    cfg["theme"] = name
    _write_config(cfg)


def load_shortcuts() -> dict:
    cfg = _read_config()
    return cfg.get("shortcuts", {
        "enabled": True,
        "mode": "toggle",
        "toggle_key": "U",
        "discard_key": "I",
        "hold_record_key": "PAUSE",
        "hold_discard_key": "SCROLL_LOCK",
    })


def save_shortcuts(shortcuts: dict):
    cfg = _read_config()
    cfg["shortcuts"] = shortcuts
    _write_config(cfg)


def load_post_processing() -> bool:
    cfg = _read_config()
    return cfg.get("post_processing", True)


def save_post_processing(enabled: bool):
    cfg = _read_config()
    cfg["post_processing"] = enabled
    _write_config(cfg)


def load_paste_sound() -> bool:
    cfg = _read_config()
    return cfg.get("paste_sound", True)


def save_paste_sound(enabled: bool):
    cfg = _read_config()
    cfg["paste_sound"] = enabled
    _write_config(cfg)


# ------------------------------------------------------------------ #
#  History & cost tracking
# ------------------------------------------------------------------ #

def load_history() -> list:
    path = _history_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_transcription(text: str, duration_secs: float) -> float:
    """Save a transcription entry and return its cost."""
    cost = (duration_secs / 60.0) * WHISPER_COST_PER_MINUTE
    history = load_history()
    history.append({
        "text": text,
        "timestamp": datetime.now(IT_TZ).isoformat(),
        "duration": round(duration_secs, 1),
        "cost": round(cost, 6),
    })
    path = _history_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    return cost
