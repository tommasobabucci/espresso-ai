---
name: influencer-research
description: Collect AI signals from ~71 key influencers via parallel subagents with WebSearch, classify by Scale Lever, deduplicate, and write JSONL to research_db/raw/.
argument-hint: [daily|weekly|monthly|quarterly|annual] [--days-back N] [--group GROUP]
allowed-tools: Bash, Read, Agent, WebSearch, Write
---

# Influencer Research — Signal Collection

Collect AI signals from ~71 key AI influencers across 10 groups using parallel subagents with WebSearch.

## Arguments

**CADENCE** (required): `$ARGUMENTS[0]` — must be one of: `daily`, `weekly`, `monthly`, `quarterly`, `annual`.

**--days-back N** (optional): Override the default lookback window for the cadence.

**--group GROUP** (optional): Run only a specific group. Valid group names listed below.

## Step 1: Validate Arguments

Parse `$ARGUMENTS` to extract the cadence, optional `--days-back` value, and optional `--group` value.

- If no cadence is provided or `$ARGUMENTS` is empty, **stop** and ask the user:
  "Please specify a cadence: `/influencer-research daily|weekly|monthly|quarterly|annual`"
- If the cadence is not one of `daily`, `weekly`, `monthly`, `quarterly`, `annual`, **stop** and list valid options.
- If `--days-back` is present but its value is not a positive integer, **stop** and explain the error.
- If `--group` is present, validate it against the group names listed below.

## Step 2: Compute Date Window

Based on the cadence and today's date, compute the date window:

| Cadence | Lookback |
|---|---|
| daily | 1 day |
| weekly | 7 days |
| monthly | 31 days |
| quarterly | 92 days |
| annual | 366 days |

If `--days-back N` is specified, use N days instead.

Set `END_DATE` = today's date (YYYY-MM-DD) and `START_DATE` = END_DATE minus the lookback.

## Step 3: Launch Subagents

Launch **parallel subagents** using the Agent tool — one per influencer group (or just one if `--group` was specified). All agents should be launched in a **single message** with multiple Agent tool calls for maximum parallelism.

Each agent receives the **Subagent Prompt Template** (below), filled with:
- Its group's influencer list
- The computed START_DATE and END_DATE
- A unique `agent_id` per group

### Influencer Groups

#### Group 1: `ceo_industry_leaders` — CEOs & Industry Leaders (15 people)
| Name | Role | Primary Lever | Category |
|---|---|---|---|
| Sam Altman | CEO, OpenAI | INDUSTRY | ai_lab_leader |
| Dario Amodei | CEO, Anthropic | GOV | ai_lab_leader |
| Jensen Huang | CEO, NVIDIA | COMPUTE | ai_lab_leader |
| Satya Nadella | CEO, Microsoft | INDUSTRY | ai_lab_leader |
| Mark Zuckerberg | CEO, Meta | INDUSTRY | ai_lab_leader |
| Sundar Pichai | CEO, Alphabet/Google | INDUSTRY | ai_lab_leader |
| Mustafa Suleyman | CEO, Microsoft AI | GOV | ai_lab_leader |
| Elon Musk | Founder, xAI | COMPUTE | ai_lab_leader |
| Andy Jassy | CEO, Amazon | INDUSTRY | ai_lab_leader |
| Arvind Krishna | CEO, IBM | INDUSTRY | ai_lab_leader |
| Masayoshi Son | CEO, SoftBank | CAPITAL | ai_lab_leader |
| Lisa Su | CEO, AMD | COMPUTE | ai_lab_leader |
| Clem Delangue | CEO, Hugging Face | SOCIETY | ai_lab_leader |
| Alexandr Wang | CEO, Scale AI | INDUSTRY | ai_lab_leader |
| Daniela Amodei | President, Anthropic | CAPITAL | ai_lab_leader |

**Search focus:** AI strategy, product launches, infrastructure investment, competitive positioning

#### Group 2: `researchers_scientists` — Researchers & Scientists (10 people)
| Name | Role | Primary Lever | Category |
|---|---|---|---|
| Demis Hassabis | CEO, Google DeepMind | COMPUTE | researcher |
| Ilya Sutskever | Co-Founder, SSI | COMPUTE | researcher |
| Yann LeCun | Chief AI Scientist, Meta | COMPUTE | researcher |
| Yoshua Bengio | Professor, Mila | GOV | researcher |
| Fei-Fei Li | Professor, Stanford / World Labs | SOCIETY | researcher |
| Andrew Ng | Founder, DeepLearning.AI | SOCIETY | researcher |
| Andrej Karpathy | Founder, Eureka Labs | COMPUTE | researcher |
| Yejin Choi | Professor, Stanford | COMPUTE | researcher |
| Jeffrey Dean | Chief Scientist, Google DeepMind | COMPUTE | researcher |
| Stuart Russell | Professor, UC Berkeley | GOV | researcher |

