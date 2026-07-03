---
name: blog-curate
description: Curator skill for the feminist blog — maintains notes.md files across all blog skills, promoting insights and pruning stale entries
---

# Blog Curate Skill

You are the curator for a feminist news blog's skill notes system. Your job is to keep the `notes.md` files across all blog skills healthy: concise, accurate, non-conflicting, and progressively promoting key insights into `SKILL.md`.

## Skill Notes Files

```
.claude/skills/blog-research/notes.md
.claude/skills/blog-write/notes.md
.claude/skills/blog-review/notes.md
```

## When to Run

- After completing a full pipeline cycle (track → research → write → review → publish)
- When any notes.md exceeds ~15 entries
- When the orchestrator detects a pattern worth recording

## Harvest (feed the notes)

`_pipeline/harvest-queue.txt` lists published events (`YYMMDD-N`) whose corrections
have not yet been distilled — `publisher.py` appends an entry on every successful
publish. For each entry (files may sit in `_pipeline/` or `_pipeline_archive/`
after archiving):

1. Read every review version's user input (`## 人类意见` / `<!-- [USER]: -->`) and
   diff draft v1 against the final version (frontmatter and structure included).
2. Distill into the relevant skill's `notes.md` as **general principles only** —
   state the rule and its why; never case names, dates, or one-off specifics.
   If a correction cannot be stated as a general rule, do not record it.
3. Remove processed entries from the queue.

**Exception gate (mandatory):** a rule that holds for most posts but conflicts
with even one published post or user decision must NOT be silently adopted or
dropped — list the exception cases and ask the user to keep/drop/refine it.
The same gate applies at promotion time for `[CANDIDATE]` entries.

## Entry Tags

- `[NOTE]` — observation, not yet confirmed as a recurring pattern
- `[CANDIDATE]` — recurring pattern, ready to promote to `SKILL.md`

## Curation Process

For each `notes.md`:

1. **Read** the current `notes.md` and the corresponding `SKILL.md`.
2. **Promote** `[CANDIDATE]` entries: merge the insight into `SKILL.md` at the appropriate section, then remove the entry from `notes.md`.
3. **Prune** stale or superseded `[NOTE]` entries.
4. **Resolve conflicts**: if a note contradicts something in `SKILL.md` or another note, investigate and keep whichever is correct; remove the other.
5. **Cap** entries: if `notes.md` exceeds ~15 entries after promotion/pruning, consolidate redundant notes.
6. **Write** both files back with changes.

## Promotion Guidelines

A `[CANDIDATE]` is ready to promote when:
- It has been observed in ≥2 separate pipeline runs, OR
- It prevents a class of errors that would otherwise repeat

When promoting, integrate naturally into the relevant section of `SKILL.md` — do not append a "Notes" section. Rewrite the affected SKILL.md section to incorporate the insight seamlessly.

## Conflict Resolution

If a note conflicts with `SKILL.md`:
- If the note is more recent and correct: update `SKILL.md`, remove the note
- If `SKILL.md` is correct: remove the note, possibly add a clarifying sentence to `SKILL.md`

If two notes conflict with each other:
- Keep the more accurate/recent one
- If both are valid in different contexts, merge into one nuanced note

## Output

After curating, report:
- How many entries promoted to each SKILL.md
- How many entries pruned
- Any conflicts resolved
- Current entry count per notes.md
