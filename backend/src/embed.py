"""
Embed: Chunks text, generates dense and sparse vectors via Ollama and Qdrant, and upserts.

"""

import asyncio
import os
import signal
from typing import AsyncGenerator

import aiohttp
from dotenv import load_dotenv
from qdrant_client.models import PointStruct, SparseVector
from tqdm import tqdm

from src.qdrant_store import store

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = "nomic-embed-text"
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200
BATCH_SIZE = 50

SHUTTING_DOWN = False


def handle_shutdown(sig, frame):
    global SHUTTING_DOWN
    if not SHUTTING_DOWN:
        tqdm.write("\n\n⚠️ Graceful shutdown initiated. Finishing current batch...")
        SHUTTING_DOWN = True
    else:
        tqdm.write("\nForce quitting!")
        os._exit(1)


signal.signal(signal.SIGINT, handle_shutdown)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Splits text into overlapping chunks, falling back to periods to preserve sentences."""
    if not text:
        return []
        
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = start + chunk_size
        
        if end < text_len:
            last_period = text.rfind('.', start + chunk_size - overlap, end)
            if last_period != -1:
                end = last_period + 1
                
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end < text_len:
            start = end - overlap
        else:
            start = end
             
    return chunks


async def generate_embeddings(session: aiohttp.ClientSession, texts: list[str]) -> list[list[float]]:
    """Batch generate dense embeddings via Ollama. Falls back to sequential if batch fails."""
    url = f"{OLLAMA_URL}/api/embed"
    
    # Strip null bytes which often cause 400 Bad Request in C++ APIs
    clean_texts = [t.replace('\x00', '') for t in texts]
    payload = {"model": EMBED_MODEL, "input": clean_texts}
    
    try:
        async with session.post(url, json=payload, timeout=300) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("embeddings", [])
            else:
                err_text = await resp.text()
                # If 400, raise to trigger fallback block
                if resp.status == 400:
                    raise ValueError(f"HTTP 400: {err_text}")
                resp.raise_for_status()
                
    except aiohttp.ClientConnectorError as e:
        # Ollama is actually offline/dead. We must stop the pipeline!
        tqdm.write(f"\nOllama is unreachable: {e}")
        raise
        
    except Exception as e:
        # If it's a 400 or timeout, there might be a poison pill text in this batch.
        err_msg = str(e) or type(e).__name__
        if len(texts) > 1:
            tqdm.write(f"\nBatch embedding failed ({err_msg}). Retrying sequentially to isolate bad text...")
            embeddings = []
            for t in clean_texts:
                single_payload = {"model": EMBED_MODEL, "input": [t]}
                try:
                    async with session.post(url, json=single_payload, timeout=300) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            embeddings.extend(data.get("embeddings", [[]]))
                        else:
                            err_text = await resp.text()
                            tqdm.write(f"Skipping bad text chunk (HTTP {resp.status}): {err_text}")
                            embeddings.append([])
                except Exception as inner_e:
                    tqdm.write(f"Skipping text chunk due to error: {inner_e}")
                    embeddings.append([])
            return embeddings
        else:
            tqdm.write(f"Skipping un-embeddable text chunk: {e}")
            return [[]]


# FastEmbed BM25 sparse encoder
from fastembed import SparseTextEmbedding

_bm25_encoder = SparseTextEmbedding(model_name="Qdrant/bm25")


def generate_sparse_vector_passage(text: str) -> SparseVector:
    """Generate a BM25 sparse vector for a document passage (used during ingestion)."""
    embeddings = list(_bm25_encoder.passage_embed([text]))
    return SparseVector(
        indices=embeddings[0].indices.tolist(),
        values=embeddings[0].values.tolist(),
    )


def generate_sparse_vector_query(text: str) -> SparseVector:
    """Generate a BM25 sparse vector for a search query (used at search time)."""
    embeddings = list(_bm25_encoder.query_embed([text]))
    return SparseVector(
        indices=embeddings[0].indices.tolist(),
        values=embeddings[0].values.tolist(),
    )


# Search alias
generate_sparse_vector = generate_sparse_vector_query


async def embed_and_upsert_batch(session: aiohttp.ClientSession, docs: list[dict]):
    """Takes parsed docs, chunks them, embeds them, and upserts to Qdrant."""
    if not docs:
        return

    points = []
    texts_to_embed = []
    point_metadata = []

    for doc in docs:
        chunks = chunk_text(doc["text"])
        if not chunks:
            # If text is empty or weird, create a dummy chunk so it's still searchable by title
            chunks = [doc["title"]]
            
        for i, chunk in enumerate(chunks):
            # Context header
            context_header = f"Manual: {doc['manual_title']}\nSection: {doc['section_id']} - {doc['title']}\n\n"
            full_text = context_header + chunk
            
            texts_to_embed.append(full_text)
            
            # Point ID: section_id if 1 chunk, else section_id-chunk_index
            point_id = doc["section_id"] if len(chunks) == 1 else f"{doc['section_id']}-{i}"
            
            payload = {
                "section_id": doc["section_id"],
                "manual_slug": doc["manual_slug"],
                "manual_title": doc["manual_title"],
                "title": doc["title"],
                "text": full_text,  # Store the full chunk with header
                "chunk_index": i,
                "tax_type": doc["tax_type"],
                "related_pages": doc["related_pages"],
                "breadcrumb": doc["breadcrumb"],
                "gov_url": doc["gov_url"],
                "updated_at": doc["updated_at"],
                "audience_level": doc.get("audience_level", "internal_manual"),
                "source_type": doc.get("source_type", "hmrc_manual"),
            }
            
            point_metadata.append((point_id, payload, full_text))

    # Generate dense embeddings in one batch
    dense_embeddings = await generate_embeddings(session, texts_to_embed)
    
    # Generate sparse embeddings in one batch
    sparse_embeddings = list(_bm25_encoder.passage_embed(texts_to_embed))

    # Assemble points
    for (point_id, payload, text), dense, sparse_raw in zip(point_metadata, dense_embeddings, sparse_embeddings):
        if not dense:
            continue # Skip failed embeddings
            
        sparse = SparseVector(
            indices=sparse_raw.indices.tolist(),
            values=sparse_raw.values.tolist(),
        )
        
        # UUID generation
        import hashlib
        import uuid
        hashed_id = hashlib.md5(point_id.encode()).hexdigest()
        qdrant_id = str(uuid.UUID(hashed_id))
        
        # Store original ID in payload for easy retrieval
        payload["chunk_id"] = point_id

        point = PointStruct(
            id=qdrant_id,
            vector={
                "dense": dense,
                "bm25": sparse
            },
            payload=payload
        )
        points.append(point)

    if points:
        await store.upsert_batch(points)


async def process_pipeline(docs: list[dict]):
    """Main embedding pipeline processor."""
    await store.ensure_collection()
    
    async with aiohttp.ClientSession() as session:
        batch = []
        for doc in tqdm(docs, desc="Embedding & Upserting", unit="doc"):
            if SHUTTING_DOWN:
                break
                
            batch.append(doc)
            if len(batch) >= BATCH_SIZE:
                await embed_and_upsert_batch(session, batch)
                yield batch
                batch = []
                
        # Final batch
        if batch and not SHUTTING_DOWN:
            await embed_and_upsert_batch(session, batch)
            yield batch

