#!/usr/bin/env python3
"""
espresso·ai — SEC EDGAR Corporate Filing AI Signal Collector
Queries SEC EDGAR EFTS (free full-text search) and company submissions
for AI-related corporate filings. Classifies against Scale Levers and
outputs signal records to research_db/raw/ in JSONL format.

Usage:
    python .claude/scripts/collect_edgar_signals.py --cadence weekly [--days-back 7] [--dry-run] [--test]
"""

import json
import uuid
import hashlib
import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

# ─── Configuration ───────────────────────────────────────────────────────────

EDGAR_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
AGENT_ID = "edgar-filing-collector"
SCHEMA_VERSION = "1.0"
SOURCE_NAME = "earnings_call"
USER_AGENT = "espresso-ai/1.0 (contact@espresso-ai.com)"
REQUEST_DELAY = 0.15  # 150ms between requests (well under SEC 10 req/sec limit)

# ─── EFTS Search Terms ─────────────────────────────────────────────────────

EDGAR_SEARCH_TERMS = [
    "artificial intelligence",
    "machine learning",
    "large language model",
    "generative AI",
    "AI strategy",
    "AI capital expenditure",
    "AI infrastructure",
    "AI deployment",
]

TARGET_FORMS = "10-K,10-Q,8-K,DEF 14A"

# ─── Curated Companies ──────────────────────────────────────────────────────

CURATED_COMPANIES = [
    {"name": "Microsoft", "ticker": "MSFT", "cik": "0000789019", "lever_hint": "CAPITAL"},
    {"name": "Alphabet", "ticker": "GOOGL", "cik": "0001652044", "lever_hint": "CAPITAL"},
    {"name": "Amazon", "ticker": "AMZN", "cik": "0001018724", "lever_hint": "CAPITAL"},
    {"name": "Meta Platforms", "ticker": "META", "cik": "0001326801", "lever_hint": "CAPITAL"},
    {"name": "NVIDIA", "ticker": "NVDA", "cik": "0001045810", "lever_hint": "COMPUTE"},
    {"name": "Apple", "ticker": "AAPL", "cik": "0000320193", "lever_hint": "CAPITAL"},
    {"name": "Salesforce", "ticker": "CRM", "cik": "0001108524", "lever_hint": "INDUSTRY"},
    {"name": "Palantir", "ticker": "PLTR", "cik": "0001321655", "lever_hint": "INDUSTRY"},
    {"name": "AMD", "ticker": "AMD", "cik": "0000002488", "lever_hint": "COMPUTE"},
    {"name": "Intel", "ticker": "INTC", "cik": "0000050863", "lever_hint": "COMPUTE"},
    {"name": "ServiceNow", "ticker": "NOW", "cik": "0001373715", "lever_hint": "INDUSTRY"},
    {"name": "Snowflake", "ticker": "SNOW", "cik": "0001640147", "lever_hint": "INDUSTRY"},
    {"name": "Broadcom", "ticker": "AVGO", "cik": "0001649338", "lever_hint": "COMPUTE"},
    {"name": "Oracle", "ticker": "ORCL", "cik": "0001341439", "lever_hint": "CAPITAL"},
    {"name": "Tesla", "ticker": "TSLA", "cik": "0001318605", "lever_hint": "INDUSTRY"},
    {"name": "C3.ai", "ticker": "AI", "cik": "0001577526", "lever_hint": "INDUSTRY"},
    {"name": "UiPath", "ticker": "PATH", "cik": "0001839132", "lever_hint": "INDUSTRY"},
]

# Build CIK lookup for matching EFTS results to curated companies
CIK_LOOKUP = {c["cik"]: c for c in CURATED_COMPANIES}

# ─── AI-Relevance Scoring ──────────────────────────────────────────────────

AI_STRONG_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning",
    "large language model", "generative ai", "generative artificial intelligence",
    "foundation model", "neural network", "natural language processing",
    "computer vision", "ai strategy", "ai investment", "ai infrastructure",
    "ai capital expenditure", "ai capex", "ai spending", "ai deployment",
    "ai platform", "ai-powered", "ai-enabled", "ai-driven",
    "ai governance", "ai risk", "ai safety", "ai regulation",
    "ai revenue", "ai workload",
    "copilot", "gpu cluster", "ai data center", "inference cost",
    "ai acquisition", "ai partnership", "ai talent",
]

