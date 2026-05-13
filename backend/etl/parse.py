"""
Parse: Extracts structured text, metadata, and cross-references from the raw JSON cache.
Strips HTML from the body field.
"""

import json
import os
import re
import concurrent.futures

from bs4 import BeautifulSoup
from tqdm import tqdm

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
RAW_JSON_DIR = os.path.join(DATA_DIR, "raw_json")

# HMRC cross-reference regex (e.g. VIT13500, CG12345, PE24300, IHTM04030)
REF_REGEX = re.compile(r'\b([A-Z]{2,6}\d{4,6})\b')


def strip_html(html: str) -> str:
    """Strip HTML tags and return clean text, preserving block structure and lists."""
    if not html:
        return ""
    
    # Replace HMRC's faux MS Word bullets with standard hyphens
    html = html.replace('\u00b7', '-')
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Convert <br> to newlines
    for br in soup.find_all("br"):
        br.replace_with("\n")
        
    # Explicitly mark bullet points for true <li> tags
    for li in soup.find_all("li"):
        li.insert(0, "- ")
        
    # Add block separators after block-level elements
    for tag in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"]):
        tag.insert_after("\n\n")
        
    # Extract text with space separator to keep inline elements together
    text = soup.get_text(separator=" ")
    
    # Clean up whitespace: replace multiple spaces/tabs/nbsps with single space
    text = re.sub(r'[ \t\xa0]+', ' ', text)
    
    # Split by block separators and clean each block
    blocks = text.split("\n\n")
    clean_blocks = []
    for block in blocks:
        # Join any intra-block newlines into spaces (fixes MS Word wrapping)
        block = block.replace("\n", " ").strip()
        if block:
            clean_blocks.append(block)
            
    text = "\n\n".join(clean_blocks)
    
    # Ensure bullets have a clean space after them (e.g. "-company" -> "- company")
    text = re.sub(r'^-\s*', '- ', text, flags=re.MULTILINE)
    
    return text


def parse_section(manual_slug: str, section_id: str) -> dict | None:
    """Parse a single cached JSON file into a structured document."""
    cache_path = os.path.join(RAW_JSON_DIR, manual_slug, f"{section_id}.json")
    if not os.path.exists(cache_path):
        return None

    try:
        with open(cache_path, "r") as f:
            data = json.load(f)
    except Exception:
        return None

    details = data.get("details", {})
    body_html = details.get("body", "")
    
    if not body_html:
        return None

    clean_text = strip_html(body_html)

    # ── Content quality filter ──
    # Skip TOC stubs, boilerplate-only pages, and near-empty sections.
    # These just contain "Contents", email addresses, or single cross-references
    # and pollute search results with noise.
    _lower = clean_text.lower().strip()
    if (
        len(clean_text.strip()) < 50
        or _lower in ("contents",)
        or _lower.startswith("this section contains the following")
        or _lower.startswith("hmrcmanualsteam@hmrc.gov.uk")
    ):
        return None
    
    # Extract cross-references
    related_pages = list(set(REF_REGEX.findall(clean_text)))
    
    # Ensure the section itself isn't in related pages
    if section_id in related_pages:
        related_pages.remove(section_id)

    # Extract breadcrumbs
    breadcrumbs = [b.get("section_id") for b in details.get("breadcrumbs", []) if b.get("section_id")]

    # Derive tax type from manual slug prefix (heuristic)
    tax_type = "Unknown"
    prefix = manual_slug.split("-")[0].upper()
    if prefix in ["VAT", "CG", "PE", "IHT", "CT", "PAYE"]:
        tax_type = prefix

    return {
        "manual_slug": manual_slug,
        "manual_title": data.get("title", "").split(" - ")[0], # Fallback title extraction
        "section_id": section_id,
        "title": data.get("title", ""),
        "text": clean_text,
        "tax_type": tax_type,
        "related_pages": related_pages,
        "breadcrumb": breadcrumbs,
        "gov_url": f"https://www.gov.uk{data.get('base_path', '')}",
        "updated_at": data.get("public_updated_at", ""),
    }


def parse_all(discovered_sections: list[dict]) -> list[dict]:
    """Parse all downloaded sections."""
    parsed = []
    
    # Fix manual_title fallback by keeping a map of slug -> title
    manual_titles = {s["manual_slug"]: s["manual_title"] for s in discovered_sections}

    # Multithread the file reading and parsing to bypass Windows sequential I/O bottlenecks
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures = [
            executor.submit(parse_section, section["manual_slug"], section["section_id"])
            for section in discovered_sections
        ]
        
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Parsing JSON files", unit="file"):
            doc = future.result()
            if doc:
                doc["manual_title"] = manual_titles.get(doc["manual_slug"], doc["manual_title"])
                parsed.append(doc)

    print(f"Parsed {len(parsed)} documents.")
    return parsed
