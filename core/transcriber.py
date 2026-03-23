import os
from openai import OpenAI
from PyQt6.QtCore import QThread, pyqtSignal


class TranscriberWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, wav_path: str, api_key: str, parent=None):
        super().__init__(parent)
        self._wav_path = wav_path
        self._api_key = api_key

    def run(self):
        try:
            client = OpenAI(api_key=self._api_key)

            with open(self._wav_path, 'rb') as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text",
                )

            self._cleanup()

            text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
            if text:
                self.finished.emit(text)
            else:
                self.error.emit("Empty transcription received")

        except Exception as e:
            self._cleanup()
            self.error.emit(f"Transcription error: {e}")

    def _cleanup(self):
        try:
            os.unlink(self._wav_path)
        except OSError:
            pass
