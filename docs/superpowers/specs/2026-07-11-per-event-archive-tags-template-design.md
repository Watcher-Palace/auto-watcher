# 设计：CSV 状态账本 · 按事件归档 · TAG-PROPOSAL · 模板唯一权威 · 一致性修正

日期：2026-07-11
状态：待用户批准（v2 —— 新增方案 E 状态重构，方案 A 相应简化）

## 背景

日常维护中暴露五类问题：

1. **状态维护繁冗脆弱**：状态散在 7 个载体（events md 的 `## N.` 解析、status 侧车、工件文件存在性、`.state`、`done-dates.txt`、`.tracker-state.json`、`harvest-queue.txt`），批准/废弃事件要跑 python 片段，events md 一丢整个日期卡死（260524 事故）。
2. 归档以"日期"为原子单位——日期下任一事件未完结，已完结事件的文件也无法归档（260524-2 已发布却因 260524-1 卡在 v1 而滞留）。
3. writer 从 `src/tags.yml` 硬凑边缘关联标签，从不提出新标签——skill 要求"停下来问用户"，而子代理无法中途问人；linter/publisher 又硬拒未注册标签。
4. writer 不按模板写、reviewer 不指出——`source/_drafts/template.md` 是三月老骨架，与 blog-write SKILL.md 规范矛盾；orchestrator 派发 prompt 只带参数不带约束；review skill 没有格式规范可对照。
5. 全量审计发现的其余漂移：`.env` 路径写错（实际 `src/.env`）、abort 流程在所有 skill 中缺失、`--date.md` 垃圾文件进 git、发布文件名文档不准、research 收集专家评论但 writer 全删、research 章节标题中英混用。

## 方案 E：CSV 单一状态账本（用户提出并定稿字段）

### 账本文件 `_pipeline/events.csv`

一行 = 一个事件（或一个"无事件"日期）。**按维护日期倒序**：最近维护的在最上面；新行作为块插入表头之下，块内按（收录日期, 事件编号）升序。所有写操作经 helper 整文件重写（规模数百行，无性能问题）。UTF-8。手工改动用 CLI 或文本编辑器，不要用 Excel 保存。

| 字段 | 格式 | 谁写 / 何时 | 说明 |
|------|------|------------|------|
| 维护日期 | YYMMDD | tracker，收录时 | 哪天的维护运行收录的（运行事实，写后不变）；手工补录填当天。替代 `.state` |
| 收录日期 | YYMMDD | tracker，收录时 | 事件归属日期。全库连接键：与 `events/YYMMDD.md`、工件文件名、发布文件名一致 |
| 事件编号 | 数字 N | tracker，收录时 | 日期内序号，同工件文件名的 N。"无事件"行留空 |
| 标题 | 文本 | tracker，收录时 | 即 `events/YYMMDD.md` 中 `## N. 标题` 的标题，也是工件文件名组成部分 |
| 状态 | 枚举 | CLI / publisher / 自动对账 | `candidate` → `selected` → `research` / `draft-vN` / `review-vN`（中间态，自动对账回填）→ `published` / `abort`；整日期无事件为 `无事件`。替代侧车 + `done-dates.txt` |
| 发布日期 | YYMMDD | publisher，发布时 | 实际发布日（区别于文章 frontmatter `date:` = 事件发生日），唯一记录真实发布时刻处 |
| 发布标题 | 文本 | publisher，发布时 | 发布文章的 frontmatter title |
| 经验提取 | 空/待提取/已提取 | publisher 置待提取；curate 置已提取 | 替代 `harvest-queue.txt` |

### 对账（reconcile）

子代理只写工件文件、不跑代码，所以中间态不靠人也不靠 prose 记忆：对账**内建于 `ledger.py` 的读路径**——任何状态读取（CLI 全部子命令、publisher、`finalize_event`）先对账再返回，不存在"要记得跑"的独立对账步骤（orchestrator 忘不掉一个不存在的步骤）。对账逻辑：对每个非终态行扫描 `research/ draft/ review/` 的 `{收录日期}-{事件编号}-*` 文件，按最高阶段 + 最大版本号回填状态（`review-v2` > `draft-v3` > `research`）；终态行（published/abort/无事件）与 candidate（无工件时）不动；有变化则写回 CSV。幂等、纯文件系统推导——CSV 落后只影响裸看文件的显示，任何经代码的决策进门先自愈，陈旧不累积。skill 中写明：查看状态一律 `pipeline_cli.py status`，不要裸读 CSV。

