---
name: fact-check
description: Fact-check all signal claims in an espresso·ai report via 6 parallel subagents (one per Scale Lever), then automatically remediate issues across all pipeline artifacts. Run this after generating a carousel and before publishing.
argument-hint: <report-path> [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
allowed-tools: Bash, Read, Write, Agent, WebSearch, WebFetch
---

# Fact-Check — Signal Verification & Remediation

Verify every signal claim in an espresso·ai report against its source, cross-reference with independent reporting, and remediate inaccuracies across all pipeline artifacts.

## Arguments

**report-path** (required): Path to the report file in `PR/{cadence}/` (HTML or PDF). The cadence is inferred from the report's parent directory (e.g., `PR/weekly/` → weekly). If PDF, the skill uses the carousel data JSON as the structured source and only remediates the HTML version.

**--start-date** (optional): Start of the reporting window. If omitted, auto-detected from artifact filenames.

**--end-date** (optional): End of the reporting window. If omitted, auto-detected from artifact filenames.

## Step 1: Validate Arguments & Locate Artifacts

Parse `$ARGUMENTS` for the report path and optional date range.

1. Verify the report file exists at the given path (e.g., `PR/{cadence}/{report-path}`)
2. Infer `{cadence}` from the report's parent directory name (e.g., `PR/weekly/` → `weekly`, `PR/monthly/` → `monthly`)
3. If `--start-date` and `--end-date` are not provided, scan `research_db/processed/` for the most recent `*_{cadence}_carousel_data.json` and extract dates from its filename
4. Locate all pipeline artifacts for the date window:
   - Carousel data: `research_db/processed/{start}_{end}_{cadence}_carousel_data.json`
   - Deduped JSONL: `research_db/processed/{start}_{end}_{cadence}_deduped.jsonl`
   - Synthesis log: `research_db/processed/{start}_{end}_{cadence}_synthesis_log.json`
   - Raw JSONL: all `research_db/raw/*` files with dates overlapping the window
   - HTML report: the corresponding `.html` file in `PR/{cadence}/` (if input was PDF, find the HTML sibling)
4. If the carousel data JSON is missing, **stop** — synthesis must run before fact-checking

Report to the user: report file found, date window, number of artifact files located.

## Step 2: Extract Claims Per Lever

Read the carousel data JSON. For each of the 6 levers, extract `lever_summaries.{LEVER}.top_signals[]`.

Read the HTML report file. For each `<div class="signal-item">`, extract:
- The editorial headline from `<div class="signal-headline">`
- The editorial summary from `<div class="signal-summary">`
- The source from `<span class="signal-source">`

Match editorial text to carousel data signals by correlating headlines with signal titles (word overlap matching). Build a unified mapping:

```
{
  "COMPUTE": [
    {
      "signal_id": "...",
      "title": "raw title from carousel data",
      "editorial_headline": "rewritten headline from HTML",
      "editorial_summary": "rewritten summary from HTML",
      "source_url": "...",
      "source_name": "...",
      "key_facts": [...],
      "publication_date": "...",
      "sub_variable": "..."
    }
  ],
  "ENERGY": [...],
  ...
}
```

Report: total signals to fact-check, count per lever.

## Step 3: Launch 6 Fact-Check Subagents (Parallel)

Launch all 6 subagents **in a single message** using the Agent tool. Each subagent receives its lever's signals and the verification protocol below.

For each lever, use this prompt template (fill in `{LEVER_CODE}`, `{LEVER_NAME}`, `{N}`, `{START_DATE}`, `{END_DATE}`, `{SIGNALS_JSON}`):

```
You are a fact-check agent for espresso·ai, an AI news intelligence service. Your task is to verify {N} signal claims classified under {LEVER_NAME} ({LEVER_CODE}) for the reporting period {START_DATE} to {END_DATE}.

## Signals to Verify

{SIGNALS_JSON}

Each signal has: signal_id, title (raw from data), editorial_headline (as published), editorial_summary (as published), source_url, source_name, key_facts, publication_date.

## Verification Protocol

For EACH signal, perform these checks:

1. **Source Verification**: Fetch the source_url using WebFetch. Confirm:
   - The URL resolves and is accessible
   - The content supports the claims in both the raw title and editorial headline
   - If paywalled or dead, note this and rely on cross-referencing

2. **Cross-Reference**: Use WebSearch to find independent corroboration:
   - Search for the core event, announcement, or finding
   - Find at least one independent source confirming the claim
   - Note contradictions

3. **Quantitative Accuracy**: Compare every number in the editorial text against the source:
   - Percentages must match exactly (95.83% must not become 96%)
   - Dollar amounts, counts, and dates must be verbatim
   - Flag any rounding or embellishment

4. **Name and Title Accuracy**: Verify:
   - Organization, product, and institute names use their official names
   - Person names and titles are correct
   - Technical method names match the source paper

5. **Date Window Check**: Verify:
   - The publication_date falls within {START_DATE} to {END_DATE}
   - The underlying event also falls within this window or within 30 days before it
   - Flag as stale if the event predates the window by more than 30 days

6. **Editorial Fidelity**: Compare editorial_headline and editorial_summary against the raw title and source:
   - Has the rewrite introduced claims not in the source?
   - Has it omitted important caveats?

## Verdicts

Assign exactly one per signal:

- CONFIRMED: All checks pass, numbers exact, names correct, event in window
- PARTIALLY_CONFIRMED: Core claim true but details embellished, rounded, or imprecise
- UNVERIFIABLE: Cannot find source or corroboration; may be hallucinated or too recent
- INACCURATE: Claim contradicted by evidence
- CONFIRMED_BUT_STALE: Facts correct but event predates reporting window by >30 days

## Output Format

Return ONLY a JSON array (no markdown fencing, no commentary before or after):

[
  {
    "signal_id": "...",
    "lever": "{LEVER_CODE}",
    "verdict": "CONFIRMED",
    "fact_check_note": "2-3 sentences. Cite sources consulted.",
    "sources_consulted": ["url1", "url2"],
    "issues_found": []
  },
  {
    "signal_id": "...",
    "lever": "{LEVER_CODE}",
    "verdict": "PARTIALLY_CONFIRMED",
    "fact_check_note": "Explanation of what is wrong.",
    "sources_consulted": ["url1"],
    "issues_found": [
      {
        "type": "quantitative_error|name_error|stale_event|missing_source|editorial_drift|hallucination",
        "detail": "Specific description",
        "original_text": "What the report says",
        "corrected_text": "What it should say"
      }
    ]
  }
]

Be thorough. A missed inaccuracy that reaches LinkedIn damages credibility. When in doubt between CONFIRMED and PARTIALLY_CONFIRMED, choose PARTIALLY_CONFIRMED.
```

## Step 4: Compile Fact-Check Results

After all 6 subagents return, parse their JSON results and merge into a single array. Build:

1. **Verdict summary**: count per verdict type
2. **Lever breakdown**: checked/confirmed/issues per lever
3. **Remediation list**: all non-CONFIRMED signals with their issues

Report the summary table to the user, then proceed immediately to remediation.

## Step 5: Apply Remediation

For each non-CONFIRMED signal, apply edits **sequentially** (do not use subagents for file writes — concurrent writes to shared files cause corruption).

For each signal requiring remediation:

### 5a. Carousel Data JSON

Read `research_db/processed/{start}_{end}_{cadence}_carousel_data.json`. Find the signal by `signal_id` in `lever_summaries.{LEVER}.top_signals[]`. Add:
- `"fact_check_status": "{VERDICT}"`
- `"fact_check_note": "{NOTE}"`

If PARTIALLY_CONFIRMED and `issues_found` contains corrections, apply `corrected_text` to the matching fields (`title`, `summary`, `key_facts`).

### 5b. Deduped JSONL

Read `research_db/processed/{start}_{end}_{cadence}_deduped.jsonl`. Find the line with matching `signal_id`. Add the same `fact_check_status` and `fact_check_note` fields. Apply text corrections if applicable. Write the file back.

### 5c. Synthesis Log

Read `research_db/processed/{start}_{end}_{cadence}_synthesis_log.json`. In `editorial_decisions.signals_per_lever.{LEVER}`, find the signal title string and append ` [FACT-CHECK: {VERDICT}]`.

### 5d. Raw JSONL

Search all files in `research_db/raw/` for lines containing the `signal_id`. For each match, add `fact_check_status` and `fact_check_note`. Apply text corrections if applicable.

### 5e. HTML Report

In the HTML report file, find the `<div class="signal-item">` containing the signal's headline text. Add:
- `data-fact-check="{VERDICT}"` attribute to the div
- `<!-- FACT-CHECK: {VERDICT} — {NOTE}. Flagged {TODAY}. -->` comment before the div

If PARTIALLY_CONFIRMED with text corrections:
- Update the `signal-headline` div content
- Update the `signal-summary` div content

## Step 6: Write Fact-Check Log

Write `research_db/processed/{start}_{end}_fact_check_log.json`:

```json
{
  "fact_check_run_id": "{start}_{end}_factcheck_{8char_uuid}",
  "report_file": "PR/{cadence}/{filename}",
  "date_window": {"start": "{start}", "end": "{end}"},
  "executed_at": "{ISO timestamp}",
  "total_signals_checked": N,
  "verdict_summary": {
    "CONFIRMED": N,
    "PARTIALLY_CONFIRMED": N,
    "UNVERIFIABLE": N,
    "INACCURATE": N,
    "CONFIRMED_BUT_STALE": N
  },
  "signals": [
    {
      "signal_id": "...",
      "lever": "...",
      "title": "...",
      "verdict": "...",
      "fact_check_note": "...",
      "sources_consulted": [],
      "issues_found": [],
      "remediation_applied": true,
      "files_modified": []
    }
  ],
  "lever_breakdown": {
    "COMPUTE": {"checked": N, "confirmed": N, "issues": N},
    "ENERGY": {"checked": N, "confirmed": N, "issues": N},
    "SOCIETY": {"checked": N, "confirmed": N, "issues": N},
    "INDUSTRY": {"checked": N, "confirmed": N, "issues": N},
    "CAPITAL": {"checked": N, "confirmed": N, "issues": N},
    "GOV": {"checked": N, "confirmed": N, "issues": N}
  }
}
```

## Step 7: Post-Run Summary

Present the full fact-check report:

```
## Fact-Check Complete: {report filename}

**Date window:** {start} to {end}
**Signals checked:** {total}

### Verdict Summary

| Verdict | Count |
|---|---|
| CONFIRMED | N |
| PARTIALLY_CONFIRMED | N |
| UNVERIFIABLE | N |
| INACCURATE | N |
| CONFIRMED_BUT_STALE | N |

### Issues Found & Remediated

| # | Lever | Signal | Verdict | Issue |
|---|---|---|---|---|
| 1 | COMPUTE | {title} | PARTIALLY_CONFIRMED | {detail} |
| ... | ... | ... | ... | ... |

### Files Modified

- {list of all files touched during remediation}

### Fact-Check Log

Written to: `research_db/processed/{start}_{end}_fact_check_log.json`

**Next step:** If the report was published from a PDF, re-export from the updated HTML file.
```

## Pre-Output Checklist

Before completing, verify:
- [ ] All signals from the report were checked (count matches carousel data top_signals total)
- [ ] Every non-CONFIRMED signal has `fact_check_status` and `fact_check_note` in the carousel data JSON
- [ ] Every non-CONFIRMED signal has the same fields in the deduped JSONL
- [ ] Every non-CONFIRMED signal has `data-fact-check` attribute and HTML comment in the report
- [ ] The synthesis log has `[FACT-CHECK: VERDICT]` annotations for non-CONFIRMED signals
- [ ] No signals were removed — only annotated
- [ ] PARTIALLY_CONFIRMED signals have corrected text applied where corrections were provided
- [ ] The fact-check log JSON is written and contains all signal results
- [ ] All JSON files remain valid JSON after modification
- [ ] All JSONL files remain valid JSONL (one object per line) after modification
- [ ] Quantitative corrections match source data exactly — no rounding
- [ ] All organization/product names use official names from verified sources
