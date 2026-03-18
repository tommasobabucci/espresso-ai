# CLAUDE.md Guide — Official Best Practices

> Source: https://code.claude.com/docs/en/memory
> Last updated for espresso.ai: 2026-03-18

---

## What is CLAUDE.md?

CLAUDE.md files give Claude **persistent instructions** for a project, your personal workflow, or your entire organization. They are read at the start of every session and loaded into context alongside your conversation.

Claude treats them as **context, not enforced configuration** — the more specific and concise your instructions, the more consistently Claude follows them.

---

## Two Memory Systems

| | CLAUDE.md files | Auto memory |
|---|---|---|
| **Who writes it** | You | Claude |
| **What it contains** | Instructions and rules | Learnings and patterns |
| **Scope** | Project, user, or org | Per working tree |
| **Loaded into** | Every session | Every session (first 200 lines) |
| **Use for** | Coding standards, workflows, architecture | Build commands, debugging insights, discovered preferences |

---

## Where to Put CLAUDE.md

| Scope | Location | Purpose |
|---|---|---|
| **Managed policy** | `/Library/Application Support/ClaudeCode/CLAUDE.md` (macOS) | Org-wide, managed by IT |
| **Project instructions** | `./CLAUDE.md` or `./.claude/CLAUDE.md` | Team-shared via source control |
| **User instructions** | `~/.claude/CLAUDE.md` | Personal preferences for all projects |

More specific locations take precedence over broader ones.

---

## Writing Effective Instructions

- **Target under 200 lines** per CLAUDE.md — longer files consume more context and reduce adherence
- **Use markdown headers and bullets** — organized sections are easier for Claude to follow
- **Be specific and concrete:**
  - ✅ "Use 2-space indentation"
  - ❌ "Format code properly"
  - ✅ "Run `npm test` before committing"
  - ❌ "Test your changes"
- **Avoid conflicts** — if two rules contradict each other, Claude may pick one arbitrarily

---

## Importing Additional Files

Use `@path/to/file` syntax to import additional context:

```markdown
See @README for project overview.
# Git workflow: @docs/git-instructions.md
```

- Both relative and absolute paths are supported
- Imported files are expanded at launch
- Maximum import depth: 5 hops

---

## Organizing Rules with `.claude/rules/`

For larger projects, put topic-specific instruction files in `.claude/rules/`:

```
.claude/
├── CLAUDE.md
└── rules/
    ├── code-style.md
    ├── testing.md
    └── security.md
```

Rules can be **path-scoped** with YAML frontmatter:

```yaml
---
paths:
  - "src/api/**/*.ts"
---
# API Development Rules
- All endpoints must include input validation
```

---

## Auto Memory

Claude accumulates learnings automatically in `~/.claude/projects/<project>/memory/`:

```
memory/
├── MEMORY.md          # Index (first 200 lines loaded every session)
├── debugging.md       # Detailed debugging patterns
└── api-conventions.md # Discovered API patterns
```

Use `/memory` command to view and edit all loaded instruction files.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Claude isn't following CLAUDE.md | Run `/memory` to verify the file is loading; make instructions more specific |
| CLAUDE.md too large | Split into `.claude/rules/` files using `@` imports |
| Instructions lost after `/compact` | Add them to CLAUDE.md — conversation-only instructions don't persist |
