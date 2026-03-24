"""
Test RAG API key rotation
"""
import sys
sys.path.insert(0, '.')

from config import GEMINI_API_KEYS
from rag import RAGMemory

print("="*50)
print("RAG KEY ROTATION TEST")
print("="*50)

# Check how many keys we have
print(f"\n[1] API Keys configured: {len(GEMINI_API_KEYS)}")
for i, key in enumerate(GEMINI_API_KEYS):
    masked = key[:8] + "..." + key[-4:] if len(key) > 12 else key
    print(f"    Key #{i+1}: {masked}")

# Test RAG search with rotation
print(f"\n[2] Testing RAG search (should rotate if key #1 is exhausted)...")

rag = RAGMemory()
rag.connect()

try:
    memories = rag.search("test query")
    if memories:
        print(f"\n[OK] RAG returned {len(memories)} memories!")
        for i, m in enumerate(memories[:2], 1):
            print(f"    {i}. {m[:80]}...")
    else:
        print("\n[OK] RAG search completed (no memories found)")
except Exception as e:
    print(f"\n[FAIL] RAG search failed: {e}")

print("\n" + "="*50)
