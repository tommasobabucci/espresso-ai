#!/usr/bin/env python3
"""
espresso·ai — OpenAlex Cross-Discipline AI Signal Collector
Queries the OpenAlex API (free, no auth) for AI-related papers published in
non-CS fields: medicine, law, energy, finance, education, materials science.

Complements the ArXiv collector (which covers CS/ML papers → COMPUTE lever) by
capturing signals of AI diffusion into real-world domains → SOCIETY + INDUSTRY levers.

Usage:
    python .claude/scripts/collect_openalex_signals.py --cadence weekly [--days-back 7] [--dry-run]
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

OPENALEX_API_BASE = "https://api.openalex.org"
AGENT_ID = "openalex-cross-discipline-collector"
SCHEMA_VERSION = "1.0"
SOURCE_NAME = "academic_paper"

# Contact email for OpenAlex polite pool (faster rate limits)
POLITE_EMAIL = "espresso-ai@example.com"

# Maximum results per query
MAX_RESULTS_PER_QUERY = 50

# ─── Cross-Discipline Query Definitions ──────────────────────────────────────
# Each query targets AI concepts intersected with a non-CS discipline.
# OpenAlex uses concept IDs (openalex.org/concepts) for filtering.
#
# Strategy: find papers where AI/ML is applied IN another field,
# not papers about AI itself (ArXiv covers that).

CROSS_DISCIPLINE_QUERIES = [
    {
        "name": "AI in Medicine & Healthcare",
        "search": "(artificial intelligence OR machine learning OR deep learning) AND (clinical OR diagnosis OR patient OR medical OR healthcare OR radiology OR drug discovery)",
        "topic_filter": None,
        "lever_hint": "SOCIETY",
        "sub_var_hint": "high_stakes_domain_adoption",
        "domain": "healthcare",
    },
    {
        "name": "AI in Law & Policy",
        "search": "(artificial intelligence OR machine learning OR algorithmic) AND (legal OR judicial OR court OR regulation OR compliance OR law)",
        "topic_filter": None,
        "lever_hint": "SOCIETY",
        "sub_var_hint": "high_stakes_domain_adoption",
        "domain": "legal",
    },
    {
        "name": "AI in Energy & Environment",
        "search": "(artificial intelligence OR machine learning OR deep learning) AND (energy OR power grid OR renewable OR solar OR wind OR electricity OR carbon)",
        "topic_filter": None,
        "lever_hint": "INDUSTRY",
        "sub_var_hint": "cross_sector_diffusion",
        "domain": "energy",
    },
    {
        "name": "AI in Economics & Finance",
        "search": "(artificial intelligence OR machine learning OR deep learning) AND (financial OR banking OR trading OR economic OR investment OR credit OR insurance)",
        "topic_filter": None,
        "lever_hint": "INDUSTRY",
        "sub_var_hint": "cross_sector_diffusion",
        "domain": "finance",
    },
    {
        "name": "AI in Education",
        "search": "(artificial intelligence OR machine learning) AND (education OR student OR learning OR teaching OR curriculum OR classroom)",
        "topic_filter": None,
        "lever_hint": "SOCIETY",
        "sub_var_hint": "ai_literacy_distribution",
        "domain": "education",
    },
    {
        "name": "AI in Manufacturing & Engineering",
        "search": "(artificial intelligence OR machine learning OR deep learning) AND (manufacturing OR industrial OR predictive maintenance OR quality control OR supply chain)",
        "topic_filter": None,
        "lever_hint": "INDUSTRY",
        "sub_var_hint": "cross_sector_diffusion",
        "domain": "manufacturing",
    },
    {
        "name": "AI in Materials Science",
        "search": "(artificial intelligence OR machine learning OR neural network) AND (materials OR molecular OR crystal OR polymer OR alloy)",
        "topic_filter": None,
        "lever_hint": "INDUSTRY",
        "sub_var_hint": "cross_sector_diffusion",
        "domain": "materials",
    },
    {
        "name": "AI Ethics, Fairness & Society",
        "search": "AI fairness OR AI bias OR AI ethics OR responsible AI OR AI governance",
        "topic_filter": None,
        "lever_hint": "SOCIETY",
        "sub_var_hint": "incident_impact_on_trust",
        "domain": "ethics",
    },
    {
        "name": "AI & Workforce / Labor Economics",
        "search": "(artificial intelligence OR automation) AND (employment OR labor OR workforce OR displacement OR jobs OR wages)",
        "topic_filter": None,
        "lever_hint": "SOCIETY",
        "sub_var_hint": "professional_displacement_signals",
        "domain": "labor",
    },
]

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


def openalex_request(endpoint: str, params: dict) -> dict | None:
    """Make a request to the OpenAlex API."""
    url = f"{OPENALEX_API_BASE}/{endpoint}"
    params["mailto"] = POLITE_EMAIL
    try:
        resp = requests.get(url, params=params,
                            headers={"User-Agent": "espresso-ai/1.0"},
                            timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"    [ERROR] OpenAlex API request failed: {e}")
        return None


# ─── Classification ─────────────────────────────────────────────────────────

SUB_VAR_KEYWORDS = {
    "SOCIETY": {
        "enterprise_penetration_depth": [
            "enterprise", "corporate", "organization", "deployment",
        ],
        "high_stakes_domain_adoption": [
            "clinical", "medical", "diagnostic", "patient", "legal",
            "court", "judicial", "financial", "banking", "insurance",
            "healthcare", "hospital", "drug discovery", "radiology",
        ],
        "ai_literacy_distribution": [
            "education", "literacy", "training", "curriculum", "student",
            "learning", "teaching", "pedagogy", "skills",
        ],
        "researcher_and_engineer_stock": [
            "researcher", "engineer", "talent", "hiring", "workforce",
            "scientist", "developer", "graduate",
        ],
        "skill_diffusion_rate": [
            "adoption", "diffusion", "spread", "transfer", "open-source",
            "democratiz", "accessibility",
        ],
        "professional_displacement_signals": [
            "displacement", "automation", "labor", "employment",
            "unemployment", "wage", "replacement", "substitution",
            "job loss", "workforce reduction",
        ],
        "incident_impact_on_trust": [
            "trust", "safety", "risk", "failure", "harm", "bias",
            "fairness", "ethics", "responsible", "accountability",
            "transparency", "explainability",
        ],
    },
    "INDUSTRY": {
        "production_deployment_rate": [
            "production", "deployment", "implementation", "pilot",
            "real-world", "practical", "system",
        ],
        "productivity_measurement_transparency": [
            "productivity", "efficiency", "performance", "benchmark",
            "evaluation", "metric", "measurement",
        ],
        "cross_sector_diffusion": [
            "manufacturing", "energy", "agriculture", "logistics",
            "construction", "transportation", "materials", "chemical",
            "pharmaceutical", "mining", "retail",
        ],
        "workflow_integration_depth": [
            "workflow", "pipeline", "integration", "embedded",
            "end-to-end", "automated", "operational",
        ],
        "business_model_reinvention": [
            "business model", "pricing", "service", "platform",
            "revenue", "market", "commercial",
        ],
    },
}

POSITIVE_INDICATORS = [
    "effective", "improved", "outperform", "superior", "successful",
    "promising", "breakthrough", "novel", "state-of-the-art", "advance",
    "enhance", "benefit", "enables", "accelerat", "transform",
]
NEGATIVE_INDICATORS = [
    "fail", "limitation", "bias", "harm", "risk", "concern",
    "challenge", "barrier", "gap", "underperform", "inequit",
    "displacement", "threat", "vulnerability", "danger",
]


def classify_signal(title: str, abstract: str, lever_hint: str = None,
                    sub_var_hint: str = None) -> dict:
    """Classify a paper against the Scale Levers framework."""
    text = (title + " " + abstract).lower()

    # Determine primary lever
    if lever_hint:
        lever_primary = lever_hint
    else:
        # Score both SOCIETY and INDUSTRY, pick the higher one
        society_score = 0
        for keywords in SUB_VAR_KEYWORDS.get("SOCIETY", {}).values():
            society_score += sum(1 for kw in keywords if kw in text)
        industry_score = 0
        for keywords in SUB_VAR_KEYWORDS.get("INDUSTRY", {}).values():
            industry_score += sum(1 for kw in keywords if kw in text)
        lever_primary = "SOCIETY" if society_score >= industry_score else "INDUSTRY"

    # Find best sub_variable
    best_sub = sub_var_hint or ("skill_diffusion_rate" if lever_primary == "SOCIETY" else "cross_sector_diffusion")
    best_score = 0

    lever_subs = SUB_VAR_KEYWORDS.get(lever_primary, {})
    for sub_var, keywords in lever_subs.items():
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
        direction = "+"  # Default for academic papers: they advance capability

    # Confidence: based on keyword score + citation count (added later)
    confidence = "high" if best_score >= 3 else "medium" if best_score >= 1 else "low"

    # Detect secondary lever
    secondary = None
    other_lever = "INDUSTRY" if lever_primary == "SOCIETY" else "SOCIETY"
    other_score = 0
    for keywords in SUB_VAR_KEYWORDS.get(other_lever, {}).values():
        other_score += sum(1 for kw in keywords if kw in text)
    if other_score >= 3:
        secondary = other_lever

    return {
        "lever_primary": lever_primary,
        "lever_secondary": secondary,
        "sub_variable": best_sub,
        "direction": direction,
        "confidence": confidence,
    }


# ─── OpenAlex Data Collector ────────────────────────────────────────────────


def collect_cross_discipline_papers(start: datetime, end: datetime) -> list[dict]:
    """Query OpenAlex for AI papers in non-CS disciplines."""
    entries = []
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    for query_def in CROSS_DISCIPLINE_QUERIES:
        name = query_def["name"]
        search_text = query_def["search"]
        topic_filter = query_def.get("topic_filter")
        extra_filter = query_def.get("extra_filter")
        lever_hint = query_def["lever_hint"]
        sub_var_hint = query_def["sub_var_hint"]
        domain = query_def["domain"]

        print(f"  Querying: {name}...")

        # Build filter string
        filter_parts = [
            f"from_publication_date:{start_str}",
            f"to_publication_date:{end_str}",
            "type:article",  # Only journal articles (not preprints, which ArXiv covers)
        ]
        if topic_filter:
            filter_parts.append(topic_filter)
        if extra_filter:
            filter_parts.append(extra_filter)

        filter_str = ",".join(filter_parts)

        params = {
            "search": search_text,
            "filter": filter_str,
            "sort": "cited_by_count:desc",
            "per_page": str(MAX_RESULTS_PER_QUERY),
            "select": "id,doi,title,publication_date,cited_by_count,authorships,topics,open_access,abstract_inverted_index,primary_location",
        }

        data = openalex_request("works", params)
        if not data:
            continue

        results = data.get("results", [])
        count = data.get("meta", {}).get("count", 0)
        print(f"    → {len(results)} papers (of {count} total)")

        for work in results:
            title = work.get("title", "")
            if not title:
                continue

            # Reconstruct abstract from inverted index
            abstract = ""
            abstract_inv = work.get("abstract_inverted_index")
            if abstract_inv:
                # OpenAlex stores abstracts as inverted indexes: {"word": [position1, position2]}
                word_positions = []
                for word, positions in abstract_inv.items():
                    for pos in positions:
                        word_positions.append((pos, word))
                word_positions.sort(key=lambda x: x[0])
                abstract = " ".join(w for _, w in word_positions)

            doi = work.get("doi", "")
            openalex_id = work.get("id", "")
            pub_date = work.get("publication_date", "")
            cited_by = work.get("cited_by_count", 0) or 0

            # Source URL: prefer DOI, fall back to OpenAlex URL
            source_url = doi if doi else openalex_id
            if source_url and not source_url.startswith("http"):
                source_url = f"https://doi.org/{source_url}" if "/" in source_url else openalex_id

            # Extract institution info
            institutions = []
            authorships = work.get("authorships", [])
            for authorship in authorships[:5]:
                for inst in authorship.get("institutions", []):
                    inst_name = inst.get("display_name", "")
                    if inst_name and inst_name not in institutions:
                        institutions.append(inst_name)

            # Extract journal/source info
            journal = ""
            primary_loc = work.get("primary_location", {})
            if primary_loc:
                source = primary_loc.get("source", {})
                if source:
                    journal = source.get("display_name", "")

            # Open access status
            oa = work.get("open_access", {})
            is_oa = oa.get("is_oa", False)

            # Extract topics
            topics = work.get("topics", [])
            topic_names = [t.get("display_name", "") for t in topics[:5] if t.get("display_name")]

            # Classify
            classification = classify_signal(title, abstract, lever_hint, sub_var_hint)

            # Boost confidence for highly-cited papers
            if cited_by >= 50:
                classification["confidence"] = "high"
            elif cited_by >= 10:
                if classification["confidence"] == "low":
                    classification["confidence"] = "medium"

            # Build summary
            if abstract:
                # Take first sentence of abstract as basis
                first_sent = abstract.split(". ")[0] + "."
                if len(first_sent) > 300:
                    first_sent = first_sent[:297] + "..."
                summary = first_sent
            else:
                summary = f"Paper on {', '.join(topic_names[:3]) if topic_names else domain} applying AI/ML techniques."

            # Build key facts
            key_facts = [
                f"Domain: {domain}",
                f"Citations: {cited_by}",
            ]
            if journal:
                key_facts.append(f"Journal: {journal}")
            if institutions:
                key_facts.append(f"Institutions: {', '.join(institutions[:3])}")
            if topic_names:
                key_facts.append(f"Topics: {', '.join(topic_names[:3])}")

            # Build tags
            tags = [
                f"domain:{domain}",
                f"cited_by:{cited_by}",
                f"open_access:{str(is_oa).lower()}",
                "data_type:cross_discipline_paper",
                f"query:{name}",
            ]
            if journal:
                tags.append(f"journal:{journal[:50]}")
            for inst in institutions[:2]:
                tags.append(f"institution:{inst[:50]}")

            entries.append({
                "title": title[:200],
                "summary": summary[:500],
                "source_url": source_url,
                "publication_date": pub_date,
                "direction": classification["direction"],
                "lever_primary": classification["lever_primary"],
                "lever_secondary": classification["lever_secondary"],
                "sub_variable": classification["sub_variable"],
                "confidence": classification["confidence"],
                "key_facts": key_facts[:5],
                "tags": tags,
                "cited_by_count": cited_by,
                "_openalex_meta": {
                    "openalex_id": openalex_id,
                    "doi": doi,
                    "cited_by_count": cited_by,
                    "is_open_access": is_oa,
                    "journal": journal,
                    "institutions": institutions[:5],
                    "topics": topic_names[:5],
                },
            })

        time.sleep(0.5)  # Polite delay between queries

    return entries


# ─── Signal Record Builder ──────────────────────────────────────────────────


def entry_to_signal_record(entry: dict, cadence: str,
                            pipeline_run_id: str, batch_id: str) -> dict:
    """Convert a collected OpenAlex entry into an espresso·ai signal record."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "signal_id": generate_signal_id(SOURCE_NAME, now),
        "source_name": SOURCE_NAME,
        "source_url": entry.get("source_url", ""),
        "fetch_timestamp": now,
        "agent_id": AGENT_ID,
        "cadence": cadence,
        "pipeline_run_id": pipeline_run_id,
        "collection_batch_id": batch_id,

        "lever_primary": entry.get("lever_primary", "SOCIETY"),
        "lever_secondary": entry.get("lever_secondary"),
        "direction": entry.get("direction", "+"),
        "sub_variable": entry.get("sub_variable", "skill_diffusion_rate"),
        "confidence": entry.get("confidence", "medium"),

        "title": entry.get("title", "Untitled")[:200],
        "summary": entry.get("summary", "")[:500],
        "key_facts": entry.get("key_facts", [])[:5],
        "raw_content": None,

        "publication_date": entry.get("publication_date", ""),
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
        "tags": entry.get("tags", []) + ["source_api:openalex"],
        "schema_version": SCHEMA_VERSION,
    }


