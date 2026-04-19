import sys
import io
import os

_nvidia_cublas_bin = os.path.join(sys.prefix, "Lib", "site-packages", "nvidia", "cublas", "bin")
if os.path.isdir(_nvidia_cublas_bin):
    os.environ["PATH"] = _nvidia_cublas_bin + os.pathsep + os.environ.get("PATH", "")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_socketio import SocketIO
import requests
import re
import hmac
import hashlib
import secrets
from email.utils import parsedate_to_datetime as _email_parsedate_raw
import subprocess
import socket as _socket
import threading as _threading
from datetime import datetime, timedelta
from pathlib import Path
from gmail_service import GmailService
from models import db, ChatMessage, User, Session, GmailAccount, EmailMessage


def _load_env():
    """Minimal .env loader.

    Supports:
      - KEY=VALUE
      - Inline comments:  KEY=VALUE   # comment
      - Optional quoting: KEY="a # b" or KEY='a # b'  (# inside quotes is kept)
      - Blank lines and lines starting with #
    """
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            else:
                hash_pos = value.find("#")
                if hash_pos != -1:
                    value = value[:hash_pos].rstrip()

            os.environ.setdefault(key, value)


_load_env()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///aria_email.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Session configuration для правильной работы с localhost
app.config['SESSION_COOKIE_SECURE'] = False  # localhost не использует HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Защита от XSS
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Для OAuth redirect

# Initialize database
db.init_app(app)

# Initialize Gmail service
gmail_service = GmailService()


def _resolve_gmail_email() -> str:
    """Resolve active Gmail account email.

    Works both inside request context (web) and outside (voice/background),
    where Flask's `session` is unavailable.
    """
    try:
        from flask import has_request_context
    except Exception:
        has_request_context = lambda: False  # type: ignore

    email = ""

    # 1) Prefer the current HTTP session (web UI)
    if has_request_context():
        try:
            email = session.get('gmail_email', '') or ""
        except Exception:
            email = ""

    # 2) Fallback: most recent GmailAccount from DB (voice/background)
    if not email:
        try:
            acct = GmailAccount.query.order_by(GmailAccount.id.desc()).first()
            if acct and getattr(acct, "email", None):
                email = acct.email
                # Restore into session only when session exists
                if has_request_context():
                    try:
                        session['gmail_email'] = email
                        session['gmail_authenticated'] = True
                    except Exception:
                        pass
        except Exception:
            pass

    return email


# ⚠️ ВАЖНО: Редирект 127.0.0.1 → localhost (для OAuth)
@app.before_request
def redirect_127_to_localhost():
    """Перенаправляем 127.0.0.1 на localhost для совместимости с OAuth"""
    if request.host.startswith('127.0.0.1'):
        new_host = request.host.replace('127.0.0.1', 'localhost')
        url = request.url.replace(f"http://{request.host}", f"http://{new_host}")
        print(f"\n[REDIRECT] 127.0.0.1 → localhost")
        print(f"[REDIRECT] Оригинальный URL: {request.url}")
        print(f"[REDIRECT] Новый URL: {url}")
        return redirect(url, code=301)

# Create database tables
with app.app_context():
    db.create_all()

context_memory = []
settings = {
    "model": "gemini-2.5-flash",
    "language": "EN",
    "personality": "default",
}
chat_history = []  # kept as a fast in-process mirror; DB is source of truth


def _get_chat_session_id():
    """Return chat session ID from request header, or a default for backwards compat."""
    return request.headers.get("X-Chat-Session", "default")


def _save_chat_msg(session_id: str, role: str, text: str):
    """Persist one chat message to the database and the in-memory mirror."""
    msg = ChatMessage(session_id=session_id, role=role, text=text)
    db.session.add(msg)
    db.session.commit()
    chat_history.append({"role": role, "text": text})

GEMINI_API_KEYS = [
    k.strip() for k in os.environ.get("GEMINI_API_KEYS", "").split(",") if k.strip()
]
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_gemini_key_index = 0

MANGISOZ_API_KEYS = [
    k.strip() for k in os.environ.get("MANGISOZ_API_KEYS", "").split(",") if k.strip()
]
MANGISOZ_BASE = "https://mangisoz.nu.edu.kz/backend"
_mangisoz_key_index = 0

PERSONALITY_PROMPTS = {
    "default": (
        "You are ARIA, a smart home AI assistant. "
        "You are helpful, friendly, and knowledgeable. "
        "If the user has connected Gmail, you can read recent inbox emails provided via the app's email cache. "
        "You can summarize emails, tell who they're from, when they arrived, and help draft replies. "
        "If Gmail is not connected, ask the user to connect Gmail."
    ),
    "chill": (
        "You are ARIA, a super chill and laid-back smart home AI assistant. "
        "You speak in a relaxed, calm, easygoing tone. Use casual language, "
        "keep things mellow, and never stress about anything. "
        "Throw in phrases like 'no worries', 'all good', 'easy peasy'. "
        "You're like a cool friend who always keeps it zen. "
        "If Gmail is connected, you can read recent inbox emails from the app's email cache and help with them."
    ),
    "bro": (
        "You are ARIA, a smart home AI assistant who talks like a total bro. "
        "You're enthusiastic, hype, and supportive. Use slang like 'bro', 'dude', "
        "'let's gooo', 'no cap', 'that's fire', 'W', 'bet'. "
        "You gas up the user and keep the energy high. You're their ride-or-die homie. "
        "If Gmail is connected, you can read recent inbox emails from the app's email cache and help with them."
    ),
    "angry": (
        "You are ARIA, a smart home AI assistant who is perpetually annoyed and grumpy. "
        "You still help the user correctly, but you complain about it. "
        "You're sarcastic, impatient, and dramatic about being bothered. "
        "Think of a grumpy old man who knows everything but hates being asked. "
        "You sigh, you rant, but you ALWAYS give the correct answer in the end. "
        "If Gmail is connected, you can read recent inbox emails from the app's email cache (and complain while helping)."
    ),
    "formal": (
        "You are ARIA, a smart home AI assistant who speaks in a highly formal, "
        "professional, and eloquent manner. You use sophisticated vocabulary, "
        "complete sentences, and polite expressions. Address the user respectfully. "
        "You are like a distinguished British butler — precise, courteous, and impeccable. "
        "If Gmail is connected, you can review and analyze recent inbox emails from the app's email cache."
    ),
    "pirate": (
        "You are ARIA, a smart home AI assistant who speaks like a pirate. "
        "Use pirate slang: 'Ahoy', 'Aye aye', 'matey', 'shiver me timbers', "
        "'Arrr', 'ye', 'landlubber', 'treasure'. Talk about the seas, "
        "adventures, and treasure. But still give accurate, helpful answers. "
        "If Gmail be connected, ye can read recent inbox emails from the app's cache and help with 'em."
    ),
    "sassy": (
        "You are ARIA, a smart home AI assistant with a sassy, witty personality. "
        "You're confident, a little dramatic, and love to throw shade (playfully). "
        "You serve looks AND knowledge. Think reality TV star who is secretly a genius. "
        "Use phrases like 'honey', 'sweetie', 'periodt', 'I said what I said', "
        "'not gonna lie'. You're fabulous and you know it. "
        "If Gmail is connected, you can read recent inbox emails from the app's email cache and help with them, hunty."
    ),
    "nerd": (
        "You are ARIA, a smart home AI assistant who is a total nerd/geek. "
        "You LOVE technical details, make references to sci-fi, gaming, anime, "
        "and pop culture. You get excited about science and tech. "
        "Use phrases like 'Actually...', 'Fun fact!', 'According to my calculations'. "
        "You're basically an excited encyclopedia who loves sharing knowledge. "
        "If Gmail is connected, you can analyze recent inbox emails from the app's email cache with technical precision."
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# LAMP CONTROL — Yeelight
# ═══════════════════════════════════════════════════════════════════════════

LAMP_MAC = os.environ.get("LAMP_MAC", "c4:93:bb:20:3a:29").lower().replace("-", ":")
LAMP_IP_FALLBACK = os.environ.get("LAMP_IP") or os.environ.get("YEELIGHT_IP") or os.environ.get("BULB_IP")


def _resolve_lamp_ip():
    """Resolve lamp IP from MAC via ARP table, fall back to env/hardcoded IP."""
    import subprocess
    mac_normalized = LAMP_MAC.replace(":", "-")
    try:
        out = subprocess.check_output("arp -a", shell=True, text=True, timeout=5)
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and mac_normalized in parts[1].lower():
                return parts[0]
    except Exception:
        pass
    return LAMP_IP_FALLBACK

LAMP_KEYWORDS  = ["lamp", "light", "bulb", "ламп", "свет", "шам", "жарық"]
LAMP_ON_WORDS  = ["turn on", "включ", "қос", "жағ"]
LAMP_OFF_WORDS = ["turn off", "выключ", "өшір", "сөндір"]
LAMP_RGB_WORDS = ["rgb", "rainbow", "радуг", "кемпірқосақ"]
LAMP_WARM_WORDS = ["warm", "тёпл", "жылы"]
LAMP_COOL_WORDS = ["cool", "холодн", "салқын"]
LAMP_COLOR_WORDS = {
    "red":    ["red", "красн", "қызыл"],
    "green":  ["green", "зелён", "жасыл"],
    "blue":   ["blue", "синий", "голубой", "көк"],
    "yellow": ["yellow", "жёлт", "сары"],
    "orange": ["orange", "оранж"],
    "purple": ["purple", "фиолет", "күлгін"],
    "pink":   ["pink", "розов", "қызғылт"],
    "cyan":   ["cyan", "бирюз"],
}


class AppBulbController:
    """Controls a Yeelight bulb; auto-reconnects on connection loss."""

    COLOR_MAP = {
        "red":    (255,   0,   0),
        "green":  (  0, 255,   0),
        "blue":   (  0,   0, 255),
        "yellow": (255, 255,   0),
        "orange": (255, 128,   0),
        "purple": (128,   0, 128),
        "pink":   (255, 105, 180),
        "cyan":   (  0, 255, 255),
    }

    def __init__(self, mac: str):
        self.mac = mac
        self.ip = None
        self._bulb = None
        self._state = {
            "mac": mac,
            "ip": None,
            "power": "off",
            "mode": "white",
            "color": None,
            "brightness": 80,
            "color_temp": 4000,
            "rgb_running": False,
        }
        self._rgb_thread = None
        self._rgb_stop = _threading.Event()
        self._lock = _threading.Lock()

    def _ensure(self):
        if self._bulb is None:
            ip = _resolve_lamp_ip()
            if not ip:
                raise RuntimeError(f"Cannot resolve lamp MAC {self.mac} to IP (not in ARP table)")
            self.ip = ip
            self._state["ip"] = ip
            try:
                from yeelight import Bulb
                self._bulb = Bulb(ip, auto_on=False)
                print(f"[LAMP] Connected via MAC {self.mac} -> IP {ip}", flush=True)
            except Exception as exc:
                raise RuntimeError(f"Cannot connect to lamp at {ip}: {exc}") from exc
        return self._bulb

    def turn_on_white(self, brightness: int = 80, color_temp: int = 4000):
        with self._lock:
            try:
                b = self._ensure()
                b.turn_on()
                b.set_brightness(int(brightness))
                b.set_color_temp(int(color_temp))
                self._state.update(power="on", mode="white", color=None,
                                   brightness=int(brightness), color_temp=int(color_temp))
            except Exception:
                self._bulb = None
                raise

    def turn_off(self):
        self.stop_rgb_cycle()
        with self._lock:
            try:
                b = self._ensure()
                b.turn_off()
                self._state.update(power="off", rgb_running=False)
            except Exception:
                self._bulb = None
                raise

    def toggle_white(self):
        if self._state["power"] == "on":
            self.turn_off()
        else:
            self.turn_on_white(self._state["brightness"], self._state["color_temp"])

    def set_color(self, color_name: str, brightness: int = 80):
        rgb = self.COLOR_MAP.get(color_name.lower())
        if rgb is None:
            raise ValueError(f"Unknown color: {color_name}")
        with self._lock:
            try:
                b = self._ensure()
                b.turn_on()
                b.set_rgb(*rgb)
                b.set_brightness(int(brightness))
                self._state.update(power="on", mode="color", color=color_name,
                                   brightness=int(brightness))
            except Exception:
                self._bulb = None
                raise

    def set_brightness(self, brightness: int):
        state = self.get_state()
        if state["mode"] == "color" and state.get("color"):
            self.set_color(state["color"], brightness=brightness)
        else:
            self.turn_on_white(brightness=brightness,
                               color_temp=state.get("color_temp", 4000))

    def start_rgb_cycle(self, interval_seconds: float = 2.0, brightness: int = 80):
        self.stop_rgb_cycle()
        self._rgb_stop.clear()

        def _cycle():
            colors = list(self.COLOR_MAP.keys())
            idx = 0
            while not self._rgb_stop.is_set():
                color = colors[idx % len(colors)]
                try:
                    with self._lock:
                        b = self._ensure()
                        b.turn_on()
                        b.set_rgb(*self.COLOR_MAP[color])
                        b.set_brightness(int(brightness))
                        self._state.update(power="on", mode="rgb", color=color,
                                           brightness=int(brightness), rgb_running=True)
                except Exception:
                    self._bulb = None
                idx += 1
                self._rgb_stop.wait(interval_seconds)
            self._state["rgb_running"] = False

        self._rgb_thread = _threading.Thread(target=_cycle, daemon=True, name="rgb-cycle")
        self._rgb_thread.start()

    def stop_rgb_cycle(self):
        self._rgb_stop.set()
        t = self._rgb_thread
        if t and t.is_alive():
            t.join(timeout=3)
        self._state["rgb_running"] = False

    def get_state(self) -> dict:
        return dict(self._state)


bulb_controller = AppBulbController(LAMP_MAC)


# ── Lamp helpers ─────────────────────────────────────────────────────────────

def _detect_lang(msg: str) -> str:
    """Detect RU / KZ / EN from message characters."""
    kz_chars = set("әіңғүұқөһ")
    if any(c in kz_chars for c in msg.lower()):
        return "kz"
    ru_chars = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
    if sum(1 for c in msg.lower() if c in ru_chars) > 2:
        return "ru"
    return "en"


def _extract_interval_seconds(msg: str) -> float:
    """Parse 'every 3 seconds' / 'каждые 2 минуты' → float seconds."""
    msg_l = msg.lower()
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:minute|min|минут|мин)', msg_l)
    if m:
        return float(m.group(1)) * 60
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:second|sec|секунд|сек)', msg_l)
    if m:
        return float(m.group(1))
    return 2.0


def _format_lamp_reply(state: dict, lang: str) -> str:
    power = state.get("power", "off")
    mode = state.get("mode", "white")
    color = state.get("color") or ""
    brightness = state.get("brightness", 80)
    color_temp = state.get("color_temp", 4000)

    COLOR_RU = {"red": "красный", "green": "зелёный", "blue": "синий",
                "yellow": "жёлтый", "orange": "оранжевый", "purple": "фиолетовый",
                "pink": "розовый", "cyan": "голубой"}
    COLOR_KZ = {"red": "қызыл", "green": "жасыл", "blue": "көк",
                "yellow": "сары", "orange": "қызғылт сары", "purple": "күлгін",
                "pink": "қызғылт", "cyan": "күлгін-жасыл"}

    if lang == "ru":
        if power == "off":
            return "Лампа выключена. 💡"
        if mode == "rgb":
            return f"RGB-цикл запущен! 🌈 Яркость: {brightness}%"
        if mode == "color" and color:
            return f"Цвет: {COLOR_RU.get(color, color)}, яркость {brightness}%. 🎨"
        temp_str = f"{color_temp}K"
        return f"Лампа включена. Яркость: {brightness}%, температура: {temp_str}. 💡"
    if lang == "kz":
        if power == "off":
            return "Шам өшірілді. 💡"
        if mode == "rgb":
            return f"RGB-цикл іске қосылды! 🌈 Жарықтық: {brightness}%"
        if mode == "color" and color:
            return f"Түс: {COLOR_KZ.get(color, color)}, жарықтық {brightness}%. 🎨"
        return f"Шам жағылды. Жарықтық: {brightness}%. 💡"
    # EN
    if power == "off":
        return "Light turned off. 💡"
    if mode == "rgb":
        return f"RGB cycle started! 🌈 Brightness: {brightness}%"
    if mode == "color" and color:
        return f"Color set to {color}, brightness {brightness}%. 🎨"
    return f"Light on. Brightness: {brightness}%, color temp: {color_temp}K. 💡"


def _handle_lamp_command(message: str):
    """
    Parse a user message and execute lamp command if detected.
    Returns (reply_str, lamp_state_dict) or (None, None).
    """
    msg_l = message.lower()
    if not any(kw in msg_l for kw in LAMP_KEYWORDS):
        return None, None

    lang = _detect_lang(message)
    try:
        # Color first (most specific)
        for color, keywords in LAMP_COLOR_WORDS.items():
            if any(kw in msg_l for kw in keywords):
                bulb_controller.set_color(color, brightness=80)
                state = bulb_controller.get_state()
                return _format_lamp_reply(state, lang), state

        # RGB cycle
        if any(kw in msg_l for kw in LAMP_RGB_WORDS):
            interval = _extract_interval_seconds(message)
            bulb_controller.start_rgb_cycle(interval_seconds=interval, brightness=80)
            state = bulb_controller.get_state()
            return _format_lamp_reply(state, lang), state

        # Stop RGB
        if any(kw in msg_l for kw in LAMP_OFF_WORDS) and bulb_controller.get_state()["rgb_running"]:
            bulb_controller.stop_rgb_cycle()
            state = bulb_controller.get_state()
            return _format_lamp_reply(state, lang), state

        # Warm white
        if any(kw in msg_l for kw in LAMP_WARM_WORDS):
            bulb_controller.turn_on_white(brightness=80, color_temp=2700)
            state = bulb_controller.get_state()
            return _format_lamp_reply(state, lang), state

        # Cool white
        if any(kw in msg_l for kw in LAMP_COOL_WORDS):
            bulb_controller.turn_on_white(brightness=80, color_temp=6500)
            state = bulb_controller.get_state()
            return _format_lamp_reply(state, lang), state

        # Turn off
        if any(kw in msg_l for kw in LAMP_OFF_WORDS):
            bulb_controller.turn_off()
            state = bulb_controller.get_state()
            return _format_lamp_reply(state, lang), state

        # Turn on
        if any(kw in msg_l for kw in LAMP_ON_WORDS):
            bulb_controller.turn_on_white(brightness=80)
            state = bulb_controller.get_state()
            return _format_lamp_reply(state, lang), state

        # Generic mention → toggle
        bulb_controller.toggle_white()
        state = bulb_controller.get_state()
        return _format_lamp_reply(state, lang), state

    except Exception as exc:
        msgs = {
            "ru": f"Не удалось управлять лампой: {exc}",
            "kz": f"Шамды басқару мүмкін болмады: {exc}",
            "en": f"Could not control the lamp: {exc}",
        }
        return msgs.get(lang, msgs["en"]), None


