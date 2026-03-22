# espresso·ai — Carousel Template Specification

> **For Claude Code:** This is the authoritative specification for generating LinkedIn carousel HTML files for any cadence. Follow every rule exactly. When in doubt, match the reference template at `brand_assets/linkedin_templates/weekly_carousel_template.html` (which shows a weekly example — adapt cover content per the Cadence Configuration table below).

---

## Overview

The carousel is an 8-slide HTML document sized at **1080 x 1350px per slide** (portrait LinkedIn carousel format). It synthesizes AI signals for a given cadence period into an editorial brief organized by the six Scale Levers.

- **Slide 1**: Navy cover with headline, stats, lever dashboard, and about section
- **Slides 2–7**: One lever per slide with 6–7 signal cards each
- **Slide 8**: Navy about page with brand identity, Scale Levers framework, and author

**Output path:** `PR/{cadence}/{YYYY-MM-DD}_{cadence}_carousel.html`

---

## Cadence Configuration

The cover slide adapts its text based on cadence. All other slides are identical across cadences.

| Cadence | Nav Right Text | Date Eyebrow Format | Section Label |
|---|---|---|---|
| daily | `A strong sip of today's AI news` | `{Month} {DD}, {YYYY}` | `Today` |
| weekly | `A strong sip of this week's AI news` | `Week of {Month} {DD}–{DD}, {YYYY}` | `This Week` |
| monthly | `A strong sip of this month's AI news` | `{Month} {YYYY}` | `This Month` |
| quarterly | `A strong sip of this quarter's AI news` | `Q{N} {YYYY}` | `This Quarter` |
| annual | `A strong sip of this year's AI news` | `{YYYY}` | `This Year` |

**Quarterly eyebrow logic:** If start_date is in Jan–Mar → Q1, Apr–Jun → Q2, Jul–Sep → Q3, Oct–Dec → Q4.

---

## Slide Sequence

| # | Slide Type | Background | Nav Right Label |
|---|---|---|---|
| 1 | Cover | Navy (`#162B4E`) | `{NAV_RIGHT_TEXT}` (see Cadence Configuration) |
| 2 | COMPUTE | White (`#FFFFFF`) | `Scale Lever 1 of 6` |
| 3 | ENERGY | Cream (`#FAF9F7`) | `Scale Lever 2 of 6` |
| 4 | SOCIETY | White | `Scale Lever 3 of 6` |
| 5 | INDUSTRY | Cream | `Scale Lever 4 of 6` |
| 6 | CAPITAL | White | `Scale Lever 5 of 6` |
| 7 | GOV | Cream | `Scale Lever 6 of 6` |
| 8 | About | Navy (`#162B4E`) | `About` |

---

## CSS Variables & Fonts

Every carousel HTML file must include these exact CSS custom properties and font imports:

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400;1,600&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet" />
```

```css
:root {
  --navy:       #162B4E;
  --navy-mid:   #1E3A65;
  --red:        #BF3A2B;
  --red-light:  #D94E3C;
  --white:      #FFFFFF;
  --cream:      #FAF9F7;
  --gray-100:   #F4F3F1;
  --gray-200:   #E8E6E3;
  --gray-400:   #A09D99;
  --gray-600:   #6B6760;
  --ink:        #111827;

  --serif: 'Playfair Display', Georgia, serif;
  --sans:  'Inter', -apple-system, sans-serif;

  --slide-w: 1080px;
  --slide-h: 1350px;
}
```

---

## Shared Structural Elements

### Slide Container

Every slide uses this base structure:

```html
<div class="slide {slide-type-class}">
  <div class="slide-nav">
    <div class="slide-nav-logo">espresso<span class="dot">·</span>ai</div>
    <div class="slide-nav-right">{NAV_RIGHT_LABEL}</div>
  </div>
  <div class="slide-content">
    <!-- Slide-specific content here -->
  </div>
  <div class="slide-footer">
    <div class="slide-footer-left">espresso·ai</div>
    <div class="slide-footer-right">{N} / 8</div>
  </div>
