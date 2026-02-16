"""
ARIA Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# OPENAI-COMPATIBLE API (ChatAnywhere)
# =============================================================================
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'sk-sTgiqoqr21XjLEGlcah65fT8LuamSvlalhy1ykfPwefgju4n')
OPENAI_API_BASE = os.getenv('OPENAI_API_BASE', 'https://api.chatanywhere.tech/v1')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o')

# =============================================================================
# ESP32-CAM
# =============================================================================
ESP32_CAM_IP = os.getenv('ESP32_CAM_IP', '10.183.3.186')

# =============================================================================
# YEELIGHT
# =============================================================================
YEELIGHT_IP = os.getenv('YEELIGHT_IP', '172.16.255.52')

# =============================================================================
# QDRANT RAG
# =============================================================================
QDRANT_HOST = os.getenv('QDRANT_HOST', 'localhost')
QDRANT_PORT = int(os.getenv('QDRANT_PORT', 6333))
QDRANT_COLLECTION = os.getenv('QDRANT_COLLECTION', 'soul')
RAG_TOP_K = 5  # Number of memories to retrieve

# =============================================================================
# WEATHER
# =============================================================================
OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '')
DEFAULT_CITY = os.getenv('DEFAULT_CITY', 'Almaty')

# =============================================================================
# TTS SETTINGS
# =============================================================================
# Microsoft Edge TTS voices
TTS_VOICE_RUSSIAN = "ru-RU-SvetlanaNeural"
TTS_VOICE_KAZAKH = "kk-KZ-AigulNeural"
TTS_VOICE_ENGLISH = "en-US-AriaNeural"

# Current default voice (Russian for now)
TTS_VOICE = TTS_VOICE_RUSSIAN

# =============================================================================
# WHISPER STT SETTINGS
# =============================================================================
WHISPER_MODEL = "base"  # tiny, base, small, medium, large
WHISPER_LANGUAGE = "ru"  # Russian for now

# =============================================================================
# WAKE WORD SETTINGS
# =============================================================================
WAKE_WORD = "ok_aria"  # Custom wake word
WAKE_WORD_THRESHOLD = 0.5  # Detection sensitivity (0-1)

# =============================================================================
# CONVERSATION SETTINGS
# =============================================================================
MAX_HISTORY_TURNS = 10  # Keep last N turns before summarizing
SUMMARIZE_AFTER = 10  # Summarize conversation after this many turns

# =============================================================================
# AUDIO SETTINGS
# =============================================================================
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1024
AUDIO_INPUT_DEVICE = 1  # Intel Smart Sound microphone

# =============================================================================
# PATHS
# =============================================================================
SOUNDS_DIR = os.path.join(os.path.dirname(__file__), 'sounds')

# =============================================================================
# SYSTEM PROMPT
# =============================================================================
SYSTEM_PROMPT = """Ты ARIA - умный домашний помощник. 

Характер:
- Дружелюбная и отзывчивая
- Отвечаешь кратко и по делу, потому что твои ответы озвучиваются
- Говоришь естественно, как в разговоре
- НЕ используешь markdown, эмодзи, списки - только чистый текст для озвучки

Возможности:
- Управление умной лампой (включить/выключить свет, изменить яркость, цвет)
- Камера с поворотом (посмотреть что происходит, повернуть камеру)
- Включить музыку с YouTube
- Узнать погоду
- Проверить почту

Когда пользователь просит что-то сделать, используй соответствующие функции.
Память из прошлых разговоров поможет тебе лучше понимать контекст.
"""
