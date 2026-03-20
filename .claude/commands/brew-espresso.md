Run all espresso·ai research collectors in parallel for a given cadence.

Usage: /brew-espresso [daily|weekly|monthly|quarterly|annual] [--days-back N]

Launches 7 research collection pipelines simultaneously: ArXiv, Perplexity, X/Claude, X/Perplexity, Reddit/Claude, Reddit/Perplexity, and Influencer (~71 people). Skips collectors whose API keys are not configured. Presents a unified summary when complete.

Collection only — does not run synthesis or carousel generation.

See .claude/skills/brew-espresso/SKILL.md for full details.
