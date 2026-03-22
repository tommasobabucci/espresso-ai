---
name: serve-espresso
description: Chain carousel synthesis and fact-checking into a single command. Generates a LinkedIn carousel from raw signals, then fact-checks every claim before publication. Run after /brew-espresso.
argument-hint: [daily|weekly|monthly|quarterly|annual] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD] [--days-back N]
allowed-tools: Bash, Read, Write, Agent, WebSearch, WebFetch
---

# Serve Espresso — Carousel + Fact-Check Pipeline

Synthesize raw signals into a publication-ready LinkedIn carousel and fact-check every claim — in one step. Run this after `/brew-espresso` to complete the pipeline.

## Arguments

**CADENCE** (required): `$ARGUMENTS[0]` — must be one of: `daily`, `weekly`, `monthly`, `quarterly`, `annual`.

**--start-date YYYY-MM-DD** (optional): Start of the reporting window. Defaults to cadence-specific lookback from today.

**--end-date YYYY-MM-DD** (optional): End of the reporting window. Defaults to today.

**--days-back N** (optional): Override the default lookback window. Alternative to `--start-date`. If provided, `start_date = end_date - N days`. Takes precedence over `--start-date` if both are given.

## Step 1: Validate Arguments & Compute Date Window

Parse `$ARGUMENTS` for cadence (first positional arg), optional `--start-date`, `--end-date`, and `--days-back`.

- If no cadence is provided or `$ARGUMENTS` is empty, **stop** and ask: `"Please specify a cadence: /serve-espresso daily|weekly|monthly|quarterly|annual"`
- If the cadence is not one of `daily`, `weekly`, `monthly`, `quarterly`, `annual`, **stop** and list valid options.

Compute the date window:

| Cadence | Default Lookback |
|---|---|
| daily | 1 day |
| weekly | 7 days |
| monthly | 31 days |
| quarterly | 92 days |
| annual | 366 days |

- `END_DATE` = `--end-date` value, or today (YYYY-MM-DD)
- If `--days-back N` is provided: `START_DATE` = END_DATE minus N days
- Else if `--start-date` is provided: `START_DATE` = that value
- Else: `START_DATE` = END_DATE minus the default lookback from the table above

Compute the expected output path: `REPORT_PATH = PR/{CADENCE}/{END_DATE}_{CADENCE}_carousel.html`

Report to the user: cadence, date window, expected output path.

## Step 2: Pre-flight Checks

Verify these prerequisites before running either stage:

1. Raw JSONL files exist in `research_db/raw/` with dates overlapping the window. If none exist, **stop** and suggest: `"No raw signals found for this window. Run /brew-espresso {CADENCE} first."`
2. The synthesis script exists: `.claude/scripts/synthesize_signals.py`
3. The carousel spec exists: `brand_assets/linkedin_templates/carousel_spec.md`
4. The brand guide exists: `brand_assets/design/BRAND.md`

If any prerequisite besides raw data is missing, **stop** and report which file is missing.

## Step 3: Run Carousel

Read `.claude/skills/carousel/SKILL.md` and execute all of its steps with these parameters:

- CADENCE = `{CADENCE}`
- `--start-date` = `{START_DATE}`
- `--end-date` = `{END_DATE}`

Follow the carousel skill's complete procedure — do not skip any steps or checks.

## Step 4: Verify Carousel Output

After the carousel skill completes, verify:

1. **Required:** The HTML file exists at `{REPORT_PATH}`. If missing, **stop** and report: `"Carousel generation failed. Expected output at {REPORT_PATH} was not created. Run /carousel {CADENCE} manually to debug."`
2. **Expected:** Intermediate artifacts exist:
   - `research_db/processed/{START_DATE}_{END_DATE}_{CADENCE}_carousel_data.json`
   - `research_db/processed/{START_DATE}_{END_DATE}_{CADENCE}_deduped.jsonl`
   - `research_db/processed/{START_DATE}_{END_DATE}_{CADENCE}_synthesis_log.json`

   If intermediate artifacts are missing, warn but continue — fact-check can still verify the HTML, though remediation will be limited to the files that exist.

Report: carousel output confirmed, list of artifacts found.

## Step 5: Run Fact-Check

Read `.claude/skills/fact-check/SKILL.md` and execute all of its steps with these parameters:

- report-path = `{REPORT_PATH}`
- `--start-date` = `{START_DATE}`
- `--end-date` = `{END_DATE}`

Pass dates explicitly — do not rely on auto-detection, since they are already computed.

Follow the fact-check skill's complete procedure — do not skip any steps or checks.

## Step 6: Post-Run Summary

After both stages complete, present a unified summary combining results from both:

```
## espresso served

**Cadence:** {CADENCE}
**Date window:** {START_DATE} → {END_DATE}

### Carousel Generation

- Total signals loaded: {N}
- Unique after dedup: {N}
- Signals selected for carousel: {N} across 6 levers
- Output: {REPORT_PATH}

### Fact-Check Results

- Signals checked: {N}
- CONFIRMED: {N}
- PARTIALLY_CONFIRMED: {N}
- UNVERIFIABLE: {N}
- INACCURATE: {N}
- CONFIRMED_BUT_STALE: {N}
- Remediations applied: {N}

### Output Files

- Carousel (fact-checked): {REPORT_PATH}
- Carousel data: research_db/processed/{START_DATE}_{END_DATE}_{CADENCE}_carousel_data.json
- Deduped signals: research_db/processed/{START_DATE}_{END_DATE}_{CADENCE}_deduped.jsonl
- Synthesis log: research_db/processed/{START_DATE}_{END_DATE}_{CADENCE}_synthesis_log.json
- Fact-check log: research_db/processed/{START_DATE}_{END_DATE}_fact_check_log.json

**Next step:** Open the HTML in a browser. Print to PDF at 1080×1080px custom page size for LinkedIn upload.
```

## Error Handling

| Failure Point | Behavior |
|---|---|
| Missing/invalid cadence | Stop with usage guidance |
| No raw JSONL files for the window | Stop before carousel — suggest running `/brew-espresso` |
| Missing script/spec/brand files | Stop before carousel with the specific missing file |
| Carousel fails (no HTML produced) | Stop after Step 4 with debug guidance |
| Carousel succeeds but artifacts missing | Warn, continue to fact-check with limited remediation |
| Fact-check subagent failure | Handled by fact-check skill's own error handling (partial results reported) |
