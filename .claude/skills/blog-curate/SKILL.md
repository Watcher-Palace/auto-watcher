---
name: blog-curate
description: Curator skill for the feminist blog — maintains the 累积经验 sections in each pipeline agent file, promoting insights and pruning stale entries
---

# Blog Curate Skill

You are the curator for a feminist news blog's pipeline agents. Your job is to keep the `累积经验` sections across the pipeline agents healthy: concise, accurate, non-conflicting, and progressively promoting key insights into the agent's instruction sections.

## Curated Files

Each pipeline agent carries its accumulated experience in a `## 累积经验` section of its own definition file:

```
.claude/agents/blog-researcher.md
.claude/agents/blog-writer.md
.claude/agents/blog-reviewer.md
```

## When to Run

- After completing a full pipeline cycle (track → research → write → review → publish)
- When any agent's `累积经验` section exceeds ~15 entries
- When the orchestrator detects a pattern worth recording

## Harvest (feed the notes)

`python src/pipeline_cli.py harvest` lists published events (`YYMMDD-N`) whose
corrections have not yet been distilled (经验提取=待提取 in `_pipeline/events.csv`;
the publisher marks each publish 待提取). For each entry (files may sit in
`_pipeline/` or `_pipeline_archive/` after archiving):

1. Read every review version's user input (`## 人类意见` / `<!-- [USER]: -->`) and
   diff draft v1 against the final version (frontmatter and structure included).
2. Distill into the relevant agent's `## 累积经验` section as **general principles
   only** — state the rule and its why; never case names, dates, or one-off
   specifics. If a correction cannot be stated as a general rule, do not
   record it.
3. Mark each processed entry: `python src/pipeline_cli.py harvest done YYMMDD N`.

**Exception gate (mandatory):** a rule that holds for most posts but conflicts
with even one published post or user decision must NOT be silently adopted or
dropped — list the exception cases and ask the user to keep/drop/refine it.
The same gate applies at promotion time for `[CANDIDATE]` entries.

## Entry Tags

- `[NOTE]` — observation, not yet confirmed as a recurring pattern
- `[CANDIDATE]` — recurring pattern, ready to promote to the agent's instruction sections

## Curation Process

For each agent file:

1. **Read** the current `## 累积经验` section and the instruction sections above it.
2. **Promote** `[CANDIDATE]` entries: merge the insight into the appropriate instruction section, then remove the entry from `## 累积经验`.
3. **Prune** stale or superseded `[NOTE]` entries.
4. **Resolve conflicts**: if an entry contradicts something in the instruction sections or another entry, investigate and keep whichever is correct; remove the other.
5. **Cap** entries: if `## 累积经验` exceeds ~15 entries after promotion/pruning, consolidate redundant entries.
6. **Write** the file back with changes.

## Promotion Guidelines

A `[CANDIDATE]` is ready to promote when:
- It has been observed in ≥2 separate pipeline runs, OR
- It prevents a class of errors that would otherwise repeat

When promoting, integrate naturally into the relevant instruction section of the agent file — do not append a "Notes" section. Rewrite the affected section to incorporate the insight seamlessly.

**Prefer code over prose (anti-bloat):** if a promoted rule is mechanically
checkable, implement it as a `src/linter.py` check (with a test) and keep at
most one line about it in the agent file. Prose rules depend on subagent
attention and dilute each other as the file grows; lint rules are enforced
for free. When promoting into the agent file, also merge any overlapping
existing rules — net growth of the file should be near zero. If an agent
file exceeds ~180 lines, flag it to the user for a compaction pass instead
of appending more.
Routing when promoting: mechanically checkable → `src/linter.py` or
`src/review_linter.py` (with a test); format/structure rules →
`source/_drafts/template.md`; judgment rules → the agent's instruction
sections.

## Conflict Resolution

If an entry conflicts with the instruction sections:
- If the entry is more recent and correct: update the instruction sections, remove the entry
- If the instruction sections are correct: remove the entry, possibly add a clarifying sentence to the instruction sections

If two entries conflict with each other:
- Keep the more accurate/recent one
- If both are valid in different contexts, merge into one nuanced entry

## Output

After curating, report:
- How many entries promoted to each agent file
- How many entries pruned
- Any conflicts resolved
- Current entry count per agent's `累积经验` section
