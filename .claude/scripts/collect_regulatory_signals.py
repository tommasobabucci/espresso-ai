#!/usr/bin/env python3
"""
espresso·ai — Regulatory & Government Primary Source Collector
Queries the US Federal Register API (free, no auth) for AI-related documents.
Classifies against Scale Levers and outputs signal records to research_db/raw/ in JSONL format.

Usage:
    python .claude/scripts/collect_regulatory_signals.py --cadence weekly [--days-back 7] [--dry-run]
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

FEDERAL_REGISTER_API = "https://www.federalregister.gov/api/v1/documents.json"
AGENT_ID = "regulatory-primary-collector"
SCHEMA_VERSION = "1.0"
SOURCE_NAME = "regulatory_filing"

# ─── Federal Register Search Terms ─────────────────────────────────────────

FR_SEARCH_TERMS = [
    "artificial intelligence",
    "machine learning",
    "large language model",
    "automated decision making",
    "algorithmic accountability",
]

# ─── AI-Relevance Scoring ──────────────────────────────────────────────────
# Local keyword-based filter to drop false positives from broad FR searches.
# No API cost — runs entirely on title + abstract text.

# Strong AI signals (each hit = 3 points)
AI_STRONG_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning",
    "large language model", "generative ai", "generative artificial intelligence",
    "foundation model", "neural network", "natural language processing",
    "computer vision", "ai system", "ai model", "ai training",
    "ai safety", "ai risk", "ai governance", "ai regulation",
    "ai transparency", "ai accountability", "ai bias",
    "ai-generated", "ai-enabled", "ai-powered",
    "chatbot", "autonomous system", "automated decision system",
    "algorithmic accountability", "algorithmic bias", "algorithmic transparency",
    "frontier model", "open-source ai", "open source ai",
]

# Moderate AI signals (each hit = 1 point)
AI_MODERATE_KEYWORDS = [
    "algorithm", "automated decision", "automation", "predictive model",
    "data-driven", "training data", "synthetic data", "compute",
    "semiconductor", "gpu", "chip", "deepfake", "facial recognition",
    "surveillance", "robotics", "autonomous vehicle",
]

# Negative signals — topics that use AI keywords but aren't about AI policy
# (each hit = -2 points)
AI_NEGATIVE_KEYWORDS = [
    "marine mammal", "air pollutant", "hazardous waste", "emission standard",
    "truck bed", "mattress", "tire", "lumber", "steel import",
    "fish", "wildlife", "endangered species", "pesticide",
    "coal", "mining safety", "food additive", "drug approval",
    "broadcast", "radio frequency", "spectrum allocation",
]

AI_RELEVANCE_THRESHOLD = 3  # Minimum score to keep a document


def score_ai_relevance(title: str, abstract: str) -> int:
    """Score how likely a Federal Register document is about AI policy.
    Returns an integer score. Documents below AI_RELEVANCE_THRESHOLD are dropped."""
    text = (title + " " + abstract).lower()
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


# ─── Classification ─────────────────────────────────────────────────────────

SUB_VAR_KEYWORDS = {
    "GOV": {
        "regulatory_framework_clarity": ["regulation", "rule", "proposed rule", "final rule",
                                          "compliance", "liability", "copyright", "ai act",
                                          "executive order", "guidance", "standard", "framework"],
        "export_controls_and_chip_access": ["export control", "chip ban", "semiconductor restriction",
                                             "entity list", "commerce department", "bis", "itar"],
        "cross_border_data_and_model_mobility": ["data localization", "model weights", "cross-border",
                                                   "data sovereignty", "data transfer"],
        "alignment_and_safety_maturity": ["safety", "alignment", "red team", "testing",
                                           "evaluation", "risk assessment", "audit",
                                           "interpretability", "transparency"],
        "geopolitical_fragmentation_index": ["us-china", "geopolitical", "tech war", "decoupling",
                                              "ai sovereignty", "foreign policy", "sanctions"],
        "antitrust_and_market_structure": ["antitrust", "monopoly", "competition", "market concentration",
                                            "merger", "acquisition"],
        "institutional_trust": ["public trust", "government ai", "institutional adoption",
                                 "procurement", "federal agency"],
    },
}

# Secondary lever detection keywords
SECONDARY_LEVER_KEYWORDS = {
    "COMPUTE": ["chip", "semiconductor", "gpu", "compute", "data center", "hardware",
                 "supply chain", "manufacturing"],
    "ENERGY": ["energy", "power", "grid", "carbon", "environmental", "sustainability",
               "emissions", "renewable"],
    "SOCIETY": ["workforce", "education", "training", "employment", "labor", "worker",
                "consumer", "privacy", "bias", "discrimination"],
    "INDUSTRY": ["deployment", "enterprise", "production", "healthcare", "financial",
                  "manufacturing", "sector"],
    "CAPITAL": ["investment", "funding", "capex", "venture", "valuation"],
}

POSITIVE_INDICATORS = [
    "approved", "enacted", "established", "launched", "adopted",
    "framework", "standard", "guidance", "partnership", "agreement",
    "funded", "allocated", "support", "accelerat",
]
NEGATIVE_INDICATORS = [
    "ban", "restriction", "moratorium", "halt", "suspend",
    "penalty", "fine", "enforcement", "violation", "concern",
    "delay", "blocked", "prohibited", "revoked",
]


def classify_signal(title: str, summary: str) -> dict:
    """Classify a regulatory signal."""
    text = (title + " " + summary).lower()

    # Find best sub_variable within GOV lever
    best_sub = "regulatory_framework_clarity"  # default for regulatory docs
    best_score = 0

    for sub_var, keywords in SUB_VAR_KEYWORDS["GOV"].items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
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

    confidence = "high" if best_score >= 3 else "medium" if best_score >= 1 else "low"

    # Detect secondary lever
    secondary = None
    secondary_score = 0
    for lever, keywords in SECONDARY_LEVER_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > secondary_score and score >= 2:
            secondary_score = score
            secondary = lever

    return {
        "lever_primary": "GOV",
        "lever_secondary": secondary,
        "sub_variable": best_sub,
        "direction": direction,
        "confidence": confidence,
    }


# ─── Federal Register Collector ─────────────────────────────────────────────


def collect_federal_register(start: datetime, end: datetime) -> list[dict]:
    """Query the Federal Register API for AI-related documents."""
    entries = []
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    for term in FR_SEARCH_TERMS:
        print(f"  Searching Federal Register: \"{term}\"...")

        params = [
            ("conditions[term]", term),
            ("conditions[publication_date][gte]", start_str),
            ("conditions[publication_date][lte]", end_str),
            ("per_page", "50"),
            ("order", "newest"),
        ]
        for field in ["title", "abstract", "document_number", "publication_date",
                       "html_url", "agency_names", "type", "subtype",
                       "action", "dates", "significant"]:
            params.append(("fields[]", field))

        try:
            resp = requests.get(FEDERAL_REGISTER_API, params=params,
                                headers={"User-Agent": "espresso-ai/1.0"}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            print(f"    [ERROR] Federal Register query failed: {e}")
            continue

        results = data.get("results", [])
        print(f"    → {len(results)} documents")

        filtered = 0
        for doc in results:
            title = doc.get("title", "")
            abstract = doc.get("abstract", "") or ""

            # AI-relevance filter: drop documents that aren't about AI
            relevance = score_ai_relevance(title, abstract)
            if relevance < AI_RELEVANCE_THRESHOLD:
                filtered += 1
                continue

            doc_number = doc.get("document_number", "")
            pub_date = doc.get("publication_date", "")
            html_url = doc.get("html_url", "")
            agencies = doc.get("agency_names", [])
            doc_type = doc.get("type", "Notice")
            action = doc.get("action", "")
            significant = doc.get("significant", False)

            # Map Federal Register doc types to our document_type enum
            type_map = {
                "Rule": "regulation",
                "Proposed Rule": "proposed_rule",
                "Notice": "notice",
                "Presidential Document": "executive_order",
            }
            document_type = type_map.get(doc_type, "notice")

            entries.append({
                "source": "federal_register",
                "title": title[:200],
                "summary": abstract[:500] if abstract else f"Federal Register {doc_type}: {title[:200]}",
                "source_url": html_url,
                "publication_date": pub_date,
                "document_number": doc_number,
                "document_type": document_type,
                "jurisdiction": "us_federal",
                "agencies": agencies,
                "action": action,
                "significant": significant,
                "key_facts": [
                    f"Document type: {doc_type}",
                    f"Document number: {doc_number}",
                    f"Agencies: {', '.join(agencies)}" if agencies else "Agency: Not specified",
                ],
                "confidence": "high",  # Primary source
                "ai_relevance_score": relevance,
            })

        if filtered:
            print(f"    ✗ {filtered} dropped (not AI-relevant)")

        time.sleep(1)  # Be polite to the API

    return entries


# ─── Signal Record Builder ──────────────────────────────────────────────────


def entry_to_signal_record(entry: dict, cadence: str,
                            pipeline_run_id: str, batch_id: str) -> dict:
    """Convert a collected regulatory entry into an espresso·ai signal record."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    title = entry.get("title", "Untitled")
    summary = entry.get("summary", "")
    pub_date = entry.get("publication_date", "")

    # Classify
    classification = classify_signal(title, summary)

    # Build tags
    jurisdiction = entry.get("jurisdiction", "unknown")
    document_type = entry.get("document_type", "notice")
    agencies = entry.get("agencies", [])

    tags = [
        f"jurisdiction:{jurisdiction}",
        f"document_type:{document_type}",
        f"source_api:{entry.get('source', 'unknown')}",
    ]
    if entry.get("document_number"):
        tags.append(f"regulatory_id:{entry['document_number']}")
    for agency in agencies[:3]:
        tags.append(f"agency:{agency}")
    if entry.get("significant"):
        tags.append("significant:true")

    # Key facts
    key_facts = entry.get("key_facts", [])
    if not key_facts:
        key_facts = [f"Document type: {document_type}", f"Jurisdiction: {jurisdiction}"]

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
        "lever_secondary": classification["lever_secondary"],
        "direction": classification["direction"],
        "sub_variable": classification["sub_variable"],
        "confidence": entry.get("confidence", classification["confidence"]),

        "title": title[:200],
        "summary": summary[:500] if summary else title[:200],
        "key_facts": key_facts[:5],
        "raw_content": summary[:2000] if summary else None,

        "publication_date": pub_date,
        "reporting_period": None,

        # Synthesis fields
        "signal_strength": None,
        "cross_lever_interactions": [],
        "novelty_flag": None,
        "countervailing_signals": [],
        "synthesis_notes": None,
        "is_duplicate": False,
        "duplicate_of": None,

        "in_scope": True,
        "data_quality_flags": [],
        "tags": tags,
        "schema_version": SCHEMA_VERSION,
    }


