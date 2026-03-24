<p align="center">
  <img src="assets/icon.png" width="100" alt="Whisper logo">
</p>

<h1 align="center">Whisper</h1>

<p align="center">
  Voice-to-text desktop app for Windows.<br>
  Record, transcribe, paste — in one click or shortcut.
</p>

---

## How it works

1. **Click the pill** (or press `Shift+Alt+U`) to start recording
2. **Click again** (or press the shortcut again) to stop
3. Audio is sent to OpenAI Whisper API → corrected by GPT-5-mini
4. Text is **automatically pasted** into the window you were using before

## Setup

```bash
git clone https://github.com/sonkase/Whisper.git
cd Whisper
pip install -r requirements.txt
python main.py
```

Requires **Python 3.10+**, **Windows 10/11**, and an **OpenAI API key** (enter it in settings on first launch).

### Build executable

```bash
build.bat
```

## Shortcuts

**Toggle mode** (default): `Shift+Alt+U` start/stop, `Shift+Alt+I` discard.

**Hold mode** (push-to-talk): hold `Pause` to record, release to transcribe. `Scroll Lock` to discard.

Mode and keys are configurable in settings.

## System tray

The app lives in the system tray. Closing the window hides it to tray — double-click the tray icon to show it again, right-click to quit. By default, the app starts minimized to tray.

## Cost

OpenAI Whisper API: **$0.006/min**. GPT-5-mini post-processing: fractions of a cent per transcription.

## License

MIT
