Synthesize raw signals into a LinkedIn carousel for any cadence.

Usage: /carousel [daily|weekly|monthly|quarterly|annual] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]

Runs the full synthesis pipeline: loads raw JSONL signals, deduplicates across sources, scores and ranks them, selects top 5 per Scale Lever, writes editorial content in espresso·ai voice, and generates an 8-slide HTML carousel (cover + 6 lever slides + about).

Cadence is required. If no dates are provided, defaults to the cadence's standard lookback window.

Output: PR/{cadence}/{date}_{cadence}_carousel.html

See .claude/skills/carousel/SKILL.md for detailed step-by-step instructions.
