"""
ARIA Tools
All integrations: ESP32-CAM, Yeelight, YouTube, Weather, Email
"""
import os
import re
import subprocess
import requests
import tempfile
from config import ESP32_CAM_IP, YEELIGHT_IP, OPENWEATHER_API_KEY, DEFAULT_CITY


# =============================================================================
# ESP32-CAM Control
# =============================================================================
class ESP32Camera:
    """Control ESP32-CAM pan/tilt and capture images"""
    
    def __init__(self, ip=None):
        self.ip = ip or ESP32_CAM_IP
    
    def move(self, direction):
        """Move camera: up, down, left, right"""
        try:
            requests.get(f"http://{self.ip}/action?go={direction}", timeout=2)
            return True
        except Exception as e:
            print(f"Camera move error: {e}")
            return False
    
    def up(self): 
        return self.move("up")
    
    def down(self): 
        return self.move("down")
    
    def left(self): 
        return self.move("left")
    
    def right(self): 
        return self.move("right")
    
    def capture(self):
        """Capture a frame from the camera stream"""
        try:
            resp = requests.get(f"http://{self.ip}:81/stream", stream=True, timeout=5)
            buf = b''
            
            for chunk in resp.iter_content(1024):
                buf += chunk
                s = buf.find(b'\xff\xd8')  # JPEG start
                e = buf.find(b'\xff\xd9')  # JPEG end
                
                if s != -1 and e > s:
                    resp.close()
                    return buf[s:e+2]
                    
                if len(buf) > 500000:  # 500KB limit
                    break
                    
            resp.close()
            return None
            
        except Exception as e:
            print(f"Camera capture error: {e}")
            return None


# =============================================================================
# Yeelight Smart Bulb
# =============================================================================
class SmartBulb:
    """Control Yeelight smart bulb"""
    
    def __init__(self, ip=None):
        self.ip = ip or YEELIGHT_IP
        self._bulb = None
    
    def _get_bulb(self):
        if self._bulb is None:
            from yeelight import Bulb
            self._bulb = Bulb(self.ip)
        return self._bulb
    
    def toggle(self):
        """Toggle bulb on/off"""
        try:
            self._get_bulb().toggle()
            return "Свет переключен"
        except Exception as e:
            return f"Ошибка лампы: {e}"
    
    def turn_on(self):
        """Turn bulb on"""
        try:
            self._get_bulb().turn_on()
            return "Свет включен"
        except Exception as e:
            return f"Ошибка: {e}"
    
    def turn_off(self):
        """Turn bulb off"""
        try:
            self._get_bulb().turn_off()
            return "Свет выключен"
        except Exception as e:
            return f"Ошибка: {e}"
    
    def set_brightness(self, level):
        """Set brightness (1-100)"""
        try:
            level = max(1, min(100, int(level)))
            self._get_bulb().set_brightness(level)
            return f"Яркость установлена на {level}%"
        except Exception as e:
            return f"Ошибка: {e}"
    
    def set_color(self, r, g, b):
        """Set RGB color"""
        try:
            self._get_bulb().set_rgb(int(r), int(g), int(b))
            return "Цвет изменен"
        except Exception as e:
            return f"Ошибка: {e}"
    
    def set_color_temp(self, temp):
        """Set color temperature (1700-6500K)"""
        try:
            temp = max(1700, min(6500, int(temp)))
            self._get_bulb().set_color_temp(temp)
            return f"Температура цвета: {temp}K"
        except Exception as e:
            return f"Ошибка: {e}"


