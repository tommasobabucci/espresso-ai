#!/usr/bin/env python3
"""
espresso·ai — ArXiv Signal Collector
Queries the ArXiv API for AI-related papers, extracts structured signal records,
and appends them to the weekly JSONL file in research_db/raw/.

Usage:
    python research_db/collect_arxiv_signals.py [--max-results 100] [--cadence weekly]
"""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import hashlib
import uuid
import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────────────────

ARXIV_API_URL = "http://export.arxiv.org/api/query"
AGENT_ID = "arxiv-signal-collector"
SCHEMA_VERSION = "1.0"
SOURCE_NAME = "academic_paper"

# ArXiv categories relevant to AI research
AI_CATEGORIES = [
    "cs.AI",   # Artificial Intelligence
    "cs.LG",   # Machine Learning
    "cs.CL",   # Computation and Language (NLP)
    "cs.CV",   # Computer Vision
    "cs.NE",   # Neural and Evolutionary Computing
    "cs.RO",   # Robotics (AI-relevant)
    "cs.MA",   # Multiagent Systems
    "stat.ML", # Machine Learning (Statistics)
]

# Search terms that map to espresso·ai's Scale Levers framework
# These target high-signal papers, not incremental benchmark improvements
SIGNAL_QUERIES = [
    # COMPUTE lever
    '"large language model" AND (scaling OR efficiency OR inference)',
    '"transformer architecture" AND (efficiency OR optimization)',
    '"model compression" OR "knowledge distillation" OR "quantization"',
    '"neural architecture search" OR "efficient training"',

    # INDUSTRY lever
    '"AI agent" OR "autonomous agent" OR "tool use"',
    '"enterprise AI" OR "production deployment" OR "AI systems"',
    '"retrieval augmented generation" OR RAG',
    '"code generation" OR "program synthesis"',

    # SOCIETY lever
    '"AI alignment" OR "AI safety" OR "value alignment"',
    '"AI fairness" OR "AI bias" OR "responsible AI"',
    '"human-AI interaction" OR "AI augmentation"',
    '"AI education" OR "AI literacy"',

    # GOV lever
    '"AI regulation" OR "AI governance" OR "AI policy"',
    '"AI ethics" OR "trustworthy AI"',
    '"interpretability" OR "explainability" OR "mechanistic interpretability"',

    # ENERGY lever
    '"energy efficient" AND ("neural network" OR "deep learning")',
    '"green AI" OR "sustainable AI" OR "carbon footprint"',

    # CAPITAL lever — frontier model releases, benchmarks that move markets
    '"foundation model" OR "frontier model"',
    '"multimodal" AND ("model" OR "learning")',
    '"reasoning" AND ("language model" OR "LLM")',
    '"world model" OR "embodied AI"',
]

# Atom namespace
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"

# ─── Helper Functions ────────────────────────────────────────────────────────

def generate_signal_id(source_name: str, timestamp: str) -> str:
    """Generate unique signal ID per schema: YYYYMMDD-source_name-HHMMSS-5char"""
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    date_part = dt.strftime("%Y%m%d")
    time_part = dt.strftime("%H%M%S")
    hash_part = hashlib.md5(f"{timestamp}{uuid.uuid4()}".encode()).hexdigest()[:5]
    return f"{date_part}-{source_name}-{time_part}-{hash_part}"


def get_date_range_prefix(start: datetime, end: datetime) -> str:
    """Get date range string for file naming: YYYY-MM-DD_YYYY-MM-DD"""
    return f"{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}"


