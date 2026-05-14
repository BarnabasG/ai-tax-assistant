"""
Ingestion Orchestrator: Runs discover -> fetch -> parse -> embed.
"""

import asyncio
import json
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.etl import discover, fetch, parse
from src.embed import process_pipeline

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
STATE_FILE = os.path.join(DATA_DIR, "ingest_state.json")

# Module path setup (removed in favor of project scripts)


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"processed_sections": []}


def save_state(state: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


async def run_pipeline():
    print("=== HMRC RAG Ingestion Pipeline ===")
    
    # 1. Discover all sections (uses cache if available)
    print("\n[1/4] Discovering HMRC manuals...")
    sections = await discover.discover_all()
    
    # 2. Fetch raw JSON for all sections
    print("\n[2/4] Fetching raw JSON from GOV.UK Content API...")
    await fetch.fetch_all(sections)
    
    # 3. Parse JSON into structured docs
    print("\n[3/4] Parsing structured documents...")
    docs = parse.parse_all(sections)
    
    # 4. Filter already processed
    state = load_state()
    processed_set = set(state.get("processed_sections", []))
    
    docs_to_process = [d for d in docs if d["section_id"] not in processed_set]
    
    print(f"\n[4/4] Embedding and upserting {len(docs_to_process)} remaining documents...")
    if not docs_to_process:
        print("Everything is up to date!")
        return

    # Batch process and checkpoint state
    async for processed_batch in process_pipeline(docs_to_process):
        state["processed_sections"].extend([d["section_id"] for d in processed_batch])
        save_state(state)
        
    print("\nIngestion complete!")


def main():
    asyncio.run(run_pipeline())

if __name__ == "__main__":
    main()
