# PR — LinkedIn Output Archive

This folder stores all finalized LinkedIn posts produced by the `linkedin-writer` agent.

## Subfolders by Cadence

- **daily/** — Daily snapshot posts
- **weekly/** — Weekly digest posts
- **monthly/** — Monthly synthesis posts
- **quarterly/** — Quarterly trend reports
- **annual/** — Annual state-of-AI articles

## File Naming Convention

```
YYYY-MM-DD_[cadence]_post.md
```

Examples:
- `2026-03-18_daily_post.md`
- `2026-03-17_weekly_post.md`
- `2026-03-01_monthly_post.md`

## Post Status

Each file should include a status header:

```markdown
---
status: draft | reviewed | published
published_at: (timestamp if published)
linkedin_url: (URL if published)
---
```

## Workflow

1. `linkedin-writer` agent generates draft → saved here
2. Run `/brand-check [filepath]` to review
3. Manually review and edit
4. Change status to `published` when posted to LinkedIn
5. Add the LinkedIn URL for tracking