</div>
```

**Slide type classes:** `slide-title` (cover), `slide-lever` (lever slides), `slide-navy` (about)

For cream-background slides, add inline style: `style="background: var(--cream);"`

### Nav Bar (52px)

- Fixed top, 56px horizontal padding
- Left: `espresso·ai` wordmark (Playfair Display, 16px, weight 600, navy; dot in red)
- Right: section label (Inter, 13px, weight 500, uppercase, 0.08em tracking, gray-400)
- Bottom border: 1px solid `--gray-200` (or `rgba(255,255,255,0.08)` on navy cover)

### Footer (44px)

- Fixed bottom, 56px horizontal padding
- Left: `espresso·ai` (13px, weight 500, gray-400)
- Right: page number `{N} / 8` (13px, weight 600, gray-400)
- Top border: 1px solid `--gray-200` (or `rgba(255,255,255,0.08)` on navy cover)
- On navy cover: both left and right text use `rgba(255,255,255,0.3)`

---

## Slide 1 — Cover (Navy)

**Class:** `slide-title`
**Background:** Navy (`#162B4E`)

The cover slide has two sections separated by a horizontal divider:
1. **Brand identity** (top) — large wordmark, tagline, description of espresso·ai, curator credit
2. **This Period section** (bottom) — issue badge + date eyebrow, editorial headline, stat cards, compact lever dashboard. The section label and date eyebrow are cadence-dependent (see Cadence Configuration table).

### Structure

```html
<div class="slide slide-title">
  <div class="slide-nav">
    <div class="slide-nav-logo">espresso<span class="dot">·</span>ai</div>
    <div class="slide-nav-right">{NAV_RIGHT_TEXT}</div>
  </div>
  <div class="slide-content">
    <div class="title-inner">
      <!-- Brand identity section -->
      <div class="cover-brand">
        <div class="cover-wordmark">espresso<span class="dot">·</span>ai</div>
        <div class="cover-tagline">AI news. Concentrated.</div>
        <div class="cover-desc">A multi-agent intelligence pipeline that collects signals from research papers, news, regulatory filings, corporate disclosures, open-source releases, energy data, social media, and 71 key influencers. Every signal is classified against six structural levers that determine whether AI reaches transformational scale or stalls before it gets there.</div>
        <div class="cover-curated">Curated by Tommaso Babucci</div>
      </div>

      <!-- This period section -->
      <div class="cover-period">
        <div class="cover-issue-row">
          <span class="cover-issue-badge">Issue {N}</span>
          <div class="eyebrow" style="color: var(--red-light);">{DATE_EYEBROW}</div>
        </div>
        <div class="title-rule"></div>
        <h1 class="title-headline">{LINE_1}<br/>{LINE_2}<br/>{LINE_3}</h1>
        <div class="title-stats">
          <div class="stat-card">
            <div class="stat-num">{TOTAL_SIGNALS}</div>
            <div class="stat-label">Signals collected</div>
          </div>
          <div class="stat-card">
            <div class="stat-num">{SOURCE_COUNT}</div>
            <div class="stat-label">Source pipelines</div>
          </div>
          <div class="stat-card">
            <div class="stat-num">6</div>
            <div class="stat-label">Scale levers</div>
          </div>
        </div>
        <div class="dashboard-grid">
          <!-- 6 lever items (2-column grid) — code + direction + count + scope title only -->
          <div class="dashboard-item">
            <div class="dashboard-header">
              <span class="dashboard-lever-code">{LEVER_CODE}</span>
              <span class="dashboard-dir dir-{TYPE}">{SYMBOL}</span>
              <span class="dashboard-count">{N} signals</span>
            </div>
            <div class="dashboard-lever-name">{LEVER_SCOPE_TITLE}</div>
          </div>
          <!-- repeat for all 6 levers -->
        </div>
      </div>
    </div>
  </div>
  <div class="slide-footer">
    <div class="slide-footer-left">espresso·ai</div>
    <div class="slide-footer-right">1 / 8</div>
  </div>
</div>
```

### Cover Content Slots

| Slot | Type | Constraints |
|---|---|---|
| Wordmark | Text | Static: `espresso·ai` at 56px Playfair Display |
| Tagline | Text | Static: `AI news. Concentrated.` |
| Description | Paragraph | Semi-static. Describes the multi-agent pipeline and Scale Levers framework. Update when active collectors materially change. |
| Curator credit | Text | Static: `Curated by Tommaso Babucci` |
| Issue badge | Badge | Format: `Issue {N}` — red background, white text |
| Date eyebrow | Text | Cadence-dependent format (see Cadence Configuration table) |
| Headline | 3 lines | 3 short declarative phrases via `<br/>`. Max 60 chars total. Capture dominant tensions. |
| Stat cards | 3 cards | Total signals, source pipeline count, always 6 for scale levers. |
| Dashboard items (x6) | 2-col grid | Lever code + direction badge + signal count + scope title. No per-lever summaries. |