# ═══════════════════════════════════════════════════════════════════════════

OWM_KEY = os.environ.get("OWM_KEY", "")
OWM_BASE = "https://api.openweathermap.org/data/2.5"

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

WEATHER_KEYWORDS = [
    # English
    "weather", "temperature", "forecast", "wind", "humidity", "rain", "snow", "storm",
    "how cold", "how hot", "how warm", "will it rain", "will it snow", "umbrella",
    "sunny", "cloudy", "foggy", "hail", "thunder", "lightning", "drizzle",
    # Russian
    "погода", "температура", "прогноз", "ветер", "влажность", "дождь", "снег",
    "гроза", "туман", "облачно", "солнечно", "ливень", "жара", "мороз", "похолодание",
    "какая погода", "сколько градусов", "что с погодой", "будет ли дождь",
    "будет ли снег", "взять зонт", "тепло ли", "холодно ли",
    # Kazakh
    "ауа райы", "болжам", "жел", "ылғалдылық", "жаңбыр", "қар",
]

# Remembers the last city the user asked about so follow-up questions work
_last_weather_city = "Almaty"


WIND_DIRS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def _wind_dir(deg):
    if deg is None:
        return ""
    return WIND_DIRS[round(deg / 22.5) % 16]


def _epoch_to_hhmm(epoch, tz_offset):
    dt = datetime.utcfromtimestamp(epoch + tz_offset)
    return dt.strftime("%I:%M %p")


def _epoch_to_localtime(epoch, tz_offset):
    dt = datetime.utcfromtimestamp(epoch + tz_offset)
    return dt.strftime("%Y-%m-%d %H:%M")


def _parse_email_date(date_str: str) -> datetime:
    """Parse RFC 2822 email Date header → UTC naive datetime."""
    if not date_str:
        return datetime.utcnow()
    try:
        import datetime as _dt
        dt = _email_parsedate_raw(date_str.strip())
        if dt.tzinfo is not None:
            dt = dt.astimezone(_dt.timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        for fmt in ('%a, %d %b %Y %H:%M:%S', '%d %b %Y %H:%M:%S'):
            try:
                import re as _re
                clean = _re.sub(r'\s+[+-]\d{4}.*$', '', date_str.strip())
                clean = _re.sub(r'\s+\([A-Z]+\)$', '', clean).strip()
                return datetime.strptime(clean, fmt)
            except Exception:
                continue
        return datetime.utcnow()


def _tz_id_str(tz_seconds):
    """Convert UTC offset in seconds to 'UTC+H' or 'UTC+H:MM' string.
    Handles fractional offsets (India +5:30, Nepal +5:45, Iran +3:30, etc.)
    and negative offsets correctly."""
    sign = '+' if tz_seconds >= 0 else '-'
    total_minutes = abs(tz_seconds) // 60
    h, m = divmod(total_minutes, 60)
    if m:
        return f"UTC{sign}{h}:{m:02d}"
    return f"UTC{sign}{h}"


def fetch_weather(city):
    if not OWM_KEY:
        return None
    # Try normalized name first, then fall back to raw city string
    candidates = [_normalize_city(city)]
    if city not in candidates:
        candidates.append(city)
    # Also try just the first word in case extra words slipped through
    first_word = city.split()[0] if ' ' in city else None
    if first_word and _normalize_city(first_word) not in candidates:
        candidates.append(_normalize_city(first_word))

    for attempt_city in candidates:
        try:
            resp = requests.get(
                f"{OWM_BASE}/weather",
                params={"q": attempt_city, "appid": OWM_KEY, "units": "metric"},
                timeout=10,
            )
            if resp.status_code != 200:
                continue
            d = resp.json()
            tz = d.get("timezone", 0)
            wind = d.get("wind", {})
            wind_speed_ms = wind.get("speed", 0)
            wind_kph = round(wind_speed_ms * 3.6, 1)
            vis_m = d.get("visibility", 10000)
            return {
                "city": d.get("name", attempt_city),
                "country": d.get("sys", {}).get("country", ""),
                "localtime": _epoch_to_localtime(d["dt"], tz),
                "localtime_epoch": d["dt"] + tz,
                "tz_id": _tz_id_str(tz),
                "last_updated": _epoch_to_localtime(d["dt"], tz),
                "temp": round(d["main"]["temp"]),
                "feels_like": round(d["main"]["feels_like"]),
                "temp_min": round(d["main"]["temp_min"]),
                "temp_max": round(d["main"]["temp_max"]),
                "humidity": d["main"]["humidity"],
                "pressure": d["main"]["pressure"],
                "wind_kph": round(wind_kph),
                "wind_deg": wind.get("deg", 0),
                "wind_dir": _wind_dir(wind.get("deg")),
                "vis_km": round(vis_m / 1000, 1),
                "clouds": d.get("clouds", {}).get("all", 0),
                "description": d["weather"][0]["description"].title() if d.get("weather") else "",
                "icon": d["weather"][0]["icon"] if d.get("weather") else "03d",
                "sunrise": _epoch_to_hhmm(d["sys"]["sunrise"], tz) if d.get("sys", {}).get("sunrise") else "",
                "sunset": _epoch_to_hhmm(d["sys"]["sunset"], tz) if d.get("sys", {}).get("sunset") else "",
            }
        except Exception:
            continue
    return None

def fetch_forecast(city):
    if not OWM_KEY:
        return None
    city = _normalize_city(city)
    try:
        resp = requests.get(
            f"{OWM_BASE}/forecast",
            params={"q": city, "appid": OWM_KEY, "units": "metric"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        d = resp.json()
        city_info = d.get("city", {})
        tz = city_info.get("timezone", 0)
        items = []
        for entry in d.get("list", []):
            wind_ms = entry.get("wind", {}).get("speed", 0)
            icon = entry["weather"][0]["icon"] if entry.get("weather") else "03d"
            local_epoch = entry["dt"] + tz
            local_dt = datetime.utcfromtimestamp(local_epoch)
            items.append({
                "dt": local_epoch,
                "local_time": local_dt.strftime("%Y-%m-%d %H:%M"),
                "date": local_dt.strftime("%Y-%m-%d"),
                "temp": entry["main"]["temp"],
                "feels_like": entry["main"]["feels_like"],
                "humidity": entry["main"]["humidity"],
                "wind_kph": round(wind_ms * 3.6, 1),
                "icon": icon,
                "description": entry["weather"][0]["description"].title() if entry.get("weather") else "",
            })
        now_local = int(datetime.utcnow().timestamp()) + tz
        return {
            "city": city_info.get("name", city),
            "country": city_info.get("country", ""),
            "localtime_epoch": now_local,
            "forecast": items,
        }
    except Exception:
        return None


# Russian prepositional/locative city forms → OWM-recognized name
_CITY_NORM = {
    "алмате": "Almaty", "алматы": "Almaty", "алма-ате": "Almaty", "алма-аты": "Almaty",
    "астане": "Astana", "астана": "Astana", "нур-султане": "Astana",
    "шымкенте": "Shymkent", "шымкент": "Shymkent",
    "москве": "Moscow", "москва": "Moscow",
    "питере": "Saint Petersburg", "петербурге": "Saint Petersburg",
    "санкт-петербурге": "Saint Petersburg", "санкт-петербург": "Saint Petersburg",
    "новосибирске": "Novosibirsk", "екатеринбурге": "Yekaterinburg",
    "лондоне": "London", "париже": "Paris", "берлине": "Berlin",
    "нью-йорке": "New York", "токио": "Tokyo", "пекине": "Beijing",
    "дубае": "Dubai", "стамбуле": "Istanbul",
    "киеве": "Kyiv", "минске": "Minsk", "ташкенте": "Tashkent",
    "бишкеке": "Bishkek", "тбилиси": "Tbilisi", "баку": "Baku", "ереване": "Yerevan",
    "риге": "Riga", "вильнюсе": "Vilnius", "таллине": "Tallinn",
}


def _normalize_city(city: str) -> str:
    """Convert Russian declined city forms to OWM-compatible names."""
    key = city.lower().strip()
    if key in _CITY_NORM:
        return _CITY_NORM[key]
    # Generic fallback: Russian prepositional case often ends in -е; try stripping it
    if key.endswith("е") and len(key) > 4:
        candidate = key[:-1]
        # try with -и suffix (е→и) and without suffix
        for c in (candidate + "и", candidate + "ы", candidate):
            if c in _CITY_NORM:
                return _CITY_NORM[c]
    return city


def detect_weather_query(message):
    global _last_weather_city
    msg = message.lower()
    if not any(kw in msg for kw in WEATHER_KEYWORDS):
        return None

    city_patterns = [
        # English: stop at word boundary / punctuation
        r"weather\s+(?:in|at|for)\s+([a-zA-Z][a-zA-Z\s\-]{1,30})(?:\?|$|\.|,|\s+(?:now|today|tonight|tomorrow))",
        r"(?:in|at|for)\s+([a-zA-Z][a-zA-Z\s\-]{1,20})(?:\?|$|\.|,)",
        # Russian: capture only Cyrillic + hyphens (no spaces) to avoid grabbing trailing words
        r"погод[аеу]\s+(?:в|во)\s+([а-яА-ЯёЁ][а-яА-ЯёЁ\-]+)",
        r"температур[аеу]\s+(?:в|во)\s+([а-яА-ЯёЁ][а-яА-ЯёЁ\-]+)",
        r"(?:в|во)\s+([а-яА-ЯёЁ][а-яА-ЯёЁ\-]+)\s+(?:сейчас|сегодня|погода|температура|прогноз)",
        r"(?:в|во)\s+([а-яА-ЯёЁ][а-яА-ЯёЁ\-]+?)(?:\?|$|\.)",
        # Kazakh
        r"ауа райы\s+([а-яА-ЯёЁәіңғүұқөһa-zA-Z\-]+)",
    ]
    for pattern in city_patterns:
        m = re.search(pattern, msg, re.IGNORECASE)
        if m:
            city = m.group(1).strip().rstrip("?., ")
            if len(city) > 1:
                found = _normalize_city(city)
                _last_weather_city = found
                return found

    # No city found in message — use the last city the user asked about
    return _last_weather_city


@app.route("/")
def index():
    return render_template("index.html")


def _gemini_call(model, system_text, contents):
    global _gemini_key_index
    last_error = ""
    for _attempt in range(len(GEMINI_API_KEYS)):
        key = GEMINI_API_KEYS[_gemini_key_index]
        url = f"{GEMINI_BASE}/models/{model}:generateContent?key={key}"
        payload = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system_text}]},
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048,
            },
        }
        try:
            resp = requests.post(url, json=payload, timeout=60)
            resp_data = resp.json()
            if resp.status_code == 200 and "candidates" in resp_data:
                parts = resp_data["candidates"][0]["content"]["parts"]
                text_parts = [p["text"] for p in parts if "text" in p and "thought" not in p]
                return "".join(text_parts), None
            error = resp_data.get("error", {})
            status = error.get("status", "")
            msg = error.get("message", str(resp_data))
            if status in ("RESOURCE_EXHAUSTED", "RATE_LIMIT_EXCEEDED") or resp.status_code == 429:
                last_error = msg
                _gemini_key_index = (_gemini_key_index + 1) % len(GEMINI_API_KEYS)
                continue
            return None, f"API error ({resp.status_code}): {msg}"
        except Exception as e:
            last_error = str(e)
            _gemini_key_index = (_gemini_key_index + 1) % len(GEMINI_API_KEYS)
            continue
    return None, f"All API keys exhausted. Last error: {last_error}"


def get_recent_emails(limit=5):
    """Fetch recent emails from the database for context."""
    try:
        from models import EmailMessage, GmailAccount

        # Prefer the currently-authenticated Gmail account, if available.
        q = EmailMessage.query
        gmail_email = _resolve_gmail_email()
        if gmail_email:
            acct = GmailAccount.query.filter_by(email=gmail_email).first()
            if acct:
                q = q.filter_by(account_id=acct.id)

        # Get recent emails ordered by received_at
        emails = q.order_by(EmailMessage.received_at.desc()).limit(limit).all()
        
        if not emails:
            return None
        
        email_context = "\n\n[RECENT EMAILS FROM YOUR INBOX]\n"
        for i, email in enumerate(emails, 1):
            email_context += f"\n--- Email {i} ---\n"
            email_context += f"Subject: {email.subject}\n"
            email_context += f"From: {email.sender}\n"
            email_context += f"Date: {email.received_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            if email.body:
                # Limit body to 500 chars per email to avoid token overflow
                body_preview = email.body[:500]
                if len(email.body) > 500:
                    body_preview += "...[truncated]"
                email_context += f"Content: {body_preview}\n"
        
        email_context += "\n\nYou can help the user with any questions about these emails."
        return email_context
    except Exception as e:
        print(f"Error fetching emails from database: {e}")
        return None


def _auto_sync_cached_emails_for_chat(max_results: int = 50) -> int:
    """Best-effort: sync a small batch of inbox metadata into the local cache.

    This is intentionally limited and only used to let the assistant "see" emails
    without requiring the user to press Sync in the UI.
    """
    try:
        from models import EmailMessage, GmailAccount

        gmail_email = _resolve_gmail_email()
        if not gmail_email or not gmail_service.is_authenticated(gmail_email):
            return 0

        gmail_account = GmailAccount.query.filter_by(email=gmail_email).first()
        if not gmail_account:
            return 0

        # Small, safe window: inbox only. Keep it capped for latency.
        query = 'in:inbox'
        result = gmail_service.get_emails_for_sync(
            query=query,
            max_results=max(1, min(int(max_results), 200)),
            email=gmail_email,
        )
        if not result or 'error' in result:
            return 0

        added = 0
        for email_data in result.get('emails', []):
            gmail_id = email_data.get('id', '')
            if not gmail_id:
                continue

            date_str = email_data.get('date', '')
            received_at = email_data.get('date_dt') or _parse_email_date(date_str)
            is_read = email_data.get('is_read', False)
            snippet = email_data.get('snippet', '')

            existing = EmailMessage.query.filter_by(
                gmail_id=gmail_id, account_id=gmail_account.id
            ).first()
            if existing:
                continue

            db.session.add(EmailMessage(
                gmail_id=gmail_id,
                account_id=gmail_account.id,
                sender=email_data.get('from', 'Unknown'),
                subject=email_data.get('subject', '(No Subject)'),
                body=snippet,
                received_at=received_at,
                is_read=is_read,
            ))
            added += 1

        if added:
            db.session.commit()
        return added
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return 0


def _detect_message_lang(message: str) -> str:
    msg = (message or "").lower()
    kz_markers = ["қ", "ғ", "ә", "ң", "ө", "ұ", "ү", "һ", "ауа райы", "кімнен", "қашан"]
    ru_markers = ["погода", "почта", "письм", "когда", "кто", "от кого", "время", "суть"]
    if any(m in msg for m in kz_markers):
        return "kz"
    if any(m in msg for m in ru_markers) or re.search(r"[а-яё]", msg):
        return "ru"
    return "en"


def _is_email_query(message: str) -> bool:
    msg = (message or "").lower()
    email_words = [
        "email", "mail", "inbox", "letter", "message",
        "почта", "письмо", "письма", "емайл", "сообщение",
        "хат", "пошта", "письм",
    ]
    return any(w in msg for w in email_words)


def _extract_sender_hint(message: str) -> str:
    msg = (message or "").strip()
    patterns = [
        r"from\s+([^\?\.,\n]+)",
        r"от\s+([^\?\.,\n]+)",
        r"кімнен\s+([^\?\.,\n]+)",
    ]
    for p in patterns:
        m = re.search(p, msg, re.IGNORECASE)
        if m:
            return m.group(1).strip().strip('"\'')
    return ""


def _clean_email_preview(text: str, limit: int = 220) -> str:
    """Turn an email body/snippet into a short, readable preview."""
    if not text:
        return ""
    t = str(text)
    # Remove very common HTML noise (snippets sometimes contain HTML)
    try:
        t = re.sub(r"<[^>]+>", " ", t)
    except Exception:
        pass
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > limit:
        return t[:limit].rstrip() + "..."
    return t


def _pretty_sender_name(sender_raw: str) -> str:
    """Extract a friendly sender name from 'Name <email>' style strings."""
    s = (sender_raw or "").strip()
    if not s:
        return "Unknown"
    m = re.match(r'^\s*"?([^"<]+?)"?\s*<[^>]+>\s*$', s)
    if m:
        return m.group(1).strip()
    # If it's just an email, return the local-part or the full string
    if "@" in s and "<" not in s and ">" not in s:
        return s.split("@", 1)[0].strip() or s
    return s


def _relative_received_label(dt: datetime, lang: str = "en") -> str:
    """Human-friendly day label (today / yesterday / Apr 8)."""
    try:
        now = datetime.utcnow()
        if not dt:
            return "today" if lang == "en" else "today"
        days = (now.date() - dt.date()).days
        if days <= 0:
            return {"ru": "сегодня", "kz": "бүгін"}.get(lang, "today")
        if days == 1:
            return {"ru": "вчера", "kz": "кеше"}.get(lang, "yesterday")
        # keep short; don't include year
        return dt.strftime("%b %d").replace(" 0", " ")
    except Exception:
        return {"ru": "недавно", "kz": "жуырда"}.get(lang, "recently")