# ─── Deduplication ──────────────────────────────────────────────────────────


def deduplicate_entries(entries: list[dict]) -> tuple[list[dict], int]:
    """Remove duplicate entries by URL and title similarity."""
    seen_urls = set()
    seen_titles = set()
    seen_doc_numbers = set()
    unique = []

    for entry in entries:
        # Deduplicate by document number (Federal Register)
        doc_num = entry.get("document_number", "")
        if doc_num and doc_num in seen_doc_numbers:
            continue

        # Deduplicate by URL
        url = entry.get("source_url", "").rstrip("/").lower()
        if url and url in seen_urls:
            continue

        # Deduplicate by exact title
        title_key = entry.get("title", "").lower().strip()
        if title_key and title_key in seen_titles:
            continue

        if doc_num:
            seen_doc_numbers.add(doc_num)
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
    parser = argparse.ArgumentParser(description="espresso·ai Regulatory Signal Collector (Federal Register)")
    parser.add_argument("--cadence", default="weekly",
                        choices=["daily", "weekly", "monthly", "quarterly", "annual"])
    parser.add_argument("--days-back", type=int, default=None,
                        help="Override: look back N days (default: auto from cadence)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print results without writing to disk")
    args = parser.parse_args()

    cadence = args.cadence
    now = datetime.now(timezone.utc)
    pipeline_run_id = f"{now.strftime('%Y-%m-%d')}_{cadence}_{uuid.uuid4().hex[:8]}"
    batch_id = f"batch_{now.strftime('%Y%m%d_%H%M')}"
    start_date, end_date = get_date_range(cadence, args.days_back)

    print("=" * 70)
    print("espresso·ai — Regulatory Signal Collector (Federal Register)")
    print("=" * 70)
    print(f"Pipeline run:      {pipeline_run_id}")
    print(f"Batch:             {batch_id}")
    print(f"Cadence:           {cadence}")
    print(f"Date range:        {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}")
    print(f"Source:            US Federal Register (free API, no auth)")
    print("=" * 70)

    # ── Collect from Federal Register ──
    print(f"\n{'─' * 40}")
    print("Querying US Federal Register API")
    print(f"{'─' * 40}")
    all_entries = collect_federal_register(start_date, end_date)
    print(f"\nTotal: {len(all_entries)} documents")

    # Deduplicate
    pre_dedup = len(all_entries)
    all_entries, dupes_removed = deduplicate_entries(all_entries)

    print(f"\n{'=' * 70}")
    print(f"Total collected:    {pre_dedup}")
    print(f"Duplicates removed: {dupes_removed}")
    print(f"Unique signals:     {len(all_entries)}")

    if not all_entries:
        print("\nNo regulatory signals found in the target date range.")
        print("Suggestions:")
        print("  - Try a longer cadence or increase --days-back")
        print("  - Check network connectivity to federalregister.gov")
        return

    # Convert to signal records
    signal_records = []
    for entry in all_entries:
        record = entry_to_signal_record(entry, cadence, pipeline_run_id, batch_id)
        record = validate_and_flag(record, start_date, end_date)
        signal_records.append(record)

    # Metrics
    doc_type_counts = {}
    direction_counts = {}
    for entry in all_entries:
        dt = entry.get("document_type", "unknown")
        doc_type_counts[dt] = doc_type_counts.get(dt, 0) + 1

    for rec in signal_records:
        d = rec["direction"]
        direction_counts[d] = direction_counts.get(d, 0) + 1

    def count_flag(flag_name):
        return sum(1 for s in signal_records if flag_name in s.get("data_quality_flags", []))

    print(f"\nDocument Type Distribution:")
    for dt, count in sorted(doc_type_counts.items(), key=lambda x: -x[1]):
        print(f"  {dt:20s}  {count:3d}")

    print(f"\nDirection: + {direction_counts.get('+', 0)} | - {direction_counts.get('-', 0)} | ~ {direction_counts.get('~', 0)} | ? {direction_counts.get('?', 0)}")
    print(f"Missing URLs:        {count_flag('missing_url')}")
    print(f"Out-of-date:         {count_flag('out_of_date_range')}")

    # Write JSONL
    base_dir = Path(__file__).resolve().parent.parent.parent / "research_db" / "raw"
    base_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = get_date_range_prefix(start_date, end_date)
    output_file = base_dir / f"{date_prefix}_regulatory_{cadence}_signals.jsonl"

    if args.dry_run:
        print(f"\n[DRY RUN] Would write {len(signal_records)} records to {output_file}")
        for rec in signal_records[:5]:
            print(f"\n  Title: {rec['title'][:80]}")
            print(f"  Lever: {rec['lever_primary']} | Direction: {rec['direction']} | Sub: {rec['sub_variable']}")
            print(f"  URL:   {rec['source_url'][:80]}")
            tags = [t for t in rec['tags'] if t.startswith('jurisdiction:') or t.startswith('document_type:')]
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
        "source": "federal_register",
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date_range": {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        },
        "total_results_raw": pre_dedup,
        "duplicates_removed": dupes_removed,
        "records_written": len(signal_records),
        "document_type_distribution": doc_type_counts,
        "direction_distribution": direction_counts,
        "output_file": str(output_file),
        "quality_metrics": {
            "missing_url_count": count_flag("missing_url"),
            "out_of_date_count": count_flag("out_of_date_range"),
        },
    }

    log_file = base_dir / f"{date_prefix}_regulatory_pipeline_log.json"
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
        sub = rec["sub_variable"]
        title = rec["title"][:65]
        doc_type = next((t.split(":")[1] for t in rec.get("tags", []) if t.startswith("document_type:")), "?")
        print(f"  {i:2d}. [GOV {d}] us_federal   | {doc_type:15s} | {sub:30s} | {title}")

    if len(signal_records) > 10:
        print(f"  ... and {len(signal_records) - 10} more")

    print(f"\n{'=' * 70}")
    print("Done. (Federal Register API — $0.00)")


if __name__ == "__main__":
    main()
