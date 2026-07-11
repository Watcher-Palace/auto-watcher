# 设计：按事件归档 · TAG-PROPOSAL 机制 · 模板唯一权威 · 一致性修正

日期：2026-07-11
状态：待用户批准

## 背景

日常维护中暴露四类问题：

1. 归档以"日期"为原子单位——日期下任一事件未完结，已完结事件的文件也无法归档（260524-2 已发布却因 260524-1 卡在 v1 而滞留）。另外 `events/{date}.md` 缺失或为空时日期永远无法完结（260524 缺失已人工重建；260322/260323/260510/260515 为空事件日期，永远滞留）。
2. writer 从 `src/tags.yml` 硬凑边缘关联标签，从不提出新标签——因为 skill 要求"停下来问用户"，而子代理无法中途问人；linter/publisher 又硬性拒绝未注册标签。
3. writer 不按模板写、reviewer 不指出——`source/_drafts/template.md` 是三月的老骨架，与 blog-write SKILL.md 的规范互相矛盾（独立前情/后续节、date 带时间成分）；orchestrator 派发 prompt 只带 5 个参数不带约束；review skill 没有任何格式规范可对照。
4. 全量审计发现的其余漂移：`.env` 路径写错（实际 `src/.env`）、abort 流程在所有 skill 中缺失、`--date.md` 垃圾文件进了 git、发布文件名文档不准（同日第二篇是 `YYMMDD-N.md`）、research 收集专家评论但 writer 全删、research 章节标题中英混用。

## 方案 A：按事件归档

**语义**：事件一到终态（published/abort）立即归档其专属文件；共享文件（`events/{date}.md`、`{date}-status.txt`）保留到全日期终态——pipeline 扫描和 `event_status()` 依赖它们。`done-dates.txt` 语义不变。

`src/utils/pipeline.py`：

- 新增 `archive_event(date_str, n, pipeline_dir, archive_dir) -> list[Path]`：把 `research/`、`draft/`、`review/` 下名字以 `{date}-{n}-` 开头的条目（含 `-vN.md`、`-assets/` 目录、research `.md`）移入归档同名子目录。幂等、不覆盖已存在目标（与 `archive_date` 相同约定）。前缀必须含结尾连字符，避免 n=1 误匹配 n=10。不动 `events/` 阶段。
- 新增 `finalize_event(date_str, n, ...) -> bool`：`event_status(date,n)` 为 published/abort 时调 `archive_event`；随后照旧调 `finalize_if_terminal(date)` 并返回其结果（全日期终态时收尾共享文件并写 done-dates）。
- 修改 `is_date_terminal`：events 文件**缺失** → False（保持"无法判定"语义）；文件**存在但零事件** → True（空真），使空事件日期可归档。实现上自查 `events_path.exists()`，`event_statuses()` 返回类型不变。

`src/publisher.py`：第 98 行 `finalize_if_terminal(date_str)` 改为 `finalize_event(date_str, n)`。harvest-queue 追加保持在归档之前（curate 已兼容两个位置）。

`src/archiver.py` CLI：

- `python src/archiver.py <YYMMDD> <N>` — 单事件 finalize（abort 流程的入口）。
- `python src/archiver.py <YYMMDD>` — 行为不变（整日期）。
- `--backfill` 扩展：除 done-dates 清扫外，遍历所有未完结日期——对每个终态事件调 `finalize_event`，对零事件日期调 `finalize_if_terminal`。上线后跑一次即可归档 260524-2 的文件和四个空事件日期。

`blog-orchestrator/SKILL.md`：补 abort 流程——1c/4b 关卡增加 "abort N" 选项：`record_aborted(date, n)` 后运行 `python src/archiver.py <date> <N>`。

`CLAUDE.md`：Pipeline Overview 补一行按事件归档语义与 `_pipeline_archive/` 说明。

**测试**（`src/tests/test_archiver.py` 扩展 + `test_publisher.py`）：archive_event 只动目标事件（含 assets 目录）、共享文件不动；n=1/n=10 前缀不互撞；finalize_event 非终态为 no-op；单事件终态归档后日期仍开放（不进 done-dates、events md 保留）；最后一个事件终态 → 日期收尾（done-dates + 共享文件归档）；零事件日期 → terminal 且可归档；events 文件缺失 → 不 terminal（260524 回归用例）；重复运行幂等；publish 触发按事件归档。

## 方案 B：TAG-PROPOSAL 机制

**语义**：frontmatter 只放真正贴切的已注册标签；需要新标签时 writer 在草稿中留结构化提案注释，人工关卡裁决；linter/publisher 对未注册标签保持硬拒绝。