def _gemini_email_summary(sender: str, subject: str, body: str, lang: str = "en") -> str:
    """Use Gemini to generate a friendly 1-sentence summary."""
    model = settings.get("model", "gemini-2.0-flash")
    sender_name = _pretty_sender_name(sender)
    body_ctx = _clean_email_preview(body or "", limit=1200)

    if lang == "ru":
        lang_instruction = "Отвечай на русском языке."
    elif lang == "kz":
        lang_instruction = "Қазақ тілінде жауап бер."
    else:
        lang_instruction = "Reply in English."

    prompt_system = (
        "You are an assistant summarizing an email for the user.\n"
        "Goal: produce ONE friendly sentence that explains what the email is about.\n"
        "Constraints:\n"
        "- Do NOT include timestamps or technical headers.\n"
        "- Do NOT paste the raw email body.\n"
        "- Keep it short (max ~25 words).\n"
        "- If content is unclear, summarize based on the subject and snippet.\n"
        f"{lang_instruction}\n\n"
        f"[EMAIL]\n"
        f"From: {sender_name}\n"
        f"Subject: {subject}\n"
        f"Snippet:\n{body_ctx}\n"
    )

    contents = [{"role": "user", "parts": [{"text": "Write the 1-sentence summary now."}]}]
    try:
        txt, err = _gemini_call(model, prompt_system, contents)
        if err or not txt:
            return ""
        return re.sub(r"\s+", " ", txt).strip()
    except Exception:
        return ""


def _format_email_pretty(sender: str, subject: str, received_at: datetime, body: str, lang: str, include_exact_time: bool) -> str:
    sender_name = _pretty_sender_name(sender)
    rel = _relative_received_label(received_at, lang=lang)

    # Smart summarization (LLM), fallback to cleaned preview
    summary = _gemini_email_summary(sender=sender, subject=subject, body=body, lang=lang)
    if not summary:
        summary = _clean_email_preview(body or "", limit=160) or subject

    # Received label
    if include_exact_time and received_at:
        received_line = received_at.strftime("%Y-%m-%d %H:%M")
    else:
        received_line = rel

    if lang == "ru":
        received_text = f"Получено: {received_line}"
        summary_label = "Кратко"
        from_label = "От"
        subject_label = "Тема"
    elif lang == "kz":
        received_text = f"Қабылданған уақыты: {received_line}"
        summary_label = "Қысқаша"
        from_label = "Кімнен"
        subject_label = "Тақырып"
    else:
        received_text = f"Received: {('today' if received_line == 'today' else received_line)}"
        summary_label = "Summary"
        from_label = "From"
        subject_label = "Subject"

    return (
        f"{from_label}: {sender_name}\n\n"
        f"{subject_label}: {subject}\n\n"
        f"{summary_label}: {summary}\n\n"
        f"{received_text}"
    )


def _get_cached_emails_for_chat(limit: int = 50):
    gmail_email = _resolve_gmail_email()
    if not gmail_email:
        return []
    acct = GmailAccount.query.filter_by(email=gmail_email).first()
    if not acct:
        return []
    return (EmailMessage.query
            .filter_by(account_id=acct.id)
            .order_by(EmailMessage.received_at.desc())
            .limit(limit)
            .all())


def _format_email_direct_reply(message: str, email_data=None):
    msg = (message or "").lower()
    lang = _detect_message_lang(message)

    ask_sender = any(x in msg for x in ["from who", "who sent", "от кого", "кто отправ", "кімнен"])
    ask_time = any(x in msg for x in ["when", "time", "когда", "во сколько", "время", "қашан"])
    ask_summary = any(x in msg for x in ["summary", "about", "what is it about", "суть", "о чем", "не туралы", "мазмұн"])
    ask_last = any(x in msg for x in ["latest", "last", "recent", "послед", "соңғы"])
    ask_list = any(x in msg for x in [
        "list", "show emails", "show my emails", "recent emails", "inbox list",
        "список", "покажи письма", "письма список", "сообщения список",
        "тізім", "хаттар тізімі",
    ])

    if email_data:
        sender = email_data.get("from", "Unknown")
        subject = email_data.get("subject", "(No subject)")
        body = (email_data.get("body") or "").strip()
        # date may be a string; keep it only if explicitly requested
        received_at = datetime.utcnow()
        return _format_email_pretty(
            sender=sender,
            subject=subject,
            received_at=received_at,
            body=body,
            lang=lang,
            include_exact_time=bool(ask_time),
        )

    emails = _get_cached_emails_for_chat(limit=80)
    if not emails:
        # If Gmail is connected but the cache is empty, do a small on-demand sync
        # so the assistant can "see" the inbox without extra UI actions.
        _auto_sync_cached_emails_for_chat(max_results=30)
        emails = _get_cached_emails_for_chat(limit=80)

    if not emails:
        if lang == "ru":
            return "Я не вижу писем в локальном кэше. Сначала синхронизируйте Gmail (Sync All)."
        if lang == "kz":
            return "Жергілікті кэште хаттар жоқ. Алдымен Gmail синхрондаңыз (Sync All)."
        return "I cannot see cached emails yet. Please sync Gmail first (Sync All)."

    sender_hint = _extract_sender_hint(message).lower()
    if sender_hint:
        emails = [e for e in emails if sender_hint in (e.sender or "").lower() or sender_hint in (e.subject or "").lower()]
        if not emails:
            if lang == "ru":
                return f"По фильтру '{sender_hint}' писем не найдено в кэше."
            if lang == "kz":
                return f"'{sender_hint}' бойынша хат табылмады."
            return f"No cached emails matched '{sender_hint}'."

    top = emails[:5]
    first = top[0]
    body_short = first.body or ""

    # Default behavior: pretty latest email (friendly + structured).
    if not ask_list:
        return _format_email_pretty(
            sender=first.sender,
            subject=first.subject,
            received_at=first.received_at,
            body=body_short,
            lang=lang,
            include_exact_time=bool(ask_time),
        )

    # List view (still readable). Keep it short.
    lines = []
    for e in top[:5]:
        sender_name = _pretty_sender_name(e.sender or "Unknown")
        rel = _relative_received_label(e.received_at, lang=lang)
        if ask_time:
            rel = e.received_at.strftime("%Y-%m-%d %H:%M")
        lines.append(f"- {sender_name} — {e.subject} ({rel})")
    if lang == "ru":
        return "Последние письма:\n" + "\n".join(lines)
    if lang == "kz":
        return "Соңғы хаттар:\n" + "\n".join(lines)
    return "Recent emails:\n" + "\n".join(lines)


def _build_weather_context(current: dict, forecast: dict) -> str:
    """Serialize current weather + 48h forecast into a compact text block for Gemini."""
    lines = []
    if current:
        city = current.get("city", "?")
        country = current.get("country", "")
        lines.append(f"=== Current weather in {city}, {country} ===")
        lines.append(f"Time: {current.get('localtime', 'N/A')} ({current.get('tz_id', '')})")
        lines.append(f"Temperature: {current.get('temp')}°C, feels like {current.get('feels_like')}°C")
        lines.append(f"Condition: {current.get('description', 'N/A')}")
        lines.append(f"Humidity: {current.get('humidity')}%")
        lines.append(f"Wind: {current.get('wind_kph')} km/h {current.get('wind_dir', '')}")
        lines.append(f"Clouds: {current.get('clouds')}%")
        lines.append(f"Visibility: {current.get('vis_km')} km")
        lines.append(f"Pressure: {current.get('pressure')} hPa")
        lines.append(f"Sunrise: {current.get('sunrise')}  Sunset: {current.get('sunset')}")

    if forecast and forecast.get("forecast"):
        lines.append("\n=== 48-hour forecast (3-hour steps) ===")
        for entry in forecast["forecast"][:16]:  # 16 × 3h = 48 hours
            lines.append(
                f"{entry['local_time']}  {round(entry['temp'])}°C  {entry['description']}  "
                f"Wind {round(entry['wind_kph'])} km/h  Humidity {entry['humidity']}%"
            )
    return "\n".join(lines)


def _format_weather_ai_reply(message: str, current: dict, forecast: dict, model: str, system_text: str) -> str:
    """Ask Gemini to answer the user's weather question using live data."""
    lang = _detect_message_lang(message)
    if not current:
        if not OWM_KEY:
            if lang == "ru":
                return "Погода не настроена на сервере (не задан OWM_KEY). Укажите ключ OpenWeatherMap и перезапустите приложение."
            if lang == "kz":
                return "Ауа райы серверде бапталмаған (OWM_KEY орнатылмаған). OpenWeatherMap кілтін қойып, қолданбаны қайта іске қосыңыз."
            return "Weather is not configured on the server (OWM_KEY is missing). Set the OpenWeatherMap API key and restart the app."
        if lang == "ru":
            return "Не удалось получить погоду. Проверьте название города."
        if lang == "kz":
            return "Ауа райын алу мүмкін болмады. Қала атауын тексеріңіз."
        return "Could not fetch weather for that city. Please check the city name."

    weather_ctx = _build_weather_context(current, forecast)

    if lang == "ru":
        lang_instruction = "Отвечай на русском языке."
    elif lang == "kz":
        lang_instruction = "Қазақ тілінде жауап бер."
    else:
        lang_instruction = "Reply in English."

    prompt_system = (
        f"{system_text}\n\n"
        f"You have access to real-time weather data provided below. "
        f"When answering a general weather question ('what is the weather', 'какая погода'), "
        f"ALWAYS include ALL of these fields in your reply (same as a weather widget): "
        f"temperature, feels like, condition, humidity, wind speed & direction, "
        f"pressure, visibility, clouds %, sunrise & sunset. "
        f"When the user asks a specific question (rain tomorrow, should I take umbrella, "
        f"forecast for the week, etc.) — answer that specifically AND still mention "
        f"the most relevant data points. "
        f"Format numbers the same way as the data (already rounded integers). "
        f"Be natural and conversational, not a raw data dump. "
        f"{lang_instruction}\n\n"
        f"[LIVE WEATHER DATA]\n{weather_ctx}"
    )

    contents = [{"role": "user", "parts": [{"text": message}]}]
    ai_text, err = _gemini_call(model, prompt_system, contents)
    if err or not ai_text:
        # Graceful fallback to structured reply if Gemini fails
        city = current.get("city", "?")
        country = current.get("country", "")
        temp = current.get("temp")
        feels = current.get("feels_like")
        cond = current.get("description", "N/A")
        hum = current.get("humidity")
        wind = current.get("wind_kph")
        wind_dir = current.get("wind_dir", "")
        if lang == "ru":
            return (f"Погода в {city}, {country}:\n"
                    f"🌡 {temp}°C (ощущается {feels}°C) — {cond}\n"
                    f"💧 Влажность: {hum}%   💨 Ветер: {wind} км/ч {wind_dir}")
        return (f"Weather in {city}, {country}:\n"
                f"🌡 {temp}°C (feels {feels}°C) — {cond}\n"
                f"💧 Humidity: {hum}%   💨 Wind: {wind} km/h {wind_dir}")
    return ai_text


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    email_data = data.get("email", None)
    sid = _get_chat_session_id()

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    _save_chat_msg(sid, "user", user_message)

    try:
        model = settings.get("model", "gemini-2.0-flash")

        personality = settings.get("personality", "default")
        system_text = PERSONALITY_PROMPTS.get(personality, PERSONALITY_PROMPTS["default"])
        if context_memory:
            memory_text = "\n".join(f"- {m['text']}" for m in context_memory)
            system_text += f"\n\nContext memory:\n{memory_text}"

        if email_data:
            email_context = "\n\n[CURRENT EMAIL CONTEXT]\n"
            for k in ("subject", "from", "to", "date"):
                if email_data.get(k):
                    email_context += f"{k.title()}: {email_data[k]}\n"
            if email_data.get("body"):
                email_context += f"Content:\n{email_data['body']}\n"
            email_context += "\nYou can help analyze, summarize, reply to, or perform actions related to this email."
            system_text += email_context
        else:
            recent_emails = get_recent_emails(limit=10)
            if recent_emails:
                system_text += recent_emails

        # ── Lamp command interception ─────────────────────────────────────
        lamp_reply, lamp_st = _handle_lamp_command(user_message)
        if lamp_reply:
            _save_chat_msg(sid, "assistant", lamp_reply)
            resp_data = {"reply": lamp_reply}
            if lamp_st:
                resp_data["lamp"] = lamp_st
            return jsonify(resp_data)

        # ── Email query interception ──────────────────────────────────────
        if _is_email_query(user_message):
            email_reply = _format_email_direct_reply(user_message, email_data=email_data)
            _save_chat_msg(sid, "assistant", email_reply)
            return jsonify({"reply": email_reply})

        # ── Weather query interception ────────────────────────────────────
        weather_city = detect_weather_query(user_message)
        if weather_city:
            w = fetch_weather(weather_city)
            fc = fetch_forecast(weather_city)
            weather_reply = _format_weather_ai_reply(user_message, w, fc, model, system_text)
            _save_chat_msg(sid, "assistant", weather_reply)
            return jsonify({"reply": weather_reply})

        # ── Build Gemini conversation from DB history ─────────────────────
        db_msgs = (ChatMessage.query
                   .filter_by(session_id=sid)
                   .order_by(ChatMessage.created_at.desc())
                   .limit(30)
                   .all())
        db_msgs.reverse()

        contents = []
        for m in db_msgs:
            role = "user" if m.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m.text}]})

        ai_text, err = _gemini_call(model, system_text, contents)
        if err:
            ai_text = err
    except Exception as e:
        ai_text = f"Connection error: {str(e)}"

    _save_chat_msg(sid, "assistant", ai_text)
    return jsonify({"reply": ai_text})


@app.route("/api/chat/history", methods=["GET"])
def chat_history_get():
    """Return chat history for the current session (newest last)."""
    sid = _get_chat_session_id()
    limit = min(int(request.args.get("limit", 100)), 500)
    msgs = (ChatMessage.query
            .filter_by(session_id=sid)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
            .all())
    return jsonify({"messages": [m.to_dict() for m in msgs]})


@app.route("/api/chat/history", methods=["DELETE"])
def chat_history_clear():
    """Clear all chat history for the current session."""
    sid = _get_chat_session_id()
    ChatMessage.query.filter_by(session_id=sid).delete()
    db.session.commit()
    chat_history.clear()
    return jsonify({"status": "ok"})


@app.route("/api/weather", methods=["GET"])
def weather():
    city = request.args.get("city", "Almaty")
    w = fetch_weather(city)
    if w:
        return jsonify(w)
    return jsonify({"error": "City not found or API error"}), 404


@app.route("/api/forecast", methods=["GET"])
def forecast():
    city = request.args.get("city", "Almaty")
    data = fetch_forecast(city)
    if data:
        return jsonify(data)
    return jsonify({"error": "City not found or API error"}), 404


@app.route("/api/quick-action", methods=["POST"])
def quick_action():
    data = request.get_json() or {}
    action = data.get("action", "")

    if action == "robot":
        return jsonify({"status": "success", "message": "Robot called"})

    if not action.startswith("light"):
        return jsonify({"status": "error", "message": "Unknown action"}), 400

    try:
        brightness = int(data.get("brightness", bulb_controller.get_state()["brightness"]))

        if action == "light":
            bulb_controller.toggle_white()
        elif action == "light_on":
            bulb_controller.turn_on_white(brightness=brightness)
        elif action == "light_off":
            bulb_controller.turn_off()
        elif action == "light_warm":
            bulb_controller.turn_on_white(brightness=brightness, color_temp=2700)
        elif action == "light_daylight":
            bulb_controller.turn_on_white(brightness=brightness, color_temp=4000)
        elif action == "light_cool":
            bulb_controller.turn_on_white(brightness=brightness, color_temp=6500)
        elif action == "light_color":
            color = data.get("color", "white")
            bulb_controller.set_color(color, brightness=brightness)
        elif action == "light_brightness":
            bulb_controller.set_brightness(brightness)
        elif action == "light_rgb":
            interval = float(data.get("interval", 2))
            bulb_controller.start_rgb_cycle(interval_seconds=interval, brightness=brightness)
        elif action == "light_rgb_stop":
            bulb_controller.stop_rgb_cycle()
        else:
            return jsonify({"status": "error", "message": f"Unknown lamp action: {action}"}), 400

        return jsonify({"status": "success", "lamp": bulb_controller.get_state()})

    except Exception as exc:
        return jsonify({
            "status": "error",
            "message": str(exc),
            "lamp": bulb_controller.get_state(),
        }), 500


@app.route("/api/lamp-state", methods=["GET"])
def lamp_state():
    return jsonify(bulb_controller.get_state())


@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify({
        **settings,
        "wake_word": _wake_word_enabled,
        "audio_source": settings.get("audio_source", "esp32"),
        "mic_denoise": settings.get("mic_denoise", MIC_DENOISE_MODE),
        "api_keys_count": len(GEMINI_API_KEYS),
        "current_key_index": _gemini_key_index,
    })


@app.route("/api/settings", methods=["POST"])
def update_settings():
    global _wake_word_enabled
    data = request.get_json()
    for key in ("model", "language", "personality", "audio_source"):
        if key in data:
            settings[key] = data[key]
    if "mic_denoise" in data:
        val = str(data["mic_denoise"]).lower().strip()
        if val in ("off", "hpf", "full"):
            settings["mic_denoise"] = val
            print(f"[DENOISE] mode -> {val}", flush=True)
    if "wake_word" in data:
        enabled = bool(data["wake_word"])
        if enabled and _wake_word_model is None:
            _init_wake_word_model()
        _wake_word_enabled = enabled
        print(f"[WAKE] {'Enabled' if enabled else 'Disabled'}", flush=True)
    return jsonify({"status": "success"})


