"""
espresso·ai — Influencer Signal Consolidation Script

Reads per-group JSONL fragment files from research_db/raw/, validates, deduplicates,
and writes a single consolidated JSONL file + pipeline log.

Usage:
    python .claude/scripts/consolidate_influencer_signals.py \
        --cadence weekly --start-date 2026-03-12 --end-date 2026-03-19
"""

import json
import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse


# ─── Configuration ───────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "research_db" / "raw"

REQUIRED_FIELDS = [
    "signal_id", "source_name", "source_url", "fetch_timestamp",
    "agent_id", "cadence", "pipeline_run_id", "collection_batch_id",
    "lever_primary", "direction", "sub_variable", "confidence",
    "title", "summary", "in_scope", "schema_version",
]

VALID_LEVERS = {"COMPUTE", "ENERGY", "SOCIETY", "INDUSTRY", "CAPITAL", "GOV"}
VALID_DIRECTIONS = {"+", "-", "~", "?"}

AGENT_TO_GROUP = {
    "influencer-ceo-collector": "ceo_industry_leaders",
    "influencer-researcher-collector": "researchers_scientists",
    "influencer-lab-collector": "research_labs",
    "influencer-policy-collector": "policy_governance",
    "influencer-enterprise-collector": "enterprise_industry",
    "influencer-futurist-collector": "futurists_intellectuals",
    "influencer-china-collector": "china_asia_leaders",
    "influencer-safety-collector": "safety_alignment",
    "influencer-founder-collector": "founders_emerging_labs",
    "influencer-investor-collector": "investors_capital",
}


# ─── URL Normalization ──────────────────────────────────────────────────────

