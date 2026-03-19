# espresso·ai — Signal Record Schema

**Version:** 1.0
**Owner:** espresso·ai
**Last updated:** 2026-03-18
**Status:** Active

---

## Purpose

This document defines the structure of every signal record that enters the espresso·ai research database. All agents that collect, classify, or synthesize news signals must read this document before writing or querying data.

A **signal record** is the atomic unit of the pipeline: one news event, announcement, or data point, tagged, classified, and annotated according to the Scale Levers framework (`research_db/SCALE_LEVERS.md`).

---

## Storage Architecture

espresso·ai uses a **JSONL + SQLite hybrid** — the right tool for each access pattern.

### Why Not a Single Format

| Format | Agent writes | Trend queries | Human-readable | Multi-agent safe |
|---|---|---|---|---|
| CSV | ✓ | ✗ Full scan | ✓ | Risky |
| JSON array | ✓ | ✗ Full scan | ✓ | ✗ Corruption risk |
| JSONL | ✓ O(1) append | ✗ Full scan | ✓ | ✓ Line-isolated |
| SQLite | Complex | ✓ Indexed | ✗ Binary | ✓ ACID |
| **JSONL + SQLite** | **✓ Simple** | **✓ Indexed** | **✓ Both** | **✓ Both** |

### Hot Path: JSONL (Agent Writes)

Every research agent appends signal records to a JSONL file (one JSON object per line) in `research_db/raw/`. Files are partitioned by date and cadence:

```
research_db/raw/
├── 2026-03-18_daily_signals.jsonl
├── 2026-W11_weekly_signals.jsonl
├── 2026-03_monthly_signals.jsonl
├── 2026-Q1_quarterly_signals.jsonl
└── _signal_template.json          ← copy this to create a new record
```

Naming convention: `YYYY-MM-DD_[cadence]_signals.jsonl` for daily; `YYYY-W[WW]` for weekly; `YYYY-MM` for monthly; `YYYY-Q[N]` for quarterly.

**Agents never rewrite existing files. They only append.**

### Cold Path: SQLite (Synthesis Queries)

A consolidation job runs after each pipeline cadence and imports all JSONL records into:

```
research_db/archive/signals.db
```

Synthesis agents query this file to filter by lever, direction, date range, signal strength, and cadence. The SQLite file is the single queryable source of truth across all historical runs.

### Python Libraries (No New Dependencies)

```python
import json       # JSONL read/write
import sqlite3    # archive queries
from pathlib import Path
import uuid, datetime
```

---

## Field Reference

Every signal record contains the following fields. Fields marked **Required** must be populated by the collecting agent before writing to disk. Fields marked **Synthesis** are populated later by the synthesis agent. Fields marked **Optional** improve quality but may be omitted if unavailable.

---

### Group 1: Provenance

*Who found this signal, when, and from where.*

| Field | Type | Status | Description |
|---|---|---|---|
| `signal_id` | string | Required | Unique record identifier. Format: `YYYYMMDD-[source_name]-HHMMSS-[5-char-hash]`. Auto-generate at ingestion. |
| `source_name` | enum | Required | The channel or platform the signal was collected from. See allowed values below. |
| `source_url` | string (URL) | Required | Direct link to the original content. Must be absolute and resolvable. Use canonical URL to prevent duplicates. |
| `fetch_timestamp` | string (ISO 8601) | Required | Exact datetime the agent fetched or processed this signal. Format: `YYYY-MM-DDTHH:MM:SSZ`. |
| `agent_id` | string | Required | Name of the collecting agent, matching its definition in `.claude/agents/`. Example: `earnings-call-watcher`. |
| `cadence` | enum | Required | Report cadence this signal belongs to: `daily`, `weekly`, `monthly`, `quarterly`, `annual`. |
| `pipeline_run_id` | string | Required | ID of the pipeline run. Format: `YYYY-MM-DD_[cadence]_[8-char-uuid]`. Links to `pipeline_log.json`. |
| `collection_batch_id` | string | Required | Batch ID from the collection phase. Format: `batch_YYYYMMDD_HHMM`. Used for tracing multi-stage processing. |

**Allowed `source_name` values:**
`linkedin` · `twitter` · `rss_feed` · `academic_paper` · `earnings_call` · `regulatory_filing` · `news_site` · `company_announcement` · `other`

---

### Group 2: Classification

*How this signal maps to the Scale Levers framework.*

| Field | Type | Status | Description |
|---|---|---|---|
| `lever_primary` | enum | Required | Primary Scale Lever. Must be one of: `COMPUTE`, `ENERGY`, `SOCIETY`, `INDUSTRY`, `CAPITAL`, `GOV`. See `SCALE_LEVERS.md` for full definitions. |
| `lever_secondary` | enum | Optional | Secondary lever if the signal materially impacts a second lever — not tangentially. Same allowed values as `lever_primary`. Omit if no strong secondary impact. |
| `direction` | enum | Required | Directional implication for AI scaling at long-term (multi-year) horizon. `+` = positive, `-` = negative, `~` = neutral, `?` = ambiguous. |
| `sub_variable` | string | Required | The specific sub-variable within the primary lever this signal affects. Must match a sub-variable label defined in `SCALE_LEVERS.md`. |
| `confidence` | enum | Required | Agent's confidence in the classification. `high` = clear signal with strong source; `medium` = reasonable but uncertain; `low` = plausible but weak evidence. |

