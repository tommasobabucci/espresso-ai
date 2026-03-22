#!/usr/bin/env python3
"""
espresso·ai — GitHub & Open-Source Signal Collector
Queries GitHub API for releases from curated AI repos, searches for trending
AI repositories, and checks Hugging Face for new high-impact models.
Classifies against Scale Levers and outputs signal records to research_db/raw/ in JSONL format.

Usage:
    python .claude/scripts/collect_github_signals.py --cadence weekly [--days-back 7] [--test] [--dry-run]
"""

import json
import os
import uuid
import hashlib
import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
import requests

# ─── Configuration ───────────────────────────────────────────────────────────

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env" / ".env")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_API_URL = "https://api.github.com"
HF_API_URL = "https://huggingface.co/api"
AGENT_ID = "github-oss-collector"
SCHEMA_VERSION = "1.0"
SOURCE_NAME = "company_announcement"

# ─── Curated Repository List ────────────────────────────────────────────────
# High-signal AI/ML repositories whose releases are worth tracking.

CURATED_REPOS = [
    # AI Frameworks & Libraries
    {"repo": "huggingface/transformers", "lever_hint": "COMPUTE", "category": "framework"},
    {"repo": "vllm-project/vllm", "lever_hint": "COMPUTE", "category": "framework"},
    {"repo": "langchain-ai/langchain", "lever_hint": "INDUSTRY", "category": "framework"},
    {"repo": "ollama/ollama", "lever_hint": "SOCIETY", "category": "framework"},
    {"repo": "ggerganov/llama.cpp", "lever_hint": "COMPUTE", "category": "framework"},
    {"repo": "run-llama/llama_index", "lever_hint": "INDUSTRY", "category": "framework"},

    # Model Families
    {"repo": "meta-llama/llama-models", "lever_hint": "COMPUTE", "category": "model"},
    {"repo": "deepseek-ai/DeepSeek-V3", "lever_hint": "COMPUTE", "category": "model"},
    {"repo": "deepseek-ai/DeepSeek-R1", "lever_hint": "COMPUTE", "category": "model"},
    {"repo": "QwenLM/Qwen2.5", "lever_hint": "COMPUTE", "category": "model"},
    {"repo": "mistralai/mistral-inference", "lever_hint": "COMPUTE", "category": "model"},
    {"repo": "google/gemma_pytorch", "lever_hint": "COMPUTE", "category": "model"},
    {"repo": "stabilityai/stable-diffusion", "lever_hint": "COMPUTE", "category": "model"},

    # Infrastructure & SDKs
    {"repo": "openai/openai-python", "lever_hint": "INDUSTRY", "category": "infrastructure"},
    {"repo": "anthropics/anthropic-sdk-python", "lever_hint": "INDUSTRY", "category": "infrastructure"},
    {"repo": "mlc-ai/mlc-llm", "lever_hint": "COMPUTE", "category": "infrastructure"},
    {"repo": "NVIDIA/TensorRT-LLM", "lever_hint": "COMPUTE", "category": "infrastructure"},
    {"repo": "pytorch/pytorch", "lever_hint": "COMPUTE", "category": "infrastructure"},

    # Agent & Tool Frameworks
    {"repo": "microsoft/autogen", "lever_hint": "INDUSTRY", "category": "agent_framework"},
    {"repo": "crewAIInc/crewAI", "lever_hint": "INDUSTRY", "category": "agent_framework"},
    {"repo": "BerriAI/litellm", "lever_hint": "INDUSTRY", "category": "infrastructure"},
    {"repo": "letta-ai/letta", "lever_hint": "INDUSTRY", "category": "agent_framework"},
    {"repo": "stanford-oval/storm", "lever_hint": "INDUSTRY", "category": "agent_framework"},

    # Evaluation & Benchmarks
    {"repo": "EleutherAI/lm-evaluation-harness", "lever_hint": "COMPUTE", "category": "evaluation"},
    {"repo": "huggingface/open_llm_leaderboard", "lever_hint": "COMPUTE", "category": "evaluation"},
]

# ─── GitHub Search Queries ──────────────────────────────────────────────────
# Used to discover new trending AI repos (not in the curated list).

