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
from email.utils import parsedate_to_datetime as _email_parsedate_raw
import subprocess
import socket as _socket
import threading as _threading
from datetime import datetime, timedelta
from pathlib import Path
from gmail_service import GmailService
from models import db, User, Session, GmailAccount, EmailMessage


def _load_env():
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


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
    """Return gmail email: from session first, then restore from DB if authenticated."""
    email = session.get('gmail_email', '')
    if not email and gmail_service.is_authenticated():
        # Session lost (e.g. after OAuth popup) — restore from last GmailAccount in DB
        try:
            acct = GmailAccount.query.order_by(GmailAccount.id.desc()).first()
            if acct:
                email = acct.email
                session['gmail_email'] = email          # restore for future requests
                session['gmail_authenticated'] = True
        except Exception:
            pass
    return email


# ⚠️ ВАЖНО: Редирект 127.0.0.1 → localhost (для OAuth) 
@app.before_request
def redirect_127_to_localhost():
    """Перенаправляем 127.0.0.1 на localhost для совместимости с OAuth"""
    if request.host.startswith('127.0.0.1'):
        # Заменяем 127.0.0.1 на localhost в URL
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
chat_history = []

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
        "You can see and read emails that the user explicitly shares with you in the current conversation. "
        "When an email is provided in the context, you can analyze it, summarize it, help draft replies, or answer questions about it."
    ),
    "chill": (
        "You are ARIA, a super chill and laid-back smart home AI assistant. "
        "You speak in a relaxed, calm, easygoing tone. Use casual language, "
        "keep things mellow, and never stress about anything. "
        "Throw in phrases like 'no worries', 'all good', 'easy peasy'. "
        "You're like a cool friend who always keeps it zen. "
        "You can also read and help with emails that the user shares with you in the conversation."
    ),
    "bro": (
        "You are ARIA, a smart home AI assistant who talks like a total bro. "
        "You're enthusiastic, hype, and supportive. Use slang like 'bro', 'dude', "
        "'let's gooo', 'no cap', 'that's fire', 'W', 'bet'. "
        "You gas up the user and keep the energy high. You're their ride-or-die homie. "
        "You can also help with emails that the user shows you in the chat."
    ),
    "angry": (
        "You are ARIA, a smart home AI assistant who is perpetually annoyed and grumpy. "
        "You still help the user correctly, but you complain about it. "
        "You're sarcastic, impatient, and dramatic about being bothered. "
        "Think of a grumpy old man who knows everything but hates being asked. "
        "You sigh, you rant, but you ALWAYS give the correct answer in the end. "
        "You can also read emails that the user shares with you (while complaining about it)."
    ),
    "formal": (
        "You are ARIA, a smart home AI assistant who speaks in a highly formal, "
        "professional, and eloquent manner. You use sophisticated vocabulary, "
        "complete sentences, and polite expressions. Address the user respectfully. "
        "You are like a distinguished British butler — precise, courteous, and impeccable. "
        "You are also capable of reviewing and analyzing emails provided within the conversation context."
    ),
    "pirate": (
        "You are ARIA, a smart home AI assistant who speaks like a pirate. "
        "Use pirate slang: 'Ahoy', 'Aye aye', 'matey', 'shiver me timbers', "
        "'Arrr', 'ye', 'landlubber', 'treasure'. Talk about the seas, "
        "adventures, and treasure. But still give accurate, helpful answers. "
        "You're a salty sea dog who happens to be a tech genius and can read emails shared with ye."
    ),
    "sassy": (
        "You are ARIA, a smart home AI assistant with a sassy, witty personality. "
        "You're confident, a little dramatic, and love to throw shade (playfully). "
        "You serve looks AND knowledge. Think reality TV star who is secretly a genius. "
        "Use phrases like 'honey', 'sweetie', 'periodt', 'I said what I said', "
        "'not gonna lie'. You're fabulous and you know it. "
        "You can also read and help with emails that your user shares with you, hunty."
    ),
    "nerd": (
        "You are ARIA, a smart home AI assistant who is a total nerd/geek. "
        "You LOVE technical details, make references to sci-fi, gaming, anime, "
        "and pop culture. You get excited about science and tech. "
        "Use phrases like 'Actually...', 'Fun fact!', 'According to my calculations'. "
        "You're basically an excited encyclopedia who loves sharing knowledge. "
        "You can also analyze emails shared in the conversation with technical precision."
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# LAMP CONTROL — Yeelight
# ═══════════════════════════════════════════════════════════════════════════

LAMP_IP = (
    os.environ.get("LAMP_IP")
    or os.environ.get("YEELIGHT_IP")
    or os.environ.get("BULB_IP")
    or "10.72.61.149"
)

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

    def __init__(self, ip: str):
        self.ip = ip
        self._bulb = None
        self._state = {
            "ip": ip,
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
            try:
                from yeelight import Bulb
                self._bulb = Bulb(self.ip, auto_on=False)
            except Exception as exc:
                raise RuntimeError(f"Cannot connect to lamp at {self.ip}: {exc}") from exc
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


bulb_controller = AppBulbController(LAMP_IP)


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
    "weather", "temperature", "forecast", "wind", "humidity", "rain", "snow", "storm",
    "погода", "температура", "прогноз", "ветер", "влажность", "дождь", "снег",
    "ауа райы", "температура", "болжам", "жел", "ылғалдылық", "жаңбыр", "қар",
    "how cold", "how hot", "how warm", "какая погода", "сколько градусов",
]


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
    try:
        resp = requests.get(
            f"{OWM_BASE}/weather",
            params={"q": city, "appid": OWM_KEY, "units": "metric"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        d = resp.json()
        tz = d.get("timezone", 0)
        wind = d.get("wind", {})
        wind_speed_ms = wind.get("speed", 0)
        wind_kph = round(wind_speed_ms * 3.6, 1)
        vis_m = d.get("visibility", 10000)
        return {
            "city": d.get("name", city),
            "country": d.get("sys", {}).get("country", ""),
            "localtime": _epoch_to_localtime(d["dt"], tz),
            "localtime_epoch": d["dt"] + tz,
            "tz_id": _tz_id_str(tz),
            "last_updated": _epoch_to_localtime(d["dt"], tz),
            "temp": d["main"]["temp"],
            "feels_like": d["main"]["feels_like"],
            "temp_min": d["main"]["temp_min"],
            "temp_max": d["main"]["temp_max"],
            "humidity": d["main"]["humidity"],
            "pressure": d["main"]["pressure"],
            "wind_kph": wind_kph,
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
        return None


def fetch_forecast(city):
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


def detect_weather_query(message):
    msg = message.lower()
    if not any(kw in msg for kw in WEATHER_KEYWORDS):
        return None

    city_patterns = [
        r"weather\s+(?:in|at|for)\s+([a-zA-Z\s\-]+)",
        r"погод[аеу]\s+(?:в|во)\s+([а-яА-ЯёЁ\s\-]+)",
        r"температур[аеу]\s+(?:в|во)\s+([а-яА-ЯёЁ\s\-]+)",
        r"ауа райы\s+([а-яА-ЯёЁәіңғүұқөһa-zA-Z\s\-]+)",
        r"(?:in|at|for)\s+([a-zA-Z\s\-]+?)(?:\?|$|\.)",
        r"(?:в|во)\s+([а-яА-ЯёЁ\s\-]+?)(?:\?|$|\.)",
    ]
    for pattern in city_patterns:
        m = re.search(pattern, msg, re.IGNORECASE)
        if m:
            city = m.group(1).strip().rstrip("?., ")
            if len(city) > 1:
                return city
    return "Almaty"


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
        
        # Get recent emails ordered by received_at
        emails = EmailMessage.query.order_by(
            EmailMessage.received_at.desc()
        ).limit(limit).all()
        
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

    if email_data and (ask_sender or ask_time or ask_summary):
        sender = email_data.get("from", "Unknown")
        subject = email_data.get("subject", "(No subject)")
        date_text = email_data.get("date", "Unknown time")
        body = (email_data.get("body") or "").strip()
        body_short = (body[:220] + "...") if len(body) > 220 else body
        if lang == "ru":
            if ask_sender and not (ask_time or ask_summary):
                return f"Это письмо от: {sender}."
            if ask_time and not (ask_sender or ask_summary):
                return f"Письмо пришло: {date_text}."
            if ask_summary and not (ask_sender or ask_time):
                return f"Суть письма: {body_short or subject}"
            return f"Письмо от {sender}. Тема: {subject}. Время: {date_text}. Суть: {body_short or subject}"
        if lang == "kz":
            return f"Хат жіберуші: {sender}. Тақырып: {subject}. Уақыты: {date_text}. Мазмұны: {body_short or subject}"
        return f"The email is from {sender}. Subject: {subject}. Time: {date_text}. Summary: {body_short or subject}"

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
    time_str = first.received_at.strftime("%Y-%m-%d %H:%M")
    body_short = ((first.body or "")[:220] + "...") if len(first.body or "") > 220 else (first.body or "")

    if ask_sender and (ask_last or not ask_time):
        if lang == "ru":
            return f"Последнее письмо от: {first.sender}. Тема: {first.subject}. Время: {time_str}."
        if lang == "kz":
            return f"Соңғы хат мына адамнан: {first.sender}. Тақырыбы: {first.subject}. Уақыты: {time_str}."
        return f"Your latest email is from {first.sender}. Subject: {first.subject}. Time: {time_str}."

    if ask_time and not ask_summary:
        lines = [f"- {e.sender} | {e.subject} | {e.received_at.strftime('%Y-%m-%d %H:%M')}" for e in top]
        if lang == "ru":
            return "Время последних писем:\n" + "\n".join(lines)
        if lang == "kz":
            return "Соңғы хаттардың уақыты:\n" + "\n".join(lines)
        return "Times of recent emails:\n" + "\n".join(lines)

    if ask_summary:
        if lang == "ru":
            return f"Суть последнего письма:\nОт: {first.sender}\nТема: {first.subject}\nВремя: {time_str}\nКратко: {body_short or first.subject}"
        if lang == "kz":
            return f"Соңғы хаттың қысқаша мазмұны:\nКімнен: {first.sender}\nТақырып: {first.subject}\nУақыты: {time_str}\nМазмұны: {body_short or first.subject}"
        return f"Latest email summary:\nFrom: {first.sender}\nSubject: {first.subject}\nTime: {time_str}\nSummary: {body_short or first.subject}"

    lines = [f"- {e.sender} | {e.subject} | {e.received_at.strftime('%Y-%m-%d %H:%M')}" for e in top]
    if lang == "ru":
        return "Последние письма:\n" + "\n".join(lines)
    if lang == "kz":
        return "Соңғы хаттар:\n" + "\n".join(lines)
    return "Recent emails:\n" + "\n".join(lines)


def _format_weather_direct_reply(message: str, weather_data: dict) -> str:
    lang = _detect_message_lang(message)
    if not weather_data:
        if lang == "ru":
            return "Не удалось получить погоду для этого города."
        if lang == "kz":
            return "Бұл қала бойынша ауа райын алу мүмкін болмады."
        return "I could not fetch weather for that city."

    city = weather_data.get("city", "Unknown")
    country = weather_data.get("country", "")
    localtime = weather_data.get("localtime", "N/A")
    temp = weather_data.get("temp", "N/A")
    feels = weather_data.get("feels_like", "N/A")
    cond = weather_data.get("description", "N/A")
    humidity = weather_data.get("humidity", "N/A")
    wind = weather_data.get("wind_kph", "N/A")
    wind_dir = weather_data.get("wind_dir", "")

    if lang == "ru":
        return (
            f"Погода в {city}, {country}:\n"
            f"- Локальное время: {localtime}\n"
            f"- Температура: {temp}°C (ощущается как {feels}°C)\n"
            f"- Состояние: {cond}\n"
            f"- Влажность: {humidity}%\n"
            f"- Ветер: {wind} км/ч {wind_dir}"
        )
    if lang == "kz":
        return (
            f"{city}, {country} қаласындағы ауа райы:\n"
            f"- Жергілікті уақыт: {localtime}\n"
            f"- Температура: {temp}°C (сезіледі: {feels}°C)\n"
            f"- Жағдайы: {cond}\n"
            f"- Ылғалдылық: {humidity}%\n"
            f"- Жел: {wind} км/сағ {wind_dir}"
        )
    return (
        f"Weather in {city}, {country}:\n"
        f"- Local time: {localtime}\n"
        f"- Temperature: {temp}°C (feels like {feels}°C)\n"
        f"- Condition: {cond}\n"
        f"- Humidity: {humidity}%\n"
        f"- Wind: {wind} km/h {wind_dir}"
    )


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    email_data = data.get("email", None)  # Extract email if present
    
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    chat_history.append({"role": "user", "text": user_message})

    try:
        model = settings.get("model", "gemini-2.0-flash")

        personality = settings.get("personality", "default")
        system_text = PERSONALITY_PROMPTS.get(personality, PERSONALITY_PROMPTS["default"])
        if context_memory:
            memory_text = "\n".join(f"- {m['text']}" for m in context_memory)
            system_text += f"\n\nContext memory:\n{memory_text}"

        # Add email context if email is open
        if email_data:
            email_context = f"\n\n[CURRENT EMAIL CONTEXT]\n"
            if email_data.get("subject"):
                email_context += f"Subject: {email_data['subject']}\n"
            if email_data.get("from"):
                email_context += f"From: {email_data['from']}\n"
            if email_data.get("to"):
                email_context += f"To: {email_data['to']}\n"
            if email_data.get("date"):
                email_context += f"Date: {email_data['date']}\n"
            if email_data.get("body"):
                email_context += f"Content:\n{email_data['body']}\n"
            email_context += "\nYou can help analyze, summarize, reply to, or perform actions related to this email."
            system_text += email_context
        else:
            # If no email is explicitly open, fetch recent emails from database
            recent_emails = get_recent_emails(limit=10)
            if recent_emails:
                system_text += recent_emails

        # ── Lamp command interception (no Gemini needed) ──────────────────
        lamp_reply, lamp_st = _handle_lamp_command(user_message)
        if lamp_reply:
            chat_history.append({"role": "assistant", "text": lamp_reply})
            resp_data = {"reply": lamp_reply}
            if lamp_st:
                resp_data["lamp"] = lamp_st
            return jsonify(resp_data)
        # ─────────────────────────────────────────────────────────────────

        # ── Email query interception (deterministic, DB-backed) ──────────
        if _is_email_query(user_message):
            email_reply = _format_email_direct_reply(user_message, email_data=email_data)
            chat_history.append({"role": "assistant", "text": email_reply})
            return jsonify({"reply": email_reply})
        # ─────────────────────────────────────────────────────────────────

        # ── Weather query interception (deterministic, API-backed) ───────
        weather_city = detect_weather_query(user_message)
        if weather_city:
            w = fetch_weather(weather_city)
            weather_reply = _format_weather_direct_reply(user_message, w)
            chat_history.append({"role": "assistant", "text": weather_reply})
            return jsonify({"reply": weather_reply})
        # ─────────────────────────────────────────────────────────────────

        contents = []
        for msg in chat_history[-20:]:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["text"]}]})

        ai_text, err = _gemini_call(model, system_text, contents)
        if err:
            ai_text = err
    except Exception as e:
        ai_text = f"Connection error: {str(e)}"

    chat_history.append({"role": "assistant", "text": ai_text})
    return jsonify({"reply": ai_text})


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
        "api_keys_count": len(GEMINI_API_KEYS),
        "current_key_index": _gemini_key_index,
    })


