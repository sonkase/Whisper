<p align="center">
  <img src="assets/icon.png" width="100" alt="Whisper logo">
</p>

<h1 align="center">Whisper</h1>

<p align="center">
  Voice-to-text desktop app for Windows.<br>
  Speak. Transcribe. Paste. One click or one shortcut.
</p>

<p align="center">
  100% Free &middot; Open Source &middot; Pay only for API usage
</p>

---

## How it works

1. **Record** — Click the pill or press a shortcut. Speak freely.
2. **Transcribe** — Audio is sent to OpenAI Whisper API. GPT cleans up grammar and punctuation.
3. **Paste** — Text is automatically pasted into the window you were using. No manual copy-paste.

## Features

- **Always on top** — Compact pill-shaped UI that doesn't cover your work or steal focus
- **AI correction** — Adds punctuation, fixes typos, splits text into paragraphs
- **Global shortcuts** — Toggle mode (`Shift+Alt+U`) or hold-to-talk mode (`Pause` key), fully configurable
- **Auto-paste** — Transcribed text goes straight into your active window
- **Auto-update** — The app updates itself when a new version is available
- **System tray** — Lives in the tray, starts minimized, always ready
- **7 themes** — Midnight, Violet, Bordeaux, Amber, Slate, Forest, Ocean

## Download

Grab the latest `.exe` from [Releases](https://github.com/sonkase/Whisper/releases). No installation needed — just run it.

Requires **Windows 10/11** and an **OpenAI API key** (enter it in settings on first launch).

## Cost

Only raw OpenAI API costs: **$0.006/min** of audio. The app itself is free.

## Build from source

```bash
git clone https://github.com/sonkase/Whisper.git
cd Whisper
pip install -r requirements.txt
python main.py
```

Build a standalone `.exe`:

```bash
pyinstaller build.spec --clean --noconfirm
```

Requires Python 3.10+.

## License

MIT
