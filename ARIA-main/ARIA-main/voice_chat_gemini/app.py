"""
Voice Chat - Backend
Uses OpenAI-compatible API (ChatAnywhere) for AI responses, browser TTS for speech
Supports vision from ESP32-CAM
"""
import os
import base64
import requests as http_requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='static')
CORS(app)

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'sk-sTgiqoqr21XjLEGlcah65fT8LuamSvlalhy1ykfPwefgju4n')
OPENAI_API_BASE = os.getenv('OPENAI_API_BASE', 'https://api.chatanywhere.tech/v1')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o')

# ESP32-CAM configuration - UPDATE THIS IP!
ESP32_CAM_IP = os.getenv('ESP32_CAM_IP', '10.58.187.186')

# Conversation history for context
conversation_history = []

# System prompt for the AI assistant
SYSTEM_PROMPT = """You are a helpful, friendly AI assistant. 
Keep your responses concise and conversational since they will be read aloud.
Avoid using markdown formatting, bullet points, or special characters.
Speak naturally as if having a conversation."""


def capture_frame_from_esp32():
    """Capture a single frame from ESP32-CAM MJPEG stream"""
    stream_url = f"http://{ESP32_CAM_IP}:81/stream"
    
    try:
        response = http_requests.get(stream_url, stream=True, timeout=5)
        
        if response.status_code != 200:
            return None, f"Failed to connect to camera: {response.status_code}"
        
        buffer = b''
        jpeg_start = None
        
        for chunk in response.iter_content(chunk_size=1024):
            buffer += chunk
            
            if jpeg_start is None:
                start_idx = buffer.find(b'\xff\xd8')
                if start_idx != -1:
                    jpeg_start = start_idx
            
            if jpeg_start is not None:
                end_idx = buffer.find(b'\xff\xd9', jpeg_start)
                if end_idx != -1:
                    jpeg_data = buffer[jpeg_start:end_idx + 2]
                    response.close()
                    return jpeg_data, None
            
            if len(buffer) > 500000:
                response.close()
                return None, "Frame too large or not found"
        
        response.close()
        return None, "Could not capture frame"
        
    except http_requests.exceptions.Timeout:
        return None, "Camera connection timeout"
    except http_requests.exceptions.ConnectionError:
        return None, f"Cannot connect to camera at {ESP32_CAM_IP}"
    except Exception as e:
        return None, str(e)


def call_openai_api(messages, max_tokens=500):
    """Make a call to the OpenAI-compatible API"""
    url = f"{OPENAI_API_BASE}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7
    }
    
    resp = http_requests.post(url, json=payload, headers=headers, timeout=60)
    resp_data = resp.json()
    
    if resp.status_code == 200 and "choices" in resp_data:
        return resp_data["choices"][0]["message"]["content"], None
    else:
        err = resp_data.get("error", {})
        if isinstance(err, dict):
            error_msg = err.get("message", str(resp_data))
        else:
            error_msg = str(resp_data)
        return None, f"API error ({resp.status_code}): {error_msg}"


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/chat', methods=['POST'])
def chat():
    global conversation_history
    
    if not OPENAI_API_KEY:
        return jsonify({'error': 'API key not configured. Set OPENAI_API_KEY in .env file'}), 500
    
    data = request.json
    user_message = data.get('message', '')
    
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400
    
    # Build messages with system prompt and conversation history
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    for msg in conversation_history:
        role = "user" if msg["role"] == "user" else "assistant"
        messages.append({"role": role, "content": msg["text"]})
    
    messages.append({"role": "user", "content": user_message})
    
    try:
        ai_response, error = call_openai_api(messages)
        
        if error:
            print(f"API Error: {error}")
            return jsonify({'error': error}), 500
        
        # Add to conversation history
        conversation_history.append({"role": "user", "text": user_message})
        conversation_history.append({"role": "model", "text": ai_response})
        
        # Keep only last 20 messages
        if len(conversation_history) > 20:
            conversation_history = conversation_history[-20:]
        
        return jsonify({
            'response': ai_response,
            'success': True
        })
        
    except Exception as e:
        error_msg = str(e)
        print(f"API Error: {error_msg}")
        return jsonify({'error': f'API error: {error_msg}'}), 500


@app.route('/vision', methods=['POST'])
def vision():
    """Capture image from ESP32-CAM and ask AI what it sees"""
    global conversation_history
    
    if not OPENAI_API_KEY:
        return jsonify({'error': 'API key not configured'}), 500
    
    data = request.json
    question = data.get('question', 'What do you see in this image? Describe it briefly and conversationally.')
    
    print(f"Capturing frame from ESP32-CAM at {ESP32_CAM_IP}...")
    jpeg_data, error = capture_frame_from_esp32()
    
    if error:
        return jsonify({'error': f'Camera error: {error}'}), 500
    
    if not jpeg_data:
        return jsonify({'error': 'Failed to capture image'}), 500
    
    print(f"Captured frame: {len(jpeg_data)} bytes")
    
    # For vision, describe that we captured an image in the text prompt
    vision_prompt = f"[The user is showing you a camera image from their smart home camera.] {question}\n\nRespond conversationally and concisely since your response will be read aloud."
    
    messages = [{"role": "user", "content": vision_prompt}]
    
    try:
        ai_response, api_error = call_openai_api(messages)
        
        if api_error:
            return jsonify({'error': api_error}), 500
        
        # Add to conversation history
        conversation_history.append({"role": "user", "text": f"[Showed camera image] {question}"})
        conversation_history.append({"role": "model", "text": ai_response})
        
        # Return with base64 image for display
        image_base64 = base64.b64encode(jpeg_data).decode('utf-8')
        
        return jsonify({
            'response': ai_response,
            'image': f"data:image/jpeg;base64,{image_base64}",
            'success': True
        })
        
    except Exception as e:
        error_msg = str(e)
        print(f"Vision Error: {error_msg}")
        return jsonify({'error': f'Vision API error: {error_msg}'}), 500


@app.route('/set_camera', methods=['POST'])
def set_camera():
    """Update ESP32-CAM IP address"""
    global ESP32_CAM_IP
    data = request.json
    new_ip = data.get('ip', '')
    if new_ip:
        ESP32_CAM_IP = new_ip
        return jsonify({'success': True, 'ip': ESP32_CAM_IP})
    return jsonify({'error': 'No IP provided'}), 400


@app.route('/clear', methods=['POST'])
def clear_history():
    global conversation_history
    conversation_history = []
    return jsonify({'success': True, 'message': 'Conversation cleared'})


if __name__ == '__main__':
    print("Voice Chat Server Starting...")
    print(f"Open http://localhost:5000 in your browser")
    print(f"API Key loaded: {'Yes' if OPENAI_API_KEY else 'No - add OPENAI_API_KEY to .env!'}")
    print(f"Model: {OPENAI_MODEL}")
    print(f"ESP32-CAM IP: {ESP32_CAM_IP}")
    app.run(debug=True, port=5000)
