# ARIA - AI Home Assistant

🏠 Voice-activated home assistant powered by Google Gemini with smart home control.

## Features

- **Wake Word Detection** - Say "Ok ARIA" or "Привет Ария" to activate
- **Speech Recognition** - Local Whisper model (no cloud STT)
- **Natural TTS** - Microsoft Edge voices (Russian: Svetlana)
- **Gemini AI** - With API key rotation for rate limits
- **RAG Memory** - Uses Qdrant for conversation memory
- **Vision** - ESP32-CAM integration with pan/tilt control
- **Smart Home** - Yeelight bulb control
- **Music** - YouTube playback via yt-dlp
- **Weather** - OpenWeatherMap / wttr.in
- **Email** - Gmail summary (optional)

## Installation

1. **Install Python packages:**
```bash
pip install -r requirements.txt
```

2. **Install system dependencies:**
```bash
# FFmpeg (for YouTube audio)
# Windows: winget install ffmpeg
# Linux: sudo apt install ffmpeg

# yt-dlp
pip install yt-dlp
```

3. **Create `.env` file:**
```env
# Gemini API keys (for rotation)
google_api_1=your_key_1
google_api_2=your_key_2

# ESP32-CAM
ESP32_CAM_IP=10.58.187.186

# Yeelight
YEELIGHT_IP=172.16.255.52

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=soul

# Weather (optional)
OPENWEATHER_API_KEY=your_key
DEFAULT_CITY=Almaty
```

## Usage

### Normal Mode (Voice)
```bash
python main.py
```

### Text Mode (Testing)
```bash
python main.py --text
```

### Test Components
```bash
python main.py --test
```

## Voice Commands

### Light Control
- "Включи свет" / "Выключи свет"
- "Яркость 50" (set brightness)
- "Переключи свет" (toggle)

### Camera
- "Что ты видишь?" (vision query)
- "Камера влево/вправо/вверх/вниз"

### Music
- "Включи музыку [название]"
- "Стоп" / "Выключи музыку"

### Weather
- "Какая погода?"
- "Погода в Москве"

### Email
- "Проверь почту"

### General
- Talk naturally - ARIA uses Gemini to understand context

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    main.py                            │
│                  (Entry Point)                        │
└─────────────────────┬────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────┐
│                 assistant.py                          │
│              (Main Orchestrator)                      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │
│  │ States  │ │  Flow   │ │Commands │ │  Tools  │    │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘    │
└─────────────────────┬────────────────────────────────┘
                      │
    ┌─────────────────┼─────────────────┐
    │                 │                 │
┌───▼───┐      ┌──────▼──────┐    ┌─────▼─────┐
│ Audio │      │   AI Core   │    │   Tools   │
│       │      │             │    │           │
│wake   │      │gemini_client│    │ ESP32-CAM │
│word.py│      │    rag.py   │    │ Yeelight  │
│stt.py │      │             │    │ YouTube   │
│tts.py │      │             │    │ Weather   │
│sounds │      │             │    │ Email     │
└───────┘      └─────────────┘    └───────────┘
```

## Files

| File | Description |
|------|-------------|
| `main.py` | Entry point |
| `assistant.py` | Main orchestrator |
| `config.py` | Configuration |
| `audio_handler.py` | Microphone/speaker |
| `wake_word.py` | Wake word detection |
| `stt.py` | Speech-to-text (Whisper) |
| `tts.py` | Text-to-speech (Edge TTS) |
| `sounds.py` | UI sound effects |
| `gemini_client.py` | Gemini API with key rotation |
| `rag.py` | Qdrant RAG memory |
| `tools.py` | All integrations |

## Notes

- First run downloads Whisper model (~150MB for 'base')
- Make sure Qdrant is running: `docker run -p 6333:6333 qdrant/qdrant`
- ESP32-CAM must be on same network
- YouTube playback requires ffmpeg

## Troubleshooting

**No audio input:**
- Check microphone permissions
- Run `python -c "import sounddevice; print(sounddevice.query_devices())"`

**Wake word not detecting:**
- Speak clearly: "Ok ARIA" or "Окей Ария"
- Check microphone volume

**Gemini errors:**
- Verify API key in `.env`
- Check quota at https://console.cloud.google.com

**Qdrant connection:**
- Ensure Docker is running
- Check `docker ps` for qdrant container
