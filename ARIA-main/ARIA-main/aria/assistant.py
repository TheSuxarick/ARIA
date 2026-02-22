"""
ARIA Assistant - Main Orchestrator
Coordinates all components: wake word, STT, TTS, Gemini, RAG, tools
"""
import re
import threading
import time
from enum import Enum

from config import SYSTEM_PROMPT
from audio_handler import get_audio_handler
from wake_word import get_wake_word_detector
from stt import get_stt
from tts import get_tts
from gemini_client import get_gemini
from rag import get_rag
from tools import get_tools
from sounds import get_sound_player


class AssistantState(Enum):
    """States of the assistant"""
    IDLE = "idle"               # Waiting for wake word
    LISTENING = "listening"     # Recording user speech
    PROCESSING = "processing"   # Processing with Gemini
    SPEAKING = "speaking"       # TTS output
    EXECUTING = "executing"     # Executing tool commands


class AriaAssistant:
    """
    ARIA - AI Home Assistant
    
    Flow:
    1. Wait for "Ok ARIA" wake word
    2. Play listening sound
    3. Record user speech until silence
    4. Play stop sound
    5. Transcribe with Whisper
    6. Get relevant memories from Qdrant
    7. Send to Gemini (with function calling)
    8. Execute any tool commands
    9. Speak response with Edge TTS
    10. Return to step 1
    """
    
    def __init__(self):
        self.state = AssistantState.IDLE
        self._lock = threading.Lock()
        self._running = False
        
        # Initialize components
        print("[*] Initializing ARIA...")
        
        self.audio = get_audio_handler()
        self.sounds = get_sound_player()
        self.stt = get_stt()
        self.tts = get_tts()
        self.gemini = get_gemini()
        self.rag = get_rag()
        self.tools = get_tools()
        
        # Wake word detector (callback set later)
        self.wake_detector = None
        
        # Vision keywords
        self.vision_keywords = [
            'что видишь', 'что ты видишь', 'посмотри', 'что перед тобой',
            'что на камере', 'покажи', 'что происходит', 'look', 'see',
            'what do you see', 'камера'
        ]
        
        # Tool keywords for direct execution
        self.tool_patterns = {
            # Light control
            r'(включи|зажги)\s*(свет|лампу|освещение)': 'light_on',
            r'(выключи|погаси)\s*(свет|лампу|освещение)': 'light_off',
            r'(переключи|toggle)\s*(свет|лампу)': 'light_toggle',
            r'яркость\s*(\d+)': lambda m: f'light_brightness {m.group(1)}',
            
            # Camera control
            r'камер[ау]\s*(вверх|наверх)': 'camera_up',
            r'камер[ау]\s*(вниз)': 'camera_down',
            r'камер[ау]\s*(влево|налево)': 'camera_left',
            r'камер[ау]\s*(вправо|направо)': 'camera_right',
            
            # Music
            r'(включи|поставь|играй)\s*(музыку|песню)\s*(.+)': lambda m: f'play_music {m.group(3)}',
            r'(стоп|останови|выключи)\s*(музыку|песню)': 'stop_music',
            
            # Weather
            r'(какая\s*)?погода': 'weather',
            
            # Email
            r'(проверь|прочитай)\s*(почту|письма|email)': 'check_email',
        }
        
        print("[OK] ARIA initialized!")
    
    def _set_state(self, state):
        """Thread-safe state change"""
        with self._lock:
            self.state = state
    
    def _on_wake_word(self):
        """Called when wake word is detected"""
        if self.state != AssistantState.IDLE:
            return  # Ignore if busy
        
        self._handle_activation()
    
    def _handle_activation(self):
        """Handle wake word activation"""
        self._set_state(AssistantState.LISTENING)
        
        # Play listening sound
        self.sounds.play_listen_start()
        
        # Record user speech
        audio_data = self.audio.record_until_silence(
            silence_threshold=0.01,
            silence_duration=1.5,
            max_duration=30
        )
        
        # Play stop sound
        self.sounds.play_listen_stop()
        
        if audio_data is None or len(audio_data) < 1000:
            print("[!] No speech detected")
            self._set_state(AssistantState.IDLE)
            return
        
        # Transcribe
        self._set_state(AssistantState.PROCESSING)
        print("[*] Transcribing...")
        
        text = self.stt.transcribe(audio_data)
        
        if not text or len(text.strip()) < 2:
            print("[!] Could not transcribe")
            self._set_state(AssistantState.IDLE)
            return
        
        print(f"[User] {text}")
        
        # Process the request
        self._process_request(text)
    
    def _process_request(self, text):
        """Process user request"""
        text_lower = text.lower()
        
        # Check for direct tool commands
        tool_response = self._check_tool_command(text_lower)
        if tool_response:
            self._speak(tool_response)
            return
        
        # Check if this is a vision request
        is_vision = any(kw in text_lower for kw in self.vision_keywords)
        image_data = None
        
        if is_vision:
            print("[*] Capturing camera image...")
            image_data = self.tools.camera.capture()
            if not image_data:
                self._speak("Не могу подключиться к камере")
                return
        
        # Get relevant memories from RAG
        memories = self.rag.search(text)
        
        # Send to Gemini
        self._set_state(AssistantState.PROCESSING)
        print("[*] Thinking...")
        
        try:
            response = self.gemini.chat(text, memories=memories, image_data=image_data)
            print(f"[ARIA] {response}")
            
            # Check if response contains tool commands
            tool_in_response = self._extract_tool_from_response(response)
            if tool_in_response:
                self._set_state(AssistantState.EXECUTING)
                tool_result = self.tools.execute_command(tool_in_response)
                if tool_result and isinstance(tool_result, str):
                    response += f" {tool_result}"
            
            # Speak response
            self._speak(response)
            
        except Exception as e:
            print(f"[ERROR] {e}")
            self.sounds.play_error()
            self._speak("Произошла ошибка, попробуй еще раз")
    
    def _check_tool_command(self, text):
        """Check if text is a direct tool command"""
        for pattern, command in self.tool_patterns.items():
            match = re.search(pattern, text)
            if match:
                if callable(command):
                    cmd = command(match)
                else:
                    cmd = command
                
                self._set_state(AssistantState.EXECUTING)
                result = self.tools.execute_command(cmd)
                
                if result:
                    return result
        
        return None
    
    def _extract_tool_from_response(self, response):
        """Extract tool command from AI response (if any)"""
        # AI might say things like "Включаю свет" - we can detect and execute
        response_lower = response.lower()
        
        tool_indicators = {
            'включаю свет': 'light_on',
            'выключаю свет': 'light_off',
            'поворачиваю камеру': None,  # Need more context
        }
        
        for indicator, command in tool_indicators.items():
            if indicator in response_lower and command:
                return command
        
        return None
    
    def _speak(self, text):
        """Speak text using TTS"""
        self._set_state(AssistantState.SPEAKING)
        
        # Pause wake word detection while speaking
        if self.wake_detector:
            self.wake_detector.pause()
        
        try:
            self.tts.speak(text)
        finally:
            self._set_state(AssistantState.IDLE)
            # Resume wake word detection
            if self.wake_detector:
                self.wake_detector.resume()
    
    def start(self):
        """Start ARIA assistant"""
        if self._running:
            return
        
        self._running = True
        
        print("\n" + "="*50)
        print("ARIA Home Assistant")
        print("="*50)
        print("Say 'Ok ARIA' or 'Privet ARIA' to activate")
        print("Press Ctrl+C to stop")
        print("="*50 + "\n")
        
        # Pre-load STT model
        print("[*] Loading speech recognition model...")
        self.stt.load_model()
        
        # Connect to Qdrant
        self.rag.connect()
        
        # Start wake word detection
        self.wake_detector = get_wake_word_detector(callback=self._on_wake_word)
        self.wake_detector.start()
        
        # Play startup sound
        self.sounds.play_success()
        
        # Main loop
        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[*] Stopping ARIA...")
        finally:
            self.stop()
    
    def stop(self):
        """Stop ARIA assistant"""
        self._running = False
        
        if self.wake_detector:
            self.wake_detector.stop()
        
        # Stop any playing music
        self.tools.youtube.stop()
        
        print("[*] ARIA stopped. Goodbye!")
    
    def process_text(self, text):
        """Process text input directly (for testing without voice)"""
        print(f"[User] {text}")
        self._process_request(text)


def main():
    """Main entry point"""
    assistant = AriaAssistant()
    assistant.start()


if __name__ == "__main__":
    main()
