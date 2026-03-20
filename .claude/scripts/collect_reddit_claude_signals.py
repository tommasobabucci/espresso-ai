"""
espresso·ai — Reddit Signal Collector (via Claude Web Search)
Uses Claude API (Sonnet + web_search tool) to find AI-related posts and discussions
from curated high-signal Reddit subreddits.
Classifies against Scale Levers and outputs signal records to research_db/raw/ in JSONL format.

Usage:
    python .claude/scripts/collect_reddit_claude_signals.py --cadence weekly [--days-back 7] [--test] [--dry-run]
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
AGENT_ID = "reddit-claude-collector"
SCHEMA_VERSION = "1.0"
SOURCE_NAME = "reddit"

# ─── Cost Estimation ─────────────────────────────────────────────────────────

MODEL_PRICING = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate API cost in USD from token counts."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["claude-sonnet-4-6"])
    return (input_tokens * pricing["input"] / 1_000_000) + (output_tokens * pricing["output"] / 1_000_000)


# ─── Subreddit Groups ────────────────────────────────────────────────────────
# Curated subreddits grouped by theme and tier.
# Tier determines which cadences include the group.

SUBREDDIT_GROUPS = [
    {
        "group_name": "ml_research",
        "lever_hint": "COMPUTE",
        "query_tag": "reddit_ml_research",
        "subreddits": ["MachineLearning", "deeplearning"],
        "topic": "AI research papers, model architectures, benchmark results, and training methodology",
        "tier": 1,
    },
    {
        "group_name": "open_source_models",
        "lever_hint": "COMPUTE",
        "query_tag": "reddit_open_source",
        "subreddits": ["LocalLLaMA"],
        "topic": "open-source model releases, inference optimization, quantization, and hardware benchmarks",
        "tier": 1,
    },
    {
        "group_name": "general_ai_policy",
        "lever_hint": "SOCIETY",
        "query_tag": "reddit_general_ai",
        "subreddits": ["artificial", "ArtificialIntelligence"],
        "topic": "AI news, policy debates, enterprise adoption patterns, and societal impact",
        "tier": 1,
    },
    {
        "group_name": "market_sentiment",
        "lever_hint": "CAPITAL",
        "query_tag": "reddit_market_sentiment",
        "subreddits": ["singularity", "OpenAI"],
        "topic": "AGI timeline analysis, AI market dynamics, product releases, and investment sentiment",
        "tier": 2,
    },
    {
        "group_name": "industry_practice",
        "lever_hint": "INDUSTRY",
        "query_tag": "reddit_industry",
        "subreddits": ["datascience", "experienceddevs"],
        "topic": "enterprise AI deployment, production challenges, workforce displacement, and practitioner insights",
        "tier": 2,
    },
    {
        "group_name": "regulation_mainstream",
        "lever_hint": "GOV",
        "query_tag": "reddit_regulation",
        "subreddits": ["technology", "Futurology"],
        "topic": "AI regulation, policy enforcement, public sentiment on AI, and mainstream technology impact",
        "tier": 3,
    },
]

# Cadence → which tiers to include
CADENCE_TIERS = {
    "daily": {1},
    "weekly": {1, 2},
    "monthly": {1, 2, 3},
    "quarterly": {1, 2, 3},
    "annual": {1, 2, 3},
}


def select_groups(cadence: str, test: bool = False) -> list[dict]:
    """Select subreddit groups based on cadence tier and test mode."""
    allowed = CADENCE_TIERS.get(cadence, {1, 2})
    groups = [g for g in SUBREDDIT_GROUPS if g["tier"] in allowed]
    return groups[:2] if test else groups


# ─── User Prompt Builder ────────────────────────────────────────────────────

def build_user_prompt(group: dict, start_date: str, end_date: str) -> str:
    """Construct a user prompt for the Claude API from a subreddit group."""
    subs = ", ".join(f"r/{s}" for s in group["subreddits"])
    sub_search_hints = " OR ".join(
        f"site:reddit.com/r/{s}" for s in group["subreddits"]
    )
    return (
        f"Search Reddit for high-signal AI posts in: {subs}.\n\n"
        f"Date window: {start_date} to {end_date}.\n"
        f"Topic focus: {group['topic']}.\n\n"
        f"Search strategy:\n"
        f"1. Use queries like: {sub_search_hints}\n"
        f"2. Focus on posts with significant community engagement (high upvotes)\n"
        f"3. Prioritize: research findings, practitioner experience reports, "
        f"primary source discussions, model release announcements\n"
        f"4. Exclude: memes, basic questions, prompt engineering tips, "
        f"self-promotional content, weekly discussion threads\n\n"
        f"Return a JSON array of 5-8 individual signals."
    )


# ─── System Prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a research analyst for an AI intelligence service called espresso·ai.

TASK: Search Reddit for high-signal AI posts in specific subreddits. Find posts with substantial community engagement that contain specific claims, findings, practitioner experiences, or primary source discussions about artificial intelligence.

SEARCH STRATEGY:
- Use "site:reddit.com/r/[subreddit]" queries to search within specific subreddits
- Focus on posts with significant community engagement (many upvotes and comments)
- Look for posts discussing research papers, model releases, deployment experiences, policy changes
- Cross-reference: if a Reddit post links to a primary source (paper, article, announcement), include that URL

RULES:
1. Return ONLY a JSON array. No text outside the array.
2. Extract 5-8 of the most important individual posts, each from a specific subreddit.
3. Each entry must contain a SPECIFIC claim, finding, experience, or discussion — not a general topic summary.
4. PRIORITIZE posts that cite primary sources (papers, articles, official announcements).
5. For source_url, use the actual Reddit post URL you found. If the post links to an external primary source, include it as "primary_source_url".

REQUIRED FIELDS per object:
- "subreddit": subreddit name without r/ prefix (string)
- "title": the Reddit post title (max 200 chars, string)
- "source_url": direct URL to the Reddit post (string, empty string if unavailable)
- "primary_source_url": URL to external source linked in the post, if any (string, empty string if none)
- "publication_date": YYYY-MM-DD (string)
- "summary": 1-2 sentence factual summary of the post's core claim or finding (string)
- "content_summary": 3-5 sentences on the content and its strategic implications for AI (string)
- "key_facts": 3-5 specific verifiable claims from the post or linked source (array of strings)
- "post_type": one of "research", "experience", "news_discussion", "analysis" (string)
- "has_primary_source": true if the post links to or discusses a primary source (paper, article, announcement), false if purely community discussion (boolean)
- "reddit_score": approximate upvote count if visible from search results (integer, 0 if unknown)
- "reddit_comments": approximate comment count if visible (integer, 0 if unknown)

CRITICAL RULES:
- Each object must describe ONE specific Reddit post.
- Prefer RECENT posts (within the search date window) over older ones.
- Do NOT fabricate URLs. Use only URLs from your search results. If unsure, use empty string.
- Do NOT include aggregator content ("daily digest", "weekly thread", "monthly roundup").
- Do NOT include meme posts, basic questions, or prompt engineering tips.
- Ensure valid JSON — no trailing commas, no markdown fences."""


