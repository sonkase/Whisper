import os
import wave
import tempfile
import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QThread, pyqtSignal


class AudioRecorder(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    amplitude = pyqtSignal(list)  # emits per-bar amplitude values (0.0-1.0)

    SAMPLE_RATE = 16000
    CHANNELS = 1
    BLOCKSIZE = 1024
    NUM_BARS = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recording = False
        self._frames = []

    def run(self):
        self._recording = True
        self._frames = []

        try:
            with sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype='int16',
                blocksize=self.BLOCKSIZE,
                callback=self._audio_callback,
            ):
                while self._recording:
                    sd.sleep(50)

            if self._frames:
                wav_path = self._save_wav()
                self.finished.emit(wav_path)
            else:
                self.error.emit("No audio recorded")

        except Exception as e:
            self.error.emit(f"Recording error: {e}")

    def _audio_callback(self, indata, frames, time_info, status):
        if not self._recording:
            return
        self._frames.append(indata.copy())

        # Compute amplitude for each bar from frequency bands
        data = indata[:, 0].astype(np.float32)
        chunk_size = len(data) // self.NUM_BARS
        levels = []
        for i in range(self.NUM_BARS):
            start = i * chunk_size
            end = start + chunk_size if i < self.NUM_BARS - 1 else len(data)
            segment = data[start:end]
            rms = np.sqrt(np.mean(segment ** 2)) / 32768.0
            # Scale up and clamp to 0-1
            level = min(1.0, rms * 12.0)
            levels.append(float(level))

        self.amplitude.emit(levels)

    def stop_recording(self):
        self._recording = False

    def _save_wav(self) -> str:
        audio_data = np.concatenate(self._frames, axis=0)
        fd, wav_path = tempfile.mkstemp(suffix='.wav')
        os.close(fd)

        with wave.open(wav_path, 'wb') as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(audio_data.tobytes())

        return wav_path
