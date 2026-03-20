"""
espresso·ai — Signal Synthesis Pipeline

Reads raw JSONL signal files, deduplicates across sources, scores and ranks signals,
selects top signals per Scale Lever, and writes intermediate JSON for carousel generation.

Usage:
    python .claude/scripts/synthesize_signals.py \
        --cadence weekly --start-date 2026-03-12 --end-date 2026-03-19

Output:
    research_db/processed/{start}_{end}_{cadence}_carousel_data.json
    research_db/processed/{start}_{end}_{cadence}_deduped.jsonl
"""

import json
import argparse
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from collections import defaultdict


# ─── Configuration ───────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "research_db" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "research_db" / "processed"

VALID_LEVERS = {"COMPUTE", "ENERGY", "SOCIETY", "INDUSTRY", "CAPITAL", "GOV"}
VALID_DIRECTIONS = {"+", "-", "~", "?"}
LEVER_ORDER = ["COMPUTE", "ENERGY", "SOCIETY", "INDUSTRY", "CAPITAL", "GOV"]

# Signals per lever in the carousel
SIGNALS_PER_LEVER = 5

# Stopwords for title similarity
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "shall", "can", "its", "it", "this", "that", "these", "those", "with",
    "from", "by", "about", "into", "through", "during", "before", "after",
    "above", "below", "between", "same", "each", "every", "both", "few",
    "more", "most", "other", "some", "such", "no", "not", "only", "own",
    "s", "t", "just", "than", "too", "very", "how", "what", "which", "who",
    "whom", "when", "where", "why", "ai", "new", "also", "says", "said",
    "using", "based", "via", "per", "over", "now", "up", "out", "first",
}

# Title similarity threshold for deduplication
TITLE_OVERLAP_THRESHOLD = 0.5


# ─── URL Normalization ──────────────────────────────────────────────────────

def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        # Strip UTM and tracking parameters
        query = parsed.query
        if query:
            params = [p for p in query.split("&") if not p.startswith("utm_")]
            query = "&".join(params)
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            parsed.params,
            query,
            "",  # strip fragment
        ))
        return normalized
    except Exception:
        return url.strip().lower()


# ─── Title Similarity ───────────────────────────────────────────────────────

def title_words(title: str) -> set:
    """Extract significant words from a title."""
    words = set(re.findall(r"[a-z0-9]+", title.lower()))
    return words - STOPWORDS


def title_overlap(t1: str, t2: str) -> float:
    """Compute word overlap ratio between two titles."""
    w1, w2 = title_words(t1), title_words(t2)
    if not w1 or not w2:
        return 0.0
    overlap = len(w1 & w2)
    return overlap / min(len(w1), len(w2))


# ─── Confidence to numeric ──────────────────────────────────────────────────

CONFIDENCE_SCORE = {"high": 3, "medium": 2, "low": 1}


def confidence_value(record: dict) -> int:
    return CONFIDENCE_SCORE.get(record.get("confidence", "low"), 1)


# ─── Stage 1: Load & Parse ──────────────────────────────────────────────────

def load_signals(cadence: str, start_date: str, end_date: str) -> list[dict]:
    """Load all JSONL files matching the cadence window."""
    records = []
    matched_files = []

    for jsonl_path in sorted(RAW_DIR.glob(f"*_{cadence}_signals.jsonl")):
        name = jsonl_path.name
        # Extract date range from filename (format: YYYY-MM-DD_YYYY-MM-DD_...)
        parts = name.split("_")
        if len(parts) >= 2:
            file_start = parts[0]
            file_end = parts[1]
            # Include if date ranges overlap
            if file_start <= end_date and file_end >= start_date:
                matched_files.append(jsonl_path)

    if not matched_files:
        print(f"No JSONL files found for cadence={cadence}, {start_date} to {end_date}")
        print(f"Searched in: {RAW_DIR}")
        sys.exit(1)

    print(f"Loading {len(matched_files)} signal file(s):")
    for fpath in matched_files:
        file_records = 0
        with open(fpath) as fh:
            for line_num, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"  WARN: {fpath.name}:{line_num} — invalid JSON: {e}")
                    continue

                # Filter: in_scope must be true
                if not record.get("in_scope", True):
                    continue

                # Validate lever
                if record.get("lever_primary") not in VALID_LEVERS:
                    continue

                record["_source_file"] = fpath.name
                records.append(record)
                file_records += 1

        print(f"  {fpath.name}: {file_records} records")

    print(f"Total loaded: {len(records)}")
    return records


