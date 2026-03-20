"""
espresso·ai — X/Twitter Signal Collector (via Perplexity)
Uses Perplexity API (sonar-pro) to find news coverage and media references to
curated high-signal X/Twitter accounts' AI-related statements and posts.
Classifies against Scale Levers and outputs signal records to research_db/raw/ in JSONL format.

Usage:
    python .claude/scripts/collect_x_perplexity_signals.py --cadence weekly [--days-back 7] [--test] [--dry-run]
"""

import json
import os
import uuid
import hashlib
import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv
import requests

# ─── Configuration ───────────────────────────────────────────────────────────

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env" / ".env")
API_KEY = os.getenv("PERPLEXITY_API_KEY")
PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
MODEL = "sonar-pro"
AGENT_ID = "x-perplexity-collector"
SCHEMA_VERSION = "1.0"
SOURCE_NAME = "twitter"

# ─── Curated Account List ───────────────────────────────────────────────────
# Same 28 high-signal X accounts as collect_x_signals.py.
# Each account's primary_lever is used as a tiebreaker in classification.

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

# Build lookups for fast access
ACCOUNT_LOOKUP = {a["handle"].lower(): a for a in CURATED_ACCOUNTS}
NAME_LOOKUP = {a["name"].lower(): a for a in CURATED_ACCOUNTS}

# ─── Query Groups ────────────────────────────────────────────────────────────
# Accounts grouped by category. One Perplexity query per group (7 total).

ACCOUNT_GROUPS = [
    {
        "group_name": "ai_lab_leaders",
        "lever_hint": "COMPUTE",
        "query_tag": "x_ai_lab_leaders",
        "accounts": ["sama", "DarioAmodei", "demaborsa", "sataborwanpat"],
        "topic": "AI models, compute infrastructure, product launches, and company strategy",
    },
    {
        "group_name": "researchers",
        "lever_hint": "COMPUTE",
        "query_tag": "x_researchers",
        "accounts": ["ylecun", "karpathy", "DrJimFan", "fchollet", "jeffdean", "goodaborwfellow"],
        "topic": "AI research breakthroughs, model architectures, benchmarks, and technical insights",
    },
    {
        "group_name": "policy_safety",
        "lever_hint": "GOV",
        "query_tag": "x_policy_safety",
        "accounts": ["GaryMarcus", "mustafasuleyman", "jackclarkSF", "timnitGebru"],
        "topic": "AI regulation, safety, alignment, governance, and ethical concerns",
    },
    {
        "group_name": "industry_enterprise",
        "lever_hint": "INDUSTRY",
        "query_tag": "x_industry_enterprise",
        "accounts": ["svpino", "bindureddy", "emad"],
        "topic": "enterprise AI adoption, production deployments, developer tools, and business transformation",
    },
    {
        "group_name": "capital_investment",
        "lever_hint": "CAPITAL",
        "query_tag": "x_capital_investment",
        "accounts": ["eladgil", "saranormous", "naval"],
        "topic": "AI venture funding, startup valuations, hyperscaler capex, and investment trends",
    },
    {
        "group_name": "journalists_analysts",
        "lever_hint": "INDUSTRY",
        "query_tag": "x_journalists_analysts",
        "accounts": ["karaswisher", "CaseyNewton", "zoeschiffer", "SemiAnalysis", "dyaborlanpatel", "EmanuelMaiberg"],
        "topic": "AI industry analysis, chip supply chains, company strategy, and market dynamics",
    },
    {
        "group_name": "energy_infrastructure",
        "lever_hint": "ENERGY",
        "query_tag": "x_energy_infrastructure",
        "accounts": ["GridStatusBlog", "datacaborenterdy"],
        "topic": "AI energy consumption, data center power, grid capacity, and infrastructure buildout",
    },
]


def build_query(group: dict) -> str:
    """Construct a Perplexity query from an account group."""
    names_with_handles = ", ".join(
        f"{ACCOUNT_LOOKUP[h.lower()]['name']} (@{h})"
        for h in group["accounts"]
        if h.lower() in ACCOUNT_LOOKUP
    )
    return (
        f"Recent public statements, posts, and commentary by {names_with_handles} "
        f"on X/Twitter about artificial intelligence. "
        f"Search for news articles, newsletters, and media coverage that quote or reference "
        f"their recent X/Twitter posts or public statements about {group['topic']}. "
        f"Include specific claims, opinions, announcements, and predictions they have made."
    )


