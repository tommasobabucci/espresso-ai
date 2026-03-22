---
name: eia-research
description: Collect AI-relevant energy signals from the US Energy Information Administration (free API, requires free API key). Detects trends in electricity generation, renewable capacity, and grid utilization in AI-hub states. Classifies by Scale Lever, writes JSONL to research_db/raw/.
disable-model-invocation: true
argument-hint: "daily|weekly|monthly|quarterly|annual"
---

# EIA Energy Signal Collector

Collect AI-relevant energy signals from the US Energy Information Administration — a free API that requires a free API key (register at https://www.eia.gov/opendata/register.php). Detects trends in electricity generation mix, renewable capacity additions, and state-level consumption in AI-hub states. Classifies into the Scale Levers framework and writes structured JSONL signal records to `research_db/raw/`.

## 1. Validate Cadence

**REPORT_CADENCE:** Parse `$ARGUMENTS` to extract the cadence (first positional argument).

Verify that REPORT_CADENCE is exactly one of: `daily`, `weekly`, `monthly`, `quarterly`, `annual`.

If missing or invalid, **stop immediately** and ask the user:
> Please specify a valid cadence: `/eia-research [daily|weekly|monthly|quarterly|annual]`

Also parse optional flags from `$ARGUMENTS`:
- `--days-back N`: Override default lookback window

## 2. Determine Lookback Window

Map the cadence to the correct `--days-back` value:

| Cadence     | --days-back | Rationale |
|-------------|-------------|-----------|
| `daily`     | 2           | Recent data |
| `weekly`    | 7           | Standard week |
| `monthly`   | 31          | Calendar month |
| `quarterly` | 92          | ~3 months |
| `annual`    | 366         | Full year |

## 3. Pre-flight Checks

Verify dependencies:
```
python3 -c "import requests"
```

Verify the EIA API key is set:
```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv('.env/.env'); import os
key = os.getenv('EIA_API_KEY')
print('EIA_API_KEY=' + ('SET' if key else 'MISSING'))
"
```

If `EIA_API_KEY` is missing, **stop** and tell the user:
> EIA API key not found. Register for a free key at https://www.eia.gov/opendata/register.php and add it to `.env/.env` as `EIA_API_KEY=your_key_here`

## 4. Execute the Collector

Run the EIA signal collector script using Bash:

```
python3 ${CLAUDE_SKILL_DIR}/../../scripts/collect_eia_signals.py --cadence <CADENCE> --days-back <DAYS_BACK>
```

Replace `<CADENCE>` and `<DAYS_BACK>` with the validated values. Pass through any optional flags the user provided.

The script will:
- Query the EIA API v2 for electricity generation, state consumption, and capacity data
- Detect significant trends (YoY changes, renewable milestones, state-level spikes)
- Generate ENERGY-lever signals from trend analysis
- Deduplicate and write JSONL signal records to `research_db/raw/`
- Write a pipeline log JSON alongside the JSONL

The EIA collector takes ~15 seconds (3 API queries with polite delays).

Note: EIA data has a ~2 month lag. This is normal for government statistical data. The collector uses a generous lookback window to capture the most recent available data.

## 5. Post-Run Report

After the script completes successfully:

1. Locate the pipeline log JSON file in `research_db/raw/` (filename ends with `_eia_pipeline_log.json`)
2. Read the pipeline log to extract:
   - `records_written`: number of signal records written
   - `signal_type_distribution`: breakdown by signal type (generation_mix, state_consumption, capacity_additions, renewable_share)
   - `sub_variable_distribution`: breakdown by ENERGY sub-variable
   - `direction_distribution`: direction breakdown
   - `output_file`: path to the JSONL file
   - `date_range`: start and end dates covered
3. Present a summary to the user:

```
EIA Energy Signal Collection Complete
Cadence:           <cadence>
Date range:        <start> to <end>
Signals:           <records_written> records

Signal Types:
  Generation mix:      XX
  State consumption:   XX
  Capacity additions:  XX
  Renewable share:     XX

Sub-Variables:
  grid_capacity_utilization:     XX
  renewable_allocation:          XX
  data_center_power_intensity:   XX
  renewable_capex_cost:          XX

Cost:              $0.00 (EIA API is free)

Output: <output_file>
```

## 6. Error Handling

- If the script exits with a non-zero code, report the error output to the user.
- If `EIA_API_KEY` is not set, direct the user to register at https://www.eia.gov/opendata/register.php
- If zero signals are found, inform the user and suggest:
  - EIA data lags by ~2 months — try `--cadence monthly` or `--cadence quarterly`
  - Check network connectivity to api.eia.gov