# ─── Known Domains ───────────────────────────────────────────────────────────

KNOWN_DOMAINS = {
    "reddit.com", "old.reddit.com",
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
    "arxiv.org", "huggingface.co", "github.com",
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


def classify_signal(signal: dict, lever_hint: str) -> dict:
    """Assign lever_primary, sub_variable, direction, confidence based on content keywords.
    Uses subreddit group lever_hint as tiebreaker."""
    text = " ".join([
        signal.get("title", ""),
        signal.get("summary", ""),
        signal.get("raw_content", "") or "",
        " ".join(signal.get("key_facts", [])),
    ]).lower()

    # Find best sub_variable match across all levers
    best_lever = lever_hint
    best_sub = None
    best_score = 0

    for lever, sub_vars in SUB_VAR_KEYWORDS.items():
        for sub_var, keywords in sub_vars.items():
            score = sum(1 for kw in keywords if kw in text)
            # Tiebreaker: boost group's lever_hint by +1
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

    # Confidence (subtract tiebreaker to get real keyword hits)
    real_score = best_score - 1 if best_lever == lever_hint else best_score
    confidence = "high" if real_score >= 3 else "medium" if real_score >= 1 else "low"

    signal["lever_primary"] = best_lever
    signal["sub_variable"] = best_sub or "pending_classification"
    signal["direction"] = direction
    signal["confidence"] = confidence
    return signal


# ─── Validation & Quality Flagging ───────────────────────────────────────────

AGGREGATOR_PATTERNS = [
    "weekly briefing", "weekly recap", "ai update", "weekly roundup",
    "daily digest", "monthly roundup", "weekly thread", "megathread",
    "ai insiders", "news roundup", "top stories", "recap:",
    "funding round of the month", "weekly:", "briefing –",
    "monthly discussion", "daily discussion",
]

REDDIT_QUALITY_PATTERNS = {
    "speculation_heavy": ["might", "could potentially", "speculation", "what if", "tinfoil", "conspiracy", "i think maybe"],
    "meme_or_humor": ["lmao", "shitpost", "[meme]", "satire", "joke", "lol"],
    "self_promotional": ["my project", "i built", "check out my", "my startup", "launching today"],
    "vendor_astroturf": ["we're excited to announce", "our platform", "try our", "announcing our"],
}


def validate_and_flag(signal: dict, date_start: datetime, date_end: datetime) -> dict:
    """Add data_quality_flags based on URL, title, date, post type, and Reddit-specific checks."""
    flags = signal.pop("_quality_flags", [])

    post_type = signal.pop("_post_type", "news_discussion")
    has_primary = signal.pop("_has_primary_source", False)

    # No primary source flag
    if not has_primary:
        flags.append("no_primary_source")

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

    # Reddit-specific quality pattern checks
    title_lower = title.lower()
    summary_lower = signal.get("summary", "").lower()
    check_text = title_lower + " " + summary_lower
    for flag_name, patterns in REDDIT_QUALITY_PATTERNS.items():
        if any(p in check_text for p in patterns):
            flags.append(flag_name)

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

    signal["data_quality_flags"] = flags
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

def make_signal_id(subreddit: str, title: str, pub_date: str) -> str:
    """Generate a deterministic signal_id per schema."""
    now = datetime.now(timezone.utc)
    date_part = pub_date.replace("-", "") if pub_date else now.strftime("%Y%m%d")
    time_part = now.strftime("%H%M%S")
    hash_input = f"{subreddit}{title}{pub_date}"
    short_hash = hashlib.md5(hash_input.encode()).hexdigest()[:5]
    return f"{date_part}-{SOURCE_NAME}-{time_part}-{short_hash}"


def build_signal_record(raw: dict, group: dict,
                        pipeline_run_id: str, collection_batch_id: str,
                        cadence: str) -> dict:
    """Convert a parsed Claude result into a full signal record per schema."""
    now = datetime.now(timezone.utc)
    pub_date = raw.get("publication_date", now.strftime("%Y-%m-%d"))
    title = raw.get("title", "Untitled")[:200]
    subreddit = raw.get("subreddit", "unknown")
    post_type = raw.get("post_type", "news_discussion")
    has_primary = raw.get("has_primary_source", False)
    reddit_score = raw.get("reddit_score", 0)
    reddit_comments = raw.get("reddit_comments", 0)

    # URL logic: primary source is authoritative; Reddit post is metadata
    primary_source_url = raw.get("primary_source_url", "").strip()
    reddit_url = raw.get("source_url", "").strip()
    source_url = primary_source_url if primary_source_url else reddit_url

    lever_hint = group["lever_hint"]

    # Confidence capping based on source type
    confidence_cap = None
    if not has_primary:
        if post_type in ("experience", "analysis", "research"):
            confidence_cap = "medium"
        else:
            confidence_cap = "low"

    tags = [
        f"subreddit:{subreddit}",
        f"post_type:{post_type}",
        f"reddit_score:{reddit_score}",
        f"reddit_comments:{reddit_comments}",
        f"query_tag:{group['query_tag']}",
        f"has_primary_source:{has_primary}",
    ]
    if reddit_url and reddit_url != source_url:
        tags.append(f"reddit_post_url:{reddit_url}")

    record = {
        "signal_id": make_signal_id(subreddit, title, pub_date),
        "source_name": SOURCE_NAME,
        "source_url": source_url,
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
        "tags": tags,
        "schema_version": SCHEMA_VERSION,
        # Internal fields (removed by validate_and_flag)
        "_post_type": post_type,
        "_has_primary_source": has_primary,
    }

    # Carry over quality flags from citation cross-validation
    if "_quality_flags" in raw:
        record["_quality_flags"] = raw["_quality_flags"]

    # Store confidence cap for post-classification application
    record["_confidence_cap"] = confidence_cap

    return record


# ─── Main Pipeline ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="espresso·ai Reddit Signal Collector (via Claude Web Search)")
    parser.add_argument("--cadence", default="weekly",
                        choices=["daily", "weekly", "monthly", "quarterly", "annual"])
    parser.add_argument("--days-back", type=int, default=None,
                        help="Override: look back N days (default: auto from cadence)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Claude model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--max-web-searches", type=int, default=5,
                        help="Max web searches per subreddit group (default: 10)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print signals without writing to file")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: use only 2 subreddit groups")
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
    file_stem = f"{date_start_str}_{date_end_str}_reddit_claude_{cadence}"
    pipeline_run_id = f"{file_stem}_{uuid.uuid4().hex[:8]}"
    raw_dir = Path(__file__).resolve().parent.parent.parent / "research_db" / "raw"
    output_file = raw_dir / f"{file_stem}_signals.jsonl"

    # Select groups based on cadence tier
    groups = select_groups(cadence, args.test)
    if args.test:
        print("*** TEST MODE: 2 subreddit groups only ***\n")

    total_subreddits = sum(len(g["subreddits"]) for g in groups)

    print(f"espresso·ai Reddit Signal Collector (via Claude Web Search)")
    print(f"Pipeline run:       {pipeline_run_id}")
    print(f"Cadence:            {cadence}")
    print(f"Model:              {model}")
    print(f"Max web searches:   {max_web_searches}/group")
    print(f"Date window:        {date_start_str} → {date_end_str}")
    print(f"Subreddit groups:   {len(groups)}")
    print(f"Total subreddits:   {total_subreddits}")
    print(f"Output:             {output_file}")
    print("-" * 60)

    all_signals = []
    subreddits_with_signals = set()
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
                record = build_signal_record(
                    rs, group,
                    pipeline_run_id, collection_batch_id, cadence,
                )

                # Classify
                record = classify_signal(record, lever)

                # Apply confidence cap
                cap = record.pop("_confidence_cap", None)
                if cap:
                    conf_rank = {"high": 3, "medium": 2, "low": 1}
                    if conf_rank.get(record["confidence"], 0) > conf_rank.get(cap, 0):
                        record["confidence"] = cap

                # Validate and flag
                record = validate_and_flag(record, date_start, date_end)

                all_signals.append(record)

                # Track which subreddits had signals
                sub = rs.get("subreddit", "").lower()
                if sub:
                    subreddits_with_signals.add(sub)

        except requests.exceptions.RequestException as e:
            print(f"  ERROR: API request failed: {e}")

        except (KeyError, IndexError) as e:
            print(f"  ERROR: Unexpected response format: {e}")

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
    subreddit_dist = {}
    post_type_dist = {}
    for s in all_signals:
        lev = s.get("lever_primary", "UNKNOWN")
        lever_dist[lev] = lever_dist.get(lev, 0) + 1
        sub_tag = next((t.split(":")[1] for t in s.get("tags", []) if t.startswith("subreddit:")), "unknown")
        subreddit_dist[sub_tag] = subreddit_dist.get(sub_tag, 0) + 1
        pt_tag = next((t.split(":")[1] for t in s.get("tags", []) if t.startswith("post_type:")), "unknown")
        post_type_dist[pt_tag] = post_type_dist.get(pt_tag, 0) + 1

    print(f"\n{'=' * 60}")
    print(f"Total parsed:          {pre_dedup}")
    print(f"Duplicates removed:    {dupes_removed}")
    print(f"Unique signals:        {len(all_signals)}")
    print(f"Subreddits tracked:    {total_subreddits}")
    print(f"Subreddits w/ signals: {len(subreddits_with_signals)}")
    print(f"With primary source:   {len(all_signals) - count_flag('no_primary_source')}")
    print(f"No primary source:     {count_flag('no_primary_source')}")
    print(f"Speculation heavy:     {count_flag('speculation_heavy')}")
    print(f"Unknown domains:       {count_flag('unknown_domain')}")
    print(f"Aggregator titles:     {count_flag('aggregator_title')}")
    print(f"Out-of-date:           {count_flag('out_of_date_range')}")
    print(f"Missing URLs:          {count_flag('missing_url')}")
    print(f"API tokens used:       {total_input_tokens} in / {total_output_tokens} out")
    print(f"Model:                 {model}")
    print(f"Estimated cost:        ${estimate_cost(model, total_input_tokens, total_output_tokens):.2f}")
    print(f"Direction: + {count_direction('+')} | - {count_direction('-')} | ~ {count_direction('~')} | ? {count_direction('?')}")
    print(f"Lever distribution:    {json.dumps(lever_dist, indent=None)}")
    print(f"Post type dist:        {json.dumps(post_type_dist, indent=None)}")

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
        "source": "reddit_via_claude",
        "date_window": {"start": date_start_str, "end": date_end_str},
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "queries_executed": len(groups),
        "subreddits_tracked": total_subreddits,
        "subreddits_with_signals": len(subreddits_with_signals),
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
            "with_primary_source_count": len(all_signals) - count_flag("no_primary_source"),
            "no_primary_source_count": count_flag("no_primary_source"),
            "speculation_heavy_count": count_flag("speculation_heavy"),
            "meme_or_humor_count": count_flag("meme_or_humor"),
            "self_promotional_count": count_flag("self_promotional"),
            "vendor_astroturf_count": count_flag("vendor_astroturf"),
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
            "subreddit_distribution": subreddit_dist,
            "post_type_distribution": post_type_dist,
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
        subreddit = next((t.split(":")[1] for t in rec.get("tags", []) if t.startswith("subreddit:")), "?")
        pt = next((t.split(":")[1] for t in rec.get("tags", []) if t.startswith("post_type:")), "?")
        title = rec["title"][:55]
        flags = rec.get("data_quality_flags", [])
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  [{lev:8s} {d}] r/{subreddit:22s} | {pt:18s} | {sub:30s} | {title}{flag_str}")

    if len(all_signals) > 10:
        print(f"  ... and {len(all_signals) - 10} more")


if __name__ == "__main__":
    main()
