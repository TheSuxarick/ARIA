"""
ARIA Speech-to-Text
Uses faster-whisper for fast, local transcription
"""
import numpy as np
from faster_whisper import WhisperModel
from config import WHISPER_MODEL, WHISPER_LANGUAGE, SAMPLE_RATE


class SpeechToText:
    """Speech-to-Text using faster-whisper (local, no API)"""
    
    def __init__(self, model_size=None, language=None):
        self.model_size = model_size or WHISPER_MODEL
        self.language = language or WHISPER_LANGUAGE
        self.model = None
        
    def load_model(self):
        """Load Whisper model (lazy loading)"""
        if self.model is None:
            print(f"[*] Loading Whisper model '{self.model_size}'...")
            # Use CPU with int8 for faster inference
            self.model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8"
            )
            print("[OK] Whisper model loaded!")
        return self.model
    
    def transcribe(self, audio_data):
        """
        Transcribe audio to text
        
        Args:
            audio_data: numpy array of audio (float32, mono, 16kHz)
            
        Returns:
            Transcribed text string
        """
        model = self.load_model()
        
        # Ensure correct format
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)
        
        # Flatten if needed
        if len(audio_data.shape) > 1:
            audio_data = audio_data.flatten()
        
        # Normalize
        if np.abs(audio_data).max() > 1.0:
            audio_data = audio_data / np.abs(audio_data).max()
        
        # Transcribe
        segments, info = model.transcribe(
            audio_data,
            language=self.language,
            beam_size=5,
            vad_filter=True,  # Filter out non-speech
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200
            )
        )
        
        # Collect text from segments
        text = " ".join([segment.text for segment in segments])
        
        return text.strip()
    
    def transcribe_file(self, audio_path):
        """Transcribe audio file to text"""
        model = self.load_model()
        
        segments, info = model.transcribe(
            audio_path,
            language=self.language,
            beam_size=5,
            vad_filter=True
        )
        
        text = " ".join([segment.text for segment in segments])
        return text.strip()


# Singleton instance
_stt = None

def get_stt():
    global _stt
    if _stt is None:
        _stt = SpeechToText()
    return _stt


if __name__ == "__main__":
    # Test STT
    from audio_handler import AudioHandler
    
    stt = SpeechToText()
    audio = AudioHandler()
    
    print("Say something (3 seconds)...")
    audio.start_listening()
    
    import time
    time.sleep(3)
    
    recorded = audio.stop_listening()
    
    if recorded is not None:
        print("Transcribing...")
        text = stt.transcribe(recorded)
        print(f"You said: {text}")
    else:
        print("No audio recorded")