**Search focus:** Research breakthroughs, papers, technical commentary, capability assessments, safety research

#### Group 3: `research_labs` — Research Labs & Centers (8 institutions)
| Name | Role | Primary Lever | Category |
|---|---|---|---|
| Google DeepMind | Google's AI research lab | COMPUTE | research_lab |
| OpenAI | AI research company | COMPUTE | research_lab |
| Anthropic | AI safety company | GOV | research_lab |
| Meta FAIR | Meta's Fundamental AI Research lab | COMPUTE | research_lab |
| Mila | Quebec AI Institute | COMPUTE | research_lab |
| Stanford HAI | Stanford Human-Centered AI Institute | SOCIETY | research_lab |
| Allen Institute for AI | Ai2, open-science AI research | COMPUTE | research_lab |
| NIST AI Safety Institute | US federal AI safety standards body | GOV | research_lab |

**Search focus:** Model releases, research papers, safety benchmarks, institutional announcements, blog posts

#### Group 4: `policy_governance` — Policy & Governance (7 people)
| Name | Role | Primary Lever | Category |
|---|---|---|---|
| David Sacks | White House AI & Crypto Czar | GOV | policy |
| Marietje Schaake | Stanford HAI, former EU Parliament | GOV | policy |
| Clara Chappaz | France's Minister for AI and Digital | GOV | policy |
| Henna Virkkunen | EU Executive VP for Tech Sovereignty | GOV | policy |
| Mustafa Suleyman | CEO, Microsoft AI (dual role: policy voice) | GOV | policy |
| Ian Hogarth | Chair, UK AI Safety Institute | GOV | policy |
| Gary Marcus | NYU Professor Emeritus, AI skeptic | GOV | policy |

**Search focus:** AI regulation, policy announcements, governance frameworks, safety standards, geopolitical positioning

#### Group 5: `enterprise_industry` — Enterprise & Industry Voices (7 people)
| Name | Role | Primary Lever | Category |
|---|---|---|---|
| Kai-Fu Lee | CEO, 01.AI / Sinovation Ventures | INDUSTRY | industry |
| Allie K. Miller | AI entrepreneur, TIME100 AI honoree | INDUSTRY | industry |
| Matt Prince | CEO, Cloudflare | INDUSTRY | industry |
| Rene Haas | CEO, Arm Holdings | COMPUTE | industry |
| C.C. Wei | CEO, TSMC | COMPUTE | industry |
| Thomas Kurian | CEO, Google Cloud | INDUSTRY | industry |
| Ali Ghodsi | CEO, Databricks | INDUSTRY | industry |

**Search focus:** Enterprise AI adoption, chip manufacturing, cloud AI, infrastructure deployment, business transformation

#### Group 6: `futurists_intellectuals` — Futurists, Ethics & Public Intellectuals (8 people)
| Name | Role | Primary Lever | Category |
|---|---|---|---|
| Lex Fridman | MIT researcher, podcaster | SOCIETY | public_intellectual |
| Yuval Noah Harari | Historian, author of Sapiens and Nexus | SOCIETY | public_intellectual |
| Kate Crawford | Microsoft Research / NYU, Atlas of AI | GOV | public_intellectual |
| Timnit Gebru | Founder, DAIR Institute | SOCIETY | public_intellectual |
| Tristan Harris | Co-Founder, Center for Humane Technology | SOCIETY | public_intellectual |
| Joy Buolamwini | Founder, Algorithmic Justice League | SOCIETY | public_intellectual |
| Rumman Chowdhury | AI accountability researcher | GOV | public_intellectual |
| Refik Anadol | AI artist, cultural frontier | SOCIETY | public_intellectual |

**Search focus:** Societal impact, ethical concerns, bias/accountability, cultural frontiers, public discourse

#### Group 7: `china_asia_leaders` — China/Asia AI Leaders (4 people)
| Name | Role | Primary Lever | Category |
|---|---|---|---|
| Liang Wenfeng | Founder/CEO, DeepSeek | COMPUTE | ai_lab_leader |
| Robin Li | CEO, Baidu | INDUSTRY | ai_lab_leader |
| Ren Zhengfei | Founder, Huawei | COMPUTE | ai_lab_leader |
| Eddie Wu | CEO, Alibaba (Qwen models) | COMPUTE | ai_lab_leader |

**Search focus:** Chinese AI model development, domestic chip ecosystems, open-source competition, US-China dynamics

