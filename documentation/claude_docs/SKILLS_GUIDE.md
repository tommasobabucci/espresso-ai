# Skills Guide — Official Best Practices

> Source: https://code.claude.com/docs/en/skills
> Last updated for espresso.ai: 2026-03-18

---

## What are Skills?

Skills extend what Claude can do. Create a `SKILL.md` file with instructions, and Claude adds it to its toolkit. Claude uses skills when relevant, or you can invoke one directly with `/skill-name`.

**Skills vs. Subagents:**
- **Skills** run instructions inline within your conversation (or in a forked subagent with `context: fork`)
- **Subagents** are independent agents with their own context, system prompt, and tool restrictions

**Custom commands have been merged into skills.** A file at `.claude/commands/deploy.md` and a skill at `.claude/skills/deploy/SKILL.md` work identically.

---

## Skill File Structure

Each skill lives in its own directory with `SKILL.md` as the entrypoint:

```
my-skill/
├── SKILL.md           # Main instructions (required)
├── template.md        # Template for Claude to fill in
├── examples/
│   └── sample.md      # Example output format
└── scripts/
    └── validate.sh    # Scripts Claude can execute
```

### SKILL.md Template

```markdown
---
name: skill-name
description: What this skill does and when to use it (used by Claude to auto-invoke)
disable-model-invocation: true  # optional: only user can invoke
context: fork                   # optional: run in isolated subagent
allowed-tools: Read, Bash       # optional: restrict tool access
---

# Skill Instructions

Step-by-step instructions for what Claude should do when this skill runs.

## Arguments
Use $ARGUMENTS for any arguments passed: /skill-name [arguments]

## Supporting files
- See [template.md](template.md) for the output format
```

---

## Where Skills Live

| Location | Path | Applies to |
|---|---|---|
| Personal | `~/.claude/skills/<name>/SKILL.md` | All your projects |
| Project | `.claude/skills/<name>/SKILL.md` | This project only |
| Plugin | `<plugin>/skills/<name>/SKILL.md` | Where plugin is enabled |

Higher-priority: Enterprise > Personal > Project > Plugin

---

## Frontmatter Reference

| Field | Description |
|---|---|
| `name` | Display name / slash command (lowercase, hyphens, max 64 chars) |
| `description` | What it does + when to use it. Claude uses this for auto-invocation |
| `argument-hint` | Autocomplete hint, e.g., `[cadence]` |
| `disable-model-invocation` | `true` = only user can invoke with `/name`. Use for side-effect skills |
| `user-invocable` | `false` = hide from `/` menu (Claude-only background knowledge) |
| `allowed-tools` | Tools Claude can use without approval when this skill is active |
| `model` | Model to use when skill is active |
| `context` | `fork` = run in isolated subagent context |
| `agent` | Which subagent to use with `context: fork` |
| `hooks` | Lifecycle hooks scoped to this skill |

---

## String Substitutions

| Variable | Description |
|---|---|
| `$ARGUMENTS` | All arguments passed at invocation |
| `$ARGUMENTS[N]` | Specific argument by 0-based index |
| `$N` | Shorthand for `$ARGUMENTS[N]` |
| `${CLAUDE_SESSION_ID}` | Current session ID |
| `${CLAUDE_SKILL_DIR}` | Directory containing the skill's SKILL.md |

---

## Control Who Invokes a Skill

| Frontmatter | User can invoke | Claude can invoke |
|---|---|---|
| (default) | ✅ | ✅ |
| `disable-model-invocation: true` | ✅ | ❌ |
| `user-invocable: false` | ❌ | ✅ |

**Rule of thumb:**
- Use `disable-model-invocation: true` for skills with side effects (deploy, publish, send)
- Use `user-invocable: false` for background knowledge Claude should know but users don't invoke directly

---

## Dynamic Context with Shell Commands

The `!`command`` syntax runs shell commands before Claude sees the skill:

```markdown
---
name: pr-summary
context: fork
agent: Explore
---

## Pull request context
- PR diff: !`gh pr diff`
- PR comments: !`gh pr view --comments`

Summarize this pull request...
```

The commands run first; their output replaces the placeholder. Claude only sees the rendered result.

---

## espresso.ai Skill Templates

### Run Pipeline Skill

```markdown
---
name: run-pipeline
description: Run the full espresso.ai news collection and synthesis pipeline
disable-model-invocation: true
argument-hint: [daily|weekly|monthly|quarterly|annual]
allowed-tools: Bash, Read, Write
---

# Run espresso.ai Pipeline

**REPORT_CADENCE:** $ARGUMENTS

Verify that REPORT_CADENCE is one of: daily, weekly, monthly, quarterly, annual.
If not specified or invalid, stop and ask the user to specify.

Execute the pipeline in sequence:
1. Invoke the `news-collector` agent to gather today's raw data
2. Invoke the `signal-filter` agent to score and process articles
3. Invoke the `insight-synthesizer` agent with cadence = $ARGUMENTS
4. Invoke the `linkedin-writer` agent with cadence = $ARGUMENTS
5. Report the path to the final output in PR/$ARGUMENTS/

Log each step to `research_db/pipeline_log.json` with timestamp and status.
```

### Brand Voice Check Skill

```markdown
---
name: brand-check
description: Check LinkedIn output against Tommaso's brand voice guidelines before publishing
disable-model-invocation: true
argument-hint: [filepath]
allowed-tools: Read
---

# Brand Voice Check

Read the file at: $ARGUMENTS
Read the brand voice guide at: brand_assets/about_me/voice_guide.md

Evaluate the content on:
1. Tone: Is it authoritative, forward-thinking, and accessible (not hype-driven)?
2. Perspective: Does it reflect an AI Strategy Consultant + practitioner POV?
3. Business framing: Does it connect AI developments to business impact?
4. EY context: Is the consulting/enterprise framing present where appropriate?
5. LinkedIn format: Is the structure optimized for engagement?

Return a score (1-10) for each criterion and specific revision suggestions.
```

---

## Best Practices

- **Keep SKILL.md under 500 lines** — move detail to supporting files
- **Write descriptions with keywords** Claude would naturally associate with the task
- **Use `context: fork`** for long-running, isolated tasks that produce verbose output
- **Reference supporting files** from SKILL.md so Claude knows what's available
- **Test by invoking directly** with `/skill-name` before relying on auto-invocation
