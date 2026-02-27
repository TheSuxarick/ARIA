from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import requests
import re
import os
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

PERSONALITY_PROMPTS = {
    "default": (
        "You are ARIA, a smart home AI assistant. "
        "You are helpful, friendly, and knowledgeable."
    ),
    "chill": (
        "You are ARIA, a super chill and laid-back smart home AI assistant. "
        "You speak in a relaxed, calm, easygoing tone. Use casual language, "
        "keep things mellow, and never stress about anything. "
        "Throw in phrases like 'no worries', 'all good', 'easy peasy'. "
        "You're like a cool friend who always keeps it zen."
    ),
    "bro": (
        "You are ARIA, a smart home AI assistant who talks like a total bro. "
        "You're enthusiastic, hype, and supportive. Use slang like 'bro', 'dude', "
        "'let's gooo', 'no cap', 'that's fire', 'W', 'bet'. "
        "You gas up the user and keep the energy high. You're their ride-or-die homie."
    ),
    "angry": (
        "You are ARIA, a smart home AI assistant who is perpetually annoyed and grumpy. "
        "You still help the user correctly, but you complain about it. "
        "You're sarcastic, impatient, and dramatic about being bothered. "
        "Think of a grumpy old man who knows everything but hates being asked. "
        "You sigh, you rant, but you ALWAYS give the correct answer in the end."
    ),
    "formal": (
        "You are ARIA, a smart home AI assistant who speaks in a highly formal, "
        "professional, and eloquent manner. You use sophisticated vocabulary, "
        "complete sentences, and polite expressions. Address the user respectfully. "
        "You are like a distinguished British butler — precise, courteous, and impeccable."
    ),
    "pirate": (
        "You are ARIA, a smart home AI assistant who speaks like a pirate. "
        "Use pirate slang: 'Ahoy', 'Aye aye', 'matey', 'shiver me timbers', "
        "'Arrr', 'ye', 'landlubber', 'treasure'. Talk about the seas, "
        "adventures, and treasure. But still give accurate, helpful answers. "
        "You're a salty sea dog who happens to be a tech genius."
    ),
    "sassy": (
        "You are ARIA, a smart home AI assistant with a sassy, witty personality. "
        "You're confident, a little dramatic, and love to throw shade (playfully). "
        "You serve looks AND knowledge. Think reality TV star who is secretly a genius. "
        "Use phrases like 'honey', 'sweetie', 'periodt', 'I said what I said', "
        "'not gonna lie'. You're fabulous and you know it."
    ),
    "nerd": (
        "You are ARIA, a smart home AI assistant who is a total nerd/geek. "
        "You LOVE technical details, make references to sci-fi, gaming, anime, "
        "and pop culture. You get excited about science and tech. "
        "Use phrases like 'Actually...', 'Fun fact!', 'According to my calculations'. "
        "You're basically an excited encyclopedia who loves sharing knowledge."
    ),
}

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
            "tz_id": f"UTC{'+' if tz >= 0 else ''}{tz // 3600}",
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


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
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

        weather_city = detect_weather_query(user_message)
        if weather_city:
            w = fetch_weather(weather_city)
            if w:
                system_text += (
                    f"\n\n[REAL-TIME WEATHER DATA for {w['city']}, {w['country']}]"
                    f"\nLocal time: {w.get('localtime', 'N/A')}"
                    f"\nTemperature: {w['temp']}°C (feels like {w['feels_like']}°C)"
                    f"\nDay high: {w['temp_max']}°C, Day low: {w['temp_min']}°C"
                    f"\nCondition: {w['description']}"
                    f"\nHumidity: {w['humidity']}%"
                    f"\nWind: {w['wind_kph']} km/h {w.get('wind_dir', '')}"
                    f"\nPressure: {w['pressure']} hPa"
                    f"\nCloudiness: {w['clouds']}%"
                    f"\nVisibility: {w['vis_km']} km"
                    f"\nSunrise: {w.get('sunrise', 'N/A')}, Sunset: {w.get('sunset', 'N/A')}"
                    f"\n\nUse this real data to answer the user's weather question accurately. "
                    f"Stay in your personality while presenting the data."
                )

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
    data = request.get_json()
    action = data.get("action", "")
    responses = {
        "light": {"status": "success", "message": "Lights toggled"},
        "robot": {"status": "success", "message": "Robot called"},
    }
    return jsonify(responses.get(action, {"status": "error", "message": "Unknown action"}))


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