AI_MODERATE_KEYWORDS = [
    "algorithm", "automation", "predictive model", "data-driven",
    "cloud compute", "semiconductor", "gpu", "accelerator",
    "digital transformation", "intelligent automation",
    "autonomous", "training data", "model training", "inference",
    "research and development", "technology investment",
]

AI_NEGATIVE_KEYWORDS = [
    "artificial flavoring", "artificial sweetener", "artificial turf",
    "machine shop", "machine tool", "mining machine",
    "learning center", "learning disability",
]

AI_RELEVANCE_THRESHOLD = 3


def score_ai_relevance(title: str, description: str) -> int:
    """Score how likely an SEC filing discusses AI."""
    text = (title + " " + description).lower()
    score = 0
    for kw in AI_STRONG_KEYWORDS:
        if kw in text:
            score += 3
    for kw in AI_MODERATE_KEYWORDS:
        if kw in text:
            score += 1
    for kw in AI_NEGATIVE_KEYWORDS:
        if kw in text:
            score -= 2
    return score


# ─── Helper Functions ────────────────────────────────────────────────────────


def generate_signal_id(source_name: str, timestamp: str) -> str:
    """Generate unique signal ID per schema."""
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    date_part = dt.strftime("%Y%m%d")
    time_part = dt.strftime("%H%M%S")
    hash_part = hashlib.md5(f"{timestamp}{uuid.uuid4()}".encode()).hexdigest()[:5]
    return f"{date_part}-{source_name}-{time_part}-{hash_part}"


def get_date_range(cadence: str, days_back: int = None):
    """Return start/end dates for the query window."""
    end = datetime.now(timezone.utc)
    if days_back is not None:
        start = end - timedelta(days=days_back)
    elif cadence == "daily":
        start = end - timedelta(days=2)
    elif cadence == "weekly":
        start = end - timedelta(days=7)
    elif cadence == "monthly":
        start = end - timedelta(days=31)
    elif cadence == "quarterly":
        start = end - timedelta(days=92)
    elif cadence == "annual":
        start = end - timedelta(days=366)
    else:
        start = end - timedelta(days=7)
    return start, end


def get_date_range_prefix(start: datetime, end: datetime) -> str:
    """Get date range string for file naming."""
    return f"{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}"


