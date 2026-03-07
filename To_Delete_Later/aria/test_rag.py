"""
Test RAG (Qdrant) connection and retrieval
"""
import sys
sys.path.insert(0, '.')

from rag import RAGMemory

print("="*50)
print("RAG TEST")
print("="*50)

rag = RAGMemory()

# Test 1: Connection
print("\n[1] Testing Qdrant connection...")
if rag.connect():
    print("    [OK] Connected!")
else:
    print("    [FAIL] Could not connect")
    exit(1)

# Test 2: Collection info
print("\n[2] Getting collection info...")
info = rag.get_collection_info()
if info:
    print(f"    Collection: {info['name']}")
    print(f"    Points: {info['points_count']}")
else:
    print("    [FAIL] Could not get collection info")

# Test 3: Search
print("\n[3] Testing search (query: 'programming')...")
try:
    memories = rag.search("programming")
    if memories:
        print(f"    [OK] Found {len(memories)} memories:")
        for i, mem in enumerate(memories[:3], 1):
            preview = mem[:100] + "..." if len(mem) > 100 else mem
            print(f"    {i}. {preview}")
    else:
        print("    No memories found (collection might be empty)")
except Exception as e:
    print(f"    [ERROR] {e}")

# Test 4: Russian search
print("\n[4] Testing Russian search (query: 'привет')...")
try:
    memories = rag.search("привет")
    if memories:
        print(f"    [OK] Found {len(memories)} memories")
    else:
        print("    No memories found")
except Exception as e:
    print(f"    [ERROR] {e}")

print("\n" + "="*50)
