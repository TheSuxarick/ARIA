"""
ARIA RAG (Retrieval Augmented Generation)
Uses Qdrant vector database for memory retrieval
"""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from config import QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION, RAG_TOP_K


class RAGMemory:
    """RAG-based memory retrieval from Qdrant"""
    
    def __init__(self):
        self.host = QDRANT_HOST
        self.port = QDRANT_PORT
        self.collection = QDRANT_COLLECTION
        self.top_k = RAG_TOP_K
        self.client = None
        self.embedding_model = None
        
        # API key rotation for embeddings
        self._current_key_index = 0
        
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
        Get embedding for text using Gemini embeddings
        With API key rotation on rate limits.
        
        Note: This uses the google-genai embeddings API.
        Make sure your collection was created with the same embedding model.
        """
        import time
        from google import genai
        from config import GEMINI_API_KEYS
        
        if not GEMINI_API_KEYS:
            raise ValueError("No Gemini API key for embeddings")
        
        num_keys = len(GEMINI_API_KEYS)
        last_error = None
        
        # Try each key at least once, plus some retries
        max_attempts = num_keys * 2
        keys_tried = set()
        
        for attempt in range(max_attempts):
            try:
                # Use current key
                key = GEMINI_API_KEYS[self._current_key_index]
                print(f"[*] Embedding: trying key #{self._current_key_index+1}")
                
                client = genai.Client(api_key=key)
                
                response = client.models.embed_content(
                    model="text-embedding-004",
                    contents=text
                )
                
                return response.embeddings[0].values
                
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                # Check for rate limit
                if "429" in error_str or "rate" in error_str or "quota" in error_str:
                    keys_tried.add(self._current_key_index)
                    old_index = self._current_key_index
                    
                    # Rotate to next key
                    self._current_key_index = (self._current_key_index + 1) % num_keys
                    
                    print(f"[!] Key #{old_index+1} rate limited, switching to #{self._current_key_index+1}")
                    
                    # If we've tried all keys, wait before retrying
                    if len(keys_tried) >= num_keys:
                        wait_time = 2
                        print(f"[*] All keys tried, waiting {wait_time}s...")
                        time.sleep(wait_time)
                        keys_tried.clear()
                else:
                    # Other error
                    print(f"[!] Embedding error: {str(e)[:60]}")
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
                # Try different possible payload field names
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
