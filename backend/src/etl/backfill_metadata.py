"""
Backfill Metadata:
Iterates through all points in Qdrant and sets default audience_level and source_type payload values
for existing internal manuals.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from qdrant_client import models
from src.qdrant_store import store, COLLECTION

async def backfill():
    print("=== Backfilling Qdrant Metadata ===")
    store.connect()
    
    offset = None
    batch_size = 500
    total_scanned = 0
    total_updated = 0
    
    # We query for points where audience_level is not set to any value.
    # To do this safely, we scroll all points and check the payload locally.
    while True:
        res = await store.client.scroll(
            collection_name=COLLECTION,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points, next_offset = res
        if not points:
            break
            
        total_scanned += len(points)
        ids_to_update = []
        
        for p in points:
            payload = p.payload or {}
            # If audience_level or source_type is missing, add it to list
            if "audience_level" not in payload or "source_type" not in payload:
                ids_to_update.append(p.id)
                
        if ids_to_update:
            await store.client.set_payload(
                collection_name=COLLECTION,
                payload={
                    "audience_level": "internal_manual",
                    "source_type": "hmrc_manual"
                },
                points=ids_to_update,
            )
            total_updated += len(ids_to_update)
            print(f"Scanned {total_scanned} points... Backfilled {total_updated} so far.")
            
        if next_offset is None:
            break
        offset = next_offset

    print(f"\nBackfill complete! Scanned {total_scanned} points, updated {total_updated} points.")

if __name__ == "__main__":
    asyncio.run(backfill())