def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication: lowercase host, strip trailing slash, remove fragment."""
    try:
        parsed = urlparse(url.strip())
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            parsed.params,
            parsed.query,
            "",  # strip fragment
        ))
        return normalized
    except Exception:
        return url.strip().lower()


# ─── Validation ─────────────────────────────────────────────────────────────

def validate_record(record: dict, line_num: int, filepath: str) -> list[str]:
    """Validate a signal record. Returns list of issues (empty = valid)."""
    issues = []
    for field in REQUIRED_FIELDS:
        if field not in record or record[field] is None:
            issues.append(f"{filepath}:{line_num} — missing required field '{field}'")

    if record.get("lever_primary") and record["lever_primary"] not in VALID_LEVERS:
        issues.append(f"{filepath}:{line_num} — invalid lever_primary '{record['lever_primary']}'")

    if record.get("direction") and record["direction"] not in VALID_DIRECTIONS:
        issues.append(f"{filepath}:{line_num} — invalid direction '{record['direction']}'")

    return issues


# ─── Deduplication ──────────────────────────────────────────────────────────

def deduplicate(records: list[dict]) -> tuple[list[dict], int]:
    """Deduplicate by normalized source_url and case-insensitive title. Returns (unique records, count removed)."""
    seen_urls = set()
    seen_titles = set()
    unique = []
    duplicates = 0

    for record in records:
        url_key = normalize_url(record.get("source_url", ""))
        title_key = record.get("title", "").strip().lower()

        if url_key in seen_urls or (title_key and title_key in seen_titles):
            duplicates += 1
            continue

        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        unique.append(record)

    return unique, duplicates


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Consolidate influencer signal fragments")
    parser.add_argument("--cadence", required=True, choices=["daily", "weekly", "monthly", "quarterly", "annual"])
    parser.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End date YYYY-MM-DD")
    args = parser.parse_args()

    prefix = f"{args.start_date}_{args.end_date}_influencer_"
    suffix = f"_{args.cadence}_signals.jsonl"

    # Find per-group fragment files
    fragment_files = sorted(RAW_DIR.glob(f"{prefix}*{suffix}"))

    # Exclude the consolidated output file itself
    consolidated_name = f"{args.start_date}_{args.end_date}_influencer_{args.cadence}_signals.jsonl"
    fragment_files = [f for f in fragment_files if f.name != consolidated_name]

    if not fragment_files:
        print(f"No fragment files found matching pattern: {prefix}*{suffix}")
        print(f"Looked in: {RAW_DIR}")
        sys.exit(1)

    print(f"Found {len(fragment_files)} fragment file(s):")
    for f in fragment_files:
        print(f"  {f.name}")

    # Read all records
    all_records = []
    signals_by_agent = {}
    signals_by_group = {}
    validation_issues = []

    for filepath in fragment_files:
        with open(filepath) as fh:
            for line_num, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    validation_issues.append(f"{filepath.name}:{line_num} — invalid JSON: {e}")
                    continue

                issues = validate_record(record, line_num, filepath.name)
                validation_issues.extend(issues)

                agent_id = record.get("agent_id", "unknown")
                group = AGENT_TO_GROUP.get(agent_id, agent_id)
                signals_by_agent[agent_id] = signals_by_agent.get(agent_id, 0) + 1
                signals_by_group[group] = signals_by_group.get(group, 0) + 1

                all_records.append(record)

    if validation_issues:
        print(f"\nValidation warnings ({len(validation_issues)}):")
        for issue in validation_issues[:20]:
            print(f"  {issue}")
        if len(validation_issues) > 20:
            print(f"  ... and {len(validation_issues) - 20} more")

    # Deduplicate
    unique_records, duplicates_removed = deduplicate(all_records)

    # Compute stats
    lever_counts = {}
    direction_counts = {}
    for r in unique_records:
        lp = r.get("lever_primary", "UNKNOWN")
        lever_counts[lp] = lever_counts.get(lp, 0) + 1
        d = r.get("direction", "?")
        direction_counts[d] = direction_counts.get(d, 0) + 1

    # Write consolidated JSONL
    output_jsonl = RAW_DIR / consolidated_name
    with open(output_jsonl, "w") as fh:
        for record in unique_records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Build pipeline log
    run_id = f"{args.start_date}_{args.end_date}_influencer_{args.cadence}_{uuid.uuid4().hex[:8]}"
    pipeline_log = {
        "pipeline_run_id": run_id,
        "agent_type": "influencer-research",
        "cadence": args.cadence,
        "date_window": {
            "start": args.start_date,
            "end": args.end_date,
        },
        "execution_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_signals": len(unique_records),
        "duplicates_removed": duplicates_removed,
        "signals_by_agent": signals_by_agent,
        "signals_by_group": signals_by_group,
        "signals_by_lever": lever_counts,
        "signals_by_direction": direction_counts,
        "influencer_coverage": {
            "total_influencers": 71,
            "groups": len(signals_by_group),
            "agents_completed": len(signals_by_agent),
        },
        "schema_version": "1.0",
    }

    log_path = RAW_DIR / f"{args.start_date}_{args.end_date}_influencer_{args.cadence}_pipeline_log.json"
    with open(log_path, "w") as fh:
        json.dump(pipeline_log, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    # Clean up fragment files
    for filepath in fragment_files:
        filepath.unlink()
        print(f"  Removed fragment: {filepath.name}")

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"CONSOLIDATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"Pipeline run:      {run_id}")
    print(f"Date window:       {args.start_date} → {args.end_date}")
    print(f"Total signals:     {len(unique_records)}")
    print(f"Duplicates removed:{duplicates_removed}")
    print(f"\nSignals by group:")
    for group, count in sorted(signals_by_group.items()):
        print(f"  {group:30s} {count:3d}")
    print(f"\nSignals by lever:")
    for lever, count in sorted(lever_counts.items()):
        print(f"  {lever:10s} {count:3d}")
    print(f"\nSignals by direction:")
    for direction, count in sorted(direction_counts.items()):
        print(f"  {direction:5s} {count:3d}")
    print(f"\nOutput:  {output_jsonl}")
    print(f"Log:     {log_path}")


if __name__ == "__main__":
    main()