### Cover Brand Text (Static)

**Description:**
> A multi-agent intelligence pipeline that collects signals from research papers, news, regulatory filings, corporate disclosures, open-source releases, energy data, social media, and 71 key influencers. Every signal is classified against six structural levers that determine whether AI reaches transformational scale or stalls before it gets there.

### Cover Lever Scope Titles

Each lever in the dashboard includes an expanded scope title:

| Code | Scope Title |
|---|---|
| COMPUTE | Chips, Fabs, Data Centers, Supply Chain |
| ENERGY | Power Demand, Grid, Renewables, Cooling |
| SOCIETY | Adoption, Talent, Workforce, Trust |
| INDUSTRY | Enterprise ROI, Deployments, Business Models |
| CAPITAL | VC, Hyperscaler Capex, Valuations, ROI |
| GOV | Regulation, Export Controls, Safety, Geopolitics |

### Cover Typography

| Element | Font | Size | Weight | Color |
|---|---|---|---|---|
| Nav logo | Playfair Display | 16px | 600 | white (dot: red-light) |
| Nav right | Inter | 13px | 500 | rgba(255,255,255,0.35), uppercase |
| Wordmark | Playfair Display | 56px | 700 | white (dot: red-light), -0.03em tracking |
| Tagline | Inter | 16px | 500 | rgba(255,255,255,0.4), uppercase, 0.06em tracking |
| Description | Playfair Display | 18px | 400 | rgba(255,255,255,0.6), line-height 1.55 |
| Curator credit | Inter | 13px | 600 | red-light, uppercase, 0.06em tracking |
| Issue badge | Inter | 12px | 700 | white on red-light bg, uppercase, 0.1em tracking, 4px 12px padding |
| Date eyebrow | Inter | 14px | 600 | red-light, uppercase, 0.12em tracking |
| Title rule | — | 56px wide, 3px tall | — | red-light |
| Headline | Playfair Display | 44px | 700 | white, line-height 1.1, -0.025em tracking |
| Stat number | Playfair Display | 32px | 700 | white |
| Stat label | Inter | 13px | 600 | rgba(255,255,255,0.35), uppercase, 0.06em tracking |
| Lever code badge | SF Mono / Fira Code | 11px | 600 | red-light, bg: rgba(217,78,60,0.12), 3px 8px padding |
| Direction badge | — | 12px | 700 | 20px circle (see direction badges) |
| Signal count | Inter | 14px | 500 | rgba(255,255,255,0.4) |
| Lever scope name | Inter | 16px | 600 | rgba(255,255,255,0.75) |
| Footer | Inter | 13px | 500/600 | rgba(255,255,255,0.3) |

### Cover CSS

