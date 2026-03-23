# Whisper — Voice-to-Text Desktop App

Clone di Whisper Flow costruito con PyQt6. Registra audio dal microfono, trascrive tramite OpenAI Whisper API e incolla automaticamente il testo nella finestra precedente.

---

## Stack tecnologico

- **UI**: PyQt6 (widget frameless, custom painting, animazioni)
- **Audio**: sounddevice + numpy (cattura real-time 16kHz mono PCM)
- **Trascrizione**: OpenAI API (modello whisper-1)
- **Hotkey globali**: pynput (listener keyboard in background thread)
- **Auto-paste**: ctypes (Windows API) + pyautogui (Ctrl+V)
- **Clipboard**: pyperclip
- **Icone**: qtawesome (Font Awesome)
- **Build**: PyInstaller → .exe singolo
- **Piattaforma**: Windows (usa ctypes.windll, Windows Registry, pyautogui)

---

## Struttura del progetto

```
Whisper/
├── main.py                  # Entry point, setup QApplication e icona
├── build.bat                # Script build PyInstaller
├── requirements.txt         # Dipendenze Python
├── assets/
│   ├── icon.ico             # Icona app (Windows)
│   └── icon.png             # Icona app (alta qualità)
├── core/
│   ├── recorder.py          # AudioRecorder (QThread) — cattura audio
│   └── transcriber.py       # TranscriberWorker (QThread) — OpenAI API
├── ui/
│   ├── pill_widget.py       # Widget principale (pill + state machine)
│   ├── compact_pill.py      # Mini pill per modalità minimizzata
│   ├── settings_panel.py    # Pannello impostazioni (slide-in)
│   ├── toast_widget.py      # Notifica toast per errori paste
│   └── animations.py        # Factory animazioni (success sweep, error flash)
└── utils/
    ├── config.py            # Persistenza config/history (JSON in %APPDATA%)
    └── hotkeys.py           # HotkeyManager — shortcut globali con pynput
```

---

## Macchina a stati

L'app opera come una state machine a 4 stati:

```
IDLE → RECORDING → TRANSCRIBING → SUCCESS → IDLE
                 ↘ DISCARD → IDLE
```

| Stato | Cosa succede | Visuale |
|-------|-------------|---------|
| **IDLE** | In attesa di input | 5 barrette animate (breathing sinusoidale) |
| **RECORDING** | Cattura audio in corso | Timer MM:SS rosso + waveform reattiva alla voce + pulsazione rossa |
| **TRANSCRIBING** | Audio inviato a OpenAI | 5 barrette animate veloci blu + inner edge glow pulsante |
| **SUCCESS** | Testo trascritto e incollato | Sweep gradient verde da sinistra a destra + bordo verde |

---

## Pill Widget principale (`ui/pill_widget.py`)

Finestra frameless 280×80px, always-on-top, sfondo trasparente con angoli arrotondati (18px radius).

### Layout

```
┌──────────────────────────────────┐
│ Whisper                    ⚙ — × │  ← header (30px)
│        [contenuto animato]    🗑 │  ← area contenuto
└──────────────────────────────────┘
```

- **×** chiude l'app
- **—** minimizza nella taskbar
- **⚙** apre/chiude il pannello impostazioni
- **🗑** elimina la registrazione (visibile solo durante recording)

### Interazione mouse

- **Click sulla pill** → toggle recording (start/stop)
- **Drag sulla pill** → sposta la finestra (threshold 5px per distinguere da click)
- Click sui bottoni → azioni specifiche

### Tracking del focus

Un `QTimer` ogni 300ms chiama `GetForegroundWindow()` via ctypes per tracciare l'ultima finestra esterna attiva. Quando la registrazione inizia, l'hwnd viene salvato in `_previous_hwnd` per il paste successivo.

### Temi

7 temi colore disponibili, ognuno definisce il colore di sfondo della pill:

- Midnight (20, 20, 30)
- Viola (26, 16, 36)
- Bordeaux (34, 16, 22)
- Ambra (28, 22, 14)
- Ardesia (24, 24, 24)
- Foresta (16, 28, 20)
- Oceano (16, 24, 32)

---

## Compact Pill (`ui/compact_pill.py`)

Widget minimale 180×44px che compare centrato sopra la taskbar quando l'app è minimizzata e si usa una hotkey.

### Caratteristiche

- Frameless, always-on-top, `Tool` flag (non appare nella taskbar)
- `WindowDoesNotAcceptFocus` + `WA_ShowWithoutActivating` → non ruba il focus
- Posizionata: centro schermo, 8px sopra il bordo inferiore dell'area disponibile

### Stati supportati

- **Recording**: timer + waveform reattiva (identica alla pill principale)
- **Transcribing**: 5 barrette animate blu + inner edge glow
- **Success**: sweep gradient verde, poi auto-hide dopo 1.4s con emissione segnale `closed`

### Sincronizzazione con la pill principale

Gestita tramite `changeEvent` nella PillWidget:

- **Minimize** → se in recording/transcribing, la compact pill appare con stato e dati sincronizzati (timer, waveform history, amplitude)
- **Restore** → la compact pill sparisce, la pill principale mostra lo stato corrente con tutti i controlli (cestino ecc.)
- La connessione `amplitude` del recorder viene collegata/scollegata dinamicamente

---

## Scorciatoie globali (`utils/hotkeys.py`)

### HotkeyManager

Usa `pynput.keyboard.Listener` in un thread daemon. Traccia lo stato di Shift e Alt, e quando rileva Shift+Alt+tasto emette segnali Qt.

- **Shift + Alt + K** (default): toggle recording (start/stop)
- **Shift + Alt + X** (default): elimina registrazione

I segnali (`toggle_triggered`, `discard_triggered`) sono thread-safe grazie al meccanismo `AutoConnection` di Qt che fa queue automatico quando emessi da un thread non-Qt.

### Comportamento hotkey

- **App minimizzata + toggle**: avvia compact pill + recording
- **App minimizzata + toggle di nuovo**: compact pill → transcribing → success → si chiude
- **App visibile + toggle**: identico al click sulla pill
- **Discard**: elimina registrazione sia in compact che in normal mode
- **Durante transcribing/success**: toggle ignorato

### Configurazione

I tasti sono configurabili dal pannello impostazioni. Il modificatore Shift+Alt è fisso, l'utente sceglie solo la lettera finale tramite un `KeyCaptureButton` (click → "..." → premi tasto → salvato).

---

## Registrazione audio (`core/recorder.py`)

### AudioRecorder (QThread)

- **Sample rate**: 16000 Hz
- **Canali**: 1 (mono)
- **Formato**: int16 (16-bit PCM)
- **Block size**: 1024 campioni per callback

### Amplitude real-time

Ogni callback audio:
1. Divide il chunk in 5 segmenti
2. Calcola RMS per ogni segmento
3. Scala a 0.0–1.0 (con fattore ×12)
4. Emette via segnale `amplitude` → usato per waveform reattiva

### Salvataggio

Audio concatenato e salvato come WAV temporaneo (`tempfile.mkstemp`), passato al transcriber, poi eliminato.

---

## Trascrizione (`core/transcriber.py`)

### TranscriberWorker (QThread)

- Crea client OpenAI con la API key
- Invia il WAV al modello `whisper-1` con `response_format="text"`
- Emette `finished(text)` o `error(message)`
- Elimina il file WAV temporaneo in entrambi i casi

---

## Auto-paste

### Flusso

1. `pyperclip.copy(text)` — testo in clipboard
2. `SetForegroundWindow(hwnd)` — focus alla finestra precedente (con `AttachThreadInput` per cross-thread)
3. `pyautogui.hotkey('ctrl', 'v')` — simula Ctrl+V dopo 100ms di delay

### Gestione errori

