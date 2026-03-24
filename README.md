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

1. **Click the pill** (or press `Shift+Alt+U`) to start recording
2. **Click again** (or press the shortcut again) to stop
3. Audio is sent to OpenAI Whisper API for transcription
4. Text is **automatically corrected** by GPT-5-mini (grammar, punctuation, paragraphs)
5. Text is **automatically pasted** into the window you were using before

That's it. No extra steps.

## Features

- **Floating pill widget** — minimal, always-on-top, draggable
- **AI post-processing** — GPT-5-mini corrects grammar, punctuation, adds paragraphs, and fixes misheard words
- **Two shortcut modes** — Toggle (Shift+Alt+key) or Hold-to-record (push-to-talk with a single key like Pause)
- **Global keyboard shortcuts** — works even when minimized
- **Compact mode** — when minimized, a small indicator appears near the taskbar with red glow on start, recording waveform, and fade-out on completion
- **Auto-paste** — transcribed text is copied to clipboard and pasted into the previously focused window, with foreground verification
- **Sound notifications** — custom sounds for successful paste and paste errors, togglable in settings
- **Paste error detection** — verifies the target window is in foreground before pasting; shows a yellow-glow toast with error sound if it fails
- **Search history** — search bar to filter past transcriptions by text
- **7 color themes** — Midnight, Viola, Bordeaux, Ambra, Ardesia, Foresta, Oceano
- **Cost tracking** — bar chart of daily API costs with time filters
- **Transcription history** — browse, search, and copy past transcriptions
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

On first launch, open settings and enter your OpenAI API key.

### Build executable

```bash
build.bat
```

Produces `dist/WhisperFloat.exe`.

## Shortcuts

### Toggle mode (default)

| Action | Default shortcut |
|--------|-----------------|
| Start / Stop recording | `Shift + Alt + U` |
| Discard recording | `Shift + Alt + I` |

### Hold mode (push-to-talk)

| Action | Default key |
|--------|------------|
| Hold to record, release to transcribe | `Pause` |
| Discard while holding | `Scroll Lock` |

Shortcut mode and keys are configurable in the settings panel.

## Config

Settings are stored in `%APPDATA%\Whisper\config.json`. Transcription history in `%APPDATA%\Whisper\history.json`.

## Cost

Uses the OpenAI Whisper API at **$0.006 per minute** of audio. Post-processing with GPT-5-mini costs fractions of a cent per transcription.

## License

MIT
