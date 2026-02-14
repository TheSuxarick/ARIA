from flask import Flask, render_template, request, jsonify
import requests
from datetime import datetime

app = Flask(__name__)

# In-memory storage
context_memory = []
settings = {"model": "gpt-4", "api_key": "", "language": "EN"}
chat_history = []


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

    # Use OpenAI API if key is set
    if settings.get("api_key"):
        try:
            headers = {"Authorization": f"Bearer {settings['api_key']}", "Content-Type": "application/json"}
            payload = {
                "model": settings.get("model", "gpt-4"),
                "messages": [
                    {"role": "system", "content": "You are ARIA, a smart home AI assistant."},
                    {"role": "user", "content": user_message}
                ],
                "max_tokens": 300
            }
            resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=15)
            ai_text = resp.json()["choices"][0]["message"]["content"] if resp.status_code == 200 else f"API error ({resp.status_code})."
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