- Se `_previous_hwnd` è None → toast
- Se `IsWindow(hwnd)` fallisce → toast
- Se `SetForegroundWindow` lancia eccezione → fallback diretto, poi toast se anche quello fallisce
- Toast posizionato: sopra la compact pill (se minimizzato) o sotto la pill principale (se visibile)

---

## Toast Widget (`ui/toast_widget.py`)

Notifica compatta near-taskbar per comunicare errori di paste.

- Messaggio: "Incolla non riuscito — testo negli appunti"
- Fade-in 200ms, visibile 3s, fade-out 400ms
- Posizionamento adattivo: sopra compact pill, sotto pill principale, o centrato in basso
- Stesso tema dell'app
- Si chiude automaticamente quando la compact pill completa il success

---

## Pannello impostazioni (`ui/settings_panel.py`)

Slide-in/out sotto la pill (250ms, cubic easing). Larghezza 440px.

### Sezioni

1. **Chiave API OpenAI** — campo password con toggle mostra/nascondi, auto-save
2. **Tema** — 7 cerchi colorati cliccabili
3. **Avvio automatico** — checkbox che scrive in `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`
4. **Scorciatoie** — checkbox abilita/disabilita + configurazione tasti (Shift+Alt+lettera)
5. **Costi API** — grafico a barre dei costi giornalieri ($0.006/min), filtri temporali (7gg, 30gg, 3 mesi, 1 anno, totale)
6. **Cronologia** — ultime 100 trascrizioni con timestamp, durata, costo, bottoni copia e espandi

### Vista messaggio

Cliccando "espandi" su una trascrizione, il pannello fa un crossfade alla vista messaggio completa con bottone indietro e copia.

---

## Persistenza (`utils/config.py`)

### File

- `%APPDATA%\Whisper\config.json` — API key, tema, scorciatoie
- `%APPDATA%\Whisper\history.json` — array di trascrizioni

### Formato config

```json
{
  "openai_api_key": "sk-...",
  "theme": "Midnight",
  "shortcuts": {
    "enabled": true,
    "toggle_key": "K",
    "discard_key": "X"
  }
}
```

### Formato history entry

```json
{
  "text": "testo trascritto",
  "timestamp": "2026-03-24T14:30:00+01:00",
  "duration": 5.2,
  "cost": 0.00052
}
```

- Timezone: Europe/Rome (hardcoded)
- Costo: $0.006 per minuto di audio

---

## Animazioni

| Animazione | Durata | Descrizione |
|-----------|--------|-------------|
| **Startup glow** | 1800ms | Alone blu esterno, opacity 0→140→80→0 |
| **Idle breathing** | Continua | 5 barrette sinusoidali, altezza 3–7px |
| **Recording waveform** | Real-time | Barrette rosse scrollanti destra→sinistra, altezza da amplitude |
| **Recording pulse** | Continua | Glow rosso sinusoidale (max alpha 25) |
| **Transcribing bars** | Continua | 5 barrette sinusoidali veloci (×3.5), blu |
| **Transcribing glow** | Continua | Inner edge glow 4 direzioni, pulsante |
| **Transcribing pulse** | Continua | Glow blu sinusoidale (max alpha 30) |
| **Success sweep** | 1400ms | Gradient verde che scorre sinistra→destra + bordo verde, fade out |
| **Error flash** | 600ms | Bordo rosso, opacity 0→200→0 |

### Implementazione

- Paint timer a 16ms (~60fps) guida `paintEvent`
- `QPropertyAnimation` per success e error (driven by opacity property)
- Pulse timers separati a 30ms per glow di sfondo
- Tutto il rendering è custom `QPainter` (no widget Qt standard per il contenuto)

---

## Build

```bash
pip install -r requirements.txt
pyinstaller build.spec --clean --noconfirm
# oppure
build.bat
```

Produce `dist/WhisperFloat.exe`.

---

## Setup sviluppo

```bash
cd Whisper
pip install -r requirements.txt
python main.py
```

Requisiti: Python 3.10+, Windows, microfono funzionante, chiave API OpenAI.
