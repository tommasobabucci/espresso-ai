---
name: carousel
description: Synthesize raw signals into a LinkedIn carousel for any cadence (daily, weekly, monthly, quarterly, annual). Deduplicates across sources, scores signals, selects top 5 per lever, writes editorial content in espresso·ai voice, and generates the final 8-slide HTML carousel.
argument-hint: [daily|weekly|monthly|quarterly|annual] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
allowed-tools: Bash, Read, Write
---

# Carousel — Signal Synthesis & Output Generation

Synthesize raw JSONL signals into a publication-ready LinkedIn carousel (8 slides, 1080x1350px) for any cadence.

## Arguments

**cadence** (required, positional): First argument. Must be one of: `daily`, `weekly`, `monthly`, `quarterly`, `annual`.

**--start-date** (optional): Start of the reporting window. Defaults to cadence-specific lookback from today.

**--end-date** (optional): End of the reporting window. Defaults to today.

## Cadence Configuration

This table defines all cadence-specific values. Only the cover slide changes — lever slides are identical across cadences.

| Cadence | Nav Right Text | Date Eyebrow Format | Section Label | Default Lookback |
|---|---|---|---|---|
| daily | `A strong sip of today's AI news` | `{Month} {DD}, {YYYY}` | `Today` | 1 day |
| weekly | `A strong sip of this week's AI news` | `Week of {Month} {DD}–{DD}, {YYYY}` | `This Week` | 7 days |
| monthly | `A strong sip of this month's AI news` | `{Month} {YYYY}` | `This Month` | 31 days |
| quarterly | `A strong sip of this quarter's AI news` | `Q{N} {YYYY}` | `This Quarter` | 92 days |
| annual | `A strong sip of this year's AI news` | `{YYYY}` | `This Year` | 366 days |

**Quarterly eyebrow logic:** If start_date is in Jan–Mar → Q1, Apr–Jun → Q2, Jul–Sep → Q3, Oct–Dec → Q4.

## Step 1: Validate Arguments & Compute Date Window

Parse `$ARGUMENTS` for cadence (first positional arg), `--start-date`, and `--end-date`.

- Cadence is **required**. If missing or invalid, **stop** and report: `"Please specify a cadence: /carousel daily|weekly|monthly|quarterly|annual"`
- If dates not provided, compute from today's date: `end_date = today`, `start_date = today - {lookback days from cadence table}`
- Validate date format is `YYYY-MM-DD`
- Set `CADENCE` from the validated argument

## Step 2: Pre-flight Checks

Verify:
1. The synthesis script exists: `.claude/scripts/synthesize_signals.py`
2. Raw JSONL files exist in `research_db/raw/` matching the date window
3. The template spec exists: `brand_assets/linkedin_templates/carousel_spec.md`
4. The brand guide exists: `brand_assets/design/BRAND.md`

If any are missing, **stop** and report the issue.

## Step 3: Run Synthesis Script

Execute the Python synthesis pipeline:

```bash
python3 .claude/scripts/synthesize_signals.py \
  --cadence {CADENCE} \
  --start-date {START_DATE} \
  --end-date {END_DATE}
```

This script:
1. Loads all matching JSONL files from `research_db/raw/`
2. Deduplicates signals across sources (URL normalization + title similarity + entity co-reference)
3. Scores each signal on a 1-10 scale
4. Selects top 5 signals per Scale Lever with direction and source diversity
5. Writes intermediate JSON to `research_db/processed/{start}_{end}_{cadence}_carousel_data.json`
6. Writes deduped JSONL to `research_db/processed/{start}_{end}_{cadence}_deduped.jsonl`

Review the script output for errors. Report the total loaded, duplicates removed, and unique signal counts.

## Step 4: Read Intermediate Data

Read the carousel data JSON file from `research_db/processed/{start}_{end}_{cadence}_carousel_data.json`.

Extract:
- `meta.total_signals_loaded` — total signals collected
- `meta.unique_signals` — after deduplication
- `meta.source_files` — list of source pipelines
- `overall_stats.direction_breakdown` — overall direction counts
- For each lever in `lever_summaries`: `signal_count`, `direction_breakdown`, `dominant_direction`, `top_sub_variables`, `unselected_count`, `unselected_context`, `top_signals`

## Step 5: Read Template Spec & Brand Guide

