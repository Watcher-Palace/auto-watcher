# Skill-evolution questions — rules with exceptions, awaiting your decision

Distilled 2026-07-04 from all archived reviews (14 annotated) + 30 v1→final
draft diffs, validated against the 47 published posts. Per your rule, anything
with even one counterexample is asked here, not silently adopted. For each:
**keep** (adopt into SKILL.md as stated), **drop**, or **refine** (tell me the
real boundary).

## Q1 — General A/B/D rubric beyond the 偷拍 rule

Proposed: `A` requires (a) engaged criminal process, OR (b) death/severe
bodily harm, OR (c) nationwide-scale outrage. Otherwise `B` (civil suit,
administrative-only outcome, or sizable attention) / `D` (individual conduct,
no institutional dimension, limited impact).

Fits 44/47 published posts. Exceptions:
- `260113` 女医学生遭前男友杀害案一审判决死刑 → categorized **N** (death
  sentence = engaged process; rubric predicts A)
- `260119` 16岁男子殴打五名女性，警方立案 → **N** (立案 = engaged; predicts A)
- `260507` 杭州非法代孕窝点曝光 → **A** at publish time with no visible
  criminal process yet (severe-harm carve-out (b) covers it only loosely)

Is `N` meant to override everything while YOU consider the case unresolved
(e.g. awaiting 二审/复核)? If so, what marks a case as N — your call at review
time, or a statable criterion the writer can apply?

## Q2 — B vs D for stranger violence against women

Published: 偷拍-type cases with only 行政拘留 → **B** (260601-4 地铁偷拍大爷,
260512, 260521…), but physical stranger attacks with only 行政处理 → **D**
(260511 踢倒女子, 260531 撞击女性). Both target women; the split seems to be:
privacy/sexual-content harm → B, generic physical assault w/o criminal case →
D. Correct principle, or coincidence of two cases?

## Q3 — frontmatter date format

Recent v1→final diffs strip the time component 6 times, never add it
(`2026-05-22 00:00:00` → `2026-05-22`). But 23 of 47 published posts (older
ones) still carry times. Adopt "date is always plain YYYY-MM-DD" going forward
(I'd add a linter check), or is the time sometimes meaningful?

## Q4 — 前情/后续 ban strictness

Current SKILL.md forbids standalone `## 前情`/`## 后续` and the new linter
flags them. 8 published posts (through late May) still contain them —
presumably pre-rule. Confirm the ban is absolute for new posts (old posts
grandfathered), or should reviewer-accepted exceptions be possible? (If
absolute, no change needed — linter already enforces it.)

## Q5 — data conflict on 260601-1

Your review annotation said 分级为B (23岁女孩离世男友持欠条索30万), but the
published post `260601.md` is **A**. Which is authoritative? If A was a
deliberate reversal (death involved), that supports Q1's carve-out (b); if it
slipped through, the published post is miscategorized.

---

Already adopted without asking (zero counterexamples across all 47 posts):
- 偷拍/骚扰 with administrative-only outcome → B; engaged criminal process → A
  (now in blog-write SKILL.md Categories).
- Every v1 draft must carry 2+ registered tags (SKILL.md + linter).
- Data-less 舆论 sections are format violations (was already in SKILL.md;
  linter now enforces).
