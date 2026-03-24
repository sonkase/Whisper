@echo off
echo Building WhisperFloat...
pyinstaller build.spec --clean --noconfirm
echo.
echo Build complete! Find WhisperFloat.exe in dist\
pause