# ─── Stage 2: Cross-Source Deduplication ─────────────────────────────────────

def deduplicate(records: list[dict]) -> tuple[list[dict], int, list[dict]]:
    """
    Three-pass deduplication:
    1. URL normalization — group by normalized URL
    2. Title similarity — cluster by word overlap + same lever
    3. Entity co-reference — flag remaining candidates

    Returns (unique_records, duplicates_removed, flagged_clusters)
    """
    total_removed = 0

    # ─── Pass 1: URL-based deduplication ───
    url_groups = defaultdict(list)
    no_url = []

    for record in records:
        url = normalize_url(record.get("source_url", ""))
        if url and url not in ("", "http://", "https://"):
            url_groups[url].append(record)
        else:
            no_url.append(record)

    url_deduped = []
    for url, group in url_groups.items():
        if len(group) == 1:
            winner = group[0]
        else:
            # Keep the record with highest confidence, most key_facts, longest summary
            group.sort(key=lambda r: (
                confidence_value(r),
                len(r.get("key_facts", []) or []),
                len(r.get("summary", "") or ""),
            ), reverse=True)
            winner = group[0]
            winner["_corroboration_count"] = len(group)
            winner["_corroboration_sources"] = [
                r.get("agent_id", "unknown") for r in group[1:]
            ]
            total_removed += len(group) - 1

        url_deduped.append(winner)

    # Combine URL-deduped with no-URL records
    remaining = url_deduped + no_url

    # ─── Pass 2: Title similarity deduplication ───
    # Build clusters of similar titles with the same lever_primary
    used = [False] * len(remaining)
    title_clusters = []

    for i in range(len(remaining)):
        if used[i]:
            continue
        cluster = [i]
        used[i] = True
        for j in range(i + 1, len(remaining)):
            if used[j]:
                continue
            if remaining[i].get("lever_primary") != remaining[j].get("lever_primary"):
                continue
            t1 = remaining[i].get("title", "")
            t2 = remaining[j].get("title", "")
            if title_overlap(t1, t2) >= TITLE_OVERLAP_THRESHOLD:
                cluster.append(j)
                used[j] = True
        if len(cluster) > 1:
            title_clusters.append(cluster)

    # For each title cluster, keep the best record
    title_removed_indices = set()
    for cluster in title_clusters:
        cluster_records = [(idx, remaining[idx]) for idx in cluster]
        cluster_records.sort(key=lambda ir: (
            confidence_value(ir[1]),
            len(ir[1].get("key_facts", []) or []),
            len(ir[1].get("summary", "") or ""),
        ), reverse=True)

        winner_idx, winner = cluster_records[0]
        corr = winner.get("_corroboration_count", 1)
        winner["_corroboration_count"] = corr + len(cluster_records) - 1
        existing_sources = winner.get("_corroboration_sources", [])
        for idx, r in cluster_records[1:]:
            existing_sources.append(r.get("agent_id", "unknown"))
            title_removed_indices.add(idx)

        winner["_corroboration_sources"] = existing_sources

    title_deduped = [
        r for i, r in enumerate(remaining) if i not in title_removed_indices
    ]
    total_removed += len(title_removed_indices)

    # ─── Pass 3: Entity co-reference (flag only, don't auto-merge) ───
    # Extract entities: dollar amounts, company names
    entity_pattern = re.compile(
        r"\$[\d,.]+[BMK]?"  # dollar amounts
        r"|(?:OpenAI|Google|Microsoft|Meta|Amazon|NVIDIA|AMD|Anthropic|Apple"
        r"|Huawei|Alibaba|Samsung|Intel|TSMC|Nscale|Block|Tesla"
        r"|DeepMind|Mistral|xAI|Cohere|Inflection)"  # company names
        , re.IGNORECASE
    )

    flagged_clusters = []
    entity_groups = defaultdict(list)
    for i, record in enumerate(title_deduped):
        title = record.get("title", "")
        entities = set(e.lower() for e in entity_pattern.findall(title))
        lever = record.get("lever_primary", "")
        for entity in entities:
            key = f"{entity}|{lever}"
            entity_groups[key].append(i)

    cluster_id = 0
    seen_indices = set()
    for key, indices in entity_groups.items():
        if len(indices) > 1:
            # Only flag if not already merged
            new_indices = [i for i in indices if i not in seen_indices]
            if len(new_indices) > 1:
                cluster_id += 1
                for idx in new_indices:
                    title_deduped[idx]["_candidate_cluster_id"] = cluster_id
                    seen_indices.add(idx)
                flagged_clusters.append({
                    "cluster_id": cluster_id,
                    "entity_key": key,
                    "titles": [title_deduped[i].get("title", "") for i in new_indices],
                })

    return title_deduped, total_removed, flagged_clusters


