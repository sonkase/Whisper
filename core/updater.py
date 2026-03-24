"""Auto-update system — check GitHub releases, download, replace, relaunch."""

import json
import os
import sys
import tempfile
import subprocess
from urllib.request import urlopen, Request
from urllib.error import URLError

from PyQt6.QtCore import QThread, pyqtSignal

APP_VERSION = "1.2.2"
GITHUB_REPO = "sonkase/Whisper"


def _exe_path() -> str:
    """Return the path of the running executable (PyInstaller or script)."""
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def _parse_version(tag: str) -> tuple:
    """Parse 'v1.2.3' or '1.2.3' into (1, 2, 3)."""
    tag = tag.lstrip("vV")
    parts = []
    for p in tag.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer(remote_tag: str, local_version: str = APP_VERSION) -> bool:
    return _parse_version(remote_tag) > _parse_version(local_version)


class UpdateChecker(QThread):
    """Check GitHub for a newer release.

    Signals:
        update_available(tag, download_url, release_notes)
        no_update()
        error(message)
    """

    update_available = pyqtSignal(str, str, str)  # tag, download_url, notes
    no_update = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, repo: str, parent=None):
        super().__init__(parent)
        self._repo = repo

    def run(self):
        if not self._repo:
            self.error.emit("Repository GitHub non configurato")
            return
        try:
            url = f"https://api.github.com/repos/{self._repo}/releases/latest"
            req = Request(url, headers={"Accept": "application/vnd.github+json"})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            tag = data.get("tag_name", "")
            if not tag:
                self.error.emit("Nessuna release trovata")
                return

            if not is_newer(tag):
                self.no_update.emit()
                return

            # Find .exe asset
            download_url = ""
            for asset in data.get("assets", []):
                name = asset.get("name", "").lower()
                if name.endswith(".exe"):
                    download_url = asset.get("browser_download_url", "")
                    break

            if not download_url:
                self.error.emit(f"Release {tag} trovata ma nessun .exe allegato")
                return

            notes = data.get("body", "") or ""
            self.update_available.emit(tag, download_url, notes)

        except URLError as e:
            self.error.emit(f"Errore di rete: {e.reason}")
        except Exception as e:
            self.error.emit(str(e))


class UpdateDownloader(QThread):
    """Download the new exe and prepare the swap.

    Signals:
        progress(percent)  — 0-100
        finished(temp_path) — path to downloaded exe
        error(message)
    """

    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, download_url: str, parent=None):
        super().__init__(parent)
        self._url = download_url

    def run(self):
        try:
            req = Request(self._url)
            with urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                fd, tmp_path = tempfile.mkstemp(suffix=".exe", prefix="whisper_update_")

                downloaded = 0
                with os.fdopen(fd, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            self.progress.emit(int(downloaded * 100 / total))

            self.progress.emit(100)
            self.finished.emit(tmp_path)

        except Exception as e:
            self.error.emit(str(e))


def apply_update_and_restart(new_exe_path: str):
    """Replace the current exe with the new one and relaunch.

    Creates a small batch script that:
    1. Waits for the current process to exit
    2. Replaces the old exe
    3. Launches the new exe
    4. Deletes itself
    """
    current_exe = _exe_path()

    if not getattr(sys, 'frozen', False):
        # Running as script — just inform the user
        return False

    pid = os.getpid()
    bat_content = f'''@echo off
:wait
tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    ping -n 2 127.0.0.1 >nul
    goto wait
)
ping -n 2 127.0.0.1 >nul
move /y "{new_exe_path}" "{current_exe}"
if errorlevel 1 (
    ping -n 3 127.0.0.1 >nul
    move /y "{new_exe_path}" "{current_exe}"
)
start "" "{current_exe}"
del "%~f0"
'''

    bat_fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="whisper_updater_")
    with os.fdopen(bat_fd, "w") as f:
        f.write(bat_content)

    # Use CREATE_NO_WINDOW to avoid terminal flash
    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen(
        ["cmd.exe", "/c", bat_path],
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
    )

    # Exit the app
    from PyQt6.QtWidgets import QApplication
    QApplication.quit()
    return True