Read both files:
- `brand_assets/linkedin_templates/carousel_spec.md` — structural rules, CSS, content slots
- `brand_assets/design/BRAND.md` — voice, tone, anti-patterns

These are your authoritative references for generating the HTML. Follow every rule.

## Step 6: Review Flagged Duplicate Clusters

Check `flagged_duplicate_clusters` in the carousel data. If any exist:
- Review the titles in each cluster
- Determine if they are truly about the same event
- If duplicates: use the first (highest-scored) and discard the other
- If distinct: keep both

## Step 7: Write Editorial Content

For each piece of editorial text, follow espresso·ai voice rules strictly. Check every sentence against the anti-patterns list in BRAND.md. No em dashes as connectors, no lists of three, no transitional openers, no meta-commentary, no AI vocabulary.

### Editorial Accuracy Rules

These rules are **mandatory** and override voice/style preferences when they conflict:

1. **Verbatim fidelity for paper-specific claims.** Titles, method names, benchmark names, author names, and quantitative results (percentages, dollar amounts, counts) must match the source record exactly. Do not round numbers (e.g., 95.83% must not become 96%). Do not substitute synonyms for technical terms.

2. **Use official names.** Organizations, products, institutes, and initiatives must use their official names as they appear in the source record. Do not paraphrase or shorten (e.g., "The Anthropic Institute" must not become "safety institute").

3. **Date window enforcement.** Every signal on a lever slide must have a `published` or `collected_at` date that falls within the reporting window. If a signal's underlying event predates the window by more than 30 days, exclude it and select the next-highest-scored signal for that lever.

4. **Source attribution integrity.** The `source_name` displayed on each signal card must match the original source. Do not upgrade a Reddit thread to a news outlet, or attribute an ArXiv paper to the organization that authored it unless the source record explicitly uses that attribution.

5. **No composite claims.** Each signal card must correspond to exactly one source record. Do not merge findings from multiple papers or news items into a single signal card.

### Cover Slide (Slide 1)

The cover is a navy slide with two sections separated by a divider: brand identity at top, then the period's data below.

**Brand section** (static content, do not modify):
- **Wordmark**: Large `espresso·ai` at 56px
- **Tagline**: `AI news. Concentrated.`
- **Description**: Semi-static text describing the multi-agent pipeline and Scale Levers framework (see template spec for exact text; update when active collectors change)
- **Curator credit**: `Curated by Tommaso Babucci`

**This Period section** (dynamic content — adapt based on cadence):
- **Nav right text**: Use the cadence-specific value from the Cadence Configuration table
- **Issue badge**: `Issue {N}` — use the issue number provided by the user, or increment from the last issue
- **Date eyebrow**: Use the cadence-specific format from the Cadence Configuration table
- **Headline**: 3 short declarative phrases, each on its own line. Max 60 chars total. Capture the period's dominant tensions. Examples: "Models compress. / Capital concentrates. / Governance fragments."
- **Stat cards**: Use actual numbers from `meta.total_signals_loaded`, `meta.source_files` count, and always 6 for scale levers.
- **Lever dashboard** (compact, no per-lever summaries): For each of the 6 levers:
  - Use the lever's `dominant_direction` for the direction badge
  - Use `signal_count` for the count
  - Use the lever scope title from the spec (e.g., "Chips, Fabs, Data Centers, Supply Chain" for COMPUTE)

### Lever Slides (Slides 2-7)

For each lever, write:
- **Editorial title (H2)**: 10-15 words. Declarative. Captures the lever's story for this period.
- **Lever description**: 1-2 sentences contextualizing the lever with data. Max 200 chars.
- **Stats row**: Total signal count + all non-zero direction counts (ordered: positive, negative, neutral, ambiguous). Show every direction that has at least 1 signal.
- **Signal depth line**: If `unselected_count` > 0, write a signal depth paragraph. Start with `+{N} more signals tracked this {period}.` followed by 2-3 sentences that editorially summarize themes and notable events from `unselected_context`. Reference specific companies, products, or findings. Max 300 characters. Follow espresso voice rules.
- **Signal cards (6-7)**: For each selected signal:
  - **Headline**: Rewrite the raw `title` in espresso voice. Max 80 chars. Declarative, insight-first.
  - **Summary**: Rewrite the raw `summary`. Max 180 chars. Explain what the signal means, not just what happened.
  - **Source**: Use the signal's `source_name` field.
  - **Tag**: Use the signal's `sub_variable` field.

