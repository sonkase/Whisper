"""Auto-update system — check GitHub releases, download, replace, relaunch."""

import json
import os
import sys
import tempfile
import subprocess
from urllib.request import urlopen, Request
from urllib.error import URLError

from PyQt6.QtCore import QThread, pyqtSignal

APP_VERSION = "1.2.10"
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

    Creates a PowerShell script that:
    1. Waits for the current process to fully exit
    2. Cleans stale _MEI dirs left by the old process
    3. Removes the internet Zone.Identifier from the new exe
    4. Replaces the old exe with the new one
    5. Relaunches via explorer.exe (mimics user double-click to avoid
       Windows Defender blocking extracted DLLs on first launch)
    6. Cleans up temp files
    """
    current_exe = _exe_path()

    if not getattr(sys, 'frozen', False):
        # Running as script — just inform the user
        return False

    pid = os.getpid()

    ps_fd, ps_path = tempfile.mkstemp(suffix=".ps1", prefix="whisper_updater_")
    ps_content = f'''
# 1. Wait for the old process to fully terminate
try {{
    $proc = Get-Process -Id {pid} -ErrorAction SilentlyContinue
    if ($proc) {{
        $proc.WaitForExit(30000)
    }}
}} catch {{}}
Start-Sleep -Seconds 2

# 2. Wait until the exe file handle is fully released
for ($i = 0; $i -lt 20; $i++) {{
    try {{
        $fs = [System.IO.File]::Open('{current_exe}', 'Open', 'ReadWrite', 'None')
        $fs.Close()
        break
    }} catch {{
        Start-Sleep -Milliseconds 500
    }}
}}

# 3. Clean stale _MEI directories BEFORE replacing the exe
#    (old process used os._exit so its _MEI was not cleaned up)
Get-ChildItem -Path $env:TEMP -Filter "_MEI*" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# 4. Remove internet Zone.Identifier from downloaded exe to prevent
#    Windows Defender from aggressively scanning extracted DLLs
Unblock-File -Path '{new_exe_path}' -ErrorAction SilentlyContinue

# 5. Rename old exe out of the way, then copy new one in
$oldBackup = '{current_exe}.old'
Remove-Item -Path $oldBackup -Force -ErrorAction SilentlyContinue
Rename-Item -Path '{current_exe}' -NewName $oldBackup -Force -ErrorAction SilentlyContinue
Copy-Item -Path '{new_exe_path}' -Destination '{current_exe}' -Force

# 6. Remove Zone.Identifier from the final exe path too
Unblock-File -Path '{current_exe}' -ErrorAction SilentlyContinue

# 7. Wait for filesystem to settle, then launch via explorer.exe
#    explorer.exe mimics a user double-click — same security context
#    that works when the user opens the exe manually
Start-Sleep -Seconds 2
Start-Process explorer.exe -ArgumentList '{current_exe}'

# 8. Cleanup temp files
Start-Sleep -Seconds 3
Remove-Item -Path $oldBackup -Force -ErrorAction SilentlyContinue
Remove-Item '{new_exe_path}' -ErrorAction SilentlyContinue
Remove-Item '{ps_path}' -ErrorAction SilentlyContinue
'''

    with os.fdopen(ps_fd, "w") as f:
        f.write(ps_content)

    subprocess.Popen(
        ["powershell.exe", "-ExecutionPolicy", "Bypass",
         "-WindowStyle", "Hidden", "-File", ps_path],
        creationflags=0x08000000,  # CREATE_NO_WINDOW
        close_fds=True,
    )

    # Force-kill the process immediately with os._exit().
    # QApplication.quit() triggers a graceful shutdown where PyInstaller's
    # atexit handler races to clean up _MEI — this can interfere with the
    # new process's extraction. os._exit() skips all cleanup, leaving the
    # _MEI dir for the PowerShell script to clean up safely.
    os._exit(0)
