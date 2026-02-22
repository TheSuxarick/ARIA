from flask import Flask, render_template, request, jsonify
import requests
import re
import os
from datetime import datetime
from pathlib import Path


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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