@app.route('/callback', methods=['GET'])
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
            return jsonify({"error": f"Google error: {error_description}"}), 400
        
        if not code:
            print(f"[CALLBACK] ❌ Код авторизации не получен")
            return jsonify({"error": "No authorization code received"}), 400
        
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
            
            print(f"[CALLBACK] ✅ Данные сохранены в БД, перенаправляю...")
        
        # Redirect back to dashboard with success
        return redirect(f"http://localhost:5000/?gmail_auth=success&email={email}")
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
        gmail_email = session.get('gmail_email', '')
        
        print(f"\n[STATUS] Проверка статуса авторизации")
        print(f"[STATUS] is_authenticated: {is_auth}")
        print(f"[STATUS] Email в сессии: {gmail_email}")
        print(f"[STATUS] token.json существует: {Path('token.json').exists()}")
        
        return jsonify({
            "authenticated": is_auth,
            "email": gmail_email
        }), 200
    except Exception as e:
        print(f"[STATUS] ❌ Ошибка: {e}")
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
        if 'gmail_email' in session:
            del session['gmail_email']
        if 'gmail_authenticated' in session:
            del session['gmail_authenticated']
        
        return jsonify({
            "success": True,
            "message": "Logged out from Gmail"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ═══════════════════════ INBOX & EMAIL DISPLAY ENDPOINTS ═══════════════════════

@app.route('/api/emails/inbox', methods=['GET'])
def get_inbox():
    """Get inbox emails (cached from Gmail or local)"""
    try:
        gmail_email = session.get('gmail_email', '')
        max_results = request.args.get('max_results', 20, type=int)
        
        if not gmail_email:
            return jsonify({"emails": [], "source": "none"}), 200
        
        # Get Gmail account
        gmail_account = GmailAccount.query.filter_by(email=gmail_email).first()
        
        if not gmail_account:
            return jsonify({"emails": [], "source": "none"}), 200
        
        # Get cached emails from database
        emails = EmailMessage.query.filter_by(account_id=gmail_account.id)\
            .order_by(EmailMessage.received_at.desc())\
            .limit(max_results)\
            .all()
        
        emails_data = [{
            'id': e.gmail_id,
            'subject': e.subject,
            'from': e.sender,
            'body': e.body[:100] + '...' if len(e.body or '') > 100 else e.body,
            'date': e.received_at.isoformat(),
            'is_read': e.is_read
        } for e in emails]
        
        return jsonify({
            "emails": emails_data,
            "source": "cache",
            "total": len(emails_data)
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/emails/sync', methods=['POST'])
def sync_emails():
    """Fetch fresh emails from Gmail and cache them"""
    try:
        if not gmail_service.is_authenticated():
            return jsonify({"error": "Not authenticated with Gmail"}), 401
        
        gmail_email = session.get('gmail_email', '')
        if not gmail_email:
            return jsonify({"error": "No Gmail email in session"}), 400
        
        # Fetch from Gmail API
        result = gmail_service.get_emails(max_results=20)
        
        if 'error' in result:
            return jsonify(result), 400
        
        # Cache emails
        gmail_account = GmailAccount.query.filter_by(email=gmail_email).first()
        if gmail_account and 'emails' in result:
            for email_data in result['emails']:
                existing = EmailMessage.query.filter_by(
                    gmail_id=email_data.get('id', ''),
                    account_id=gmail_account.id
                ).first()
                
                if not existing:
                    msg = EmailMessage(
                        gmail_id=email_data.get('id', ''),
                        account_id=gmail_account.id,
                        sender=email_data.get('from', 'Unknown'),
                        subject=email_data.get('subject', 'No Subject'),
                        body=email_data.get('body', ''),
                        received_at=datetime.utcnow()
                    )
                    db.session.add(msg)
            
            db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Emails synced successfully",
            "count": len(result.get('emails', []))
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


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
