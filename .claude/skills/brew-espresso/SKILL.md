---
name: brew-espresso
description: Run all espresso·ai research collectors in parallel for a given cadence. Launches ArXiv, Perplexity, X (Claude/Perplexity), Reddit (Claude/Perplexity), and Influencer collectors simultaneously. Skips collectors with missing API keys. Collection only — does not run synthesis.
argument-hint: [daily|weekly|monthly|quarterly|annual] [--days-back N]
allowed-tools: Bash, Read, Agent, WebSearch, Write
---

# Brew Espresso — Full Research Collection

Run all 9 espresso·ai research collectors in parallel for a given cadence. Skips collectors whose API keys are not configured. Presents a unified summary when complete.

## Arguments

**CADENCE** (required): `$ARGUMENTS[0]` — must be one of: `daily`, `weekly`, `monthly`, `quarterly`, `annual`.

**--days-back N** (optional): Override the default lookback window for all collectors.

## Step 1: Validate Arguments

Parse `$ARGUMENTS` to extract the cadence and optional `--days-back` value.

- If no cadence is provided or `$ARGUMENTS` is empty, **stop** and ask the user:
  "Please specify a cadence: `/brew-espresso daily|weekly|monthly|quarterly|annual`"
- If the cadence is not one of `daily`, `weekly`, `monthly`, `quarterly`, `annual`, **stop** and list valid options.
- If `--days-back` is present but its value is not a positive integer, **stop** and explain the error.

## Step 2: Compute Date Window

Based on the cadence and today's date, compute the date window:

| Cadence | Default Lookback |
|---|---|
| daily | 2 days |
| weekly | 7 days |
| monthly | 31 days |
| quarterly | 92 days |
| annual | 366 days |

If `--days-back N` is specified, use N days instead.

Set `END_DATE` = today's date (YYYY-MM-DD) and `START_DATE` = END_DATE minus the lookback.

Build the `DAYS_BACK_ARG` string: if the user specified `--days-back N`, set it to `--days-back N`; otherwise leave it empty (let each script use its own default).

## Step 3: Pre-flight Checks

Run these checks via Bash:

1. Verify `.env/.env` exists
2. Verify Python dependencies: `python3 -c "import requests; from dotenv import load_dotenv"`
3. Check which API keys are available:

```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv('.env/.env'); import os
print('ANTHROPIC_API_KEY=' + ('SET' if os.getenv('ANTHROPIC_API_KEY') else 'MISSING'))
print('PERPLEXITY_API_KEY=' + ('SET' if os.getenv('PERPLEXITY_API_KEY') else 'MISSING'))
print('EIA_API_KEY=' + ('SET' if os.getenv('EIA_API_KEY') else 'MISSING'))
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
| EIA Energy | `EIA_API_KEY` (free registration) | No |
| OpenAlex | None | Yes |
| Influencer | None (uses WebSearch) | Yes |

If any collectors will be skipped, tell the user which ones and why, then proceed with the available collectors.

If `.env/.env` is missing or Python deps are unavailable, **stop** and report the issue.

## Step 4: Launch Collectors in Parallel

Launch all eligible collectors as Agent tool calls **in a single message** for maximum parallelism.

### Script-based collectors (up to 6)

For each eligible script-based collector, launch an Agent with this prompt template (fill in `{LABEL}`, `{SCRIPT}`, `{CADENCE}`, `{DAYS_BACK_ARG}`, `{TIMEOUT}`):

```
You are a research collector agent for espresso·ai. Your job is to run a single collection script and report results.

Run this command via the Bash tool with a timeout of {TIMEOUT} milliseconds:

python3 .claude/scripts/{SCRIPT} --cadence {CADENCE} {DAYS_BACK_ARG}

After completion:
- If exit code is 0: Look for a line containing "Run log:" or "Pipeline log:" in stdout to find the pipeline log JSON path. Read that JSON file and return a summary with these fields: pipeline_run_id, date_window (start_date to end_date), signals_written, lever_distribution, direction_distribution, output_file_path.
- If exit code is non-zero: Return the full error output and mark status as "failed".

