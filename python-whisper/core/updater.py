"""Auto-update system — check GitHub releases, download, replace, relaunch."""

import json
import os
import sys
import tempfile
import subprocess
from urllib.request import urlopen, Request
from urllib.error import URLError

from PyQt6.QtCore import QThread, pyqtSignal

APP_VERSION = "1.2.11"
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

    log_path = os.path.join(os.path.dirname(current_exe), "whisper_update.log")

    ps_fd, ps_path = tempfile.mkstemp(suffix=".ps1", prefix="whisper_updater_")
    ps_content = f'''
$logFile = '{log_path}'
function Log($msg) {{
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    "$ts  $msg" | Out-File -Append -FilePath $logFile -Encoding utf8
}}

Log "=== UPDATE START ==="
Log "Old exe: {current_exe}"
Log "New exe: {new_exe_path}"
Log "Old PID: {pid}"
Log "PS script: {ps_path}"

# 1. Wait for the old process to fully terminate
Log "Step 1: Waiting for PID {pid} to exit..."
try {{
    $proc = Get-Process -Id {pid} -ErrorAction SilentlyContinue
    if ($proc) {{
        $exited = $proc.WaitForExit(30000)
        Log "  WaitForExit returned: $exited"
    }} else {{
        Log "  Process already gone"
    }}
}} catch {{
    Log "  Exception: $_"
}}
Start-Sleep -Seconds 2
Log "  Process check after sleep: $(Get-Process -Id {pid} -ErrorAction SilentlyContinue)"

# 2. Wait until the exe file handle is fully released
Log "Step 2: Waiting for file handle release..."
$fileReleased = $false
for ($i = 0; $i -lt 20; $i++) {{
    try {{
        $fs = [System.IO.File]::Open('{current_exe}', 'Open', 'ReadWrite', 'None')
        $fs.Close()
        $fileReleased = $true
        Log "  File released after $i attempts"
        break
    }} catch {{
        if ($i % 5 -eq 0) {{ Log "  Attempt $i - still locked: $_" }}
        Start-Sleep -Milliseconds 500
    }}
}}
if (-not $fileReleased) {{ Log "  WARNING: File never released after 20 attempts" }}

# 3. Check _MEI directories before cleanup
$meiDirs = Get-ChildItem -Path $env:TEMP -Filter "_MEI*" -Directory -ErrorAction SilentlyContinue
Log "Step 3: Found $($meiDirs.Count) _MEI dirs: $($meiDirs.Name -join ', ')"
$meiDirs | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
$meiAfter = Get-ChildItem -Path $env:TEMP -Filter "_MEI*" -Directory -ErrorAction SilentlyContinue
Log "  After cleanup: $($meiAfter.Count) remaining: $($meiAfter.Name -join ', ')"
Start-Sleep -Milliseconds 500

# 4. Unblock downloaded exe
Log "Step 4: Unblock-File on new exe..."
Log "  New exe exists: $(Test-Path '{new_exe_path}')"
Log "  New exe size: $((Get-Item '{new_exe_path}' -ErrorAction SilentlyContinue).Length)"
$zone = Get-Content -Path '{new_exe_path}:Zone.Identifier' -ErrorAction SilentlyContinue
Log "  Zone.Identifier before: $zone"
Unblock-File -Path '{new_exe_path}' -ErrorAction SilentlyContinue
$zoneAfter = Get-Content -Path '{new_exe_path}:Zone.Identifier' -ErrorAction SilentlyContinue
Log "  Zone.Identifier after: $zoneAfter"

# 5. Rename old exe, copy new one in
Log "Step 5: Replacing exe..."
$oldBackup = '{current_exe}.old'
Remove-Item -Path $oldBackup -Force -ErrorAction SilentlyContinue
try {{
    Rename-Item -Path '{current_exe}' -NewName $oldBackup -Force -ErrorAction Stop
    Log "  Renamed old exe to .old"
}} catch {{
    Log "  ERROR renaming: $_"
}}
try {{
    Copy-Item -Path '{new_exe_path}' -Destination '{current_exe}' -Force -ErrorAction Stop
    Log "  Copied new exe in place"
}} catch {{
    Log "  ERROR copying: $_"
}}
Log "  Final exe exists: $(Test-Path '{current_exe}')"
Log "  Final exe size: $((Get-Item '{current_exe}' -ErrorAction SilentlyContinue).Length)"

# 6. Unblock final exe
Unblock-File -Path '{current_exe}' -ErrorAction SilentlyContinue
Log "Step 6: Unblocked final exe"

# 7. Check _MEI state right before launch
$meiBefore = Get-ChildItem -Path $env:TEMP -Filter "_MEI*" -Directory -ErrorAction SilentlyContinue
Log "Step 7: _MEI dirs before launch: $($meiBefore.Count) - $($meiBefore.Name -join ', ')"

# 8. Launch the new exe
Start-Sleep -Seconds 2
Log "Step 8: Launching exe..."
Log "  Method: Start-Process with exe path directly"
try {{
    $p = Start-Process -FilePath '{current_exe}' -PassThru -ErrorAction Stop
    Log "  Launched! New PID: $($p.Id)"
}} catch {{
    Log "  ERROR launching: $_"
    Log "  Trying fallback: cmd /c start..."
    try {{
        Start-Process cmd.exe -ArgumentList '/c', 'start', '""', '"{current_exe}"' -WindowStyle Hidden -ErrorAction Stop
        Log "  Fallback launch succeeded"
    }} catch {{
        Log "  FALLBACK ERROR: $_"
    }}
}}

# 9. Check if process is alive after a moment
Start-Sleep -Seconds 3
$meiAfterLaunch = Get-ChildItem -Path $env:TEMP -Filter "_MEI*" -Directory -ErrorAction SilentlyContinue
Log "Step 9: _MEI dirs after launch: $($meiAfterLaunch.Count) - $($meiAfterLaunch.Name -join ', ')"
$whisperProcs = Get-Process -Name "Whisper" -ErrorAction SilentlyContinue
Log "  Whisper processes running: $($whisperProcs.Count) - PIDs: $($whisperProcs.Id -join ', ')"

# 10. Cleanup
Log "Step 10: Cleanup..."
Remove-Item -Path $oldBackup -Force -ErrorAction SilentlyContinue
Remove-Item '{new_exe_path}' -ErrorAction SilentlyContinue
Log "=== UPDATE COMPLETE ==="
# Don't delete the PS script yet so log is fully written
Start-Sleep -Seconds 2
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