```css
.slide-title {
  background: var(--navy);
  color: var(--white);
}
.slide-title .slide-nav {
  border-bottom-color: rgba(255,255,255,0.08);
}
.slide-title .slide-nav-logo { color: var(--white); }
.slide-title .slide-nav-logo .dot { color: var(--red-light); }
.slide-title .slide-nav-right { color: rgba(255,255,255,0.35); }
.slide-title .slide-footer {
  border-top-color: rgba(255,255,255,0.08);
}
.slide-title .slide-footer-left { color: rgba(255,255,255,0.3); }
.slide-title .slide-footer-right { color: rgba(255,255,255,0.3); }

.title-inner {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding-top: 16px;
}
.title-rule {
  width: 56px;
  height: 3px;
  background: var(--red-light);
  margin-bottom: 18px;
}
.title-headline {
  font-family: var(--serif);
  font-size: 44px;
  font-weight: 700;
  color: var(--white);
  line-height: 1.1;
  letter-spacing: -0.025em;
  margin-bottom: 24px;
}

/* Stats row */
.title-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 24px;
}
.stat-card {
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.1);
  padding: 16px 20px;
  border-radius: 2px;
}
.stat-num {
  font-family: var(--serif);
  font-size: 32px;
  font-weight: 700;
  color: var(--white);
  line-height: 1;
  margin-bottom: 4px;
}
.stat-label {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(255,255,255,0.35);
}

/* Lever dashboard */
.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 36px;
}
.dashboard-item {
  padding: 10px 0;
}
.dashboard-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 3px;
}
.dashboard-lever-code {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--red-light);
  background: rgba(217,78,60,0.12);
  padding: 3px 8px;
  border-radius: 2px;
}
.dashboard-dir {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
}
.dashboard-count {
  font-size: 14px;
  font-weight: 500;
  color: rgba(255,255,255,0.4);
}
.dashboard-lever-name {
  font-size: 16px;
  font-weight: 600;
  color: rgba(255,255,255,0.75);
  margin-bottom: 2px;
}

/* Brand hero section (top of cover) */
.cover-brand {
  display: flex;
  flex-direction: column;
  padding-bottom: 28px;
  border-bottom: 1px solid rgba(255,255,255,0.1);
  margin-bottom: 28px;
}
.cover-wordmark {
  font-family: var(--serif);
  font-size: 56px;
  font-weight: 700;
  color: var(--white);
  letter-spacing: -0.03em;
  line-height: 1;
  margin-bottom: 8px;
}
.cover-wordmark .dot { color: var(--red-light); }
.cover-tagline {
  font-family: var(--sans);
  font-size: 16px;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(255,255,255,0.4);
  margin-bottom: 20px;
}
.cover-desc {
  font-family: var(--serif);
  font-size: 18px;
  font-weight: 400;
  color: rgba(255,255,255,0.6);
  line-height: 1.55;
  max-width: 920px;
}
.cover-curated {
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
  color: var(--red-light);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-top: 14px;
}

/* Period section (cadence-dependent content) */
.cover-period {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.cover-issue-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 14px;
}
.cover-issue-badge {
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--white);
  background: var(--red-light);
  padding: 4px 12px;
  border-radius: 2px;
}
```

---

## Slides 2–7 — Scale Lever Slides

**Class:** `slide-lever`

### Structure

```html
<div class="slide slide-lever" style="background: var(--white|--cream);">
  <div class="lever-accent"></div>
  <div class="slide-nav">
    <div class="slide-nav-logo">espresso<span class="dot">·</span>ai</div>
    <div class="slide-nav-right">Scale Lever {N} of 6</div>
  </div>
  <div class="slide-content">
    <div class="lever-header">
      <div class="lever-code">{LEVER_CODE} — {LEVER_FULL_NAME}</div>
      <h2 class="lever-title">{EDITORIAL_TITLE}</h2>
      <p class="lever-subtitle">{LEVER_DESCRIPTION}</p>
    </div>
    <div class="lever-stats-row">
      <div class="lever-stat">
        <div class="lever-stat-num">{SIGNAL_COUNT}</div>
        <div class="lever-stat-label">Signals</div>
      </div>
      <!-- Include one lever-stat for EACH direction with count > 0, ordered: pos, neg, neu, amb -->
      <div class="lever-stat">
        <span class="lever-stat-dir dir-{TYPE}">{SYMBOL}</span>
        <div class="lever-stat-label">{N} {direction_label}</div>
      </div>
      <!-- repeat for each non-zero direction -->
    </div>
    <div class="lever-divider"></div>
    <div class="signal-list">
      <!-- 6-7 signal cards -->
      <div class="signal-item">
        <span class="signal-dir dir-{TYPE}">{SYMBOL}</span>
        <div class="signal-body">
          <div class="signal-headline">{HEADLINE}</div>
          <div class="signal-summary">{SUMMARY}</div>
          <div class="signal-meta">
            <span class="signal-source">{SOURCE_NAME}</span>
            <span class="signal-tag">{TAG}</span>
          </div>
        </div>
      </div>
      <!-- repeat for each signal -->
    </div>
    <!-- Signal depth line — only if unselected_count > 0 -->
    <div class="signal-depth-line">+{N} more signals tracked this {period}. {2-3 sentences summarizing themes from unselected_context. Max 300 characters.}</div>
  </div>
  <div class="slide-footer">
    <div class="slide-footer-left">espresso·ai</div>
    <div class="slide-footer-right">{N} / 8</div>
  </div>
</div>
```

### Lever Full Names

| Code | Full Name |
|---|---|
| COMPUTE | Compute &amp; Infrastructure |
| ENERGY | Energy &amp; Environment |
| SOCIETY | Society &amp; Human Capital |
| INDUSTRY | Industry &amp; Business Transformation |
| CAPITAL | Capital &amp; Investment |
| GOV | Governance &amp; Geopolitics |

