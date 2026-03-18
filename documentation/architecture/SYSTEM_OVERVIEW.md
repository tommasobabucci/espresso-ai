# espresso.ai — System Architecture Overview

> Last updated: 2026-03-18

---

## System Purpose

espresso.ai is a multi-agent intelligence pipeline designed to:
1. **Collect** AI news from across the internet (multi-source)
2. **Filter** signal from noise using structured scoring
3. **Synthesize** insights around market trajectory and strategic implications
4. **Produce** LinkedIn-ready thought leadership content for Tommaso Babucci

---

## Pipeline Flow

```
[Sources] → news-collector → research_db/raw/
                                    ↓
                          signal-filter
                                    ↓
                          research_db/processed/
                                    ↓
                          insight-synthesizer
                                    ↓
                          [Briefing Document]
                                    ↓
                          linkedin-writer
                                    ↓
                          PR/{cadence}/
                                    ↓
                          [Brand Check]
                                    ↓
                          [Published to LinkedIn]
```

---

## Agent Responsibilities

| Agent | Input | Output | Model |
|---|---|---|---|
| `news-collector` | Source configs in `.env/` | `research_db/raw/*.json` | Sonnet |
| `signal-filter` | `research_db/raw/` | `research_db/processed/*.json` | Sonnet |
| `insight-synthesizer` | `research_db/processed/` + REPORT_CADENCE | Briefing document | Opus |
| `linkedin-writer` | Briefing + brand_assets/ | `PR/{cadence}/*.md` | Opus |
| `pipeline-orchestrator` | User command + REPORT_CADENCE | Coordinates all above | Sonnet |

---

## Data Schema

### Raw Article (research_db/raw/)
```json
{
  "id": "uuid",
  "source": "source_name",
  "title": "Article title",
  "url": "https://...",
  "published_at": "2026-03-18T10:00:00Z",
  "collected_at": "2026-03-18T12:00:00Z",
  "summary": "Brief summary...",
  "full_text": "Full article text...",
  "tags": ["llm", "enterprise", "agentic"]
}
```

### Processed Article (research_db/processed/)
```json
{
  "id": "uuid",
  "source_id": "raw_uuid",
  "title": "Article title",
  "url": "https://...",
  "scores": {
    "strategic_importance": 4,
    "novelty": 3,
    "relevance": 5,
    "total": 12
  },
  "signal_category": "model_release | policy | enterprise_adoption | research | market_move",
  "key_insight": "One-sentence synthesis of the strategic implication",
  "processed_at": "2026-03-18T12:05:00Z"
}
```

---

## Output Cadence Specifications

| Cadence | Depth | Format | Recommended Length |
|---|---|---|---|
| Daily | Snapshot — 1-3 top signals | Short post + 3 bullet points | ~200 words |
| Weekly | Digest — 5-7 stories, light synthesis | Carousel-style or multi-paragraph | ~400 words |
| Monthly | Synthesis — theme identification + trajectory | Long-form narrative post | ~600 words |
| Quarterly | Trend report — macro patterns + predictions | Document + LinkedIn article | ~1000 words |
| Annual | State of AI — comprehensive retrospective + outlook | Full article + visual summary | ~1500 words |

---

## Key Design Decisions

1. **Modular agents** — Each agent is independently runnable for testing and debugging
2. **JSON-first storage** — All research data stored as structured JSON for queryability
3. **Cadence as a variable** — Pipeline adapts depth and format based on user-specified cadence
4. **Brand-first output** — LinkedIn writer always reads brand assets before writing
5. **Archive-enabled** — Historical data preserved for longitudinal trend analysis
6. **Secret isolation** — All API credentials in `.env/` folder, never in code or markdown

---

## Planned Integrations (Future)

- LinkedIn API for direct posting (requires OAuth)
- Perplexity API for web research enrichment
- NewsAPI / GDELT for broad news coverage
- RSS aggregator for newsletter sources
- Notion/Slack for internal distribution