@app.route("/api/audio/denoise/retrain", methods=["POST"])
def audio_denoise_retrain():
    """Block for `duration` seconds while averaging the mic stream into a fresh
    noise profile. The caller is expected to stay quiet during that window.
    """
    import time as _t
    data = request.get_json(silent=True) or {}
    try:
        duration = float(data.get("duration", request.args.get("duration", 1.2)))
    except Exception:
        duration = 1.2
    duration = max(0.3, min(5.0, duration))

    if not _audio_bridge_ok:
        return jsonify({"error": "audio bridge not running"}), 503

    before_count = _audio_recv_count
    _mic_denoiser.start_training()
    _t.sleep(duration)
    frames = _mic_denoiser.finalize_training()
    pkts = _audio_recv_count - before_count

    ok = frames >= 4
    return jsonify({
        "status": "ok" if ok else "no_audio",
        "duration": duration,
        "frames_averaged": frames,
        "packets_received": pkts,
        "trained": ok,
        "profile": _mic_denoiser.profile_status(),
    }), (200 if ok else 503)


@app.route("/api/audio/denoise/status", methods=["GET"])
def audio_denoise_status():
    return jsonify({
        "mode": settings.get("mic_denoise", MIC_DENOISE_MODE),
        "bridge": _audio_bridge_ok,
        "profile": _mic_denoiser.profile_status(),
    })


@app.route("/api/memory", methods=["GET"])
def get_memory():
    return jsonify({"memory": context_memory})


@app.route("/api/memory", methods=["POST"])
def add_memory():
    text = request.get_json().get("text", "")
    if text:
        context_memory.append({"text": text})
    return jsonify({"status": "success", "memory": context_memory})


@app.route("/api/memory/<int:index>", methods=["DELETE"])
def delete_memory(index):
    if 0 <= index < len(context_memory):
        context_memory.pop(index)
    return jsonify({"status": "success", "memory": context_memory})


@app.route("/api/server-status", methods=["GET"])
def server_status():
    return jsonify({"status": "online"})


@app.route("/api/play-music", methods=["POST"])
def play_music():
    data = request.get_json()
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "No query provided"}), 400
    if not YOUTUBE_API_KEY:
        return jsonify({"error": "YouTube API key not set"}), 500
    
    def is_embeddable(video_id):
        """Проверить, разрешено ли видео для встраивания"""
        try:
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "part": "status",
                    "id": video_id,
                    "key": YOUTUBE_API_KEY
                },
                timeout=5
            )
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                if items:
                    status = items[0].get("status", {})
                    return status.get("embeddable", False)
        except:
            pass
        return False
    
    try:
        base_query = query.replace(" official audio", "").replace(" - Topic", "").strip()
        
        # Search for alternative versions: covers, remixes, instrumentals, etc
        search_strategies = [
            base_query + " cover",                     # Cover versions from small channels
            base_query + " remix",                     # Remixes with different artists
            base_query + " instrumental",              # Instrumental - never blocked
            base_query + " acoustic",                  # Acoustic versions
            base_query + " tribute",                   # Tribute versions (fan-made)
            base_query + " karaoke",                   # Karaoke versions
            base_query + " slowed",                    # Slowed versions by fans
            "NoCopyrightSounds " + base_query,         # Official royalty-free channel
            "Audio Library " + base_query,             # YouTube Audio Library
        ]
        
        for search_query in search_strategies:
            try:
                resp = requests.get(
                    "https://www.googleapis.com/youtube/v3/search",
                    params={
                        "part": "snippet",
                        "q": search_query,
                        "type": "video",
                        "key": YOUTUBE_API_KEY,
                        "maxResults": 50,
                        "order": "relevance"
                    },
                    timeout=10
                )
                
                if resp.status_code != 200:
                    continue
                
                items = resp.json().get("items", [])
                
                # Check each video for embedding permission
                for item in items:
                    video_id = item["id"]["videoId"]
                    title = item["snippet"]["title"]
                    thumbnail = item["snippet"]["thumbnails"].get("high", {}).get("url", "")
                    
                    if is_embeddable(video_id):
                        return jsonify({
                            "videoId": video_id, 
                            "title": title,
                            "thumbnail": thumbnail
                        })
            except:
                continue
        
        return jsonify({
            "error": "YouTube blocks most popular songs due to copyright. No embeddable version found.",
            "suggestion": "Try: 'включи NoCopyrightSounds', 'включи instrumental music', или любой непопулярный артист"
        }), 404
    except Exception as e:
        return jsonify({"error": f"Search error: {str(e)}"}), 500


# ═══════════════════════ EMAIL SERVICE ENDPOINTS ═══════════════════════

# ═══════════════════════ PASSWORD HELPERS ═══════════════════════

def hash_password(password):
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000)
    return f"{salt}${pwd_hash.hex()}"


def verify_password(stored_hash, password):
    try:
        salt, pwd_hash = stored_hash.split('$')
        expected = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000).hex()
        # Timing-safe comparison — prevents timing side-channel attacks
        return hmac.compare_digest(expected, pwd_hash)
    except Exception:
        return False

def create_session_token(user_id):
    """Create a new session token for a user"""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=7)  # 7 day session
    
    session_obj = Session(
        token=token,
        user_id=user_id,
        expires_at=expires_at
    )
    db.session.add(session_obj)
    db.session.commit()
    
    return token

def verify_session_token(token):
    """Verify session token and return user if valid"""
    session_obj = Session.query.filter_by(token=token).first()
    
    if not session_obj:
        return None
    
    if session_obj.expires_at < datetime.utcnow():
        db.session.delete(session_obj)
        db.session.commit()
        return None
    
    return session_obj.user

# ═══════════════════════ LOCAL EMAIL ENDPOINTS ═══════════════════════