# ─── Stage 3: Signal Scoring ────────────────────────────────────────────────

def score_signals(records: list[dict]) -> list[dict]:
    """
    Score each signal on a 1-10 scale based on:
    - Source confidence (0.20)
    - Cross-source corroboration (0.25)
    - Key facts density (0.15)
    - Lever scarcity premium (0.10)
    - Data quality penalty (0.10)
    - Recency (0.10)
    - Summary quality (0.10)
    """
    if not records:
        return records

    # Pre-compute lever counts for scarcity premium
    lever_counts = defaultdict(int)
    for r in records:
        lever_counts[r.get("lever_primary", "")] += 1

    total_signals = len(records)
    avg_per_lever = total_signals / len(VALID_LEVERS) if VALID_LEVERS else 1

    # Pre-compute max key_facts count
    max_key_facts = max(
        (len(r.get("key_facts", []) or []) for r in records), default=1
    )
    if max_key_facts == 0:
        max_key_facts = 1

    # Pre-compute max summary length
    max_summary_len = max(
        (len(r.get("summary", "") or "") for r in records), default=1
    )
    if max_summary_len == 0:
        max_summary_len = 1

    # Parse date range for recency
    dates = []
    for r in records:
        pub_date = r.get("publication_date", "")
        if pub_date:
            try:
                dates.append(datetime.strptime(pub_date[:10], "%Y-%m-%d"))
            except (ValueError, TypeError):
                pass

    if dates:
        min_date = min(dates)
        date_range = (max(dates) - min_date).days or 1
    else:
        min_date = None
        date_range = 1

    for record in records:
        # Factor 1: Source confidence (0.20)
        conf_score = confidence_value(record) / 3.0  # 0.33 to 1.0

        # Factor 2: Cross-source corroboration (0.25)
        corr_count = record.get("_corroboration_count", 1)
        corr_score = min(corr_count / 3.0, 1.0)  # 3+ sources = max

        # Factor 3: Key facts density (0.15)
        key_facts = record.get("key_facts", []) or []
        kf_score = len(key_facts) / max_key_facts

        # Factor 4: Lever scarcity premium (0.10)
        lever = record.get("lever_primary", "")
        lever_count = lever_counts.get(lever, avg_per_lever)
        scarcity_ratio = avg_per_lever / lever_count if lever_count > 0 else 1.0
        scarcity_score = min(scarcity_ratio, 2.0) / 2.0  # cap at 2x

        # Factor 5: Data quality penalty (0.10)
        quality_flags = record.get("data_quality_flags", []) or []
        penalty_flags = {
            "missing_key_facts", "unverified_claim", "low_source_credibility",
            "unknown_domain", "url_not_in_citations", "indirect_source",
        }
        penalty_count = len(set(quality_flags) & penalty_flags)
        quality_score = max(1.0 - (penalty_count * 0.25), 0.0)

        # Factor 6: Recency (0.10)
        pub_date = record.get("publication_date", "")
        if pub_date and min_date:
            try:
                parsed_date = datetime.strptime(pub_date[:10], "%Y-%m-%d")
                days_from_start = (parsed_date - min_date).days
                recency_score = days_from_start / date_range
            except (ValueError, TypeError):
                recency_score = 0.5
        else:
            recency_score = 0.5

        # Factor 7: Summary quality (0.10)
        summary = record.get("summary", "") or ""
        summary_score = len(summary) / max_summary_len

        # Weighted composite
        raw_score = (
            conf_score * 0.20
            + corr_score * 0.25
            + kf_score * 0.15
            + scarcity_score * 0.10
            + quality_score * 0.10
            + recency_score * 0.10
            + summary_score * 0.10
        )

        # Map 0.0-1.0 raw score to 1-10 integer scale
        signal_strength = max(1, min(10, round(raw_score * 10)))
        record["signal_strength"] = signal_strength

    return records


