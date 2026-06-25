# 小红书趋势分析项目：下一阶段开发行动报告
## ——给项目负责人看的版本

## 0. 这份报告解决什么问题

你现在已经拥有多轮架构审查，问题不在于“还缺不缺意见”，而在于：

- 哪些问题必须现在修；
- 哪些问题虽然正确，但不应该现在做；
- 每一步改完后，项目应达到什么状态；
- 什么时候继续，什么时候暂停；
- 如何避免 AI Coding 把项目带进全面重写。

本报告只回答“接下来实际怎么推进”。

---

# 1. 当前项目所处阶段

项目已经不是最初原型，而是处于：

> **功能链路已经形成，但数据契约、流程一致性和重跑安全性尚未稳定的 MVP 后期。**

当前已经具备：

- 搜索页采集；
- 清洗和基础去重；
- topic、content pattern、entity 等规则分析；
- evidence 生成；
- data quality；
- LLM 市场报告；
- memory、judgment、rollup；
- GUI、CLI、scheduled runner；
- 多 domain 隔离。

当前不适合继续优先扩展：

- 更多视觉分析；
- 真实详情页抓取；
- 更复杂 Agent；
- 更复杂自动规则发现；
- 数据库全面迁移；
- GUI 大改版。

因为这些功能都会继续建立在当前不稳定的数据链路上。

---

# 2. 下一阶段唯一主目标

下一阶段不是增加功能，而是把现有系统变成：

> **数据不乱、流程一致、低质量数据不会误导、同一天可以安全重跑的稳定版本。**

完成这一阶段后，项目才适合继续做长期趋势、数据库和更高级 Agent。

---

# 3. 当前最重要的六个问题

## 3.1 Data Quality 只是提示，没有真正控制流程

系统已经计算：

- `report_allowed`
- `memory_update_allowed`
- `quality_level`

但普通市场报告和 memory update 仍可能继续运行。

直接后果：

- 样本无效时仍可能生成正常报告；
- 低质量日可能污染 current_state；
- 长期判断会被偶发采集失败影响。

这是最先要修的问题，因为：

- 修改范围最小；
- 收益最直接；
- 风险最低；
- 可以快速建立“程序控制，而不是 prompt 自觉”的原则。

---

## 3.2 clean_notes 被多个步骤重复覆盖

当前 clean 文件既像“基础清洗结果”，又像“附加标签结果”，还可能被：

- manual corrections；
- search signal enrichment；
- evidence ID；
- image analysis；

继续覆盖。

直接后果：

- 文件 schema 随执行顺序变化；
- 重跑结果依赖上次执行到了哪里；
- 某一步失败后，很难判断 clean 文件当前是什么状态；
- GUI 和 scheduled runner 不同顺序可能得到不同数据。

这不是“文件多不多”的问题，而是上游事实被下游污染。

---

## 3.3 Memory 中存在重复追加风险

`judgments.jsonl`、冲突队列、趋势事件、wiki log 等存在 append 行为。

同一天重跑可能：

- 重复增加 judgment；
- 重复写 conflict；
- 重复写 wiki log；
- 让历史看起来像发生了多次事件。

这会直接破坏长期跟踪可信度。

---

## 3.4 GUI 与 scheduled runner 使用两套步骤定义

当前两个入口分别维护步骤顺序和可选步骤。

已经出现：

- 顺序不同；
- optional step 不一致；
- GUI 使用数组下标修改命令；
- scheduled runner 有独立默认列表。

完整重构 PipelineRunner 风险较高，因此下一步只先统一“步骤定义”，不立即统一整个执行器。

---

## 3.5 跨关键词信息会丢失

同一篇笔记可能同时出现在多个关键词下，但过早按 note 去重后，可能只保留：

- 第一个关键词；
- 一条 rank；
- 一份搜索观察。

直接后果：

- evidence 的 keywords 不完整；
- 无法计算搜索覆盖度；
- 无法分析同一笔记在不同关键词下的占位；
- 后续 trend 和 visibility 指标失真。

这个问题很重要，但不应该和 clean_notes 不可变同时大改。应在 clean 链路稳定后单独推进。

---

## 3.6 Report 与 Memory 存在循环依赖

当前逻辑是：

```text
上一版 current_state
→ 生成本日报告
→ 生成 market_analysis.json
→ update_memory
→ 形成新版 current_state
```

这意味着报告读取的是上一版状态，而 memory 又依赖报告结果。

它不是简单的“顺序写反了”，不能机械交换两个步骤。

当前阶段应先：

- 明确报告读取的是 `previous_current_state`；
- 限制 LLM 叙事直接影响长期事实；
- 暂时保留现有执行顺序。

---

# 4. 下一步开发顺序

## Sprint 1：最小化正确性修复

这一阶段只做三件事，不碰 Note/Observation 全面分层，也不重构完整 GUI。

---

## Task 1：修复 Quality Gate

### 要改什么

在以下入口增加硬校验：

