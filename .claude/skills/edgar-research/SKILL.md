---
name: edgar-research
description: Collect AI-related SEC EDGAR corporate filings (10-K, 10-Q, 8-K) via free EFTS full-text search. Primary lever = CAPITAL. Classifies by Scale Lever, writes JSONL to research_db/raw/.
disable-model-invocation: true
argument-hint: "daily|weekly|monthly|quarterly|annual"
---

# SEC EDGAR AI Signal Collector

Collect AI-related corporate filings from SEC EDGAR — a free, public system with no authentication required. Searches for AI mentions in 10-K, 10-Q, 8-K, and DEF 14A filings from ~17 curated AI-heavy companies (NVDA, MSFT, GOOGL, AMZN, META, etc.) plus EFTS full-text search discovery. Classifies into the Scale Levers framework (primary lever: CAPITAL) and writes structured JSONL signal records to `research_db/raw/`.

## 1. Validate Cadence

**REPORT_CADENCE:** Parse `$ARGUMENTS` to extract the cadence (first positional argument).

Verify that REPORT_CADENCE is exactly one of: `daily`, `weekly`, `monthly`, `quarterly`, `annual`.

If missing or invalid, **stop immediately** and ask the user:
> Please specify a valid cadence: `/edgar-research [daily|weekly|monthly|quarterly|annual]`

Also parse optional flags from `$ARGUMENTS`:
- `--days-back N`: Override default lookback window
- `--test`: Run EFTS search only (skip company submissions endpoint)

## 2. Determine Lookback Window

Map the cadence to the correct `--days-back` value:

| Cadence     | --days-back | Rationale |
|-------------|-------------|-----------|
| `daily`     | 2           | Recent filings |
| `weekly`    | 7           | Standard week |
| `monthly`   | 31          | Calendar month |
| `quarterly` | 92          | ~3 months (captures full quarterly filing cycle) |
| `annual`    | 366         | Full year |

## 3. Pre-flight Checks

Verify dependencies:
```
python3 -c "import requests"
```

No API keys are required. SEC EDGAR EFTS is free and unauthenticated.

## 4. Execute the Collector

Run the EDGAR signal collector script using Bash:

```
python3 ${CLAUDE_SKILL_DIR}/../../scripts/collect_edgar_signals.py --cadence <CADENCE> --days-back <DAYS_BACK>
```

Replace `<CADENCE>` and `<DAYS_BACK>` with the validated values. Pass through any optional flags the user provided.

The script will:
- Query SEC EDGAR EFTS for AI-related terms in 10-K, 10-Q, 8-K, DEF 14A filings (free, no auth)
- Check ~17 curated AI-heavy companies for recent filings via submissions endpoint
- Score all EFTS results for AI relevance (keyword-based, drops false positives)
- Curated companies always pass (they're selected precisely for AI relevance)
- Classify signals with primary lever detection across CAPITAL, COMPUTE, INDUSTRY
- Deduplicate by accession number, URL, and title
- Write JSONL signal records to `research_db/raw/`
- Write a pipeline log JSON alongside the JSONL

Total runtime: ~45 seconds.

## 5. Post-Run Report

After the script completes successfully:

1. Locate the pipeline log JSON file in `research_db/raw/` (filename ends with `_edgar_pipeline_log.json`)
2. Read the pipeline log to extract:
   - `records_written`: number of signal records written
   - `form_type_distribution`: breakdown by filing type
   - `lever_distribution`: breakdown by Scale Lever
   - `company_distribution`: breakdown by company
   - `output_file`: path to the JSONL file
   - `date_range`: start and end dates covered
3. Present a summary to the user:

```
SEC EDGAR Signal Collection Complete
Cadence:           <cadence>
Date range:        <start> to <end>
Signals:           <records_written> records

Filing Types:
  10-K:            XX
  10-Q:            XX
  8-K:             XX

Lever Distribution:
  CAPITAL:         XX
  COMPUTE:         XX
  INDUSTRY:        XX

Top Companies:
  NVIDIA:          XX
  Microsoft:       XX
  ...

Cost:              $0.00 (SEC EDGAR is free)

Output: <output_file>
```

## 6. Error Handling

- If the script exits with a non-zero code, report the error output to the user.
- If zero signals are found, inform the user and suggest:
  - Try a longer cadence or increase `--days-back` (10-K/10-Q filings cluster around earnings season)
  - The SEC EDGAR EFTS may be temporarily unavailable
- If EFTS returns errors but company submissions succeed, report partial results.
