# Whisper — Voice-to-Text Desktop App

Clone di Whisper Flow costruito con PyQt6. Registra audio dal microfono, trascrive tramite OpenAI Whisper API, corregge con GPT-5-mini e incolla automaticamente il testo nella finestra precedente.

---

## Stack tecnologico

- **UI**: PyQt6 (widget frameless, custom painting, animazioni)
- **Audio**: sounddevice + numpy (cattura real-time 16kHz mono PCM)
- **Trascrizione**: OpenAI API (modello whisper-1, lingua italiana)
- **Post-processing**: OpenAI GPT-5-mini (correzione grammatica, punteggiatura, paragrafi, typo fonetici)
- **Hotkey globali**: pynput (listener keyboard in background thread)
- **Auto-paste**: ctypes (Windows API) + pyautogui (Ctrl+V) con verifica foreground
- **Clipboard**: pyperclip
- **Suoni**: Windows MCI (ctypes.windll.winmm) per riproduzione mp3
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
├── TODO.md                  # Implementazioni future
├── assets/
│   ├── icon.ico             # Icona app (Windows)
│   ├── icon.png             # Icona app (alta qualità)
│   ├── notify.mp3           # Suono notifica paste riuscito
│   └── error.mp3            # Suono notifica paste fallito
├── core/
│   ├── recorder.py          # AudioRecorder (QThread) — cattura audio
│   ├── transcriber.py       # TranscriberWorker (QThread) — OpenAI Whisper API
│   └── post_processor.py    # PostProcessorWorker (QThread) — GPT-5-mini correzione testo
├── ui/
│   ├── pill_widget.py       # Widget principale (pill + state machine)
│   ├── compact_pill.py      # Mini pill per modalità minimizzata
│   ├── settings_panel.py    # Pannello impostazioni (slide-in)
│   ├── toast_widget.py      # Notifica toast per errori paste (con glow giallo)
│   └── animations.py        # Factory animazioni (success sweep, error flash)
└── utils/
    ├── config.py            # Persistenza config/history (JSON in %APPDATA%)
    ├── hotkeys.py           # HotkeyManager — shortcut globali con pynput (toggle + hold mode)
    └── sound.py             # Riproduzione suoni notifica (MCI, volume configurabile)
```

---

## Macchina a stati

L'app opera come una state machine a 5 stati:

```
IDLE → RECORDING → TRANSCRIBING → SUCCESS → IDLE
                 ↘ DISCARD → IDLE
                                 ↘ ERROR → IDLE