- `pipeline/generate_market_report.py`
- `pipeline/update_memory.py`

### 目标行为

#### invalid

- 只保留 data quality 结果；
- 不生成普通市场报告；
- 不更新 memory；
- 不更新 current_state；
- pipeline status 标记 skipped。

#### low

- 可以生成弱报告；
- 报告必须明确样本不足；
- 不更新 current_state；
- 可以保留低置信度 daily summary。

#### medium / high

- 正常执行。

### 完成标准

- 单独执行报告模块也不能绕过 gate；
- 单独执行 memory 模块也不能绕过 gate；
- invalid、low、high 均有测试；
- 现有正常数据流程不受影响。

### 为什么第一项做

这是改动最小、最容易验证、收益最大的任务。

---

## Task 2：让 clean base 变成只读

### 第一阶段不做什么

暂时不：

- 全面新建数据库；
- 全面拆 Note/Observation；
- 重写所有 downstream；
- 删除旧 clean 输出。

### 先做什么

- `generate_evidence` 不再回写 clean 文件；
- `compute_search_page_signals` 不再回写 clean 文件；
- manual corrections 输出 corrected 版本；
- base clean 文件生成后只读。

临时建议：

```text
YYYY-MM-DD_clean_notes_base.*
YYYY-MM-DD_clean_notes_corrected.*
YYYY-MM-DD_search_signals.json
YYYY-MM-DD_evidence.jsonl
```

### 完成标准

- base clean hash 在 downstream 执行后不变化；
- evidence、signals、report 只读 clean；
- 同一天重复执行不会污染 base clean；
- 旧输出仍兼容。

---

## Task 3：修复 Memory Append 幂等性

### 要改什么

以下记录增加稳定 ID：

- judgment；
- conflict；
- trend event；
- wiki log；
- rule candidate。

建议字段：

```text
record_id
run_id
source_artifact_hash
created_at
```

### 判断 ID 示例

```text
judgment_id =
hash(domain_id + date + event_type + target + state)
```

### 写入行为

```text
不存在 → 新增
已存在且内容相同 → 跳过
已存在但内容变化 → 更新
```

### 完成标准

同一天完整重跑两次后：

- judgment 数量不增加；
- conflict 数量不增加；
- wiki log 不重复；
- trend event 不重复；
- current_state 不发生额外漂移。

---

# 5. Sprint 2：统一 Pipeline 定义，但不急着重构执行器

## Task 4：建立共享 Step Registry

新增：

```text
pipeline/step_registry.py
```

统一定义：

- step name；
- module；
- 顺序；
- requires；
- produces；
- optional；
- enabled condition。

GUI 和 scheduled runner 暂时仍保留各自执行代码，但都从 registry 生成步骤计划。

### 必须消除

- `commands[3]`
- `insert_at = 7`
- 两份 DEFAULT_STEPS
- 按数组下标启用 optional step

### 完成标准

- 相同配置下，GUI 与 scheduler 生成相同 step plan；
- 默认步骤顺序只有一份；
- optional step 按名称启用；
- 现有 GUI 可以继续运行；
- scheduled runner 可以继续运行。

---

## Task 5：清理低风险技术债

可以在 Sprint 2 后半段完成：

- 统一 `load_domains_config/get_domain`；
- 修复 `interaction_count` 语义；
- 删除或重命名 `semantic_dedupe_placeholder`；
- 标记旧 LLM 入口 deprecated；
- 合并重复 upsert 工具；
- 移除 GUI 中步骤魔数。

这些不是最影响结果的问题，但适合在步骤定义统一后清理。

---

# 6. Sprint 3：修复跨关键词数据正确性

这一阶段才正式开始动 Observation。

## Task 6：新增 clean observations 文件

建议新增：

```text
processed/YYYY-MM-DD_clean_observations.jsonl
```

该文件：

- 标准化字段；
- 不按 note 去重；
- 保留 keyword；
- 保留 rank；
- 保留 crawl_time；
- 保留互动快照；
- 生成 observation_id；
- 生成 note_global_id。

原有 clean_notes 暂时保留为 note-level 兼容视图。

---

## Task 7：Evidence 从 observations 聚合

聚合规则：

```text
group by note_global_id
```

输出至少包含：

```json
{
  "evidence_id": "ev_...",
  "note_global_id": "note_...",
  "keywords": ["关键词A", "关键词B"],
  "best_rank": 2,
  "all_ranks": [
    {"keyword": "关键词A", "rank": 2},
    {"keyword": "关键词B", "rank": 8}
  ],
  "source_observation_ids": ["obs_1", "obs_2"]
}
```

### 完成标准

- observation 保留多行；
- evidence 同日只生成一条；
- keywords 完整；
- all_ranks 完整；
- best_rank 正确；
- 缺失 rank 不报错；
- 跨日 evidence_id 不同；
- 跨日 note_global_id 相同。

---

## Task 8：正式定义 Note / Observation 数据契约