SEARCH_QUERIES = [
    {"query": "llm language model", "lever_hint": "COMPUTE"},
    {"query": "AI agent autonomous", "lever_hint": "INDUSTRY"},
    {"query": "diffusion generative model", "lever_hint": "COMPUTE"},
    {"query": "RAG retrieval augmented", "lever_hint": "INDUSTRY"},
    {"query": "machine learning framework", "lever_hint": "COMPUTE"},
]

# ─── Hugging Face Search Filters ────────────────────────────────────────────

HF_PIPELINE_TAGS = [
    "text-generation",
    "text2text-generation",
    "image-to-text",
    "text-to-image",
    "automatic-speech-recognition",
]

# ─── Star Thresholds by Cadence ─────────────────────────────────────────────

STAR_THRESHOLDS = {
    "daily": 1000,
    "weekly": 500,
    "monthly": 200,
    "quarterly": 100,
    "annual": 50,
}

# ─── Helper Functions ────────────────────────────────────────────────────────


def generate_signal_id(source_name: str, timestamp: str) -> str:
    """Generate unique signal ID per schema: YYYYMMDD-source_name-HHMMSS-5char"""
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


def github_request(path: str, params: dict = None) -> dict | list | None:
    """Make a GitHub API request with optional auth token."""
    url = f"{GITHUB_API_URL}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "espresso-ai/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 404:
            print(f"  [WARN] Not found: {path}")
            return None
        if resp.status_code == 403:
            print(f"  [WARN] Rate limited or forbidden: {path}")
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] GitHub request failed: {e}")
        return None


def hf_request(path: str, params: dict = None) -> list | None:
    """Make a Hugging Face API request (no auth needed for public data)."""
    url = f"{HF_API_URL}{path}"
    headers = {"User-Agent": "espresso-ai/1.0"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] Hugging Face API request failed: {e}")
        return None


# ─── Signal Classification ──────────────────────────────────────────────────

SUB_VAR_KEYWORDS = {
    "COMPUTE": {
        "manufacturing_capacity": ["chip", "semiconductor", "fabrication", "wafer", "tsmc"],
        "cost_per_flop": ["inference cost", "quantization", "pruning", "distillation",
                          "model compression", "efficient inference", "speculative decoding",
                          "kv cache", "cost per token"],
        "energy_efficiency": ["energy efficient", "power efficient", "flop per watt", "green ai"],
        "data_center_buildout": ["data center", "rack capacity", "hyperscale"],
        "custom_silicon_adoption": ["tpu", "trainium", "custom silicon", "accelerator", "cuda"],
        "architectural_diversity": ["neuromorphic", "mamba", "state space", "mixture of experts",
                                    "moe", "rwkv", "transformer alternative"],
    },
    "INDUSTRY": {
        "workflow_integration_depth": ["ai agent", "autonomous agent", "tool use", "function calling",
                                       "code generation", "retrieval augmented", "rag", "agentic",
                                       "workflow", "integration", "sdk", "api"],
        "production_deployment_rate": ["production", "deployment", "enterprise", "scale"],
        "cross_sector_diffusion": ["healthcare", "medical", "legal", "financial", "manufacturing"],
        "business_model_reinvention": ["open source", "license", "commercial", "pricing"],
    },
    "SOCIETY": {
        "skill_diffusion_rate": ["open source", "apache", "mit license", "permissive",
                                  "democratiz", "accessible", "local", "on-device"],
        "ai_literacy_distribution": ["tutorial", "education", "beginner", "documentation"],
        "incident_impact_on_trust": ["safety", "alignment", "bias", "harmful", "guardrail"],
    },
    "GOV": {
        "alignment_and_safety_maturity": ["safety", "red team", "evaluation", "benchmark",
                                           "interpretability", "alignment"],
    },
    "ENERGY": {
        "training_energy_per_model": ["training cost", "compute budget", "gpu hours",
                                       "training time", "energy consumption"],
    },
    "CAPITAL": {
        "valuation_multiple_dynamics": ["funding", "valuation", "series", "investment"],
    },
}

