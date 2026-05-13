from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from embed import generate_sparse_vector
from qdrant_store import store
from rag import stream_rag_answer, embed_query
from llm import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await router.close()

app = FastAPI(title="HMRC RAG API", lifespan=lifespan)

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
    from fastapi.concurrency import run_in_threadpool
    dense = await embed_query(req.query)
    sparse = await run_in_threadpool(generate_sparse_vector, req.query)
    
    results = await run_in_threadpool(store.hybrid_search, dense, sparse, limit=req.limit)
    
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

class TitleRequest(BaseModel):
    query: str
    response: str = ""
    model: str = "gemma3:12b-cloud"

@app.post("/generate-title")
async def generate_title(req: TitleRequest):
    content = f"Generate a very short, 4 to 8 word title for this conversation. Question: {req.query}"
    if req.response:
        content += f"\nAnswer: {req.response}"
    content += "\nOnly output the title, no quotes or punctuation."
    
    messages = [{"role": "user", "content": content}]
    
    async def try_model(model_name: str) -> str:
        full_response = ""
        import json
        async for chunk in router.stream_chat(messages, model_name):
            try:
                data = json.loads(chunk.strip())
                if "token" in data:
                    full_response += data["token"]
            except Exception:
                pass
        return full_response.strip().strip('"').strip("'").strip("*")

    try:
        title = await try_model("gemma3:12b-cloud")
        if not title:
            raise ValueError("Empty response")
        return {"title": title}
    except Exception:
        if req.model and req.model != "gemma3:12b-cloud":
            try:
                title = await try_model(req.model)
                if title:
                    return {"title": title}
            except Exception:
                pass
        return {"title": req.query[:30]}

@app.get("/page")
def get_page(code: str):
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
def manual_tree(manual: str):
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
    return await router.get_available_models()