这时才开始稳定 schema：

### Note

表示笔记身份和相对稳定属性。

### Observation

表示一次搜索观察。

### Annotation

表示 topic、pattern、entity、manual correction。

迁移顺序：

1. evidence 使用 observations；
2. visibility 使用 observations；
3. keyword coverage 使用 observations；
4. rank trend 使用 observations；
5. note-level metrics 继续使用 note aggregate；
6. 最后再考虑是否迁移 SQLite 或 DuckDB。

---

# 7. Sprint 4：完整 Runner 和长期状态

只有前面稳定后才做。

## Task 9：抽完整 PipelineRunner

负责：

- execution plan；
- step dependency；
- success / fail / skipped；
- optional step；
- pipeline status；
- GUI callback；
- scheduled execution；
- run_id；
- artifact manifest。

---

## Task 10：Current State 结构化

新增：

```text
memory/current_state.json
```

Markdown 从 JSON 渲染，不再由程序反向解析 Markdown。

---

## Task 11：接通 Rollup

LLM input 增加：

- recent week rollup；
- recent month rollup；
- period comparison。

只使用有效数据日。

---

## Task 12：升级 Cooling 判断

不再只依赖“跌出 Top N”。

至少结合：

- 最近 7 个有效观测日；
- topic score；
- note count；
- rank visibility；
- keyword coverage；
- quality weight。

---

# 8. 你应该如何管理 AI Coding

## 8.1 一次只发一个任务

不要把 Sprint 1 三个任务同时交给 Agent。

推荐顺序：

```text
Quality Gate
→ clean base 不可变
→ memory append 幂等
```

每个任务独立提交、独立测试。

## 8.2 每次要求 Agent 先分析再修改

必须要求它先输出：

- 涉及文件；
- 输入和输出；
- 调用关系；
- 兼容风险；
- 计划新增的测试。

确认后再修改，或者让它在同一次任务中先分析、再按分析执行，但不得越界。

## 8.3 禁止顺手重构

每次都要明确：

- 不改无关模块；
- 不引入数据库；
- 不重写 GUI；
- 不修改采集边界；
- 不删除兼容输出；
- 不修改未要求的数据契约。

## 8.4 每次必须有测试结果

Agent 完成后必须报告：

- 修改文件；
- 修改原因；
- 新增测试；
- 测试命令；
- 测试结果；
- 未解决问题；
- 下一项任务建议。

---

# 9. 项目负责人验收清单

## Sprint 1 验收

- [ ] invalid 不生成普通市场报告
- [ ] low 不更新 current_state
- [ ] generate_evidence 不覆盖 clean
- [ ] compute_search_page_signals 不覆盖 clean
- [ ] 同日重跑 judgment 不重复
- [ ] 同日重跑 wiki log 不重复
- [ ] 全部单元测试通过

## Sprint 2 验收

- [ ] GUI 与 scheduler 步骤计划一致
- [ ] 默认步骤顺序只有一份
- [ ] 无步骤数组魔数
- [ ] optional steps 可配置
- [ ] GUI 仍可正常运行
- [ ] scheduled runner 仍可正常运行

## Sprint 3 验收

- [ ] 同一 note 多关键词 observation 不丢
- [ ] evidence keywords 完整
- [ ] all_ranks 完整
- [ ] best_rank 正确
- [ ] 跨日 note_global_id 稳定
- [ ] 旧 downstream 保持兼容

## Sprint 4 验收

- [ ] GUI 和 scheduler 共用 Runner
- [ ] current_state 有 JSON 主状态
- [ ] rollup 进入 LLM context
- [ ] cooling 使用时间序列
- [ ] signal 可追溯 evidence

---

# 10. 暂时不要做的事

在 Sprint 1～3 完成前，不建议：

- 全量迁移 SQLite；
- 引入 ORM；
- 重写 GUI；
- 实现完整自由 Agent；
- 扩展实际详情页抓取；
- 大规模视觉分析；
- 自动修改规则；
- 大规模 schema 重命名；
- 删除旧输出兼容层。

---

# 11. 数据库迁移的启动条件

只有出现以下情况中的两到三项，才评估 SQLite 或 DuckDB：

- observation 达到几十万或百万级；
- 跨日查询明显变慢；
- CSV 全量重写明显耗时；
- GUI 需要交互式历史筛选；
- signal/evidence/judgment 需要频繁 join；
- 多进程并发读写；
- 文件关系维护成本已经超过迁移成本。

---

# 12. 最终行动顺序

```text
1. Quality Gate
2. clean base 不可变
3. Memory Append 幂等
4. 共享 Step Registry
5. 清理低风险技术债
6. 新增 clean observations
7. Evidence 跨关键词聚合
8. Note / Observation 正式分层
9. 完整 PipelineRunner
10. Current State / Rollup / Cooling
```

下一步应立即启动：

> **Task 1：修复 Quality Gate。**

不要同时启动其他架构重构。