POSITIVE_INDICATORS = [
    "release", "launch", "new", "major", "breakthrough", "improvement",
    "faster", "efficient", "open source", "support", "feature", "update",
]
NEGATIVE_INDICATORS = [
    "deprecat", "removal", "breaking", "security", "vulnerability",
    "concern", "limitation", "restrict",
]


def classify_signal(title: str, description: str, lever_hint: str) -> dict:
    """Classify a signal into the Scale Levers framework."""
    text = (title + " " + description).lower()

    best_lever = lever_hint
    best_sub = None
    best_score = 0

    for lever, sub_vars in SUB_VAR_KEYWORDS.items():
        for sub_var, keywords in sub_vars.items():
            score = sum(1 for kw in keywords if kw in text)
            if lever == lever_hint:
                score += 1  # tiebreaker for hint
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

    real_score = best_score - 1 if best_lever == lever_hint else best_score
    confidence = "high" if real_score >= 3 else "medium" if real_score >= 1 else "low"

    return {
        "lever_primary": best_lever,
        "sub_variable": best_sub or "pending_classification",
        "direction": direction,
        "confidence": confidence,
    }


# ─── Date Helpers ────────────────────────────────────────────────────────────


def is_within_date_range(date_str: str, start: datetime, end: datetime) -> bool:
    """Check if an ISO date string falls within the target date range."""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return start <= dt <= end
    except (ValueError, TypeError):
        return False


def parse_date(date_str: str) -> str:
    """Parse an ISO date string to YYYY-MM-DD."""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ─── Collectors ──────────────────────────────────────────────────────────────


def collect_github_releases(start: datetime, end: datetime) -> list[dict]:
    """Collect releases from curated repos within the date range."""
    entries = []

    for i, repo_info in enumerate(CURATED_REPOS, 1):
        repo = repo_info["repo"]
        print(f"  [{i}/{len(CURATED_REPOS)}] {repo}...")

        releases = github_request(f"/repos/{repo}/releases", {"per_page": 10})
        if not releases or not isinstance(releases, list):
            print(f"    → No releases found")
            continue

        in_range = 0
        for release in releases:
            pub_date = release.get("published_at", "")
            if not pub_date or not is_within_date_range(pub_date, start, end):
                continue

            tag = release.get("tag_name", "")
            name = release.get("name", "") or tag
            body = release.get("body", "") or ""
            url = release.get("html_url", "")
            is_prerelease = release.get("prerelease", False)

            # Truncate body to first 1000 chars for summary
            body_truncated = body[:1000] if len(body) > 1000 else body

            entries.append({
                "type": "release",
                "repo": repo,
                "tag": tag,
                "name": name,
                "body": body_truncated,
                "url": url,
                "published_at": pub_date,
                "is_prerelease": is_prerelease,
                "lever_hint": repo_info["lever_hint"],
                "category": repo_info["category"],
            })
            in_range += 1

        if in_range > 0:
            print(f"    → {in_range} release(s) in date range")

        # Respect GitHub API rate limits
        if i < len(CURATED_REPOS):
            time.sleep(0.5 if GITHUB_TOKEN else 2)

    return entries


def collect_trending_repos(start: datetime, end: datetime, star_threshold: int) -> list[dict]:
    """Search GitHub for newly created AI repos with high star counts."""
    entries = []
    curated_names = {r["repo"].lower() for r in CURATED_REPOS}
    start_str = start.strftime("%Y-%m-%d")

    for i, sq in enumerate(SEARCH_QUERIES, 1):
        query = sq["query"]
        print(f"  [{i}/{len(SEARCH_QUERIES)}] Searching: {query}...")

        params = {
            "q": f"{query} created:>={start_str} stars:>={star_threshold}",
            "sort": "stars",
            "order": "desc",
            "per_page": 10,
        }
        result = github_request("/search/repositories", params)
        if not result or "items" not in result:
            print(f"    → No results")
            continue

        found = 0
        for repo in result["items"]:
            full_name = repo.get("full_name", "")
            if full_name.lower() in curated_names:
                continue  # skip curated repos (already collected via releases)

            created_at = repo.get("created_at", "")
            if not is_within_date_range(created_at, start, end):
                continue

            entries.append({
                "type": "trending",
                "repo": full_name,
                "name": repo.get("name", ""),
                "description": repo.get("description", "") or "",
                "url": repo.get("html_url", ""),
                "stars": repo.get("stargazers_count", 0),
                "language": repo.get("language", ""),
                "license": repo.get("license", {}).get("spdx_id", "unknown") if repo.get("license") else "unknown",
                "created_at": created_at,
                "published_at": created_at,
                "topics": repo.get("topics", []),
                "lever_hint": sq["lever_hint"],
                "category": "trending",
            })
            found += 1

        print(f"    → {found} new repos above {star_threshold} stars")

        if i < len(SEARCH_QUERIES):
            time.sleep(1 if GITHUB_TOKEN else 3)

    return entries


