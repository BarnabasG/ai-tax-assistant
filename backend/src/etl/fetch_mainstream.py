"""
Fetch for GOV.UK Mainstream Guidance:
Downloads the raw JSON content from the GOV.UK Content API for discovered mainstream documents.
"""

import asyncio
import json
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import aiohttp
from tqdm import tqdm

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
RAW_JSON_DIR = os.path.join(DATA_DIR, "raw_json_mainstream")
CONTENT_API = "https://www.gov.uk/api/content"

async def fetch_doc(
    session: aiohttp.ClientSession,
    doc: dict,
    semaphore: asyncio.Semaphore,
) -> bool:
    """Fetch a single document JSON from Content API and save to disk."""
    link = doc["link"]
    slug = link.strip("/")
    
    cache_path = os.path.join(RAW_JSON_DIR, f"{slug}.json")
    if os.path.exists(cache_path):
        return True  # Already cached

    # Ensure parent directories exist (handles nested paths like government/publications/...)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)

    url = f"{CONTENT_API}{link}"

    async with semaphore:
        for attempt in range(10):
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        with open(cache_path, "w") as f:
                            json.dump(data, f)
                        return True
                    elif resp.status == 404:
                        return False
                    else:
                        # Rate limit or other error -> exponential backoff
                        import random
                        jitter = random.uniform(0.1, 1.0)
                        await asyncio.sleep((2 ** attempt) + jitter)
                        continue
            except Exception:
                import random
                jitter = random.uniform(0.1, 1.0)
                await asyncio.sleep((2 ** attempt) + jitter)

    print(f"Failed to fetch {url} after 10 attempts.")
    return False

async def fetch_all(docs: list[dict]):
    """Fetch JSON for all discovered documents."""
    os.makedirs(RAW_JSON_DIR, exist_ok=True)
    semaphore = asyncio.Semaphore(15)  # GOV.UK rate limit respect

    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_doc(session, d, semaphore) for d in docs
        ]
        
        success_count = 0
        for f in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Fetching Mainstream JSON", unit="doc"):
            if await f:
                success_count += 1
                
    print(f"Successfully fetched {success_count}/{len(docs)} documents.")

if __name__ == "__main__":
    from discover_mainstream import DISCOVERY_CACHE
    if os.path.exists(DISCOVERY_CACHE):
        with open(DISCOVERY_CACHE, "r") as f:
            docs = json.load(f)
        asyncio.run(fetch_all(docs))
    else:
        print("Run discover_mainstream.py first.")