### Lever Slide Backgrounds

| Slide | Lever | Background |
|---|---|---|
| 2 | COMPUTE | White |
| 3 | ENERGY | Cream |
| 4 | SOCIETY | White |
| 5 | INDUSTRY | Cream |
| 6 | CAPITAL | White |
| 7 | GOV | Cream |

### Content Slots

| Slot | Type | Constraints |
|---|---|---|
| Lever code line | Text | Format: `{CODE} — {Full Name}` (use `&amp;` for ampersand in HTML) |
| Editorial title | H2 | 10-15 words. Declarative. Captures the lever's story for this period. |
| Lever description | Paragraph | 1-2 sentences. Contextualizes the lever with data. Max 200 chars. |
| Stats row | 2-5 items | Total signal count + all non-zero direction counts (ordered: positive, negative, neutral, ambiguous) |
| Signal cards | 6-7 items | Direction badge + headline + summary + source + 1 tag |
| Signal depth line | Text | Editorial paragraph. Start with `+{N} more signals tracked this {period}.` followed by 2-3 sentences summarizing themes from `unselected_context`. Max 300 characters. Only if N > 0. |

### Signal Card Content

| Field | Constraints |
|---|---|
| Headline | Max 80 chars. Rewrite from raw signal title in espresso voice. Declarative, insight-first. |
| Summary | Max 180 chars. 1-2 sentences. Explain what the signal means, not just what happened. |
| Source | The signal's `source_name` field (e.g., "Bloomberg", "ArXiv", "Reddit r/LocalLLaMA", "X @naval"). |
| Tag | 1 tag from the signal's `sub_variable` field. Lowercase, underscores. |

### Lever Slide Typography

| Element | Font | Size | Weight | Color |
|---|---|---|---|---|
| Nav logo | Playfair Display | 16px | 600 | navy (dot: red) |
| Nav right | Inter | 13px | 500 | gray-400, uppercase, 0.08em tracking |
| Lever code | Inter | 13px | 700 | red, uppercase, 0.12em tracking |
| Lever title (H2) | Playfair Display | 34px | 700 | navy, line-height 1.15, -0.02em tracking |
| Lever subtitle | Inter | 16px | 400 | gray-600, line-height 1.5 |
| Stat number | Playfair Display | 28px | 700 | navy |
| Stat label | Inter | 14px | 500 | gray-400, uppercase, 0.04em tracking, line-height 1 |
| Stat direction badge | — | 14px | 700 | 24px circle (see direction badges) |
| Signal headline | Playfair Display | 17px | 600 | navy, line-height 1.3 |
| Signal summary | Inter | 15px | 400 | gray-600, line-height 1.45 |
| Signal source | Inter | 13px | 600 | navy, opacity 0.5 |
| Signal tag | Inter | 12px | 500 | gray-400, uppercase, 0.04em tracking |
| Signal depth line | Inter | 13px | 400 | gray-600, line-height 1.5 |
| Footer | Inter | 13px | 500/600 | gray-400 |

### Lever Slide CSS

```css
.slide-lever .slide-content {
  padding-top: 64px;
}
.lever-header {
  margin-bottom: 20px;
}
.lever-code {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--red);
  margin-bottom: 10px;
}
.lever-title {
  font-family: var(--serif);
  font-size: 34px;
  font-weight: 700;
  color: var(--navy);
  letter-spacing: -0.02em;
  line-height: 1.15;
  margin-bottom: 10px;
}
.lever-subtitle {
  font-size: 16px;
  color: var(--gray-600);
  line-height: 1.5;
}
.lever-stats-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px 24px;
  margin-bottom: 20px;
}
.lever-stat {
  display: flex;
  align-items: center;
  gap: 8px;
}
.lever-stat-num {
  font-family: var(--serif);
  font-size: 28px;
  font-weight: 700;
  color: var(--navy);
  line-height: 1;
}
.lever-stat-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--gray-400);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  line-height: 1;
}
.lever-stat-dir {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  font-size: 14px;
  font-weight: 700;
}
.lever-divider {
  width: 100%;
  height: 1px;
  background: var(--gray-200);
  margin-bottom: 16px;
}
.lever-accent {
  position: absolute;
  top: 52px; left: 0;
  width: 4px;
  height: 80px;
  background: var(--red);
}
```

### Signal Card CSS

