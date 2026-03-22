---
name: github-research
description: Collect open-source AI model releases and trending repos from GitHub and Hugging Face. Classifies by Scale Lever, writes JSONL to research_db/raw/.
disable-model-invocation: true
argument-hint: [daily|weekly|monthly|quarterly|annual]
allowed-tools: Bash, Read
---

# GitHub & Open-Source Signal Collector

Collect releases from curated AI repositories, discover trending AI repos, and track high-impact Hugging Face models. Classify them into the Scale Levers framework and write structured JSONL signal records to `research_db/raw/`.

## 1. Validate Cadence

**REPORT_CADENCE:** $ARGUMENTS

Verify that REPORT_CADENCE is exactly one of: `daily`, `weekly`, `monthly`, `quarterly`, `annual`.

If missing or invalid, **stop immediately** and ask the user:
> Please specify a valid cadence: `/github-research [daily|weekly|monthly|quarterly|annual]`

## 2. Determine Lookback Window

Map the cadence to the correct `--days-back` value:

| Cadence     | --days-back | Rationale |
|-------------|-------------|-----------|
| `daily`     | 2           | Recent releases |
| `weekly`    | 7           | Standard week |
| `monthly`   | 31          | Calendar month |
| `quarterly` | 92          | ~3 months |
| `annual`    | 366         | Full year |

## 3. Pre-flight Checks

Verify dependencies:
```
python3 -c "from dotenv import load_dotenv"
```

If this fails, tell the user to install: `pip install python-dotenv`

## 4. Execute the Collector

Run the GitHub signal collector script using Bash:

```
python3 ${CLAUDE_SKILL_DIR}/../../scripts/collect_github_signals.py --cadence <CADENCE> --days-back <DAYS_BACK>
```

Replace `<CADENCE>` and `<DAYS_BACK>` with the validated values from steps 1 and 2.

The script will:
- Check releases from ~25 curated AI repositories (transformers, vllm, llama.cpp, etc.)
- Search GitHub for newly trending AI repos above a star threshold
- Query Hugging Face for recently updated high-download models
- Classify all signals into Scale Levers sub-variables
- Deduplicate and write JSONL signal records to `research_db/raw/`
- Write a pipeline log JSON alongside the JSONL

Note: The script takes approximately 30-90 seconds depending on GitHub API rate limits. Setting a `GITHUB_TOKEN` in `.env/.env` increases the rate limit from 60 to 5,000 requests/hour.

## 5. Post-Run Report

After the script completes successfully:

1. Locate the pipeline log JSON file in `research_db/raw/` (filename ends with `_github_pipeline_log.json`)
2. Read the pipeline log to extract:
   - `total_results_unique`: number of unique entries collected
   - `records_written`: number of signal records written
   - `type_distribution`: breakdown by source type (release, trending, hf_model)
   - `lever_distribution`: breakdown by Scale Lever
   - `direction_distribution`: breakdown by direction
   - `output_file`: path to the JSONL file
   - `date_range`: start and end dates covered
3. Present a summary to the user:

```
GitHub Signal Collection Complete
Cadence:        <cadence>
Date range:     <start> to <end>
Signals:        <records_written> records (<total_results_unique> unique entries)

Source Type:
  Releases:    XX
  Trending:    XX
  HF Models:   XX

Lever Distribution:
  COMPUTE:   XX
  INDUSTRY:  XX
  SOCIETY:   XX
  GOV:       XX
  ENERGY:    XX
  CAPITAL:   XX

Output: <output_file>
```

## 6. Error Handling

- If the script exits with a non-zero code, report the error output to the user.
- If zero signals are found, inform the user and suggest:
  - Try a longer cadence or increase `--days-back`
  - Check if `GITHUB_TOKEN` is set in `.env/.env` (rate limit may be hit without it)
- If GitHub API returns 403 (rate limited), suggest setting `GITHUB_TOKEN` in `.env/.env`.
- If Hugging Face API fails, the script continues with GitHub-only results.