# ─── Stage 4: Selection ─────────────────────────────────────────────────────

def select_top_signals(
    records: list[dict], per_lever: int = SIGNALS_PER_LEVER
) -> dict[str, list[dict]]:
    """
    Select top N signals per lever with diversity filters:
    - Sort by signal_strength descending
    - Ensure direction diversity (at least one contrasting direction if possible)
    - Prefer source diversity when scores are close
    """
    lever_groups = defaultdict(list)
    for r in records:
        lever_groups[r.get("lever_primary", "")].append(r)

    selections = {}
    for lever in LEVER_ORDER:
        candidates = lever_groups.get(lever, [])
        if not candidates:
            selections[lever] = []
            continue

        # Sort by signal_strength descending, then corroboration, then confidence
        candidates.sort(key=lambda r: (
            r.get("signal_strength", 0),
            r.get("_corroboration_count", 1),
            confidence_value(r),
        ), reverse=True)

        selected = []
        used_agents = set()
        used_directions = set()

        # First pass: take the top candidates
        for c in candidates:
            if len(selected) >= per_lever:
                break
            selected.append(c)
            used_agents.add(c.get("agent_id", ""))
            used_directions.add(c.get("direction", ""))

        # Direction diversity check: if all selected have same direction,
        # try to swap the weakest for one with a different direction
        if len(used_directions) == 1 and len(selected) == per_lever:
            for c in candidates[per_lever:]:
                if c.get("direction", "") not in used_directions:
                    # Swap out the lowest-scored selected signal
                    selected[-1] = c
                    break

        selections[lever] = selected

    return selections


# ─── Stage 5: Output ────────────────────────────────────────────────────────

def compute_direction_breakdown(records: list[dict]) -> dict[str, int]:
    """Count signals by direction."""
    breakdown = defaultdict(int)
    for r in records:
        d = r.get("direction", "?")
        breakdown[d] += 1
    return dict(breakdown)


def dominant_direction(breakdown: dict[str, int]) -> str:
    """Return the direction with the most signals."""
    if not breakdown:
        return "?"
    return max(breakdown, key=breakdown.get)


def clean_record_for_output(record: dict) -> dict:
    """Remove internal fields from output."""
    output = {}
    for key, value in record.items():
        if key.startswith("_") and key not in (
            "_corroboration_count", "_corroboration_sources", "_candidate_cluster_id"
        ):
            continue
        output[key] = value
    return output


