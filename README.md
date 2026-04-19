# ARIA — Smart home assistant (diploma project)

ARIA is a **local smart-home assistant** that combines a **Python/Flask web server** (chat, Gmail, weather, music, lighting) with a **custom 3D-printed enclosure** powered from a **single 5 V / 10 A** supply. Two ESP32 boards act as peripherals on the LAN: one handles **camera + pan** motion, the other streams **microphone → PC** and **PC → speaker** audio over UDP.

**Repository:** [github.com/TheSuxarick/aria](https://github.com/TheSuxarick/aria) (if this fork differs, update the link).

---

## What is in this repo

| Path | Role |
|------|------|
| `ARIA website/` | Flask + Socket.IO app (`app.py`), SQLite models (`models.py`), Gmail OAuth (`gmail_service.py`), templates and static UI |
| `run_server.py` | Runs the app from the repo root (changes cwd to `ARIA website`, binds `0.0.0.0:5000`) |
| `Device/esp-32-cam.ino` | ESP32-CAM (AI-Thinker): MJPEG stream, HTTP control, **stepper pan** + **servo tilt** (tilt may be unused or limited mechanically—see thesis) |
| `Device/esp-32-wroom.ino` | ESP32-WROOM: **INMP441** mic + **MAX98357** speaker, **16 kHz** PCM over UDP |
| `Device/3D-model/` | STL assets (e.g. `Head.stl`) |
| `helpful_utils/` | Small Python helpers (device discovery, bulb tests, etc.) |
| `Diploma.tex` | LaTeX thesis source |
| `To_Delete_Later/` | Legacy experiments (not part of the main product) |

**Figures for the thesis / docs** (place next to `Diploma.tex` in Overleaf or set `\graphicspath`):

- `sdu_logo.png`
- `esp32-cam_connection_sheme.png`
- `esp-32-wroom_connection_scheme.png`
- `final_physical_look.png` — assembled black prototype + PSU
- `3dmodel_front.png`, `3dmodel_bottom_back.png`, `3dmodel_see_through.png` — CAD views
- `ui_dashboard.png`, `ui_camera.png`, `ui_functions.png`, `ui_settings.png` — web UI screenshots (export from browser at a consistent window width)

---

## Features (software)

- **Dashboard UI** — Single-page web app (`templates/index.html`, `static/js/app.js`, `static/css/style.css`): dashboard, embedded camera view, functions, settings; dark/light theme; i18n strings in JS.
- **Chat** — Google **Gemini** API; optional **Mangısöz** keys for Kazakh-oriented backend; personalities; session-scoped history stored in SQLite (`ChatMessage`).
- **Gmail** — OAuth2; cached messages in `EmailMessage` for assistant context.
- **Weather** — OpenWeatherMap-style integration via `app.py` (`/api/weather`, `/api/forecast`).
- **Music** — YouTube search → embed playback (`/api/play-music`).
- **Yeelight** — On/off, brightness, named colors, warm/cool, RGB cycle; discovery via ARP/MAC (`LAMP_MAC` in env). **Tested lamp:** Yeelight Smart LED Bulb W3 (Multicolor), model **YLDP005** — 100–240 V 50/60 Hz, 0.07 A, 900 lm, 1700–6500 K, 8 W.
- **Voice (robot mode)** — ESP32 mic UDP → PC; **faster-whisper** STT; **edge-tts**; optional **openWakeWord** (`models/computer_v2.onnx`); Socket.IO namespace `/audio` for browser streaming.

See `ARIA website/SETUP_INSTRUCTIONS.md` and `.env.example` for configuration.

---

## Hardware overview

### Power

- **5 V DC, ~10 A** recommended for head unit + ESP32 modules + audio + motor drivers (adjust to your actual load).

### ESP32-CAM (camera + pan/tilt)

- **Camera:** standard **AI-Thinker** pin map in firmware (`CAMERA_MODEL_AI_THINKER`).
- **Pan:** 4-wire **stepper** on GPIO **13, 15, 14, 2** (half-step sequence in firmware).
- **Tilt:** **servo** on GPIO **12** (`SERVO_1`). *Mechanical/design limits may prevent usable tilt in the printed assembly; pan remains the primary horizontal motion.*
- **HTTP:** UI and `/action` on port **80**, MJPEG **`/stream`** on port **81** (see `startCameraServer()`).

Update `ssid`, `password`, and IP usage in the sketch for your network.

### ESP32-WROOM (audio I/O bridge)

Firmware (`esp-32-wroom.ino`) uses:

| Signal | GPIO (in repo) |
|--------|----------------|
| INMP441 BCLK (SCK) | 26 |
| INMP441 LRCLK (WS) | 25 |
| INMP441 DOUT (SD) | **34** |
| MAX98357 BCLK | 12 |
| MAX98357 LRC | 14 |
| MAX98357 DIN | 27 |

Protocol: **16-bit signed PCM, mono, 16 kHz**, little-endian UDP — mic to `PC_IP:12345`, speaker from PC to ESP port `12346`.

Also connect **INMP441** VDD to **3.3 V** and **L/R** select lines as required (often tied to GND). **MAX98357** **Vin** to **5 V** (or board 5 V rail).

Set `PC_IP`, `WIFI_SSID`, and `WIFI_PASSWORD` in the sketch.

---

## Quick start (server)

```bash
cd "ARIA website"
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
# Add openwakeword + onnxruntime if using wake word (see app.py)
copy .env.example .env   # then edit keys
python app.py
```

Or from repo root:

```bash
python run_server.py
```

Open `http://localhost:5000` (OAuth flows expect `localhost`, not `127.0.0.1` — the app redirects automatically).

---

## Flashing firmware

- Open `Device/esp-32-cam.ino` or `Device/esp-32-wroom.ino` in **Arduino IDE** or **PlatformIO**, select the correct board (ESP32-CAM / ESP32 Dev Module), PSRAM settings as required for the camera board, then flash.

---

## Authors / context

Diploma project — **SDU University**, Computer Science (**6B06102**).  
Students: **Kenesbayev Arsen, Orynbek Aidos, Sagibek Adil**.  
Supervisor: **Binara Imankulova**.

For an academic write-up of architecture, methodology, and limitations, see **`Diploma.tex`**.
