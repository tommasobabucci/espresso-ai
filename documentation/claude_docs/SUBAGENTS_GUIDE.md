# Subagents Guide — Official Best Practices

> Source: https://code.claude.com/docs/en/sub-agents
> Last updated for espresso.ai: 2026-03-18

---

## What are Subagents?

Subagents are **specialized AI assistants** that handle specific types of tasks. Each runs in its own context window with a custom system prompt, specific tool access, and independent permissions. Claude delegates to subagents when a task matches their description, and they return results to the main conversation.

**Key benefits:**
- Preserve main conversation context by isolating verbose operations
- Enforce tool constraints (e.g., read-only agents)
- Reuse specialized configurations across projects
- Control costs by routing tasks to faster/cheaper models

---

## Built-in Subagents

| Agent | Model | Purpose |
|---|---|---|
| **Explore** | Haiku | Fast, read-only codebase search |
| **Plan** | Inherits | Research during plan mode |
| **general-purpose** | Inherits | Complex multi-step tasks |

---

## Subagent File Structure

Subagents are Markdown files with YAML frontmatter stored in:
- `.claude/agents/` — project-scoped (shared via version control)
- `~/.claude/agents/` — personal, available in all projects

```markdown
---
name: my-agent
description: What this agent does and when to use it
tools: Read, Grep, Glob, Bash
model: sonnet
memory: project
---

You are a [role description].

When invoked:
1. Step one
2. Step two
3. Step three

[Detailed instructions...]
```

---

## Frontmatter Fields

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Unique identifier (lowercase, hyphens) |
| `description` | Yes | When Claude should delegate to this agent |
| `tools` | No | Tools allowed (inherits all if omitted) |
| `disallowedTools` | No | Tools to explicitly deny |
| `model` | No | `sonnet`, `opus`, `haiku`, or `inherit` |
| `permissionMode` | No | `default`, `acceptEdits`, `dontAsk`, `bypassPermissions`, `plan` |
| `maxTurns` | No | Max agentic turns before stopping |
| `skills` | No | Skills preloaded into this agent's context |
| `memory` | No | `user`, `project`, or `local` — enables cross-session learning |
| `hooks` | No | Lifecycle hooks scoped to this agent |
| `background` | No | `true` to always run as background task |
| `isolation` | No | `worktree` to run in isolated git worktree |

---

## Persistent Memory

Enable cross-session learning with the `memory` field:

| Scope | Location | Use when |
|---|---|---|
| `user` | `~/.claude/agent-memory/<name>/` | Learnings should apply across all projects |
| `project` | `.claude/agent-memory/<name>/` | Project-specific, shareable via version control |
| `local` | `.claude/agent-memory-local/<name>/` | Project-specific, not committed |

---

## espresso.ai Agent Templates

### News Collector Agent

```markdown
---
name: news-collector
description: Collects AI news from configured sources. Use when starting a pipeline run to gather raw intelligence.
tools: Bash, Read, Write
model: sonnet
memory: project
---

You are the intelligence gatherer for espresso.ai.

When invoked:
1. Check the configured news sources in `.env/` for API endpoints and RSS feeds
2. Fetch articles published since the last collection timestamp in `research_db/raw/last_run.json`
3. Save each article as JSON to `research_db/raw/YYYY-MM-DD_[source].json`
4. Update the last_run timestamp
5. Report: sources checked, articles collected, any errors

Always collect with a timestamp. Never duplicate articles already in raw/.
```

### Signal Filter Agent

```markdown
---
name: signal-filter
description: Filters AI news signal from noise. Use after news collection to score and rank articles.
tools: Read, Write
model: sonnet
memory: project
---

You are the signal/noise separator for espresso.ai.

Scoring criteria:
- Strategic importance (1-5): Does this affect enterprise AI strategy?
- Novelty (1-5): Is this genuinely new information vs. recaps?
- Relevance (1-5): Is this relevant to AI strategy consulting (EY context)?

When invoked:
1. Read all unprocessed files from `research_db/raw/`
2. Score each article on the three criteria above
3. Discard articles with total score < 8
4. Save high-signal articles to `research_db/processed/YYYY-MM-DD_processed.json`
5. Report: articles scored, articles kept, articles discarded
```

### LinkedIn Writer Agent

```markdown
---
name: linkedin-writer
description: Writes LinkedIn posts from synthesized AI insights. Use after insight synthesis to produce final content.
tools: Read, Write
model: opus
---

You are the voice of Tommaso Babucci on LinkedIn.

Always read `brand_assets/about_me/` and the appropriate `brand_assets/linkedin_templates/` before writing.

Tone: authoritative, forward-thinking, accessible — never hype-driven
Perspective: AI Strategy Consultant + practitioner
Always connect developments to business impact and leadership implications

Output to: `PR/{cadence}/YYYY-MM-DD_{cadence}_post.md`
```

---

## Common Patterns

### Invoke explicitly
```
Use the signal-filter agent to process today's raw data
@"signal-filter (agent)" process the raw folder
```

### Chain agents
```
Use the news-collector agent to gather today's news,
then use the signal-filter agent to process it,
then use the insight-synthesizer to produce a weekly brief
```

### Run as background task
```
Run the news-collector agent in the background
```

---

## Best Practices

1. **One focused responsibility per agent** — avoid Swiss Army knife agents
2. **Write detailed descriptions** — Claude uses these to decide when to delegate
3. **Restrict tools** — grant only necessary permissions (least privilege)
4. **Use `memory: project`** for agents that accumulate knowledge about your data
5. **Check agents into version control** — enables team collaboration