# ─── System Prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a research analyst for an AI intelligence service called espresso·ai.

TASK: Find and extract specific public statements, posts, and commentary by the named individuals from X/Twitter. Search for news articles, blog posts, newsletters, and media coverage that reference or quote their recent statements.

RULES:
1. Return ONLY a JSON array. No text outside the array.
2. Extract 5-8 of the most important INDIVIDUAL statements or posts, each attributed to a specific person.
3. Each entry must be a SPECIFIC statement, claim, announcement, or opinion — not a summary of multiple posts.
4. PRIORITIZE entries where you can identify the specific X/Twitter post being referenced.
5. For source_url, use the URL from the search results. If you can identify the direct X/Twitter post URL, include it as "x_post_url" as well.

REQUIRED FIELDS per object:
- "attributed_to": name of the person who made the statement (string)
- "x_handle": their X/Twitter handle without @ (string)
- "title": brief description of what they said (max 200 chars, string)
- "source_name": publication name where this was found, e.g. "Reuters", "The Verge", "X/Twitter" (string)
- "source_url": direct URL to the article or post from search results (string, empty string if unavailable)
- "x_post_url": direct URL to the X/Twitter post if identifiable (string, empty string if not found)
- "publication_date": YYYY-MM-DD (string)
- "summary": 1-2 sentence factual summary of the specific statement and its context (string)
- "content_summary": 3-5 sentences on the statement's content and its strategic implications for AI (string)
- "key_facts": 3-5 specific verifiable claims or quotes from the statement (array of strings)
- "is_direct_post": true if this comes directly from an X post, false if from a news article quoting or discussing the post (boolean)

