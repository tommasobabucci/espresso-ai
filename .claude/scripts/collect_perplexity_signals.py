"""
espresso·ai — Weekly Signal Collector
Uses Perplexity API (sonar-pro) to search for AI news across prioritized sources.
Outputs signal records to research_db/raw/ in JSONL format per DB_SCHEMA.md.

Usage:
    python research_db/collect_weekly_signals.py [--cadence weekly] [--days-back 7]
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
AGENT_ID = "perplexity-weekly-collector"
SCHEMA_VERSION = "1.0"

# ─── Domain Configuration ────────────────────────────────────────────────────
# Trusted domains (used for post-hoc validation, NOT for search_domain_filter).
# Perplexity's allowlist filter blocks paywalled tier-1 sources, so we use a
# denylist approach instead: block known low-quality domains at the API level,
# validate source quality post-hoc against these tiers.
# ArXiv excluded — collected separately via collect_arxiv_signals.py.

DOMAIN_TIERS = {
    "tier1_business": [
        "reuters.com", "wsj.com", "nytimes.com", "ft.com",
        "bloomberg.com", "theinformation.com",
    ],
    "tier2_tech": [
        "arstechnica.com", "theverge.com", "wired.com", "techcrunch.com",
        "technologyreview.com", "venturebeat.com",
    ],
    "tier3_international": [
        "bbc.com", "cnn.com", "asia.nikkei.com", "scmp.com",
        "economist.com", "politico.com", "politico.eu",
    ],
    "tier4_industry": [
        "openai.com", "deepmind.google", "anthropic.com",
        "ai.meta.com", "blogs.microsoft.com", "blogs.nvidia.com", "sec.gov",
    ],
    "tier5_specialist": [
        "spglobal.com", "semianalysis.com", "anandtech.com",
        "tomshardware.com", "theregister.com", "semafor.com",
        "axios.com", "cnbc.com", "fortune.com", "forbes.com",
        "datacenterknowledge.com", "supplychaindive.com",
        "deloitte.com", "mckinsey.com", "goldmansachs.com",
        "crunchbase.com", "news.crunchbase.com", "trendforce.com",
    ],
}

ALL_KNOWN_DOMAINS = set()
for _domains in DOMAIN_TIERS.values():
    ALL_KNOWN_DOMAINS.update(_domains)

# Denylist: low-quality sources to exclude via search_domain_filter (prefix with -)
# Max 20 entries for the API.
DOMAIN_DENYLIST = [
    "-reddit.com", "-twitter.com", "-x.com", "-medium.com",
    "-quora.com", "-youtube.com", "-tiktok.com", "-facebook.com",
    "-linkedin.com", "-pinterest.com", "-instagram.com",
    "-einpresswire.com", "-prnewswire.com", "-businesswire.com",
    "-globenewswire.com", "-wikipedia.org",
]


def get_domains_for_tiers(tier_keys: list[str]) -> list[str]:
    """Flatten selected tier keys into a single domain list (max 20).
    Kept for potential future use with allowlist-mode queries."""
    domains = []
    for key in tier_keys:
        domains.extend(DOMAIN_TIERS.get(key, []))
    return domains[:20]


# ─── Search Queries ──────────────────────────────────────────────────────────
# Each query targets one Scale Lever. Date ranges are handled at the API level,
# not in query text. Source quality is enforced via denylist + post-hoc validation.

SEARCH_QUERIES = [
    {
        "query": (
            "Most important AI chip, semiconductor, data center, "
            "and compute infrastructure news stories from reputable sources "
            "like Reuters, Bloomberg, WSJ, Financial Times, Nikkei Asia. "
            "Include TSMC, Nvidia, AMD, Intel, Google TPU, AWS Trainium announcements. "
            "Focus on manufacturing capacity, cost per flop, supply chain, data center buildout."
        ),
        "lever_hint": "COMPUTE",
        "query_tag": "compute_infrastructure",
    },
    {
        "query": (
            "Most significant news stories about AI energy consumption, "
            "data center power demand, renewable energy for AI workloads, "
            "grid capacity constraints, cooling technology breakthroughs, "
            "power purchase agreements by tech companies, and AI carbon footprint. "
            "Prefer sources like Reuters, Bloomberg, BBC, Wired, NYT."
        ),
        "lever_hint": "ENERGY",
        "query_tag": "energy_environment",
    },
    {
        "query": (
            "Most important AI enterprise adoption, workforce impact, and talent news. "
            "Include AI hiring trends, job displacement or layoffs attributed to AI, "
            "new enterprise AI deployments at scale, AI literacy and skills programs, "
            "and public trust incidents involving AI systems. "
            "Prefer sources like WSJ, NYT, Financial Times, MIT Technology Review, BBC, CNN."
        ),
        "lever_hint": "SOCIETY",
        "query_tag": "society_human_capital",
    },
    {
        "query": (
            "Biggest stories about AI transforming specific industries: "
            "healthcare AI deployments, financial services AI, manufacturing AI, "
            "logistics and supply chain AI, legal AI. "
            "Include production deployments with measurable ROI, pilot-to-production "
            "conversions, business model changes driven by AI. "
            "Prefer sources like Reuters, Bloomberg, WSJ, Forbes, TechCrunch."
        ),
        "lever_hint": "INDUSTRY",
        "query_tag": "industry_transformation",
    },
    {
        "query": (
            "Most significant AI investment, funding, and capital allocation stories. "
            "Include venture capital rounds, hyperscaler capex announcements, "
            "AI-related M&A and IPOs, corporate AI budget shifts, "
            "and AI company valuation changes. "
            "Prefer sources like WSJ, Bloomberg, Financial Times, The Information, TechCrunch."
        ),
        "lever_hint": "CAPITAL",
        "query_tag": "capital_investment",
    },
    {
        "query": (
            "Most important AI regulation, policy, geopolitics, and governance news. "
            "Include new AI legislation, semiconductor export controls, "
            "EU AI Act implementation updates, US AI executive orders, "
            "China AI policy developments, AI safety announcements, "
            "and antitrust actions against AI companies. "
            "Prefer sources like Reuters, NYT, BBC, Financial Times, South China Morning Post, Politico."
        ),
        "lever_hint": "GOV",
        "query_tag": "governance_geopolitics",
    },
    {
        "query": (
            "Most significant AI model releases and capability breakthroughs. "
            "Include new model launches from OpenAI, Anthropic, Google DeepMind, "
            "Meta, Mistral, and other labs. Include benchmark results, "
            "new capabilities, and major open-source model releases. "
            "Prefer sources like The Verge, Ars Technica, MIT Technology Review, VentureBeat, company blogs."
        ),
        "lever_hint": "COMPUTE",
        "query_tag": "model_releases",
    },
]

# ─── System Prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a research analyst for an AI intelligence service called espresso·ai.

TASK: Analyze the search results and extract individual news signals.

RULES:
1. Return ONLY a JSON array. No text outside the array.
2. Extract 5-8 of the most important INDIVIDUAL news stories (not roundups or weekly briefings).
3. Each story must be a SPECIFIC event, announcement, or data point — not a summary of multiple events.
4. Use the EXACT original headline from the source article. Never generate or paraphrase a headline.
5. For source_url, use the URL from the search results/citations. If unavailable, leave as empty string.

REQUIRED FIELDS per object:
- "title": exact original headline from the source (string)
- "source_name": publication name, e.g. "Reuters", "Wall Street Journal", "Bloomberg" (string)
- "source_url": direct URL to the article from search results (string, empty string if unavailable)
- "publication_date": YYYY-MM-DD, from the source article (string)
- "summary": 1-2 sentence factual summary of the specific news event (string)
- "content_summary": 3-5 sentences on the article content and its strategic implications (string)
- "key_facts": 3-5 specific verifiable factual claims from the source (array of strings)

CRITICAL RULES:
- Do NOT include aggregator content ("Weekly Briefing", "AI Update", "Recap", "Roundup", "Top Stories").
- Do NOT fabricate URLs. Use only URLs from the search results. If unsure, use empty string.
- Prefer articles from major publications: Reuters, Bloomberg, WSJ, FT, NYT, BBC, MIT Tech Review, The Verge, Ars Technica, TechCrunch, Wired, SCMP, Nikkei.
- Each object must describe ONE specific news event, not a collection of events.
- If a search result is a roundup, extract individual stories from within it.
- Ensure valid JSON — no trailing commas, no markdown fences."""


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

