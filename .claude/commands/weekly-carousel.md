Synthesize raw signals into a weekly LinkedIn carousel.

Usage: /weekly-carousel [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]

Runs the full synthesis pipeline: loads raw JSONL signals, deduplicates across sources, scores and ranks them, selects top 5 per Scale Lever, writes editorial content in espresso·ai voice, and generates a 9-slide HTML carousel.

If no dates are provided, defaults to the last 7 days.

Output: PR/weekly/{date}_weekly_carousel.html

See .claude/skills/weekly-carousel/SKILL.md for detailed step-by-step instructions.
