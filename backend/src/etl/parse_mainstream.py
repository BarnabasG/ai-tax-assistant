"""
Parse for GOV.UK Mainstream Guidance:
Extracts text, titles, links, and updates metadata from raw cached JSON mainstream documents.
"""

import concurrent.futures
import json
import os
import re
from tqdm import tqdm

from src.etl.parse import strip_html

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
RAW_JSON_DIR = os.path.join(DATA_DIR, "raw_json_mainstream")

def parse_mainstream_file(cache_path: str, doc_info: dict) -> list[dict]:
    """Parse a single mainstream cached JSON file. Can return multiple docs for multi-part guides."""
    if not os.path.exists(cache_path):
        return []

    try:
        with open(cache_path, "r") as f:
            data = json.load(f)
    except Exception:
        return []

    base_slug = doc_info["slug"]
    doc_type = data.get("document_type", doc_info.get("document_type", ""))
    title = data.get("title", doc_info.get("title", ""))
    base_path = data.get("base_path", doc_info.get("link", f"/{base_slug}"))
    updated_at = data.get("public_updated_at", data.get("public_timestamp", doc_info.get("updated_at", "")))

    # Determine tax type keyword heuristic
    tax_type = "General"
    slug_lower = base_slug.lower()
    if "vat" in slug_lower:
        tax_type = "VAT"
    elif "capital-gains" in slug_lower:
        tax_type = "CG"
    elif "paye" in slug_lower or "payroll" in slug_lower:
        tax_type = "PAYE"
    elif "income-tax" in slug_lower or "self-assessment" in slug_lower:
        tax_type = "Income Tax"
    elif "national-insurance" in slug_lower:
        tax_type = "NI"
    elif "corporation-tax" in slug_lower:
        tax_type = "CT"

    details = data.get("details", {})
    parsed_docs = []

    if doc_type == "guide" and "parts" in details:
        # Multi-part guide
        parts = details["parts"]
        for part in parts:
            part_slug = part.get("slug", "")
            part_title = part.get("title", "")
            part_body_html = part.get("body", "")

            if not part_body_html:
                continue

            clean_text = strip_html(part_body_html)
            
            # Basic content quality check
            if len(clean_text.strip()) < 30:
                continue

            part_path = f"{base_path}/{part_slug}" if part_slug else base_path
            section_id = f"GOV:{base_slug}/{part_slug}" if part_slug else f"GOV:{base_slug}"

            parsed_docs.append({
                "manual_slug": "gov-uk-guidance",
                "manual_title": "GOV.UK Guidance",
                "section_id": section_id,
                "title": f"{title} - {part_title}" if part_title else title,
                "text": clean_text,
                "tax_type": tax_type,
                "related_pages": [],
                "breadcrumb": [],
                "gov_url": f"https://www.gov.uk{part_path}",
                "updated_at": updated_at,
                "audience_level": "mainstream",
                "source_type": "gov_uk_guide"
            })
    else:
        # Single-body page (answer, detailed_guide)
        body_html = details.get("body", "")
        if not body_html:
            return []

        clean_text = strip_html(body_html)
        if len(clean_text.strip()) < 30:
            return []

        parsed_docs.append({
            "manual_slug": "gov-uk-guidance",
            "manual_title": "GOV.UK Guidance",
            "section_id": f"GOV:{base_slug}",
            "title": title,
            "text": clean_text,
            "tax_type": tax_type,
            "related_pages": [],
            "breadcrumb": [],
            "gov_url": f"https://www.gov.uk{base_path}",
            "updated_at": updated_at,
            "audience_level": "mainstream",
            "source_type": "gov_uk_guide"
        })

    return parsed_docs

def parse_all(discovered_docs: list[dict]) -> list[dict]:
    """Parse all downloaded mainstream documents."""
    parsed = []

    # Parallel parsing
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures = []
        for doc in discovered_docs:
            slug = doc["slug"]
            cache_path = os.path.join(RAW_JSON_DIR, f"{slug}.json")
            futures.append(executor.submit(parse_mainstream_file, cache_path, doc))

        for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Parsing Mainstream JSONs", unit="file"):
            docs = future.result()
            if docs:
                parsed.extend(docs)

    print(f"Parsed {len(parsed)} mainstream documents/parts.")
    return parsed

if __name__ == "__main__":
    from discover_mainstream import DISCOVERY_CACHE
    if os.path.exists(DISCOVERY_CACHE):
        with open(DISCOVERY_CACHE, "r") as f:
            docs = json.load(f)
        parse_all(docs)
    else:
        print("Run discover_mainstream.py first.")