---

### Group 3: Content

*The actual news — what was said, and what it means.*

| Field | Type | Status | Description |
|---|---|---|---|
| `title` | string (max 200 chars) | Required | Original headline or extracted title. Preserve source wording exactly — do not paraphrase or editorialize. |
| `summary` | string (max 500 chars) | Required | 1-2 sentences stating what this signal *means* for AI scaling — not what it says. Lead with the directional implication. Write in espresso·ai voice: declarative, no hedging, practitioner perspective. |
| `key_facts` | array of strings | Optional | 3-5 specific factual claims from the source. These are the verifiable statements, not interpretation. Synthesis agents use these to cross-check claims. |
| `raw_content` | string | Optional | Full text of source if accessible. Omit if source_url is sufficient or source is paywalled — do not fabricate. |

---

### Group 4: Temporal & Run Context

*When the event occurred and which pipeline run captured it.*

| Field | Type | Status | Description |
|---|---|---|---|
| `publication_date` | string (YYYY-MM-DD) | Required | Date the original content was published or disclosed — not the fetch date. Used for chronological ordering and trend analysis. |
| `reporting_period` | string | Optional | For earnings calls and periodic filings, the period covered. Format: `Q1 2026`, `FY 2025`, `H1 2026`. Enables correlation with financial cycles. |

---

### Group 5: Quality & Synthesis

*Fields populated during the synthesis phase to support filtering, weighting, and output generation.*

| Field | Type | Status | Description |
|---|---|---|---|
| `signal_strength` | integer (1–10) | Synthesis | Synthesis-agent-assigned importance score. 1–3: weak or tangential; 4–6: clear but isolated; 7–9: strong directional signal with cross-lever implications; 10: transformational, multi-lever. Populated by synthesis agent, not collecting agent. |
| `cross_lever_interactions` | array of objects | Synthesis | If signal strongly impacts a second lever, describe the interaction. Each object: `{"lever": "ENERGY", "interaction_type": "coupled_enablement"}`. Interaction types: `coupled_enablement`, `coupled_constraint`, `sequential_gating`, `competing_for_capital`. |
| `novelty_flag` | boolean | Synthesis | `true` if this signal represents a structural break from the prior baseline — not an incremental continuation. Used to weight synthesis toward directional shifts. |
| `countervailing_signals` | array of strings | Synthesis | `signal_id` values of signals in the database that contradict or weaken this one. Synthesis agents use these to flag ambiguity. |
| `synthesis_notes` | string | Synthesis | Free-form internal annotation. Flag nuance, caveats, and cross-checking logic. Not published in final output. |
| `is_duplicate` | boolean | Synthesis | `true` if this record is redundant with another in the same pipeline run. Prevents double-counting. |
| `duplicate_of` | string | Synthesis | If `is_duplicate` is `true`, the `signal_id` of the primary record. Null otherwise. |

---

### Group 6: Metadata & Quality Control

*Operational fields for filtering, versioning, and forward compatibility.*

| Field | Type | Status | Description |
|---|---|---|---|
| `in_scope` | boolean | Required | `true` if signal falls within espresso·ai content scope per `CLAUDE.md`. `false` for general tech news, startup gossip, day-to-day market moves. Out-of-scope records are excluded before synthesis. |
| `data_quality_flags` | array of strings | Optional | Operational issues with this record. Values: `missing_key_facts`, `unverified_claim`, `paywalled_source`, `translation_needed`, `low_source_credibility`, `ambiguous_date`. Records with flags are included but deprioritized in synthesis. |
| `tags` | array of strings | Optional | Freeform labels for filtering and ad-hoc queries. Use `namespace:value` format where possible. Examples: `vendor_name:nvidia`, `region:eu`, `deployment_domain:healthcare`, `market_structure:consolidation`. |
| `schema_version` | string | Required | Schema version this record conforms to. Current: `1.0`. Enables backward-compatible parsing as schema evolves. |

---

## How Agents Use This Schema

### Collecting Agent (writes)

1. Find a signal worth recording
2. Copy `research_db/raw/_signal_template.json`
3. Populate all **Required** fields
4. Populate any **Optional** fields available from the source
5. Leave all **Synthesis** fields at their null defaults
6. Append the completed JSON object as a single line to the appropriate JSONL file in `research_db/raw/`
7. Never modify existing lines; only append

### Synthesis Agent (reads + enriches)

1. Read all records from the relevant JSONL file(s) in `research_db/raw/`
2. Filter to `in_scope: true` and `is_duplicate: false`
3. For each record, populate `signal_strength`, `cross_lever_interactions`, `novelty_flag`, `countervailing_signals`, and `synthesis_notes`
4. Write enriched records to `research_db/archive/signals.db` via the consolidation job
5. Use SQLite queries to identify trend patterns, directional shifts, and high-signal cross-lever events
6. Produce final LinkedIn output from records with `signal_strength >= 7`

### LinkedIn Output Agent (reads)

Query: `SELECT * FROM signals WHERE in_scope=1 AND is_duplicate=0 AND signal_strength >= 7 ORDER BY publication_date DESC`

---

## Versioning

Update this document when fields are added, removed, or redefined. Increment `MAJOR` for breaking changes; `MINOR` for additive changes. All records include `schema_version` so older records remain parseable.

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-03-18 | Initial schema definition |
