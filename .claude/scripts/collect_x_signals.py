"""
espresso·ai — X/Twitter Signal Collector
Uses Apify's Twitter scraper to collect tweets from curated high-signal accounts.
Classifies against Scale Levers and outputs signal records to research_db/raw/ in JSONL format.

Usage:
    python .claude/scripts/collect_x_signals.py --cadence weekly [--days-back 7] [--test] [--dry-run]
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

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env" / ".env", override=True)
API_TOKEN = os.getenv("APIFY_API_TOKEN")
APIFY_BASE_URL = "https://api.apify.com/v2"
ACTOR_ID = "apidojo~tweet-scraper"
AGENT_ID = "x-signal-collector"
SCHEMA_VERSION = "1.0"
SOURCE_NAME = "twitter"

# ─── Curated Account List ───────────────────────────────────────────────────
# High-signal X accounts organized by category and primary Scale Lever.
# Each account's primary_lever is used as a tiebreaker in classification.
# This list can be extracted to a config file later if needed.

CURATED_ACCOUNTS = [
    # AI Lab Leaders
    {"handle": "sama", "name": "Sam Altman", "primary_lever": "COMPUTE", "category": "ai_lab_leader"},
    {"handle": "DarioAmodei", "name": "Dario Amodei", "primary_lever": "GOV", "category": "ai_lab_leader"},
    {"handle": "demaborsa", "name": "Demis Hassabis", "primary_lever": "COMPUTE", "category": "ai_lab_leader"},
    {"handle": "sataborwanpat", "name": "Satya Nadella", "primary_lever": "INDUSTRY", "category": "ai_lab_leader"},
    {"handle": "ylecun", "name": "Yann LeCun", "primary_lever": "COMPUTE", "category": "researcher"},

    # Researchers
    {"handle": "karpathy", "name": "Andrej Karpathy", "primary_lever": "COMPUTE", "category": "researcher"},
    {"handle": "DrJimFan", "name": "Jim Fan", "primary_lever": "INDUSTRY", "category": "researcher"},
    {"handle": "fchollet", "name": "François Chollet", "primary_lever": "SOCIETY", "category": "researcher"},
    {"handle": "jeffdean", "name": "Jeff Dean", "primary_lever": "COMPUTE", "category": "researcher"},
    {"handle": "goodaborwfellow", "name": "Ian Goodfellow", "primary_lever": "COMPUTE", "category": "researcher"},

    # Policy / Safety / Governance
    {"handle": "GaryMarcus", "name": "Gary Marcus", "primary_lever": "GOV", "category": "policy"},
    {"handle": "mustafasuleyman", "name": "Mustafa Suleyman", "primary_lever": "GOV", "category": "policy"},
    {"handle": "jackclarkSF", "name": "Jack Clark", "primary_lever": "GOV", "category": "policy"},
    {"handle": "timnitGebru", "name": "Timnit Gebru", "primary_lever": "SOCIETY", "category": "policy"},

    # Industry / Enterprise
    {"handle": "svpino", "name": "Santiago Valdarrama", "primary_lever": "INDUSTRY", "category": "industry"},
    {"handle": "bindureddy", "name": "Bindu Reddy", "primary_lever": "INDUSTRY", "category": "industry"},
    {"handle": "emad", "name": "Emad Mostaque", "primary_lever": "CAPITAL", "category": "industry"},

    # Capital / Investment
    {"handle": "eladgil", "name": "Elad Gil", "primary_lever": "CAPITAL", "category": "capital"},
    {"handle": "saranormous", "name": "Sarah Guo", "primary_lever": "CAPITAL", "category": "capital"},
    {"handle": "naval", "name": "Naval Ravikant", "primary_lever": "CAPITAL", "category": "capital"},

    # Journalists / Analysts
    {"handle": "karaswisher", "name": "Kara Swisher", "primary_lever": "INDUSTRY", "category": "journalist"},
    {"handle": "CaseyNewton", "name": "Casey Newton", "primary_lever": "SOCIETY", "category": "journalist"},
    {"handle": "zoeschiffer", "name": "Zoe Schiffer", "primary_lever": "INDUSTRY", "category": "journalist"},
    {"handle": "SemiAnalysis", "name": "SemiAnalysis", "primary_lever": "COMPUTE", "category": "analyst"},
    {"handle": "dyaborlanpatel", "name": "Dylan Patel", "primary_lever": "COMPUTE", "category": "analyst"},
    {"handle": "EmanuelMaiberg", "name": "Emanuel Maiberg", "primary_lever": "INDUSTRY", "category": "journalist"},

    # Energy / Infrastructure
    {"handle": "GridStatusBlog", "name": "Grid Status", "primary_lever": "ENERGY", "category": "analyst"},
    {"handle": "datacaborenterdy", "name": "Data Center Dynamics", "primary_lever": "ENERGY", "category": "analyst"},
]

# Build lookup by handle for fast access
ACCOUNT_LOOKUP = {a["handle"].lower(): a for a in CURATED_ACCOUNTS}

# ─── Cadence Configuration ──────────────────────────────────────────────────

CADENCE_CONFIG = {
    "daily":     {"days_back": 2,   "min_likes": 100,  "max_tweets_per_account": 5},
    "weekly":    {"days_back": 7,   "min_likes": 250,  "max_tweets_per_account": 10},
    "monthly":   {"days_back": 31,  "min_likes": 500,  "max_tweets_per_account": 20},
    "quarterly": {"days_back": 92,  "min_likes": 1000, "max_tweets_per_account": 30},
    "annual":    {"days_back": 366, "min_likes": 2000, "max_tweets_per_account": 50},
}

# ─── Apify API Functions ────────────────────────────────────────────────────

def start_actor_run(handles: list[str], start_date: str, end_date: str,
                    max_tweets: int) -> str:
    """Start an Apify actor run for the given handles and date range.
    Returns the run ID."""
    url = f"{APIFY_BASE_URL}/acts/{ACTOR_ID}/runs"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "handles": handles,
        "tweetsDesired": max_tweets,
        "mode": "user",
        "addUserInfo": True,
        "startDate": start_date,
        "endDate": end_date,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    run_id = data["data"]["id"]
    print(f"  Actor run started: {run_id}")
    return run_id


def wait_for_run(run_id: str, timeout_seconds: int = 300, poll_interval: int = 5) -> dict:
    """Poll the actor run until it completes or times out.
    Returns the run metadata including defaultDatasetId."""
    url = f"{APIFY_BASE_URL}/actor-runs/{run_id}"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    elapsed = 0

    while elapsed < timeout_seconds:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        run_data = resp.json()["data"]
        status = run_data.get("status", "UNKNOWN")

        if status == "SUCCEEDED":
            print(f"  Actor run completed in ~{elapsed}s")
            return run_data
        elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
            error_msg = run_data.get("statusMessage", "No error message")
            raise RuntimeError(f"Actor run {status}: {error_msg}")

        time.sleep(poll_interval)
        elapsed += poll_interval

    raise TimeoutError(f"Actor run did not complete within {timeout_seconds}s")


def fetch_dataset(dataset_id: str) -> list[dict]:
    """Fetch all items from an Apify dataset, paginating if needed."""
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    items = []
    offset = 0
    limit = 1000

    while True:
        url = f"{APIFY_BASE_URL}/datasets/{dataset_id}/items"
        params = {"format": "json", "limit": limit, "offset": offset}
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        batch = resp.json()

        if not batch:
            break

        items.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    return items


# ─── Tweet Filtering & Quality Control ──────────────────────────────────────

LIKE_FLOOR = 100  # Absolute minimum regardless of cadence


def extract_tweet_fields(raw_tweet: dict) -> dict:
    """Normalize raw Apify tweet data into a consistent format.
    Apify actors vary in their output schema, so this handles common variations."""
    return {
        "tweet_id": str(raw_tweet.get("id") or raw_tweet.get("tweet_id") or raw_tweet.get("id_str", "")),
        "text": raw_tweet.get("text") or raw_tweet.get("full_text") or raw_tweet.get("tweet_text", ""),
        "handle": (raw_tweet.get("author", {}).get("userName")
                   or raw_tweet.get("user", {}).get("screen_name")
                   or raw_tweet.get("handle", "")).lower(),
        "author_name": (raw_tweet.get("author", {}).get("name")
                        or raw_tweet.get("user", {}).get("name")
                        or ""),
        "created_at": raw_tweet.get("createdAt") or raw_tweet.get("created_at") or "",
        "likes": int(raw_tweet.get("likeCount") or raw_tweet.get("favorite_count") or 0),
        "retweets": int(raw_tweet.get("retweetCount") or raw_tweet.get("retweet_count") or 0),
        "replies": int(raw_tweet.get("replyCount") or raw_tweet.get("reply_count") or 0),
        "is_reply": bool(raw_tweet.get("inReplyToStatusId") or raw_tweet.get("in_reply_to_status_id")),
        "reply_to_user": (raw_tweet.get("inReplyToUserId") or raw_tweet.get("in_reply_to_user_id") or ""),
        "author_id": str(raw_tweet.get("author", {}).get("id")
                         or raw_tweet.get("user", {}).get("id")
                         or raw_tweet.get("author_id", "")),
        "conversation_id": str(raw_tweet.get("conversationId") or raw_tweet.get("conversation_id") or ""),
        "quoted_text": (raw_tweet.get("quotedTweet", {}) or {}).get("text", ""),
        "urls": [u.get("expanded_url") or u.get("url", "")
                 for u in (raw_tweet.get("entities", {}).get("urls", [])
                           or raw_tweet.get("urls", []))],
    }


def filter_tweet(tweet: dict, min_likes: int) -> tuple[bool, list[str]]:
    """Determine if a tweet should be kept and return quality flags.
    Returns (keep, quality_flags)."""
    flags = []

    # Exclude pure retweets
    if tweet["text"].startswith("RT @"):
        return False, []

    # Exclude replies to other users (keep self-replies / threads)
    if tweet["is_reply"]:
        reply_to = str(tweet["reply_to_user"])
        author = str(tweet["author_id"])
        if reply_to and author and reply_to != author:
            return False, []

    # Exclude below absolute floor
    if tweet["likes"] < LIKE_FLOOR:
        return False, []

    # Quality flags (keep but flag)
    if tweet["likes"] < min_likes:
        flags.append("low_engagement")

    if tweet["is_reply"] and str(tweet["reply_to_user"]) == str(tweet["author_id"]):
        flags.append("thread_fragment")

    if not tweet["urls"] and not tweet["quoted_text"]:
        flags.append("no_primary_source")

    return True, flags


# ─── Signal Classification ──────────────────────────────────────────────────
# Keyword maps from RESEARCH_FRAMEWORK.md sub-variable definitions.
# Replicated from collect_perplexity_signals.py for script independence.

SUB_VAR_KEYWORDS = {
    "COMPUTE": {
        "manufacturing_capacity": ["wafer", "fab ", "fabrication", "yield", "tsmc", "node", "production volume", "semiconductor"],
        "cost_per_flop": ["inference cost", "cost per token", "cost reduction", "compute cost", "pricing", "cost decline"],
        "energy_efficiency": ["flop per watt", "power efficiency", "energy per flop", "efficient chip"],
        "supply_chain_resilience": ["supply chain", "export control", "chip shortage", "asml", "concentration risk", "chip ban"],
        "data_center_buildout": ["data center", "rack capacity", "cooling", "construction", "grid interconnection", "hyperscale"],
        "custom_silicon_adoption": ["tpu", "trainium", "custom silicon", "custom chip", "accelerator", "inferentia"],
        "architectural_diversity": ["neuromorphic", "photonic", "analog compute", "in-memory compute", "quantum"],
    },
    "ENERGY": {
        "data_center_power_intensity": ["power consumption", "energy consumption", "kwh", "power demand", "electricity demand"],
        "renewable_allocation": ["renewable", "solar", "wind", "clean energy", "net zero", "nuclear", "small modular reactor"],
        "grid_capacity_utilization": ["grid capacity", "moratorium", "blackout", "power grid", "grid constraint"],
        "renewable_capex_cost": ["renewable cost", "solar cost", "wind cost", "power purchase agreement", "ppa"],
        "training_energy_per_model": ["training energy", "training power", "mwh", "energy per model"],
        "water_consumption": ["water consumption", "water usage", "cooling water", "water stress"],
        "carbon_regulatory_exposure": ["carbon", "emissions", "esg", "carbon pricing", "carbon tax"],
    },
    "SOCIETY": {
        "enterprise_penetration_depth": ["enterprise adoption", "enterprise ai", "production deployment", "ai deployment"],
        "high_stakes_domain_adoption": ["clinical ai", "medical ai", "legal ai", "financial ai", "government ai"],
        "ai_literacy_distribution": ["ai literacy", "ai education", "ai training program", "ai skills", "upskilling"],
        "researcher_and_engineer_stock": ["ai talent", "ai engineer", "ai researcher", "talent shortage", "ai hiring"],
        "skill_diffusion_rate": ["ai workforce", "ai skills gap", "developer adoption"],
        "professional_displacement_signals": ["job displacement", "layoff", "automation", "wage compression", "headcount reduction"],
        "incident_impact_on_trust": ["ai incident", "ai failure", "ai harm", "trust", "ai safety incident"],
    },
    "INDUSTRY": {
        "production_deployment_rate": ["pilot to production", "production deployment", "ai in production", "deployed at scale"],
        "productivity_measurement_transparency": ["productivity gain", "roi", "margin improvement", "cost saving", "earnings"],
        "labor_displacement_scale": ["headcount reduction", "workforce reduction", "role consolidation", "restructuring"],
        "business_model_reinvention": ["ai-native", "ai-first", "business model", "pricing model", "outcomes-based"],
        "capital_allocation_continuity": ["ai budget", "ai spending", "ai investment", "enterprise spending"],
        "workflow_integration_depth": ["workflow", "ai integration", "embedded ai", "ai-powered"],
        "cross_sector_diffusion": ["healthcare", "manufacturing", "logistics", "finance", "legal", "pharma", "drug discovery"],
    },
    "CAPITAL": {
        "hyperscaler_capex_and_utilization": ["capex", "capital expenditure", "gpu cluster", "utilization", "cloud infrastructure spend"],
        "venture_funding_discipline": ["series a", "series b", "venture capital", "vc funding", "startup funding", "seed round"],
        "corporate_rd_reallocation": ["r&d budget", "ai budget", "corporate ai spend", "ai investment"],
        "roi_signal_clarity": ["ai roi", "payback period", "customer retention", "revenue growth"],
        "valuation_multiple_dynamics": ["valuation", "ipo", "p/s ratio", "market cap"],
        "capital_exit_velocity": ["m&a", "acquisition", "acqui-hire", "merger", "ipo"],
        "international_capital_flows": ["sovereign wealth", "international investment", "cross-border", "foreign investment"],
    },
    "GOV": {
        "regulatory_framework_clarity": ["regulation", "liability", "ip", "copyright", "approval pathway", "compliance", "ai act"],
        "export_controls_and_chip_access": ["export control", "chip ban", "semiconductor restriction", "chip access", "entity list"],
        "cross_border_data_and_model_mobility": ["data localization", "model weights", "cross-border", "data sovereignty"],
        "alignment_and_safety_maturity": ["interpretability", "alignment", "ai safety", "red team", "mechanistic interpretability"],
        "geopolitical_fragmentation_index": ["us-china", "geopolitical", "tech war", "decoupling", "ai sovereignty"],
        "antitrust_and_market_structure": ["antitrust", "monopoly", "market concentration", "competition"],
        "institutional_trust": ["public trust", "ai confidence", "institutional adoption", "government ai"],
    },
}

POSITIVE_INDICATORS = [
    "growth", "increase", "breakthrough", "expansion", "record", "launch",
    "approved", "partnership", "investment", "funding", "milestone", "surpass",
    "accelerat", "advanc", "unlock", "gain", "improvement", "exceed",
]
NEGATIVE_INDICATORS = [
    "decline", "cut", "halt", "moratorium", "restriction", "ban",
    "delay", "shortage", "failure", "lawsuit", "layoff", "concern",
    "slowdown", "contraction", "stall", "cancel", "withdraw", "suspend",
]


def classify_signal(text: str, account_lever: str) -> dict:
    """Classify tweet text against Scale Levers.
    Returns dict with lever_primary, sub_variable, direction, confidence.
    Uses account's primary_lever as a +1 tiebreaker."""
    text_lower = text.lower()

    # Score each lever's sub-variables
    best_lever = account_lever
    best_sub = None
    best_score = 0

    for lever, sub_vars in SUB_VAR_KEYWORDS.items():
        for sub_var, keywords in sub_vars.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            # Tiebreaker: boost account's known lever by +1
            if lever == account_lever:
                score += 1
            if score > best_score:
                best_score = score
                best_lever = lever
                best_sub = sub_var

    # Direction
    pos_score = sum(1 for p in POSITIVE_INDICATORS if p in text_lower)
    neg_score = sum(1 for n in NEGATIVE_INDICATORS if n in text_lower)

    if pos_score > neg_score + 1:
        direction = "+"
    elif neg_score > pos_score + 1:
        direction = "-"
    elif pos_score > 0 and neg_score > 0:
        direction = "?"
    else:
        direction = "~"

    # Confidence (subtract the +1 tiebreaker to get real keyword hits)
    real_score = best_score - 1 if best_lever == account_lever else best_score
    confidence = "high" if real_score >= 3 else "medium" if real_score >= 1 else "low"

    return {
        "lever_primary": best_lever,
        "sub_variable": best_sub or "pending_classification",
        "direction": direction,
        "confidence": confidence,
    }


