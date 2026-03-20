Run the influencer signal collector for a given cadence.

Usage: /influencer-research [daily|weekly|monthly|quarterly|annual] [--days-back N] [--group GROUP]

Collects AI signals from ~71 key influencers across 10 groups via parallel subagents with WebSearch, classifies by Scale Lever, deduplicates, and writes JSONL to research_db/raw/.

See .claude/skills/influencer-research/SKILL.md for full details.