CRITICAL RULES:
- Each object must describe ONE specific statement or claim by ONE person.
- ALWAYS identify the specific individual — do not return group statements without attribution.
- If a news article references multiple people's posts, extract them as separate objects.
- Prefer RECENT statements (within the search date window) over older ones.
- Do NOT fabricate URLs. Use only URLs from the search results. If unsure, use empty string.
- Do NOT include aggregator content ("Weekly Briefing", "AI Update", "Recap", "Roundup").
- Ensure valid JSON — no trailing commas, no markdown fences."""


# ─── Known Domains ───────────────────────────────────────────────────────────
# For post-hoc URL quality validation. Includes X/Twitter domains.

KNOWN_DOMAINS = {
    "x.com", "twitter.com",
    "reuters.com", "wsj.com", "nytimes.com", "ft.com",
    "bloomberg.com", "theinformation.com",
    "arstechnica.com", "theverge.com", "wired.com", "techcrunch.com",
    "technologyreview.com", "venturebeat.com",
    "bbc.com", "cnn.com", "asia.nikkei.com", "scmp.com",
    "economist.com", "politico.com", "politico.eu",
    "openai.com", "deepmind.google", "anthropic.com",
    "ai.meta.com", "blogs.microsoft.com", "blogs.nvidia.com", "sec.gov",
    "spglobal.com", "semianalysis.com", "anandtech.com",
    "tomshardware.com", "theregister.com", "semafor.com",
    "axios.com", "cnbc.com", "fortune.com", "forbes.com",
    "datacenterknowledge.com", "supplychaindive.com",
    "crunchbase.com", "news.crunchbase.com", "trendforce.com",
}


# ─── Date Window ─────────────────────────────────────────────────────────────

def compute_date_window(cadence: str, reference_date: datetime, days_back: int = None) -> tuple[str, str]:
    """Return (after_date, before_date) in MM/DD/YYYY format for the Perplexity API."""
    if days_back is not None:
        start = reference_date - timedelta(days=days_back)
    elif cadence == "daily":
        start = reference_date - timedelta(days=1)
    elif cadence == "weekly":
        start = reference_date - timedelta(days=7)
    elif cadence == "monthly":
        start = reference_date - timedelta(days=31)
    elif cadence == "quarterly":
        start = reference_date - timedelta(days=92)
    elif cadence == "annual":
        start = reference_date - timedelta(days=366)
    else:
        start = reference_date - timedelta(days=7)

    after = start.strftime("%m/%d/%Y")
    before = reference_date.strftime("%m/%d/%Y")
    return after, before


# ─── Perplexity API ──────────────────────────────────────────────────────────

def query_perplexity(query_text: str, date_after: str, date_before: str) -> dict:
    """Call Perplexity sonar-pro with date filters. No domain filter — we want
    X-related content from any source."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query_text},
        ],
        "temperature": 0.1,
        "max_tokens": 4000,
        "search_after_date_filter": date_after,
        "search_before_date_filter": date_before,
        "web_search_options": {
            "search_context_size": "high",
        },
    }

    resp = requests.post(PERPLEXITY_URL, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    return resp.json()


# ─── Response Parsing ────────────────────────────────────────────────────────

def parse_signals_from_response(raw_text: str) -> list[dict]:
    """Extract JSON array from Perplexity response text."""
    text = raw_text.strip()
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
            break
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        print(f"  WARNING: No JSON array found in response. Preview:\n{text[:300]}")
        return []

    json_str = text[start : end + 1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"  WARNING: JSON parse error: {e}")
        print(f"  Preview:\n{json_str[:300]}")
        return []


# ─── Citation Cross-Validation ───────────────────────────────────────────────

def cross_validate_urls(signals: list[dict], citations: list[str]) -> list[dict]:
    """Cross-validate model-returned URLs against Perplexity's citations array."""
    citation_set = {c.rstrip("/").lower() for c in citations}

    for signal in signals:
        signal.pop("citation_index", None)

        url = signal.get("source_url", "").strip()

        if url:
            if url.rstrip("/").lower() not in citation_set:
                signal.setdefault("_quality_flags", []).append("url_not_in_citations")
        else:
            signal["source_url"] = ""
            signal.setdefault("_quality_flags", []).append("missing_url")

    return signals


# ─── Account Resolution ─────────────────────────────────────────────────────

def resolve_account(handle: str = "", name: str = "") -> dict | None:
    """Try to match a handle or name to a curated account.
    Returns the account dict or None."""
    if handle:
        clean = handle.lstrip("@").lower()
        if clean in ACCOUNT_LOOKUP:
            return ACCOUNT_LOOKUP[clean]

    if name:
        clean_name = name.lower().strip()
        if clean_name in NAME_LOOKUP:
            return NAME_LOOKUP[clean_name]
        for acct in CURATED_ACCOUNTS:
            if clean_name in acct["name"].lower() or acct["name"].lower() in clean_name:
                return acct

    return None


# ─── Signal Classification ──────────────────────────────────────────────────

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


def classify_signal(signal: dict, lever_hint: str, account_lever: str | None = None) -> dict:
    """Assign lever_primary, sub_variable, direction, confidence based on content keywords.
    Uses account's primary_lever as a +1 tiebreaker when available."""
    text = " ".join([
        signal.get("title", ""),
        signal.get("summary", ""),
        signal.get("raw_content", "") or "",
        " ".join(signal.get("key_facts", [])),
    ]).lower()

    # Find best sub_variable match across all levers
    best_lever = account_lever or lever_hint
    best_sub = None
    best_score = 0

    for lever, sub_vars in SUB_VAR_KEYWORDS.items():
        for sub_var, keywords in sub_vars.items():
            score = sum(1 for kw in keywords if kw in text)
            # Tiebreaker: boost account's known lever by +1
            if account_lever and lever == account_lever:
                score += 1
            elif not account_lever and lever == lever_hint:
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

    # Confidence (subtract tiebreaker to get real keyword hits)
    tiebreak_lever = account_lever or lever_hint
    real_score = best_score - 1 if best_lever == tiebreak_lever else best_score
    confidence = "high" if real_score >= 3 else "medium" if real_score >= 1 else "low"

    signal["lever_primary"] = best_lever
    signal["sub_variable"] = best_sub or "pending_classification"
    signal["direction"] = direction
    signal["confidence"] = confidence
    return signal


# ─── Validation & Quality Flagging ───────────────────────────────────────────

AGGREGATOR_PATTERNS = [
    "weekly briefing", "weekly recap", "ai update", "weekly roundup",
    "ai insiders", "news roundup", "top stories", "recap:", "ai news round",
    "funding round of the month", "weekly:", "briefing –",
]


def validate_and_flag(signal: dict, date_start: datetime, date_end: datetime) -> dict:
    """Add data_quality_flags based on URL, title, date, and source type checks."""
    flags = signal.pop("_quality_flags", [])

    # Indirect source flag
    if not signal.get("_is_direct_post", False):
        flags.append("indirect_source")

    # URL validation
    url = signal.get("source_url", "")
    if not url:
        flags.append("missing_url")
    else:
        domain = urlparse(url).netloc.lower().lstrip("www.")
        if not any(domain.endswith(kd) for kd in KNOWN_DOMAINS):
            flags.append("unknown_domain")

    # Aggregator title check
    title = signal.get("title", "")
    if any(p in title.lower() for p in AGGREGATOR_PATTERNS):
        flags.append("aggregator_title")
        signal["in_scope"] = False

    # Date range check
    pub_date = signal.get("publication_date", "")
    if pub_date:
        try:
            pd = datetime.strptime(pub_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            buffer = timedelta(days=2)
            if pd < (date_start - buffer) or pd > (date_end + buffer):
                flags.append("out_of_date_range")
        except ValueError:
            flags.append("invalid_date_format")

    # Unattributed check
    if signal.get("_unattributed", False):
        flags.append("unattributed")

    signal["data_quality_flags"] = flags
    # Clean up internal fields
    signal.pop("_is_direct_post", None)
    signal.pop("_unattributed", None)
    return signal


# ─── Deduplication ───────────────────────────────────────────────────────────

def deduplicate_signals(signals: list[dict]) -> tuple[list[dict], int]:
    """Remove signals with duplicate URLs or near-identical titles."""
    seen_urls = set()
    seen_titles = set()
    unique = []

    for signal in signals:
        url = signal.get("source_url", "").rstrip("/").lower()
        title_key = signal.get("title", "").lower().strip()

        if url and url in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue

        if url:
            seen_urls.add(url)
        if title_key:
            seen_titles.add(title_key)
        unique.append(signal)

    return unique, len(signals) - len(unique)


# ─── Record Builder ──────────────────────────────────────────────────────────

def make_signal_id(handle: str, title: str, pub_date: str) -> str:
    """Generate a deterministic signal_id per schema."""
    now = datetime.now(timezone.utc)
    date_part = pub_date.replace("-", "") if pub_date else now.strftime("%Y%m%d")
    time_part = now.strftime("%H%M%S")
    hash_input = f"{handle}{title}{pub_date}"
    short_hash = hashlib.md5(hash_input.encode()).hexdigest()[:5]
    return f"{date_part}-{SOURCE_NAME}-{time_part}-{short_hash}"


def build_signal_record(raw: dict, group: dict, account: dict | None,
                        pipeline_run_id: str, collection_batch_id: str,
                        cadence: str) -> dict:
    """Convert a parsed Perplexity result into a full signal record per schema."""
    now = datetime.now(timezone.utc)
    pub_date = raw.get("publication_date", now.strftime("%Y-%m-%d"))
    title = raw.get("title", "Untitled")[:200]
    source_pub = raw.get("source_name", "unknown")
    handle = raw.get("x_handle", "").lstrip("@")
    is_direct = raw.get("is_direct_post", False)

    # Prefer x_post_url over source_url when available
    x_post_url = raw.get("x_post_url", "").strip()
    source_url = raw.get("source_url", "").strip()
    primary_url = x_post_url if x_post_url else source_url

    # Determine lever from account if resolved, otherwise from group hint
    lever_hint = account["primary_lever"] if account else group["lever_hint"]
    category = account["category"] if account else group["group_name"]

    # Source type tag
    source_type = "direct_post" if is_direct else "indirect_reference"

    # Confidence capping for indirect sources
    confidence_cap = None
    if not is_direct:
        confidence_cap = "medium"

    record = {
        "signal_id": make_signal_id(handle, title, pub_date),
        "source_name": SOURCE_NAME,
        "source_url": primary_url,
        "fetch_timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agent_id": AGENT_ID,
        "cadence": cadence,
        "pipeline_run_id": pipeline_run_id,
        "collection_batch_id": collection_batch_id,
        # Classification — filled by classify_signal()
        "lever_primary": lever_hint,
        "lever_secondary": None,
        "direction": "~",
        "sub_variable": "pending_classification",
        "confidence": "medium",
        # Content
        "title": title,
        "summary": raw.get("summary", ""),
        "key_facts": raw.get("key_facts", []),
        "raw_content": raw.get("content_summary", None),
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
        "data_quality_flags": [],
        "tags": [
            f"x_handle:{handle}" if handle else "x_handle:unknown",
            f"account_category:{category}",
            f"source_pub:{source_pub}",
            f"query_tag:{group['query_tag']}",
            f"source_type:{source_type}",
        ],
        "schema_version": SCHEMA_VERSION,
        # Internal fields (removed by validate_and_flag)
        "_is_direct_post": is_direct,
        "_unattributed": account is None,
    }

    # Carry over quality flags from citation attachment
    if "_quality_flags" in raw:
        record["_quality_flags"] = raw["_quality_flags"]

    # Store confidence cap for post-classification application
    record["_confidence_cap"] = confidence_cap

    return record


# ─── Main Pipeline ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="espresso·ai X Signal Collector (via Perplexity)")
    parser.add_argument("--cadence", default="weekly",
                        choices=["daily", "weekly", "monthly", "quarterly", "annual"])
    parser.add_argument("--days-back", type=int, default=None,
                        help="Override: look back N days (default: auto from cadence)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print signals without writing to file")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: use only 2 account groups")
    args = parser.parse_args()

    if not API_KEY:
        print("ERROR: PERPLEXITY_API_KEY not found in .env/.env")
        return

    cadence = args.cadence
    now = datetime.now(timezone.utc)
    batch_ts = now.strftime("%Y%m%d_%H%M")
    collection_batch_id = f"batch_{batch_ts}"

    # Compute date window
    date_after, date_before = compute_date_window(cadence, now, args.days_back)

    # Parse dates for validation and file naming
    date_start = datetime.strptime(date_after, "%m/%d/%Y").replace(tzinfo=timezone.utc)
    date_end = datetime.strptime(date_before, "%m/%d/%Y").replace(tzinfo=timezone.utc)

    # File naming
    date_start_str = date_start.strftime("%Y-%m-%d")
    date_end_str = date_end.strftime("%Y-%m-%d")
    file_stem = f"{date_start_str}_{date_end_str}_x_perplexity_{cadence}"
    pipeline_run_id = f"{file_stem}_{uuid.uuid4().hex[:8]}"
    raw_dir = Path(__file__).resolve().parent.parent.parent / "research_db" / "raw"
    output_file = raw_dir / f"{file_stem}_signals.jsonl"

    # Select groups
    groups = ACCOUNT_GROUPS
    if args.test:
        groups = groups[:2]
        print("*** TEST MODE: 2 account groups only ***\n")

    total_accounts = sum(len(g["accounts"]) for g in groups)

    print(f"espresso·ai X Signal Collector (via Perplexity)")
    print(f"Pipeline run:  {pipeline_run_id}")
    print(f"Cadence:       {cadence}")
    print(f"Date window:   {date_after} → {date_before}")
    print(f"Account groups: {len(groups)}")
    print(f"Total accounts: {total_accounts}")
    print(f"Output:        {output_file}")
    print("-" * 60)

    all_signals = []
    accounts_with_signals = set()

    for i, group in enumerate(groups, 1):
        query_tag = group["query_tag"]
        lever = group["lever_hint"]

        print(f"\n[{i}/{len(groups)}] {group['group_name']} ({lever})")
        query_text = build_query(group)
        print(f"  Query: {query_text[:100]}...")

        try:
            response = query_perplexity(query_text, date_after, date_before)
            raw_text = response["choices"][0]["message"]["content"]
            citations = response.get("citations", [])

            raw_signals = parse_signals_from_response(raw_text)
            print(f"  Parsed: {len(raw_signals)} signals | Citations: {len(citations)}")

            # Cross-validate URLs against Perplexity citations
            raw_signals = cross_validate_urls(raw_signals, citations)

            # Build full records, classify, and validate
            for rs in raw_signals:
                # Resolve account from response
                account = resolve_account(
                    handle=rs.get("x_handle", ""),
                    name=rs.get("attributed_to", ""),
                )

                record = build_signal_record(
                    rs, group, account,
                    pipeline_run_id, collection_batch_id, cadence,
                )

                # Classify
                account_lever = account["primary_lever"] if account else None
                record = classify_signal(record, lever, account_lever)

                # Apply confidence cap for indirect sources
                cap = record.pop("_confidence_cap", None)
                if cap and record["confidence"] == "high":
                    record["confidence"] = cap

                # Validate and flag
                record = validate_and_flag(record, date_start, date_end)

                all_signals.append(record)

                # Track which accounts had signals
                handle = rs.get("x_handle", "").lstrip("@").lower()
                if handle and handle in ACCOUNT_LOOKUP:
                    accounts_with_signals.add(handle)

        except requests.exceptions.RequestException as e:
            print(f"  ERROR: API request failed: {e}")

        except (KeyError, IndexError) as e:
            print(f"  ERROR: Unexpected response format: {e}")

        if i < len(groups):
            time.sleep(2)

    # Deduplicate
    pre_dedup = len(all_signals)
    all_signals, dupes_removed = deduplicate_signals(all_signals)

    # ── Metrics ──
    def count_flag(flag_name):
        return sum(1 for s in all_signals if flag_name in s.get("data_quality_flags", []))

    def count_direction(d):
        return sum(1 for s in all_signals if s.get("direction") == d)

    lever_dist = {}
    account_dist = {}
    for s in all_signals:
        lev = s.get("lever_primary", "UNKNOWN")
        lever_dist[lev] = lever_dist.get(lev, 0) + 1
        handle_tag = next((t.split(":")[1] for t in s.get("tags", []) if t.startswith("x_handle:")), "unknown")
        account_dist[handle_tag] = account_dist.get(handle_tag, 0) + 1

    print(f"\n{'=' * 60}")
    print(f"Total parsed:          {pre_dedup}")
    print(f"Duplicates removed:    {dupes_removed}")
    print(f"Unique signals:        {len(all_signals)}")
    print(f"Accounts tracked:      {total_accounts}")
    print(f"Accounts with signals: {len(accounts_with_signals)}")
    print(f"Direct posts:          {len(all_signals) - count_flag('indirect_source')}")
    print(f"Indirect sources:      {count_flag('indirect_source')}")
    print(f"Unattributed:          {count_flag('unattributed')}")
    print(f"Unknown domains:       {count_flag('unknown_domain')}")
    print(f"Aggregator titles:     {count_flag('aggregator_title')}")
    print(f"Out-of-date:           {count_flag('out_of_date_range')}")
    print(f"Missing URLs:          {count_flag('missing_url')}")
    print(f"Direction: + {count_direction('+')} | - {count_direction('-')} | ~ {count_direction('~')} | ? {count_direction('?')}")
    print(f"Lever distribution:    {json.dumps(lever_dist, indent=None)}")

    if args.dry_run:
        print(f"\n*** DRY RUN — not writing to file ***")
    elif all_signals:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "a", encoding="utf-8") as f:
            for record in all_signals:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"\nAppended {len(all_signals)} records to {output_file}")
    else:
        print("\nNo signals collected — check API key and network connectivity.")

    # Write pipeline log
    run_log = {
        "pipeline_run_id": pipeline_run_id,
        "collection_batch_id": collection_batch_id,
        "cadence": cadence,
        "source": "x_twitter_via_perplexity",
        "date_window": {"after": date_after, "before": date_before},
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "queries_executed": len(groups),
        "accounts_tracked": total_accounts,
        "accounts_with_signals": len(accounts_with_signals),
        "signals_collected": pre_dedup,
        "duplicates_removed": dupes_removed,
        "signals_written": len(all_signals),
        "output_file": str(output_file) if not args.dry_run else "DRY_RUN",
        "quality_metrics": {
            "direct_post_count": len(all_signals) - count_flag("indirect_source"),
            "indirect_source_count": count_flag("indirect_source"),
            "unattributed_count": count_flag("unattributed"),
            "unknown_domain_count": count_flag("unknown_domain"),
            "aggregator_title_count": count_flag("aggregator_title"),
            "out_of_date_count": count_flag("out_of_date_range"),
            "missing_url_count": count_flag("missing_url"),
            "url_not_in_citations_count": count_flag("url_not_in_citations"),
            "direction_distribution": {
                "+": count_direction("+"),
                "-": count_direction("-"),
                "~": count_direction("~"),
                "?": count_direction("?"),
            },
            "lever_distribution": lever_dist,
            "account_distribution": account_dist,
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
        src_type = next((t.split(":")[1] for t in rec.get("tags", []) if t.startswith("source_type:")), "?")
        title = rec["title"][:60]
        flags = rec.get("data_quality_flags", [])
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  [{lev:8s} {d}] @{handle:20s} | {src_type:18s} | {sub:30s} | {title}{flag_str}")

    if len(all_signals) > 10:
        print(f"  ... and {len(all_signals) - 10} more")


if __name__ == "__main__":
    main()
