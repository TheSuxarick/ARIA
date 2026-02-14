"""
ARIA Text-to-Speech
Uses Microsoft Edge TTS for natural sounding voices
"""
import asyncio
import edge_tts
import tempfile
import os
from config import TTS_VOICE, TTS_VOICE_RUSSIAN, TTS_VOICE_KAZAKH, TTS_VOICE_ENGLISH


class TextToSpeech:
    """Text-to-Speech using Edge TTS"""
    
    def __init__(self, voice=None):
        self.voice = voice or TTS_VOICE
        self.temp_dir = tempfile.gettempdir()
        
    def set_voice(self, voice):
        """Change TTS voice"""
        self.voice = voice
        
    def set_russian(self):
        self.voice = TTS_VOICE_RUSSIAN
        
    def set_kazakh(self):
        self.voice = TTS_VOICE_KAZAKH
        
    def set_english(self):
        self.voice = TTS_VOICE_ENGLISH
    
    async def _synthesize_async(self, text, output_file):
        """Async synthesis"""
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(output_file)
    
    def synthesize(self, text):
        """
        Convert text to speech and return path to audio file
        
        Args:
            text: Text to synthesize
            
        Returns:
            Path to temporary MP3 file
        """
        # Generate unique filename
        output_file = os.path.join(self.temp_dir, f"aria_tts_{id(text)}.mp3")
        
        # Run async synthesis
        asyncio.run(self._synthesize_async(text, output_file))
        
        return output_file
    
    def speak(self, text):
        """Synthesize and play audio"""
        from audio_handler import get_audio_handler
        
        audio_file = self.synthesize(text)
        
        handler = get_audio_handler()
        handler.play_file(audio_file)
        
        # Cleanup
        try:
            os.remove(audio_file)
        except:
            pass
    
    @staticmethod
    async def list_voices():
        """List all available voices"""
        voices = await edge_tts.list_voices()
        return voices


# Singleton instance
_tts = None

def get_tts():
    global _tts
    if _tts is None:
        _tts = TextToSpeech()
    return _tts


if __name__ == "__main__":
    # Test TTS
    tts = TextToSpeech()
    
    print("Testing Russian voice...")
    tts.set_russian()
    tts.speak("Привет! Я Ария, твой умный домашний помощник.")
    
    print("\nListing some voices...")
    voices = asyncio.run(TextToSpeech.list_voices())
    
    # Show Russian and Kazakh voices
    for v in voices:
        if 'ru-RU' in v['Locale'] or 'kk-KZ' in v['Locale'] or 'en-US' in v['Locale']:
            print(f"{v['ShortName']}: {v['Locale']}")