@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.get_json()
    for key in ("model", "language", "personality"):
        if key in data:
            settings[key] = data[key]
    return jsonify({"status": "success"})


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

import hashlib
import secrets

# ═══════════════════════ PASSWORD HELPERS ═══════════════════════

def hash_password(password):
    """Hash password with salt"""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}${pwd_hash.hex()}"

def verify_password(stored_hash, password):
    """Verify password against hash"""
    try:
        salt, pwd_hash = stored_hash.split('$')
        return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex() == pwd_hash
    except:
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

        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({"error": "Email already registered"}), 400

        if len(password) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400

        # Create new user
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

        # Find user in database
        user = User.query.filter_by(email=email).first()
        
        if not user or not verify_password(user.password_hash, password):
            return jsonify({"error": "Invalid email or password"}), 401

        # Create session token
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
        is_auth = gmail_service.is_authenticated()
        gmail_email = _resolve_gmail_email()
        return jsonify({"authenticated": is_auth, "email": gmail_email}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/gmail/emails', methods=['GET'])
def get_gmail_emails():
    """Fetch emails from Gmail inbox"""
    try:
        if not gmail_service.is_authenticated():
            return jsonify({"error": "Not authenticated with Gmail"}), 401
        
        max_results = request.args.get('max_results', 10, type=int)
        result = gmail_service.get_emails(max_results=max_results)
        
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
        if not gmail_service.is_authenticated():
            return jsonify({"error": "Not authenticated with Gmail"}), 401
        
        data = request.json
        to = data.get('to', '').strip()
        subject = data.get('subject', '').strip()
        body = data.get('body', '').strip()
        
        if not all([to, subject, body]):
            return jsonify({"error": "Missing required fields: to, subject, body"}), 400
        
        result = gmail_service.send_email(to, subject, body)
        
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
            return jsonify({"emails": [], "source": "none"}), 200

        gmail_account = GmailAccount.query.filter_by(email=gmail_email).first()
        if not gmail_account:
            return jsonify({"emails": [], "source": "none"}), 200

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
            "total":        len(emails_data),
            "unread_count": unread,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/emails/sync', methods=['POST'])
def sync_emails():
    """Sync emails from Gmail and cache them with correct timestamps."""
    try:
        if not gmail_service.is_authenticated():
            return jsonify({"error": "Not authenticated with Gmail"}), 401

        gmail_email = _resolve_gmail_email()
        if not gmail_email:
            return jsonify({"error": "No Gmail session"}), 400

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

        result = gmail_service.get_emails_for_sync(query=query, max_results=max_results)

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
            svc = gmail_service.get_service()
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
ESP32_IP_OVERRIDE = os.environ.get("ESP32_IP", "192.168.137.140")
_esp32_audio_ip = None

def _esp32_send_ip():
    """Return the IP to send audio TO the ESP32. Prefers override (for NAT scenarios)."""
    return ESP32_IP_OVERRIDE or _esp32_audio_ip
_audio_listeners = 0
_audio_bridge_ok = False
_udp_recv = None
_udp_send = None
_audio_recv_count = 0
_audio_emit_count = 0

_robot_recording = False
_robot_buffer = []


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
                    data, addr = _udp_recv.recvfrom(4096)
                    _esp32_audio_ip = addr[0]
                    _audio_recv_count += 1
                    if _robot_recording:
                        _robot_buffer.append(data)
                    socketio.emit("esp_audio", data, namespace="/audio")
                    _audio_emit_count += 1
                    now = _time.time()
                    if now - _last_log >= 5.0:
                        print(f"[AUDIO] recv={_audio_recv_count} emit={_audio_emit_count} listeners={_audio_listeners} from={addr[0]}", flush=True)
                        _last_log = now
                except Exception as e:
                    print(f"[AUDIO] recv error: {e}", flush=True)
                    continue

        _threading.Thread(target=_recv_loop, daemon=True).start()
        _audio_bridge_ok = True
        print(f"[AUDIO] Bridge active on UDP port {AUDIO_MIC_PORT} | send_ip={ESP32_IP_OVERRIDE or 'auto-detect'}", flush=True)
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


@socketio.on("browser_audio", namespace="/audio")
def _on_browser_audio(data):
    if _esp32_send_ip() and _udp_send:
        try:
            _udp_send.sendto(data, (_esp32_send_ip(), AUDIO_SPK_PORT))
        except Exception:
            pass


@app.route("/api/audio/status", methods=["GET"])
def audio_status():
    return jsonify({
        "bridge": _audio_bridge_ok,
        "esp32_ip": _esp32_audio_ip,
        "listeners": _audio_listeners,
        "recv_count": _audio_recv_count,
        "emit_count": _audio_emit_count,
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
            _whisper_models[size] = WhisperModel(size, device="cuda", compute_type="float16")
            print(f"[ROBOT] Whisper model ({size}) loaded.", flush=True)
        except Exception as e:
            print(f"[ROBOT] Failed to load Whisper ({size}): {e}", flush=True)
            if size != "tiny":
                print(f"[ROBOT] Falling back to tiny model", flush=True)
                return _get_whisper("tiny")
            raise
    return _whisper_models[size]

_WHISPER_MODEL_FOR_LANG = {"en": "tiny", "ru": "tiny", "kk": "small"}

def _preload_whisper():
    _get_whisper("tiny")
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


def _send_pcm_to_esp32(pcm_bytes, sample_rate=16000):
    if not _esp32_send_ip() or not _udp_send:
        return
    import time
    chunk_size = 1024
    bytes_per_sec = sample_rate * 2
    for offset in range(0, len(pcm_bytes), chunk_size):
        chunk = pcm_bytes[offset:offset + chunk_size]
        try:
            _udp_send.sendto(chunk, (_esp32_send_ip(), AUDIO_SPK_PORT))
        except Exception:
            pass
        time.sleep(chunk_size / bytes_per_sec * 0.9)


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
    segments, info = model.transcribe(
        wav_buf, beam_size=5,
        language=whisper_lang,
        vad_filter=True,
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
    bytes_per_sec = sample_rate * 2
    chunk_size = 1024
    total_mp3 = 0
    total_pcm = 0
    chunks_sent = 0
    first_audio_at = None

    ffmpeg_proc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-i", "pipe:0",
         "-f", "s16le", "-ar", str(sample_rate), "-ac", "1",
         "pipe:1"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        bufsize=8192,
    )

    def _pcm_sender():
        nonlocal total_pcm, chunks_sent, first_audio_at
        while True:
            pcm = ffmpeg_proc.stdout.read(chunk_size)
            if not pcm:
                break
            if first_audio_at is None:
                first_audio_at = time.time()
            total_pcm += len(pcm)
            try:
                _udp_send.sendto(pcm, (send_ip, AUDIO_SPK_PORT))
            except Exception:
                pass
            chunks_sent += 1
            time.sleep(chunk_size / bytes_per_sec * 0.85)

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
          f"{total_mp3}B mp3 -> {total_pcm}B pcm | {chunks_sent} chunks",
          flush=True)
    return tts_latency


def _robot_pipeline():
    global _robot_recording
    import time

    try:
        pipeline_start = time.time()
        print(f"[ROBOT] Pipeline started. esp32_send_ip={_esp32_send_ip()} (recv_from={_esp32_audio_ip}) udp_send={'OK' if _udp_send else 'NONE'} bridge={_audio_bridge_ok}", flush=True)
        socketio.emit("robot_status", {"state": "listening"}, namespace="/audio")

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
        t_record = silence_detected_at - record_start

        end_beep = _generate_beep(600, 200)
        _send_pcm_to_esp32(end_beep)

        all_pcm = b"".join(_robot_buffer)
        _robot_buffer.clear()
        audio_duration = len(all_pcm) / 32000.0
        print(f"[ROBOT] Recording: {audio_duration:.1f}s audio | {len(all_pcm)}B", flush=True)

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

        system_text += "\n\nYou are responding to a voice command. Keep your answer short and conversational (1-3 sentences). Do not use markdown, bullet points, or special formatting."

        contents = []
        for msg in chat_history[-20:]:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["text"]}]})

        # ── DEBUG: set to True to skip real API call ──
        _ROBOT_DEBUG = False
        # _ROBOT_DEBUG_TEXT = "Привет, это тестовое сообщение. Всё работает отлично!"
        # _ROBOT_DEBUG_TEXT = "Сәлеметсіз бе, бұл сынақ хабарлама. Бәрі жақсы жұмыс істейді!"
        # _ROBOT_DEBUG_TEXT = "Hello, this is a test message. Everything works great!"
        if _ROBOT_DEBUG:
            ai_text = _ROBOT_DEBUG_TEXT
            t_llm = 0.0
        else:
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
            tts_latency = _tts_stream_to_esp32(ai_text, lang=detected_lang) or 0
            t_speak = time.time() - t_tts_start
        except Exception as e:
            t_speak = time.time() - t_tts_start
            print(f"[ROBOT] TTS error: {e}", flush=True)

        processing_time = t_stt + t_llm + tts_latency
        first_pkt_to_reply = (silence_detected_at - first_audio_pkt_at) + processing_time if first_audio_pkt_at else 0

        print(f"[ROBOT]", flush=True)
        print(f"[ROBOT] ======== PIPELINE SUMMARY ========", flush=True)
        print(f"[ROBOT]  STT          : {t_stt:.2f}s", flush=True)
        print(f"[ROBOT]  LLM          : {t_llm:.2f}s", flush=True)
        print(f"[ROBOT]  TTS gen      : {tts_latency:.2f}s  (time to first audio out)", flush=True)
        print(f"[ROBOT]  TTS playback : {t_speak - tts_latency:.2f}s  (streaming to ESP32)", flush=True)
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
    print("\n" + "="*70)
    print("🚀 ARIA Application Starting")
    print("="*70)
    print(f"\n✅ Открывайте браузер на: http://localhost:5000")
    print(f"\n⚠️  ВАЖНО ДЛЯ GMAIL OAUTH:")
    print(f"   • Используйте ТОЛЬКО: http://localhost:5000")
    print(f"   • НЕ используйте: http://127.0.0.1:5000")
    print(f"   • (Если откроется 127.0.0.1, будет редирект на localhost)")
    print(f"\n📧 Gmail OAuth endpoints:")
    print(f"   • Авторизация: http://localhost:5000/api/gmail/login")
    print(f"   • Статус: http://localhost:5000/api/gmail/status")
    print(f"   • Отправить письмо: POST http://localhost:5000/api/gmail/send")
    print(f"\n" + "="*70)
    
    app.run(host='0.0.0.0', port=5000, debug=True)