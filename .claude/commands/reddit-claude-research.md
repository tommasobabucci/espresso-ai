Run the Reddit signal collector (via Claude web search) for a given cadence.

Usage: /reddit-claude-research [daily|weekly|monthly|quarterly|annual] [--days-back N]

Collects AI signals from curated high-signal Reddit subreddits via Claude API with web search, classifies by Scale Lever, and writes JSONL to research_db/raw/.

See .claude/skills/reddit-claude-research/SKILL.md for full details.