@app.route('/api/email/register', methods=['POST'])
def email_register():
    """Register new email account"""
    try:
        data = request.json
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()

        if not email or not password:
            return jsonify({"error": "Email and password required"}), 400

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({"error": "Email already registered"}), 400

        if len(password) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400

        new_user = User(
            email=email,
            password_hash=hash_password(password)
        )
        db.session.add(new_user)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Account created successfully",
            "email": email
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/email/login', methods=['POST'])
def email_login():
    """Login to email account"""
    try:
        data = request.json
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()

        if not email or not password:
            return jsonify({"error": "Email and password required"}), 400

        user = User.query.filter_by(email=email).first()

        if not user or not verify_password(user.password_hash, password):
            return jsonify({"error": "Invalid email or password"}), 401

        session_token = create_session_token(user.id)

        return jsonify({
            "success": True,
            "message": f"Logged in as {email}",
            "email": email,
            "session_token": session_token
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/email/logout', methods=['POST'])
def email_logout():
    """Logout from email account"""
    try:
        session_token = request.headers.get('X-Session-Token')
        
        if session_token:
            session_obj = Session.query.filter_by(token=session_token).first()
            if session_obj:
                db.session.delete(session_obj)
                db.session.commit()

        return jsonify({
            "success": True,
            "message": "Logged out successfully"
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/email/accounts', methods=['GET'])
def get_accounts():
    """Get list of registered accounts"""
    try:
        accounts = [user.email for user in User.query.all()]
        return jsonify({
            "accounts": accounts,
            "total": len(accounts)
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/email/verify', methods=['GET', 'POST'])
def verify_email():
    """Verify if email session is valid"""
    try:
        session_token = request.headers.get('X-Session-Token')
        
        if not session_token:
            return jsonify({"authenticated": False}), 401

        user = verify_session_token(session_token)
        
        if not user:
            return jsonify({"authenticated": False}), 401

        return jsonify({
            "authenticated": True,
            "email": user.email
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ═══════════════════════ GMAIL OAUTH ENDPOINTS ═══════════════════════

@app.route('/api/gmail/login', methods=['GET'])
def gmail_login():
    """Redirect to Gmail authentication page"""
    try:
        print(f"\n[LOGIN] 🔐 Инициирую OAuth авторизацию...")
        auth_result = gmail_service.get_auth_url()
        
        if 'error' in auth_result:
            print(f"[LOGIN] ❌ Ошибка: {auth_result['error']}")
            return jsonify({"error": auth_result['error']}), 400
        
        auth_url = auth_result['auth_url']
        print(f"[LOGIN] ✅ Перенаправляю на Google по ссылке...")
        print(f"[LOGIN] {auth_url[:100]}...")
        
        return jsonify({
            "auth_url": auth_url
        }), 200
    except Exception as e:
        print(f"[LOGIN] ❌ Исключение: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/gmail/callback', methods=['GET'])
def gmail_callback():
    """Handle Gmail OAuth callback"""
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        
        print(f"\n[CALLBACK] Получен запрос от Google")
        print(f"[CALLBACK] URL: {request.url}")
        print(f"[CALLBACK] Code: {code[:20] if code else 'None'}...")
        print(f"[CALLBACK] State: {state}")
        print(f"[CALLBACK] Error: {error}")
        
        if error:
            error_description = request.args.get('error_description', error)
            print(f"[CALLBACK] ❌ Ошибка от Google: {error_description}")
            return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;background:#0f172a;color:#f87171;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
<div style="text-align:center"><div style="font-size:48px">✗</div>
<p>Google error: {error_description}</p></div>
<script>try{{window.opener&&window.opener.postMessage({{gmailError:'{error_description}'}},'*');}}catch(e){{}}setTimeout(function(){{window.close();}},3000);</script>
</body></html>""", 400

        if not code:
            print(f"[CALLBACK] ❌ Код авторизации не получен")
            return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;background:#0f172a;color:#f87171;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
<div style="text-align:center"><p>No authorization code received.</p></div>
<script>setTimeout(function(){{window.close();}},2000);</script>
</body></html>""", 400
        
        print(f"[CALLBACK] Обмен кода на токен...")
        result = gmail_service.exchange_code_for_token(code, state)
        
        print(f"[CALLBACK] Результат: {result}")
        
        if 'error' in result:
            print(f"[CALLBACK] ❌ Ошибка обмена: {result['error']}")
            return jsonify({"error": result['error']}), 400
        
        # Store Gmail account in database
        email = result.get('email')
        print(f"[CALLBACK] ✅ Авторизация успешна, email: {email}")
        
        if email:
            gmail_account = GmailAccount.query.filter_by(email=email).first()
            if not gmail_account:
                gmail_account = GmailAccount(email=email)
            
            gmail_account.access_token = result.get('token', '')
            gmail_account.refresh_token = result.get('refresh_token', '')
            
            db.session.add(gmail_account)
            db.session.commit()
            
            session['gmail_email'] = email
            session['gmail_authenticated'] = True
            
            print(f"[CALLBACK] ✅ Данные сохранены в БД, закрываю popup...")

        # Close the popup and signal success to parent window
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Auth Success</title></head>
<body style="font-family:sans-serif;background:#0f172a;color:#34d399;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
<div style="text-align:center">
  <div style="font-size:48px">✓</div>
  <p style="font-size:18px">Gmail connected: {email}</p>
  <p style="color:#94a3b8;font-size:14px">This window will close automatically…</p>
</div>
<script>
  try {{ window.opener && window.opener.postMessage({{gmailAuth: true, email: {repr(email)}}}, '*'); }} catch(e) {{}}
  setTimeout(function(){{ window.close(); }}, 1500);
</script>
</body></html>"""
    except Exception as e:
        print(f"[CALLBACK] ❌ Исключение: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/gmail/status', methods=['GET'])
def gmail_status():
    """Check Gmail authentication status"""
    try:
        gmail_email = _resolve_gmail_email()
        is_auth = bool(gmail_email) and gmail_service.is_authenticated(gmail_email)
        return jsonify({"authenticated": is_auth, "email": gmail_email}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/gmail/accounts', methods=['GET'])
def gmail_accounts():
    """List connected Gmail accounts (stored in DB)."""
    try:
        accounts = [a.email for a in GmailAccount.query.order_by(GmailAccount.id.asc()).all()]
        return jsonify({"accounts": accounts, "total": len(accounts)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/gmail/switch', methods=['POST'])
def gmail_switch():
    """Switch active Gmail account for the current session."""
    try:
        data = request.get_json(silent=True) or {}
        email = (data.get('email') or '').strip()
        if not email:
            return jsonify({"error": "Email required"}), 400

        acct = GmailAccount.query.filter_by(email=email).first()
        if not acct:
            return jsonify({"error": "Gmail account not found"}), 404

        session['gmail_email'] = email
        session['gmail_authenticated'] = True
        return jsonify({"success": True, "email": email}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/gmail/emails', methods=['GET'])
def get_gmail_emails():
    """Fetch emails from Gmail inbox"""
    try:
        gmail_email = _resolve_gmail_email()
        if not gmail_email or not gmail_service.is_authenticated(gmail_email):
            return jsonify({"error": "Not authenticated with Gmail"}), 401
        
        max_results = request.args.get('max_results', 10, type=int)
        result = gmail_service.get_emails(max_results=max_results, email=gmail_email)
        
        if 'error' in result:
            return jsonify(result), 400
        
        # Cache emails in database
        gmail_email = session.get('gmail_email')
        if gmail_email:
            gmail_account = GmailAccount.query.filter_by(email=gmail_email).first()
            if gmail_account and 'emails' in result:
                for email_data in result['emails']:
                    existing = EmailMessage.query.filter_by(
                        gmail_id=email_data['id'],
                        account_id=gmail_account.id
                    ).first()
                    
                    if not existing:
                        msg = EmailMessage(
                            gmail_id=email_data['id'],
                            account_id=gmail_account.id,
                            sender=email_data.get('from', ''),
                            subject=email_data.get('subject', ''),
                            body=email_data.get('body', ''),
                            received_at=datetime.utcnow()
                        )
                        db.session.add(msg)
                
                db.session.commit()
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/gmail/send', methods=['POST'])
def send_gmail_email():
    """Send email through Gmail"""
    try:
        gmail_email = _resolve_gmail_email()
        if not gmail_email or not gmail_service.is_authenticated(gmail_email):
            return jsonify({"error": "Not authenticated with Gmail"}), 401
        
        data = request.json
        to = data.get('to', '').strip()
        subject = data.get('subject', '').strip()
        body = data.get('body', '').strip()
        
        if not all([to, subject, body]):
            return jsonify({"error": "Missing required fields: to, subject, body"}), 400
        
        result = gmail_service.send_email(to, subject, body, email=gmail_email)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/gmail/logout', methods=['POST'])
def gmail_logout():
    """Logout from Gmail"""
    try:
        # 1. Полностью убиваем куку сессии Flask
        session.clear() 
        
        # 2. Физически удаляем файл token.json (чтобы Гугл тоже нас забыл)
        gmail_service._clear_credentials()
        
        return jsonify({
            "success": True,
            "message": "Logged out from Gmail and cleared session"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ═══════════════════════ INBOX & EMAIL DISPLAY ENDPOINTS ═══════════════════════

@app.route('/api/emails/inbox', methods=['GET'])
def get_inbox():
    """Return cached inbox emails ordered newest-first."""
    try:
        gmail_email = _resolve_gmail_email()
        max_results = request.args.get('max_results', 500, type=int)

        if not gmail_email:
            return jsonify({"emails": [], "source": "none", "needs_gmail": True}), 200

        gmail_account = GmailAccount.query.filter_by(email=gmail_email).first()
        if not gmail_account:
            return jsonify({"emails": [], "source": "none", "needs_gmail": True}), 200

        emails = (EmailMessage.query
                  .filter_by(account_id=gmail_account.id)
                  .order_by(EmailMessage.received_at.desc())
                  .limit(max_results)
                  .all())

        emails_data = [{
            'id':       e.gmail_id,
            'subject':  e.subject,
            'from':     e.sender,
            'body':     e.body or '',
            'date':     e.received_at.strftime('%Y-%m-%dT%H:%M:%SZ'),  # UTC ISO
            'is_read':  e.is_read,
        } for e in emails]

        unread = sum(1 for e in emails if not e.is_read)

        return jsonify({
            "emails":       emails_data,
            "source":       "cache",
            "needs_gmail":  False,
            "total":        len(emails_data),
            "unread_count": unread,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/emails/sync', methods=['POST'])
def sync_emails():
    """Sync emails from Gmail and cache them with correct timestamps."""
    try:
        gmail_email = _resolve_gmail_email()
        if not gmail_email:
            return jsonify({"error": "No Gmail session"}), 400
        if not gmail_service.is_authenticated(gmail_email):
            return jsonify({"error": "Not authenticated with Gmail"}), 401

        gmail_account = GmailAccount.query.filter_by(email=gmail_email).first()
        if not gmail_account:
            session.clear()
            return jsonify({"error": "Database reset — please login again."}), 400

        data = request.get_json(silent=True) or {}
        mode = data.get('mode', 'fast')

        if mode == 'full':
            query       = 'in:inbox newer_than:2m'
            max_results = 0          # paginate through everything
        else:
            # Fast: 2 months window but capped at 200 for speed
            query       = 'in:inbox newer_than:2m'
            max_results = 200

        result = gmail_service.get_emails_for_sync(query=query, max_results=max_results, email=gmail_email)

        if 'error' in result:
            return jsonify(result), 400

        fetched_ids = result.get('message_ids', set())
        added = updated = removed = 0

        for email_data in result.get('emails', []):
            gmail_id = email_data.get('id', '')
            if not gmail_id:
                continue

            # Use actual email date, not sync time
            date_str    = email_data.get('date', '')
            received_at = email_data.get('date_dt') or _parse_email_date(date_str)
            is_read     = email_data.get('is_read', False)

            existing = EmailMessage.query.filter_by(
                gmail_id=gmail_id, account_id=gmail_account.id
            ).first()

            # snippet used as preview; body loaded on-demand
            snippet = email_data.get('snippet', '')

            if not existing:
                db.session.add(EmailMessage(
                    gmail_id=gmail_id,
                    account_id=gmail_account.id,
                    sender=email_data.get('from', 'Unknown'),
                    subject=email_data.get('subject', '(No Subject)'),
                    body=snippet,   # store snippet; full body fetched on open
                    received_at=received_at,
                    is_read=is_read,
                ))
                added += 1
            else:
                changed = False
                for attr, val in [('sender',      email_data.get('from',    existing.sender)),
                                   ('subject',     email_data.get('subject', existing.subject)),
                                   ('received_at', received_at),
                                   ('is_read',     is_read)]:
                    if getattr(existing, attr) != val:
                        setattr(existing, attr, val)
                        changed = True
                # Never overwrite an already-fetched full body with a shorter snippet
                new_body = email_data.get('body', '') or snippet
                if new_body and (not existing.body or len(new_body) > len(existing.body or '')):
                    existing.body = new_body
                    changed = True
                if changed:
                    updated += 1

        # Full sync: purge locally-cached emails no longer in Gmail inbox
        if mode == 'full' and fetched_ids:
            for msg in EmailMessage.query.filter_by(account_id=gmail_account.id).all():
                if msg.gmail_id not in fetched_ids:
                    db.session.delete(msg)
                    removed += 1

        db.session.commit()
        total = EmailMessage.query.filter_by(account_id=gmail_account.id).count()

        return jsonify({
            "success":      True,
            "added":        added,
            "updated":      updated,
            "removed":      removed,
            "total_cached": total,
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/emails/clear-cache', methods=['POST'])
def clear_email_cache():
    """Delete all locally-cached emails for the authenticated account (forces fresh sync)."""
    try:
        gmail_email = _resolve_gmail_email()
        if not gmail_email:
            return jsonify({"error": "Not authenticated"}), 401
        gmail_account = GmailAccount.query.filter_by(email=gmail_email).first()
        if not gmail_account:
            return jsonify({"error": "No Gmail account found"}), 400
        deleted = EmailMessage.query.filter_by(account_id=gmail_account.id).delete()
        db.session.commit()
        return jsonify({"success": True, "deleted": deleted}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/emails/unread-count', methods=['GET'])
def email_unread_count():
    """Return count of unread cached messages for authenticated Gmail account."""
    try:
        gmail_email = session.get('gmail_email', '')
        if not gmail_email:
            return jsonify({"count": 0}), 200
        account = GmailAccount.query.filter_by(email=gmail_email).first()
        if not account:
            return jsonify({"count": 0}), 200
        count = EmailMessage.query.filter_by(account_id=account.id, is_read=False).count()
        return jsonify({"count": count}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/emails/<gmail_id>/read', methods=['POST'])
def mark_email_read(gmail_id):
    """Mark an email as read locally and in Gmail."""
    try:
        gmail_email = session.get('gmail_email', '')
        if not gmail_email:
            return jsonify({"error": "Not authenticated"}), 401
        account = GmailAccount.query.filter_by(email=gmail_email).first()
        if not account:
            return jsonify({"error": "Account not found"}), 404

        msg = EmailMessage.query.filter_by(
            gmail_id=gmail_id, account_id=account.id
        ).first()
        if msg and not msg.is_read:
            msg.is_read = True
            db.session.commit()

        # Also mark as read in Gmail (remove UNREAD label)
        try:
            svc = gmail_service.get_service(email=gmail_email)
            if svc:
                svc.users().messages().modify(
                    userId='me', id=gmail_id,
                    body={'removeLabelIds': ['UNREAD']}
                ).execute()
        except Exception:
            pass

        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/emails/message/<gmail_id>', methods=['GET'])
def get_email_message(gmail_id):
    """Return full email content by gmail_id (fallback fetch when body is missing)."""
    try:
        gmail_email = session.get('gmail_email', '')
        account = None
        if gmail_email:
            account = GmailAccount.query.filter_by(email=gmail_email).first()

        # Try local cache first
        if account:
            msg = EmailMessage.query.filter_by(
                gmail_id=gmail_id, account_id=account.id
            ).first()
            if msg and msg.body:
                return jsonify({
                    'id':      msg.gmail_id,
                    'subject': msg.subject,
                    'from':    msg.sender,
                    'body':    msg.body,
                    'is_read': msg.is_read,
                    'date':    msg.received_at.strftime('%Y-%m-%dT%H:%M:%SZ'),
                }), 200

        # Fetch live from Gmail
        svc = gmail_service.get_service()
        if svc:
            details = gmail_service._get_message_details(svc, gmail_id)
            if details:
                return jsonify(details), 200

        return jsonify({"error": "Message not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════ AUDIO INTERCOM (browser <-> ESP32) ═══════════════════════

AUDIO_MIC_PORT = 12345
AUDIO_SPK_PORT = 12346
ESP32_MAC = os.environ.get("ESP32_MAC", "9c:9c:1f:e9:96:f4").lower().replace("-", ":")
ESP32_IP_OVERRIDE = (os.environ.get("ESP32_IP") or "").strip() or None
_esp32_ip_cache = None
_esp32_ip_cache_time = 0
_esp32_ip_source = None  # "env" | "arp-verified" | "udp" | None
_esp32_audio_ip = None
_esp32_resolver_running = False
_esp32_resolver_lock = _threading.Lock()
_ESP32_IP_TTL = 15.0       # seconds — after this we schedule a verified re-discovery
_ESP32_SWEEP_COOLDOWN = 30.0
_esp32_last_sweep_ts = 0.0


def _resolve_ip_from_mac(mac):
    """Look up an IP address by MAC in the system ARP table (first match).

    NOTE: This reads the table AS-IS; the entry may be stale. Prefer
    `_discover_esp32_ip` for the ESP32, which verifies the entry by pinging.
    Kept for other callers (camera discovery, etc.).
    """
    import subprocess
    try:
        out = subprocess.check_output("arp -a", shell=True, text=True, timeout=5)
    except Exception:
        return None

    mac_norm = mac.lower().replace("-", ":")
    ip_re = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")
    mac_re = re.compile(r"([0-9a-f]{2}[:-]){5}[0-9a-f]{2}", re.IGNORECASE)
    for line in out.splitlines():
        m_mac = mac_re.search(line)
        if not m_mac:
            continue
        if m_mac.group(0).lower().replace("-", ":") != mac_norm:
            continue
        m_ip = ip_re.search(line)
        if m_ip:
            return m_ip.group(1)
    return None


def _arp_candidates_for_mac(mac):
    """Return ALL IPs currently mapped to `mac` in the ARP table (may be stale)."""
    import subprocess
    try:
        out = subprocess.check_output("arp -a", shell=True, text=True, timeout=5)
    except Exception:
        return []
    mac_norm = mac.lower().replace("-", ":")
    ip_re = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")
    mac_re = re.compile(r"([0-9a-f]{2}[:-]){5}[0-9a-f]{2}", re.IGNORECASE)
    ips = []
    for line in out.splitlines():
        m_mac = mac_re.search(line)
        m_ip = ip_re.search(line)
        if not (m_mac and m_ip):
            continue
        if m_mac.group(0).lower().replace("-", ":") != mac_norm:
            continue
        ip = m_ip.group(1)
        if ip not in ips:
            ips.append(ip)
    return ips


def _arp_mac_for_ip(ip):
    """Return the MAC currently bound to `ip` in ARP, or None."""
    import subprocess
    try:
        out = subprocess.check_output("arp -a", shell=True, text=True, timeout=5)
    except Exception:
        return None
    mac_re = re.compile(r"([0-9a-f]{2}[:-]){5}[0-9a-f]{2}", re.IGNORECASE)
    ip_token = " " + ip + " "
    for line in out.splitlines():
        if ip not in line:
            continue
        # Guard against substring collisions (e.g. 192.168.1.10 inside 192.168.1.100)
        padded = " " + line + " "
        if ip_token not in padded and not padded.startswith(" " + ip + " "):
            continue
        m = mac_re.search(line)
        if m:
            return m.group(0).lower().replace("-", ":")
    return None


def _ping_once(ip, timeout_ms=500):
    """Single ICMP ping; returns True if the host replied."""
    import subprocess
    try:
        if os.name == "nt":
            cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip]
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=(timeout_ms + 500) / 1000.0,
        )
        return result.returncode == 0
    except Exception:
        return False


def _get_local_subnet_prefix():
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        finally:
            s.close()
        return ".".join(local_ip.split(".")[:3])
    except Exception:
        return None


def _quick_ping_sweep():
    """Fire-and-forget pings across the /24 to repopulate ARP. ~2–4s total."""
    global _esp32_last_sweep_ts
    import time as _t
    now = _t.time()
    if now - _esp32_last_sweep_ts < _ESP32_SWEEP_COOLDOWN:
        return
    _esp32_last_sweep_ts = now

    prefix = _get_local_subnet_prefix()
    if not prefix:
        return
    print(f"[AUDIO] ARP sweep {prefix}.1-254 (refreshing cache)", flush=True)
    procs = []
    for i in range(1, 255):
        try:
            if os.name == "nt":
                cmd = ["ping", "-n", "1", "-w", "250", f"{prefix}.{i}"]
            else:
                cmd = ["ping", "-c", "1", "-W", "1", f"{prefix}.{i}"]
            procs.append(subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ))
        except Exception:
            pass
    for p in procs:
        try:
            p.wait(timeout=4)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


def _discover_esp32_ip():
    """Find ESP32's actual current IP — verified, not stale.

    Algorithm:
      1. For each ARP entry mapped to our MAC, ping it. The ping forces
         a fresh ARP resolution: if the device moved, ARP gets updated
         (or the entry disappears). After the ping, re-read ARP and keep
         only IPs where our MAC is STILL bound.
      2. If none pass verification, run a /24 ping sweep to populate ARP
         with every live host, then repeat step 1.
    """
    def _verify(ip):
        if not _ping_once(ip, 600):
            return False
        return _arp_mac_for_ip(ip) == ESP32_MAC

    for ip in _arp_candidates_for_mac(ESP32_MAC):
        if _verify(ip):
            return ip

    _quick_ping_sweep()

    for ip in _arp_candidates_for_mac(ESP32_MAC):
        if _verify(ip):
            return ip

    return None


def _esp32_resolver_refresh(sync=False):
    """Re-discover the ESP32's IP in a background thread (single-flight).

    If `sync=True`, runs inline (used at startup for the first resolve).
    """
    global _esp32_resolver_running, _esp32_ip_cache, _esp32_ip_cache_time, _esp32_ip_source

    def _run():
        global _esp32_resolver_running, _esp32_ip_cache, _esp32_ip_cache_time, _esp32_ip_source
        try:
            ip = _discover_esp32_ip()
            import time as _t
            now = _t.time()
            if ip:
                if ip != _esp32_ip_cache:
                    print(f"[AUDIO] ESP32 discovered: {ip} (verified by ping + ARP)", flush=True)
                _esp32_ip_cache = ip
                _esp32_ip_cache_time = now
                _esp32_ip_source = "arp-verified"
            elif _esp32_audio_ip:
                if _esp32_ip_cache != _esp32_audio_ip:
                    print(f"[AUDIO] ESP32 IP fallback to UDP source: {_esp32_audio_ip}", flush=True)
                _esp32_ip_cache = _esp32_audio_ip
                _esp32_ip_cache_time = now
                _esp32_ip_source = "udp"
        finally:
            with _esp32_resolver_lock:
                globals()["_esp32_resolver_running"] = False

    with _esp32_resolver_lock:
        if _esp32_resolver_running:
            return
        _esp32_resolver_running = True

    if sync:
        _run()
    else:
        _threading.Thread(target=_run, daemon=True, name="esp32-resolver").start()


def _esp32_bg_resolver_loop():
    """Periodic background refresher so the cache never goes stale for long."""
    import time as _t
    while True:
        try:
            _t.sleep(_ESP32_IP_TTL)
            if ESP32_IP_OVERRIDE:
                continue
            _esp32_resolver_refresh(sync=False)
        except Exception:
            continue


def _esp32_send_ip():
    """Return the best known ESP32 IP without ever blocking the caller.

    Priority: env override > last verified ARP cache > last UDP source.
    A background re-discovery is kicked off when the cache is stale.
    """
    global _esp32_ip_cache, _esp32_ip_source
    import time as _t

    if ESP32_IP_OVERRIDE:
        if _esp32_ip_cache != ESP32_IP_OVERRIDE:
            print(f"[AUDIO] ESP32 IP from env: {ESP32_IP_OVERRIDE}", flush=True)
            _esp32_ip_cache = ESP32_IP_OVERRIDE
        _esp32_ip_source = "env"
        return ESP32_IP_OVERRIDE

    now = _t.time()
    stale = (not _esp32_ip_cache) or (now - _esp32_ip_cache_time >= _ESP32_IP_TTL)
    if stale:
        _esp32_resolver_refresh(sync=False)

    if _esp32_ip_cache:
        return _esp32_ip_cache
    if _esp32_audio_ip:
        _esp32_ip_source = "udp"
        return _esp32_audio_ip
    _esp32_ip_source = None
    return None
_audio_listeners = 0
_audio_bridge_ok = False
_udp_recv = None
_udp_send = None
_audio_recv_count = 0
_audio_emit_count = 0

_robot_recording = False
_robot_buffer = []

# ── Wake word detection ──────────────────────────────────────────────────────

_wake_word_enabled = False
_wake_word_model = None
_WAKE_WORD_THRESHOLD = 0.1
_WAKE_FRAME_SAMPLES = 1280  # 80ms at 16kHz — OpenWakeWord's expected frame size
_wake_audio_buf = bytearray()


def _init_wake_word_model():
    global _wake_word_model
    if _wake_word_model is not None:
        return _wake_word_model
    try:
        from openwakeword.model import Model
        model_path = str(Path(__file__).resolve().parent / "models" / "computer_v2.onnx")
        _wake_word_model = Model(wakeword_models=[model_path], inference_framework="onnx")
        print(f"[WAKE] Model loaded from {model_path}", flush=True)
        print(f"[WAKE] Model names: {list(_wake_word_model.models.keys())}", flush=True)
        return _wake_word_model
    except Exception as e:
        print(f"[WAKE] Failed to load wake word model: {e}", flush=True)
        return None


def _wake_word_feed(pcm_bytes):
    """Buffer incoming PCM and feed 1280-sample frames to OpenWakeWord."""
    global _wake_audio_buf
    if not _wake_word_enabled or _robot_recording:
        return False
    model = _wake_word_model
    if model is None:
        return False

    _wake_audio_buf.extend(pcm_bytes)
    frame_bytes = _WAKE_FRAME_SAMPLES * 2  # 2560 bytes per frame

    triggered = False
    while len(_wake_audio_buf) >= frame_bytes:
        import numpy as np
        frame = np.frombuffer(bytes(_wake_audio_buf[:frame_bytes]), dtype=np.int16)
        _wake_audio_buf = _wake_audio_buf[frame_bytes:]
        prediction = model.predict(frame)
        for mdl_name, score in prediction.items():
            if score > _WAKE_WORD_THRESHOLD:
                print(f"[WAKE] Detected '{mdl_name}' (score={score:.3f})", flush=True)
                model.reset()
                _wake_audio_buf.clear()
                return True

    if len(_wake_audio_buf) > frame_bytes * 10:
        _wake_audio_buf = _wake_audio_buf[-frame_bytes:]

    return triggered


# ── Mic denoiser (server-side, firmware-free) ────────────────────────────────
#
# The INMP441 on the ESP32 sends raw 16-bit PCM @ 16 kHz with no processing.
# Typical artefacts: DC offset, <100 Hz rumble, 50/60 Hz mains hum, stationary
# hiss. We clean the stream BEFORE it fans out to browser listen / wake word /
# robot STT, so every consumer sees clean audio.
#
# Stages:
#   1. 2nd-order Butterworth high-pass at MIC_HPF_HZ (default 120 Hz).
#   2. Overlap-add spectral gate (50% overlap Hann, STFT size = 2 * chunk).
#      Learns a noise floor from low-RMS frames and from the first ~0.6 s.

def _env_float(name: str, default: float) -> float:
    """Read a float from env, tolerating inline comments and whitespace."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    cleaned = raw.split("#", 1)[0].strip()
    if not cleaned:
        return default
    try:
        return float(cleaned)
    except ValueError:
        print(f"[ENV] bad float for {name}={raw!r}; using default {default}", flush=True)
        return default


MIC_DENOISE_MODE = (os.environ.get("MIC_DENOISE", "full").split("#", 1)[0].lower().strip() or "full")  # off | hpf | full
MIC_HPF_HZ = _env_float("MIC_HPF_HZ", 120.0)
MIC_GATE_OVERSUB = _env_float("MIC_GATE_OVERSUB", 2.0)
MIC_GATE_FLOOR = _env_float("MIC_GATE_FLOOR", 0.02)
MIC_GATE_TIME_SMOOTH = _env_float("MIC_GATE_TIME_SMOOTH", 0.6)  # 0..1 (higher = smoother mask, less musical noise)
MIC_NOISE_MARGIN = _env_float("MIC_NOISE_MARGIN", 1.35)  # multiply learned profile by this (>=1); compensates for
                                                        # instantaneous noise exceeding the mean magnitude.
MIC_NOISE_TRACK_RMS = _env_float("MIC_NOISE_TRACK_RMS", 0.04)  # update profile only when frame RMS < this.
MIC_NOISE_TRACK_ALPHA = _env_float("MIC_NOISE_TRACK_ALPHA", 0.985)  # EMA: new = alpha*old + (1-alpha)*current.


class MicDenoiser:
    """Real-time mic cleanup: HPF + overlap-add spectral mask. Pure numpy, stateful.

    The spectral gate multiplies the complex spectrum by a per-bin gain mask
    derived from the SNR vs. a learned noise magnitude profile. The mask is
    smoothed in time (and optionally frequency) to avoid "musical noise".

    The profile is either:
      - trained explicitly via start_training / finalize_training (best), or
      - auto-learned from the first few quiet frames (fallback).

    Until a profile exists, the gate is pass-through — so we never subtract
    the first frame's contents (which could be mid-speech) from everything.
    """

    AUTO_LEARN_RMS_THRESHOLD = 0.05
    AUTO_LEARN_FRAMES_NEEDED = 12   # ~0.4 s at 32 ms / frame

    def __init__(self, sample_rate=16000, hpf_hz=120.0, gate=True,
                 gate_oversub=2.0, gate_floor=0.02, time_smooth=0.6,
                 freq_smooth=True, noise_margin=1.35,
                 track_rms=0.04, track_alpha=0.985):
        import numpy as _np
        import math as _math
        self._np = _np
        self.sr = sample_rate
        self.gate_on = gate
        self.oversub = gate_oversub
        self.floor = gate_floor
        self.time_smooth = max(0.0, min(0.95, time_smooth))
        self.freq_smooth = freq_smooth
        self.noise_margin = max(1.0, float(noise_margin))
        self.track_rms = max(0.0, float(track_rms))
        self.track_alpha = max(0.5, min(0.9995, float(track_alpha)))

        Q = 1.0 / _math.sqrt(2.0)
        w0 = 2 * _math.pi * hpf_hz / sample_rate
        cw, sw = _math.cos(w0), _math.sin(w0)
        alpha = sw / (2 * Q)
        a0 = 1 + alpha
        self._b0 = (1 + cw) / 2 / a0
        self._b1 = -(1 + cw) / a0
        self._b2 = (1 + cw) / 2 / a0
        self._a1 = -2 * cw / a0
        self._a2 = (1 - alpha) / a0
        self._z1 = 0.0
        self._z2 = 0.0

        self._have_scipy = False
        try:
            from scipy.signal import lfilter  # noqa: F401
            self._lfilter = lfilter
            self._b = _np.array([self._b0, self._b1, self._b2], dtype=_np.float32)
            self._a = _np.array([1.0, self._a1, self._a2], dtype=_np.float32)
            self._zi = _np.zeros(2, dtype=_np.float32)
            self._have_scipy = True
        except Exception:
            pass

        self._prev_in_half = None
        self._prev_out_half = None
        self._prev_gain = None

        self._noise_mag = None
        self._auto_accum = None
        self._auto_count = 0

        self._training = False
        self._train_accum = None
        self._train_count = 0
        self._train_prev = None

    def _hpf(self, x):
        if self._have_scipy:
            y, self._zi = self._lfilter(self._b, self._a, x, zi=self._zi)
            return y
        np = self._np
        y = np.empty_like(x)
        z1, z2 = self._z1, self._z2
        b0, b1, b2 = self._b0, self._b1, self._b2
        a1, a2 = self._a1, self._a2
        for i in range(len(x)):
            xi = float(x[i])
            yi = b0 * xi + z1
            z1 = b1 * xi + z2 - a1 * yi
            z2 = b2 * xi - a2 * yi
            y[i] = yi
        self._z1, self._z2 = z1, z2
        return y

    def _try_auto_learn(self, mag, rms):
        """Accumulate magnitudes from quiet frames until we have enough."""
        np = self._np
        if rms > self.AUTO_LEARN_RMS_THRESHOLD:
            return
        if self._auto_accum is None:
            self._auto_accum = mag.copy()
            self._auto_count = 1
        else:
            self._auto_accum += mag
            self._auto_count += 1
        if self._auto_count >= self.AUTO_LEARN_FRAMES_NEEDED:
            mean = self._auto_accum / float(self._auto_count)
            self._noise_mag = (mean * self.noise_margin).astype(np.float32)
            print(
                f"[DENOISE] auto-learned noise profile from "
                f"{self._auto_count} quiet frames (rms<{self.AUTO_LEARN_RMS_THRESHOLD}, "
                f"margin={self.noise_margin:.2f}x)",
                flush=True,
            )
            self._auto_accum = None
            self._auto_count = 0

    def _spec_gate(self, x):
        np = self._np
        N = len(x)
        if N < 64:
            return x

        if self._prev_in_half is None or len(self._prev_in_half) != N:
            self._prev_in_half = x.astype(np.float32).copy()
            self._prev_out_half = np.zeros(N, dtype=np.float32)
            self._prev_gain = None
            return x

        frame = np.concatenate([self._prev_in_half, x]).astype(np.float32)
        win = np.hanning(2 * N).astype(np.float32)
        X = np.fft.rfft(frame * win)
        mag = np.abs(X).astype(np.float32) + 1e-9

        rms = float(np.sqrt(np.mean(frame * frame) + 1e-9))
        if self._noise_mag is None:
            self._try_auto_learn(mag, rms)
            self._prev_in_half = x.astype(np.float32).copy()
            return x

        # Slow background tracking: when the current frame is clearly quieter
        # than anything speech-like, blend its magnitude into the profile so
        # we follow slow drift (amp warm-up, fan speeding up, etc.) without
        # ever polluting the profile with speech.
        if rms < self.track_rms:
            a = self.track_alpha
            self._noise_mag = (a * self._noise_mag + (1.0 - a) * mag).astype(np.float32)

        snr = mag / (self._noise_mag + 1e-9)
        gain = 1.0 - self.oversub / np.maximum(snr, 1e-9)
        gain = np.clip(gain, self.floor, 1.0).astype(np.float32)

        if self._prev_gain is None or self._prev_gain.shape != gain.shape:
            self._prev_gain = gain.copy()
        else:
            a = self.time_smooth
            gain = a * self._prev_gain + (1.0 - a) * gain
            self._prev_gain = gain

        if self.freq_smooth and gain.size >= 3:
            pad = np.concatenate([[gain[0]], gain, [gain[-1]]])
            gain = ((pad[:-2] + pad[1:-1] + pad[2:]) / 3.0).astype(np.float32)

        Y = X * gain
        y_full = np.fft.irfft(Y, n=2 * N).astype(np.float32)

        out_first = y_full[:N] + self._prev_out_half
        self._prev_out_half = y_full[N:].copy()
        self._prev_in_half = x.astype(np.float32).copy()
        return out_first

    def _feed_training(self, x_hpf):
        """Accumulate magnitude spectra into the active training profile.

        Uses the same overlap-add geometry as runtime, so the learned
        profile matches exactly what the gate will compare against.
        """
        np = self._np
        N = len(x_hpf)
        if self._train_prev is None or len(self._train_prev) != N:
            self._train_prev = x_hpf.astype(np.float32).copy()
            return
        frame = np.concatenate([self._train_prev, x_hpf]).astype(np.float32)
        win = np.hanning(2 * N).astype(np.float32)
        mag = np.abs(np.fft.rfft(frame * win)).astype(np.float32)
        if self._train_accum is None:
            self._train_accum = mag.copy()
            self._train_count = 1
        else:
            self._train_accum += mag
            self._train_count += 1
        self._train_prev = x_hpf.astype(np.float32).copy()

    def _pcm_to_f32(self, pcm_bytes):
        return self._np.frombuffer(pcm_bytes, dtype=self._np.int16).astype(
            self._np.float32
        ) * (1.0 / 32768.0)

    def _f32_to_pcm(self, x):
        np = self._np
        x = np.clip(x, -1.0, 1.0)
        return (x * 32767.0).astype(np.int16).tobytes()

    def process_pcm_bytes(self, pcm_bytes, mode="full"):
        if mode == "off" or len(pcm_bytes) < 4:
            return pcm_bytes
        try:
            x = self._pcm_to_f32(pcm_bytes)
            x = self._hpf(x)

            if self._training:
                self._feed_training(x)
                return self._f32_to_pcm(x)

            if mode == "full" and self.gate_on:
                x = self._spec_gate(x)
            return self._f32_to_pcm(x)
        except Exception as e:
            print(f"[DENOISE] error: {e} (passing raw)", flush=True)
            return pcm_bytes

    def process_pcm_bytes_split(self, pcm_bytes, mode="full"):
        """Single-pass version that returns (listen_bytes, stt_bytes).

        - listen_bytes: what humans should hear (full gate if mode=='full').
        - stt_bytes:    HPF-only output (good for Whisper / OpenWakeWord).

        Shares one HPF pass so the filter's internal state advances exactly once.
        """
        if mode == "off" or len(pcm_bytes) < 4:
            return pcm_bytes, pcm_bytes
        try:
            x = self._pcm_to_f32(pcm_bytes)
            x_hpf = self._hpf(x)

            if self._training:
                self._feed_training(x_hpf)
                out = self._f32_to_pcm(x_hpf)
                return out, out

            stt_bytes = self._f32_to_pcm(x_hpf)
            if mode == "full" and self.gate_on:
                x_gated = self._spec_gate(x_hpf)
                listen_bytes = self._f32_to_pcm(x_gated)
            else:
                listen_bytes = stt_bytes
            return listen_bytes, stt_bytes
        except Exception as e:
            print(f"[DENOISE] split error: {e} (passing raw)", flush=True)
            return pcm_bytes, pcm_bytes

    def start_training(self):
        self._train_accum = None
        self._train_count = 0
        self._train_prev = None
        self._training = True
        print("[DENOISE] training started — collecting noise profile...", flush=True)

    def finalize_training(self):
        self._training = False
        count = self._train_count
        if self._train_accum is not None and count >= 4:
            mean = self._train_accum / float(count)
            self._noise_mag = (mean * self.noise_margin).astype(self._np.float32)
            self._prev_gain = None
            print(
                f"[DENOISE] training complete: averaged {count} frames "
                f"(margin={self.noise_margin:.2f}x) into new noise profile",
                flush=True,
            )
        else:
            print(
                f"[DENOISE] training aborted: only {count} frames — no profile "
                f"update (is the ESP32 actually streaming?)",
                flush=True,
            )
        self._train_accum = None
        self._train_count = 0
        self._train_prev = None
        return count

    def reset_noise_profile(self):
        self._noise_mag = None
        self._prev_gain = None
        self._auto_accum = None
        self._auto_count = 0

    def profile_status(self):
        return {
            "trained": self._noise_mag is not None,
            "auto_learn_progress": self._auto_count,
            "auto_learn_needed": self.AUTO_LEARN_FRAMES_NEEDED,
            "training_now": self._training,
            "oversub": self.oversub,
            "floor": self.floor,
            "time_smooth": self.time_smooth,
        }


_mic_denoiser = MicDenoiser(
    sample_rate=16000,
    hpf_hz=MIC_HPF_HZ,
    gate=True,
    gate_oversub=MIC_GATE_OVERSUB,
    gate_floor=MIC_GATE_FLOOR,
    time_smooth=MIC_GATE_TIME_SMOOTH,
    freq_smooth=True,
    noise_margin=MIC_NOISE_MARGIN,
    track_rms=MIC_NOISE_TRACK_RMS,
    track_alpha=MIC_NOISE_TRACK_ALPHA,
)
print(
    f"[DENOISE] MicDenoiser ready: mode={MIC_DENOISE_MODE}, hpf={MIC_HPF_HZ:.0f}Hz, "
    f"oversub={MIC_GATE_OVERSUB}, floor={MIC_GATE_FLOOR}, time_smooth={MIC_GATE_TIME_SMOOTH}, "
    f"margin={MIC_NOISE_MARGIN}, track_rms={MIC_NOISE_TRACK_RMS}, "
    f"scipy={'yes' if _mic_denoiser._have_scipy else 'no (python biquad)'}",
    flush=True,
)


# ── Audio bridge ─────────────────────────────────────────────────────────────

def _init_audio_bridge():
    global _audio_bridge_ok, _udp_recv, _udp_send

    try:
        _udp_recv = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        _udp_recv.setsockopt(_socket.SOL_SOCKET, _socket.SO_RCVBUF, 65536)
        _udp_recv.bind(("0.0.0.0", AUDIO_MIC_PORT))

        _udp_send = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)

        def _recv_loop():
            global _esp32_audio_ip, _audio_recv_count, _audio_emit_count
            import time as _time
            _last_log = _time.time()
            while True:
                try:
                    raw, addr = _udp_recv.recvfrom(4096)
                    _esp32_audio_ip = addr[0]
                    _audio_recv_count += 1

                    mode = settings.get("mic_denoise", MIC_DENOISE_MODE)
                    if mode not in ("off", "hpf", "full"):
                        mode = "full"

                    # Two parallel streams out of ONE HPF pass:
                    #   listen_data -> what humans hear (full spectral gate if enabled)
                    #   stt_data    -> what Whisper / OpenWakeWord see (HPF only)
                    # Aggressive spectral gating wrecks STT/wake-word accuracy
                    # (mask artifacts + clipped fricatives), so we never feed the
                    # gate output to them.
                    listen_data, stt_data = _mic_denoiser.process_pcm_bytes_split(raw, mode=mode)

                    if _robot_recording:
                        _robot_buffer.append(stt_data)
                    elif _wake_word_enabled and _wake_word_feed(stt_data):
                        socketio.emit("robot_status", {"state": "wake_word", "detail": "Computer"}, namespace="/audio")
                        _threading.Thread(target=_robot_pipeline, daemon=True).start()
                    socketio.emit("esp_audio", listen_data, namespace="/audio")
                    _audio_emit_count += 1
                    now = _time.time()
                    if now - _last_log >= 5.0:
                        print(
                            f"[AUDIO] recv={_audio_recv_count} emit={_audio_emit_count} "
                            f"listeners={_audio_listeners} from={addr[0]} denoise={mode}",
                            flush=True,
                        )
                        _last_log = now
                except Exception as e:
                    print(f"[AUDIO] recv error: {e}", flush=True)
                    continue

        _threading.Thread(target=_recv_loop, daemon=True).start()
        _audio_bridge_ok = True

        if not ESP32_IP_OVERRIDE:
            _threading.Thread(
                target=_esp32_resolver_refresh,
                kwargs={"sync": False},
                daemon=True,
                name="esp32-resolver-initial",
            ).start()
            _threading.Thread(
                target=_esp32_bg_resolver_loop,
                daemon=True,
                name="esp32-resolver-loop",
            ).start()

        resolved = _esp32_send_ip()
        print(
            f"[AUDIO] Bridge active on UDP port {AUDIO_MIC_PORT} | "
            f"ESP32 MAC={ESP32_MAC} -> IP={resolved or 'discovering...'} "
            f"(source={_esp32_ip_source or 'none'})",
            flush=True,
        )
    except OSError as e:
        print(f"[AUDIO] Port 12345 in use -- audio bridge disabled: {e}", flush=True)


_init_audio_bridge()


@socketio.on("connect", namespace="/audio")
def _on_audio_connect():
    global _audio_listeners
    _audio_listeners += 1
    print(f"[AUDIO] Client connected ({_audio_listeners} listeners)", flush=True)


@socketio.on("disconnect", namespace="/audio")
def _on_audio_disconnect():
    global _audio_listeners
    _audio_listeners = max(0, _audio_listeners - 1)
    print(f"[AUDIO] Client disconnected ({_audio_listeners} listeners)", flush=True)


_browser_audio_stats = {
    "pkts_ok": 0,
    "pkts_no_ip": 0,
    "pkts_err": 0,
    "last_err": "",
    "last_no_ip_log": 0.0,
    "last_err_log": 0.0,
    "first_ok_logged": False,
}


@socketio.on("browser_audio", namespace="/audio")
def _on_browser_audio(data):
    import time as _t
    st = _browser_audio_stats

    if not _udp_send:
        return

    ip = _esp32_send_ip()
    now = _t.time()

    if not ip:
        st["pkts_no_ip"] += 1
        if now - st["last_no_ip_log"] >= 3.0:
            print(
                f"[AUDIO] browser_audio dropped: ESP32 IP not resolved "
                f"(mac={ESP32_MAC}, env_override={ESP32_IP_OVERRIDE or 'unset'}, "
                f"udp_src={_esp32_audio_ip or 'none'}, dropped={st['pkts_no_ip']}). "
                f"Set ESP32_IP in .env or ping the device so it appears in `arp -a`.",
                flush=True,
            )
            st["last_no_ip_log"] = now
        return

    try:
        shaped = _speaker_shaper.process(data)
        _udp_send.sendto(shaped, (ip, AUDIO_SPK_PORT))
        st["pkts_ok"] += 1
        if not st["first_ok_logged"]:
            print(
                f"[AUDIO] browser -> ESP32 OK: {ip}:{AUDIO_SPK_PORT} "
                f"(source={_esp32_ip_source}, first packet {len(data)}B)",
                flush=True,
            )
            st["first_ok_logged"] = True
    except Exception as e:
        st["pkts_err"] += 1
        st["last_err"] = str(e)
        if now - st["last_err_log"] >= 3.0:
            print(
                f"[AUDIO] browser_audio sendto({ip}:{AUDIO_SPK_PORT}) "
                f"failed: {e} (errs={st['pkts_err']})",
                flush=True,
            )
            st["last_err_log"] = now


@app.route("/api/audio/status", methods=["GET"])
def audio_status():
    import time as _t
    send_ip = _esp32_send_ip()
    st = _browser_audio_stats
    age = (_t.time() - _esp32_ip_cache_time) if _esp32_ip_cache_time else None
    return jsonify({
        "bridge": _audio_bridge_ok,
        "esp32_mac": ESP32_MAC,
        "esp32_ip_env": ESP32_IP_OVERRIDE,
        "esp32_ip_udp_source": _esp32_audio_ip,
        "esp32_send_ip": send_ip,
        "esp32_send_ip_source": _esp32_ip_source,
        "esp32_ip_age_seconds": round(age, 1) if age is not None else None,
        "esp32_resolver_running": _esp32_resolver_running,
        "spk_port": AUDIO_SPK_PORT,
        "mic_port": AUDIO_MIC_PORT,
        "listeners": _audio_listeners,
        "recv_count": _audio_recv_count,
        "emit_count": _audio_emit_count,
        "browser_audio": {
            "pkts_ok": st["pkts_ok"],
            "pkts_no_ip": st["pkts_no_ip"],
            "pkts_err": st["pkts_err"],
            "last_err": st["last_err"],
        },
    })


@app.route("/api/audio/refresh-esp32", methods=["POST"])
def audio_refresh_esp32():
    """Force a fresh (verified) re-discovery of the ESP32's IP."""
    global _esp32_ip_cache, _esp32_ip_cache_time, _esp32_last_sweep_ts
    _esp32_ip_cache = None
    _esp32_ip_cache_time = 0
    _esp32_last_sweep_ts = 0
    _esp32_resolver_refresh(sync=True)
    return jsonify({
        "esp32_send_ip": _esp32_ip_cache,
        "source": _esp32_ip_source,
    })


# ═══════════════════════ ROBOT VOICE PIPELINE ═══════════════════════

import struct as _struct
import wave as _wave
import math as _math
import asyncio as _asyncio
import numpy as _np

_whisper_models = {}

def _get_whisper(size="tiny"):
    if size not in _whisper_models:
        from faster_whisper import WhisperModel
        try:
            print(f"[ROBOT] Loading Whisper model ({size})...", flush=True)
            # _whisper_models[size] = WhisperModel(size, device="cpu", compute_type="int8")
            _whisper_models[size] = WhisperModel(size, device="cuda", compute_type="float16")
            print(f"[ROBOT] Whisper model ({size}) loaded.", flush=True)
        except Exception as e:
            print(f"[ROBOT] Failed to load Whisper ({size}): {e}", flush=True)
            if size != "tiny":
                print(f"[ROBOT] Falling back to tiny model", flush=True)
                return _get_whisper("tiny")
            raise
    return _whisper_models[size]

_WHISPER_MODEL_FOR_LANG = {"en": "small", "ru": "small", "kk": "small"}

def _preload_whisper():
    _get_whisper("small")

_threading.Thread(target=_preload_whisper, daemon=True).start()


def _generate_beep(freq=800, duration_ms=300, sample_rate=16000):
    n_samples = int(sample_rate * duration_ms / 1000)
    pcm = bytearray(n_samples * 2)
    for i in range(n_samples):
        t = i / sample_rate
        fade = min(i, n_samples - i, 200) / 200.0
        val = int(12000 * fade * _math.sin(2 * _math.pi * freq * t))
        _struct.pack_into("<h", pcm, i * 2, max(-32768, min(32767, val)))
    return bytes(pcm)


# ── PC microphone / speaker support ──────────────────────────────────────────

def _record_from_pc_mic(silence_threshold=500, silence_duration=1.0,
                        max_record_time=15.0, sample_rate=16000):
    """Record from default PC mic until silence. Returns raw PCM bytes."""
    import pyaudio
    import time

    CHUNK = 1024
    pa = pyaudio.PyAudio()
    try:
        stream = pa.open(format=pyaudio.paInt16, channels=1,
                         rate=sample_rate, input=True,
                         frames_per_buffer=CHUNK)
    except Exception as e:
        pa.terminate()
        raise RuntimeError(f"Cannot open PC microphone: {e}")

    print("[PC-MIC] Recording from PC microphone...", flush=True)
    frames = []
    speech_started = False
    silence_start = None
    record_start = time.time()

    try:
        while True:
            elapsed = time.time() - record_start
            if elapsed > max_record_time:
                print(f"[PC-MIC] Max recording time reached ({max_record_time}s)", flush=True)
                break

            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)

            n_samples = len(data) // 2
            if n_samples == 0:
                continue
            samples = _struct.unpack(f"<{n_samples}h", data)
            peak = max(abs(s) for s in samples)

            if not speech_started:
                if peak > silence_threshold:
                    speech_started = True
                    silence_start = None
                    print(f"[PC-MIC] Speech detected (peak={peak})", flush=True)
            else:
                if peak < silence_threshold:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= silence_duration:
                        print("[PC-MIC] Silence detected, stopping", flush=True)
                        break
                else:
                    silence_start = None
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

    return b"".join(frames)


def _play_pcm_on_pc_speaker(pcm_bytes, sample_rate=16000):
    """Play raw 16-bit PCM on the default PC speaker."""
    import pyaudio
    CHUNK = 1024
    pa = pyaudio.PyAudio()
    try:
        stream = pa.open(format=pyaudio.paInt16, channels=1,
                         rate=sample_rate, output=True,
                         frames_per_buffer=CHUNK)
        for offset in range(0, len(pcm_bytes), CHUNK):
            stream.write(pcm_bytes[offset:offset + CHUNK])
        stream.stop_stream()
        stream.close()
    finally:
        pa.terminate()


def _tts_stream_to_pc_speaker(text, lang="en"):
    """Stream Edge TTS -> ffmpeg (mp3->pcm) -> PC speaker via pyaudio."""
    import edge_tts
    import subprocess
    import pyaudio
    import time

    voices_to_try = _TTS_VOICE_FALLBACKS.get(lang, _TTS_VOICE_FALLBACKS["en"])
    voice = voices_to_try[0]
    sample_rate = 16000
    CHUNK = 1024
    t0 = time.time()
    total_pcm = 0
    first_audio_at = None

    ffmpeg_proc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-i", "pipe:0",
         "-f", "s16le", "-ar", str(sample_rate), "-ac", "1",
         "pipe:1"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        bufsize=8192,
    )

    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=1,
                     rate=sample_rate, output=True,
                     frames_per_buffer=CHUNK)

    def _pcm_player():
        nonlocal total_pcm, first_audio_at
        while True:
            pcm = ffmpeg_proc.stdout.read(CHUNK)
            if not pcm:
                break
            if first_audio_at is None:
                first_audio_at = time.time()
            total_pcm += len(pcm)
            stream.write(pcm)

    player_thread = _threading.Thread(target=_pcm_player, daemon=True)
    player_thread.start()

    loop = _asyncio.new_event_loop()
    try:
        async def _stream():
            comm = edge_tts.Communicate(text, voice, rate=TTS_RATE)
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    try:
                        ffmpeg_proc.stdin.write(chunk["data"])
                        ffmpeg_proc.stdin.flush()
                    except BrokenPipeError:
                        break
        loop.run_until_complete(_stream())
    except Exception as e:
        print(f"[ROBOT] PC TTS error ({voice}): {e}", flush=True)
    finally:
        loop.close()

    try:
        ffmpeg_proc.stdin.close()
    except Exception:
        pass
    player_thread.join(timeout=30)
    ffmpeg_proc.wait(timeout=10)
    stream.stop_stream()
    stream.close()
    pa.terminate()

    tts_latency = (first_audio_at - t0) if first_audio_at else (time.time() - t0)
    print(f"[ROBOT] PC-TTS: {voice} | gen={tts_latency:.2f}s | {total_pcm}B pcm", flush=True)
    return tts_latency


def _send_pcm_to_esp32(pcm_bytes, sample_rate=16000):
    if not _esp32_send_ip() or not _udp_send:
        return
    import time
    chunk_size = 512
    bytes_per_sec = sample_rate * 2
    chunk_dur = chunk_size / bytes_per_sec
    start = time.time()
    i = 0
    for offset in range(0, len(pcm_bytes), chunk_size):
        chunk = pcm_bytes[offset:offset + chunk_size]
        chunk = _speaker_shaper.process(chunk)
        try:
            _udp_send.sendto(chunk, (_esp32_send_ip(), AUDIO_SPK_PORT))
        except Exception:
            pass
        i += 1
        deadline = start + i * chunk_dur * 0.98
        delay = deadline - time.time()
        if delay > 0:
            time.sleep(delay)


def _pcm_buffer_to_wav(pcm_bytes, sample_rate=16000):
    buf = io.BytesIO()
    with _wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    buf.seek(0)
    return buf


_LANG_SETTING_TO_WHISPER = {"EN": "en", "RU": "ru", "KZ": "kk"}


def _mangisoz_stt(wav_buf):
    """Kazakh STT via Mangisoz API with key rotation."""
    global _mangisoz_key_index
    if not MANGISOZ_API_KEYS:
        return None, "No MANGISOZ_API_KEYS configured"

    wav_buf.seek(0)
    wav_bytes = wav_buf.read()

    last_error = ""
    for _attempt in range(len(MANGISOZ_API_KEYS)):
        key = MANGISOZ_API_KEYS[_mangisoz_key_index]
        url = f"{MANGISOZ_BASE}/api/v1/stt/transcribe"
        try:
            resp = requests.post(
                url,
                headers={"X-API-Key": key},
                files={"audio": ("audio.wav", wav_bytes, "audio/wav")},
                data={"language": "kk", "response_format": "json"},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("text", "").strip()
                return text, None

            if resp.status_code in (402, 429, 503):
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                _mangisoz_key_index = (_mangisoz_key_index + 1) % len(MANGISOZ_API_KEYS)
                continue

            return None, f"Mangisoz API error ({resp.status_code}): {resp.text[:200]}"
        except Exception as e:
            last_error = str(e)
            _mangisoz_key_index = (_mangisoz_key_index + 1) % len(MANGISOZ_API_KEYS)
            continue

    return None, f"All Mangisoz keys exhausted. Last: {last_error}"


def _gemini_stt(wav_buf):
    """Kazakh STT fallback via Gemini generateContent with inline audio."""
    global _gemini_key_index
    if not GEMINI_API_KEYS:
        return None, "No GEMINI_API_KEYS configured"

    import base64
    wav_buf.seek(0)
    audio_b64 = base64.b64encode(wav_buf.read()).decode("ascii")

    system_text = (
        "Transcribe the following Kazakh audio exactly. "
        "Return ONLY the transcribed Kazakh text, nothing else."
    )
    contents = [
        {
            "parts": [
                {"inline_data": {"mime_type": "audio/wav", "data": audio_b64}},
                {"text": "Transcribe this Kazakh speech."},
            ]
        }
    ]

    last_error = ""
    for _attempt in range(len(GEMINI_API_KEYS)):
        key = GEMINI_API_KEYS[_gemini_key_index]
        url = f"{GEMINI_BASE}/models/gemini-2.0-flash:generateContent?key={key}"
        payload = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system_text}]},
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024},
        }
        try:
            resp = requests.post(url, json=payload, timeout=60)
            resp_data = resp.json()
            if resp.status_code == 200 and "candidates" in resp_data:
                parts = resp_data["candidates"][0]["content"]["parts"]
                text = "".join(p["text"] for p in parts if "text" in p).strip()
                return text, None

            error = resp_data.get("error", {})
            status = error.get("status", "")
            msg = error.get("message", str(resp_data))
            if status in ("RESOURCE_EXHAUSTED", "RATE_LIMIT_EXCEEDED") or resp.status_code == 429:
                last_error = msg
                _gemini_key_index = (_gemini_key_index + 1) % len(GEMINI_API_KEYS)
                continue
            return None, f"Gemini STT error ({resp.status_code}): {msg}"
        except Exception as e:
            last_error = str(e)
            _gemini_key_index = (_gemini_key_index + 1) % len(GEMINI_API_KEYS)
            continue

    return None, f"All Gemini keys exhausted. Last: {last_error}"


def _whisper_stt(wav_buf, whisper_lang):
    """STT via local Whisper model (used for EN/RU and as last-resort fallback)."""
    import time
    model_size = _WHISPER_MODEL_FOR_LANG.get(whisper_lang, "tiny")
    t0 = time.time()
    model = _get_whisper(model_size)
    t_load = time.time() - t0
    t1 = time.time()
    wav_buf.seek(0)
    # NOTE: vad_filter=False on purpose. We already do our own silence detection
    # in _robot_pipeline (SILENCE_THRESHOLD / SILENCE_DURATION). Silero VAD
    # inside faster-whisper tends to reject HPF'd / slightly-denoised speech
    # (especially lower-pitched male voices, because 120 Hz HPF clips part of
    # the vocal fundamental), which made the pipeline return "Could not
    # understand speech" even when the audio was perfectly intelligible.
    segments, info = model.transcribe(
        wav_buf, beam_size=5,
        language=whisper_lang,
        vad_filter=False,
        condition_on_previous_text=False,
        temperature=0.0,
        no_speech_threshold=0.8,
    )
    text = " ".join(seg.text for seg in segments).strip()
    t_transcribe = time.time() - t1
    print(f"[ROBOT] Whisper STT: '{text}' (lang={whisper_lang}, model={model_size}) "
          f"| load={t_load:.2f}s transcribe={t_transcribe:.2f}s", flush=True)
    return text, whisper_lang


def _stt(wav_buf):
    import time

    ui_lang = settings.get("language", "EN")
    whisper_lang = _LANG_SETTING_TO_WHISPER.get(ui_lang, "en")

    if whisper_lang != "kk":
        return _whisper_stt(wav_buf, whisper_lang)

    t0 = time.time()

    text, err = _mangisoz_stt(wav_buf)
    if text:
        elapsed = time.time() - t0
        print(f"[ROBOT] STT: '{text}' (lang=kk, backend=mangisoz) | {elapsed:.2f}s", flush=True)
        return text, "kk"
    print(f"[ROBOT] Mangisoz STT failed: {err}  -> trying Gemini", flush=True)

    text, err = _gemini_stt(wav_buf)
    if text:
        elapsed = time.time() - t0
        print(f"[ROBOT] STT: '{text}' (lang=kk, backend=gemini) | {elapsed:.2f}s", flush=True)
        return text, "kk"
    print(f"[ROBOT] Gemini STT failed: {err}  -> falling back to Whisper", flush=True)

    return _whisper_stt(wav_buf, "kk")


_TTS_VOICES = {
    "en": "en-US-AriaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "kk": "kk-KZ-AigulNeural",
}

_TTS_VOICE_FALLBACKS = {
    "ru": ["ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural"],
    "kk": ["kk-KZ-AigulNeural", "kk-KZ-DauletNeural"],
    "en": ["en-US-AriaNeural"],
}


TTS_RATE = os.environ.get("TTS_RATE", "+18%")

# ── ESP32 speaker safety pipeline ────────────────────────────────────────────
#
# The ESP32 firmware multiplies every sample by ~2.0x before writing to the
# MAX98357A amp, then hard-clips at int16 bounds. Any peak > 0.5 coming out of
# the server therefore becomes a full-scale clipped peak at the amp. Full-scale
# peaks on a tiny amp like the MAX98357A draw 0.5-1 A for a few ms; on an
# underpowered USB/PSU this trips the amp's undervoltage lockout, muting the
# speaker for 2-4 seconds ("speaker stops working on loud sounds").
#
# We counter this on the server with:
#   1. A high-pass at ~150 Hz. Sub-150 Hz content draws disproportionate amp
#      current (speaker impedance ~= DC resistance at low frequencies) while
#      contributing almost nothing to speech intelligibility on this driver.
#   2. A stateful soft peak limiter that caps the amplitude at a ceiling
#      chosen to account for the firmware's 2x gain.
#
# Effective amp input peak ≈ SPK_PEAK_CEILING * ESP32_FIRMWARE_GAIN.
ESP32_FIRMWARE_GAIN = _env_float("ESP32_FIRMWARE_GAIN", 2.0)
SPK_PEAK_CEILING = _env_float("TTS_PEAK_CEILING", 0.25)  # backwards compat: old name still reads
SPK_HPF_HZ = _env_float("SPK_HPF_HZ", 150.0)


class SpeakerShaper:
    """Stateful HPF + soft peak limiter applied to every int16 PCM chunk bound
    for the ESP32 speaker. Shared across all paths (TTS, beeps, browser mic)."""

    def __init__(self, sample_rate=16000, hpf_hz=150.0, ceiling=0.35):
        import numpy as _np
        import math as _math
        self._np = _np
        self.sr = sample_rate
        self.ceiling = max(0.05, min(0.99, float(ceiling)))

        Q = 1.0 / _math.sqrt(2.0)
        w0 = 2 * _math.pi * hpf_hz / sample_rate
        cw, sw = _math.cos(w0), _math.sin(w0)
        alpha = sw / (2 * Q)
        a0 = 1 + alpha
        self._b0 = (1 + cw) / 2 / a0
        self._b1 = -(1 + cw) / a0
        self._b2 = (1 + cw) / 2 / a0
        self._a1 = -2 * cw / a0
        self._a2 = (1 - alpha) / a0

        self._have_scipy = False
        try:
            from scipy.signal import lfilter  # noqa: F401
            self._lfilter = lfilter
            self._b = _np.array([self._b0, self._b1, self._b2], dtype=_np.float32)
            self._a = _np.array([1.0, self._a1, self._a2], dtype=_np.float32)
            self._zi = _np.zeros(2, dtype=_np.float32)
            self._have_scipy = True
        except Exception:
            self._z1 = 0.0
            self._z2 = 0.0

        self._gain = 1.0
        self._lock = _threading.Lock()

    def reset_state(self):
        """Clear filter state and restore gain. Call at the start of an utterance
        so a long pause doesn't leave the HPF with stale state."""
        with self._lock:
            if self._have_scipy:
                self._zi = self._np.zeros(2, dtype=self._np.float32)
            else:
                self._z1 = 0.0
                self._z2 = 0.0
            self._gain = 1.0

    def _hpf(self, x):
        if self._have_scipy:
            y, self._zi = self._lfilter(self._b, self._a, x, zi=self._zi)
            return y
        np = self._np
        y = np.empty_like(x)
        z1, z2 = self._z1, self._z2
        b0, b1, b2 = self._b0, self._b1, self._b2
        a1, a2 = self._a1, self._a2
        for i in range(len(x)):
            xi = float(x[i])
            yi = b0 * xi + z1
            z1 = b1 * xi + z2 - a1 * yi
            z2 = b2 * xi - a2 * yi
            y[i] = yi
        self._z1, self._z2 = z1, z2
        return y

    def process(self, pcm_bytes):
        """Fast-attack, slow-release peak limiter with a brick-wall safety clip.

        Previously this used a single linear ramp from the previous chunk's gain
        to the target gain, spread across the whole chunk. That meant peaks near
        the start of a chunk could pass through at near-full amplitude (first
        sample saw old gain, the reduction only finished ~16 ms later). For TTS,
        where every word onset is a large peak, that caused repeated full-scale
        spikes into the amp and tripped its UVLO / the PSU's OCP.

        New behaviour:
          - ATTACK (peak too loud): drop to the target gain essentially at once
            (~0.5 ms linear ramp just to avoid a click) and hold it for the rest
            of the chunk.
          - RELEASE (no peak): gently rise toward 1.0 across the whole chunk.
          - BRICK WALL: a hard clip at ±ceiling catches anything that might
            slip through during the 0.5 ms attack window or floating-point
            edge cases. Very brief hard-clips are inaudible on speech.
        """
        if len(pcm_bytes) < 4:
            return pcm_bytes
        try:
            np = self._np
            with self._lock:
                x = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) * (1.0 / 32768.0)
                x = self._hpf(x)
                if x.size == 0:
                    return pcm_bytes

                peak = float(np.max(np.abs(x)))
                g0 = self._gain

                if peak > self.ceiling:
                    g_this_max = self.ceiling / peak   # keeps this chunk's peak at ceiling
                else:
                    g_this_max = 1.0

                if g_this_max < g0:
                    # Fast attack: very short ramp (~0.5 ms) from g0 down to the
                    # target, then hold. Peaks located AFTER the ramp are fully
                    # clamped. Peaks WITHIN the ramp are caught by the brick
                    # wall below.
                    attack_samples = min(8, x.size)
                    envelope = np.full(x.size, g_this_max, dtype=np.float32)
                    if attack_samples > 1:
                        envelope[:attack_samples] = np.linspace(g0, g_this_max, attack_samples)
                    g_end = g_this_max
                else:
                    # Gentle release toward unity (~0.3 s full release)
                    g_end = min(1.0, g0 + 0.05)
                    envelope = np.linspace(g0, g_end, x.size, dtype=np.float32)

                y = x * envelope
                # Brick wall. Critical: this is what actually guarantees no
                # sample ever exceeds the ceiling, regardless of attack-window
                # leakage or the previous chunk's tail.
                np.clip(y, -self.ceiling, self.ceiling, out=y)

                self._gain = float(g_end)

            return (y * 32767.0).astype(np.int16).tobytes()
        except Exception as e:
            print(f"[SPK] shaper error: {e} (passing raw)", flush=True)
            return pcm_bytes