### 载体裁撤与保留

**删除**：`events/*-status.txt` 侧车（含 `record_selected/aborted/published` 的侧车读写实现）、`done-dates.txt` + `mark_done/_read_done_dates`、`.state` + `get_state/set_state/set_last_tracked_date`、`harvest-queue.txt`。

**保留**：`events/YYMMDD.md` —— **内容文件**（brief、来源链接）。用户在批准关卡阅读它，orchestrator 派发 research 时从中取 brief/来源放进 prompt，research 子代理也可直接读；但 Python 状态逻辑不再解析它（事件枚举/状态/归档判断全部来自 CSV），文件丢失只损失介绍文字，不再卡死流程。无事件日期不再写空存根 md（CSV 一行"无事件"即为"查过"记录）。`.tracker-state.json` —— 微博 API 游标，非管线状态，内部文件。

### 代码

- 新增 `src/utils/ledger.py`：CSV 读写（csv 模块，quoting 处理标题逗号）、行查询/更新、块插入（倒序规则）、reconcile。`event_status/event_statuses/is_date_terminal` 改由账本实现（`event_statuses(date)` = 该收录日期所有行；日期完结 = 全部行终态）。
- 新增 `src/pipeline_cli.py` 子命令：
  - `status` —— reconcile 后打印对齐状态表（替代 `pipeline_summary`；"最后追踪日期" = 账本首块的维护日期/收录日期范围）
  - `select <收录日期> <N...>` —— candidate → selected
  - `abort <收录日期> <N...>` —— 置 abort 并触发按事件归档（方案 A 的 `finalize_event`）
  - `add <收录日期> <N> <标题>` —— 手工补录（tracker 限流时的工作流；维护日期=当天）
  - `archive [<收录日期> [N]]` —— 手动归档入口（无参 = 全量清扫，接替 `--backfill`）
- `src/tracker.py`：写 events md（内容职责不变）的同时写账本行；无事件日期只写"无事件"行、不写 md；不再写 `.state`。
- `src/publisher.py`：`record_published` 改为账本更新（状态/发布日期/发布标题/经验提取=待提取）；`_post_slug` 改读账本。
- 一次性迁移脚本 `src/migrate_ledger.py`：从现有侧车 + 工件文件 + 归档 + `source/_posts` frontmatter + done-dates 生成初始 CSV（历史行维护日期不可考则留空）；随后 `git rm` 侧车、done-dates、.state、harvest-queue；存量空存根 md（260322/260323/260510/260515）转为"无事件"行后删除。脚本用完即删。

### 文档/skill 同步

- `blog-orchestrator/SKILL.md`：1a 用 `pipeline_cli.py status`；1c 批准用 `select`；关卡增加 "abort N" 选项用 `abort`；python 片段全部移除。
- `blog-curate/SKILL.md`：harvest 队列来源改为账本"经验提取=待提取"的行，处理完置"已提取"。
- `CLAUDE.md`：Pipeline Overview 重写（events.csv 为状态唯一权威、events md 为纯内容、pipeline check = 账本非终态行；删除侧车/done-dates/.state/harvest-queue 描述）。

### 测试

`test_ledger.py`（新）：读写/倒序插入/含逗号标题 round-trip/reconcile 各阶段与版本号/终态判断/无事件行。`test_pipeline_status.py`、`test_harvest_queue.py`、`test_publisher.py`、`test_tracker*.py` 相应改写。

## 方案 A：按事件归档（基于账本，较 v1 简化）

**语义**：事件一到终态（published/abort）立即归档其专属工件；`events/YYMMDD.md` 保留到全日期终态（全部行终态）再归档。零事件日期无文件可归档，无特殊分支（v1 的"零事件日期终态化"与"events 文件缺失"分支整体删除——终态判断已与文件无关）。

- `archive_event(收录日期, N)`：移动 `research/ draft/ review/` 下 `{date}-{n}-` 前缀条目（含 `-assets/`）入归档；幂等、不覆盖；前缀含结尾连字符防 n=1 误匹配 n=10。
- `finalize_event(收录日期, N)`：账本状态终态 → `archive_event`；随后若日期全终态 → 归档 events md。
- `publisher.py` 发布后调 `finalize_event`；abort 经 `pipeline_cli.py abort` 触发。
- `archiver.py` 并入 `pipeline_cli.py archive`（全量清扫模式接替 `--backfill`；上线跑一次归档 260524-2 滞留工件）。
- 测试：只动目标事件（含 assets）/共享 md 保留至日期终态/前缀不互撞/非终态 no-op/幂等/publish 触发归档。