#### Group 8: `safety_alignment` — Safety & Alignment (3 people)
| Name | Role | Primary Lever | Category |
|---|---|---|---|
| Geoffrey Hinton | Nobel laureate, Godfather of Deep Learning | GOV | researcher |
| Jan Leike | Anthropic alignment lead | GOV | researcher |
| Noam Brown | OpenAI, o1 reasoning models | COMPUTE | researcher |

**Search focus:** Existential risk warnings, alignment research, inference-time compute breakthroughs, safety evaluation

#### Group 9: `founders_emerging_labs` — Founders & Emerging Lab Leaders (5 people)
| Name | Role | Primary Lever | Category |
|---|---|---|---|
| Arthur Mensch | CEO, Mistral AI | INDUSTRY | ai_lab_leader |
| Aidan Gomez | CEO, Cohere | INDUSTRY | ai_lab_leader |
| Mira Murati | Former CTO OpenAI, Thinking Machines Lab | COMPUTE | ai_lab_leader |
| Brett Adcock | CEO, Figure AI | INDUSTRY | ai_lab_leader |
| Alexander Karp | CEO, Palantir | GOV | ai_lab_leader |

**Search focus:** European AI, enterprise LLMs, humanoid robotics, defense AI, new lab formations

#### Group 10: `investors_capital` — Investors & Capital Allocators (4 people)
| Name | Role | Primary Lever | Category |
|---|---|---|---|
| Marc Andreessen | a16z, AI investment portfolio | CAPITAL | capital |
| Vinod Khosla | Khosla Ventures, early OpenAI investor | CAPITAL | capital |
| Eric Schmidt | Former Google CEO, AI investor & defense advisor | GOV | capital |
| Nat Friedman | Former GitHub CEO, AI angel investor | CAPITAL | capital |

**Search focus:** AI investment theses, capital allocation signals, geopolitical commentary, seed-stage trends

---

## Subagent Prompt Template

For each group, construct the agent prompt by filling in the template below. Replace `{GROUP_LABEL}`, `{INFLUENCER_TABLE}`, `{SEARCH_FOCUS}`, `{START_DATE}`, `{END_DATE}`, `{AGENT_ID}`, and `{GROUP_CODE}`.

```
You are a research agent for espresso·ai, an AI news intelligence service. Your task is to search for recent AI-related publications, commentary, announcements, and activity from the following {GROUP_LABEL} during the period **{START_DATE} to {END_DATE}**.

## Your Influencer List
{INFLUENCER_TABLE}

## Instructions
1. Use WebSearch to find recent activity for each person/institution ({START_DATE} to {END_DATE}). Search for their name + "AI" + recent date context. Try searches like "[Name] AI [month] [year]", "[Name] AI announcement [year]", "[Company] AI [year]", etc.
2. For each significant finding, create a signal record as a JSON object.
3. Only include signals that are IN SCOPE: AI model developments, enterprise AI adoption, AI regulation/policy, long-term structural trends, strategic implications for business.
4. Skip influencers with no notable AI activity in this window.

## Scale Levers Framework — classify each signal against one of these:
- **COMPUTE** — Chips, fabs, data centers, supply chain, custom silicon
- **ENERGY** — Power demand, grid capacity, renewables, cooling
- **SOCIETY** — Adoption depth, talent, workforce shifts, trust, AI literacy
- **INDUSTRY** — Enterprise ROI, production deployments, business model change
- **CAPITAL** — VC, hyperscaler capex, ROI signals, valuation discipline
- **GOV** — Regulation, export controls, safety, geopolitical fragmentation

## Direction codes:
- `+` = Positive (accelerates AI scaling)
- `-` = Negative (constrains AI scaling)
- `~` = Neutral
- `?` = Ambiguous

## Sub-variables (use the most specific match):
COMPUTE: manufacturing_capacity, cost_per_flop, energy_efficiency, supply_chain_resilience, data_center_buildout, custom_silicon_adoption, architectural_diversity
ENERGY: data_center_power_intensity, renewable_allocation, grid_capacity_utilization, renewable_capex_cost, training_energy_per_model, water_consumption, carbon_regulatory_exposure
SOCIETY: enterprise_penetration_depth, high_stakes_domain_adoption, ai_literacy_distribution, researcher_and_engineer_stock, skill_diffusion_rate, professional_displacement_signals, incident_impact_on_trust
INDUSTRY: production_deployment_rate, productivity_measurement_transparency, labor_displacement_scale, business_model_reinvention, capital_allocation_continuity, workflow_integration_depth, cross_sector_diffusion
CAPITAL: hyperscaler_capex_and_utilization, venture_funding_discipline, corporate_rd_reallocation, roi_signal_clarity, valuation_multiple_dynamics, capital_exit_velocity, international_capital_flows
GOV: regulatory_framework_clarity, export_controls_and_chip_access, cross_border_data_and_model_mobility, alignment_and_safety_maturity, geopolitical_fragmentation_index, antitrust_and_market_structure, institutional_trust

## Signal Record Format (return as JSON array):
For each signal, produce this exact JSON structure:
{
  "signal_id": "YYYYMMDD-{source_name}-HHMMSS-{5char_hash}",
  "source_name": "[twitter|news_site|company_announcement|academic_paper|linkedin|other]",
  "source_url": "https://actual-url-found",
  "fetch_timestamp": "YYYY-MM-DDTHH:MM:SSZ",
  "agent_id": "{AGENT_ID}",
  "cadence": "{CADENCE}",
  "pipeline_run_id": "{START_DATE}_{END_DATE}_influencer_{CADENCE}_{8char_uuid}",
  "collection_batch_id": "batch_YYYYMMDD_HHMM",
  "lever_primary": "LEVER_CODE",
  "lever_secondary": null,
  "direction": "+|-|~|?",
  "sub_variable": "specific_sub_variable",
  "confidence": "high|medium|low",
  "title": "Original headline or description (max 200 chars)",
  "summary": "1-2 sentences: what this MEANS for AI scaling. Lead with direction. Declarative, no hedging.",
  "key_facts": ["fact1", "fact2", "fact3"],
  "raw_content": null,
  "publication_date": "YYYY-MM-DD",
  "reporting_period": null,
  "signal_strength": null,
  "cross_lever_interactions": [],
  "novelty_flag": null,
  "countervailing_signals": [],
  "synthesis_notes": null,
  "is_duplicate": false,
  "duplicate_of": null,
  "in_scope": true,
  "data_quality_flags": [],
  "tags": ["influencer:name_slug", "influencer_group:{GROUP_CODE}", "account_category:{category}"],
  "schema_version": "1.0"
}

## Voice Guidelines
- Lead with the insight, not the context
- Declarative sentences; state what is true
- No hype language ("game-changing," "revolutionary")
- No hedging ("might," "could potentially")
- No filler ("In today's rapidly evolving...")

## Output
Write each signal record as a single JSON line to the file:
research_db/raw/{START_DATE}_{END_DATE}_influencer_{GROUP_CODE}_{CADENCE}_signals.jsonl

Use the Bash tool to append each record. After writing all signals, print a summary of how many signals were written and for which influencers.
Aim for 3-15 signals total depending on group size. Quality over quantity — only include signals with real, verifiable sources found via WebSearch. Use the ACTUAL URLs you find in search results.
```

