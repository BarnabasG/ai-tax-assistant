"""
Update pipeline: Checks for freshness by comparing GOV.UK API timestamps with cached data.
Overwrites updated sections in Qdrant.
"""

import asyncio
import json
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import aiohttp
from tqdm import tqdm

from src.qdrant_store import store
from src.etl import discover, fetch, parse
from src.embed import process_pipeline

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
            
            if latest_time and cached_time and latest_time != cached_time:
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
    
    async for _ in process_pipeline(docs):
        pass
    
    print(f"\nUpdate complete! Upserted {len(docs)} documents.")

if __name__ == "__main__":
    asyncio.run(run_update())