## Step 8: Generate HTML

Using the template spec as your structural guide:

1. Copy the complete CSS from the template spec (all variables, classes, print rules)
2. Build each of the 8 slides following the exact HTML structure documented in the spec
3. Apply:
   - Cover slide (slide 1) has navy background
   - Lever slides alternate white/cream backgrounds (2=W, 3=C, 4=W, 5=C, 6=W, 7=C)
   - About slide (slide 8) has navy background with brand identity, levers grid, and author
   - Correct direction badge CSS classes (`+`→`dir-pos`, `-`→`dir-neg`, `~`→`dir-neu`, `?`→`dir-amb`)
   - Correct page numbers (1/8 through 8/8)
   - Escape `&` as `&amp;` in all HTML content
   - Use `−` (minus sign entity) for negative direction badges, not a hyphen
   - Include source attribution (`<span class="signal-source">`) on every signal card
   - Use `cover-period` as the class name for the period section (not `cover-week`)
   - Use cadence-specific nav right text from the Cadence Configuration table
   - Use cadence-specific date eyebrow format from the Cadence Configuration table
4. Include Google Fonts `<link>` in `<head>`
5. Include `@media print` and `@page` rules

**Reference template**: `brand_assets/linkedin_templates/weekly_carousel_template.html` — compare your output to this for visual fidelity (note: the reference shows a weekly example; adapt cover content per the Cadence Configuration table).

## Step 9: Write Output

Write the HTML carousel to: `PR/{CADENCE}/{YYYY-MM-DD}_{CADENCE}_carousel.html`

Use `end_date` as the `YYYY-MM-DD` in the filename.

Also write a synthesis log to `research_db/processed/{start}_{end}_{cadence}_synthesis_log.json` containing:
```json
{
  "pipeline_run_id": "{from carousel_data.meta}",
  "cadence": "{CADENCE}",
  "date_window": {"start": "{start}", "end": "{end}"},
  "generated_at": "{ISO timestamp}",
  "total_signals_loaded": N,
  "duplicates_removed": N,
  "unique_signals": N,
  "signals_selected": N,
  "output_file": "PR/{CADENCE}/{date}_{CADENCE}_carousel.html",
  "editorial_decisions": {
    "headline": "{the 3-phrase headline you wrote}",
    "signals_per_lever": {
      "COMPUTE": ["{titles of selected signals}"],
      "ENERGY": ["..."],
      ...
    }
  }
}
```

## Step 10: Post-Run Summary

Present to the user:
- Cadence and date window used
- Total signals processed and unique count
- Duplicates removed
- Selected signals per lever (titles only, in a table)
- Output file path
- Instruction: "Open the HTML in a browser to review. Print to PDF at 1080x1080px custom size for LinkedIn upload."

## Pre-Output Checklist

Before writing the final HTML, verify:
- [ ] Exactly 8 slides in correct order (1 cover + 6 lever + 1 about)
- [ ] Cover is navy with brand identity section (wordmark, tagline, description, curator) then period section (issue badge, date, headline, stats, dashboard)
- [ ] Cover nav right text matches the cadence from the Cadence Configuration table
- [ ] Cover date eyebrow uses the correct cadence-specific format
- [ ] Cover period section uses class `cover-period`
- [ ] Lever slides alternate white/cream backgrounds (2=W, 3=C, 4=W, 5=C, 6=W, 7=C)
- [ ] Lever stats row shows all non-zero direction counts (positive, negative, neutral, ambiguous)
- [ ] Signal depth line present on each lever slide with unselected_count > 0
- [ ] About slide (slide 8) is navy with brand identity, levers grid, and author
- [ ] All page numbers correct (1/8 through 8/8)
- [ ] 6-7 signal cards per lever slide
- [ ] Every signal card includes source attribution
- [ ] No AI writing giveaways in any editorial text
- [ ] All `&` escaped as `&amp;`
- [ ] Direction badge classes match signal direction values
- [ ] Print CSS rules included
- [ ] Google Fonts link in `<head>`
- [ ] Stat cards use actual data from intermediate JSON
- [ ] No watermarks on any slide
- [ ] All quantitative claims (percentages, dollar amounts, counts) match source records exactly — no rounding
- [ ] All organization/product/institute names use official names from source records
- [ ] Every signal's underlying event falls within the reporting window (or within 30 days before it)
- [ ] No signal card merges findings from multiple source records
