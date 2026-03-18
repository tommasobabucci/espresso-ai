# espresso.ai — AI Thought Leadership Pipeline

## Project Overview

**espresso.ai** is a multi-agent AI pipeline that filters the signal from the noise in the fast-moving AI market. It collects AI news from across the internet, separates signal from noise, synthesizes insights around market trajectory, and produces structured LinkedIn outputs to support Tommaso Babucci's AI thought leadership.

**Owner:** Tommaso Babucci — AI Strategy Consultant, Ernst & Young (EY), Global & Americas

> In the AI market, the speed of change forces leaders to think short-term, and all the voices in the market pull in different directions — making it hard to gather true signal from AI news. espresso.ai is the solution.

---

## Key Concept: REPORT_CADENCE

Before running any pipeline, the user **must specify** the report cadence:

```
REPORT_CADENCE = [daily | weekly | monthly | quarterly | annual]
```

All agents and skills adapt output tone, depth, synthesis level, and format based on cadence.

---

## Brand & Voice Guidelines

- Tommaso writes from the perspective of an **AI Strategy Consultant at EY** shaping the future of enterprise AI
- Tone: **authoritative, forward-thinking, accessible** — not hype-driven
- Perspective: **practitioner + strategist** — not researcher or journalist
- Avoid: jargon overload, breathless hype, purely tactical takes without strategic framing
- Always connect AI developments to **business impact**, **organizational transformation**, and **leadership implications**
- Reference Tommaso's work at EY (Global + Americas) when contextually relevant
- LinkedIn posts should feel like **curated intelligence**, not news aggregation

---

## Folder Structure

```
espresso_AI/
├── CLAUDE.md                    ← Master instructions (you are here)
├── .claude/
│   ├── agents/                  ← Subagent definitions (.md files)
│   ├── skills/                  ← Reusable skills (SKILL.md per directory)
│   ├── commands/                ← Slash commands
│   └── rules/                   ← Path-scoped rules
├── research_db/
│   ├── raw/                     ← Unprocessed scraped/fetched news data
│   ├── processed/               ← Cleaned, tagged, and scored articles
│   └── archive/                 ← Historical data for longitudinal analysis
├── brand_assets/
│   ├── about_me/                ← Tommaso's CV, bio, expertise, voice guide
│   ├── linkedin_templates/      ← LinkedIn post templates by cadence & format
│   └── design/                  ← Brand colors, fonts, visual identity
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

## Standards

- **Language**: Python for pipeline scripts; Markdown for docs and outputs
- **Data format**: JSON for structured storage in `research_db/`; Markdown for reports
- **File naming**: `YYYY-MM-DD_[cadence]_[type].md` for all PR outputs
- **Secrets**: All API keys live in `.env/` — never hardcode in any script or agent
- **Evolution**: Update this CLAUDE.md as new agents, skills, and components are built
