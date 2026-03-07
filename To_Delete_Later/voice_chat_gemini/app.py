"""
Gemini Voice Chat - Backend
Uses Gemini API for AI responses, browser TTS for speech
Supports vision from ESP32-CAM
"""
import os
import base64
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

app = Flask(__name__, static_folder='static')
CORS(app)

GEMINI_API_KEY = os.getenv('google_api')

# Initialize Gemini client
client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_ID = "gemini-2.5-flash-lite"

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
        # Request the stream with a short timeout
        response = requests.get(stream_url, stream=True, timeout=5)
        
        if response.status_code != 200:
            return None, f"Failed to connect to camera: {response.status_code}"
        
        # Read until we find a complete JPEG frame
        buffer = b''
        jpeg_start = None
        
        for chunk in response.iter_content(chunk_size=1024):
            buffer += chunk
            
            # Find JPEG start marker (FFD8)
            if jpeg_start is None:
                start_idx = buffer.find(b'\xff\xd8')
                if start_idx != -1:
                    jpeg_start = start_idx
            
            # Find JPEG end marker (FFD9) after start
            if jpeg_start is not None:
                end_idx = buffer.find(b'\xff\xd9', jpeg_start)
                if end_idx != -1:
                    # Extract complete JPEG
                    jpeg_data = buffer[jpeg_start:end_idx + 2]
                    response.close()
                    return jpeg_data, None
            
            # Limit buffer size to prevent memory issues
            if len(buffer) > 500000:  # 500KB limit
                response.close()
                return None, "Frame too large or not found"
        
        response.close()
        return None, "Could not capture frame"
        
    except requests.exceptions.Timeout:
        return None, "Camera connection timeout"
    except requests.exceptions.ConnectionError:
        return None, f"Cannot connect to camera at {ESP32_CAM_IP}"
    except Exception as e:
        return None, str(e)


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/chat', methods=['POST'])
def chat():
    global conversation_history
    
    if not client:
        return jsonify({'error': 'API key not configured. Add google_api to .env file'}), 500
    
    data = request.json
    user_message = data.get('message', '')
    
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400
    
    # Build contents with system prompt and conversation history
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=SYSTEM_PROMPT)]
        ),
        types.Content(
            role="model",
            parts=[types.Part.from_text(text="Understood! I'll be helpful and conversational, keeping responses concise for speech.")]
        )
    ]
    
    # Add conversation history
    for msg in conversation_history:
        contents.append(types.Content(
            role=msg["role"],
            parts=[types.Part.from_text(text=msg["text"])]
        ))
    
    # Add current user message
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_message)]
    ))
    
    # Safety settings
    safety_settings = [
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
    ]
    
    config = types.GenerateContentConfig(
        safety_settings=safety_settings,
        max_output_tokens=500,
        temperature=0.7
    )
    
    try:
        # Generate response (non-streaming for simplicity)
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=contents,
            config=config
        )
        
        ai_response = response.text
        
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
        print(f"Gemini API Error: {error_msg}")
        return jsonify({'error': f'API error: {error_msg}'}), 500


@app.route('/vision', methods=['POST'])
def vision():
    """Capture image from ESP32-CAM and ask Gemini what it sees"""
    global conversation_history
    
    if not client:
        return jsonify({'error': 'API key not configured'}), 500
    
    data = request.json
    question = data.get('question', 'What do you see in this image? Describe it briefly and conversationally.')
    
    # Capture frame from ESP32-CAM
    print(f"Capturing frame from ESP32-CAM at {ESP32_CAM_IP}...")
    jpeg_data, error = capture_frame_from_esp32()
    
    if error:
        return jsonify({'error': f'Camera error: {error}'}), 500
    
    if not jpeg_data:
        return jsonify({'error': 'Failed to capture image'}), 500
    
    print(f"Captured frame: {len(jpeg_data)} bytes")
    
    # Create image part for Gemini
    image_part = types.Part.from_bytes(
        data=jpeg_data,
        mime_type="image/jpeg"
    )
    
    # Build content with image and question
    contents = [
        types.Content(
            role="user",
            parts=[
                image_part,
                types.Part.from_text(text=f"{question}\n\nRespond conversationally and concisely since your response will be read aloud.")
            ]
        )
    ]
    
    # Safety settings
    safety_settings = [
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
    ]
    
    config = types.GenerateContentConfig(
        safety_settings=safety_settings,
        max_output_tokens=500,
        temperature=0.7
    )
    
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=contents,
            config=config
        )
        
        ai_response = response.text
        
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
        print(f"Gemini Vision Error: {error_msg}")
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
    print("🎤 Gemini Voice Chat Server Starting...")
    print(f"📍 Open http://localhost:5000 in your browser")
    print(f"🔑 API Key loaded: {'Yes' if GEMINI_API_KEY else 'No - add google_api to .env!'}")
    print(f"📷 ESP32-CAM IP: {ESP32_CAM_IP}")
    app.run(debug=True, port=5000)