```css
.signal-list {
  display: flex;
  flex-direction: column;
}
.signal-item {
  padding: 12px 0;
  border-bottom: 1px solid var(--gray-100);
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.signal-item:last-child { border-bottom: none; }
.signal-dir {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  font-size: 15px;
  font-weight: 700;
  flex-shrink: 0;
  margin-top: 2px;
}
.signal-body { flex: 1; }
.signal-headline {
  font-family: var(--serif);
  font-size: 17px;
  font-weight: 600;
  color: var(--navy);
  line-height: 1.3;
  margin-bottom: 4px;
}
.signal-summary {
  font-size: 15px;
  color: var(--gray-600);
  line-height: 1.45;
  margin-bottom: 5px;
}
.signal-meta {
  display: flex;
  gap: 16px;
  align-items: center;
}
.signal-source {
  font-size: 13px;
  font-weight: 600;
  color: var(--navy);
  opacity: 0.5;
}
.signal-tag {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--gray-400);
}

/* Signal depth line */
.signal-depth-line {
  font-size: 13px;
  font-weight: 400;
  color: var(--gray-600);
  line-height: 1.5;
  padding-top: 14px;
  margin-top: 0;
  border-top: 1px solid var(--gray-100);
}
```

---

## Slide 8 — About (Navy)

**Class:** `slide-navy`
**Background:** Navy (`#162B4E`)

The about slide closes the carousel with brand identity, the Scale Levers framework, and author information.

### Structure

```html
<div class="slide slide-navy">
  <div class="slide-nav">
    <div class="slide-nav-logo">espresso<span class="dot">·</span>ai</div>
    <div class="slide-nav-right">About</div>
  </div>
  <div class="slide-content">
    <div style="padding-top: 28px;"></div>
    <div class="about-logo">espresso<span class="dot">·</span>ai</div>
    <div class="about-tagline">AI news. Concentrated.</div>
    <div class="about-rule"></div>
    <p class="about-desc">espresso·ai is an AI news agent that delivers concentrated, high-signal intelligence on artificial intelligence developments and long-term trends. Every signal is classified against six structural Scale Levers to answer one question: is AI accelerating toward transformational scale, or stalling before it gets there?</p>

    <div class="about-levers-label">The Scale Levers Framework</div>
    <div class="about-levers-grid">
      <div class="about-lever-item">
        <span class="about-lever-code">COMPUTE</span>
        <span class="about-lever-name">Compute &amp; Infrastructure</span>
      </div>
      <div class="about-lever-item">
        <span class="about-lever-code">ENERGY</span>
        <span class="about-lever-name">Energy &amp; Environment</span>
      </div>
      <div class="about-lever-item">
        <span class="about-lever-code">SOCIETY</span>
        <span class="about-lever-name">Society &amp; Human Capital</span>
      </div>
      <div class="about-lever-item">
        <span class="about-lever-code">INDUSTRY</span>
        <span class="about-lever-name">Industry &amp; Business</span>
      </div>
      <div class="about-lever-item">
        <span class="about-lever-code">CAPITAL</span>
        <span class="about-lever-name">Capital &amp; Investment</span>
      </div>
      <div class="about-lever-item">
        <span class="about-lever-code">GOV</span>
        <span class="about-lever-name">Governance &amp; Geopolitics</span>
      </div>
    </div>

    <div class="about-author">
      <div class="about-author-info">
        <div class="about-author-name">Curated By Tommaso Babucci</div>
        <div class="about-author-role">AI Strategy &amp; Development Lead</div>
        <div class="about-cta">espresso·ai</div>
      </div>
    </div>
  </div>
  <div class="slide-footer">
    <div class="slide-footer-left">Dense signal. Zero noise.</div>
    <div class="slide-footer-right">8 / 8</div>
  </div>
</div>
```

### About Content Slots

| Slot | Type | Constraints |
|---|---|---|
| Wordmark | Text | `espresso·ai` at 48px Playfair Display, white |
| Tagline | Text | `AI news. Concentrated.` italic, 20px |
| Divider rule | Decorative | 48px wide, 2px tall, red-light |
| Description | Paragraph | Explains espresso·ai and the Scale Levers question. Semi-static. |
| Levers label | Text | `The Scale Levers Framework` |
| Levers grid | 2×3 grid | Lever code badges + full names for all 6 levers |
| Author name | Text | `Curated By Tommaso Babucci` |
| Author role | Text | `AI Strategy & Development Lead` |
| CTA | Text | `espresso·ai` |

