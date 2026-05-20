"""
Update pipeline: Checks for freshness by comparing GOV.UK API timestamps with cached data.
Overwrites updated sections in Qdrant.

Both run_update() and run_mainstream_update() support resumability via
checkpoint state files. If interrupted mid-embedding, the next run will
skip already-processed documents and continue from where it left off.
"""

import asyncio
import json
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from datetime import datetime, timezone
import aiohttp
from tqdm import tqdm

from src.qdrant_store import store
from src.etl import discover, fetch, parse
from src.embed import process_pipeline

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
UPDATE_STATE_FILE = os.path.join(DATA_DIR, "update_state.json")


def _parse_timestamp(t: str) -> datetime:
    """Parse GOV.UK timestamp string robustly, converting to UTC datetime."""
    if not t:
        return datetime.min.replace(tzinfo=timezone.utc)
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _timestamps_differ(t1: str, t2: str) -> bool:
    """Check if two timestamp strings represent different points in time."""
    if not t1 or not t2:
        return False
    return _parse_timestamp(t1) != _parse_timestamp(t2)



def _load_update_state() -> dict:
    """Load the update checkpoint state, or return a fresh state."""
    if os.path.exists(UPDATE_STATE_FILE):
        try:
            with open(UPDATE_STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"embedded_sections": []}


def _save_update_state(state: dict):
    """Persist the update checkpoint state to disk."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(UPDATE_STATE_FILE, "w") as f:
        json.dump(state, f)


def _clear_update_state():
    """Remove the checkpoint file after a successful full run."""
    if os.path.exists(UPDATE_STATE_FILE):
        os.remove(UPDATE_STATE_FILE)


async def run_update():
    print("=== HMRC RAG Freshness Update ===")
    
    # 1. Re-discover everything (force=True to bypass cache)
    print("\n[1/3] Checking GOV.UK for latest timestamps...")
    latest_sections = await discover.discover_all(force=True)
    
    # 2. Compare against what we currently have in Qdrant
    # Qdrant allows us to scroll through payload fields. 
    # But since we have a fast cache locally, it's easier to compare against the local discovery cache.
    # Actually, we just generated a new cache, so let's look at the raw json cache.
    
    raw_json_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw_json")
    
    needs_update = []
    
    for sec in latest_sections:
        manual_slug = sec["manual_slug"]
        section_id = sec["section_id"]
        latest_time = sec["updated_at"]
        
        cache_path = os.path.join(raw_json_dir, manual_slug, f"{section_id}.json")
        
        if not os.path.exists(cache_path):
            needs_update.append(sec)
            continue
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            cached_time = data.get("public_updated_at", "")
            if _timestamps_differ(latest_time, cached_time):
                needs_update.append(sec)
        except Exception:
            needs_update.append(sec)
            
    print(f"\nFound {len(needs_update)} sections that are new or modified.")
    
    if not needs_update:
        print("Everything is up to date.")
        return
        
    # 3. Fetch, parse, embed just the updated ones
    print("\n[2/3] Fetching updated content...")
    # Delete old cached JSON so fetch.py downloads fresh ones
    for sec in needs_update:
        p = os.path.join(raw_json_dir, sec["manual_slug"], f"{sec['section_id']}.json")
        if os.path.exists(p):
            os.remove(p)
            
    await fetch.fetch_all(needs_update)
    
    print("\n[3/3] Parsing and embedding updates...")
    docs = parse.parse_all(needs_update)

    # Resumable: load checkpoint state and skip already-embedded docs
    state = _load_update_state()
    embedded_set = set(state.get("embedded_sections", []))
    docs_to_embed = [d for d in docs if d["section_id"] not in embedded_set]

    if not docs_to_embed:
        print("All documents already embedded (resumed from checkpoint).")
        _clear_update_state()
        return

    print(f"Embedding {len(docs_to_embed)} documents ({len(embedded_set)} already done)...")

    async for batch in process_pipeline(docs_to_embed):
        state["embedded_sections"].extend([d["section_id"] for d in batch])
        _save_update_state(state)

    _clear_update_state()
    print(f"\nUpdate complete! Upserted {len(docs_to_embed)} documents.")

async def run_mainstream_update():
    print("=== GOV.UK Mainstream Freshness Update ===")
    from src.etl import discover_mainstream, fetch_mainstream, parse_mainstream
    
    # 1. Re-discover everything (force=True to bypass cache)
    print("\n[1/3] Checking GOV.UK for latest mainstream timestamps...")
    latest_docs = await discover_mainstream.discover_all(force=True)
    
    # 2. Compare against what we currently have
    raw_json_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw_json_mainstream"))
    needs_update = []
    
    for doc in latest_docs:
        slug = doc["slug"]
        latest_time = doc["updated_at"]
        
        # Slugs can contain slashes (e.g. "guidance/foo"), so flatten for file path
        safe_slug = slug.replace("/", "_")
        cache_path = os.path.join(raw_json_dir, f"{safe_slug}.json")
        
        if not os.path.exists(cache_path):
            # Also check the non-flattened path for backward compat
            alt_path = os.path.join(raw_json_dir, f"{slug}.json")
            if not os.path.exists(alt_path):
                needs_update.append(doc)
                continue
            cache_path = alt_path
            
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            cached_time = data.get("public_updated_at", data.get("public_timestamp", ""))
            
            if _timestamps_differ(latest_time, cached_time):
                needs_update.append(doc)
        except Exception:
            needs_update.append(doc)
            
    print(f"\nFound {len(needs_update)} mainstream documents that are new or modified.")
    
    if not needs_update:
        print("Everything is up to date.")
        return
        
    # 3. Fetch, parse, embed just the updated ones
    print("\n[2/3] Fetching updated mainstream content...")
    for doc in needs_update:
        slug = doc["slug"]
        safe_slug = slug.replace("/", "_")
        for path_slug in [safe_slug, slug]:
            p = os.path.join(raw_json_dir, f"{path_slug}.json")
            if os.path.exists(p):
                os.remove(p)
            
    await fetch_mainstream.fetch_all(needs_update)
    
    print("\n[3/3] Parsing and embedding updates...")
    docs = parse_mainstream.parse_all(needs_update)

    # Resumable: load checkpoint state and skip already-embedded docs
    state = _load_update_state()
    embedded_set = set(state.get("embedded_sections", []))
    docs_to_embed = [d for d in docs if d["section_id"] not in embedded_set]

    if not docs_to_embed:
        print("All documents already embedded (resumed from checkpoint).")
        _clear_update_state()
        return

    print(f"Embedding {len(docs_to_embed)} documents ({len(embedded_set)} already done)...")

    async for batch in process_pipeline(docs_to_embed):
        state["embedded_sections"].extend([d["section_id"] for d in batch])
        _save_update_state(state)

    _clear_update_state()
    print(f"\nUpdate complete! Upserted {len(docs_to_embed)} documents.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="HMRC RAG Update Pipeline")
    parser.add_argument(
        "--manuals",
        action="store_true",
        help="Update internal technical manuals only",
    )
    parser.add_argument(
        "--mainstream",
        action="store_true",
        help="Update mainstream GOV.UK guidance only",
    )
    args = parser.parse_args()

    # If neither flag is specified, update both
    update_all = not args.manuals and not args.mainstream

    if update_all or args.manuals:
        asyncio.run(run_update())
        
    if update_all or args.mainstream:
        asyncio.run(run_mainstream_update())
