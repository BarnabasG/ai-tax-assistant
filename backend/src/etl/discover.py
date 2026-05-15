"""
Discovery: Finds all HMRC manuals and their sections via the GOV.UK Content API.
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
DISCOVERY_CACHE = os.path.join(DATA_DIR, "discovery_cache.json")
SEARCH_API = "https://www.gov.uk/api/search.json"
CONTENT_API = "https://www.gov.uk/api/content"

# Manuals that are just for testing or contain no real guidance
BLACKLIST = {
    "sharepoint-tax-manuals-test-site",
}


async def discover_all_manuals(session: aiohttp.ClientSession) -> list[dict]:
    """Paginate the GOV.UK Search API to find every HMRC manual."""
    manuals = []
    start = 0
    page_size = 50

    pbar = tqdm(desc="Discovering Manuals", unit="manual")

    while True:
        params = {
            "filter_document_type": "hmrc_manual",
            "count": page_size,
            "start": start,
            "fields": "title,link,description,public_timestamp",
        }
        
        # Retry logic for pagination
        for attempt in range(5):
            try:
                async with session.get(SEARCH_API, params=params) as resp:
                    if resp.status != 200:
                        raise Exception(f"Search API returned {resp.status}")
                    data = await resp.json()
                break
            except Exception as e:
                if attempt == 4:
                    print(f"Failed to fetch search results at start={start}: {e}")
                    return manuals
                await asyncio.sleep(2 ** attempt)

        results = data.get("results", [])
        if not results:
            break

        for r in results:
            link = r.get("link", "")
            slug = link.replace("/hmrc-internal-manuals/", "").strip("/")
            
            # Skip verified test/placeholder manuals
            if slug in BLACKLIST:
                continue
                
            manuals.append({
                "slug": slug,
                "title": r.get("title", slug),
                "description": r.get("description", ""),
                "link": r["link"],
                "updated_at": r.get("public_timestamp", ""),
            })

        pbar.update(len(results))
        start += page_size

        if start >= data.get("total", 0):
            break

    pbar.close()
    print(f"Discovered {len(manuals)} HMRC manuals.")
    return manuals


async def get_manual_sections(
    session: aiohttp.ClientSession,
    manual_slug: str,
    manual_title: str,
    semaphore: asyncio.Semaphore,
) -> list[dict]:
    """Recursively fetch all sections for a manual via the Content API."""
    sections = []

    async def walk(base_path: str):
        url = f"{CONTENT_API}{base_path}"
        
        for attempt in range(3):
            try:
                async with semaphore:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            if resp.status == 429:
                                raise Exception("Rate limited")
                            # 429 or 5xx should retry, 404 should probably just stop
                            if resp.status == 404:
                                return
                            raise Exception(f"HTTP {resp.status}")
                        data = await resp.json()
                break
            except Exception as e:
                if attempt == 2:
                    return
                await asyncio.sleep((2 ** attempt) + 0.5)

        details = data.get("details", {})

        # If this page has body content, it's a leaf section
        body = details.get("body", "").strip()
        if body:
            sections.append({
                "manual_slug": manual_slug,
                "manual_title": manual_title,
                "section_id": details.get("section_id", ""),
                "title": data.get("title", ""),
                "base_path": base_path,
                "updated_at": data.get("public_updated_at", ""),
            })

        # Walk child sections in parallel
        tasks = []
        for group in details.get("child_section_groups", []):
            for child in group.get("child_sections", []):
                child_path = child.get("base_path", "")
                if child_path:
                    tasks.append(walk(child_path))
        
        if tasks:
            await asyncio.gather(*tasks)

    await walk(f"/hmrc-internal-manuals/{manual_slug}")
    return sections


async def discover_all(force: bool = False) -> list[dict]:
    """
    Full discovery: finds every HMRC manual and every section within each.
    Caches the result to disk for instant re-runs.
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    if not force and os.path.exists(DISCOVERY_CACHE):
        with open(DISCOVERY_CACHE, "r") as f:
            cached = json.load(f)
        print(f"Loaded {len(cached)} sections from discovery cache.")
        return cached

    all_sections = []
    semaphore = asyncio.Semaphore(50)  # GOV.UK rate limits

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        manuals = await discover_all_manuals(session)

        pbar = tqdm(total=len(manuals), desc="Walking Manual Trees", unit="manual")

        async def process_manual(manual):
            pbar.set_postfix(current=manual["slug"][:20])
            sections = await get_manual_sections(
                session, manual["slug"], manual["title"], semaphore
            )
            pbar.update(1)
            return sections

        tasks = [process_manual(m) for m in manuals]
        results = await asyncio.gather(*tasks)
        
        for sections in results:
            all_sections.extend(sections)

        pbar.close()

    print(f"\nTotal sections discovered: {len(all_sections)}")

    # Cache to disk
    with open(DISCOVERY_CACHE, "w") as f:
        json.dump(all_sections, f)
    print(f"Discovery cache saved to {DISCOVERY_CACHE}")

    return all_sections


if __name__ == "__main__":
    asyncio.run(discover_all())
