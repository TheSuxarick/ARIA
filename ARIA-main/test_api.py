"""Quick test for the ChatAnywhere API with the new key"""
import requests
import json

API_KEY = "sk-sTgiqoqr21XjLEGlcah65fT8LuamSvlalhy1ykfPwefgju4n"
API_BASE = "https://api.chatanywhere.tech/v1"

print("Testing ChatAnywhere API...")
print(f"API Base: {API_BASE}")
print(f"Key: {API_KEY[:8]}...{API_KEY[-4:]}")
print()

url = f"{API_BASE}/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}
payload = {
    "model": "gpt-4o",
    "messages": [
        {"role": "system", "content": "You are ARIA, a smart AI assistant. Reply briefly."},
        {"role": "user", "content": "Hello! Who are you? Reply in 1-2 sentences."}
    ],
    "max_tokens": 100,
    "temperature": 0.7
}

try:
    print("Sending request...")
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    print(f"Status: {resp.status_code}")
    
    data = resp.json()
    print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
    
    if resp.status_code == 200 and "choices" in data:
        reply = data["choices"][0]["message"]["content"]
        print(f"\nAI Reply: {reply}")
        print("\nSUCCESS! API is working!")
    else:
        print(f"\nERROR: {data}")
except Exception as e:
    print(f"\nConnection error: {e}")