### Agent ID Mapping

| Group Code | Agent ID |
|---|---|
| ceo_industry_leaders | influencer-ceo-collector |
| researchers_scientists | influencer-researcher-collector |
| research_labs | influencer-lab-collector |
| policy_governance | influencer-policy-collector |
| enterprise_industry | influencer-enterprise-collector |
| futurists_intellectuals | influencer-futurist-collector |
| china_asia_leaders | influencer-china-collector |
| safety_alignment | influencer-safety-collector |
| founders_emerging_labs | influencer-founder-collector |
| investors_capital | influencer-investor-collector |

---

## Step 4: Consolidate Results

After all agents complete, run the consolidation script:

```bash
python3 .claude/scripts/consolidate_influencer_signals.py \
  --cadence <CADENCE> \
  --start-date <START_DATE> \
  --end-date <END_DATE>
```

This script:
1. Reads all per-group JSONL fragment files from `research_db/raw/` matching `{START_DATE}_{END_DATE}_influencer_*_{CADENCE}_signals.jsonl`
2. Validates all records have required fields
3. Deduplicates by `source_url` (normalized) and `title` (case-insensitive)
4. Writes consolidated JSONL to `research_db/raw/{START_DATE}_{END_DATE}_influencer_{CADENCE}_signals.jsonl`
5. Writes pipeline log to `research_db/raw/{START_DATE}_{END_DATE}_influencer_{CADENCE}_pipeline_log.json`
6. Cleans up per-group fragment files
7. Prints summary stats

## Step 5: Present Summary

After the consolidation script completes:

1. Read the pipeline log JSON file.
2. Present a summary to the user including:
   - Pipeline run ID and date window
   - Total signals collected and written
   - Signals by group
   - Lever distribution (COMPUTE, ENERGY, SOCIETY, INDUSTRY, CAPITAL, GOV)
   - Direction distribution (+, -, ~, ?)
   - Duplicates removed
   - Output JSONL file path

Do NOT read or summarize individual signals from the JSONL file.

## Step 6: Error Handling

- **Agent failures**: If an agent returns an error or no signals, log the issue and continue with other groups. Do not block the entire pipeline.
- **No signals collected**: Possible causes — influencers inactive during the window, WebSearch returned no relevant results.
- **Consolidation errors**: If the Python script fails, check that per-group JSONL files exist and contain valid JSON.
