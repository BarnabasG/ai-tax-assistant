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

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
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


async def run_mainstream_pipeline():
    print("=== GOV.UK Mainstream Ingestion Pipeline ===")
    from src.etl import discover_mainstream, fetch_mainstream, parse_mainstream
    
    # 1. Discover
    print("\n[1/4] Discovering GOV.UK mainstream guides...")
    docs = await discover_mainstream.discover_all()
    
    # 2. Fetch
    print("\n[2/4] Fetching raw JSON from GOV.UK Content API...")
    await fetch_mainstream.fetch_all(docs)
    
    # 3. Parse
    print("\n[3/4] Parsing structured documents...")
    parsed_docs = parse_mainstream.parse_all(docs)
    
    # 4. Filter already processed
    state = load_state()
    processed_set = set(state.get("processed_sections", []))
    
    docs_to_process = [d for d in parsed_docs if d["section_id"] not in processed_set]
    
    print(f"\n[4/4] Embedding and upserting {len(docs_to_process)} remaining documents...")
    if not docs_to_process:
        print("Everything is up to date!")
        return

    # Batch process and checkpoint state
    async for processed_batch in process_pipeline(docs_to_process):
        state["processed_sections"].extend([d["section_id"] for d in processed_batch])
        save_state(state)
        
    print("\nMainstream Ingestion complete!")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="HMRC RAG Ingestion Pipeline")
    parser.add_argument(
        "--manuals",
        action="store_true",
        help="Run internal technical manuals pipeline only",
    )
    parser.add_argument(
        "--mainstream",
        action="store_true",
        help="Run mainstream GOV.UK guidance pipeline only",
    )
    args = parser.parse_args()

    # If neither flag is specified, run both
    run_all = not args.manuals and not args.mainstream

    if run_all or args.manuals:
        asyncio.run(run_pipeline())
        
    if run_all or args.mainstream:
        asyncio.run(run_mainstream_pipeline())


if __name__ == "__main__":
    main()
