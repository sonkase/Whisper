import sys
import os

# Ensure project root is on the path (for PyInstaller and direct execution)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from utils.config import load_api_key, load_start_minimized
from ui.pill_widget import PillWidget


def resource_path(relative: str) -> str:
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Try PNG first (higher quality), fall back to ICO
    icon_path = resource_path(os.path.join("assets", "icon.png"))
    if not os.path.exists(icon_path):
        icon_path = resource_path(os.path.join("assets", "icon.ico"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Windows taskbar icon: set AppUserModelID so the taskbar uses our icon
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("whisper.float.app")
        except Exception:
            pass

    api_key = load_api_key()
    pill = PillWidget(api_key=api_key)
    if not load_start_minimized():
        pill.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
