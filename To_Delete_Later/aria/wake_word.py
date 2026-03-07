"""
ARIA Wake Word Detection
Local wake word detection using Whisper-based keyword spotting
Listens for "Ok ARIA" / "Окей Ария" / "Привет Ария"
"""
import numpy as np
import threading
import queue
import time
from config import WAKE_WORD_THRESHOLD, SAMPLE_RATE, AUDIO_INPUT_DEVICE

# We use Whisper-based detection for custom wake words like "Ok ARIA"
# OpenWakeWord only has pre-trained models (hey_jarvis, alexa, etc.)
OPENWAKEWORD_AVAILABLE = False  # Disabled - use Whisper for custom wake words


class WakeWordDetector:
    """
    Detects "Ok ARIA" wake word locally
    
    Uses openwakeword if available, otherwise falls back to 
    continuous Whisper-based keyword detection
    """
    
    def __init__(self, callback=None):
        """
        Args:
            callback: Function to call when wake word detected
        """
        self.callback = callback
        self.is_running = False
        self.threshold = WAKE_WORD_THRESHOLD
        self._thread = None
        self._audio_queue = queue.Queue()
        
        # OpenWakeWord model
        self.oww_model = None
        
        # For simple detection
        self.stt = None
        
    def _init_openwakeword(self):
        """Initialize OpenWakeWord model"""
        if OPENWAKEWORD_AVAILABLE and self.oww_model is None:
            print("[*] Loading wake word model...")
            # Download and load pre-trained models
            # We'll use "hey_jarvis" as base and also listen for "ok aria" via custom logic
            openwakeword.utils.download_models()
            self.oww_model = Model(
                wakeword_models=["hey_jarvis"],  # Built-in model as fallback
                inference_framework="onnx"
            )
            print("[OK] Wake word model loaded!")
    
    def _init_simple_detector(self):
        """Initialize simple Whisper-based detector"""
        from stt import get_stt
        self.stt = get_stt()
        self.stt.load_model()  # Pre-load model
    
    def _check_wake_word_simple(self, text):
        """Check if text contains wake word"""
        text = text.lower().strip()
        
        # Remove punctuation for better matching
        import re
        text = re.sub(r'[^\w\s]', '', text)
        
        # Various ways user might say it (Russian, English, variations)
        wake_phrases = [
            # English variations
            "ok aria", "okay aria", "hey aria", "hi aria",
            "ok arya", "okay arya", "hey arya",
            # Russian variations
            "окей ария", "оке ария", "окей арья", 
            "привет ария", "привет арья",
            "эй ария", "хей ария",
            "слушай ария", "ария слушай",
            # Short forms (more aggressive matching)
            "ария",  # Just "Aria" in Russian
        ]
        
        for phrase in wake_phrases:
            if phrase in text:
                return True
        
        # Also check for "aria" separately (English) but only if it's a word
        words = text.split()
        if "aria" in words or "arya" in words:
            return True
            
        return False
    
    def _detection_loop_oww(self):
        """Detection loop using OpenWakeWord"""
        import sounddevice as sd
        
        chunk_size = 1280  # ~80ms at 16kHz
        
        def audio_callback(indata, frames, time, status):
            if self.is_running:
                self._audio_queue.put(indata.copy())
        
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='int16',
            blocksize=chunk_size,
            callback=audio_callback
        ):
            while self.is_running:
                try:
                    audio_chunk = self._audio_queue.get(timeout=0.1)
                    
                    # Process with OpenWakeWord
                    prediction = self.oww_model.predict(audio_chunk.flatten())
                    
                    # Check all models
                    for model_name, score in prediction.items():
                        if score > self.threshold:
                            print(f"[WAKE] Detected! ({model_name}: {score:.2f})")
                            if self.callback:
                                self.callback()
                            # Clear queue to avoid re-triggering
                            while not self._audio_queue.empty():
                                self._audio_queue.get_nowait()
                            time.sleep(0.5)  # Brief pause
                            
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"Wake word error: {e}")
    
    def _detection_loop_simple(self):
        """Detection loop using Whisper for keyword spotting"""
        import sounddevice as sd
        
        # Record in 2.5-second chunks for keyword detection
        chunk_duration = 2.5
        samples_per_chunk = int(SAMPLE_RATE * chunk_duration)
        
        print("[*] Listening for 'Ok ARIA' / 'Okey Aria' / 'Privet Aria'...")
        print("   (Whisper-based detection - speak clearly)")
        
        while self.is_running:
            try:
                # Record short audio chunk
                audio = sd.rec(
                    samples_per_chunk,
                    samplerate=SAMPLE_RATE,
                    channels=1,
                    dtype='float32',
                    device=AUDIO_INPUT_DEVICE
                )
                sd.wait()
                
                if not self.is_running:
                    break
                
                # Check volume - skip if too quiet
                volume = np.abs(audio).mean()
                if volume < 0.003:  # Lower silence threshold for better sensitivity
                    continue
                
                # Transcribe
                text = self.stt.transcribe(audio)
                
                if text:
                    # Debug: show what was heard (can comment out later)
                    if len(text) > 3:  # Only show if meaningful
                        print(f"   [heard: {text[:50]}...]" if len(text) > 50 else f"   [heard: {text}]")
                    
                    if self._check_wake_word_simple(text):
                        print(f"\n[WAKE] Detected! '{text}'")
                        if self.callback:
                            self.callback()
                        time.sleep(1.0)  # Pause after detection to avoid re-trigger
                    
            except Exception as e:
                if self.is_running:
                    print(f"Detection error: {e}")
                time.sleep(0.1)
    
    def start(self):
        """Start wake word detection in background"""
        if self.is_running:
            return
        
        self.is_running = True
        
        if OPENWAKEWORD_AVAILABLE:
            self._init_openwakeword()
            self._thread = threading.Thread(target=self._detection_loop_oww, daemon=True)
        else:
            self._init_simple_detector()
            self._thread = threading.Thread(target=self._detection_loop_simple, daemon=True)
        
        self._thread.start()
        print("[OK] Wake word detection started")
    
    def stop(self):
        """Stop wake word detection"""
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=2)
        print("[*] Wake word detection stopped")
    
    def pause(self):
        """Temporarily pause detection (e.g., while ARIA is speaking)"""
        self.is_running = False
        # Clear audio queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except:
                break
    
    def resume(self):
        """Resume detection after pause"""
        if not self.is_running and self._thread and self._thread.is_alive():
            self.is_running = True
        elif not self._thread or not self._thread.is_alive():
            self.start()


# Singleton
_detector = None

def get_wake_word_detector(callback=None):
    global _detector
    if _detector is None:
        _detector = WakeWordDetector(callback)
    elif callback:
        _detector.callback = callback
    return _detector


if __name__ == "__main__":
    # Test wake word detection
    def on_wake_word():
        print("\n" + "="*50)
        print(">>> WAKE WORD DETECTED! ARIA is listening...")
        print("="*50 + "\n")
    
    detector = WakeWordDetector(callback=on_wake_word)
    
    print("Testing wake word detection...")
    print("Say 'Ok ARIA' or 'Привет Ария'")
    print("Press Ctrl+C to stop\n")
    
    detector.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        detector.stop()
