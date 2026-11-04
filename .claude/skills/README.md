# `.claude/skills`

**Overview.** Claude Code's view of the project skills. Each folder holds a `SKILL.md` with the same name and description as the canonical skill, and a single instruction to load the canonical file in [`.agents/skills`](../../.agents/skills). That keeps one copy of each skill for every agent.

## Extending

When you add a skill to `.agents/skills/<name>/SKILL.md`, add `.claude/skills/<name>/SKILL.md` with the same front matter and a link to the canonical file. Don't put content here; edit the canonical copy.