# =============================================================================
# YouTube Music
# =============================================================================
class YouTubePlayer:
    """Play music from YouTube using yt-dlp"""
    
    def __init__(self):
        self.current_process = None
    
    def search_and_play(self, query):
        """Search YouTube and play first result"""
        try:
            # First, get the video URL using yt-dlp
            search_url = f"ytsearch1:{query}"
            
            # Get audio URL
            result = subprocess.run(
                ["yt-dlp", "-f", "bestaudio", "-g", search_url],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return f"Не удалось найти: {query}"
            
            audio_url = result.stdout.strip()
            
            # Get title
            title_result = subprocess.run(
                ["yt-dlp", "--get-title", search_url],
                capture_output=True,
                text=True,
                timeout=15
            )
            title = title_result.stdout.strip() if title_result.returncode == 0 else query
            
            # Stop any currently playing audio
            self.stop()
            
            # Play using ffplay (comes with ffmpeg)
            self.current_process = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", audio_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            return f"Играет: {title}"
            
        except subprocess.TimeoutExpired:
            return "Превышено время поиска"
        except FileNotFoundError:
            return "Нужно установить yt-dlp и ffmpeg"
        except Exception as e:
            return f"Ошибка: {e}"
    
    def stop(self):
        """Stop currently playing music"""
        if self.current_process:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=2)
            except:
                self.current_process.kill()
            self.current_process = None
            return "Музыка остановлена"
        return "Ничего не играет"
    
    def is_playing(self):
        """Check if music is currently playing"""
        if self.current_process:
            return self.current_process.poll() is None
        return False


# =============================================================================
# Weather
# =============================================================================
class Weather:
    """Get weather information using OpenWeatherMap"""
    
    def __init__(self):
        self.api_key = OPENWEATHER_API_KEY
        self.default_city = DEFAULT_CITY
    
    def get_weather(self, city=None):
        """Get current weather for a city"""
        city = city or self.default_city
        
        if not self.api_key:
            # Fallback to wttr.in (no API key needed)
            return self._get_weather_wttr(city)
        
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather"
            params = {
                "q": city,
                "appid": self.api_key,
                "units": "metric",
                "lang": "ru"
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if response.status_code == 200:
                temp = round(data["main"]["temp"])
                feels = round(data["main"]["feels_like"])
                desc = data["weather"][0]["description"]
                humidity = data["main"]["humidity"]
                
                return (f"В городе {city}: {temp}°C, {desc}. "
                        f"Ощущается как {feels}°C. Влажность {humidity}%.")
            else:
                return f"Не удалось получить погоду для {city}"
                
        except Exception as e:
            return f"Ошибка погоды: {e}"
    
    def _get_weather_wttr(self, city):
        """Fallback weather using wttr.in"""
        try:
            response = requests.get(
                f"https://wttr.in/{city}?format=%t+%C&lang=ru",
                timeout=10
            )
            if response.status_code == 200:
                return f"Погода в {city}: {response.text.strip()}"
            return "Не удалось получить погоду"
        except:
            return "Сервис погоды недоступен"


# =============================================================================
# Email (Gmail)
# =============================================================================
class EmailClient:
    """Read and summarize Gmail emails"""
    
    def __init__(self):
        self.service = None
        self.credentials_file = os.getenv('GMAIL_CREDENTIALS_FILE', 'credentials.json')
    
    def _get_service(self):
        """Initialize Gmail API service"""
        if self.service:
            return self.service
            
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            import pickle
            
            SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
            
            creds = None
            token_file = 'gmail_token.pickle'
            
            if os.path.exists(token_file):
                with open(token_file, 'rb') as token:
                    creds = pickle.load(token)
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(self.credentials_file):
                        return None
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_file, SCOPES)
                    creds = flow.run_local_server(port=0)
                
                with open(token_file, 'wb') as token:
                    pickle.dump(creds, token)
            
            self.service = build('gmail', 'v1', credentials=creds)
            return self.service
            
        except Exception as e:
            print(f"Gmail auth error: {e}")
            return None
    
    def get_unread_summary(self, max_emails=5):
        """Get summary of unread emails"""
        service = self._get_service()
        
        if not service:
            return "Gmail не настроен. Нужен файл credentials.json из Google Cloud Console."
        
        try:
            # Get unread emails
            results = service.users().messages().list(
                userId='me',
                q='is:unread',
                maxResults=max_emails
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                return "Нет непрочитанных писем."
            
            summaries = []
            for msg in messages:
                email = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='metadata',
                    metadataHeaders=['From', 'Subject']
                ).execute()
                
                headers = {h['name']: h['value'] for h in email['payload']['headers']}
                sender = headers.get('From', 'Unknown')
                subject = headers.get('Subject', 'No subject')
                
                # Clean sender name
                if '<' in sender:
                    sender = sender.split('<')[0].strip().strip('"')
                
                summaries.append(f"От {sender}: {subject}")
            
            result = f"У вас {len(messages)} непрочитанных писем:\n"
            result += "\n".join(summaries)
            
            return result
            
        except Exception as e:
            return f"Ошибка чтения почты: {e}"


