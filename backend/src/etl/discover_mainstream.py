"""
Discovery for GOV.UK Mainstream Guidance:
Uses GOV.UK's own browse-page taxonomy to find tax-related guides, answers,
and detailed_guides. This avoids keyword-search noise (vehicle tax, driving
tests, visa pages, etc.) by restricting results to GOV.UK's curated
mainstream browse categories that are actually about taxation, PAYE, NI,
and closely related topics.

The GOV.UK Search API supports `filter_mainstream_browse_pages[]` which
filters results to only pages tagged to specific browse categories.
We use this with the set of browse page paths listed below.
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
DISCOVERY_CACHE = os.path.join(DATA_DIR, "mainstream_discovery_cache.json")
SEARCH_API = "https://www.gov.uk/api/search.json"

# --- Taxonomy-based filtering ---
# These are GOV.UK mainstream browse page paths. Each one is a curated
# category that GOV.UK editors tag content into.  Using these as filters
# means we get exactly the pages GOV.UK considers to belong to each topic,
# with zero keyword-matching noise.
#
# Source: https://www.gov.uk/api/content/browse/tax (and siblings)
#         Verified via GOV.UK Content API 2026-05.

BROWSE_PAGES = [
    # --- Core Tax ---
    "tax/income-tax",                    # ~46 guides: tax codes, rates, allowances
    "tax/self-assessment",               # ~23 guides: filing, payments, deadlines
    "tax/capital-gains",                 # ~17 guides: CGT on property, shares, assets
    "tax/inheritance-tax",               # ~14 guides: IHT thresholds, rules, probate
    "tax/national-insurance",            # ~19 guides: NI rates, credits, contributions
    "tax/vat",                           # ~33 guides: registration, returns, schemes
    "tax/dealing-with-hmrc",             # ~21 guides: contacting HMRC, penalties, appeals
    "tax/court-claims-debt-bankruptcy",  # ~27 guides: tax debts, CCJs, bankruptcy

    # --- Business Tax & Structure ---
    "business/business-tax-returns",      # ~36 guides: corporation tax, company accounts, PAYE for employers
    "business/start-your-business",       # ~16 guides: VAT registration, self-employed records, structure
    "business/sell-transfer-your-business", # ~10 guides: business asset relief, ownership transfers
    "business/professional-financial-services", # ~14 guides: partial exemption, money laundering rules

    # --- Employer / Payroll ---
    "employing-people/payroll",          # ~36 guides: PAYE, RTI, statutory payments

    # --- Pensions ---
    "working/state-pension",             # ~23 guides: state pension, deferral, NI credits, voluntary NI
    "working/workplace-personal-pensions", # ~13 guides: tax on pension, private contributions, death benefits

    # --- Your Pay & Wages ---
    "working/tax-minimum-wage",          # ~17 guides: Income tax introduction, minimum wage rates

    # --- Charity Tax Relief ---
    "business/running-charity",          # ~5 guides: Gift Aid, charities and tax, donations

    # --- Property Tax ---
    "housing-local-services/council-tax", # ~4 guides: council tax bands, appeals, arrears
    "housing-local-services/buying-owning-property", # ~22 guides: SDLT, tax on property sales, ISAs

    # --- Tax-adjacent (child benefit, tax credits, tax-free childcare) ---
    "childcare-parenting/financial-help-children",  # ~39 guides: child benefit, tax-free childcare, HICBC
]

# Document types we want (mainstream user-facing content only)
DOC_TYPES = ["guide", "answer", "detailed_guide"]

PAGE_SIZE = 100


async def _fetch_browse_page(
    session: aiohttp.ClientSession,
    browse_page: str,
) -> list[dict]:
    """Fetch all documents tagged to a single browse page, handling pagination."""
    results_list = []
    start = 0

    while True:
        params = {
            "filter_mainstream_browse_pages[]": browse_page,
            "count": PAGE_SIZE,
            "start": start,
            "fields": "title,link,description,public_timestamp,content_store_document_type",
        }
        # Add each doc type as a separate filter param
        for dt in DOC_TYPES:
            params.setdefault("filter_content_store_document_type[]", [])
            if isinstance(params["filter_content_store_document_type[]"], str):
                params["filter_content_store_document_type[]"] = [params["filter_content_store_document_type[]"]]
            params["filter_content_store_document_type[]"].append(dt)

        data = None
        for attempt in range(5):
            try:
                async with session.get(SEARCH_API, params=params) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    if resp.status != 200:
                        raise Exception(f"Search API returned {resp.status}")
                    data = await resp.json()
                break
            except Exception as e:
                if attempt == 4:
                    print(f"Failed to fetch browse page '{browse_page}' at start={start}: {e}")
                    return results_list
                await asyncio.sleep(2 ** attempt)

        if data is None:
            break

        results = data.get("results", [])
        if not results:
            break

        for r in results:
            link = r.get("link", "")
            if not link or not link.startswith("/"):
                continue

            doc_type = r.get("content_store_document_type", "")

            results_list.append({
                "slug": link.strip("/"),
                "title": r.get("title", ""),
                "description": r.get("description", ""),
                "link": link,
                "document_type": doc_type,
                "updated_at": r.get("public_timestamp", ""),
            })

        start += PAGE_SIZE
        if start >= data.get("total", 0):
            break

    return results_list


async def discover_all(force: bool = False) -> list[dict]:
    """Discover all mainstream tax documents using GOV.UK browse-page taxonomy."""
    os.makedirs(DATA_DIR, exist_ok=True)

    if not force and os.path.exists(DISCOVERY_CACHE):
        with open(DISCOVERY_CACHE, "r") as f:
            cached = json.load(f)
        print(f"Loaded {len(cached)} documents from mainstream discovery cache.")
        return cached

    all_docs = {}
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for browse_page in tqdm(BROWSE_PAGES, desc="Scanning GOV.UK browse pages", unit="category"):
            docs = await _fetch_browse_page(session, browse_page)
            for d in docs:
                # Deduplicate by link (a page can appear under multiple browse categories)
                all_docs[d["link"]] = d

    unique_docs = list(all_docs.values())
    print(f"Discovered {len(unique_docs)} unique mainstream tax documents across {len(BROWSE_PAGES)} browse categories.")

    with open(DISCOVERY_CACHE, "w") as f:
        json.dump(unique_docs, f, indent=2)
    print(f"Mainstream discovery cache saved to {DISCOVERY_CACHE}")
    return unique_docs


if __name__ == "__main__":
    asyncio.run(discover_all(force=True))
