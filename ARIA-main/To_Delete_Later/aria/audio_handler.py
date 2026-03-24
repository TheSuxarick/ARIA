"""
ARIA Audio Handler
Manages microphone input and speaker output using laptop's built-in devices
"""
import numpy as np
import sounddevice as sd
import queue
import threading
from config import SAMPLE_RATE, CHANNELS, CHUNK_SIZE, AUDIO_INPUT_DEVICE


class AudioHandler:
    """Handles audio input/output for ARIA"""
    
    def __init__(self):
        self.sample_rate = SAMPLE_RATE
        self.channels = CHANNELS
        self.chunk_size = CHUNK_SIZE
        self.audio_queue = queue.Queue()
        self.is_recording = False
        self._stream = None
        
    def _audio_callback(self, indata, frames, time, status):
        """Callback for audio stream"""
        if status:
            print(f"Audio status: {status}")
        if self.is_recording:
            self.audio_queue.put(indata.copy())
    
    def start_listening(self):
        """Start listening to microphone"""
        self.is_recording = True
        self.audio_queue = queue.Queue()  # Clear queue
        
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype='float32',
            blocksize=self.chunk_size,
            callback=self._audio_callback,
            device=AUDIO_INPUT_DEVICE
        )
        self._stream.start()
        
    def stop_listening(self):
        """Stop listening and return recorded audio"""
        self.is_recording = False
        
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        
        # Collect all audio from queue
        audio_chunks = []
        while not self.audio_queue.empty():
            audio_chunks.append(self.audio_queue.get())
        
        if audio_chunks:
            return np.concatenate(audio_chunks, axis=0)
        return None
    
    def record_until_silence(self, silence_threshold=0.01, silence_duration=1.5, max_duration=30):
        """
        Record audio until silence is detected
        
        Args:
            silence_threshold: Volume level considered as silence
            silence_duration: Seconds of silence before stopping
            max_duration: Maximum recording duration in seconds
        
        Returns:
            numpy array of recorded audio
        """
        print("[*] Listening...")
        
        self.start_listening()
        
        audio_chunks = []
        silence_chunks = 0
        chunks_for_silence = int(silence_duration * self.sample_rate / self.chunk_size)
        max_chunks = int(max_duration * self.sample_rate / self.chunk_size)
        total_chunks = 0
        speech_started = False
        
        try:
            while total_chunks < max_chunks:
                try:
                    chunk = self.audio_queue.get(timeout=0.1)
                    audio_chunks.append(chunk)
                    total_chunks += 1
                    
                    # Check volume
                    volume = np.abs(chunk).mean()
                    
                    if volume > silence_threshold:
                        speech_started = True
                        silence_chunks = 0
                    elif speech_started:
                        silence_chunks += 1
                        
                        if silence_chunks >= chunks_for_silence:
                            print("[*] Silence detected, stopping...")
                            break
                            
                except queue.Empty:
                    continue
                    
        finally:
            self.stop_listening()
        
        if audio_chunks:
            return np.concatenate(audio_chunks, axis=0)
        return None
    
    def play_audio(self, audio_data, sample_rate=None):
        """Play audio through speakers"""
        if sample_rate is None:
            sample_rate = self.sample_rate
            
        sd.play(audio_data, sample_rate)
        sd.wait()
    
    def play_file(self, filepath):
        """Play audio file through speakers using pygame"""
        import pygame
        
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        
        pygame.mixer.music.load(filepath)
        pygame.mixer.music.play()
        
        # Wait for playback to finish
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
    
    def get_audio_devices(self):
        """List available audio devices"""
        return sd.query_devices()


# Singleton instance
_audio_handler = None

def get_audio_handler():
    global _audio_handler
    if _audio_handler is None:
        _audio_handler = AudioHandler()
    return _audio_handler


if __name__ == "__main__":
    # Test audio
    handler = AudioHandler()
    print("Available devices:")
    print(handler.get_audio_devices())
    
    print("\nRecording for 3 seconds...")
    handler.start_listening()
    import time
    time.sleep(3)
    audio = handler.stop_listening()
    
    if audio is not None:
        print(f"Recorded {len(audio)} samples")
        print("Playing back...")
        handler.play_audio(audio)
    else:
        print("No audio recorded")
