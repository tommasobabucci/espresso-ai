# Reddit Signal Collection — Research & Implementation Plan

**Version:** 1.0
**Date:** 2026-03-18
**Status:** Planning
**Author:** espresso·ai

---

## 1. Why Reddit

Reddit fills a gap the current pipeline misses. Perplexity and ArXiv capture published news and academic research. Reddit captures the *practitioner layer* — what engineers are actually building, what enterprise teams are struggling with, what researchers think matters before it becomes a headline. The signal-to-noise ratio varies wildly by subreddit, which is why targeting matters more than breadth.

Reddit's value for espresso·ai is threefold:

- **Leading indicators.** Technical breakthroughs surface on r/MachineLearning and r/LocalLLaMA days before they reach mainstream tech press. Model releases, benchmark results, and inference optimizations are discussed in real time.
- **Practitioner sentiment.** Enterprise deployment pain points, adoption blockers, and workforce impacts are discussed candidly in ways that press coverage sanitizes.
- **Contrarian signal.** Reddit's community structure naturally produces pushback against hype, which is valuable for the `?` (ambiguous) direction classification.

---

## 2. Subreddit Targeting — Tiered by Signal Quality

### Tier 1: High-Signal, Must-Track

These subreddits consistently produce content that maps directly to Scale Levers with high confidence.

| Subreddit | Members | Primary Levers | Signal Type | Why It Matters |
|---|---|---|---|---|
| **r/MachineLearning** | ~3M+ | `COMPUTE`, `INDUSTRY` | Research papers, model releases, benchmark discussions, author AMAs | The canonical ML research community. Paper authors frequently post directly. High technical rigor, low noise. |
| **r/LocalLLaMA** | ~650K+ | `COMPUTE`, `INDUSTRY` | Open-source model releases, inference optimization, quantization results, hardware benchmarks | Ground truth for open-source AI capability. What runs locally today ships in enterprise products in 6 months. |
| **r/artificial** | ~1.1M | `SOCIETY`, `GOV`, `INDUSTRY` | News aggregation, policy discussions, enterprise adoption debates | Broader AI news with decent discussion quality. Good for cross-lever signals. |

### Tier 2: Valuable with Filtering

These produce strong signal but require aggressive noise filtering (memes, beginner questions, hype).

| Subreddit | Members | Primary Levers | Signal Type | Filtering Strategy |
|---|---|---|---|---|
| **r/singularity** | ~3.8M | `SOCIETY`, `CAPITAL` | AGI timeline debates, capability speculation, adoption trend discussions | Very high volume, variable quality. Filter by score threshold (>100 upvotes) and flair. Useful for sentiment tracking and contrarian signals. |
| **r/OpenAI** | ~1M+ | `COMPUTE`, `INDUSTRY` | Product releases, capability updates, enterprise deployment discussions | Vendor-specific but high-traffic. Filter out support requests and basic usage questions. |
| **r/ArtificialIntelligence** | ~500K+ | `SOCIETY`, `GOV` | Policy debates, ethical discussions, adoption patterns | More accessible tone than r/MachineLearning. Good for society/governance signals. |

### Tier 3: Niche / Supplementary

Track selectively for specific lever coverage.

| Subreddit | Primary Levers | When to Track |
|---|---|---|
| **r/LanguageTechnology** | `COMPUTE` | NLP-specific breakthroughs, transformer architecture advances |
| **r/deeplearning** | `COMPUTE` | Training methodology, architecture innovations |
| **r/datascience** | `INDUSTRY`, `SOCIETY` | Enterprise deployment patterns, workforce skill signals |
| **r/StableDiffusion** | `COMPUTE`, `GOV` | Open-source image generation, IP/copyright policy signals |
| **r/Futurology** | `SOCIETY` | Public sentiment on AI disruption (high noise, use sparingly) |
| **r/technology** | `GOV`, `SOCIETY` | AI regulation discussions reaching mainstream audience |
| **r/cscareer** / **r/experienceddevs** | `SOCIETY` | AI workforce displacement signals, hiring trend changes |

### Explicitly Excluded

| Subreddit | Reason |
|---|---|
| r/ChatGPT | Dominated by usage tips and prompt engineering. No structural signal. |
| r/ChatGPTPro | Consumer product discussion, not strategic. |
| r/learnmachinelearning | Educational content. No signal for Scale Levers. |
| r/MLQuestions | Q&A forum. No news signal. |

---

## 3. User Tracking — High-Signal Contributors

