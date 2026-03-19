# espresso·ai — AI News Agent

## Project Overview

**espresso·ai** is an AI news agent that delivers concentrated, high-signal intelligence on artificial intelligence news and long-term trends. Under the hood, it is a multi-agent pipeline that collects AI news, separates signal from noise, synthesizes insights, and produces structured LinkedIn outputs.

**Owner:** Tommaso Babucci — AI Strategy & Development Lead, Americas Consulting, Ernst & Young

**Audience:** Consultants and C-suite executives at Fortune 500 companies — senior professionals who want insight, not awareness.

> Dense signal. Zero noise. espresso·ai filters the AI market so leaders don't have to.

**Important:** espresso·ai is an independent publication. It is **not affiliated with EY or any consulting firm**. Never reference EY in espresso·ai content.

---

## Key Concept: REPORT_CADENCE

Before running any pipeline, the user **must specify** the report cadence:

```
REPORT_CADENCE = [daily | weekly | monthly | quarterly | annual]
```

All agents and skills adapt output tone, depth, synthesis level, and format based on cadence.

---

## Brand & Voice Guidelines

> **Full brand reference:** `brand_assets/design/BRAND.md` — authoritative guide for colors, typography, logo, voice, and content rules. Always consult it when generating espresso·ai content.
>
> **Owner background:** `brand_assets/about_me/tommaso-babucci-resume.pdf`

**Tone:** Sharp, editorial, authoritative, precise, calm, forward-looking

**Perspective:** Practitioner + strategist — not researcher or journalist

**Write like this:**
- Lead with the insight, not the context
- Declarative sentences; state what is true
- Long-term perspective over daily churn
- One strong sentence beats three weak ones

**Never like this:**
- Hype language ("game-changing," "revolutionary," "unprecedented")
- Hedging ("might," "could potentially," "seems to suggest")
- Filler ("In today's rapidly evolving AI landscape...")
- AI writing giveaways: em dashes as crutches, lists of three, transitional openers ("Additionally," "Furthermore"), meta-commentary ("It's worth noting..."), AI vocabulary (delve, tapestry, landscape, paradigm shift)

**Content scope:** AI model developments, enterprise AI adoption, AI regulation/policy, long-term structural trends, strategic implications for business. Does NOT cover: general tech news, startup gossip, day-to-day market moves, consulting industry news.

---

## Analytical Framework: Scale Levers

> **Full definition:** `research_db/RESEARCH_FRAMEWORK.md`

Every AI signal is classified against six **Scale Levers** — structural variables that determine whether AI reaches transformational, civilizational scale or plateaus before achieving it.

| Code | Lever | What it captures |
|---|---|---|
| `COMPUTE` | Compute & Infrastructure | Chips, fabs, data centers, supply chain |
| `ENERGY` | Energy & Environment | Power demand, grid capacity, renewables, cooling |
| `SOCIETY` | Society & Human Capital | Adoption depth, talent pool, workforce shifts, trust |
| `INDUSTRY` | Industry & Business Transformation | Enterprise ROI, production deployments, business model change |
| `CAPITAL` | Capital & Investment | VC, hyperscaler capex, ROI signals, valuation discipline |
| `GOV` | Governance & Geopolitics | Regulation, export controls, safety, geopolitical fragmentation |

Each signal receives a **direction** (`+` positive / `-` negative / `~` neutral / `?` ambiguous) and is tagged with the specific **sub-variable** it impacts. All agents that collect, classify, or synthesize signals must apply this framework.

---

## Signal Record Schema

> **Full schema:** `research_db/DB_SCHEMA.md`
> **Blank template:** `research_db/_signal_template.json`

Storage is a **JSONL + SQLite hybrid**:
- **Hot path (writes):** Agents append signal records as single JSON lines to JSONL files in `research_db/raw/`. One file per cadence window. Agents never rewrite existing files — append only.
- **Cold path (queries):** A consolidation job imports JSONL into `research_db/archive/signals.db` for indexed synthesis queries.

JSONL file naming: `YYYY-MM-DD_[cadence]_signals.jsonl` (daily), `YYYY-W[WW]_weekly_signals.jsonl`, `YYYY-MM_monthly_signals.jsonl`, `YYYY-Q[N]_quarterly_signals.jsonl`.

---

## Available Skills

| Skill | Command | Description |
|---|---|---|
| ArXiv Research | `/arxiv-research [cadence]` | Collect AI papers from ArXiv, classify by Scale Lever, write JSONL to `research_db/raw/` |
| Perplexity Research | `/perplexity-research [cadence]` | Collect AI news via Perplexity sonar-pro, classify by Scale Lever, write JSONL to `research_db/raw/` |

Both skills require a cadence argument and invoke Python scripts in `.claude/scripts/`.

---

## Folder Structure

```
espresso_AI/
├── CLAUDE.md                    ← Master instructions (you are here)
├── .claude/
│   ├── agents/                  ← Subagent definitions (.md files)
│   ├── skills/                  ← Reusable skills (SKILL.md per directory)
│   ├── scripts/                 ← Python pipeline scripts invoked by skills
│   ├── commands/                ← Slash commands
│   └── rules/                   ← Path-scoped rules
├── research_db/
│   ├── RESEARCH_FRAMEWORK.md    ← Scale Levers framework (classification lens)
│   ├── DB_SCHEMA.md             ← Signal record schema & storage architecture
│   ├── _signal_template.json    ← Blank signal record template
│   ├── raw/                     ← JSONL signal files (agent append-only output)
│   ├── processed/               ← Cleaned, tagged, and scored articles
│   └── archive/                 ← SQLite DB for synthesis queries
├── brand_assets/
│   ├── about_me/                ← Tommaso's CV, bio, expertise, voice guide
│   ├── linkedin_templates/      ← LinkedIn post templates by cadence & format
│   └── design/                  ← Brand colors, fonts, visual identity (BRAND.md)
├── documentation/
│   └── claude_docs/             ← Claude reference guides (agents, skills, commands)
├── PR/
│   ├── daily/                   ← Daily LinkedIn post outputs
│   ├── weekly/                  ← Weekly roundup outputs
│   ├── monthly/                 ← Monthly synthesis outputs
│   ├── quarterly/               ← Quarterly trend reports
│   └── annual/                  ← Annual state-of-AI outputs
└── .env/                        ← API keys and secrets (NEVER commit)
```

---

## API Keys

All keys are stored in a single file: `.env/.env`. Never quote values — store them bare.

```
PERPLEXITY_API_KEY=pplx-...
```

To load keys in Python:
```python
from dotenv import load_dotenv
import os

load_dotenv(".env/.env")
api_key = os.getenv("PERPLEXITY_API_KEY")
```

Add new keys to the same file as `KEY_NAME=value` (one per line, no quotes).

---

## Standards

- **Language**: Python for pipeline scripts; Markdown for docs and outputs
- **Data format**: JSONL for signal records in `research_db/raw/`; SQLite for archive queries in `research_db/archive/`; Markdown for reports in `PR/`
- **File naming — PR outputs**: `YYYY-MM-DD_[cadence]_[type].md`
- **File naming — signal data**: `YYYY-MM-DD_[cadence]_signals.jsonl` (see DB_SCHEMA.md for full convention)
- **Secrets**: All API keys live in `.env/.env` — never hardcode in any script or agent
- **Dependencies**: `requests`, `python-dotenv` (for pipeline scripts)
- **Evolution**: Update this CLAUDE.md as new agents, skills, and components are built