def get_date_range(days_back: int = 7):
    """Return start/end dates for the query window."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)
    return start, end


def query_arxiv(search_query: str, start: int = 0, max_results: int = 30) -> list:
    """
    Query ArXiv API and return parsed entries.
    ArXiv API docs: https://info.arxiv.org/help/api/user-manual.html
    """
    params = {
        "search_query": search_query,
        "start": start,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    url = f"{ARXIV_API_URL}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "espresso-ai/1.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read().decode("utf-8")
        return parse_arxiv_response(data)
    except Exception as e:
        print(f"  [ERROR] ArXiv query failed: {e}")
        return []


def parse_arxiv_response(xml_data: str) -> list:
    """Parse ArXiv Atom XML response into structured dicts."""
    root = ET.fromstring(xml_data)
    entries = []

    for entry in root.findall(f"{ATOM_NS}entry"):
        # Extract basic fields
        title = entry.find(f"{ATOM_NS}title")
        summary = entry.find(f"{ATOM_NS}summary")
        published = entry.find(f"{ATOM_NS}published")
        updated = entry.find(f"{ATOM_NS}updated")
        arxiv_id = entry.find(f"{ATOM_NS}id")

        # Extract authors
        authors = []
        for author in entry.findall(f"{ATOM_NS}author"):
            name = author.find(f"{ATOM_NS}name")
            if name is not None and name.text:
                authors.append(name.text.strip())

        # Extract categories
        categories = []
        for cat in entry.findall(f"{ATOM_NS}category"):
            term = cat.get("term", "")
            if term:
                categories.append(term)

        # Extract links (PDF, abstract)
        abstract_url = ""
        pdf_url = ""
        for link in entry.findall(f"{ATOM_NS}link"):
            rel = link.get("rel", "")
            link_type = link.get("type", "")
            href = link.get("href", "")
            if rel == "alternate":
                abstract_url = href
            elif link_type == "application/pdf":
                pdf_url = href

        # Extract comment (often has page count, conference info)
        comment = entry.find(f"{ARXIV_NS}comment")

        # Clean up text fields
        title_text = " ".join(title.text.strip().split()) if title is not None and title.text else ""
        summary_text = " ".join(summary.text.strip().split()) if summary is not None and summary.text else ""
        published_text = published.text.strip() if published is not None and published.text else ""

        entries.append({
            "arxiv_id": arxiv_id.text.strip() if arxiv_id is not None and arxiv_id.text else "",
            "title": title_text,
            "abstract": summary_text,
            "authors": authors,
            "categories": categories,
            "published": published_text,
            "updated": updated.text.strip() if updated is not None and updated.text else "",
            "abstract_url": abstract_url,
            "pdf_url": pdf_url,
            "comment": comment.text.strip() if comment is not None and comment.text else "",
        })

    return entries


def is_within_date_range(published_str: str, start: datetime, end: datetime) -> bool:
    """Check if paper was published within the target date range."""
    try:
        pub_date = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        return start <= pub_date <= end
    except (ValueError, TypeError):
        return False


def classify_lever(title: str, abstract: str, categories: list) -> dict:
    """
    Auto-classify a paper into the Scale Levers framework based on content.
    Returns primary lever, sub-variable, and initial direction assessment.
    """
    text = (title + " " + abstract).lower()

    # COMPUTE signals
    compute_terms = {
        "manufacturing_capacity": ["chip", "semiconductor", "fabrication", "fab ", "wafer", "tsmc", "asml"],
        "cost_per_flop": ["inference cost", "training cost", "compute cost", "flop", "cost per token", "cost reduction"],
        "energy_efficiency": ["energy efficient", "power efficient", "flop per watt", "green ai"],
        "architectural_diversity": ["neuromorphic", "photonic", "analog compute", "in-memory compute", "spiking neural"],
        "custom_silicon_adoption": ["tpu", "trainium", "custom accelerator", "custom silicon", "specialized hardware"],
    }

    # Check for model efficiency / compression — maps to COMPUTE
    efficiency_terms = {
        "cost_per_flop": ["quantization", "pruning", "distillation", "model compression", "efficient inference",
                          "sparse", "mixture of experts", "moe ", "speculative decoding", "kv cache"],
    }

    # INDUSTRY signals
    industry_terms = {
        "production_deployment_rate": ["production deployment", "enterprise deployment", "real-world application",
                                       "industrial application", "deployed system"],
        "workflow_integration_depth": ["ai agent", "autonomous agent", "tool use", "function calling",
                                       "code generation", "program synthesis", "retrieval augmented",
                                       "rag ", "agentic"],
        "business_model_reinvention": ["business model", "pricing model", "ai-native", "ai-first"],
        "cross_sector_diffusion": ["healthcare ai", "medical ai", "clinical", "legal ai", "financial ai",
                                    "manufacturing ai", "drug discovery", "robotics"],
    }

    # SOCIETY signals
    society_terms = {
        "ai_literacy_distribution": ["ai literacy", "ai education", "human-ai interaction", "ai augmentation",
                                      "ai assistance", "copilot", "ai tutor"],
        "incident_impact_on_trust": ["ai safety", "alignment", "value alignment", "harmful", "toxic",
                                      "bias", "fairness", "trustworthy"],
        "professional_displacement_signals": ["labor market", "job displacement", "automation", "workforce"],
        "researcher_and_engineer_stock": ["ai talent", "ai workforce", "ai skills"],
    }

    # GOV signals
    gov_terms = {
        "alignment_and_safety_maturity": ["interpretability", "explainability", "mechanistic interpretability",
                                           "transparency", "audit", "red team"],
        "regulatory_framework_clarity": ["regulation", "governance", "policy", "compliance", "liability",
                                          "ai act", "executive order"],
        "institutional_trust": ["trust", "responsible ai", "ethical ai", "ai ethics"],
    }

    # ENERGY signals
    energy_terms = {
        "data_center_power_intensity": ["energy consumption", "power consumption", "carbon footprint",
                                         "sustainable ai", "green ai"],
        "training_energy_per_model": ["training energy", "training cost", "compute budget"],
    }

    # Score each lever
    lever_scores = {
        "COMPUTE": (compute_terms, efficiency_terms),
        "INDUSTRY": (industry_terms,),
        "SOCIETY": (society_terms,),
        "GOV": (gov_terms,),
        "ENERGY": (energy_terms,),
    }

    best_lever = "COMPUTE"  # default for ML papers
    best_sub = "cost_per_flop"
    best_score = 0

    for lever, term_dicts in lever_scores.items():
        for term_dict in term_dicts:
            for sub_var, keywords in term_dict.items():
                score = sum(1 for kw in keywords if kw in text)
                if score > best_score:
                    best_score = score
                    best_lever = lever
                    best_sub = sub_var

    # Default direction: most papers are positive signals (advancing capability)
    direction = "+"
    negative_indicators = ["limitation", "failure", "bias", "harmful", "risk", "challenge",
                           "barrier", "constraint", "concern"]
    if sum(1 for ni in negative_indicators if ni in text) >= 2:
        direction = "?"  # ambiguous — needs synthesis review

    # Confidence based on classification strength
    confidence = "high" if best_score >= 3 else "medium" if best_score >= 1 else "low"

    return {
        "lever_primary": best_lever,
        "sub_variable": best_sub,
        "direction": direction,
        "confidence": confidence,
    }


def entry_to_signal_record(entry: dict, cadence: str, pipeline_run_id: str,
                            batch_id: str) -> dict:
    """Convert a parsed ArXiv entry into an espresso·ai signal record."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Classify using the Scale Levers framework
    classification = classify_lever(
        entry["title"], entry["abstract"], entry["categories"]
    )

    # Extract publication date
    pub_date = ""
    try:
        pub_dt = datetime.fromisoformat(entry["published"].replace("Z", "+00:00"))
        pub_date = pub_dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        pub_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Build key facts from abstract (first 3 sentences or key claims)
    abstract = entry["abstract"]
    sentences = [s.strip() for s in abstract.replace("\n", " ").split(". ") if len(s.strip()) > 20]
    key_facts = sentences[:5]

    # Build tags
    tags = [f"arxiv_cat:{cat}" for cat in entry["categories"][:5]]
    if entry["authors"]:
        tags.append(f"first_author:{entry['authors'][0]}")

    # Truncate summary of abstract to 500 chars for the summary field
    summary_text = abstract[:497] + "..." if len(abstract) > 500 else abstract

    return {
        "signal_id": generate_signal_id(SOURCE_NAME, now),
        "source_name": SOURCE_NAME,
        "source_url": entry["abstract_url"] or entry["arxiv_id"],
        "fetch_timestamp": now,
        "agent_id": AGENT_ID,
        "cadence": cadence,
        "pipeline_run_id": pipeline_run_id,
        "collection_batch_id": batch_id,

        "lever_primary": classification["lever_primary"],
        "lever_secondary": None,
        "direction": classification["direction"],
        "sub_variable": classification["sub_variable"],
        "confidence": classification["confidence"],

        "title": entry["title"],
        "summary": summary_text,
        "key_facts": key_facts,
        "raw_content": abstract,  # Full abstract as raw content

        "publication_date": pub_date,
        "reporting_period": None,

        # Synthesis fields — left null for synthesis agent
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

        # Extra metadata for ArXiv-specific context
        "_arxiv_meta": {
            "arxiv_id": entry["arxiv_id"],
            "pdf_url": entry["pdf_url"],
            "authors": entry["authors"],
            "categories": entry["categories"],
            "comment": entry["comment"],
        }
    }


