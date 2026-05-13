import asyncio
import sys
from qdrant_store import QdrantStore
from embed import generate_sparse_vector
from rag import embed_query

async def main():
    query = sys.argv[1]
    dense = await embed_query(query)
    sparse = generate_sparse_vector(query)
    
    store = QdrantStore()
    results = store.hybrid_search(dense, sparse, limit=5)
    
    for i, r in enumerate(results):
        print(f"[{i+1}] {r.payload.get('section_id')} - Score: {r.score}")

if __name__ == "__main__":
    asyncio.run(main())
