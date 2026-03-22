---
allowed-tools: Bash, Read
---

# EIA Energy Research

Collect AI-relevant energy signals from the US Energy Information Administration (EIA).

**Usage:** `/eia-research [daily|weekly|monthly|quarterly|annual]`

Queries the EIA API v2 (free, requires free API key) for:
- US electricity generation by fuel source (solar, wind, gas, nuclear, coal)
- State-level consumption in AI-hub states (VA, TX, OR, IA, NV, GA, OH, IL, AZ, NC)
- Renewable capacity additions

Generates ENERGY-lever signals from trend analysis (YoY changes, MoM spikes, renewable milestones). Writes JSONL to `research_db/raw/`.

**API key:** Register free at https://www.eia.gov/opendata/register.php, then add `EIA_API_KEY=your_key` to `.env/.env`.

**Note:** EIA data lags ~2 months. For best results, use `monthly` or `quarterly` cadence.

See `.claude/skills/eia-research/SKILL.md` for full details.
