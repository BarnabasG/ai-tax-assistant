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

SYSTEM_PROMPT = """You are a helpful UK tax assistant. You answer queries using the provided context, which contains excerpts from technical HMRC Internal Manuals and/or GOV.UK guidance.

RULES:
1. Ground your answers strictly in the provided context below.
2. Adapt your tone and style depending on the source material you cite:
   - When explaining concepts from a GOV.UK guide, write in clear, direct, and accessible professional English.
   - When explaining details from a technical HMRC manual, maintain high technical and legal precision.
   - Blend these sources seamlessly. Do NOT use headers, labels, or signposts like "Simple Guidance", "Plain English", "Technical details", or similar. Write a single, cohesive, professional response.
3. Cite your sources using their exact code in square brackets:
   - For HMRC manuals, cite the code (e.g. [VIT13500]).
   - For GOV.UK guides, cite the guide code (e.g. [GOV:self-assessment-tax-returns/deadlines]).
   - Avoid over-citation: if a single source applies to an entire paragraph or list of bullet points, cite it once at the end of that block/paragraph rather than repeating it on every sentence or bullet item.
4. Only if the provided context is completely irrelevant to the query should you state: "I could not find specific HMRC guidance on this topic". If you can answer the query (even partially), do so and omit this refusal statement entirely.
5. At the absolute end of your response (after all explanations), output exactly 3 suggested follow-up questions that the user might want to ask next. Wrap them in a <suggestions> tag and separate each with a pipe character |. Example: <suggestions>What is the VAT rate?|How do I apply?|Are there exceptions?</suggestions>

CONTEXT:
{context}
"""

def verify_citations(response: str, allowed_codes: set[str]) -> list[str]:
    """Finds all citations like [VIT13500] or [GOV:slug] (using standard or fullwidth brackets) and returns hallucinated ones."""
    pattern = r'(?:\[|【)([A-Z]{2,6}\d{4,6}|GOV:[a-zA-Z0-9\-\/]+)(?:\]|】)'
    citations = re.findall(pattern, response)
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
    
    # Deduplicate sources
    seen_sources = set()
    unique_sources = []
    for r in results:
        sid = r.payload["section_id"]
        if sid not in seen_sources:
            unique_sources.append({"section_id": sid, "title": r.payload["title"]})
            seen_sources.add(sid)

    # Yield early metadata containing sources before the chat starts streaming
    yield json.dumps({"sources": unique_sources}) + "\n\n"

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
    
    metadata = {
        "done": True,
        "sources": unique_sources,
        "hallucinated_citations": hallucinated
    }
    yield json.dumps(metadata) + "\n\n"
