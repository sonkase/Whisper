from openai import OpenAI
from PyQt6.QtCore import QThread, pyqtSignal

SYSTEM_PROMPT = (
    "Sei un assistente che corregge e migliora testi trascritti dalla voce. "
    "Il testo proviene da un sistema di speech-to-text e potrebbe avere errori "
    "di punteggiatura, grammatica o formattazione.\n\n"
    "Regole:\n"
    "- Correggi punteggiatura e grammatica\n"
    "- Dividi il testo in paragrafi logici inserendo a-capo dove appropriato "
    "(cambio argomento, nuova frase di apertura, elenchi)\n"
    "- Se una parola sembra sbagliata o fuori contesto, deduci dal suono "
    "cosa l'utente intendeva realmente e correggila\n"
    "- Mantieni il significato originale esattamente com'è\n"
    "- Non aggiungere contenuto, non riassumere, non riformulare\n"
    "- Non aggiungere saluti, introduzioni o commenti\n"
    "- Rispondi SOLO con il testo corretto, nient'altro"
)


class PostProcessorWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, text: str, api_key: str, parent=None):
        super().__init__(parent)
        self._text = text
        self._api_key = api_key

    def run(self):
        try:
            client = OpenAI(api_key=self._api_key)
            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": self._text},
                ],
                temperature=0.3,
                max_tokens=2048,
            )
            result = response.choices[0].message.content.strip()
            if result:
                self.finished.emit(result)
            else:
                self.finished.emit(self._text)
        except Exception as e:
            self.error.emit(f"Post-processing error: {e}")