# ─── Record Builder ─────────────────────────────────────────────────────────

def make_signal_id(handle: str, tweet_id: str) -> str:
    """Generate a deterministic signal_id per schema."""
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y%m%d")
    time_part = now.strftime("%H%M%S")
    hash_input = f"{handle}{tweet_id}"
    short_hash = hashlib.md5(hash_input.encode()).hexdigest()[:5]
    return f"{date_part}-{SOURCE_NAME}-{time_part}-{short_hash}"


def parse_tweet_date(date_str: str) -> str:
    """Parse various date formats from Apify into YYYY-MM-DD."""
    if not date_str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%a %b %d %H:%M:%S %z %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return date_str[:10] if len(date_str) >= 10 else datetime.now(timezone.utc).strftime("%Y-%m-%d")


def build_signal_record(tweet: dict, account: dict, classification: dict,
                        quality_flags: list[str], pipeline_run_id: str,
                        collection_batch_id: str, cadence: str) -> dict:
    """Build a full signal record from a normalized tweet."""
    now = datetime.now(timezone.utc)
    pub_date = parse_tweet_date(tweet["created_at"])
    full_text = tweet["text"]
    if tweet["quoted_text"]:
        full_text += f"\n\n[Quoted] {tweet['quoted_text']}"

    # Cap confidence for tweets without URLs
    confidence = classification["confidence"]
    if not tweet["urls"] and not tweet["quoted_text"]:
        if confidence == "high":
            confidence = "medium"

    return {
        "signal_id": make_signal_id(tweet["handle"], tweet["tweet_id"]),
        "source_name": SOURCE_NAME,
        "source_url": f"https://x.com/{tweet['handle']}/status/{tweet['tweet_id']}",
        "fetch_timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agent_id": AGENT_ID,
        "cadence": cadence,
        "pipeline_run_id": pipeline_run_id,
        "collection_batch_id": collection_batch_id,
        # Classification
        "lever_primary": classification["lever_primary"],
        "lever_secondary": None,
        "direction": classification["direction"],
        "sub_variable": classification["sub_variable"],
        "confidence": confidence,
        # Content
        "title": tweet["text"][:200],
        "summary": tweet["text"],
        "key_facts": [],
        "raw_content": full_text,
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
        # Metadata
        "in_scope": True,
        "data_quality_flags": quality_flags,
        "tags": [
            f"x_handle:{tweet['handle']}",
            f"x_likes:{tweet['likes']}",
            f"x_retweets:{tweet['retweets']}",
            f"x_replies:{tweet['replies']}",
            f"account_category:{account['category']}",
        ],
        "schema_version": SCHEMA_VERSION,
    }