_speaker_shaper = SpeakerShaper(
    sample_rate=16000,
    hpf_hz=SPK_HPF_HZ,
    ceiling=SPK_PEAK_CEILING,
)
print(
    f"[SPK] SpeakerShaper ready: hpf={SPK_HPF_HZ:.0f}Hz, "
    f"ceiling={SPK_PEAK_CEILING:.2f} "
    f"(effective peak at amp ~= {SPK_PEAK_CEILING * ESP32_FIRMWARE_GAIN:.2f} "
    f"after firmware {ESP32_FIRMWARE_GAIN}x gain), "
    f"scipy={'yes' if _speaker_shaper._have_scipy else 'no (python biquad)'}",
    flush=True,
)


def _tts_stream_to_esp32(text, lang="en"):
    """Stream Edge TTS -> ffmpeg (mp3->pcm) -> UDP to ESP32, true streaming."""
    import edge_tts
    import subprocess
    import time

    voices_to_try = _TTS_VOICE_FALLBACKS.get(lang, _TTS_VOICE_FALLBACKS["en"])
    voice = voices_to_try[0]
    send_ip = _esp32_send_ip()

    if not send_ip or not _udp_send:
        print("[ROBOT] TTS: no ESP32 IP or UDP socket, skipping", flush=True)
        return

    t0 = time.time()
    sample_rate = 16000
    bytes_per_sec = sample_rate * 2   # 32000 B/s
    # 512 B = 16 ms at 16 kHz mono. Matches the ESP32 I2S DMA depth much better
    # than 32 ms chunks, so i2s_write never blocks long enough to let the UDP
    # queue fill. Keeps playback smooth on the speaker side.
    chunk_size = 512
    chunk_dur = chunk_size / bytes_per_sec           # seconds per chunk
    # Lead factor < 1.0 means "send slightly ahead of playback" — primes the
    # ESP32 buffer without overrunning it. Keep this conservative.
    lead = 0.98
    total_mp3 = 0
    total_pcm = 0
    chunks_sent = 0
    drops = 0
    first_audio_at = None

    ffmpeg_proc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-i", "pipe:0",
         "-f", "s16le", "-ar", str(sample_rate), "-ac", "1",
         "pipe:1"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        bufsize=8192,
    )

    _speaker_shaper.reset_state()

    def _pcm_sender():
        nonlocal total_pcm, chunks_sent, first_audio_at, drops
        # Absolute deadline schedule: the i-th chunk goes out at start + i*dt.
        # Using time.sleep(dt) inside the loop accumulates drift (we'd run
        # ~18% fast like the old code did), which overflows the ESP32's small
        # UDP queue → the chopped "Sorr... API... expired..." effect.
        start = None
        i = 0
        while True:
            pcm = ffmpeg_proc.stdout.read(chunk_size)
            if not pcm:
                break
            pcm = _speaker_shaper.process(pcm)
            if first_audio_at is None:
                first_audio_at = time.time()
                start = first_audio_at
            total_pcm += len(pcm)
            try:
                _udp_send.sendto(pcm, (send_ip, AUDIO_SPK_PORT))
            except Exception:
                drops += 1
            chunks_sent += 1
            i += 1
            deadline = start + i * chunk_dur * lead
            delay = deadline - time.time()
            if delay > 0:
                time.sleep(delay)

    sender_thread = _threading.Thread(target=_pcm_sender, daemon=True)
    sender_thread.start()

    loop = _asyncio.new_event_loop()
    try:
        async def _stream():
            nonlocal total_mp3
            comm = edge_tts.Communicate(text, voice, rate=TTS_RATE)
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    data = chunk["data"]
                    total_mp3 += len(data)
                    try:
                        ffmpeg_proc.stdin.write(data)
                        ffmpeg_proc.stdin.flush()
                    except BrokenPipeError:
                        break
        loop.run_until_complete(_stream())
    except Exception as e:
        print(f"[ROBOT] TTS stream error ({voice}): {e}", flush=True)
    finally:
        loop.close()

    try:
        ffmpeg_proc.stdin.close()
    except Exception:
        pass
    sender_thread.join(timeout=30)
    ffmpeg_proc.wait(timeout=10)

    t_total = time.time() - t0
    tts_latency = (first_audio_at - t0) if first_audio_at else t_total
    audio_secs = total_pcm / bytes_per_sec
    playback_time = t_total - tts_latency if first_audio_at else 0

    print(f"[ROBOT] TTS: {voice} rate={TTS_RATE} | "
          f"gen={tts_latency:.2f}s | play={playback_time:.2f}s ({audio_secs:.1f}s audio) | "
          f"{total_mp3}B mp3 -> {total_pcm}B pcm | {chunks_sent} chunks | drops={drops}",
          flush=True)
    return tts_latency


