from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from embed import generate_sparse_vector
from qdrant_store import store
from rag import stream_rag_answer, embed_query

app = FastAPI(title="HMRC RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    query: str
    history: list[dict] = []
    model: str = ""

class SearchRequest(BaseModel):
    query: str
    limit: int = 10

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    return StreamingResponse(
        stream_rag_answer(req.query, req.history, req.model),
        media_type="text/event-stream"
    )

@app.post("/search")
async def search_endpoint(req: SearchRequest):
    dense = await embed_query(req.query)
    sparse = generate_sparse_vector(req.query)
    
    results = store.hybrid_search(dense, sparse, limit=req.limit)
    
    # Group by manual
    manuals = {}
    for r in results:
        p = r.payload
        slug = p["manual_slug"]
        if slug not in manuals:
            manuals[slug] = {
                "manual_title": p["manual_title"],
                "results": []
            }
        manuals[slug]["results"].append({
            "section_id": p["section_id"],
            "title": p["title"],
            "score": r.score
        })
        
    return {"groups": manuals}

@app.get("/page")
async def get_page(code: str):
    results = store.get_by_section_id(code)
    if not results:
        return {"error": "Page not found"}
        
    p = results[0].payload
    manual_slug = p["manual_slug"]
    
    # Read pristine, unchunked full text directly from the local JSON cache
    # This avoids having to stitch overlapping chunks back together
    from etl.parse import parse_section
    doc = parse_section(manual_slug, code)
    
    if doc:
        full_text = doc["text"]
    else:
        # Fallback if cache is missing (shouldn't happen)
        context_header = f"Manual: {p['manual_title']}\nSection: {p['section_id']} - {p['title']}\n\n"
        chunk_text = p.get("text", "")
        if chunk_text.startswith(context_header):
            chunk_text = chunk_text[len(context_header):]
        full_text = chunk_text + "\n\n[Warning: Document too long and local cache missing, showing partial chunk]"

    return {
        "section_id": p["section_id"],
        "title": p["title"],
        "manual_title": p["manual_title"],
        "text": full_text,
        "related_pages": p["related_pages"],
        "breadcrumb": p["breadcrumb"],
        "gov_url": p["gov_url"],
        "updated_at": p["updated_at"]
    }

@app.get("/autocomplete")
async def autocomplete(q: str):
    if len(q) < 3:
        return {"suggestions": []}
        
    results = store.search_by_title(q, limit=5)
    suggestions = []
    for r in results:
        p = r.payload
        suggestions.append({
            "code": p["section_id"],
            "title": p["title"],
            "manual": p["manual_title"]
        })
    return {"suggestions": suggestions}

@app.get("/manual-tree")
async def manual_tree(manual: str):
    results = store.get_sections_for_manual(manual)
    
    # Reconstruct tree from breadcrumbs
    # This is a flat list for now, the frontend can build the hierarchy
    sections = []
    for r in results:
        p = r.payload
        sections.append({
            "id": p["section_id"],
            "title": p["title"],
            "breadcrumb": p["breadcrumb"]
        })
    return {"sections": sections}

@app.get("/models")
async def list_models():
    from llm import router
    return await router.get_available_models()
