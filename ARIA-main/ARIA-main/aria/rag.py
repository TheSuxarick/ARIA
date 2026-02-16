"""
ARIA RAG (Retrieval Augmented Generation)
Uses Qdrant vector database for memory retrieval
"""
import time
import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from config import (
    QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION, RAG_TOP_K,
    OPENAI_API_KEY, OPENAI_API_BASE
)


class RAGMemory:
    """RAG-based memory retrieval from Qdrant"""
    
    def __init__(self):
        self.host = QDRANT_HOST
        self.port = QDRANT_PORT
        self.collection = QDRANT_COLLECTION
        self.top_k = RAG_TOP_K
        self.client = None
        
    def connect(self):
        """Connect to Qdrant"""
        if self.client is None:
            try:
                self.client = QdrantClient(host=self.host, port=self.port)
                # Test connection
                collections = self.client.get_collections()
                print(f"[OK] Connected to Qdrant at {self.host}:{self.port}")
                print(f"[*] Available collections: {[c.name for c in collections.collections]}")
                return True
            except Exception as e:
                print(f"[ERROR] Could not connect to Qdrant: {e}")
                self.client = None
                return False
        return True
    
    def _get_embedding(self, text):
        """
        Get embedding for text using OpenAI-compatible embeddings API.
        """
        if not OPENAI_API_KEY:
            raise ValueError("No API key for embeddings")
        
        url = f"{OPENAI_API_BASE}/embeddings"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        }
        payload = {
            "model": "text-embedding-ada-002",
            "input": text
        }
        
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                resp_data = resp.json()
                
                if resp.status_code == 200 and "data" in resp_data:
                    return resp_data["data"][0]["embedding"]
                else:
                    err = resp_data.get("error", {})
                    if isinstance(err, dict):
                        error_msg = err.get("message", str(resp_data))
                    else:
                        error_msg = str(resp_data)
                    raise Exception(f"Embedding API error ({resp.status_code}): {error_msg}")
                    
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                if "429" in error_str or "rate" in error_str:
                    wait_time = 2 ** attempt
                    print(f"[!] Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"[!] Embedding error: {str(e)[:60]}")
                    if attempt < max_retries - 1:
                        time.sleep(0.5)
        
        raise last_error
    
    def search(self, query, top_k=None):
        """
        Search for relevant memories
        
        Args:
            query: Search query text
            top_k: Number of results (default: RAG_TOP_K from config)
            
        Returns:
            List of memory strings
        """
        if not self.connect():
            return []
        
        top_k = top_k or self.top_k
        
        try:
            # Check if collection exists
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if self.collection not in collection_names:
                print(f"[!] Collection '{self.collection}' not found")
                return []
            
            # Get query embedding
            query_embedding = self._get_embedding(query)
            
            # Search in Qdrant
            results = self.client.query_points(
                collection_name=self.collection,
                query=query_embedding,
                limit=top_k
            ).points
            
            # Extract text from results
            memories = []
            for hit in results:
                payload = hit.payload
                if payload:
                    text = payload.get('text') or payload.get('content') or payload.get('message') or str(payload)
                    memories.append(text)
            
            if memories:
                print(f"[*] Found {len(memories)} relevant memories")
            
            return memories
            
        except Exception as e:
            print(f"[!] RAG search error: {e}")
            return []
    
    def get_collection_info(self):
        """Get information about the collection"""
        if not self.connect():
            return None
        
        try:
            info = self.client.get_collection(self.collection)
            return {
                "name": self.collection,
                "points_count": info.points_count
            }
        except Exception as e:
            print(f"[!] Could not get collection info: {e}")
            return None


# Singleton
_rag = None

def get_rag():
    global _rag
    if _rag is None:
        _rag = RAGMemory()
    return _rag


if __name__ == "__main__":
    # Test RAG
    rag = RAGMemory()
    
    print("Testing RAG connection...")
    if rag.connect():
        info = rag.get_collection_info()
        if info:
            print(f"Collection info: {info}")
        
        print("\nSearching for 'программирование'...")
        memories = rag.search("программирование")
        for i, mem in enumerate(memories, 1):
            print(f"\n{i}. {mem[:200]}...")
