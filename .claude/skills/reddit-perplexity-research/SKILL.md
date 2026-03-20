---
name: reddit-perplexity-research
description: Run the Perplexity sonar-pro signal collector to find high-signal AI posts from curated Reddit subreddits by searching recent discussions, research posts, and practitioner experience reports. Classifies by Scale Lever, deduplicates, and writes JSONL output to research_db/raw/.
disable-model-invocation: true
argument-hint: [daily|weekly|monthly|quarterly|annual] [--days-back N]
allowed-tools: Bash, Read
---

# Reddit Perplexity Research — Signal Collection

Run the espresso·ai Reddit-Perplexity signal collector to find AI signals from curated subreddits via Perplexity web search.

## Arguments

**CADENCE** (required): `$ARGUMENTS[0]` — must be one of: `daily`, `weekly`, `monthly`, `quarterly`, `annual`.

**--days-back N** (optional): If `$ARGUMENTS` contains `--days-back` followed by an integer, pass it through to override the default lookback window for the cadence.

## Step 1: Validate Arguments

Parse `$ARGUMENTS` to extract the cadence and optional `--days-back` value.

- If no cadence is provided or `$ARGUMENTS` is empty, **stop** and ask the user:
  "Please specify a cadence: `/reddit-perplexity-research daily|weekly|monthly|quarterly|annual`"
- If the cadence is not one of `daily`, `weekly`, `monthly`, `quarterly`, `annual`, **stop** and list the valid options.
- If `--days-back` is present but its value is not a positive integer, **stop** and explain the error.

## Step 2: Pre-flight Checks

Run these checks via Bash before executing the collector. If any fail, report the specific issue and stop.

1. Verify the script exists:
   ```
   test -f .claude/scripts/collect_reddit_perplexity_signals.py
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
python3 .claude/scripts/collect_reddit_perplexity_signals.py --cadence <CADENCE> [--days-back <N>]
```

Use a Bash timeout of 300000ms (5 minutes) — the script makes up to 6 Perplexity API calls with 2-second delays between them, so expect 30-90 seconds total runtime.

The script prints progress per subreddit group to stdout. Let it run to completion.

## Step 4: Post-Execution Summary

After the script completes successfully:

1. Find the pipeline log path from the script's stdout — it prints `Run log: <path>` near the end.
2. Read that pipeline log JSON file.
3. Present a summary to the user including:
   - Pipeline run ID
   - Date window covered
   - Subreddits tracked vs. subreddits with signals
   - Total signals collected (before dedup)
   - Duplicates removed
   - Final signals written
   - Signals with primary source vs. without
   - Quality metrics: speculation heavy, meme/humor, self-promotional, vendor astroturf counts
   - Direction distribution (+, -, ~, ?)
   - Lever distribution
   - Post type distribution
   - Subreddit distribution
   - Output JSONL file path

Do NOT read or summarize individual signals from the JSONL file — it is meant for downstream agents.

## Step 5: Error Handling

- **Non-zero exit code**: Report the error output to the user.
- **"ERROR: PERPLEXITY_API_KEY not found"**: Tell the user to verify `.env/.env` contains `PERPLEXITY_API_KEY=pplx-...`
- **"ERROR: API request failed"**: Suggest checking network connectivity and API key validity.
- **"No signals collected"**: Possible causes — subreddits had low activity for the period, network issues, or Perplexity not indexing Reddit content recently.