def collect_hf_models(start: datetime, end: datetime) -> list[dict]:
    """Collect recently updated high-impact models from Hugging Face."""
    entries = []
    seen_models = set()

    for tag in HF_PIPELINE_TAGS:
        print(f"  Searching HF: {tag}...")

        params = {
            "sort": "lastModified",
            "direction": "-1",
            "limit": "20",
            "pipeline_tag": tag,
        }
        models = hf_request("/models", params)
        if not models or not isinstance(models, list):
            print(f"    → No results")
            continue

        found = 0
        for model in models:
            model_id = model.get("modelId", "")
            if model_id in seen_models:
                continue

            last_modified = model.get("lastModified", "")
            if not last_modified or not is_within_date_range(last_modified, start, end):
                continue

            downloads = model.get("downloads", 0)
            if downloads < 10000:
                continue

            seen_models.add(model_id)
            entries.append({
                "type": "hf_model",
                "repo": model_id,
                "name": model_id.split("/")[-1] if "/" in model_id else model_id,
                "description": model.get("pipeline_tag", "") + " model",
                "url": f"https://huggingface.co/{model_id}",
                "downloads": downloads,
                "likes": model.get("likes", 0),
                "pipeline_tag": model.get("pipeline_tag", ""),
                "library_name": model.get("library_name", ""),
                "published_at": last_modified,
                "lever_hint": "COMPUTE",
                "category": "model",
            })
            found += 1

        print(f"    → {found} models with ≥10K downloads")
        time.sleep(0.5)

    return entries


# ─── Signal Record Builder ──────────────────────────────────────────────────


