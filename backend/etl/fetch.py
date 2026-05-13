"""
Fetch: Downloads the raw JSON content from the GOV.UK Content API for discovered sections.
"""

import asyncio
import json
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import aiohttp
from tqdm import tqdm

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
RAW_JSON_DIR = os.path.join(DATA_DIR, "raw_json")
CONTENT_API = "https://www.gov.uk/api/content"


async def fetch_section(
    session: aiohttp.ClientSession,
    section: dict,
    semaphore: asyncio.Semaphore,
) -> bool:
    """Fetch a single section JSON and save to disk."""
    manual_slug = section["manual_slug"]
    section_id = section["section_id"]
    base_path = section["base_path"]

    # Ensure manual directory exists
    manual_dir = os.path.join(RAW_JSON_DIR, manual_slug)
    os.makedirs(manual_dir, exist_ok=True)

    cache_path = os.path.join(manual_dir, f"{section_id}.json")
    if os.path.exists(cache_path):
        return True  # Already cached

    url = f"{CONTENT_API}{base_path}"

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
                        # Rate limit, server error, or other HTTP error
                        import random
                        jitter = random.uniform(0.1, 1.0)
                        await asyncio.sleep((2 ** attempt) + jitter)
                        continue
            except Exception as e:
                import random
                jitter = random.uniform(0.1, 1.0)
                await asyncio.sleep((2 ** attempt) + jitter)

    print(f"Failed to fetch {url} after 10 attempts.")
    return False


async def fetch_all(sections: list[dict]):
    """Fetch JSON for all discovered sections."""
    os.makedirs(RAW_JSON_DIR, exist_ok=True)
    semaphore = asyncio.Semaphore(15)  # GOV.UK rate limit respect

    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_section(session, s, semaphore) for s in sections
        ]
        
        # Run with progress bar
        success_count = 0
        for f in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Fetching JSON", unit="section"):
            if await f:
                success_count += 1
                
    print(f"Successfully fetched {success_count}/{len(sections)} sections.")


if __name__ == "__main__":
    from discover import DISCOVERY_CACHE
    if os.path.exists(DISCOVERY_CACHE):
        with open(DISCOVERY_CACHE, "r") as f:
            sections = json.load(f)
        asyncio.run(fetch_all(sections))
    else:
        print("Run discover.py first.")
