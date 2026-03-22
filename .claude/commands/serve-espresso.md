Synthesize a carousel and fact-check it in one step. Run after /brew-espresso.

Usage: /serve-espresso [daily|weekly|monthly|quarterly|annual] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD] [--days-back N]

Chains two skills in sequence: first generates a LinkedIn carousel from raw signals (/carousel), then fact-checks all claims in the output (/fact-check). The report path is computed automatically and passed between stages.

Cadence is required. If no dates are provided, defaults to the cadence's standard lookback window. Use --days-back to match a custom window from /brew-espresso.

Output: PR/{cadence}/{date}_{cadence}_carousel.html (fact-checked)

See .claude/skills/serve-espresso/SKILL.md for detailed step-by-step instructions.
