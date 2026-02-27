"""
Test RAG with OpenAI-compatible API
"""
import sys
sys.path.insert(0, '.')

from config import OPENAI_API_KEY, OPENAI_API_BASE
from rag import RAGMemory

print("="*50)
print("RAG TEST")
print("="*50)

# Check API key
masked = OPENAI_API_KEY[:8] + "..." + OPENAI_API_KEY[-4:] if len(OPENAI_API_KEY) > 12 else OPENAI_API_KEY
print(f"\n[1] API Key: {masked}")
print(f"    API Base: {OPENAI_API_BASE}")

# Test RAG search
print(f"\n[2] Testing RAG search...")

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