def entry_to_signal_record(entry: dict, cadence: str,
                            pipeline_run_id: str, batch_id: str) -> dict:
    """Convert a collected entry into an espresso·ai signal record."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry_type = entry["type"]

    # Build title
    if entry_type == "release":
        title = f"{entry['repo']}: {entry['name']}"[:200]
        description = entry.get("body", "")
    elif entry_type == "trending":
        title = f"New trending repo: {entry['repo']} ({entry.get('stars', 0)} stars)"[:200]
        description = entry.get("description", "")
    elif entry_type == "hf_model":
        title = f"HF model update: {entry['repo']} ({entry.get('downloads', 0):,} downloads)"[:200]
        description = entry.get("description", "")
    else:
        title = entry.get("name", "Unknown")[:200]
        description = ""

    # Classify
    classification = classify_signal(title, description, entry["lever_hint"])

    # Publication date
    pub_date = parse_date(entry.get("published_at", ""))

    # Build key facts
    key_facts = []
    if entry_type == "release":
        key_facts.append(f"Repository: {entry['repo']}")
        key_facts.append(f"Release tag: {entry.get('tag', '')}")
        if entry.get("is_prerelease"):
            key_facts.append("Pre-release")
        # Extract first 3 meaningful lines from release body
        body_lines = [l.strip() for l in description.split("\n") if l.strip() and not l.strip().startswith("#")]
        key_facts.extend(body_lines[:3])
    elif entry_type == "trending":
        key_facts.append(f"Repository: {entry['repo']}")
        key_facts.append(f"Stars: {entry.get('stars', 0)}")
        key_facts.append(f"Language: {entry.get('language', 'unknown')}")
        key_facts.append(f"License: {entry.get('license', 'unknown')}")
        if entry.get("description"):
            key_facts.append(entry["description"][:200])
    elif entry_type == "hf_model":
        key_facts.append(f"Model: {entry['repo']}")
        key_facts.append(f"Downloads: {entry.get('downloads', 0):,}")
        key_facts.append(f"Likes: {entry.get('likes', 0)}")
        key_facts.append(f"Pipeline: {entry.get('pipeline_tag', '')}")
        key_facts.append(f"Library: {entry.get('library_name', '')}")

    # Build tags
    tags = [
        f"repo:{entry['repo']}",
        f"source_type:{entry_type}",
        f"category:{entry.get('category', 'unknown')}",
    ]
    if entry_type == "release":
        tags.append(f"release_tag:{entry.get('tag', '')}")
    if entry_type == "trending":
        tags.append(f"github_stars:{entry.get('stars', 0)}")
        tags.append(f"license:{entry.get('license', 'unknown')}")
    if entry_type == "hf_model":
        tags.append(f"hf_downloads:{entry.get('downloads', 0)}")
        tags.append(f"pipeline_tag:{entry.get('pipeline_tag', '')}")

    # Summary
    if entry_type == "release":
        summary = f"New release from {entry['repo']}: {entry.get('name', '')}."
    elif entry_type == "trending":
        summary = f"New AI repository {entry['repo']} trending with {entry.get('stars', 0)} stars."
    elif entry_type == "hf_model":
        summary = f"Hugging Face model {entry['repo']} updated with {entry.get('downloads', 0):,} downloads."
    else:
        summary = title

    summary = summary[:497] + "..." if len(summary) > 500 else summary

    # Quality flags
    quality_flags = []
    if entry_type == "release" and not entry.get("body", "").strip():
        quality_flags.append("no_release_notes")
    if entry_type == "trending" and entry.get("stars", 0) < STAR_THRESHOLDS.get("weekly", 500):
        quality_flags.append("low_stars")

    return {
        "signal_id": generate_signal_id(SOURCE_NAME, now),
        "source_name": SOURCE_NAME,
        "source_url": entry.get("url", ""),
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

        "title": title,
        "summary": summary,
        "key_facts": key_facts[:5],
        "raw_content": description[:2000] if description else None,

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
        "data_quality_flags": quality_flags,
        "tags": tags,
        "schema_version": SCHEMA_VERSION,
    }


# ─── Deduplication ──────────────────────────────────────────────────────────


def deduplicate_entries(entries: list[dict]) -> list[dict]:
    """Remove duplicate entries by repo + type + tag/name."""
    seen = set()
    unique = []
    for entry in entries:
        if entry["type"] == "release":
            key = f"{entry['repo']}:{entry.get('tag', '')}"
        elif entry["type"] == "trending":
            key = f"trending:{entry['repo']}"
        elif entry["type"] == "hf_model":
            key = f"hf:{entry['repo']}"
        else:
            key = f"{entry['type']}:{entry.get('url', uuid.uuid4())}"

        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


# ─── Main Pipeline ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="espresso·ai GitHub & Open-Source Signal Collector")
    parser.add_argument("--cadence", default="weekly",
                        choices=["daily", "weekly", "monthly", "quarterly", "annual"])
    parser.add_argument("--days-back", type=int, default=None,
                        help="Override: look back N days (default: auto from cadence)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print results without writing to disk")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: curated releases only (skip search & HF)")
    args = parser.parse_args()

    cadence = args.cadence
    now = datetime.now(timezone.utc)
    pipeline_run_id = f"{now.strftime('%Y-%m-%d')}_{cadence}_{uuid.uuid4().hex[:8]}"
    batch_id = f"batch_{now.strftime('%Y%m%d_%H%M')}"
    start_date, end_date = get_date_range(cadence, args.days_back)
    star_threshold = STAR_THRESHOLDS.get(cadence, 500)

    print("=" * 70)
    print("espresso·ai — GitHub & Open-Source Signal Collector")
    print("=" * 70)
    print(f"Pipeline run:  {pipeline_run_id}")
    print(f"Batch:         {batch_id}")
    print(f"Cadence:       {cadence}")
    print(f"Date range:    {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}")
    print(f"GitHub token:  {'SET' if GITHUB_TOKEN else 'NOT SET (rate limit: 60 req/hr)'}")
    print(f"Star threshold:{star_threshold}")
    print(f"Test mode:     {args.test}")
    print("=" * 70)

    # ── Phase 1: Curated repo releases ──
    print(f"\n{'─' * 40}")
    print("Phase 1: Curated Repository Releases")
    print(f"{'─' * 40}")
    release_entries = collect_github_releases(start_date, end_date)
    print(f"\nPhase 1 total: {len(release_entries)} releases")

    all_entries = list(release_entries)

    if not args.test:
        # ── Phase 2: Trending repos ──
        print(f"\n{'─' * 40}")
        print("Phase 2: Trending AI Repositories")
        print(f"{'─' * 40}")
        trending_entries = collect_trending_repos(start_date, end_date, star_threshold)
        print(f"\nPhase 2 total: {len(trending_entries)} trending repos")
        all_entries.extend(trending_entries)

        # ── Phase 3: Hugging Face models ──
        print(f"\n{'─' * 40}")
        print("Phase 3: Hugging Face Models")
        print(f"{'─' * 40}")
        hf_entries = collect_hf_models(start_date, end_date)
        print(f"\nPhase 3 total: {len(hf_entries)} models")
        all_entries.extend(hf_entries)

    # Deduplicate
    unique_entries = deduplicate_entries(all_entries)
    print(f"\n{'=' * 70}")
    print(f"Total collected: {len(all_entries)} | Unique: {len(unique_entries)}")

    if not unique_entries:
        print("\nNo signals found in the target date range.")
        print("Suggestions:")
        print("  - Try a longer cadence or increase --days-back")
        print("  - Check GitHub API rate limits (set GITHUB_TOKEN for 5K req/hr)")
        return

    # Convert to signal records
    signal_records = []
    for entry in unique_entries:
        record = entry_to_signal_record(entry, cadence, pipeline_run_id, batch_id)
        signal_records.append(record)

    # Classification summary
    lever_counts = {}
    type_counts = {}
    direction_counts = {}
    for rec in signal_records:
        lev = rec["lever_primary"]
        lever_counts[lev] = lever_counts.get(lev, 0) + 1
        d = rec["direction"]
        direction_counts[d] = direction_counts.get(d, 0) + 1

    for entry in unique_entries:
        t = entry["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"\n{'─' * 40}")
    print("Source Type Distribution:")
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:15s}  {count:3d}")

    print(f"\nLever Distribution:")
    for lever, count in sorted(lever_counts.items(), key=lambda x: -x[1]):
        print(f"  {lever:12s}  {count:3d}")

    print(f"\nDirection Distribution:")
    for d, count in sorted(direction_counts.items()):
        print(f"  {d:3s}  {count:3d}")
    print(f"{'─' * 40}")

    # Write JSONL
    base_dir = Path(__file__).resolve().parent.parent.parent / "research_db" / "raw"
    base_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = get_date_range_prefix(start_date, end_date)
    output_file = base_dir / f"{date_prefix}_github_{cadence}_signals.jsonl"

    if args.dry_run:
        print(f"\n[DRY RUN] Would write {len(signal_records)} records to {output_file}")
        for rec in signal_records[:5]:
            print(f"\n  Title: {rec['title'][:80]}")
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
        "collection_batch_id": batch_id,
        "cadence": cadence,
        "source": "github_oss",
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date_range": {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        },
        "github_token_set": bool(GITHUB_TOKEN),
        "star_threshold": star_threshold,
        "test_mode": args.test,
        "repos_checked": len(CURATED_REPOS),
        "search_queries": len(SEARCH_QUERIES) if not args.test else 0,
        "total_results_raw": len(all_entries),
        "total_results_unique": len(unique_entries),
        "records_written": len(signal_records),
        "type_distribution": type_counts,
        "lever_distribution": lever_counts,
        "direction_distribution": direction_counts,
        "output_file": str(output_file),
    }

    log_file = base_dir / f"{date_prefix}_github_pipeline_log.json"
    if not args.dry_run:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
        print(f"✓ Pipeline log: {log_file}")

    # Print top signals
    print(f"\n{'=' * 70}")
    print("TOP SIGNALS (by recency):")
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