def edgar_request(url: str, params: dict = None) -> dict | None:
    """Make an SEC EDGAR API request with required User-Agent."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        time.sleep(REQUEST_DELAY)
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"    [ERROR] EDGAR request failed: {e}")
        return None


# ─── Classification ─────────────────────────────────────────────────────────

SUB_VAR_KEYWORDS = {
    "CAPITAL": {
        "hyperscaler_capex_and_utilization": [
            "capital expenditure", "capex", "data center investment", "infrastructure spend",
            "gpu cluster", "ai infrastructure", "cloud capacity", "utilization rate",
            "ai workload", "compute capacity",
        ],
        "corporate_rd_reallocation": [
            "r&d", "research and development", "r&d spending", "technology investment",
            "ai budget", "ai spending", "digital transformation budget",
            "technology budget", "innovation investment",
        ],
        "venture_funding_discipline": [
            "venture", "series a", "series b", "funding round", "startup investment",
            "strategic investment", "corporate venture", "seed round",
        ],
        "capital_exit_velocity": [
            "acquisition", "merger", "ipo", "acqui-hire", "strategic acquisition",
            "m&a", "divestiture", "exit", "liquidity event",
        ],
        "roi_signal_clarity": [
            "return on investment", "roi", "payback period", "productivity gain",
            "cost savings", "margin improvement", "revenue impact",
            "ai revenue", "customer retention",
        ],
        "compute_market_economics": [
            "inference cost", "cost per token", "compute cost", "pricing",
            "gross margin", "ai services margin", "unit economics",
        ],
    },
    "COMPUTE": {
        "manufacturing_capacity": [
            "chip", "semiconductor", "fab", "wafer", "manufacturing",
            "supply chain", "lead time",
        ],
        "cost_per_flop": [
            "inference cost", "cost per flop", "compute efficiency",
            "gpu pricing", "cloud pricing",
        ],
        "data_center_buildout": [
            "data center", "rack capacity", "cooling", "power capacity",
            "construction", "hyperscale",
        ],
        "custom_silicon_adoption": [
            "custom chip", "custom silicon", "tpu", "trainium",
            "asic", "accelerator",
        ],
    },
    "INDUSTRY": {
        "production_deployment_rate": [
            "production deployment", "enterprise adoption", "at scale",
            "production ai", "deployed", "rollout",
        ],
        "cross_sector_diffusion": [
            "healthcare", "financial services", "manufacturing",
            "retail", "logistics", "energy sector",
        ],
        "enterprise_tool_maturity": [
            "copilot", "ai assistant", "ai platform", "saas ai",
            "enterprise ai", "ai product",
        ],
    },
    "GOV": {
        "regulatory_framework_clarity": [
            "regulatory compliance", "ai regulation", "ai governance",
            "sec guidance", "disclosure requirement",
        ],
    },
}

SECONDARY_LEVER_KEYWORDS = {
    "COMPUTE": ["chip", "semiconductor", "gpu", "compute", "data center", "hardware",
                 "supply chain", "manufacturing"],
    "ENERGY": ["energy", "power", "grid", "carbon", "environmental", "sustainability",
               "emissions", "renewable"],
    "SOCIETY": ["workforce", "education", "training", "employment", "labor", "worker",
                "consumer", "privacy", "bias"],
    "INDUSTRY": ["deployment", "enterprise", "production", "healthcare", "financial",
                  "manufacturing", "sector"],
    "GOV": ["regulation", "compliance", "governance", "audit", "oversight"],
}

POSITIVE_INDICATORS = [
    "increased", "growth", "expanded", "accelerat", "invested",
    "acquired", "launched", "deployed", "committed", "exceeded",
    "improved", "strong demand", "strategic priority",
]

NEGATIVE_INDICATORS = [
    "decreased", "declined", "reduced", "cut", "delayed",
    "impaired", "write-down", "restructur", "downsiz",
    "underperform", "below expectations", "concern",
]


def classify_signal(title: str, description: str, lever_hint: str = "CAPITAL") -> dict:
    """Classify an EDGAR filing signal."""
    text = (title + " " + description).lower()

    # Score each lever's sub-variables
    best_lever = "CAPITAL"
    best_sub = "corporate_rd_reallocation"
    best_score = 0

    for lever, sub_vars in SUB_VAR_KEYWORDS.items():
        for sub_var, keywords in sub_vars.items():
            score = sum(1 for kw in keywords if kw in text)
            # lever_hint gives a +1 tiebreaker
            if lever == lever_hint:
                score += 1
            if score > best_score:
                best_score = score
                best_lever = lever
                best_sub = sub_var

    # Direction
    pos_score = sum(1 for p in POSITIVE_INDICATORS if p in text)
    neg_score = sum(1 for n in NEGATIVE_INDICATORS if n in text)

    if pos_score > neg_score + 1:
        direction = "+"
    elif neg_score > pos_score + 1:
        direction = "-"
    elif pos_score > 0 and neg_score > 0:
        direction = "?"
    else:
        direction = "~"

    confidence = "high" if best_score >= 4 else "medium" if best_score >= 2 else "low"

    # Detect secondary lever
    secondary = None
    secondary_score = 0
    for lever, keywords in SECONDARY_LEVER_KEYWORDS.items():
        if lever == best_lever:
            continue
        score = sum(1 for kw in keywords if kw in text)
        if score > secondary_score and score >= 2:
            secondary_score = score
            secondary = lever

    return {
        "lever_primary": best_lever,
        "lever_secondary": secondary,
        "sub_variable": best_sub,
        "direction": direction,
        "confidence": confidence,
    }


# ─── Phase 1: EFTS Full-Text Search ─────────────────────────────────────────


def collect_efts_filings(start: datetime, end: datetime) -> list[dict]:
    """Query EFTS full-text search for AI mentions in SEC filings."""
    entries = []
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    for term in EDGAR_SEARCH_TERMS:
        print(f'  Searching EFTS: "{term}"...')

        params = {
            "q": f'"{term}"',
            "dateRange": "custom",
            "startdt": start_str,
            "enddt": end_str,
            "forms": TARGET_FORMS,
        }
        data = edgar_request(EDGAR_EFTS_URL, params)
        if not data:
            continue

        hits = data.get("hits", {}).get("hits", [])
        total = data.get("hits", {}).get("total", {}).get("value", 0)
        print(f"    → {len(hits)} hits (of {total} total)")

        filtered = 0
        for hit in hits:
            source = hit.get("_source", {})
            display_names = source.get("display_names", [])
            form = source.get("form", "")
            file_date = source.get("file_date", "")
            adsh = source.get("adsh", "")
            file_description = source.get("file_description") or ""
            ciks = source.get("ciks", [])

            company_name = display_names[0] if display_names else "Unknown"
            # Extract ticker from display_name like "NVIDIA CORP  (NVDA)  (CIK ...)"
            ticker = ""
            if "(" in company_name:
                parts = company_name.split("(")
                if len(parts) >= 2:
                    ticker = parts[1].strip().rstrip(")")
                # Clean company name
                company_name = parts[0].strip()

            cik = ciks[0] if ciks else ""

            # Look up curated company info
            curated = CIK_LOOKUP.get(cik, {})
            is_curated = bool(curated)
            lever_hint = curated.get("lever_hint", "CAPITAL")

            title = f"{company_name} ({ticker}) {form}: {file_description}"[:200] if ticker else f"{company_name} {form}: {file_description}"[:200]

            # AI-relevance filter: score the file_description alone (not company name)
            # to avoid false positives from companies named "AI Something Inc."
            # Curated companies always pass — they're curated precisely because they're AI-relevant.
            if not is_curated:
                relevance = score_ai_relevance(file_description, "")
                if relevance < AI_RELEVANCE_THRESHOLD:
                    filtered += 1
                    continue

            summary = f"{company_name} filed {form} on {file_date}. {file_description}"

            # Build filing URL
            adsh_clean = adsh.replace("-", "")
            cik_num = cik.lstrip("0") if cik else ""
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{adsh_clean}/" if cik_num and adsh_clean else ""

            entries.append({
                "source": "efts_search",
                "title": title,
                "summary": summary,
                "source_url": filing_url,
                "publication_date": file_date,
                "form_type": form,
                "company_name": curated.get("name", company_name),
                "ticker": curated.get("ticker", ticker),
                "cik": cik,
                "accession_number": adsh,
                "lever_hint": lever_hint,
                "ai_relevance_score": relevance,
                "confidence": "high" if cik in CIK_LOOKUP else "medium",
            })

        if filtered:
            print(f"    ✗ {filtered} dropped (not AI-relevant)")

    return entries


# ─── Phase 2: Curated Company Filings ────────────────────────────────────────


def collect_company_filings(start: datetime, end: datetime) -> list[dict]:
    """Check curated companies for recent filings."""
    entries = []
    target_forms = set(f.strip() for f in TARGET_FORMS.split(","))

    for i, company in enumerate(CURATED_COMPANIES, 1):
        print(f"  [{i}/{len(CURATED_COMPANIES)}] {company['name']} ({company['ticker']})...")

        url = EDGAR_SUBMISSIONS_URL.format(cik=company["cik"])
        data = edgar_request(url)
        if not data:
            continue

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        doc_descriptions = recent.get("primaryDocDescription", [])
        primary_docs = recent.get("primaryDocument", [])

        in_range = 0
        for j, form_type in enumerate(forms):
            if form_type not in target_forms:
                continue
            filing_date = dates[j] if j < len(dates) else ""
            if not filing_date:
                continue

            try:
                fd = datetime.strptime(filing_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if fd < start or fd > end:
                    continue
            except ValueError:
                continue

            accession = accessions[j] if j < len(accessions) else ""
            doc_desc = doc_descriptions[j] if j < len(doc_descriptions) else ""
            primary_doc = primary_docs[j] if j < len(primary_docs) else ""

            accession_clean = accession.replace("-", "")
            cik_num = company["cik"].lstrip("0")
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{accession_clean}/{primary_doc}" if primary_doc else f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{accession_clean}/"

            title = f"{company['name']} ({company['ticker']}) {form_type}: {doc_desc}"[:200]
            summary = f"{company['name']} filed {form_type} on {filing_date}. {doc_desc}"

            entries.append({
                "source": "company_submissions",
                "title": title,
                "summary": summary,
                "source_url": filing_url,
                "publication_date": filing_date,
                "form_type": form_type,
                "company_name": company["name"],
                "ticker": company["ticker"],
                "cik": company["cik"],
                "accession_number": accession,
                "lever_hint": company["lever_hint"],
                "ai_relevance_score": None,  # AI content inferred, not verified
                "confidence": "medium",
            })
            in_range += 1

        if in_range > 0:
            print(f"    → {in_range} filing(s) in date range")

    return entries


# ─── Signal Record Builder ──────────────────────────────────────────────────


def entry_to_signal_record(entry: dict, cadence: str,
                            pipeline_run_id: str, batch_id: str) -> dict:
    """Convert an EDGAR entry into a schema-compliant signal record."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    title = entry.get("title", "Untitled")
    summary = entry.get("summary", "")
    lever_hint = entry.get("lever_hint", "CAPITAL")

    classification = classify_signal(title, summary, lever_hint)

    # Tags
    tags = [
        f"filing_type:{entry.get('form_type', 'unknown')}",
        f"source_api:{entry.get('source', 'unknown')}",
    ]
    if entry.get("ticker"):
        tags.append(f"ticker:{entry['ticker']}")
    if entry.get("company_name"):
        tags.append(f"company:{entry['company_name']}")
    if entry.get("cik"):
        tags.append(f"cik:{entry['cik']}")
    if entry.get("accession_number"):
        tags.append(f"accession:{entry['accession_number']}")

    # Key facts
    key_facts = [
        f"Form type: {entry.get('form_type', '')}",
        f"Company: {entry.get('company_name', '')} ({entry.get('ticker', '')})",
        f"Filing date: {entry.get('publication_date', '')}",
    ]

    # Reporting period inference
    reporting_period = None
    form = entry.get("form_type", "")
    pub_date = entry.get("publication_date", "")
    if form == "10-K" and pub_date:
        try:
            fd = datetime.strptime(pub_date, "%Y-%m-%d")
            reporting_period = f"FY {fd.year - 1}" if fd.month <= 3 else f"FY {fd.year}"
        except ValueError:
            pass
    elif form == "10-Q" and pub_date:
        try:
            fd = datetime.strptime(pub_date, "%Y-%m-%d")
            q = (fd.month - 1) // 3
            reporting_period = f"Q{q} {fd.year}" if q > 0 else f"Q4 {fd.year - 1}"
        except ValueError:
            pass

    # Quality flags
    quality_flags = []
    if entry.get("source") == "company_submissions":
        quality_flags.append("ai_content_inferred")
    if not entry.get("source_url"):
        quality_flags.append("missing_url")

    return {
        "signal_id": generate_signal_id(SOURCE_NAME, now),
        "source_name": SOURCE_NAME,
        "source_url": entry.get("source_url", ""),
        "fetch_timestamp": now,
        "agent_id": AGENT_ID,
        "cadence": cadence,
        "pipeline_run_id": pipeline_run_id,
        "collection_batch_id": batch_id,

        "lever_primary": classification["lever_primary"],
        "lever_secondary": classification.get("lever_secondary"),
        "direction": classification["direction"],
        "sub_variable": classification["sub_variable"],
        "confidence": entry.get("confidence", classification["confidence"]),

        "title": title[:200],
        "summary": summary[:500] if summary else title[:200],
        "key_facts": key_facts[:5],
        "raw_content": summary[:2000] if summary else None,

        "publication_date": pub_date,
        "reporting_period": reporting_period,

        "signal_strength": None,
        "cross_lever_interactions": [],
        "novelty_flag": None,
        "countervailing_signals": [],
        "synthesis_notes": None,
        "is_duplicate": False,
        "duplicate_of": None,

        "in_scope": True,
        "data_quality_flags": quality_flags,
        "tags": tags,
        "schema_version": SCHEMA_VERSION,
    }


