#!/usr/bin/env python3
"""
ARIA - AI Home Assistant
========================

Voice-activated home assistant with:
- Wake word detection ("Ok ARIA" / "Привет Ария")
- Speech-to-Text (Whisper, local)
- Text-to-Speech (Edge TTS, Russian)
- Gemini AI with RAG memory
- Smart home control (Yeelight bulb)
- ESP32-CAM vision and pan/tilt
- YouTube music playback
- Weather information
- Email summarization

Usage:
    python main.py         - Start assistant with wake word
    python main.py --text  - Text input mode (for testing)
    python main.py --test  - Test individual components
"""

import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description='ARIA Home Assistant')
    parser.add_argument('--text', action='store_true', help='Text input mode')
    parser.add_argument('--test', action='store_true', help='Test components')
    args = parser.parse_args()
    
    if args.test:
        test_components()
    elif args.text:
        text_mode()
    else:
        voice_mode()


def voice_mode():
    """Normal voice-activated mode"""
    from assistant import AriaAssistant
    
    assistant = AriaAssistant()
    assistant.start()


def text_mode():
    """Text input mode for testing without microphone"""
    from assistant import AriaAssistant
    
    print("\n" + "="*50)
    print("ARIA - Text Mode")
    print("="*50)
    print("Type your messages (or 'quit' to exit)")
    print("="*50 + "\n")
    
    assistant = AriaAssistant()
    
    # Don't start wake word detection
    assistant.stt.load_model()
    assistant.rag.connect()
    
    try:
        while True:
            text = input("\nYou: ").strip()
            
            if not text:
                continue
            
            if text.lower() in ['quit', 'exit', 'выход', 'q']:
                break
            
            assistant.process_text(text)
            
    except KeyboardInterrupt:
        pass
    
    print("\nGoodbye!")


def test_components():
    """Test individual components"""
    print("\n[TEST] Testing ARIA Components\n")
    
    # Test 1: Audio
    print("[1] Testing Audio...")
    try:
        from audio_handler import AudioHandler
        audio = AudioHandler()
        devices = audio.get_audio_devices()
        print(f"   [OK] Found {len(devices)} audio devices")
    except Exception as e:
        print(f"   [FAIL] Audio error: {e}")
    
    # Test 2: TTS
    print("\n[2] Testing TTS...")
    try:
        from tts import TextToSpeech
        tts = TextToSpeech()
        tts.speak("Test voice")
        print("   [OK] TTS working")
    except Exception as e:
        print(f"   [FAIL] TTS error: {e}")
    
    # Test 3: Sounds
    print("\n[3] Testing Sounds...")
    try:
        from sounds import SoundPlayer
        player = SoundPlayer()
        player.play_listen_start()
        print("   [OK] Sounds working")
    except Exception as e:
        print(f"   [FAIL] Sounds error: {e}")
    
    # Test 4: STT
    print("\n[4] Testing STT (loading model)...")
    try:
        from stt import SpeechToText
        stt = SpeechToText()
        stt.load_model()
        print("   [OK] Whisper model loaded")
    except Exception as e:
        print(f"   [FAIL] STT error: {e}")
    
    # Test 5: Gemini
    print("\n[5] Testing Gemini...")
    try:
        from gemini_client import GeminiClient
        client = GeminiClient()
        response = client.chat("Say 'test successful'")
        print(f"   [OK] Gemini response: {response[:50]}...")
    except Exception as e:
        print(f"   [FAIL] Gemini error: {e}")
    
    # Test 6: RAG
    print("\n[6] Testing RAG (Qdrant)...")
    try:
        from rag import RAGMemory
        rag = RAGMemory()
        if rag.connect():
            info = rag.get_collection_info()
            if info:
                print(f"   [OK] Collection '{info['name']}' has {info['points_count']} points")
            else:
                print("   [!] Collection not found")
        else:
            print("   [FAIL] Could not connect to Qdrant")
    except Exception as e:
        print(f"   [FAIL] RAG error: {e}")
    
    # Test 7: Weather
    print("\n[7] Testing Weather...")
    try:
        from tools import Weather
        weather = Weather()
        result = weather.get_weather()
        print(f"   [OK] {result}")
    except Exception as e:
        print(f"   [FAIL] Weather error: {e}")
    
    # Test 8: Light
    print("\n[8] Testing Light (Yeelight)...")
    try:
        from tools import SmartBulb
        bulb = SmartBulb()
        # Don't actually toggle, just check connection
        print("   [!] Light test skipped (would toggle bulb)")
    except Exception as e:
        print(f"   [FAIL] Light error: {e}")
    
    print("\n[OK] Component tests complete!\n")


if __name__ == "__main__":
    main()