```

| Stato | Cosa succede | Visuale |
|-------|-------------|---------|
| **IDLE** | In attesa di input | 5 barrette animate (breathing sinusoidale) |
| **RECORDING** | Cattura audio in corso | Timer MM:SS rosso + waveform reattiva alla voce + pulsazione rossa |
| **TRANSCRIBING** | Audio inviato a OpenAI + post-processing GPT | 5 barrette animate veloci blu + inner edge glow pulsante |
| **SUCCESS** | Testo trascritto e incollato | Sweep gradient verde da sinistra a destra + bordo verde |
| **ERROR** | Paste fallito | Toast con glow giallo + suono errore, blocca nuove registrazioni per 2.5s |

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

- **Recording**: timer + waveform reattiva (identica alla pill principale) + red glow iniziale (1s)
- **Transcribing**: 5 barrette animate blu + inner edge glow
- **Success**: sweep gradient verde (800ms), poi fade-out finestra (250ms)

### Sincronizzazione con la pill principale

Gestita tramite `changeEvent` nella PillWidget:

- **Minimize** → se in recording/transcribing, la compact pill appare con stato e dati sincronizzati (timer, waveform history, amplitude)
- **Restore** → la compact pill sparisce, la pill principale mostra lo stato corrente con tutti i controlli (cestino ecc.)
- La connessione `amplitude` del recorder viene collegata/scollegata dinamicamente
- In stato **error**, la compact pill resta visibile fino al termine del toast

---

## Scorciatoie globali (`utils/hotkeys.py`)

### HotkeyManager

Usa `pynput.keyboard.Listener` in un thread daemon. Supporta due modalità:

### Modalità Toggle (default)

- **Shift + Alt + U** (default): toggle recording (start/stop)
- **Shift + Alt + I** (default): elimina registrazione

### Modalità Hold (push-to-talk)

- **Pause** (default): tieni premuto per registrare, rilascia per trascrivere
- **Scroll Lock** (default): elimina registrazione mentre si tiene premuto il tasto di registrazione

I segnali (`toggle_triggered`, `stop_triggered`, `discard_triggered`) sono thread-safe grazie al meccanismo `AutoConnection` di Qt.

### Comportamento hotkey

- **App minimizzata + toggle**: avvia compact pill + recording
- **App minimizzata + toggle di nuovo**: compact pill → transcribing → success → fade-out
- **App visibile + toggle**: identico al click sulla pill
- **Discard**: elimina registrazione sia in compact che in normal mode
- **Durante transcribing/success/error**: toggle ignorato

### Configurazione

Due selettori nel pannello impostazioni per scegliere la modalità. In toggle mode, l'utente sceglie la lettera (Shift+Alt fisso). In hold mode, l'utente sceglie tasti speciali (Pause, Scroll Lock, F-keys, ecc.) tramite `SpecialKeyCaptureButton`.

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
- Invia il WAV al modello `whisper-1` con `response_format="text"` e `language="it"`
- Emette `finished(text)` o `error(message)`
- Elimina il file WAV temporaneo in entrambi i casi

---

## Post-processing (`core/post_processor.py`)

### PostProcessorWorker (QThread)

- Riceve il testo trascritto da Whisper
- Lo invia a GPT-5-mini con un system prompt che:
  - Corregge punteggiatura e grammatica
  - Divide in paragrafi logici con a-capo
  - Deduce dal suono le parole fraintese dal speech-to-text
  - Non aggiunge contenuto, non riassume, non riformula
- Emette `finished(text)` o `error(message)`
- In caso di errore, il pill_widget usa il testo raw di Whisper come fallback
- Abilitabile/disabilitabile da settings ("Correggi testo con AI")

---

## Auto-paste

### Flusso

1. `pyperclip.copy(text + " ")` — testo in clipboard (con spazio finale)
2. `SetForegroundWindow(hwnd)` — focus alla finestra precedente (con `AttachThreadInput` per cross-thread)
3. Verifica `GetForegroundWindow() == hwnd` — controlla che la finestra sia effettivamente in primo piano
4. `pyautogui.hotkey('ctrl', 'v')` — simula Ctrl+V dopo 100ms di delay
5. `play_ding()` — suono di conferma (se abilitato)

### Gestione errori

- Se `_previous_hwnd` è None → stato error + toast + suono errore
- Se `IsWindow(hwnd)` fallisce → stato error + toast + suono errore
- Se `GetForegroundWindow()` non corrisponde all'hwnd target → stato error + toast + suono errore
- Se `SetForegroundWindow` lancia eccezione → fallback diretto, poi toast se anche quello fallisce
- Toast posizionato: sopra la compact pill (se minimizzato) o sotto la pill principale (se visibile)
- Durante lo stato error (2.5s), le registrazioni sono bloccate

---

## Suoni (`utils/sound.py`)

- Riproduzione asincrona di file mp3 tramite Windows MCI (`winmm.mciSendStringW`)
- **notify.mp3**: suono di conferma paste riuscito (volume 20%)
- **error.mp3**: suono di errore paste fallito (volume 14%)
- Abilitabili/disabilitabili da settings ("Suono dopo incolla")

---

## Toast Widget (`ui/toast_widget.py`)

Notifica compatta near-taskbar per comunicare errori di paste.

- Messaggio: "Incolla non riuscito — testo negli appunti"
- Fade-in 200ms, visibile 2s, fade-out 400ms
- **Glow giallo**: flash giallo animato (1.2s) con bordo giallo al comparire
- Posizionamento adattivo: sopra compact pill, sotto pill principale, o centrato in basso
- Stesso tema dell'app

---

## Pannello impostazioni (`ui/settings_panel.py`)

Slide-in/out sotto la pill (250ms, cubic easing). Larghezza 440px.

### Sezioni

1. **Chiave API OpenAI** — campo password con toggle mostra/nascondi, auto-save
2. **Tema** — 7 cerchi colorati su 2 righe (4+3)
3. **Avvio automatico** — checkbox che scrive in `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`
4. **Correggi testo con AI** — checkbox per abilitare/disabilitare il post-processing GPT
5. **Suono dopo incolla** — checkbox per abilitare/disabilitare i suoni di notifica
6. **Scorciatoie** — checkbox abilita/disabilita + selettore modalità (Toggle / Tieni premuto) + configurazione tasti per ogni modalità
7. **Costi API** — grafico a barre dei costi giornalieri ($0.006/min), filtri temporali (7gg, 30gg, 3 mesi, 1 anno, totale)
8. **Cronologia** — barra di ricerca + ultime 100 trascrizioni con timestamp, durata, costo, bottoni copia e espandi

### Vista messaggio

Cliccando "espandi" su una trascrizione, il pannello fa un crossfade alla vista messaggio completa con bottone indietro e copia.

---

## Persistenza (`utils/config.py`)

### File

- `%APPDATA%\Whisper\config.json` — API key, tema, scorciatoie, post-processing, suono
- `%APPDATA%\Whisper\history.json` — array di trascrizioni

### Formato config

```json
{
  "openai_api_key": "sk-...",
  "theme": "Midnight",
  "shortcuts": {
    "enabled": true,
    "mode": "toggle",
    "toggle_key": "U",
    "discard_key": "I",
    "hold_record_key": "PAUSE",
    "hold_discard_key": "SCROLL_LOCK"
  },
  "post_processing": true,
  "paste_sound": true
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
| **Compact start glow** | 1000ms | Glow rosso sulla compact pill all'avvio registrazione, opacity 0→80→40→0 |
| **Idle breathing** | Continua | 5 barrette sinusoidali, altezza 3–7px |
| **Recording waveform** | Real-time | Barrette rosse scrollanti destra→sinistra, altezza da amplitude |
| **Recording pulse** | Continua | Glow rosso sinusoidale (max alpha 25) |
| **Transcribing bars** | Continua | 5 barrette sinusoidali veloci (×3.5), blu |
| **Transcribing glow** | Continua | Inner edge glow 4 direzioni, pulsante |
| **Transcribing pulse** | Continua | Glow blu sinusoidale (max alpha 30) |
| **Success sweep** | 1400ms (pill) / 800ms (compact) | Gradient verde sinistra→destra + bordo verde |
| **Compact fade-out** | 250ms | Fade opacità finestra 1→0 dopo success sweep |
| **Error flash** | 600ms | Bordo rosso, opacity 0→200→0 |
| **Toast glow** | 1200ms | Glow giallo + bordo giallo, opacity 0→100→50→0 |

### Implementazione

- Paint timer a 16ms (~60fps) guida `paintEvent`
- `QPropertyAnimation` per success, error, glow e fade-out (driven by opacity properties)
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