Do NOT read or summarize individual signals from the JSONL output.
```

Use these specific parameters per collector:

| Label | Script | Timeout (ms) |
|---|---|---|
| `arxiv-collector` | `collect_arxiv_signals.py` | 120000 |
| `perplexity-collector` | `collect_perplexity_signals.py` | 300000 |
| `x-claude-collector` | `collect_x_claude_signals.py` | 600000 |
| `x-perplexity-collector` | `collect_x_perplexity_signals.py` | 300000 |
| `reddit-claude-collector` | `collect_reddit_claude_signals.py` | 600000 |
| `reddit-perplexity-collector` | `collect_reddit_perplexity_signals.py` | 300000 |
| `github-collector` | `collect_github_signals.py` | 120000 |
| `regulatory-collector` | `collect_regulatory_signals.py` | 120000 |
| `edgar-collector` | `collect_edgar_signals.py` | 120000 |
| `eia-collector` | `collect_eia_signals.py` | 120000 |
| `openalex-collector` | `collect_openalex_signals.py` | 120000 |

### Influencer collector

Launch one Agent with the following prompt (fill in `{CADENCE}`, `{START_DATE}`, `{END_DATE}`, `{DAYS_BACK_ARG}`):

```
You are the influencer research orchestrator for espresso·ai.

1. Read the file `.claude/skills/influencer-research/SKILL.md`
2. Execute Steps 2 through 5 from that skill with these parameters:
   - CADENCE = {CADENCE}
   - START_DATE = {START_DATE}
   - END_DATE = {END_DATE}
   - DAYS_BACK override = {DAYS_BACK_ARG} (empty means use the skill's default)
3. After the consolidation script completes, read the pipeline log JSON and return a summary with: pipeline_run_id, date_window, signals_written, lever_distribution, direction_distribution, output_file_path.

Do NOT read or summarize individual signals from the JSONL output.
```

This agent needs tools: Bash, Read, Agent, WebSearch, Write.

## Step 5: Present Unified Summary

After all agents return, present a single consolidated summary:

```
## espresso brew complete

**Cadence:** {cadence}
**Date window:** {START_DATE} → {END_DATE}

### Collector Results

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
| EDGAR | success | NN | LEVER |
| EIA Energy | success | NN | LEVER |
| OpenAlex | success | NN | LEVER |
| Influencer | success | NN | LEVER |

**Total signals:** NNN across N/12 sources

### Aggregate Lever Distribution

| Lever | Count | Share |
|---|---|---|
| COMPUTE | NN | NN% |
| ENERGY | NN | NN% |
| SOCIETY | NN | NN% |
| INDUSTRY | NN | NN% |
| CAPITAL | NN | NN% |
| GOV | NN | NN% |

### Aggregate Direction Distribution

| Direction | Count | Share |
|---|---|---|
| + | NN | NN% |
| - | NN | NN% |
| ~ | NN | NN% |
| ? | NN | NN% |

### Skipped / Failed

- {source}: SKIPPED ({reason})
- {source}: FAILED ({error summary})

### Output Files

- `research_db/raw/{file1}`
- `research_db/raw/{file2}`
- ...

**Next step:** Run `/carousel {cadence}` to synthesize these signals into a LinkedIn carousel.
```

Compute aggregate distributions by summing across all successful collectors. Calculate shares as percentages of total signals.

## Step 6: Error Handling

- **Each collector is independent.** A failure in one does not block or affect others.
- **Partial success is normal.** Report per-collector status (success / failed / skipped).
- **Agent timeout:** Report as failed with "timed out" status.
- **Script non-zero exit:** Capture stderr/stdout from the agent's report, show as failed with error summary.
- **All collectors fail:** Report the full failure list with error details. Suggest running individual collectors (e.g., `/x-claude-research weekly`) for debugging.
- **Influencer subagent partial failure:** Handled internally by the influencer skill. brew-espresso sees it as a single result.