# ─── Deduplication ──────────────────────────────────────────────────────────

def deduplicate_signals(signals: list[dict]) -> tuple[list[dict], int]:
    """Remove signals with duplicate tweet IDs or near-identical titles."""
    seen_ids = set()
    seen_titles = set()
    unique = []

    for signal in signals:
        tweet_id = signal["source_url"].split("/status/")[-1] if "/status/" in signal["source_url"] else ""
        title_key = signal.get("title", "").lower().strip()

        if tweet_id and tweet_id in seen_ids:
            continue
        if title_key and title_key in seen_titles:
            continue

        if tweet_id:
            seen_ids.add(tweet_id)
        if title_key:
            seen_titles.add(title_key)
        unique.append(signal)

    return unique, len(signals) - len(unique)


# ─── Main Pipeline ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="espresso·ai X/Twitter Signal Collector")
    parser.add_argument("--cadence", default="weekly",
                        choices=["daily", "weekly", "monthly", "quarterly", "annual"])
    parser.add_argument("--days-back", type=int, default=None,
                        help="Override: look back N days (default: auto from cadence)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print signals without writing to file")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: use only 2 accounts and 2 tweets per account")
    args = parser.parse_args()

    if not API_TOKEN:
        print("ERROR: APIFY_API_TOKEN not found in .env/.env")
        print("Add your Apify API token: APIFY_API_TOKEN=apify_api_...")
        return

    cadence = args.cadence
    config = CADENCE_CONFIG[cadence]
    days_back = args.days_back if args.days_back is not None else config["days_back"]
    min_likes = config["min_likes"]
    max_tweets = config["max_tweets_per_account"]

    now = datetime.now(timezone.utc)
    batch_ts = now.strftime("%Y%m%d_%H%M")
    collection_batch_id = f"batch_{batch_ts}"

    # Compute date window
    start_date = now - timedelta(days=days_back)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = now.strftime("%Y-%m-%d")

    # File naming
    file_stem = f"{start_str}_{end_str}_x_{cadence}"
    pipeline_run_id = f"{file_stem}_{uuid.uuid4().hex[:8]}"
    raw_dir = Path(__file__).resolve().parent.parent.parent / "research_db" / "raw"
    output_file = raw_dir / f"{file_stem}_signals.jsonl"

    # Select accounts
    accounts = CURATED_ACCOUNTS
    if args.test:
        accounts = accounts[:2]
        max_tweets = 2
        print("*** TEST MODE: 2 accounts, 2 tweets each ***\n")

    handles = [a["handle"] for a in accounts]

    print(f"espresso·ai X Signal Collector")
    print(f"Pipeline run:  {pipeline_run_id}")
    print(f"Cadence:       {cadence}")
    print(f"Date window:   {start_str} → {end_str}")
    print(f"Accounts:      {len(accounts)}")
    print(f"Max tweets/acct: {max_tweets}")
    print(f"Min likes:     {min_likes}")
    print(f"Output:        {output_file}")
    print("-" * 60)

    # ── Step 1: Collect tweets via Apify ──
    print(f"\n[1/4] Starting Apify actor run...")
    try:
        run_id = start_actor_run(handles, start_str, end_str, max_tweets)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to start actor run: {e}")
        return

    print(f"\n[2/4] Waiting for actor to complete...")
    try:
        run_meta = wait_for_run(run_id)
    except (RuntimeError, TimeoutError) as e:
        print(f"ERROR: {e}")
        return

    dataset_id = run_meta.get("defaultDatasetId")
    if not dataset_id:
        print("ERROR: No dataset ID in run metadata")
        return

    print(f"\n[3/4] Fetching results from dataset {dataset_id}...")
    try:
        raw_tweets = fetch_dataset(dataset_id)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to fetch dataset: {e}")
        return

    print(f"  Raw tweets fetched: {len(raw_tweets)}")

    # ── Step 2: Filter, classify, build records ──
    print(f"\n[4/4] Processing tweets...")
    all_signals = []
    skipped = {"retweet": 0, "reply": 0, "low_engagement": 0}
    account_counts = {}

    for raw in raw_tweets:
        tweet = extract_tweet_fields(raw)

        if not tweet["tweet_id"] or not tweet["text"]:
            continue

        # Look up account
        account = ACCOUNT_LOOKUP.get(tweet["handle"])
        if not account:
            continue

        # Filter
        keep, flags = filter_tweet(tweet, min_likes)
        if not keep:
            if tweet["text"].startswith("RT @"):
                skipped["retweet"] += 1
            elif tweet["is_reply"]:
                skipped["reply"] += 1
            else:
                skipped["low_engagement"] += 1
            continue

        # Enforce per-account limit (keep highest engagement first)
        handle_key = tweet["handle"]
        account_counts.setdefault(handle_key, 0)
        if account_counts[handle_key] >= max_tweets:
            continue
        account_counts[handle_key] += 1

        # Classify
        classify_text = tweet["text"]
        if tweet["quoted_text"]:
            classify_text += " " + tweet["quoted_text"]
        classification = classify_signal(classify_text, account["primary_lever"])

        # Build record
        record = build_signal_record(
            tweet, account, classification, flags,
            pipeline_run_id, collection_batch_id, cadence
        )
        all_signals.append(record)

    # Sort by engagement (likes descending) before dedup
    all_signals.sort(key=lambda s: int(next(
        (t.split(":")[1] for t in s.get("tags", []) if t.startswith("x_likes:")), "0"
    )), reverse=True)

    # Deduplicate
    pre_dedup = len(all_signals)
    all_signals, dupes_removed = deduplicate_signals(all_signals)

    # ── Metrics ──
    def count_flag(flag_name):
        return sum(1 for s in all_signals if flag_name in s.get("data_quality_flags", []))

    def count_direction(d):
        return sum(1 for s in all_signals if s.get("direction") == d)

    lever_dist = {}
    for s in all_signals:
        lev = s.get("lever_primary", "UNKNOWN")
        lever_dist[lev] = lever_dist.get(lev, 0) + 1

    active_accounts = len(set(
        next((t.split(":")[1] for t in s.get("tags", []) if t.startswith("x_handle:")), "")
        for s in all_signals
    ))

    print(f"\n{'=' * 60}")
    print(f"Raw tweets fetched:   {len(raw_tweets)}")
    print(f"Skipped (retweets):   {skipped['retweet']}")
    print(f"Skipped (replies):    {skipped['reply']}")
    print(f"Skipped (low engage): {skipped['low_engagement']}")
    print(f"Signals pre-dedup:    {pre_dedup}")
    print(f"Duplicates removed:   {dupes_removed}")
    print(f"Final signals:        {len(all_signals)}")
    print(f"Active accounts:      {active_accounts}")
    print(f"No primary source:    {count_flag('no_primary_source')}")
    print(f"Low engagement flags: {count_flag('low_engagement')}")
    print(f"Thread fragments:     {count_flag('thread_fragment')}")
    print(f"Direction: + {count_direction('+')} | - {count_direction('-')} | ~ {count_direction('~')} | ? {count_direction('?')}")
    print(f"Lever distribution:   {json.dumps(lever_dist, indent=None)}")

    if args.dry_run:
        print(f"\n*** DRY RUN — not writing to file ***")
    elif all_signals:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "a", encoding="utf-8") as f:
            for record in all_signals:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"\nAppended {len(all_signals)} records to {output_file}")
    else:
        print("\nNo signals collected — check Apify token, account handles, and date range.")

    # Write pipeline log
    run_log = {
        "pipeline_run_id": pipeline_run_id,
        "collection_batch_id": collection_batch_id,
        "cadence": cadence,
        "source": "x_twitter",
        "date_window": {"start": start_str, "end": end_str},
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "accounts_tracked": len(accounts),
        "accounts_with_signals": active_accounts,
        "raw_tweets_fetched": len(raw_tweets),
        "skipped": skipped,
        "signals_collected": pre_dedup,
        "duplicates_removed": dupes_removed,
        "signals_written": len(all_signals),
        "output_file": str(output_file) if not args.dry_run else "DRY_RUN",
        "quality_metrics": {
            "no_primary_source_count": count_flag("no_primary_source"),
            "low_engagement_count": count_flag("low_engagement"),
            "thread_fragment_count": count_flag("thread_fragment"),
            "direction_distribution": {
                "+": count_direction("+"),
                "-": count_direction("-"),
                "~": count_direction("~"),
                "?": count_direction("?"),
            },
            "lever_distribution": lever_dist,
        },
    }
    log_path = raw_dir / f"{file_stem}_pipeline_log.json"
    if not args.dry_run:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(run_log, f, indent=2)
        print(f"Run log: {log_path}")
    else:
        print(f"\nPipeline log (dry run):")
        print(json.dumps(run_log, indent=2))

    # Print signal sample
    print(f"\n{'=' * 60}")
    print("SAMPLE SIGNALS:")
    for rec in all_signals[:10]:
        d = rec["direction"]
        lev = rec["lever_primary"]
        sub = rec["sub_variable"]
        handle = next((t.split(":")[1] for t in rec.get("tags", []) if t.startswith("x_handle:")), "?")
        likes = next((t.split(":")[1] for t in rec.get("tags", []) if t.startswith("x_likes:")), "?")
        title = rec["title"][:60]
        flags = rec.get("data_quality_flags", [])
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  [{lev:8s} {d}] @{handle:20s} | {likes:>6s} likes | {sub:30s} | {title}{flag_str}")

    if len(all_signals) > 10:
        print(f"  ... and {len(all_signals) - 10} more")


if __name__ == "__main__":
    main()