### About Typography

| Element | Font | Size | Weight | Color |
|---|---|---|---|---|
| Nav logo | Playfair Display | 16px | 600 | white (dot: red-light) |
| Nav right | Inter | 13px | 500 | rgba(255,255,255,0.35), uppercase |
| Wordmark | Playfair Display | 48px | 700 | white (dot: red-light) |
| Tagline | Playfair Display | 20px | 400 | rgba(255,255,255,0.5), italic |
| Divider rule | — | 48px wide, 2px tall | — | red-light |
| Description | Inter | 16px | 400 | rgba(255,255,255,0.55), line-height 1.65 |
| Levers label | Inter | 13px | 700 | red-light, uppercase, 0.1em tracking |
| Lever code badge | SF Mono / Fira Code | 11px | 600 | red-light, bg: rgba(217,78,60,0.15), 3px 8px padding |
| Lever name | Inter | 15px | 500 | rgba(255,255,255,0.7) |
| Author name | Playfair Display | 22px | 700 | white |
| Author role | Inter | 14px | 500 | rgba(255,255,255,0.5) |
| CTA | Inter | 14px | 600 | red-light |
| Footer left | Inter | 13px | 500 | rgba(255,255,255,0.3) |
| Footer right | Inter | 13px | 600 | rgba(255,255,255,0.3) |

### About CSS

```css
.slide-navy {
  background: var(--navy);
  color: var(--white);
}
.slide-navy .slide-nav {
  border-bottom-color: rgba(255,255,255,0.08);
}
.slide-navy .slide-nav-logo { color: var(--white); }
.slide-navy .slide-nav-logo .dot { color: var(--red-light); }
.slide-navy .slide-nav-right { color: rgba(255,255,255,0.35); }
.slide-navy .slide-footer {
  border-top-color: rgba(255,255,255,0.08);
}
.slide-navy .slide-footer-left { color: rgba(255,255,255,0.3); }
.slide-navy .slide-footer-right { color: rgba(255,255,255,0.3); }

.about-logo {
  font-family: var(--serif);
  font-size: 48px;
  font-weight: 700;
  color: var(--white);
  letter-spacing: -0.03em;
  line-height: 1;
  margin-bottom: 8px;
}
.about-logo .dot { color: var(--red-light); }
.about-tagline {
  font-family: var(--serif);
  font-size: 20px;
  font-weight: 400;
  font-style: italic;
  color: rgba(255,255,255,0.5);
  margin-bottom: 24px;
}
.about-rule {
  width: 48px;
  height: 2px;
  background: var(--red-light);
  margin-bottom: 24px;
}
.about-desc {
  font-family: var(--sans);
  font-size: 16px;
  font-weight: 400;
  color: rgba(255,255,255,0.55);
  line-height: 1.65;
  margin-bottom: 32px;
}
.about-levers-label {
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--red-light);
  margin-bottom: 16px;
}
.about-levers-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 36px;
  margin-bottom: 36px;
}
.about-lever-item {
  display: flex;
  align-items: center;
  gap: 10px;
}
.about-lever-code {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--red-light);
  background: rgba(217,78,60,0.15);
  padding: 3px 8px;
  border-radius: 2px;
}
.about-lever-name {
  font-family: var(--sans);
  font-size: 15px;
  font-weight: 500;
  color: rgba(255,255,255,0.7);
}
.about-author {
  margin-top: auto;
}
.about-author-name {
  font-family: var(--serif);
  font-size: 22px;
  font-weight: 700;
  color: var(--white);
  margin-bottom: 4px;
}
.about-author-role {
  font-family: var(--sans);
  font-size: 14px;
  font-weight: 500;
  color: rgba(255,255,255,0.5);
  margin-bottom: 12px;
}
.about-cta {
  font-family: var(--sans);
  font-size: 14px;
  font-weight: 600;
  color: var(--red-light);
}
```

---

## Direction Badges

Used in stats rows, signal cards, and the cover dashboard. Map the signal's `direction` field to CSS class:

| Direction | Symbol | CSS Class | Background | Text Color |
|---|---|---|---|---|
| `+` (positive) | `+` | `dir-pos` | `#E8F5E9` | `#2E7D32` |
| `-` (negative) | `−` | `dir-neg` | `#FFEBEE` | `#C62828` |
| `~` (neutral) | `~` | `dir-neu` | `var(--gray-100)` | `var(--gray-600)` |
| `?` (ambiguous) | `?` | `dir-amb` | `#FFF8E1` | `#F57F17` |

