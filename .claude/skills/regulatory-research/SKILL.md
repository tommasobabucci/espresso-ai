---
name: regulatory-research
description: Collect AI regulatory signals from the US Federal Register (free API, no auth). Classifies by Scale Lever, writes JSONL to research_db/raw/.
disable-model-invocation: true
argument-hint: "daily|weekly|monthly|quarterly|annual"
---

# Federal Register AI Signal Collector

Collect AI regulatory signals from the US Federal Register — a free, public API with no authentication required. Classify into the Scale Levers framework and write structured JSONL signal records to `research_db/raw/`.

## 1. Validate Cadence

**REPORT_CADENCE:** Parse `$ARGUMENTS` to extract the cadence (first positional argument).

Verify that REPORT_CADENCE is exactly one of: `daily`, `weekly`, `monthly`, `quarterly`, `annual`.

If missing or invalid, **stop immediately** and ask the user:
> Please specify a valid cadence: `/regulatory-research [daily|weekly|monthly|quarterly|annual]`

Also parse optional flags from `$ARGUMENTS`:
- `--days-back N`: Override default lookback window

## 2. Determine Lookback Window

Map the cadence to the correct `--days-back` value:

| Cadence     | --days-back | Rationale |
|-------------|-------------|-----------|
| `daily`     | 2           | Recent filings |
| `weekly`    | 7           | Standard week |
| `monthly`   | 31          | Calendar month |
| `quarterly` | 92          | ~3 months |
| `annual`    | 366         | Full year |

## 3. Pre-flight Checks

Verify dependencies:
```
python3 -c "import requests"
```

No API keys are required. The Federal Register API is free and unauthenticated.

## 4. Execute the Collector

Run the regulatory signal collector script using Bash:

```
python3 ${CLAUDE_SKILL_DIR}/../../scripts/collect_regulatory_signals.py --cadence <CADENCE> --days-back <DAYS_BACK>
```

Replace `<CADENCE>` and `<DAYS_BACK>` with the validated values. Pass through any optional flags the user provided.

The script will:
- Query the US Federal Register API for AI-related documents (no auth, free)
- Classify all signals as GOV lever with appropriate sub-variables
- Detect secondary lever impacts (COMPUTE for chip controls, ENERGY for environmental policy, etc.)
- Deduplicate and write JSONL signal records to `research_db/raw/`
- Write a pipeline log JSON alongside the JSONL

The Federal Register portion takes ~10 seconds.

## 5. Post-Run Report

After the script completes successfully:

1. Locate the pipeline log JSON file in `research_db/raw/` (filename ends with `_regulatory_pipeline_log.json`)
2. Read the pipeline log to extract:
   - `records_written`: number of signal records written
   - `document_type_distribution`: breakdown by document type
   - `direction_distribution`: direction breakdown
   - `output_file`: path to the JSONL file
   - `date_range`: start and end dates covered
3. Present a summary to the user:

```
Regulatory Signal Collection Complete
Cadence:           <cadence>
Date range:        <start> to <end>
Signals:           <records_written> records

Document Types:
  Regulation:      XX
  Proposed Rule:   XX
  Notice:          XX

Cost:              $0.00 (Federal Register is free)

Output: <output_file>
```

## 6. Error Handling

- If the script exits with a non-zero code, report the error output to the user.
- If zero signals are found, inform the user and suggest:
  - Try a longer cadence or increase `--days-back`
  - Check network connectivity to federalregister.gov
