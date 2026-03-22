Full end-to-end pipeline: collect signals, synthesize carousel, fact-check. Chains /brew-espresso + /serve-espresso.

Usage: /brew-and-serve-espresso [daily|weekly|monthly|quarterly|annual] [--days-back N] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]

Runs the entire espresso pipeline in one command: first collects signals from all sources (/brew-espresso), then synthesizes a LinkedIn carousel and fact-checks every claim (/serve-espresso). The report path is computed automatically.

Cadence is required. --days-back is forwarded to both stages. --start-date/--end-date are forwarded only to the serve stage. If dates are given without --days-back, the lookback is computed to keep both stages aligned.

Output: PR/{cadence}/{date}_{cadence}_carousel.html (fact-checked)

See .claude/skills/brew-and-serve-espresso/SKILL.md for detailed step-by-step instructions.