# ─── Deduplication ──────────────────────────────────────────────────────────


def deduplicate_entries(entries: list[dict]) -> tuple[list[dict], int]:
    """Remove duplicate entries by URL and title."""
    seen_urls = set()
    seen_titles = set()
    unique = []

    for entry in entries:
        # Deduplicate by URL (DOI)
        url = entry.get("source_url", "").rstrip("/").lower()
        if url and url in seen_urls:
            continue

        # Deduplicate by exact title
        title_key = entry.get("title", "").lower().strip()
        if title_key and title_key in seen_titles:
            continue

        if url:
            seen_urls.add(url)
        if title_key:
            seen_titles.add(title_key)
        unique.append(entry)

    return unique, len(entries) - len(unique)


# ─── Validation ─────────────────────────────────────────────────────────────


def validate_and_flag(record: dict, date_start: datetime, date_end: datetime) -> dict:
    """Add quality flags based on data checks."""
    flags = list(record.get("data_quality_flags", []))

    url = record.get("source_url", "")
    if not url:
        flags.append("missing_url")

    pub_date = record.get("publication_date", "")
    if pub_date:
        try:
            pd = datetime.strptime(pub_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            buffer = timedelta(days=7)
            if pd < (date_start - buffer) or pd > (date_end + buffer):
                flags.append("out_of_date_range")
        except ValueError:
            flags.append("invalid_date_format")

    record["data_quality_flags"] = flags
    return record


# ─── Main Pipeline ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="espresso·ai OpenAlex Cross-Discipline AI Signal Collector"
    )
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
    print("espresso·ai — OpenAlex Cross-Discipline AI Signal Collector")
    print("=" * 70)
    print(f"Pipeline run:      {pipeline_run_id}")
    print(f"Batch:             {batch_id}")
    print(f"Cadence:           {cadence}")
    print(f"Date range:        {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}")
    print(f"Source:            OpenAlex (free, no auth)")
    print(f"Strategy:          AI papers in non-CS fields (complements ArXiv)")
    print("=" * 70)

    # ── Collect from OpenAlex ──
    print(f"\n{'─' * 40}")
    print("Querying Cross-Discipline AI Papers")
    print(f"{'─' * 40}")
    all_entries = collect_cross_discipline_papers(start_date, end_date)
    print(f"\nTotal: {len(all_entries)} papers")

    # Deduplicate
    pre_dedup = len(all_entries)
    all_entries, dupes_removed = deduplicate_entries(all_entries)

    # Sort by citation count (highest first)
    all_entries.sort(key=lambda x: x.get("cited_by_count", 0), reverse=True)

    print(f"\n{'=' * 70}")
    print(f"Total collected:    {pre_dedup}")
    print(f"Duplicates removed: {dupes_removed}")
    print(f"Unique signals:     {len(all_entries)}")

    if not all_entries:
        print("\nNo cross-discipline AI papers found in the target date range.")
        print("Suggestions:")
        print("  - Try a longer cadence (monthly or quarterly)")
        print("  - Increase --days-back")
        print("  - Check network connectivity to api.openalex.org")
        return

    # Convert to signal records
    signal_records = []
    for entry in all_entries:
        record = entry_to_signal_record(entry, cadence, pipeline_run_id, batch_id)
        record = validate_and_flag(record, start_date, end_date)
        signal_records.append(record)

    # Metrics
    lever_counts = {}
    direction_counts = {}
    sub_var_counts = {}
    domain_counts = {}

    for rec in signal_records:
        lp = rec["lever_primary"]
        lever_counts[lp] = lever_counts.get(lp, 0) + 1
        d = rec["direction"]
        direction_counts[d] = direction_counts.get(d, 0) + 1
        sv = rec["sub_variable"]
        sub_var_counts[sv] = sub_var_counts.get(sv, 0) + 1

    for entry in all_entries:
        for tag in entry.get("tags", []):
            if tag.startswith("domain:"):
                domain = tag.split(":")[1]
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

    def count_flag(flag_name):
        return sum(1 for s in signal_records if flag_name in s.get("data_quality_flags", []))

    print(f"\nLever Distribution:")
    for lp, count in sorted(lever_counts.items(), key=lambda x: -x[1]):
        print(f"  {lp:15s}  {count:3d}")

    print(f"\nDomain Distribution:")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        print(f"  {domain:20s}  {count:3d}")

    print(f"\nSub-Variable Distribution:")
    for sv, count in sorted(sub_var_counts.items(), key=lambda x: -x[1]):
        print(f"  {sv:35s}  {count:3d}")

    print(f"\nDirection: + {direction_counts.get('+', 0)} | - {direction_counts.get('-', 0)} | ~ {direction_counts.get('~', 0)} | ? {direction_counts.get('?', 0)}")
    print(f"Out-of-date:         {count_flag('out_of_date_range')}")

    # Citation stats
    citations = [e.get("cited_by_count", 0) for e in all_entries]
    if citations:
        print(f"\nCitation Stats:")
        print(f"  Max:     {max(citations)}")
        print(f"  Median:  {sorted(citations)[len(citations)//2]}")
        print(f"  Total:   {sum(citations)}")

    # Write JSONL
    base_dir = Path(__file__).resolve().parent.parent.parent / "research_db" / "raw"
    base_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = get_date_range_prefix(start_date, end_date)
    output_file = base_dir / f"{date_prefix}_openalex_{cadence}_signals.jsonl"

    if args.dry_run:
        print(f"\n[DRY RUN] Would write {len(signal_records)} records to {output_file}")
        for rec in signal_records[:8]:
            cited = next((t.split(":")[1] for t in rec.get("tags", []) if t.startswith("cited_by:")), "?")
            domain = next((t.split(":")[1] for t in rec.get("tags", []) if t.startswith("domain:")), "?")
            print(f"\n  Title:    {rec['title'][:75]}")
            print(f"  Lever:    {rec['lever_primary']} | Direction: {rec['direction']} | Sub: {rec['sub_variable']}")
            print(f"  Domain:   {domain} | Citations: {cited}")
            print(f"  URL:      {rec['source_url'][:75]}")
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
        "source": "openalex",
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date_range": {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        },
        "total_results_raw": pre_dedup,
        "duplicates_removed": dupes_removed,
        "records_written": len(signal_records),
        "lever_distribution": lever_counts,
        "domain_distribution": domain_counts,
        "sub_variable_distribution": sub_var_counts,
        "direction_distribution": direction_counts,
        "output_file": str(output_file),
        "quality_metrics": {
            "out_of_date_count": count_flag("out_of_date_range"),
            "missing_url_count": count_flag("missing_url"),
            "max_citations": max(citations) if citations else 0,
            "median_citations": sorted(citations)[len(citations) // 2] if citations else 0,
        },
    }

    log_file = base_dir / f"{date_prefix}_openalex_pipeline_log.json"
    if not args.dry_run:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
        print(f"✓ Pipeline log: {log_file}")

    # Print signal sample
    print(f"\n{'=' * 70}")
    print("SAMPLE SIGNALS (sorted by citations):")
    print(f"{'=' * 70}")
    for i, rec in enumerate(signal_records[:10], 1):
        d = rec["direction"]
        lp = rec["lever_primary"]
        sub = rec["sub_variable"]
        title = rec["title"][:55]
        cited = next((t.split(":")[1] for t in rec.get("tags", []) if t.startswith("cited_by:")), "?")
        domain = next((t.split(":")[1] for t in rec.get("tags", []) if t.startswith("domain:")), "?")
        print(f"  {i:2d}. [{lp} {d}] {domain:12s} | cite:{cited:>4s} | {sub:28s} | {title}")

    if len(signal_records) > 10:
        print(f"  ... and {len(signal_records) - 10} more")

    print(f"\n{'=' * 70}")
    print("Done. (OpenAlex API — $0.00, no auth required)")


if __name__ == "__main__":
    main()
