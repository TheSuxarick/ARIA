"""
Test Edge TTS with Russian and Kazakh voices
"""
import asyncio
import edge_tts
import os

# Voice names for Edge TTS
VOICES = {
    "russian": "ru-RU-SvetlanaNeural",   # Svetlana - Russian
    "kazakh": "kk-KZ-AigulNeural",        # Aigul - Kazakh
    "english": "en-US-JennyNeural"        # Jenny - English (bonus)
}

async def speak(text: str, voice: str, output_file: str):
    """Generate speech and save to file"""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)
    print(f"Saved: {output_file}")

async def main():
    # Test Russian - Svetlana
    print("\n[RU] Russian (Svetlana):")
    russian_text = "Привет! Меня зовут Светлана. Я твой голосовой ассистент."
    await speak(russian_text, VOICES["russian"], "test_russian.mp3")
    
    # Test Kazakh - Aigul
    print("\n[KZ] Kazakh (Aigul):")
    kazakh_text = "Сәлем! Менің атым Айгүл. Мен сіздің дауыстық көмекшіңізмін."
    await speak(kazakh_text, VOICES["kazakh"], "test_kazakh.mp3")
    
    # Test English - Jenny
    print("\n[EN] English (Jenny):")
    english_text = "Hello! My name is Jenny. I am your voice assistant."
    await speak(english_text, VOICES["english"], "test_english.mp3")
    
    print("\n[OK] All audio files generated!")
    print("\nPlaying audio files...")
    
    # Play the files (Windows)
    for lang in ["russian", "kazakh", "english"]:
        file = f"test_{lang}.mp3"
        print(f"\nPlaying {lang}...")
        os.system(f'start /wait "" "{file}"')

if __name__ == "__main__":
    asyncio.run(main())
