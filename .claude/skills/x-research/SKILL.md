---
name: x-research
description: Run the X/Twitter signal collector to gather AI signals from curated high-signal accounts via Apify, classify by Scale Lever, deduplicate, and write JSONL output to research_db/raw/.
disable-model-invocation: true
argument-hint: [daily|weekly|monthly|quarterly|annual] [--days-back N]
allowed-tools: Bash, Read
---

# X Research — Signal Collection

Run the espresso·ai X/Twitter signal collector to gather AI signals from curated accounts.

## Arguments

**CADENCE** (required): `$ARGUMENTS[0]` — must be one of: `daily`, `weekly`, `monthly`, `quarterly`, `annual`.

**--days-back N** (optional): If `$ARGUMENTS` contains `--days-back` followed by an integer, pass it through to override the default lookback window for the cadence.

## Step 1: Validate Arguments

Parse `$ARGUMENTS` to extract the cadence and optional `--days-back` value.

- If no cadence is provided or `$ARGUMENTS` is empty, **stop** and ask the user:
  "Please specify a cadence: `/x-research daily|weekly|monthly|quarterly|annual`"
- If the cadence is not one of `daily`, `weekly`, `monthly`, `quarterly`, `annual`, **stop** and list the valid options.
- If `--days-back` is present but its value is not a positive integer, **stop** and explain the error.

## Step 2: Pre-flight Checks

Run these checks via Bash before executing the collector. If any fail, report the specific issue and stop.

1. Verify the script exists:
   ```
   test -f .claude/scripts/collect_x_signals.py
   ```

2. Verify the .env file exists:
   ```
   test -f .env/.env
   ```

3. Verify Python dependencies are available:
   ```
   python3 -c "import requests; from dotenv import load_dotenv"
   ```
   If this fails, tell the user to run: `pip install requests python-dotenv`

## Step 3: Run the Collector

Execute the script from the project root directory:

```bash
python3 .claude/scripts/collect_x_signals.py --cadence <CADENCE> [--days-back <N>]
```

Use a Bash timeout of 600000ms (10 minutes) — the script starts an Apify actor run which scrapes ~28 X accounts, so expect 2-5 minutes total runtime.

The script prints progress to stdout. Let it run to completion.

## Step 4: Post-Execution Summary

After the script completes successfully:

1. Find the pipeline log path from the script's stdout — it prints `Run log: <path>` near the end.
2. Read that pipeline log JSON file.
3. Present a summary to the user including:
   - Pipeline run ID
   - Date window covered
   - Accounts tracked vs. accounts with signals
   - Raw tweets fetched
   - Skipped counts (retweets, replies, low engagement)
   - Final signals written
   - Quality metrics: no_primary_source, low_engagement, thread_fragment counts
   - Direction distribution (+, -, ~, ?)
   - Lever distribution
   - Output JSONL file path

Do NOT read or summarize individual signals from the JSONL file — it is meant for downstream agents.

## Step 5: Error Handling

- **Non-zero exit code**: Report the error output to the user.
- **"ERROR: APIFY_API_TOKEN not found"**: Tell the user to add their Apify API token to `.env/.env` as `APIFY_API_TOKEN=apify_api_...`
- **"ERROR: Failed to start actor run"**: Suggest checking Apify token validity and account credits at apify.com.
- **"Actor run FAILED"**: The Apify actor may have encountered an issue. Suggest checking the Apify dashboard for run details.
- **"No signals collected"**: Possible causes — inactive accounts, date range too narrow, or engagement thresholds too high for the selected cadence.
