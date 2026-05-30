# Claude Code Skills

This directory holds project-level [Agent Skills](https://docs.claude.com/en/docs/claude-code/skills) for the Jesse codebase. Claude Code auto-discovers every `*/SKILL.md` under here and loads a skill's full body on demand when its `description` matches what you're doing.

## Layout

```
.claude/skills/
  <skill-name>/
    SKILL.md            # required: frontmatter + instructions
    <supporting files>  # optional: examples, scripts, reference docs
```

- One directory per skill. The directory name should match the `name` in the frontmatter.
- `name`: lowercase letters, numbers, and hyphens only (max 64 chars).
- `description`: written in the third person, stating **what** the skill does and **when** to use it, with concrete trigger words. This is the only part always in context, so it must be specific enough for Claude to decide relevance.
- Keep `SKILL.md` focused (a few hundred lines at most). Push long references, templates, or data into separate files in the same directory and link to them — Claude reads them only when needed (progressive disclosure).

## Frontmatter template

```markdown
---
name: my-skill
description: Use when <situation/triggers>. Does <what it provides>.
---

# My Skill

<instructions Claude should follow when this skill is active>
```

## Skills in this repo

- `jesse-strategy-tests/` — conventions for writing Jesse strategy/engine tests.