def deduplicate_entries(entries: list) -> list:
    """Remove duplicate papers (same ArXiv ID)."""
    seen = set()
    unique = []
    for entry in entries:
        aid = entry.get("arxiv_id", "")
        if aid and aid not in seen:
            seen.add(aid)
            unique.append(entry)
    return unique


# ─── Main Pipeline ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="espresso·ai ArXiv Signal Collector")
    parser.add_argument("--max-results", type=int, default=30,
                        help="Max results per query (default: 30)")
    parser.add_argument("--cadence", default="weekly",
                        choices=["daily", "weekly", "monthly", "quarterly", "annual"])
    parser.add_argument("--days-back", type=int, default=7,
                        help="Look back N days from today (default: 7)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print results without writing to disk")
    args = parser.parse_args()

    # Set up pipeline identifiers
    now = datetime.now(timezone.utc)
    pipeline_run_id = f"{now.strftime('%Y-%m-%d')}_{args.cadence}_{uuid.uuid4().hex[:8]}"
    batch_id = f"batch_{now.strftime('%Y%m%d_%H%M')}"

    start_date, end_date = get_date_range(args.days_back)

    print("=" * 70)
    print("espresso·ai — ArXiv Signal Collector")
    print("=" * 70)
    print(f"Pipeline run:  {pipeline_run_id}")
    print(f"Batch:         {batch_id}")
    print(f"Cadence:       {args.cadence}")
    print(f"Date range:    {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}")
    print(f"Max per query: {args.max_results}")
    print(f"Queries:       {len(SIGNAL_QUERIES)}")
    print("=" * 70)

    # Collect papers across all signal queries
    all_entries = []

    for i, query in enumerate(SIGNAL_QUERIES, 1):
        print(f"\n[{i}/{len(SIGNAL_QUERIES)}] Querying: {query[:60]}...")
        entries = query_arxiv(query, max_results=args.max_results)

        # Filter to date range
        in_range = [e for e in entries if is_within_date_range(e["published"], start_date, end_date)]
        all_entries.extend(in_range)

        print(f"  → {len(entries)} results, {len(in_range)} in date range")

        # Be polite to ArXiv API — 3 second delay between requests
        if i < len(SIGNAL_QUERIES):
            time.sleep(3)

    # Deduplicate
    unique_entries = deduplicate_entries(all_entries)
    print(f"\n{'=' * 70}")
    print(f"Total collected: {len(all_entries)} | Unique: {len(unique_entries)}")

    if not unique_entries:
        print("\nNo papers found in the target date range.")
        print("This could mean:")
        print("  - ArXiv indexing lag (papers may appear 1-2 days after submission)")
        print("  - The date range is too narrow")
        print("  - Try increasing --days-back")
        print("\nAttempting broader search without date filter...")

        # Fallback: collect recent papers without strict date filtering
        all_entries = []
        for i, query in enumerate(SIGNAL_QUERIES[:5], 1):  # Top 5 queries only for speed
            print(f"\n[{i}/5] Broad query: {query[:60]}...")
            entries = query_arxiv(query, max_results=args.max_results)
            all_entries.extend(entries)
            print(f"  → {len(entries)} results")
            if i < 5:
                time.sleep(3)

        unique_entries = deduplicate_entries(all_entries)
        print(f"\nBroad search: {len(unique_entries)} unique papers")

    if not unique_entries:
        print("\nNo results from ArXiv API. Exiting.")
        return

    # Convert to signal records
    signal_records = []
    for entry in unique_entries:
        record = entry_to_signal_record(entry, args.cadence, pipeline_run_id, batch_id)
        signal_records.append(record)

    # Print classification summary
    lever_counts = {}
    for rec in signal_records:
        lev = rec["lever_primary"]
        lever_counts[lev] = lever_counts.get(lev, 0) + 1

    print(f"\n{'─' * 40}")
    print("Classification Summary:")
    for lever, count in sorted(lever_counts.items(), key=lambda x: -x[1]):
        print(f"  {lever:12s}  {count:3d} papers")
    print(f"{'─' * 40}")

    # Write to JSONL file
    base_dir = Path(__file__).resolve().parent.parent.parent / "research_db" / "raw"
    base_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = get_date_range_prefix(start_date, end_date)
    output_file = base_dir / f"{date_prefix}_arxiv_{args.cadence}_signals.jsonl"

    if args.dry_run:
        print(f"\n[DRY RUN] Would write {len(signal_records)} records to {output_file}")
        # Print first 3 records as sample
        for rec in signal_records[:3]:
            print(f"\n  Title: {rec['title'][:80]}...")
            print(f"  Lever: {rec['lever_primary']} | Direction: {rec['direction']} | Sub: {rec['sub_variable']}")
            print(f"  URL:   {rec['source_url']}")
    else:
        with open(output_file, "a", encoding="utf-8") as f:
            for record in signal_records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        print(f"\n✓ Wrote {len(signal_records)} signal records to:")
        print(f"  {output_file}")

    # Write pipeline log
    log = {
        "pipeline_run_id": pipeline_run_id,
        "batch_id": batch_id,
        "cadence": args.cadence,
        "source": "arxiv",
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date_range": {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        },
        "queries_executed": len(SIGNAL_QUERIES),
        "total_results_raw": len(all_entries),
        "total_results_unique": len(unique_entries),
        "records_written": len(signal_records),
        "lever_distribution": lever_counts,
        "output_file": str(output_file),
    }

    log_file = base_dir / f"{date_prefix}_arxiv_pipeline_log.json"
    if not args.dry_run:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
        print(f"✓ Pipeline log: {log_file}")

    # Print top papers by title (quick scan for the operator)
    print(f"\n{'=' * 70}")
    print("TOP PAPERS (by recency):")
    print(f"{'=' * 70}")
    for i, rec in enumerate(signal_records[:15], 1):
        lever = rec["lever_primary"]
        direction = rec["direction"]
        title = rec["title"][:75]
        print(f"  {i:2d}. [{lever:8s} {direction}] {title}")

    if len(signal_records) > 15:
        print(f"  ... and {len(signal_records) - 15} more")

    print(f"\n{'=' * 70}")
    print("Done.")


if __name__ == "__main__":
    main()