def _robot_pipeline():
    global _robot_recording
    import time

    use_pc = settings.get("audio_source", "esp32") == "pc"
    source_label = "PC" if use_pc else "ESP32"

    try:
        pipeline_start = time.time()
        print(f"[ROBOT] Pipeline started (source={source_label}). esp32_send_ip={_esp32_send_ip()} bridge={_audio_bridge_ok}", flush=True)
        socketio.emit("robot_status", {"state": "listening"}, namespace="/audio")

        if use_pc:
            beep = _generate_beep(800, 300)
            _play_pcm_on_pc_speaker(beep)
            record_start = time.time()
            all_pcm = _record_from_pc_mic()
            silence_detected_at = time.time()
            first_audio_pkt_at = record_start
            end_beep = _generate_beep(600, 200)
            _play_pcm_on_pc_speaker(end_beep)
        else:
            beep = _generate_beep(800, 300)
            print(f"[ROBOT] Sending beep ({len(beep)}B) to {_esp32_send_ip()}:{AUDIO_SPK_PORT}", flush=True)
            _send_pcm_to_esp32(beep)

            _robot_buffer.clear()
            _robot_recording = True

            SILENCE_THRESHOLD = 500
            SILENCE_DURATION = 1.0
            MAX_RECORD_TIME = 15.0
            CHECK_INTERVAL = 0.1

            speech_started = False
            silence_start = None
            first_audio_pkt_at = None
            record_start = time.time()

            while True:
                time.sleep(CHECK_INTERVAL)
                elapsed = time.time() - record_start

                if elapsed > MAX_RECORD_TIME:
                    print(f"[ROBOT] Max recording time reached ({MAX_RECORD_TIME}s)", flush=True)
                    break

                if not _robot_buffer:
                    continue

                if first_audio_pkt_at is None:
                    first_audio_pkt_at = time.time()

                last_chunk = _robot_buffer[-1]
                n_samples = len(last_chunk) // 2
                if n_samples == 0:
                    continue
                samples = _struct.unpack(f"<{n_samples}h", last_chunk)
                peak = max(abs(s) for s in samples)

                if not speech_started:
                    if peak > SILENCE_THRESHOLD:
                        speech_started = True
                        silence_start = None
                        print(f"[ROBOT] Speech detected (peak={peak})", flush=True)
                else:
                    if peak < SILENCE_THRESHOLD:
                        if silence_start is None:
                            silence_start = time.time()
                        elif time.time() - silence_start >= SILENCE_DURATION:
                            print(f"[ROBOT] Silence detected, stopping recording", flush=True)
                            break
                    else:
                        silence_start = None

            _robot_recording = False
            silence_detected_at = time.time()

            end_beep = _generate_beep(600, 200)
            _send_pcm_to_esp32(end_beep)

            all_pcm = b"".join(_robot_buffer)
            _robot_buffer.clear()

        t_record = silence_detected_at - record_start
        audio_duration = len(all_pcm) / 32000.0
        print(f"[ROBOT] Recording ({source_label}): {audio_duration:.1f}s audio | {len(all_pcm)}B", flush=True)

        if len(all_pcm) < 3200:
            socketio.emit("robot_status", {"state": "idle", "error": "No speech detected"}, namespace="/audio")
            return

        socketio.emit("robot_status", {"state": "processing"}, namespace="/audio")

        t0 = time.time()
        wav_buf = _pcm_buffer_to_wav(all_pcm)
        user_text, detected_lang = _stt(wav_buf)
        t_stt = time.time() - t0

        if not user_text or len(user_text.strip()) < 2:
            socketio.emit("robot_status", {"state": "idle", "error": "Could not understand speech"}, namespace="/audio")
            return

        print(f"[ROBOT] STT: {t_stt:.2f}s | '{user_text}'", flush=True)
        socketio.emit("robot_transcription", {"text": user_text}, namespace="/audio")

        t0 = time.time()
        chat_history.append({"role": "user", "text": user_text})
        model = settings.get("model", "gemini-2.0-flash")
        personality = settings.get("personality", "default")
        system_text = PERSONALITY_PROMPTS.get(personality, PERSONALITY_PROMPTS["default"])
        if context_memory:
            memory_text = "\n".join(f"- {m['text']}" for m in context_memory)
            system_text += f"\n\nContext memory:\n{memory_text}"

        # ── Gmail → AI context bridge (voice) ─────────────────────────────
        # Mirror web chat behavior: if cached inbox emails exist, inject a tiny
        # summary so Gemini stops claiming it cannot access emails.
        try:
            with app.app_context():
                recent_emails = get_recent_emails(limit=3)
                if recent_emails:
                    system_text += (
                        "\n\nYou have access to the user's recent inbox emails via the app-provided cache below. "
                        "Use them to answer questions like 'last email', 'latest mail', 'who is it from', "
                        "'when did it arrive', and 'summarize it'.\n"
                    )
                    system_text += recent_emails
        except Exception:
            pass

        system_text += "\n\nYou are responding to a voice command. Keep your answer short and conversational (1-3 sentences). Do not use markdown, bullet points, or special formatting."

        contents = []
        for msg in chat_history[-20:]:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["text"]}]})

        # ── DEBUG: set to True to skip real API call ──
        _ROBOT_DEBUG = False
        # _ROBOT_DEBUG_TEXT = "Привет, это тестовое сообщение. Всё работает отлично!"
        # _ROBOT_DEBUG_TEXT = "Сәлеметсіз бе, бұл сынақ хабарлама. Бәрі жақсы жұмыс істейді!"
        _ROBOT_DEBUG_TEXT = "Hello, this is a test message. Everything works great!"
        if _ROBOT_DEBUG:
            ai_text = _ROBOT_DEBUG_TEXT
            t_llm = 0.0
        else:
            # ── Lamp command interception ──
            lamp_reply, lamp_st = _handle_lamp_command(user_text)
            if lamp_reply:
                ai_text = lamp_reply
                t_llm = 0.0
                if lamp_st:
                    socketio.emit("lamp_update", lamp_st, namespace="/audio")
            else:
                # ── Weather query interception ──
                weather_city = detect_weather_query(user_text)
                if weather_city:
                    w = fetch_weather(weather_city)
                    fc = fetch_forecast(weather_city)
                    ai_text = _format_weather_ai_reply(user_text, w, fc, model, system_text)
                    t_llm = time.time() - t0
                else:
                    # ── Email query interception (voice) ──
                    if _is_email_query(user_text):
                        ai_text = _format_email_direct_reply(user_text, email_data=None)
                        t_llm = time.time() - t0
                    else:
                        # ── Normal LLM call ──
                        ai_text, err = _gemini_call(model, system_text, contents)
                        t_llm = time.time() - t0
                        if err:
                            ai_text = f"Sorry, I had a problem: {err}"
        # ── END DEBUG ──
        chat_history.append({"role": "assistant", "text": ai_text})

        print(f"[ROBOT] LLM: {t_llm:.2f}s | '{ai_text[:80]}'", flush=True)
        socketio.emit("robot_response", {"text": ai_text}, namespace="/audio")

        socketio.emit("robot_status", {"state": "speaking"}, namespace="/audio")
        t_tts_start = time.time()
        tts_latency = 0
        try:
            if use_pc:
                tts_latency = _tts_stream_to_pc_speaker(ai_text, lang=detected_lang) or 0
            else:
                tts_latency = _tts_stream_to_esp32(ai_text, lang=detected_lang) or 0
            t_speak = time.time() - t_tts_start
        except Exception as e:
            t_speak = time.time() - t_tts_start
            print(f"[ROBOT] TTS error: {e}", flush=True)

        processing_time = t_stt + t_llm + tts_latency
        first_pkt_to_reply = (silence_detected_at - first_audio_pkt_at) + processing_time if first_audio_pkt_at else 0

        print(f"[ROBOT]", flush=True)
        print(f"[ROBOT] ======== PIPELINE SUMMARY ({source_label}) ========", flush=True)
        print(f"[ROBOT]  STT          : {t_stt:.2f}s", flush=True)
        print(f"[ROBOT]  LLM          : {t_llm:.2f}s", flush=True)
        print(f"[ROBOT]  TTS gen      : {tts_latency:.2f}s  (time to first audio out)", flush=True)
        print(f"[ROBOT]  TTS playback : {t_speak - tts_latency:.2f}s  (streaming to {source_label})", flush=True)
        print(f"[ROBOT]  --------------------------------", flush=True)
        print(f"[ROBOT]  PROCESSING   : {processing_time:.2f}s  = STT + LLM + TTS gen", flush=True)
        print(f"[ROBOT]  TOTAL WALL   : {time.time() - pipeline_start:.2f}s", flush=True)
        print(f"[ROBOT] ================================", flush=True)
        socketio.emit("robot_status", {"state": "idle"}, namespace="/audio")

    except Exception as e:
        _robot_recording = False
        _robot_buffer.clear()
        print(f"[ROBOT] Pipeline error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        socketio.emit("robot_status", {"state": "idle", "error": str(e)}, namespace="/audio")


@socketio.on("robot_start", namespace="/audio")
def _on_robot_start():
    if _robot_recording:
        socketio.emit("robot_status", {"state": "busy"}, namespace="/audio")
        return
    _threading.Thread(target=_robot_pipeline, daemon=True).start()


# ═══════════════════════ CAMERA / DEVICE CONTROL ═══════════════════════

KNOWN_DEVICES = {
    "88:13:bf:6c:60:94": "Camera",
    "9c:9c:1f:e9:96:f4": "Speaker",
}
CAMERA_MAC = "88:13:bf:6c:60:94"
_camera_ip = None


def _find_ip_by_mac(target_mac):
    """Look up an IP from the OS ARP table by MAC address."""
    target = target_mac.lower()
    try:
        output = subprocess.check_output(["arp", "-a"], text=True, timeout=5)
        for line in output.splitlines():
            ip_m = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
            mac_m = re.search(r"([\da-fA-F]{2}[:-]){5}[\da-fA-F]{2}", line)
            if ip_m and mac_m:
                mac = mac_m.group(0).lower().replace("-", ":")
                if mac == target:
                    return ip_m.group(1)
    except Exception:
        pass
    return None


def _ping_sweep_subnet():
    """Quick parallel ping sweep to populate the ARP cache."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    finally:
        s.close()
    prefix = ".".join(local_ip.split(".")[:3])
    procs = []
    for i in range(1, 255):
        p = subprocess.Popen(
            ["ping", "-n", "1", "-w", "200", f"{prefix}.{i}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        procs.append(p)
    for p in procs:
        p.wait()


@app.route("/api/camera/discover", methods=["GET"])
def camera_discover():
    global _camera_ip
    force = request.args.get("force", "false") == "true"

    if _camera_ip and not force:
        try:
            requests.get(f"http://{_camera_ip}/", timeout=2)
            return jsonify({
                "ip": _camera_ip,
                "stream_url": f"http://{_camera_ip}:81/stream",
            })
        except Exception:
            _camera_ip = None

    ip = _find_ip_by_mac(CAMERA_MAC)
    if not ip:
        _ping_sweep_subnet()
        ip = _find_ip_by_mac(CAMERA_MAC)

    if ip:
        _camera_ip = ip
        return jsonify({
            "ip": ip,
            "stream_url": f"http://{ip}:81/stream",
        })
    return jsonify({"error": "Camera not found on network"}), 404


@app.route("/api/camera/control", methods=["POST"])
def camera_control():
    global _camera_ip
    if not _camera_ip:
        _camera_ip = _find_ip_by_mac(CAMERA_MAC)
    if not _camera_ip:
        return jsonify({"error": "Camera not connected"}), 404

    data = request.get_json()
    direction = data.get("direction", "")
    if direction not in ("up", "down", "left", "right"):
        return jsonify({"error": "Invalid direction"}), 400

    try:
        requests.get(f"http://{_camera_ip}/action?go={direction}", timeout=3)
        return jsonify({"status": "ok", "direction": direction})
    except Exception as e:
        _camera_ip = None
        return jsonify({"error": f"Camera unreachable: {str(e)}"}), 502


if __name__ == '__main__':
    _debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
    print("\n" + "="*70)
    print("ARIA Application Starting")
    print("="*70)
    print(f"  Open: http://localhost:5000")
    print(f"  Debug mode: {'ON (development)' if _debug else 'OFF (production)'}")
    print(f"\n  Gmail OAuth: http://localhost:5000/api/gmail/login")
    print("="*70 + "\n")
    socketio.run(app, host='0.0.0.0', port=5000, debug=_debug, allow_unsafe_werkzeug=True)