# Whisper — Implementazioni future

## Alto impatto

### 1. Selezione lingua nelle impostazioni
Aggiungere un selettore lingua nelle impostazioni (italiano, inglese, spagnolo, ecc.) per passare il parametro `language` alla chiamata Whisper API. Attualmente la lingua è fissa su italiano. Il parametro `prompt` di Whisper permette anche di guidare lo stile (punteggiatura, nomi propri, gergo di settore).

### 2. Modalità traduzione istantanea
L'API Whisper ha l'endpoint `audio.translations.create` che traduce qualsiasi lingua in inglese. Aggiungere un toggle "Trascrivi / Traduci" — utile per chi lavora in contesti multilingue.

### 3. Selezione dispositivo audio
Aggiungere un dropdown nelle impostazioni per scegliere il microfono. `sounddevice.query_devices()` fornisce la lista di tutti i dispositivi — permette di selezionare microfoni USB, cuffie Bluetooth, ecc. invece di usare sempre il default di sistema.

### 4. System audio capture (audio loopback)
Catturare l'audio di sistema (es. una call Zoom/Teams) oltre al microfono. Su Windows si può fare con WASAPI loopback via `sounddevice`. Permetterebbe di trascrivere meeting in tempo reale.

---

## Medio impatto

### 5. Scorciatoia "riprova"
Se la trascrizione è sbagliata, una hotkey per ri-inviare lo stesso audio — magari con lingua diversa o prompt correttivo.

### 6. Esporta cronologia
Bottone per esportare tutta la history in CSV, TXT o JSON. Utile per chi usa l'app intensivamente.

### 7. Limite di durata registrazione
Un timer massimo configurabile (es. 5 min) per evitare registrazioni accidentali lasciate aperte, con avviso visuale quando ci si avvicina al limite.

---

## Nice-to-have

### 8. Whisper locale (offline)
Supporto opzionale per `faster-whisper` o `whisper.cpp` per trascrizione offline — zero costi API, funziona senza internet. Richiede download del modello (~1-3GB).

### 9. Tray icon
Invece di minimizzare nella taskbar, un'icona nella system tray con menu contestuale (start/stop, settings, quit). Più pulito e standard per app always-on.

### 10. Multi-monitor awareness
Posizionare la pill/compact pill sullo schermo dove si trova il mouse, non sempre sul primario.

### 11. Aggiornamento automatico
Check versione su GitHub + notifica quando c'è un update disponibile.
