---
allowed-tools: Bash, Read
---

# OpenAlex Cross-Discipline AI Research

Collect AI signals from academic papers in non-CS fields via OpenAlex.

**Usage:** `/openalex-research [daily|weekly|monthly|quarterly|annual]`

Queries the OpenAlex API (free, no auth) for AI papers published in:
- Medicine & Healthcare
- Law & Policy
- Energy & Environment
- Economics & Finance
- Education
- Manufacturing & Engineering
- Materials Science
- AI Ethics & Fairness
- Labor Economics & Workforce

Complements ArXiv (CS/ML papers → COMPUTE lever) by capturing AI diffusion into real-world domains → SOCIETY + INDUSTRY levers. Papers sorted by citation count. Writes JSONL to `research_db/raw/`.

**No API key required.**

See `.claude/skills/openalex-research/SKILL.md` for full details.