# =============================================================================
# Tool Manager - Central access to all tools
# =============================================================================
class ToolManager:
    """Manages all ARIA tools"""
    
    def __init__(self):
        self.camera = ESP32Camera()
        self.bulb = SmartBulb()
        self.youtube = YouTubePlayer()
        self.weather = Weather()
        self.email = EmailClient()
    
    def execute_command(self, command, args=None):
        """
        Execute a tool command
        
        Commands:
            - light_on, light_off, light_toggle
            - light_brightness <level>
            - light_color <r> <g> <b>
            - camera_up, camera_down, camera_left, camera_right
            - camera_capture
            - play_music <query>
            - stop_music
            - weather [city]
            - check_email
        """
        args = args or []
        command = command.lower().strip()
        
        # Light commands
        if command in ['light_on', 'включи свет', 'свет включи']:
            return self.bulb.turn_on()
        elif command in ['light_off', 'выключи свет', 'свет выключи']:
            return self.bulb.turn_off()
        elif command in ['light_toggle', 'переключи свет']:
            return self.bulb.toggle()
        elif command.startswith('light_brightness') or 'яркость' in command:
            level = self._extract_number(command, args, 50)
            return self.bulb.set_brightness(level)
        elif command.startswith('light_color'):
            if len(args) >= 3:
                return self.bulb.set_color(args[0], args[1], args[2])
            return "Укажите цвет (r g b)"
        
        # Camera commands
        elif command in ['camera_up', 'камера вверх']:
            self.camera.up()
            return "Камера повернута вверх"
        elif command in ['camera_down', 'камера вниз']:
            self.camera.down()
            return "Камера повернута вниз"
        elif command in ['camera_left', 'камера влево']:
            self.camera.left()
            return "Камера повернута влево"
        elif command in ['camera_right', 'камера вправо']:
            self.camera.right()
            return "Камера повернута вправо"
        elif command in ['camera_capture', 'что видишь', 'посмотри']:
            return self.camera.capture()  # Returns image bytes
        
        # Music commands
        elif command.startswith('play_music') or command.startswith('включи музыку'):
            query = ' '.join(args) if args else command.replace('play_music', '').replace('включи музыку', '').strip()
            if query:
                return self.youtube.search_and_play(query)
            return "Что включить?"
        elif command in ['stop_music', 'стоп', 'выключи музыку']:
            return self.youtube.stop()
        
        # Weather
        elif command.startswith('weather') or 'погода' in command:
            city = args[0] if args else None
            return self.weather.get_weather(city)
        
        # Email
        elif command in ['check_email', 'проверь почту', 'почта']:
            return self.email.get_unread_summary()
        
        return None
    
    def _extract_number(self, text, args, default):
        """Extract a number from text or args"""
        if args:
            try:
                return int(args[0])
            except:
                pass
        
        numbers = re.findall(r'\d+', text)
        if numbers:
            return int(numbers[0])
        return default


# Singleton
_tools = None

def get_tools():
    global _tools
    if _tools is None:
        _tools = ToolManager()
    return _tools


if __name__ == "__main__":
    # Test tools
    tools = ToolManager()
    
    print("Testing weather...")
    print(tools.weather.get_weather())
    
    print("\nTesting light toggle...")
    print(tools.bulb.toggle())
