"""
espresso·ai — X/Twitter Signal Collector (via Claude Web Search)
Uses Claude API (Sonnet + web_search tool) to find AI-related posts and statements
from curated high-signal X/Twitter accounts.
Classifies against Scale Levers and outputs signal records to research_db/raw/ in JSONL format.

Usage:
    python .claude/scripts/collect_x_claude_signals.py --cadence weekly [--days-back 7] [--test] [--dry-run]
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
API_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-6"
AGENT_ID = "x-claude-collector"
SCHEMA_VERSION = "1.0"
SOURCE_NAME = "twitter"

# ─── Cost Estimation ─────────────────────────────────────────────────────────
# Pricing per million tokens (as of 2026-03)

MODEL_PRICING = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate API cost in USD from token counts."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["claude-sonnet-4-6"])
    return (input_tokens * pricing["input"] / 1_000_000) + (output_tokens * pricing["output"] / 1_000_000)


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
# Accounts grouped by category. One Claude API query per group (7 total).

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
        "group_name": "capital_infrastructure",
        "lever_hint": "CAPITAL",
        "query_tag": "x_capital_infrastructure",
        "accounts": ["eladgil", "saranormous", "naval", "GridStatusBlog", "datacaborenterdy"],
        "topic": "AI venture funding, hyperscaler capex, investment trends, AI energy consumption, data center power, and infrastructure buildout",
    },
    {
        "group_name": "journalists_analysts",
        "lever_hint": "INDUSTRY",
        "query_tag": "x_journalists_analysts",
        "accounts": ["karaswisher", "CaseyNewton", "zoeschiffer", "SemiAnalysis", "dyaborlanpatel", "EmanuelMaiberg"],
        "topic": "AI industry analysis, chip supply chains, company strategy, and market dynamics",
    },
]


# ─── User Prompt Builder ────────────────────────────────────────────────────

def build_user_prompt(group: dict, start_date: str, end_date: str) -> str:
    """Construct a user prompt for the Claude API from an account group."""
    names_with_handles = ", ".join(
        f"{ACCOUNT_LOOKUP[h.lower()]['name']} (@{h})"
        for h in group["accounts"]
        if h.lower() in ACCOUNT_LOOKUP
    )
    n_accounts = len(group["accounts"])
    if n_accounts <= 3:
        signal_target = "3-5"
    elif n_accounts <= 5:
        signal_target = "5-8"
    else:
        signal_target = "6-10"

    return (
        f"Search for recent AI-related public statements and X/Twitter posts by: "
        f"{names_with_handles}.\n\n"
        f"Date window: {start_date} to {end_date}.\n"
        f"Topic focus: {group['topic']}.\n\n"
        f"Search for:\n"
        f"1. Their recent X/Twitter posts about AI (search x.com or twitter.com)\n"
        f"2. News articles quoting or referencing their recent AI-related statements\n"
        f"3. Newsletter coverage of their public commentary\n\n"
        f"Return a JSON array of {signal_target} individual signals."
    )


# ─── System Prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a research analyst for an AI intelligence service called espresso·ai.

TASK: Search the web for recent public statements, posts, and commentary by specific individuals on X/Twitter about artificial intelligence. Find news articles, blog posts, newsletters, and media coverage that reference or quote their recent X/Twitter posts.

SEARCH STRATEGY:
- Search for each person by name AND their X/Twitter handle
- Use queries like "[name] AI" or "site:x.com [handle]" to find relevant content
- Search for news articles quoting their recent statements
- Focus on the specific date window provided

SEARCH EFFICIENCY:
- Combine multiple people from the same group in a single search query when possible
- Extract all relevant signals from a page before searching further
- Stop searching once you have enough high-quality signals for the group
- Prioritize results from the target date window — discard older content

RULES:
1. Return ONLY a JSON array. No text outside the array.
2. Extract 5-8 of the most important INDIVIDUAL statements or posts, each attributed to a specific person.
3. Each entry must be a SPECIFIC statement, claim, announcement, or opinion — not a summary of multiple posts.
4. PRIORITIZE entries where you can identify the specific X/Twitter post being referenced.
5. For source_url, use the actual URL you found. If you can identify the direct X/Twitter post URL, include it as "x_post_url" as well.

REQUIRED FIELDS per object:
- "attributed_to": name of the person who made the statement (string)
- "x_handle": their X/Twitter handle without @ (string)
- "title": brief description of what they said (max 200 chars, string)
- "source_name": publication name where this was found, e.g. "Reuters", "The Verge", "X/Twitter" (string)
- "source_url": direct URL to the article or post (string, empty string if unavailable)
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
- Do NOT fabricate URLs. Use only URLs from your search results. If unsure, use empty string.
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
    """Return (start_date, end_date) in YYYY-MM-DD format."""
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

    return start.strftime("%Y-%m-%d"), reference_date.strftime("%Y-%m-%d")


# ─── Claude API ──────────────────────────────────────────────────────────────

def query_claude(system_prompt: str, user_prompt: str,
                 model: str = DEFAULT_MODEL,
                 max_web_searches: int = 5) -> dict:
    """Call Claude Messages API with web search tool.
    Returns the raw API response dict."""
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 8000,
        "tools": [
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": max_web_searches,
            }
        ],
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
    }

    resp = requests.post(CLAUDE_API_URL, headers=headers, json=payload, timeout=180)
    resp.raise_for_status()
    return resp.json()


def query_claude_with_retry(system_prompt: str, user_prompt: str,
                            model: str = DEFAULT_MODEL,
                            max_web_searches: int = 10,
                            max_retries: int = 3,
                            base_delay: int = 5) -> dict:
    """Call Claude API with exponential backoff retry for rate limits and overload."""
    for attempt in range(max_retries + 1):
        try:
            return query_claude(system_prompt, user_prompt, model, max_web_searches)
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status == 429 and attempt < max_retries:
                retry_after = int(e.response.headers.get("retry-after", base_delay * (2 ** attempt)))
                print(f"  Rate limited. Retrying in {retry_after}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(retry_after)
            elif status == 529 and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                print(f"  API overloaded. Retrying in {delay}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(delay)
            else:
                raise


# ─── Response Parsing ────────────────────────────────────────────────────────

def parse_claude_response(response: dict) -> tuple[list[dict], list[str]]:
    """Parse Claude API response with web search results.
    Returns (parsed_signals, citation_urls)."""
    content_blocks = response.get("content", [])

    # Collect citation URLs from web search results
    citation_urls = []
    for block in content_blocks:
        if block.get("type") == "web_search_tool_result":
            for result in block.get("content", []):
                if not isinstance(result, dict):
                    continue
                if result.get("type") == "web_result":
                    url = result.get("url", "")
                    if url:
                        citation_urls.append(url)

    # Extract text from all text blocks
    text_parts = []
    for block in content_blocks:
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))

    full_text = "\n".join(text_parts)
    signals = parse_signals_from_response(full_text)

    return signals, citation_urls


def parse_signals_from_response(raw_text: str) -> list[dict]:
    """Extract JSON array from response text."""
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
    """Cross-validate model-returned URLs against web search citation URLs."""
    citation_set = {c.rstrip("/").lower() for c in citations}

    for signal in signals:
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
    """Convert a parsed Claude result into a full signal record per schema."""
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

    # Carry over quality flags from citation cross-validation
    if "_quality_flags" in raw:
        record["_quality_flags"] = raw["_quality_flags"]

    # Store confidence cap for post-classification application
    record["_confidence_cap"] = confidence_cap

    return record


# ─── Main Pipeline ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="espresso·ai X Signal Collector (via Claude Web Search)")
    parser.add_argument("--cadence", default="weekly",
                        choices=["daily", "weekly", "monthly", "quarterly", "annual"])
    parser.add_argument("--days-back", type=int, default=None,
                        help="Override: look back N days (default: auto from cadence)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Claude model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--max-web-searches", type=int, default=5,
                        help="Max web searches per account group (default: 5)")
    parser.add_argument("--max-cost", type=float, default=None,
                        help="Stop processing if estimated cost exceeds this amount in USD")
    parser.add_argument("--groups", nargs="+", default=None,
                        help="Run only specific groups by name (e.g., --groups ai_lab_leaders researchers)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print signals without writing to file")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: use only 2 account groups")
    args = parser.parse_args()

    if not API_KEY:
        print("ERROR: ANTHROPIC_API_KEY (or CLAUDE_API_KEY) not found in .env/.env")
        return

    cadence = args.cadence
    model = args.model
    max_web_searches = args.max_web_searches
    now = datetime.now(timezone.utc)
    batch_ts = now.strftime("%Y%m%d_%H%M")
    collection_batch_id = f"batch_{batch_ts}"

    # Compute date window
    date_start_str, date_end_str = compute_date_window(cadence, now, args.days_back)

    # Parse dates for validation
    date_start = datetime.strptime(date_start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    date_end = datetime.strptime(date_end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # File naming
    file_stem = f"{date_start_str}_{date_end_str}_x_claude_{cadence}"
    pipeline_run_id = f"{file_stem}_{uuid.uuid4().hex[:8]}"
    raw_dir = Path(__file__).resolve().parent.parent.parent / "research_db" / "raw"
    output_file = raw_dir / f"{file_stem}_signals.jsonl"

    # Select groups
    groups = ACCOUNT_GROUPS
    if args.groups:
        groups = [g for g in groups if g["group_name"] in args.groups]
        if not groups:
            print(f"ERROR: No matching groups. Available: {[g['group_name'] for g in ACCOUNT_GROUPS]}")
            return
        print(f"*** SELECTIVE MODE: {[g['group_name'] for g in groups]} ***\n")
    if args.test:
        groups = groups[:2]
        print("*** TEST MODE: 2 account groups only ***\n")

    total_accounts = sum(len(g["accounts"]) for g in groups)

    print(f"espresso·ai X Signal Collector (via Claude Web Search)")
    print(f"Pipeline run:       {pipeline_run_id}")
    print(f"Cadence:            {cadence}")
    print(f"Model:              {model}")
    print(f"Max web searches:   {max_web_searches}/group")
    print(f"Date window:        {date_start_str} → {date_end_str}")
    print(f"Account groups:     {len(groups)}")
    print(f"Total accounts:     {total_accounts}")
    print(f"Output:             {output_file}")
    print("-" * 60)

    all_signals = []
    accounts_with_signals = set()
    total_input_tokens = 0
    total_output_tokens = 0
    group_stats = []

    for i, group in enumerate(groups, 1):
        query_tag = group["query_tag"]
        lever = group["lever_hint"]

        print(f"\n[{i}/{len(groups)}] {group['group_name']} ({lever})")
        user_prompt = build_user_prompt(group, date_start_str, date_end_str)
        print(f"  Prompt: {user_prompt[:100]}...")

        try:
            response = query_claude_with_retry(
                SYSTEM_PROMPT, user_prompt,
                model=model,
                max_web_searches=max_web_searches,
            )

            # Track token usage
            usage = response.get("usage", {})
            total_input_tokens += usage.get("input_tokens", 0)
            total_output_tokens += usage.get("output_tokens", 0)
            print(f"  Tokens: {usage.get('input_tokens', 0)} in / {usage.get('output_tokens', 0)} out")

            # Parse response
            raw_signals, citation_urls = parse_claude_response(response)
            print(f"  Parsed: {len(raw_signals)} signals | Citations: {len(citation_urls)}")

            # Track per-group stats
            group_stats.append({
                "group_name": group["group_name"],
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "signals_parsed": len(raw_signals),
                "estimated_cost_usd": round(estimate_cost(
                    model, usage.get("input_tokens", 0), usage.get("output_tokens", 0)
                ), 4),
            })

            # Cross-validate URLs against web search citations
            raw_signals = cross_validate_urls(raw_signals, citation_urls)

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

        # Budget check
        if args.max_cost is not None:
            running_cost = estimate_cost(model, total_input_tokens, total_output_tokens)
            if running_cost >= args.max_cost:
                print(f"\n  BUDGET CAP: ${running_cost:.2f} >= ${args.max_cost:.2f}. Stopping after {i}/{len(groups)} groups.")
                break

        if i < len(groups):
            time.sleep(3)

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
    print(f"API tokens used:       {total_input_tokens} in / {total_output_tokens} out")
    print(f"Model:                 {model}")
    print(f"Estimated cost:        ${estimate_cost(model, total_input_tokens, total_output_tokens):.2f}")
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
        "source": "x_twitter_via_claude",
        "date_window": {"start": date_start_str, "end": date_end_str},
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "queries_executed": len(groups),
        "accounts_tracked": total_accounts,
        "accounts_with_signals": len(accounts_with_signals),
        "signals_collected": pre_dedup,
        "duplicates_removed": dupes_removed,
        "signals_written": len(all_signals),
        "output_file": str(output_file) if not args.dry_run else "DRY_RUN",
        "api_usage": {
            "model": model,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "max_web_searches_per_group": max_web_searches,
            "estimated_cost_usd": round(estimate_cost(model, total_input_tokens, total_output_tokens), 4),
            "group_stats": group_stats,
        },
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