Reddit is pseudonymous, so tracking is community-driven rather than personality-driven. That said, certain posting patterns reliably produce high-signal content.

### Priority User Categories

**Category 1: Paper Authors & Lab Researchers**
Posts tagged `[R]` (Research) on r/MachineLearning from verified authors. These often include "We are the authors, AMA" threads. Track posts with this pattern rather than specific usernames.

**Category 2: Open-Source Model Builders**
On r/LocalLLaMA, users who release quantized models, publish benchmark comparisons, or document inference optimization results. The community naturally surfaces these through upvotes. Track by post score + flair rather than username.

**Category 3: Enterprise Practitioners**
Across r/MachineLearning, r/datascience, and r/artificial — users sharing real deployment case studies, production challenges, and measurable outcomes. These are rare and high-value. Flag posts containing terms like "production," "deployed," "ROI," "enterprise," "at scale."

### Tracking Strategy

Rather than maintaining a static user list (which goes stale), the collector should use a **dynamic scoring approach**:

1. **Post-level filtering** — Score threshold + keyword matching + flair filtering
2. **Author karma weighting** — Higher comment/post karma in AI subreddits correlates with signal quality
3. **Engagement ratio** — Posts with high comment-to-upvote ratios often indicate substantive discussion
4. **Cross-post detection** — Signals that appear across multiple tracked subreddits carry higher weight

---

## 4. Signal Mapping — Reddit to Scale Levers

| Reddit Content Type | Primary Lever | Sub-variables | Example |
|---|---|---|---|
| Model release announcements | `COMPUTE` | `architectural_diversity`, `custom_silicon_adoption` | "Meta releases Llama 4 with 2x inference throughput" |
| Benchmark comparisons | `COMPUTE` | `cost_per_flop`, `energy_efficiency` | "Running Mixtral 8x22B at 40 tok/s on a single 4090" |
| Enterprise deployment posts | `INDUSTRY` | `production_deployment_rate`, `workflow_integration_depth` | "We replaced our entire document review pipeline with fine-tuned model" |
| Job market discussions | `SOCIETY` | `professional_displacement_signals`, `researcher_and_engineer_stock` | "Our company just laid off 30% of junior analysts, replaced with AI" |
| Policy/regulation threads | `GOV` | `regulatory_framework_clarity`, `export_controls_and_chip_access` | "EU AI Act enforcement timeline just leaked" |
| Investment discussions | `CAPITAL` | `venture_funding_discipline`, `hyperscaler_capex_and_utilization` | "Nvidia's latest earnings imply 80%+ GPU utilization across cloud" |
| Data center / hardware posts | `ENERGY` | `data_center_power_intensity`, `grid_capacity_utilization` | "Our data center in Virginia was told no more grid capacity for 18 months" |
| Open-source ecosystem posts | `COMPUTE`, `INDUSTRY` | `cost_per_flop`, `cross_sector_diffusion` | "Hospital running local Llama model for radiology triage" |

---

## 5. Technical Architecture

### API Access: PRAW (Python Reddit API Wrapper)

PRAW is the right choice for the espresso·ai pipeline. It handles OAuth, rate limiting, and pagination automatically. It aligns with the existing Python-based pipeline architecture.

**Rate limits:** 60 requests/minute (OAuth). PRAW manages this automatically.

**Authentication setup:**
1. Create a Reddit app at reddit.com/prefs/apps (type: "script")
2. Store credentials in `.env/.env`:
```
REDDIT_CLIENT_ID=<client_id>
REDDIT_CLIENT_SECRET=<client_secret>
REDDIT_USER_AGENT=espresso-ai-signal-collector/1.0
```

### Schema Integration

The DB_SCHEMA.md `source_name` enum needs a new value: `reddit`. All other schema fields apply directly.

**Signal ID format:** `YYYYMMDD-reddit-HHMMSS-[5char]`

**Tags:** Each Reddit signal gets additional tags:
- `subreddit:<name>` — source subreddit
- `reddit_score:<int>` — upvote score at collection time
- `reddit_flair:<flair>` — post flair if present
- `reddit_comments:<int>` — comment count at collection

### Script: `collect_reddit_signals.py`

Follow the pattern established by `collect_perplexity_signals.py`:

```
Input:  --cadence [daily|weekly|monthly|quarterly|annual]
        --days-back N (optional override)

Process:
  1. Authenticate via PRAW
  2. For each Tier 1+2 subreddit:
     a. Fetch top posts within date window (sorted by: hot, top)
     b. Apply score threshold filter
     c. Apply keyword/flair filter
     d. Extract post title, body, top comments
  3. For each qualifying post:
     a. Classify against Scale Levers (reuse SUB_VAR_KEYWORDS from perplexity script)
     b. Assign direction via keyword scoring
     c. Build full signal record per schema
     d. Validate and flag quality issues
  4. Deduplicate against existing signals in the same window
  5. Append to JSONL in research_db/raw/

Output: research_db/raw/YYYY-MM-DD_YYYY-MM-DD_reddit_[cadence]_signals.jsonl
        research_db/raw/..._pipeline_log.json
```

### Filtering Parameters by Cadence

| Cadence | Score Threshold | Subreddit Tiers | Max Posts/Sub | Comment Depth |
|---|---|---|---|---|
| Daily | ≥50 | Tier 1 only | 25 | Top 3 comments |
| Weekly | ≥100 | Tier 1 + 2 | 50 | Top 5 comments |
| Monthly | ≥200 | Tier 1 + 2 + selective Tier 3 | 100 | Top 10 comments |
| Quarterly | ≥500 | All tiers | 200 | Top 10 comments |

### Deduplication Strategy

Reddit signals will overlap with Perplexity signals when Reddit posts link to news articles. The collector must:
1. Extract URLs from Reddit post bodies
2. Compare against `source_url` values in existing JSONL files for the same date window
3. If a Reddit post links to an article already captured by Perplexity, mark as `is_duplicate: true` but preserve the Reddit discussion context in `synthesis_notes`

---

## 6. Quality Control

### Reddit-Specific Quality Flags

Add to `data_quality_flags`:
- `low_reddit_score` — post below tier threshold but included for lever coverage
- `meme_or_humor` — detected humor/meme flair or patterns
- `self_promotional` — user promoting their own product/service
- `speculation_heavy` — high ratio of hedging/speculative language
- `vendor_astroturf` — suspected corporate posting (new account, product-focused)

### Content Filters (Exclude Before Processing)

- Posts with flair: "Meme", "Humor", "Shitpost", "Discussion" (on r/singularity)
- Posts with score < 10 (absolute floor regardless of cadence)
- Posts from accounts < 30 days old
- Posts that are pure link shares with no discussion (< 5 comments)
- Posts in languages other than English

### Signal Confidence Adjustment

Reddit signals inherently carry lower source authority than Reuters or ArXiv. Apply a confidence penalty:
- Reddit post citing a primary source (news article, paper, official announcement) → confidence from keyword scoring, no penalty
- Reddit post with original analysis/experience → cap at `medium`
- Reddit discussion thread (no primary source) → cap at `low`

---

## 7. Dependencies & New Packages

```
praw>=7.7.0          # Reddit API wrapper
```

Add to existing `requirements.txt` or install alongside `requests` and `python-dotenv`.

---

## 8. Implementation Sequence

| Step | Task | Dependency |
|---|---|---|
| 1 | Create Reddit app credentials, add to `.env/.env` | Reddit account |
| 2 | Add `reddit` to `source_name` enum in DB_SCHEMA.md | None |
| 3 | Build `collect_reddit_signals.py` following perplexity script pattern | Step 1, 2 |
| 4 | Create `/reddit-research` skill (SKILL.md + command) | Step 3 |
| 5 | Test on daily cadence against Tier 1 subreddits | Step 3 |
| 6 | Add Tier 2 subreddits, tune score thresholds | Step 5 |
| 7 | Implement cross-source deduplication with Perplexity signals | Step 6 |
| 8 | Run parallel with Perplexity collector for one week, compare signal overlap | Step 7 |

---

## 9. Open Questions

1. **Reddit API pricing.** Free tier is sufficient for non-commercial research use at 60 req/min. If espresso·ai scales to commercial distribution, evaluate whether Reddit's API terms require paid access.

2. **Comment extraction depth.** Top-level comments on r/MachineLearning paper threads often contain the most valuable practitioner analysis. Worth investing in comment parsing for Tier 1 subreddits — but adds complexity and API calls.

3. **Historical backfill.** Pushshift (Reddit archive) can provide historical data for trend analysis. Consider a one-time backfill for signals dating back 6-12 months to establish baseline patterns.

4. **Sentiment scoring.** Reddit's upvote/downvote mechanism provides a natural sentiment signal. Consider incorporating net score trends over time as a proxy for practitioner consensus shifts.