- `blog-write/SKILL.md` Tags 节重写：删除"停下来问用户"；禁止为凑数选边缘关联标签；贴切的已注册标签不足 2 个、或有重要主题无标签覆盖时，在 frontmatter 之后写 `<!-- [TAG-PROPOSAL]: 标签名 — 理由 -->`（一条一个注释，可多条）；已注册标签数 + 提案数合计须 ≥ 2。
- `src/linter.py`：识别 `<!-- [TAG-PROPOSAL]: ... -->`；存在提案时豁免"tags 为空"违规；未注册标签照旧违规（提案在注释里不进 frontmatter）。
- `src/publisher.py`：发布前若草稿仍含 `[TAG-PROPOSAL]` → 拒绝发布并提示裁决路径（批准：标签加入 `src/tags.yml` 相应分组 + frontmatter，删注释；否决：删注释）。
- `blog-review/SKILL.md`：要求 reviewer 将草稿中的 TAG-PROPOSAL 逐条转录到 review 文件（专门小节），确保人工关卡可见。
- `blog-orchestrator/SKILL.md` 4b-ii：报告 review 状态时列出提案，请用户裁决；批准后由 orchestrator 直接机械修改 `tags.yml` + 草稿 frontmatter 并删注释（机械编辑，非管线阶段，不违反人工关卡原则）。

**测试**：linter——空 tags + 有提案 → 通过；空 tags 无提案 → 违规；未注册标签仍违规。publisher——含提案的草稿拒绝发布。

## 方案 C：template.md 为格式唯一权威

**语义**（用户指定方向）：`source/_drafts/template.md` 同步为最新格式规范并成为唯一权威；skill 不再自带格式块，只指向它。`render_drafts: false` 已确认，模板永不渲染发布。

- 重写 `source/_drafts/template.md`：以现行 blog-write Draft Format 为准——frontmatter 字段规则（date 只写 YYYY-MM-DD 无时间、categories 单字母、tags 只用已注册 + TAG-PROPOSAL 指引）、章节骨架（概述 + #### 子节；信息来源行格式；舆论仅限具体数据否则整节删除；相关内容仅限一般性/对比性材料）、结构规则（案件相关内容全部进概述子节，不建独立前情/后续）、`<font>` 三色约定、资产嵌入写法。旧骨架中与现行规范矛盾的内容全部清除。
- `blog-write/SKILL.md`：Draft Format / Inline Formatting / Assets 三节收缩为一句"先完整阅读 `source/_drafts/template.md`（格式唯一权威）"；保留流程与判断规则（Modes、追踪到今天、蓝字规则、修订协议、Style Rules、Categories 边界、Tags 协议、lint 关卡）。
- `blog-review/SKILL.md`：第 6 条具体化——先读 template.md，逐节对照检查，结构/格式偏差必须记为 ISSUES。
- `blog-orchestrator/SKILL.md`：write/review 派发块加硬指令——子代理 prompt 必须以"先读 `.claude/skills/blog-{write,review}/SKILL.md`、对应 `notes.md`、`source/_drafts/template.md`"开头（子代理自动获得 CLAUDE.md，但不会自动加载 skill）。
- `CLAUDE.md` Post Format 节：格式权威指向 template.md，判断规则仍在 blog-write skill；保留"不要在本文件复制规范"的反漂移语。
- `blog-curate/SKILL.md` 促升指南补一行：机械规则 → linter；格式/结构规则 → template.md；判断类规则 → SKILL.md。

## 方案 D：杂项一致性修正

1. `.env` 路径：orchestrator Environment 节与 CLAUDE.md Environment Variables 节明确为 `src/.env`。
2. 发布文件名：CLAUDE.md 与 orchestrator 改为 "`source/_posts/YYMMDD.md`（同日第二篇起为 `YYMMDD-N.md`）"。
3. `blog-research/SKILL.md`：① 自身写明"全文简体中文"；② 输出模板章节标题改中文 `## 事实 / ## 当事方 / ## 信息来源`（用户已确认），CLAUDE.md Stage 2 同步；③ 搜索策略第 4 步和覆盖标准改为只收法条、司法解释、判决等事实性法律信息，不再收集具名专家评论（用户已确认）。存量 research 文件不回改。
4. `git rm _pipeline/events/--date.md`（其中霞浦事件已在 260325-3/260326-1 下处理并发布）。
5. orchestrator 5b 措辞改为 build + deploy 链。

## 不做的事

- 不改 linter 对格式规则的覆盖范围（除 B 的标签逻辑）；机械规则促升继续走 curate 流程。
- 不回改存量 research/draft 文件。
- 不动 blog-summary（审计无冲突）。
- 不实现"未完结日期超时提醒"之类的新功能。

## 实施顺序

1. A（纯代码 + 测试，TDD）
2. B（linter/publisher 代码 + 测试，TDD；随后三个 skill 文案）
3. C（template.md 重写 → 三个 skill + CLAUDE.md 指针）
4. D（文档修正 + git rm）
5. 跑全量测试；`archiver.py --backfill` 清扫存量（260524-2 文件、四个空事件日期）