def query_perplexity(query_text: str, date_after: str, date_before: str,
                     use_denylist: bool = True) -> dict:
    """Call Perplexity sonar-pro with date filters and optional domain denylist."""
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

    if use_denylist and DOMAIN_DENYLIST:
        payload["search_domain_filter"] = DOMAIN_DENYLIST[:20]

    resp = requests.post(PERPLEXITY_URL, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    return resp.json()


# ─── Response Parsing ────────────────────────────────────────────────────────

def parse_signals_from_response(raw_text: str) -> list[dict]:
    """Extract JSON array from Perplexity response text."""
    text = raw_text.strip()
    # Strip markdown fences if present
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


# ─── Citation Attachment ─────────────────────────────────────────────────────

def cross_validate_urls(signals: list[dict], citations: list[str]) -> list[dict]:
    """Cross-validate model-returned URLs against Perplexity's citations array.

    Strategy:
    1. If model returned a non-empty source_url, keep it but check if it matches a citation.
    2. If model returned empty source_url but provided citation_index, use citation.
    3. Flag unverified URLs (not found in citations).
    """
    citation_set = {c.rstrip("/").lower() for c in citations}

    for signal in signals:
        # Remove citation_index if present (not part of schema)
        signal.pop("citation_index", None)

        url = signal.get("source_url", "").strip()

        if url:
            # Check if the model's URL matches a known citation
            if url.rstrip("/").lower() not in citation_set:
                signal.setdefault("_quality_flags", []).append("url_not_in_citations")
        else:
            signal["source_url"] = ""
            signal.setdefault("_quality_flags", []).append("missing_url")

    return signals


# ─── Signal Classification ───────────────────────────────────────────────────
# Keyword-based classification adapted from collect_arxiv_signals.py classify_lever().
# Keyword maps derived from RESEARCH_FRAMEWORK.md sub-variable definitions.

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
    """Assign direction and sub_variable based on content keywords."""
    text = " ".join([
        signal.get("title", ""),
        signal.get("summary", ""),
        signal.get("raw_content", "") or "",
        " ".join(signal.get("key_facts", [])),
    ]).lower()

    # Find best sub_variable match
    best_sub = None
    best_score = 0
    lever_map = SUB_VAR_KEYWORDS.get(lever_hint, {})
    for sub_var, keywords in lever_map.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_sub = sub_var

    # Assign direction
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

    signal["lever_primary"] = lever_hint
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
    """Add data_quality_flags based on URL, title, and date checks."""
    flags = signal.pop("_quality_flags", [])

    url = signal.get("source_url", "")
    if not url:
        flags.append("missing_url")
    else:
        domain = urlparse(url).netloc.lower().lstrip("www.")
        if not any(domain.endswith(kd) for kd in ALL_KNOWN_DOMAINS):
            flags.append("unknown_domain")

    title = signal.get("title", "")
    if any(p in title.lower() for p in AGGREGATOR_PATTERNS):
        flags.append("aggregator_title")
        signal["in_scope"] = False

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
    """Remove signals with duplicate URLs or near-identical titles. Returns (unique, removed_count)."""
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

def make_signal_id(source_name: str, title: str, pub_date: str) -> str:
    """Generate a deterministic signal_id per schema."""
    now = datetime.now(timezone.utc)
    date_part = pub_date.replace("-", "") if pub_date else now.strftime("%Y%m%d")
    time_part = now.strftime("%H%M%S")
    hash_input = f"{title}{source_name}{pub_date}"
    short_hash = hashlib.md5(hash_input.encode()).hexdigest()[:5]
    return f"{date_part}-news_site-{time_part}-{short_hash}"


def build_signal_record(raw: dict, lever_hint: str, query_tag: str,
                        pipeline_run_id: str, collection_batch_id: str,
                        cadence: str) -> dict:
    """Convert a parsed Perplexity result into a full signal record per schema."""
    now = datetime.now(timezone.utc)
    pub_date = raw.get("publication_date", now.strftime("%Y-%m-%d"))
    title = raw.get("title", "Untitled")
    source = raw.get("source_name", "unknown")

    record = {
        "signal_id": make_signal_id(source, title, pub_date),
        "source_name": "news_site",
        "source_url": raw.get("source_url", ""),
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
        "tags": [f"source_pub:{source}", f"query_tag:{query_tag}"],
        "schema_version": SCHEMA_VERSION,
    }

    # Carry over any quality flags from citation attachment
    if "_quality_flags" in raw:
        record["_quality_flags"] = raw["_quality_flags"]

    return record


# ─── Main Pipeline ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="espresso·ai Weekly Signal Collector")
    parser.add_argument("--cadence", default="weekly",
                        choices=["daily", "weekly", "monthly", "quarterly", "annual"])
    parser.add_argument("--days-back", type=int, default=None,
                        help="Override: look back N days (default: auto from cadence)")
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

    # File naming: date range + source
    date_start_str = date_start.strftime("%Y-%m-%d")
    date_end_str = date_end.strftime("%Y-%m-%d")
    file_stem = f"{date_start_str}_{date_end_str}_perplexity_{cadence}"
    pipeline_run_id = f"{file_stem}_{uuid.uuid4().hex[:8]}"
    raw_dir = Path(__file__).resolve().parent.parent.parent / "research_db" / "raw"
    output_file = raw_dir / f"{file_stem}_signals.jsonl"

    print(f"espresso·ai Signal Collector")
    print(f"Pipeline run:  {pipeline_run_id}")
    print(f"Cadence:       {cadence}")
    print(f"Date window:   {date_after} → {date_before}")
    print(f"Output:        {output_file}")
    print(f"Queries:       {len(SEARCH_QUERIES)}")
    print("-" * 60)

    all_signals = []

    for i, sq in enumerate(SEARCH_QUERIES, 1):
        lever = sq["lever_hint"]
        query_tag = sq["query_tag"]

        print(f"\n[{i}/{len(SEARCH_QUERIES)}] {lever} ({query_tag})")
        print(f"  Query: {sq['query'][:80]}...")

        try:
            response = query_perplexity(sq["query"], date_after, date_before)
            raw_text = response["choices"][0]["message"]["content"]
            citations = response.get("citations", [])

            raw_signals = parse_signals_from_response(raw_text)
            print(f"  Parsed: {len(raw_signals)} signals | Citations: {len(citations)}")

            # Cross-validate URLs against Perplexity citations
            raw_signals = cross_validate_urls(raw_signals, citations)

            # Build full records, classify, and validate
            for rs in raw_signals:
                record = build_signal_record(rs, lever, query_tag,
                                             pipeline_run_id, collection_batch_id, cadence)
                record = classify_signal(record, lever)
                record = validate_and_flag(record, date_start, date_end)
                all_signals.append(record)

        except requests.exceptions.RequestException as e:
            print(f"  ERROR: API request failed: {e}")

        except (KeyError, IndexError) as e:
            print(f"  ERROR: Unexpected response format: {e}")

        if i < len(SEARCH_QUERIES):
            time.sleep(2)

    # Deduplicate
    pre_dedup = len(all_signals)
    all_signals, dupes_removed = deduplicate_signals(all_signals)

    # Quality metrics
    def count_flag(flag_name):
        return sum(1 for s in all_signals if flag_name in s.get("data_quality_flags", []))

    def count_direction(d):
        return sum(1 for s in all_signals if s.get("direction") == d)

    tier1_domains = set(DOMAIN_TIERS["tier1_business"])
    tier1_count = sum(
        1 for s in all_signals
        if any(urlparse(s.get("source_url", "")).netloc.lower().lstrip("www.").endswith(d)
               for d in tier1_domains)
    )

    print(f"\n{'=' * 60}")
    print(f"Total parsed:       {pre_dedup}")
    print(f"Duplicates removed: {dupes_removed}")
    print(f"Unique signals:     {len(all_signals)}")
    print(f"Tier-1 sources:     {tier1_count}")
    print(f"Unknown domains:    {count_flag('unknown_domain')}")
    print(f"Aggregator titles:  {count_flag('aggregator_title')}")
    print(f"Out-of-date:        {count_flag('out_of_date_range')}")
    print(f"Missing URLs:       {count_flag('missing_url')}")
    print(f"Direction: + {count_direction('+')} | - {count_direction('-')} | ~ {count_direction('~')} | ? {count_direction('?')}")

    # Write JSONL
    if all_signals:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "a", encoding="utf-8") as f:
            for record in all_signals:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"\nAppended {len(all_signals)} records to {output_file}")
    else:
        print("\nNo signals collected — check API key and network connectivity.")

    # Write pipeline log with quality metrics
    run_log = {
        "pipeline_run_id": pipeline_run_id,
        "collection_batch_id": collection_batch_id,
        "cadence": cadence,
        "date_window": {"after": date_after, "before": date_before},
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "queries_executed": len(SEARCH_QUERIES),
        "signals_collected": pre_dedup,
        "duplicates_removed": dupes_removed,
        "signals_written": len(all_signals),
        "output_file": str(output_file),
        "quality_metrics": {
            "tier1_source_count": tier1_count,
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
        },
    }
    log_path = output_file.parent / f"{file_stem}_pipeline_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(run_log, f, indent=2)
    print(f"Run log: {log_path}")

    # Print signal sample
    print(f"\n{'=' * 60}")
    print("SAMPLE SIGNALS:")
    for rec in all_signals[:10]:
        d = rec["direction"]
        lev = rec["lever_primary"]
        sub = rec["sub_variable"]
        title = rec["title"][:70]
        url_domain = urlparse(rec.get("source_url", "")).netloc or "no-url"
        flags = rec.get("data_quality_flags", [])
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  [{lev:8s} {d}] {sub:30s} | {url_domain:25s} | {title}{flag_str}")

    if len(all_signals) > 10:
        print(f"  ... and {len(all_signals) - 10} more")


if __name__ == "__main__":
    main()
