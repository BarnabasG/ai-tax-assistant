import json
import re
from typing import AsyncGenerator

import aiohttp
from src.embed import generate_sparse_vector, OLLAMA_URL, EMBED_MODEL
from src.llm import router
from src.qdrant_store import store

async def embed_query(query: str) -> list[float]:
    """Get dense embedding for the query.
    
    Uses keep_alive=0 so Ollama immediately unloads nomic-embed-text after
    each request, freeing VRAM for the chat LLM to load without contention.
    """
    url = f"{OLLAMA_URL}/api/embed"
    payload = {"model": EMBED_MODEL, "input": [query], "keep_alive": 0}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("embeddings", [[]])[0]
    return []

SYSTEM_PROMPT = """You are an expert UK tax legislation assistant for an accountancy firm.

RULES:
1. Answer ONLY using the provided HMRC manual excerpts below.
2. Cite every factual claim with the exact page code in square brackets, e.g. [VIT13500].
3. Only if the provided context is completely irrelevant to the query should you state: "I could not find specific HMRC guidance on this topic". If you can answer the query (even partially), do so and omit this refusal statement entirely.
4. Be precise and professional. Quote exact wording from the manuals where highly relevant.
5. At the absolute end of your response (after all explanations), output exactly 3 suggested follow-up questions that the user might want to ask next. Wrap them in a <suggestions> tag and separate each with a pipe character |. Example: <suggestions>What is the VAT rate?|How do I apply?|Are there exceptions?</suggestions>

CONTEXT:
{context}
"""

def verify_citations(response: str, allowed_codes: set[str]) -> list[str]:
    """Finds all citations like [VIT13500] and returns any that are hallucinated."""
    citations = re.findall(r'\[([A-Z]{2,6}\d{4,6})\]', response)
    hallucinated = [c for c in citations if c not in allowed_codes]
    return hallucinated

async def stream_rag_answer(query: str, chat_history: list[dict], model: str) -> AsyncGenerator[str, None]:
    """
    1. Embed query
    2. Hybrid search Qdrant
    3. Construct prompt
    4. Stream response
    5. Yield final verification metadata
    """
    # 1 & 2. Retrieval
    dense = await embed_query(query)
    sparse = generate_sparse_vector(query)
    
    if not dense:
        yield json.dumps({"error": "Failed to embed query."}) + "\n\n"
        return
        
    results = await store.hybrid_search(dense_vector=dense, sparse_vector=sparse, limit=8)
    
    if not results:
        yield json.dumps({"token": "I could not find any relevant HMRC guidance for this query."}) + "\n\n"
        return
        
    # Build context
    context_blocks = []
    allowed_codes = set()
    
    for r in results:
        p = r.payload
        code = p["section_id"]
        allowed_codes.add(code)
        block = f"--- [{code}] {p['manual_title']} - {p['title']} ---\n{p['text']}\n"
        context_blocks.append(block)
        
    context_str = "\n".join(context_blocks)
    sys_prompt = SYSTEM_PROMPT.format(context=context_str)
    
    messages = [{"role": "system", "content": sys_prompt}] + chat_history + [{"role": "user", "content": query}]
    
    # 4. Stream response
    full_response = ""
    async for chunk_json in router.stream_chat(messages, model):
        try:
            data = json.loads(chunk_json.strip())
            if "token" in data:
                full_response += data["token"]
        except json.JSONDecodeError:
            pass
        yield chunk_json
        
    # 5. Verification
    hallucinated = verify_citations(full_response, allowed_codes)
    
    # Deduplicate sources
    seen_sources = set()
    unique_sources = []
    for r in results:
        sid = r.payload["section_id"]
        if sid not in seen_sources:
            unique_sources.append({"section_id": sid, "title": r.payload["title"]})
            seen_sources.add(sid)

    metadata = {
        "done": True,
        "sources": unique_sources,
        "hallucinated_citations": hallucinated
    }
    yield json.dumps(metadata) + "\n\n"