**Note:** Use the HTML minus sign `−` (or `&minus;`) for negative, not a hyphen.

```css
.dir-pos { background: #E8F5E9; color: #2E7D32; }
.dir-neg { background: #FFEBEE; color: #C62828; }
.dir-neu { background: var(--gray-100); color: var(--gray-600); }
.dir-amb { background: #FFF8E1; color: #F57F17; }
```

---

## Stats Row Rules

The stats row shows the total signal count plus **every direction that has at least 1 signal**, ordered: positive, negative, neutral, ambiguous. This ensures negative signals are always visible when present.

Example:

- If a lever has 172 signals: 142 positive, 4 negative, 2 neutral, 24 ambiguous
- Stats row shows: `172 Signals` | `+ 142 positive` | `− 4 negative` | `~ 2 neutral` | `? 24 ambiguous`

---

## Print & PDF Rules

These CSS rules must be included in every carousel for correct PDF export (Chrome Print → PDF, custom size 1080x1350px):

```css
@media print {
  body {
    background: none;
    gap: 0;
    padding: 0;
  }
  .slide {
    page-break-after: always;
    page-break-inside: avoid;
  }
  .slide:last-child {
    page-break-after: auto;
  }
}
@page {
  size: 1080px 1350px;
  margin: 0;
}
```

---

## Editorial Voice Rules (inline from BRAND.md)

All editorial text in the carousel must follow these rules:

### Do

- Lead with the insight, not the context
- Use declarative sentences; state what is true
- One strong sentence beats three weak ones
- Long-term perspective over daily churn
- Confident, precise, not pedantic
- Explain what signals mean for strategy, not just what happened

### Do Not

- Hype language: "game-changing," "revolutionary," "unprecedented"
- Hedging: "might," "could potentially," "seems to suggest"
- Filler: "In today's rapidly evolving AI landscape..."
- Em dashes as connectors (rewrite as two sentences)
- Lists of three ("X, Y, and Z")
- Transitional openers: "Additionally," "Furthermore," "Moreover"
- Meta-commentary: "It's worth noting..." "It's important to understand..."
- AI vocabulary: delve, tapestry, landscape (metaphor), paradigm shift, game-changer
- Rhetorical questions as hooks
- Summary bullets at the end
- Nested qualifiers ("not only... but also...")

### Voice Examples

**Lever title (good):** "The supply chain diversifies. The efficiency race accelerates."

**Lever title (bad):** "A Revolutionary Week for Compute Infrastructure and Innovation"

**Signal summary (good):** "Sub-year ROI on agentic deployments in regulated domains. When payback periods compress below annual budget cycles, the adoption flywheel becomes self-reinforcing."

**Signal summary (bad):** "This is a game-changing development that could potentially reshape the landscape of enterprise AI adoption."

---

## Checklist Before Output

Before writing the final HTML file, verify:

- [ ] Exactly 8 slides in correct order (1 cover + 6 lever + 1 about)
- [ ] Cover is navy with headline, stats, dashboard, and about section
- [ ] Cover nav right text matches the cadence from the Cadence Configuration table
- [ ] Cover date eyebrow uses the correct cadence-specific format
- [ ] Cover period section uses class `cover-period`
- [ ] Lever slides alternate white/cream (2=W, 3=C, 4=W, 5=C, 6=W, 7=C)
- [ ] All page numbers correct (1/8 through 8/8)
- [ ] 4-5 signal cards per lever slide (never fewer than 3, never more than 5)
- [ ] Each signal card includes source attribution
- [ ] Lever stats row shows all non-zero direction counts (positive, negative, neutral, ambiguous)
- [ ] Signal depth line present on each lever slide with unselected_count > 0
- [ ] About slide (slide 8) is navy with brand identity, levers grid, and author
- [ ] No AI writing giveaways in any editorial text
- [ ] All `&` characters escaped as `&amp;` in HTML
- [ ] Direction badge classes match signal direction values
- [ ] `−` (minus sign entity) used for negative badges, not hyphen
- [ ] Print CSS rules included
- [ ] Google Fonts link included in `<head>`
- [ ] Stat cards use actual data from intermediate JSON
- [ ] No watermarks on any slide

---

*espresso·ai Carousel Spec · v5.0 · March 2026*
