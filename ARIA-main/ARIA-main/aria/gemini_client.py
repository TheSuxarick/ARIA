"""
ARIA Gemini Client
Handles Gemini API calls with automatic key rotation on rate limits
"""
import time
from google import genai
from google.genai import types
from config import GEMINI_API_KEYS, GEMINI_MODEL, SYSTEM_PROMPT


class GeminiClient:
    """Gemini API client with key rotation"""
    
    def __init__(self):
        self.api_keys = GEMINI_API_KEYS.copy()
        self.current_key_index = 0
        self.client = None
        self.model = GEMINI_MODEL
        
        # Conversation history
        self.history = []
        self.history_summary = ""
        
        # Track key failures
        self.key_failures = {}
        
        # Safety settings (allow all)
        self.safety_settings = [
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
        ]
        
        self._init_client()
    
    def _init_client(self):
        """Initialize client with current API key"""
        if not self.api_keys:
            raise ValueError("No Gemini API keys configured!")
        
        key = self.api_keys[self.current_key_index]
        self.client = genai.Client(api_key=key)
        print(f"[*] Using Gemini API key #{self.current_key_index + 1}")
    
    def _rotate_key(self):
        """Rotate to next API key"""
        if len(self.api_keys) <= 1:
            print("[!] Only one API key available, cannot rotate")
            return False
        
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self._init_client()
        print(f"[*] Rotated to API key #{self.current_key_index + 1}")
        return True
    
    def _build_contents(self, user_message, memories=None, image_data=None):
        """Build conversation contents for API"""
        contents = []
        
        # System prompt with memories
        system_text = SYSTEM_PROMPT
        
        if memories:
            system_text += "\n\n--- Воспоминания из прошлых разговоров ---\n"
            for i, memory in enumerate(memories, 1):
                system_text += f"{i}. {memory}\n"
            system_text += "--- Конец воспоминаний ---\n"
        
        if self.history_summary:
            system_text += f"\n--- Краткое содержание предыдущего разговора ---\n{self.history_summary}\n"
        
        # Add system prompt as first user message
        contents.append(types.Content(
            role="user",
            parts=[types.Part.from_text(text=system_text)]
        ))
        contents.append(types.Content(
            role="model",
            parts=[types.Part.from_text(text="Понятно! Я ARIA - твой умный домашний помощник. Готова помочь!")]
        ))
        
        # Add conversation history
        for msg in self.history:
            contents.append(types.Content(
                role=msg["role"],
                parts=[types.Part.from_text(text=msg["text"])]
            ))
        
        # Add current message (with image if provided)
        parts = []
        if image_data:
            parts.append(types.Part.from_bytes(data=image_data, mime_type="image/jpeg"))
        parts.append(types.Part.from_text(text=user_message))
        
        contents.append(types.Content(role="user", parts=parts))
        
        return contents
    
    def chat(self, message, memories=None, image_data=None, max_retries=3):
        """
        Send message to Gemini and get response
        
        Args:
            message: User message text
            memories: List of relevant memories from RAG
            image_data: Optional image bytes for vision
            max_retries: Number of retries with key rotation
            
        Returns:
            AI response text
        """
        contents = self._build_contents(message, memories, image_data)
        
        config = types.GenerateContentConfig(
            safety_settings=self.safety_settings,
            max_output_tokens=500,
            temperature=0.7
        )
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config
                )
                
                ai_response = response.text
                
                # Add to history
                if image_data:
                    self.history.append({"role": "user", "text": f"[Изображение с камеры] {message}"})
                else:
                    self.history.append({"role": "user", "text": message})
                self.history.append({"role": "model", "text": ai_response})
                
                # Check if we need to summarize
                self._maybe_summarize()
                
                return ai_response
                
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                # Check if it's a rate limit error
                if "429" in error_str or "rate" in error_str or "quota" in error_str:
                    print(f"[!] Rate limit hit on key #{self.current_key_index + 1}")
                    self.key_failures[self.current_key_index] = time.time()
                    
                    if not self._rotate_key():
                        # Exponential backoff if can't rotate
                        wait_time = 2 ** attempt
                        print(f"[*] Waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                else:
                    print(f"[ERROR] Gemini error: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(1)
        
        raise Exception(f"Failed after {max_retries} attempts: {last_error}")
    
    def _maybe_summarize(self):
        """Summarize conversation if history is too long"""
        from config import MAX_HISTORY_TURNS, SUMMARIZE_AFTER
        
        if len(self.history) >= SUMMARIZE_AFTER * 2:  # *2 because user+model pairs
            print("[*] Summarizing conversation history...")
            
            # Keep last N turns
            keep_count = MAX_HISTORY_TURNS * 2
            old_history = self.history[:-keep_count]
            self.history = self.history[-keep_count:]
            
            # Summarize old history
            summary_prompt = "Кратко резюмируй этот разговор (2-3 предложения):\n\n"
            for msg in old_history:
                role = "Пользователь" if msg["role"] == "user" else "ARIA"
                summary_prompt += f"{role}: {msg['text']}\n"
            
            try:
                contents = [types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=summary_prompt)]
                )]
                
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(max_output_tokens=200)
                )
                
                if self.history_summary:
                    self.history_summary = f"{self.history_summary}\n{response.text}"
                else:
                    self.history_summary = response.text
                    
            except Exception as e:
                print(f"[!] Could not summarize: {e}")
    
    def clear_history(self):
        """Clear conversation history"""
        self.history = []
        self.history_summary = ""
        print("[*] Conversation history cleared")


# Singleton
_gemini = None

def get_gemini():
    global _gemini
    if _gemini is None:
        _gemini = GeminiClient()
    return _gemini


if __name__ == "__main__":
    # Test Gemini client
    client = GeminiClient()
    
    response = client.chat("Привет! Как тебя зовут?")
    print(f"ARIA: {response}")
    
    response = client.chat("А что ты умеешь делать?")
    print(f"ARIA: {response}")
