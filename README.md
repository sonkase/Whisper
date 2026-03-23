<p align="center">
  <img src="assets/icon.png" width="100" alt="Whisper logo">
</p>

<h1 align="center">Whisper</h1>

<p align="center">
  Voice-to-text desktop app for Windows.<br>
  Record, transcribe, paste — in one click or shortcut.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/platform-Windows-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/UI-PyQt6-green" alt="PyQt6">
  <img src="https://img.shields.io/badge/API-OpenAI%20Whisper-orange" alt="OpenAI">
</p>

---

## How it works

1. **Click the pill** (or press `Shift+Alt+K`) to start recording
2. **Click again** (or press the shortcut again) to stop
3. Audio is sent to OpenAI Whisper API for transcription
4. Text is **automatically pasted** into the window you were using before

That's it. No extra steps.

## Features

- **Floating pill widget** — minimal, always-on-top, draggable
- **Global keyboard shortcuts** — works even when minimized (`Shift+Alt+K` to record, `Shift+Alt+X` to discard)
- **Compact mode** — when minimized, a small indicator appears near the taskbar showing recording time and waveform
- **Auto-paste** — transcribed text is copied to clipboard and pasted into the previously focused window
- **7 color themes** — Midnight, Viola, Bordeaux, Ambra, Ardesia, Foresta, Oceano
- **Cost tracking** — bar chart of daily API costs with time filters
- **Transcription history** — browse and copy past transcriptions
- **Auto-start** — optional Windows startup entry
- **Voice-reactive waveform** — real-time audio visualization during recording

## Setup

### Requirements

- Python 3.10+
- Windows 10/11
- OpenAI API key

### Install

```bash
git clone https://github.com/sonkase/Whisper.git
cd Whisper
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

On first launch, open settings (☰) and enter your OpenAI API key.

### Build executable

```bash
build.bat
```

Produces `dist/WhisperFloat.exe`.

## Shortcuts

| Action | Default shortcut |
|--------|-----------------|
| Start / Stop recording | `Shift + Alt + K` |
| Discard recording | `Shift + Alt + X` |

Shortcuts are configurable in the settings panel. The modifier `Shift+Alt` is fixed — you choose the final key.

## Config

Settings are stored in `%APPDATA%\Whisper\config.json`. Transcription history in `%APPDATA%\Whisper\history.json`.

## Cost

Uses the OpenAI Whisper API at **$0.006 per minute** of audio. A typical 10-second recording costs ~$0.001.

## License

MIT
