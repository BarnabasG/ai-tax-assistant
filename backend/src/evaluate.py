"""
Evaluation Harness for HMRC RAG
Tests retrieval precision and LLM hallucination rate.
"""

import asyncio
import json
import os
from collections import Counter

from src.qdrant_store import store
from src.embed import generate_sparse_vector
from src.rag import embed_query

TEST_CASES = [
    {
        "query": "Can a business claim VAT back on legal expenses for an insurance claim?",
        "expected_code": "VIT13500",
    },
    {
        "query": "Can holding companies register for VAT?",
        "expected_code": "VIT40100", # Or VIT40600
    },
    {
        "query": "What is the VAT fraction for motoring road fuel?",
        "expected_code": "VIT55400",
    },

]

async def run_evaluation():
    # Pre-run checks
    if (await store.count()) == 0:
        print("Error: Qdrant collection is empty. Run 'make ingest' first.")
        return

    print(f"Running evaluation on {len(TEST_CASES)} queries...\n")
    
    results = []
    found_in_top_1 = 0
    found_in_top_5 = 0
    
    for case in TEST_CASES:
        query = case["query"]
        expected = case["expected_code"]
        
        # Embed
        dense = await embed_query(query)
        sparse = generate_sparse_vector(query)
        
        # Search
        hits = await store.hybrid_search(dense, sparse, limit=5)
        
        top_5_codes = [h.payload["section_id"] for h in hits]
        
        hit_pos = -1
        if expected in top_5_codes:
            hit_pos = top_5_codes.index(expected) + 1
            found_in_top_5 += 1
            if hit_pos == 1:
                found_in_top_1 += 1
                
        results.append({
            "query": query,
            "expected": expected,
            "hit_position": hit_pos,
            "retrieved_top_5": top_5_codes,
            "best_score": hits[0].score if hits else 0
        })
        
        status = f"✅ (Rank {hit_pos})" if hit_pos > 0 else "❌"
        print(f"[{status}] {query}")
        print(f"    Expected: {expected}")
        if hit_pos < 0:
            print(f"    Got: {top_5_codes}")
            
    print("\n=== Summary ===")
    print(f"Precision @ 1: {found_in_top_1 / len(TEST_CASES) * 100:.1f}%")
    print(f"Recall @ 5:    {found_in_top_5 / len(TEST_CASES) * 100:.1f}%")
    
    # Save results
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "eval_results.json"), "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    asyncio.run(run_evaluation())
