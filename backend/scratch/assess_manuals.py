import asyncio
import os
import sys
import json
from collections import defaultdict

# Add current directory to path so 'src' package is found
sys.path.append(os.getcwd())

from src.qdrant_store import store

async def assess():
    print("=== HMRC RAG Content Assessment ===\n")
    
    # Ensure client is connected
    store.connect()
    
    # 1. Get all points from Qdrant (scrolling through the whole collection)
    # Note: We only need the payload to check content
    manual_stats = defaultdict(lambda: {"count": 0, "total_len": 0, "titles": set(), "samples": []})
    
    offset = None
    total_processed = 0
    
    while True:
        # Scroll through points
        # We use a large limit to speed it up
        res, next_offset = await store.client.scroll(
            collection_name="hmrc_pages",
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False
        )
        
        for point in res:
            p = point.payload
            slug = p["manual_slug"]
            text = p.get("text", "")
            
            # Basic stats
            manual_stats[slug]["count"] += 1
            manual_stats[slug]["total_len"] += len(text)
            manual_stats[slug]["titles"].add(p.get("title", ""))
            manual_stats[slug]["manual_title"] = p.get("manual_title", slug)
            
            # Keep a few samples of very short text
            if len(text.strip()) < 100:
                manual_stats[slug]["samples"].append(text.strip())

        total_processed += len(res)
        offset = next_offset
        if not offset:
            break

    print(f"Total points analyzed: {total_processed}")
    print(f"Total unique manuals: {len(manual_stats)}\n")

    # 2. Flagging logic
    suspicious = []
    
    for slug, stats in manual_stats.items():
        avg_len = stats["total_len"] / stats["count"]
        manual_title = stats.get("manual_title", "")
        
        reasons = []
        
        # Criterion 1: Generic/Test Title
        test_keywords = ["test", "dummy", "sandbox", "training", "placeholder", "template"]
        if any(kw in manual_title.lower() for kw in test_keywords) or any(kw in slug.lower() for kw in test_keywords):
            # Special check for "Statutory Residence Test" which is VALID
            if "residence test" not in manual_title.lower() and "residence test" not in slug.lower():
                reasons.append(f"Suspicious title/slug: '{manual_title}' ({slug})")
        
        # Criterion 2: Extremely short average content
        if avg_len < 150:
            reasons.append(f"Low average content length: {avg_len:.1f} characters")
            
        # Criterion 3: Samples look like junk
        if stats["samples"]:
            junk_indicators = ["test", "lorem", "coming soon", "tbc", "asdf"]
            for s in stats["samples"][:5]:
                if any(ji in s.lower() for ji in junk_indicators):
                    reasons.append(f"Sample content contains junk: '{s}'")
                    break

        if reasons:
            suspicious.append({
                "slug": slug,
                "title": manual_title,
                "reasons": reasons,
                "section_count": stats["count"]
            })

    # 3. Output results
    if not suspicious:
        print("No suspicious manuals found.")
    else:
        print(f"Found {len(suspicious)} suspicious manuals:\n")
        for s in suspicious:
            print(f"Manual: {s['title']}")
            print(f"Slug:   {s['slug']}")
            print(f"Stats:  {s['section_count']} sections")
            for r in s['reasons']:
                print(f"  - {r}")
            print("-" * 30)

    # Export a candidate blacklist
    blacklist_candidates = [s["slug"] for s in suspicious]
    with open("blacklist_candidates.json", "w") as f:
        json.dump(blacklist_candidates, f, indent=2)
    print(f"\nSaved {len(blacklist_candidates)} candidates to blacklist_candidates.json")

if __name__ == "__main__":
    asyncio.run(assess())
