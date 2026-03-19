---
name: arxiv-research
description: Collect and classify AI research papers from ArXiv using the Scale Levers framework. Runs the ArXiv signal collector pipeline for a specified cadence and writes structured JSONL records to research_db/raw/.
disable-model-invocation: true
argument-hint: [daily|weekly|monthly|quarterly|annual]
allowed-tools: Bash, Read
---

# ArXiv Research Signal Collector

Collect AI research papers from ArXiv, classify them into the Scale Levers framework, and write structured JSONL signal records to `research_db/raw/`.

## 1. Validate Cadence

**REPORT_CADENCE:** $ARGUMENTS

Verify that REPORT_CADENCE is exactly one of: `daily`, `weekly`, `monthly`, `quarterly`, `annual`.

If missing or invalid, **stop immediately** and ask the user:
> Please specify a valid cadence: `/arxiv-research [daily|weekly|monthly|quarterly|annual]`

## 2. Determine Lookback Window

Map the cadence to the correct `--days-back` value:

| Cadence     | --days-back | Rationale |
|-------------|-------------|-----------|
| `daily`     | 2           | ArXiv has 1-2 day indexing lag |
| `weekly`    | 7           | Standard week |
| `monthly`   | 31          | Calendar month |
| `quarterly` | 92          | ~3 months |
| `annual`    | 366         | Full year |

## 3. Execute the Collector

Run the ArXiv signal collector script using Bash:

```
python ${CLAUDE_SKILL_DIR}/../../scripts/collect_arxiv_signals.py --cadence <CADENCE> --days-back <DAYS_BACK>
```

Replace `<CADENCE>` and `<DAYS_BACK>` with the validated values from steps 1 and 2.

The script will:
- Query ArXiv API across 20 signal queries covering all Scale Levers (COMPUTE, ENERGY, SOCIETY, INDUSTRY, CAPITAL, GOV)
- Classify papers into Scale Levers sub-variables
- Deduplicate by ArXiv ID
- Write JSONL signal records to `research_db/raw/`
- Write a pipeline log JSON alongside the JSONL

Note: The script takes approximately 60-90 seconds due to ArXiv API rate limiting (3-second delay between queries).

## 4. Post-Run Report

After the script completes successfully:

1. Locate the pipeline log JSON file in `research_db/raw/` (filename ends with `_arxiv_pipeline_log.json`)
2. Read the pipeline log to extract:
   - `total_results_unique`: number of unique papers collected
   - `records_written`: number of signal records written
   - `lever_distribution`: breakdown by Scale Lever
   - `output_file`: path to the JSONL file
   - `date_range`: start and end dates covered
3. Present a summary to the user:

```
ArXiv Signal Collection Complete
Cadence:        <cadence>
Date range:     <start> to <end>
Signals:        <records_written> records (<total_results_unique> unique papers)

Lever Distribution:
  COMPUTE:   XX papers
  INDUSTRY:  XX papers
  SOCIETY:   XX papers
  GOV:       XX papers
  ENERGY:    XX papers
  CAPITAL:   XX papers

Output: <output_file>
```

## 5. Error Handling

- If the script exits with a non-zero code, report the error output to the user.
- If zero papers are found, inform the user and suggest:
  - ArXiv indexing lag may mean very recent papers are not yet available
  - Try increasing the lookback window: `The script attempted a broader fallback search automatically. If still empty, try a longer cadence or wait a day.`
- If the output file is not found in `research_db/raw/`, flag this as an issue.
