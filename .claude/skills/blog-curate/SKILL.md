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
2. **"写手当时就该知道"这类归因，一律先证伪再写。** `src/tags.yml`、研究文件、
   linter 规则都可能在草稿写完之后才被规范化，你事后读到的是**修正后**的状态；
   用户批注本身也会用"注册表已有 X"来描述自己刚刚才加的 X。据此推断"写手没查
   注册表／写作阶段引入了偏差"必然出错。要落这类结论，先回到草稿写作时点核对
   （`git log -S<关键词> -- <文件>`、`git show <草稿所在提交之前>:<文件>`），
   核不出来就不写这条。
3. Distill into the relevant agent's `## 累积经验` section as **general principles
   only** — state the rule and its why; never case names, dates, or one-off
   specifics. If a correction cannot be stated as a general rule, do not
   record it.
4. Mark each processed entry: `python src/pipeline_cli.py harvest done YYMMDD N`.

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
existing rules — net growth of the file should be near zero.
Routing when promoting: mechanically checkable → `src/linter.py` or
`src/review_linter.py` (with a test); format/structure rules →
`source/_drafts/template.md`; judgment rules → the agent's instruction
sections.

## 体积预算（硬闸口，2026-08-05）

起因：07-22 密度压缩后仅两周，researcher 文件 13.9KB→25.7KB 近翻倍，而旧的
"~180 行"阈值全程没触发——只 +27 行，字节 +85%，规则是**横着长的**（越写越像
段落）。因此：

- **量字节，不量行数**。每轮 curate 开始与结束都跑
  `wc -c .claude/agents/blog-*.md`，两组数字写进报告。
- **预算线（UTF-8 字节）**：`blog-researcher.md` ≤ 19000、`blog-writer.md` ≤ 24000、
  `blog-reviewer.md` ≤ 12000（≈ 07-22 压缩后基线 +30%；researcher 上调 1000 系
  2026-08-05 首轮执行实测——基线不含其后新增的 汇报纪律/自媒体分层/安全闸口/形态标注
  四个规则域，压到一行反例、短 why 后诚实的底在 ~19000）。
- **超线 = 冻结 prose 新增**：先压缩回线内（反例迁 casebook、合并重叠规则、
  段落收紧成条目），才许晋升/新增任何 prose 规则。改造成 linter/机械闸口后的
  一行指针不受冻结——那正是出路。贴线运行是设计意图不是故障：晋升新段落就该在
  存量里找等量空间，新规则与最弱的旧规则竞争；压缩红利耗尽后，出路只有机械化
  与合并，没有"再涨一点"。
- **[NOTE] 进栏不受冻结，欠账由 curate 结算**：一行 `[NOTE]` 落进 `## 累积经验`
  即使在超线状态也允许——进栏通道另有 ~15 条上限与"一行为限"兜着，堵死它只会
  让经验丢失或流落错误位置。代价收在结算点：**每轮 curate 结束时文件必须回到
  线内**；预算约束的是 curate 交付时点，不是逐笔记录时点。
- **同一规则违反复发时，禁止"加强版重写"**：规则已存在还被违反，说明 prose 的
  边际收益已尽，只有两个出口——(a) 改造成机械自证/linter 检查；(b) 原句收紧且
  字数不增。不得追加第二段更详细的重述（反面型：08-04"信息来源摘录规则三项
  收紧"一笔 +3.2KB，重述的正是已存在却被违反 5 次的规则）。

## 反例写法与去重（硬规则，2026-07-22；防规则/反例跨文件重复）

- **一条规则至多一个反例，一行为限**：写进 agent 文件的反例只写"事件号 + 一句话"
  （如 `（例：260716-7 "白女士"被二次化名为"林悦"）`）。完整错误链条（谁转引谁、
  错误如何扩散、用户如何纠正）一律不进 agent 文件——移入 `docs/casebook.md` 按事件号
  登记，agent 文件里的一行反例就是它的索引；原始留痕在 `_pipeline_archive/` 的
  research/review 文件里，casebook 条目注明出处即可。
- **反例只落一个文件**：同一条规则约束多个阶段时（如研究管入库、写手管入稿），每个
  agent 各写一条自己视角的义务，反例只写在错误实际发生的那个 agent 文件里，另一侧
  不带例子。
- **落笔前先查重**：向任何 agent 文件新增或晋升规则前，先在其余 agent 文件与
  `source/_drafts/template.md` 里检索同一规则；已存在时按上方 Routing 收敛到单一
  归宿，不得出现第二份全文。**写手与评审都要用的规则不是例外，恰是收敛对象**：
  二者共同必读 `source/_drafts/template.md`（写手照它写，评审照它开 `类型：格式`
  问题），这类规则全文只进 template，两个 agent 文件里各留至多一行指针（如
  "风格硬规则见 template"）。没有共同必读文件的组合（如研究↔写手）才按上一条
  处理：各写一条自己视角的义务，原文与反例不复制。

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
