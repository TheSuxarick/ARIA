from flask import Flask, render_template, request, jsonify
import requests
from datetime import datetime

app = Flask(__name__)

# In-memory storage
context_memory = []
settings = {
    "model": "gpt-4o",
    "api_key": "sk-sTgiqoqr21XjLEGlcah65fT8LuamSvlalhy1ykfPwefgju4n",
    "language": "EN"
}
chat_history = []

OPENAI_API_BASE = "https://api.chatanywhere.tech/v1"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    chat_history.append({"role": "user", "text": user_message})

    if settings.get("api_key"):
        try:
            model = settings.get("model", "gpt-4o")
            api_key = settings["api_key"]
            url = f"{OPENAI_API_BASE}/chat/completions"

            # System instruction with context memory
            system_text = "You are ARIA, a smart home AI assistant. You are helpful, friendly, and knowledgeable."
            if context_memory:
                memory_text = "\n".join(f"- {m['text']}" for m in context_memory)
                system_text += f"\n\nContext memory:\n{memory_text}"

            # Build conversation messages in OpenAI format
            messages = [{"role": "system", "content": system_text}]
            for msg in chat_history[-20:]:
                role = "user" if msg["role"] == "user" else "assistant"
                messages.append({"role": role, "content": msg["text"]})

            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": 1024,
                "temperature": 0.7
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            resp_data = resp.json()

            if resp.status_code == 200 and "choices" in resp_data:
                ai_text = resp_data["choices"][0]["message"]["content"]
            else:
                err = resp_data.get("error", {})
                if isinstance(err, dict):
                    error_msg = err.get("message", str(resp_data))
                else:
                    error_msg = str(resp_data)
                ai_text = f"API error ({resp.status_code}): {error_msg}"
        except Exception as e:
            ai_text = f"Connection error: {str(e)}"
    else:
        ai_text = f'Demo mode. Received: "{user_message}". Add API key in Settings.'

    chat_history.append({"role": "assistant", "text": ai_text})
    return jsonify({"reply": ai_text})


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
    return jsonify({**settings, "api_key": "••••" if settings["api_key"] else ""})


@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.get_json()
    for key in ("model", "api_key", "language"):
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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
