"""
ARIA AI Client
Handles OpenAI-compatible API calls (ChatAnywhere) with conversation history
"""
import time
import base64
import requests
from config import OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL, SYSTEM_PROMPT


class AIClient:
    """OpenAI-compatible API client for ChatAnywhere"""
    
    def __init__(self):
        self.api_key = OPENAI_API_KEY
        self.api_base = OPENAI_API_BASE
        self.model = OPENAI_MODEL
        
        # Conversation history
        self.history = []
        self.history_summary = ""
        
        if not self.api_key:
            raise ValueError("No API key configured! Set OPENAI_API_KEY in .env")
        
        print(f"[*] AI Client initialized with model: {self.model}")
        print(f"[*] API base: {self.api_base}")
    
    def _build_messages(self, user_message, memories=None):
        """Build conversation messages in OpenAI format"""
        messages = []
        
        # System prompt with memories
        system_text = SYSTEM_PROMPT
        
        if memories:
            system_text += "\n\n--- Воспоминания из прошлых разговоров ---\n"
            for i, memory in enumerate(memories, 1):
                system_text += f"{i}. {memory}\n"
            system_text += "--- Конец воспоминаний ---\n"
        
        if self.history_summary:
            system_text += f"\n--- Краткое содержание предыдущего разговора ---\n{self.history_summary}\n"
        
        messages.append({"role": "system", "content": system_text})
        
        # Add conversation history
        for msg in self.history:
            role = "user" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["text"]})
        
        # Add current message
        messages.append({"role": "user", "content": user_message})
        
        return messages
    
    def chat(self, message, memories=None, image_data=None, max_retries=3):
        """
        Send message to AI and get response
        
        Args:
            message: User message text
            memories: List of relevant memories from RAG
            image_data: Optional image bytes for vision (not supported in free tier)
            max_retries: Number of retries
            
        Returns:
            AI response text
        """
        if image_data:
            message = f"[Пользователь показал изображение с камеры] {message}"
        
        messages = self._build_messages(message, memories)
        
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 500,
            "temperature": 0.7
        }
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                resp_data = resp.json()
                
                if resp.status_code == 200 and "choices" in resp_data:
                    ai_response = resp_data["choices"][0]["message"]["content"]
                    
                    # Add to history
                    if image_data:
                        self.history.append({"role": "user", "text": f"[Изображение с камеры] {message}"})
                    else:
                        self.history.append({"role": "user", "text": message})
                    self.history.append({"role": "model", "text": ai_response})
                    
                    # Check if we need to summarize
                    self._maybe_summarize()
                    
                    return ai_response
                else:
                    err = resp_data.get("error", {})
                    if isinstance(err, dict):
                        error_msg = err.get("message", str(resp_data))
                    else:
                        error_msg = str(resp_data)
                    raise Exception(f"API error ({resp.status_code}): {error_msg}")
                    
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                if "429" in error_str or "rate" in error_str or "quota" in error_str:
                    print(f"[!] Rate limit hit")
                    wait_time = 2 ** attempt
                    print(f"[*] Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    print(f"[ERROR] API error: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(1)
        
        raise Exception(f"Failed after {max_retries} attempts: {last_error}")
    
    def _maybe_summarize(self):
        """Summarize conversation if history is too long"""
        from config import MAX_HISTORY_TURNS, SUMMARIZE_AFTER
        
        if len(self.history) >= SUMMARIZE_AFTER * 2:
            print("[*] Summarizing conversation history...")
            
            keep_count = MAX_HISTORY_TURNS * 2
            old_history = self.history[:-keep_count]
            self.history = self.history[-keep_count:]
            
            summary_prompt = "Кратко резюмируй этот разговор (2-3 предложения):\n\n"
            for msg in old_history:
                role = "Пользователь" if msg["role"] == "user" else "ARIA"
                summary_prompt += f"{role}: {msg['text']}\n"
            
            try:
                url = f"{self.api_base}/chat/completions"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": summary_prompt}],
                    "max_tokens": 200,
                    "temperature": 0.5
                }
                
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                resp_data = resp.json()
                
                if resp.status_code == 200 and "choices" in resp_data:
                    summary = resp_data["choices"][0]["message"]["content"]
                    if self.history_summary:
                        self.history_summary = f"{self.history_summary}\n{summary}"
                    else:
                        self.history_summary = summary
                        
            except Exception as e:
                print(f"[!] Could not summarize: {e}")
    
    def clear_history(self):
        """Clear conversation history"""
        self.history = []
        self.history_summary = ""
        print("[*] Conversation history cleared")


# Singleton
_client = None

def get_gemini():
    """Get AI client instance (kept name for backward compatibility)"""
    global _client
    if _client is None:
        _client = AIClient()
    return _client


if __name__ == "__main__":
    # Test AI client
    client = AIClient()
    
    response = client.chat("Привет! Как тебя зовут?")
    print(f"ARIA: {response}")
    
    response = client.chat("А что ты умеешь делать?")
    print(f"ARIA: {response}")
