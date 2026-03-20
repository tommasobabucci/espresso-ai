---
name: reddit-claude-research
description: Run the Reddit signal collector (via Claude web search) to gather AI signals from curated high-signal subreddits, classify by Scale Lever, deduplicate, and write JSONL output to research_db/raw/.
disable-model-invocation: true
argument-hint: [daily|weekly|monthly|quarterly|annual] [--days-back N]
allowed-tools: Bash, Read
---

# Reddit Claude Research — Signal Collection

Run the espresso·ai Reddit signal collector (via Claude API web search) to gather AI signals from curated subreddits.

## Arguments

**CADENCE** (required): `$ARGUMENTS[0]` — must be one of: `daily`, `weekly`, `monthly`, `quarterly`, `annual`.

**--days-back N** (optional): If `$ARGUMENTS` contains `--days-back` followed by an integer, pass it through to override the default lookback window for the cadence.

## Step 1: Validate Arguments

Parse `$ARGUMENTS` to extract the cadence and optional `--days-back` value.

- If no cadence is provided or `$ARGUMENTS` is empty, **stop** and ask the user:
  "Please specify a cadence: `/reddit-claude-research daily|weekly|monthly|quarterly|annual`"
- If the cadence is not one of `daily`, `weekly`, `monthly`, `quarterly`, `annual`, **stop** and list the valid options.
- If `--days-back` is present but its value is not a positive integer, **stop** and explain the error.

## Step 2: Pre-flight Checks

Run these checks via Bash before executing the collector. If any fail, report the specific issue and stop.

1. Verify the script exists:
   ```
   test -f .claude/scripts/collect_reddit_claude_signals.py
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
python3 .claude/scripts/collect_reddit_claude_signals.py --cadence <CADENCE> [--days-back <N>]
```

Use a Bash timeout of 600000ms (10 minutes) — the script makes up to 6 Claude API calls with web search (depending on cadence tier), so expect 2-5 minutes total runtime.

The script prints progress to stdout. Let it run to completion.

## Step 4: Post-Execution Summary

After the script completes successfully:

1. Find the pipeline log path from the script's stdout — it prints `Run log: <path>` near the end.
2. Read that pipeline log JSON file.
3. Present a summary to the user including:
   - Pipeline run ID
   - Date window covered
   - Model used
   - Subreddits tracked vs. subreddits with signals
   - Total signals collected and written
   - Signals with primary source vs. without
   - Quality metrics: speculation heavy, meme/humor, self-promotional, vendor astroturf, unknown domain, aggregator title, out-of-date, missing URL counts
   - API usage: input/output tokens, model
   - Direction distribution (+, -, ~, ?)
   - Lever distribution
   - Post type distribution
   - Subreddit distribution
   - Output JSONL file path

Do NOT read or summarize individual signals from the JSONL file — it is meant for downstream agents.

## Step 5: Error Handling

- **Non-zero exit code**: Report the error output to the user.
- **"ERROR: ANTHROPIC_API_KEY not found"**: Tell the user to add their Anthropic API key to `.env/.env` as `ANTHROPIC_API_KEY=sk-ant-...`
- **"Rate limited"**: The script handles retries automatically. If it still fails, suggest waiting a few minutes and retrying.
- **"API overloaded"**: Same as rate limiting — built-in retries. If persistent, try again later.
- **"No signals collected"**: Possible causes — API key invalid, web search returned no relevant Reddit posts for the date range, or subreddits had low activity during the window.