def write_outputs(
    cadence: str,
    start_date: str,
    end_date: str,
    all_records: list[dict],
    unique_records: list[dict],
    duplicates_removed: int,
    flagged_clusters: list[dict],
    selections: dict[str, list[dict]],
    source_files: list[str],
) -> tuple[Path, Path]:
    """Write intermediate JSON and deduped JSONL."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    prefix = f"{start_date}_{end_date}_{cadence}"

    # Build lever summaries
    lever_records = defaultdict(list)
    for r in unique_records:
        lever_records[r.get("lever_primary", "")].append(r)

    lever_summaries = {}
    for lever in LEVER_ORDER:
        records_for_lever = lever_records.get(lever, [])
        breakdown = compute_direction_breakdown(records_for_lever)
        lever_summaries[lever] = {
            "signal_count": len(records_for_lever),
            "direction_breakdown": breakdown,
            "dominant_direction": dominant_direction(breakdown),
            "top_signals": [
                clean_record_for_output(s) for s in selections.get(lever, [])
            ],
        }

    # Overall stats
    overall_breakdown = compute_direction_breakdown(unique_records)

    carousel_data = {
        "meta": {
            "cadence": cadence,
            "date_window": {"start": start_date, "end": end_date},
            "total_signals_loaded": len(all_records),
            "duplicates_removed": duplicates_removed,
            "unique_signals": len(unique_records),
            "source_files": source_files,
            "pipeline_run_id": f"{prefix}_synth_{uuid.uuid4().hex[:8]}",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "lever_summaries": lever_summaries,
        "overall_stats": {
            "total_unique": len(unique_records),
            "source_pipeline_count": len(source_files),
            "lever_count": len(LEVER_ORDER),
            "dominant_direction": dominant_direction(overall_breakdown),
            "direction_breakdown": overall_breakdown,
        },
        "flagged_duplicate_clusters": flagged_clusters,
    }

    # Write carousel data JSON
    json_path = PROCESSED_DIR / f"{prefix}_carousel_data.json"
    with open(json_path, "w") as fh:
        json.dump(carousel_data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    # Write deduped JSONL
    jsonl_path = PROCESSED_DIR / f"{prefix}_deduped.jsonl"
    with open(jsonl_path, "w") as fh:
        for record in unique_records:
            fh.write(json.dumps(clean_record_for_output(record), ensure_ascii=False) + "\n")

    return json_path, jsonl_path


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="espresso·ai Signal Synthesis Pipeline"
    )
    parser.add_argument(
        "--cadence", required=True,
        choices=["daily", "weekly", "monthly", "quarterly", "annual"],
    )
    parser.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--signals-per-lever", type=int, default=SIGNALS_PER_LEVER,
        help=f"Number of top signals per lever (default: {SIGNALS_PER_LEVER})",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("espresso·ai — Signal Synthesis Pipeline")
    print("=" * 60)
    print(f"Cadence:    {args.cadence}")
    print(f"Window:     {args.start_date} → {args.end_date}")
    print()

    # Stage 1: Load
    print("─── Stage 1: Load & Parse ───")
    all_records = load_signals(args.cadence, args.start_date, args.end_date)
    source_files = list(set(r.get("_source_file", "") for r in all_records))
    print()

    # Stage 2: Deduplicate
    print("─── Stage 2: Cross-Source Deduplication ───")
    unique_records, duplicates_removed, flagged_clusters = deduplicate(all_records)
    print(f"Duplicates removed: {duplicates_removed}")
    print(f"Unique signals:     {len(unique_records)}")
    if flagged_clusters:
        print(f"Flagged clusters:   {len(flagged_clusters)} (for editorial review)")
    print()

    # Stage 3: Score
    print("─── Stage 3: Signal Scoring ───")
    unique_records = score_signals(unique_records)
    scores = [r.get("signal_strength", 0) for r in unique_records]
    if scores:
        avg_score = sum(scores) / len(scores)
        print(f"Score range: {min(scores)}–{max(scores)}, avg: {avg_score:.1f}")
        # Distribution
        dist = defaultdict(int)
        for s in scores:
            dist[s] += 1
        print("Distribution:", " | ".join(
            f"{k}:{v}" for k, v in sorted(dist.items())
        ))
    print()

    # Stage 4: Select
    print("─── Stage 4: Selection ───")
    selections = select_top_signals(unique_records, args.signals_per_lever)
    for lever in LEVER_ORDER:
        selected = selections.get(lever, [])
        directions = [s.get("direction", "?") for s in selected]
        print(f"  {lever:10s}: {len(selected)} signals selected  "
              f"[{', '.join(directions)}]")
    print()

    # Stage 5: Output
    print("─── Stage 5: Output ───")
    json_path, jsonl_path = write_outputs(
        cadence=args.cadence,
        start_date=args.start_date,
        end_date=args.end_date,
        all_records=all_records,
        unique_records=unique_records,
        duplicates_removed=duplicates_removed,
        flagged_clusters=flagged_clusters,
        selections=selections,
        source_files=source_files,
    )
    print(f"Carousel data: {json_path}")
    print(f"Deduped JSONL:  {jsonl_path}")
    print()

    # Summary
    print("=" * 60)
    print("SYNTHESIS COMPLETE")
    print("=" * 60)
    print(f"Total loaded:       {len(all_records)}")
    print(f"Duplicates removed: {duplicates_removed}")
    print(f"Unique signals:     {len(unique_records)}")
    print(f"Source files:       {len(source_files)}")
    print()
    print("Signals by lever:")
    lever_counts = defaultdict(int)
    for r in unique_records:
        lever_counts[r.get("lever_primary", "")] += 1
    for lever in LEVER_ORDER:
        count = lever_counts.get(lever, 0)
        selected = len(selections.get(lever, []))
        print(f"  {lever:10s}: {count:4d} total, {selected} selected")
    print()
    print("Signals by direction:")
    dir_counts = compute_direction_breakdown(unique_records)
    for d in ["+", "-", "~", "?"]:
        print(f"  {d:5s}: {dir_counts.get(d, 0)}")


if __name__ == "__main__":
    main()
