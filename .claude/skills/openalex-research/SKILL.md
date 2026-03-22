---
name: openalex-research
description: Collect AI signals from cross-discipline academic papers via OpenAlex (free, no auth). Targets AI applied in medicine, law, energy, finance, education, and manufacturing — not CS papers (ArXiv covers those). Classifies by Scale Lever, writes JSONL to research_db/raw/.
disable-model-invocation: true
argument-hint: "daily|weekly|monthly|quarterly|annual"
---

# OpenAlex Cross-Discipline AI Signal Collector

Collect AI signals from academic papers published in non-CS fields via the OpenAlex API — free, no authentication required. This collector complements ArXiv (which covers CS/ML papers → COMPUTE lever) by capturing signals of AI diffusion into healthcare, law, energy, finance, education, and manufacturing → SOCIETY + INDUSTRY levers.

## 1. Validate Cadence

**REPORT_CADENCE:** Parse `$ARGUMENTS` to extract the cadence (first positional argument).

Verify that REPORT_CADENCE is exactly one of: `daily`, `weekly`, `monthly`, `quarterly`, `annual`.

If missing or invalid, **stop immediately** and ask the user:
> Please specify a valid cadence: `/openalex-research [daily|weekly|monthly|quarterly|annual]`

Also parse optional flags from `$ARGUMENTS`:
- `--days-back N`: Override default lookback window

## 2. Determine Lookback Window

Map the cadence to the correct `--days-back` value:

| Cadence     | --days-back | Rationale |
|-------------|-------------|-----------|
| `daily`     | 2           | Recent papers |
| `weekly`    | 7           | Standard week |
| `monthly`   | 31          | Calendar month |
| `quarterly` | 92          | ~3 months |
| `annual`    | 366         | Full year |

## 3. Pre-flight Checks

Verify dependencies:
```
python3 -c "import requests"
```

No API keys are required. OpenAlex is free and unauthenticated.

## 4. Execute the Collector

Run the OpenAlex signal collector script using Bash:

```
python3 ${CLAUDE_SKILL_DIR}/../../scripts/collect_openalex_signals.py --cadence <CADENCE> --days-back <DAYS_BACK>
```

Replace `<CADENCE>` and `<DAYS_BACK>` with the validated values. Pass through any optional flags the user provided.

The script will:
- Query OpenAlex for AI-related papers in 9 non-CS disciplines
- Sort results by citation count (highest-cited papers first)
- Classify signals against SOCIETY and INDUSTRY levers
- Deduplicate and write JSONL signal records to `research_db/raw/`
- Write a pipeline log JSON alongside the JSONL

The OpenAlex collector takes ~15-30 seconds (9 queries with polite delays).

## 5. Post-Run Report

After the script completes successfully:

1. Locate the pipeline log JSON file in `research_db/raw/` (filename ends with `_openalex_pipeline_log.json`)
2. Read the pipeline log to extract:
   - `records_written`: number of signal records written
   - `lever_distribution`: breakdown by primary lever
   - `domain_distribution`: breakdown by research domain
   - `direction_distribution`: direction breakdown
   - `output_file`: path to the JSONL file
   - `date_range`: start and end dates covered
3. Present a summary to the user:

```
OpenAlex Cross-Discipline AI Signal Collection Complete
Cadence:           <cadence>
Date range:        <start> to <end>
Signals:           <records_written> records

Lever Distribution:
  SOCIETY:         XX
  INDUSTRY:        XX

Domain Distribution:
  Healthcare:      XX
  Legal:           XX
  Energy:          XX
  Finance:         XX
  Education:       XX
  Manufacturing:   XX
  Materials:       XX
  Ethics:          XX
  Labor:           XX

Citation Stats:
  Max:             XX
  Median:          XX

Cost:              $0.00 (OpenAlex is free)

Output: <output_file>
```

## 6. Error Handling

- If the script exits with a non-zero code, report the error output to the user.
- If zero signals are found, inform the user and suggest:
  - Try a longer cadence (monthly or quarterly for more papers)
  - Increase `--days-back`
  - Check network connectivity to api.openalex.org
