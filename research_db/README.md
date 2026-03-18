# research_db — Intelligence Storage

This folder is the persistent memory of espresso.ai. All collected and processed AI news data lives here.

## Subfolders

- **raw/** — Unprocessed articles fetched by `news-collector`. JSON files named `YYYY-MM-DD_[source].json`
- **processed/** — Scored and filtered articles from `signal-filter`. JSON files named `YYYY-MM-DD_processed.json`
- **archive/** — Historical data moved here after pipeline runs. Enables longitudinal analysis.

## Naming Convention

```
YYYY-MM-DD_[agent]_[source/type].json
```

## Key Files

- `pipeline_log.json` — Running log of all pipeline executions with timestamps and status
- `last_run.json` — Tracks last collection timestamp per source to avoid re-fetching

## Data Retention

- Raw data: kept for 30 days, then archived
- Processed data: kept for 90 days, then archived
- Archive: kept indefinitely for trend analysis
