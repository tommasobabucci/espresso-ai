---
name: brew-and-serve-espresso
description: Full end-to-end pipeline: collect signals from all sources, synthesize a LinkedIn carousel, and fact-check every claim. Chains brew-espresso + serve-espresso.
argument-hint: [daily|weekly|monthly|quarterly|annual] [--days-back N] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
allowed-tools: Bash, Read, Write, Agent, WebSearch, WebFetch
---

# Brew & Serve Espresso — Full End-to-End Pipeline

Collect signals from all sources, synthesize a LinkedIn carousel, and fact-check every claim — in one command. This chains `/brew-espresso` (collection) and `/serve-espresso` (synthesis + fact-check) sequentially.

## Arguments

**CADENCE** (required): `$ARGUMENTS[0]` — must be one of: `daily`, `weekly`, `monthly`, `quarterly`, `annual`.

**--days-back N** (optional): Override the default lookback window. Forwarded to both brew and serve stages.

**--start-date YYYY-MM-DD** (optional): Start of the reporting window. Forwarded only to the serve stage (brew-espresso does not accept it).

**--end-date YYYY-MM-DD** (optional): End of the reporting window. Forwarded only to the serve stage.

## Step 1: Validate Arguments & Compute Date Window

Parse `$ARGUMENTS` for cadence (first positional arg), optional `--days-back N`, `--start-date`, `--end-date`.

- If no cadence is provided or `$ARGUMENTS` is empty, **stop** and ask: `"Please specify a cadence: /brew-and-serve-espresso daily|weekly|monthly|quarterly|annual"`
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

### Argument Forwarding

Build separate argument strings for each stage:

- `BREW_ARGS` = `{CADENCE}` + (if `--days-back N` provided: ` --days-back N`)
- `SERVE_ARGS` = `{CADENCE}` + all date flags provided by the user (`--days-back N`, `--start-date`, `--end-date`)

**Alignment rule:** If `--start-date`/`--end-date` are given but `--days-back` is NOT, compute `N = (END_DATE - START_DATE).days` and pass `--days-back N` to brew so both stages cover the same date window. brew-espresso does not accept `--start-date`/`--end-date`.

Report to the user: cadence, date window, expected output path.

## Step 2: Pre-flight Checks

Run combined checks from both brew-espresso and serve-espresso in one pass:

1. Verify `.env/.env` exists
2. Verify Python dependencies: `python3 -c "import requests; from dotenv import load_dotenv"`
3. Check which API keys are available:

```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv('.env/.env'); import os
print('ANTHROPIC_API_KEY=' + ('SET' if os.getenv('ANTHROPIC_API_KEY') else 'MISSING'))
print('PERPLEXITY_API_KEY=' + ('SET' if os.getenv('PERPLEXITY_API_KEY') else 'MISSING'))
"
```

Based on results, determine which collectors to **run** vs **skip**:

| Collector | Required API Key | Always runs? |
|---|---|---|
| ArXiv | None | Yes |
| Perplexity | `PERPLEXITY_API_KEY` | No |
| X / Claude | `ANTHROPIC_API_KEY` | No |
| X / Perplexity | `PERPLEXITY_API_KEY` | No |
| Reddit / Claude | `ANTHROPIC_API_KEY` | No |
| Reddit / Perplexity | `PERPLEXITY_API_KEY` | No |
| GitHub | None (optional `GITHUB_TOKEN`) | Yes |
| Regulatory | `ANTHROPIC_API_KEY` | No (Federal Register always runs; Claude web search requires key) |
| Influencer | None (uses WebSearch) | Yes |

4. Verify synthesis script exists: `.claude/scripts/synthesize_signals.py`
5. Verify carousel spec exists: `brand_assets/linkedin_templates/carousel_spec.md`
6. Verify brand guide exists: `brand_assets/design/BRAND.md`

If `.env/.env` is missing, Python deps are unavailable, or synthesis script/spec/brand files are missing, **stop** and report the issue.

If any collectors will be skipped, tell the user which ones and why, then proceed.

## Step 3: Run Brew Stage

Read `.claude/skills/brew-espresso/SKILL.md` and execute Steps 4–5 (parallel collector launch and unified summary) with `BREW_ARGS`.

This means: launch all eligible collectors as Agent tool calls in a single message, exactly as brew-espresso Step 4 specifies, using the same agent prompt templates, scripts, and timeouts.

After all agents return, compile the brew summary data. Do **NOT** display a "Next step" prompt — instead store the summary data for the unified summary at the end.

Report a brief status line: `"Brew complete: {N} signals from {M}/9 sources. Proceeding to synthesis..."`

## Step 4: Validate Brew Results

Check brew results before proceeding to serve:

- Count total signals collected across all successful collectors.
- If total signals = 0 (all collectors failed or returned empty): **stop** and report: `"All collectors failed or returned zero signals. Cannot proceed to synthesis. Debug individual collectors with /brew-espresso {CADENCE}."`
- If total signals > 0 but fewer than 3 collectors succeeded: **warn** that signal diversity may be low, but continue.
- Verify that at least one JSONL file exists in `research_db/raw/` with dates overlapping the computed date window. If none found, **stop** and report.

## Step 5: Run Serve Stage

Read `.claude/skills/serve-espresso/SKILL.md` and execute Steps 3–5 (run carousel, verify output, run fact-check) with `SERVE_ARGS`.

Skip serve-espresso's Step 2 (pre-flight checks) since they were already covered in Step 2 of this skill.

Follow serve-espresso's Steps 3–5 completely — do not skip any sub-steps or checks within the carousel or fact-check skills.

After completion, store the carousel and fact-check summary data for the unified summary.

## Step 6: Unified Summary

After both stages complete, present a single combined summary:

```
## espresso brewed & served

**Cadence:** {CADENCE}
**Date window:** {START_DATE} → {END_DATE}

### Stage 1: Collection (brew)

| Source | Status | Signals | Top Lever |
|---|---|---|---|
| ArXiv | success | NN | LEVER |
| Perplexity | success | NN | LEVER |
| X / Claude | success | NN | LEVER |
| X / Perplexity | success | NN | LEVER |
| Reddit / Claude | success | NN | LEVER |
| Reddit / Perplexity | success | NN | LEVER |
| GitHub | success | NN | LEVER |
| Regulatory | success | NN | LEVER |
| Influencer | success | NN | LEVER |

**Total signals:** NNN across N/9 sources

### Stage 2: Synthesis + Fact-Check (serve)

**Carousel:**
- Total signals loaded: {N}
- Unique after dedup: {N}
- Signals selected for carousel: {N} across 6 levers

**Fact-Check:**
- Signals checked: {N}
- CONFIRMED: {N}
- PARTIALLY_CONFIRMED: {N}
- UNVERIFIABLE: {N}
- INACCURATE: {N}
- CONFIRMED_BUT_STALE: {N}
- Remediations applied: {N}

### Skipped / Failed

- {source}: SKIPPED ({reason})
- {source}: FAILED ({error summary})

### Output Files

- Carousel HTML (fact-checked): {REPORT_PATH}
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
| Missing `.env/.env` or Python deps | Stop immediately |
| Missing synthesis script/spec/brand files | Stop immediately |
| Some collectors fail | Continue — partial results are normal |
| All collectors fail (0 signals) | Stop before serve stage |
| No JSONL in date window after brew | Stop before serve stage |
| Carousel synthesis fails (no HTML) | Stop — no HTML to fact-check |
| Carousel artifacts missing | Warn, continue to fact-check |
| Fact-check subagent failures | Partial results reported, continue |