## 方案 B：TAG-PROPOSAL 机制

（不变，与账本无耦合）

- `blog-write/SKILL.md` Tags 节重写：删"停下来问用户"；禁止凑数选边缘标签；贴切已注册标签不足 2 个或重要主题无标签时，写 `<!-- [TAG-PROPOSAL]: 标签名 — 理由 -->`（一条一注释，可多条）；已注册数+提案数 ≥ 2。
- `src/linter.py`：有提案时豁免"tags 为空"；未注册标签照旧违规。
- `src/publisher.py`：草稿残留 `[TAG-PROPOSAL]` → 拒绝发布并提示裁决路径（批准：入 `src/tags.yml` + frontmatter，删注释；否决：删注释）。
- `blog-review/SKILL.md`：提案逐条转录进 review 文件专门小节。
- `blog-orchestrator/SKILL.md` 4b-ii：列出提案请用户裁决；批准后 orchestrator 机械修改 tags.yml + frontmatter 并删注释。
- 测试：空 tags+有提案通过 / 空 tags 无提案违规 / 未注册仍违规 / 含提案拒绝发布。

## 方案 C：template.md 为格式唯一权威

（不变）

- 重写 `source/_drafts/template.md` 为现行规范骨架+规则注释（date 无时间、categories 单字母、tags 注册制+TAG-PROPOSAL 指引、概述+####子节、信息来源行格式、舆论仅限具体数据、相关内容仅限一般性材料、`<font>` 三色、资产嵌入）。`render_drafts: false` 已确认不渲染。
- `blog-write/SKILL.md`：Draft Format/Inline Formatting/Assets 三节收缩为"先完整阅读 template.md"；保留流程与判断规则。
- `blog-review/SKILL.md`：先读 template.md，逐节对照，格式偏差记 ISSUES。
- `blog-orchestrator/SKILL.md`：write/review 派发 prompt 必须以"先读对应 SKILL.md、notes.md、template.md"开头。
- `CLAUDE.md` Post Format 指向 template.md（格式）+ blog-write skill（判断）。
- `blog-curate/SKILL.md` 促升指南补：机械规则→linter；格式规则→template.md；判断规则→SKILL.md。

## 方案 D：杂项一致性修正

1. `.env` 路径：orchestrator 与 CLAUDE.md 明确为 `src/.env`。
2. 发布文件名：文档改为 "`source/_posts/YYMMDD.md`（同日第二篇起为 `YYMMDD-N.md`）"。
3. `blog-research/SKILL.md`：自身写明"全文简体中文"；输出章节标题改中文 `## 事实 / ## 当事方 / ## 信息来源`（CLAUDE.md 同步）；不再收集具名专家评论，只收法条/司法解释/判决等事实性法律信息。存量文件不回改。
4. `git rm _pipeline/events/--date.md`（霞浦事件已于 260325-3 处理发布）。
5. orchestrator 5b 措辞改为 build + deploy 链。
6. `_pipeline/category-tag-heatmap.csv`（2605 月度总结画图的工作文件）移入 `_pipeline_archive/summary/`。【已完成 2026-07-11】
7. `done-dates.txt` 的删除在方案 E 迁移步骤中执行（现行代码仍在读写它，提前删会被 `mark_done` 重建）。

## 不做的事

- 不改 linter 对格式规则的覆盖（除 B 的标签逻辑）。
- 不回改存量 research/draft 文件。
- 不动 blog-summary（审计无冲突）。
- 不做未完结事件超时提醒等新功能。
- 不拆分/轮转账本 CSV（数百行/年，无必要）。

## 实施顺序

1. **E**：ledger 模块 + pipeline_cli + tracker/publisher 接入 + 迁移脚本 + 测试（TDD）
2. **A**：archive_event/finalize_event（基于账本）+ 测试
3. **B**：linter/publisher 代码 + 测试；skill 文案
4. **C**：template.md 重写 + skill/CLAUDE.md 指针
5. **D**：文档修正 + git rm
6. 全量测试；跑迁移脚本与全量归档清扫；更新 CLAUDE.md