# ─── Deduplication ──────────────────────────────────────────────────────────


def deduplicate_entries(entries: list[dict]) -> tuple[list[dict], int]:
    """Remove duplicates by accession number, URL, and title."""
    seen_accessions = set()
    seen_urls = set()
    seen_titles = set()
    unique = []

    for entry in entries:
        acc = entry.get("accession_number", "")
        if acc and acc in seen_accessions:
            continue

        url = entry.get("source_url", "").rstrip("/").lower()
        if url and url in seen_urls:
            continue

        title_key = entry.get("title", "").lower().strip()
        if title_key and title_key in seen_titles:
            continue

        if acc:
            seen_accessions.add(acc)
        if url:
            seen_urls.add(url)
        if title_key:
            seen_titles.add(title_key)
        unique.append(entry)

    return unique, len(entries) - len(unique)


# ─── Validation ─────────────────────────────────────────────────────────────


def validate_and_flag(record: dict, date_start: datetime, date_end: datetime) -> dict:
    """Add quality flags based on URL and date checks."""
    flags = list(record.get("data_quality_flags", []))

    url = record.get("source_url", "")
    if not url:
        if "missing_url" not in flags:
            flags.append("missing_url")

    pub_date = record.get("publication_date", "")
    if pub_date:
        try:
            pd = datetime.strptime(pub_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            buffer = timedelta(days=2)
            if pd < (date_start - buffer) or pd > (date_end + buffer):
                flags.append("out_of_date_range")
        except ValueError:
            flags.append("invalid_date_format")

    record["data_quality_flags"] = flags
    return record


# ─── Main Pipeline ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="espresso·ai SEC EDGAR AI Signal Collector")
    parser.add_argument("--cadence", default="weekly",
                        choices=["daily", "weekly", "monthly", "quarterly", "annual"])
    parser.add_argument("--days-back", type=int, default=None,
                        help="Override: look back N days (default: auto from cadence)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print results without writing to disk")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: EFTS search only (skip company submissions)")
    args = parser.parse_args()

    cadence = args.cadence
    now = datetime.now(timezone.utc)
    pipeline_run_id = f"{now.strftime('%Y-%m-%d')}_{cadence}_{uuid.uuid4().hex[:8]}"
    batch_id = f"batch_{now.strftime('%Y%m%d_%H%M')}"
    start_date, end_date = get_date_range(cadence, args.days_back)

    print("=" * 70)
    print("espresso·ai — SEC EDGAR AI Signal Collector")
    print("=" * 70)
    print(f"Pipeline run:      {pipeline_run_id}")
    print(f"Batch:             {batch_id}")
    print(f"Cadence:           {cadence}")
    print(f"Date range:        {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}")
    print(f"Source:            SEC EDGAR EFTS + Company Submissions (free, no auth)")
    print(f"Target forms:      {TARGET_FORMS}")
    print(f"Curated companies: {len(CURATED_COMPANIES)}")
    print("=" * 70)

    all_entries = []

    # ── Phase 1: EFTS full-text search ──
    print(f"\n{'─' * 40}")
    print("Phase 1: EFTS Full-Text Search")
    print(f"{'─' * 40}")
    efts_entries = collect_efts_filings(start_date, end_date)
    print(f"\nPhase 1 total: {len(efts_entries)} AI-relevant filings")
    all_entries.extend(efts_entries)

    # ── Phase 2: Curated company filings ──
    if not args.test:
        print(f"\n{'─' * 40}")
        print("Phase 2: Curated Company Filings")
        print(f"{'─' * 40}")
        company_entries = collect_company_filings(start_date, end_date)
        print(f"\nPhase 2 total: {len(company_entries)} filings from curated companies")
        all_entries.extend(company_entries)
    else:
        print("\n[TEST MODE] Skipping company submissions.")

    # Deduplicate
    pre_dedup = len(all_entries)
    all_entries, dupes_removed = deduplicate_entries(all_entries)

    print(f"\n{'=' * 70}")
    print(f"Total collected:    {pre_dedup}")
    print(f"Duplicates removed: {dupes_removed}")
    print(f"Unique signals:     {len(all_entries)}")

    if not all_entries:
        print("\nNo AI-related SEC filings found in the target date range.")
        print("Suggestions:")
        print("  - Try a longer cadence or increase --days-back")
        print("  - 10-K/10-Q filings cluster around earnings season dates")
        return

    # Convert to signal records
    signal_records = []
    for entry in all_entries:
        record = entry_to_signal_record(entry, cadence, pipeline_run_id, batch_id)
        record = validate_and_flag(record, start_date, end_date)
        signal_records.append(record)

    # Metrics
    form_type_counts = {}
    lever_counts = {}
    company_counts = {}
    direction_counts = {}
    for entry in all_entries:
        ft = entry.get("form_type", "unknown")
        form_type_counts[ft] = form_type_counts.get(ft, 0) + 1
        cn = entry.get("company_name", "unknown")
        company_counts[cn] = company_counts.get(cn, 0) + 1

    for rec in signal_records:
        lp = rec["lever_primary"]
        lever_counts[lp] = lever_counts.get(lp, 0) + 1
        d = rec["direction"]
        direction_counts[d] = direction_counts.get(d, 0) + 1

    def count_flag(flag_name):
        return sum(1 for s in signal_records if flag_name in s.get("data_quality_flags", []))

    print(f"\nFiling Type Distribution:")
    for ft, count in sorted(form_type_counts.items(), key=lambda x: -x[1]):
        print(f"  {ft:15s}  {count:3d}")

    print(f"\nLever Distribution:")
    for lp, count in sorted(lever_counts.items(), key=lambda x: -x[1]):
        print(f"  {lp:15s}  {count:3d}")

    print(f"\nTop Companies:")
    for cn, count in sorted(company_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {cn:30s}  {count:3d}")

    print(f"\nDirection: + {direction_counts.get('+', 0)} | - {direction_counts.get('-', 0)} | ~ {direction_counts.get('~', 0)} | ? {direction_counts.get('?', 0)}")
    print(f"Missing URLs:        {count_flag('missing_url')}")
    print(f"AI content inferred: {count_flag('ai_content_inferred')}")
    print(f"Out-of-date:         {count_flag('out_of_date_range')}")

    # Write JSONL
    base_dir = Path(__file__).resolve().parent.parent.parent / "research_db" / "raw"
    base_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = get_date_range_prefix(start_date, end_date)
    output_file = base_dir / f"{date_prefix}_edgar_{cadence}_signals.jsonl"

    if args.dry_run:
        print(f"\n[DRY RUN] Would write {len(signal_records)} records to {output_file}")
        for rec in signal_records[:5]:
            print(f"\n  Title: {rec['title'][:80]}")
            print(f"  Lever: {rec['lever_primary']} | Direction: {rec['direction']} | Sub: {rec['sub_variable']}")
            print(f"  URL:   {rec['source_url'][:80]}")
            tags = [t for t in rec['tags'] if t.startswith('filing_type:') or t.startswith('ticker:')]
            print(f"  Tags:  {', '.join(tags)}")
    else:
        with open(output_file, "a", encoding="utf-8") as f:
            for record in signal_records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"\n✓ Wrote {len(signal_records)} signal records to:")
        print(f"  {output_file}")

    # Write pipeline log
    log = {
        "pipeline_run_id": pipeline_run_id,
        "collection_batch_id": batch_id,
        "cadence": cadence,
        "source": "sec_edgar",
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date_range": {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        },
        "test_mode": args.test,
        "total_results_raw": pre_dedup,
        "duplicates_removed": dupes_removed,
        "records_written": len(signal_records),
        "form_type_distribution": form_type_counts,
        "lever_distribution": lever_counts,
        "direction_distribution": direction_counts,
        "company_distribution": company_counts,
        "output_file": str(output_file),
        "quality_metrics": {
            "missing_url_count": count_flag("missing_url"),
            "ai_content_inferred_count": count_flag("ai_content_inferred"),
            "out_of_date_count": count_flag("out_of_date_range"),
        },
    }

    log_file = base_dir / f"{date_prefix}_edgar_pipeline_log.json"
    if not args.dry_run:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
        print(f"✓ Pipeline log: {log_file}")

    # Print signal sample
    print(f"\n{'=' * 70}")
    print("SAMPLE SIGNALS:")
    print(f"{'=' * 70}")
    for i, rec in enumerate(signal_records[:10], 1):
        d = rec["direction"]
        lever = rec["lever_primary"]
        sub = rec["sub_variable"]
        title = rec["title"][:55]
        form = next((t.split(":")[1] for t in rec.get("tags", []) if t.startswith("filing_type:")), "?")
        print(f"  {i:2d}. [{lever} {d}] {form:8s} | {sub:30s} | {title}")

    if len(signal_records) > 10:
        print(f"  ... and {len(signal_records) - 10} more")

    print(f"\n{'=' * 70}")
    print("Done. (SEC EDGAR — $0.00)")


if __name__ == "__main__":
    main()
