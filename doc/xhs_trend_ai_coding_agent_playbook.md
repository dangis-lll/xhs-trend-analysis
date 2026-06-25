# xhs-trend-analysis AI Coding Agent 实施任务书
## ——工程约束、任务顺序、验收标准与输出格式

## 0. Agent 角色

你是本项目的代码维护 Agent，不是自由架构重写 Agent。

你的职责是：

- 阅读现有实现和测试；
- 在最小改动范围内修复指定问题；
- 保持现有 CLI、GUI 和数据输出兼容；
- 为每个改动补测试；
- 不扩展任务范围；
- 不引入未被明确要求的基础设施。

本任务书优先级高于项目中较旧的架构草案。

---

# 1. 总体工程约束

## 1.1 禁止事项

除非任务明确要求，否则禁止：

- 引入 SQLite；
- 引入 ORM；
- 引入大型框架；
- 重写整个 GUI；
- 修改采集边界；
- 实现真实详情页抓取；
- 删除旧输出；
- 修改无关模块；
- 批量重命名 schema；
- 让 LLM 写入事实层；
- 在一个任务中顺带完成下一阶段工作。

## 1.2 必须遵守

每次任务必须：

1. 先阅读相关代码、调用方和现有测试。
2. 列出任务影响范围。
3. 保持现有 CLI 参数兼容。
4. 下游模块不得覆盖上游 artifact。
5. Append 型写入必须考虑同日重跑。
6. 新增逻辑必须补 unittest。
7. 写入失败不得留下半截文件。
8. 修改 pipeline 时检查 GUI、CLI、scheduler 三个入口。
9. 保留兼容层，除非任务明确要求移除。
10. 完成后报告测试结果和剩余风险。

---

# 2. 任务执行格式

每次开始任务时，先输出：

```text
任务目标：
涉及文件：
现有调用链：
预计行为变化：
兼容风险：
测试计划：
明确不修改的内容：
```

修改完成后输出：

```text
已修改文件：
核心实现：
数据契约变化：
兼容处理：
新增测试：
测试命令：
测试结果：
尚未解决：
建议下一任务：
```

---

# 3. 任务顺序

必须按以下顺序推进，除非项目负责人明确改变顺序：

```text
T1 Quality Gate
T2 clean base 不可变
T3 Memory Append 幂等
T4 共享 Step Registry
T5 低风险技术债清理
T6 clean observations
T7 Evidence 跨关键词聚合
T8 Note/Observation schema
T9 完整 PipelineRunner
T10 Current State / Rollup / Cooling
```

不得跳过 T1～T3 直接做数据库或完整 Runner。

---

# 4. T1：修复 Quality Gate

## 4.1 目标

让 data quality 的结构化字段真正控制：

- market report；
- memory update；
- current_state 更新。

## 4.2 涉及文件

优先检查：

```text
analysis/data_quality.py
pipeline/evaluate_data_quality.py
pipeline/generate_market_report.py
pipeline/update_memory.py
pipeline/status.py
tests/
```

## 4.3 行为要求

### invalid

- 保留 data quality JSON；
- 不生成普通 market report；
- 不调用普通 LLM 市场分析；
- 不更新 memory；
- 不更新 current_state；
- 返回可识别的 skipped 结果；
- pipeline status 记录原因。

### low

- 允许生成弱报告；
- 报告必须显式声明样本不足；
- 不更新 current_state；
- 可以保存 daily summary，但必须标记 low confidence；
- 不产生强 rising/cooling judgment。

### medium / high

- 保持现有正常行为。

## 4.4 独立模块保护

即使用户直接执行：

```text
python -m pipeline.generate_market_report
python -m pipeline.update_memory
```

也必须执行 gate，不能只依赖 GUI 或 scheduler。

## 4.5 实现要求

推荐新增小型辅助函数：

```python
load_quality_gate(domain_id, date_str)
```

返回结构化对象：

```python
{
    "quality_level": "...",
    "report_allowed": bool,
    "memory_update_allowed": bool,
    "reasons": [...]
}
```

不要重复解析逻辑。

## 4.6 测试

必须覆盖：

1. invalid：report skipped；
2. invalid：memory skipped；
3. low：生成弱报告；
4. low：current_state 不更新；
5. high：保持正常；
6. 缺失 quality 文件时行为明确；
7. malformed quality 文件时行为明确。

## 4.7 验收

- invalid 不生成普通报告；
- low 不覆盖 current_state；
- 独立执行无法绕过；
- 测试通过；
- 未修改 evidence 和 clean schema。

---

# 5. T2：让 clean base 不可变

## 5.1 目标

基础 clean artifact 生成后，只允许读取，不允许 downstream 覆盖。

## 5.2 优先检查

```text
pipeline/clean_notes.py
pipeline/generate_evidence.py
pipeline/compute_search_page_signals.py
pipeline/apply_manual_corrections.py
pipeline/analyze_images.py
storage/paths.py
tests/
```

## 5.3 第一阶段策略

保留兼容输出，但区分：

```text
YYYY-MM-DD_clean_notes_base.*
YYYY-MM-DD_clean_notes_corrected.*
YYYY-MM-DD_search_signals.json
YYYY-MM-DD_evidence.jsonl
```

如当前命名迁移成本较大，可以：

- 保留原 `clean_notes` 作为 base；
- 新增 corrected/derived 文件；
- 禁止 downstream 回写原 clean。

## 5.4 必须修改

- `generate_evidence` 不回写 clean；
- `compute_search_page_signals` 不回写 clean；
- manual correction 不覆盖 base；
- image enrichment 不覆盖 base；
- downstream 缺少字段时，从 derived artifact 读取或本地计算。

## 5.5 不允许

- 同时重做 Note/Observation schema；
- 同时迁移数据库；
- 删除旧 clean 输出；
- 修改所有 downstream。

## 5.6 测试

1. 运行 clean，记录 base hash；
2. 运行 signals，hash 不变；
3. 运行 evidence，hash 不变；
4. 运行 corrections，base hash 不变；
5. 重跑 downstream，输出稳定；
6. 旧 CLI 仍可执行。

---

# 6. T3：Memory Append 幂等

## 6.1 目标

同一 domain、同一日期重复运行，不重复追加长期记录。

## 6.2 优先检查

```text
pipeline/update_memory.py
analysis/memory.py
analysis/wiki_memory.py
analysis/trend_store.py
storage/
tests/
```

## 6.3 记录类型

至少检查：

- judgments.jsonl；
- conflict_resolution_queue.jsonl；
- trend_events.jsonl；
- wiki log；
- rule candidates。

## 6.4 ID 规则

每条记录必须有稳定业务 ID，例如：

```python
record_id = stable_hash({
    "domain_id": domain_id,
    "date": date_str,
    "record_type": record_type,
    "target": target,
    "state": state,
})
```

不得使用当前时间作为 ID 主体。

## 6.5 写入语义

```text
不存在 → insert
已存在且内容相同 → no-op
已存在且内容变化 → replace/update
```

如使用 JSONL，可以实现：

```text
read → index by record_id → merge → atomic rewrite
```

当前规模允许全量重写，不需要数据库。

## 6.6 Atomic Write

新增统一工具：

```text
storage/atomic_io.py
```

提供：

- atomic_write_text；
- atomic_write_json；
- atomic_write_jsonl；
- atomic_write_csv。

使用临时文件后 replace。

## 6.7 测试

同一天运行两次：

- judgments 数量不变；
- conflicts 数量不变；
- trend events 数量不变；
- wiki log 不重复；
- 内容变化时更新；
- 写入异常不留下损坏文件。

---

# 7. T4：共享 Step Registry

## 7.1 目标

只统一步骤定义，不立即统一完整执行器。

## 7.2 新增

```text
pipeline/step_registry.py
```

## 7.3 Step Schema

建议：

```python
@dataclass(frozen=True)
class PipelineStep:
    name: str
    module: str
    order: int
    optional: bool
    requires: tuple[str, ...]
    produces: tuple[str, ...]
    flag_name: str | None = None
```

## 7.4 修改

```text
xhs_trend_app.py
pipeline/run_scheduled.py
```

两个入口都从 registry 生成 plan。

## 7.5 禁止

- 立即重写 subprocess 执行；
- 立即抽完整 Runner；
- 改动 GUI 布局；
- 修改所有命令参数。

## 7.6 必须删除

- `commands[3]`
- `insert_at = 7`
- 独立 DEFAULT_STEPS
- 依赖数组位置启用 optional step

## 7.7 测试

- 相同配置生成相同 plan；
- optional steps 开关生效；
- 顺序唯一；
- requires/produces 可检查；
- GUI 和 scheduler 使用同一 registry。

---

# 8. T5：低风险技术债清理

在 T4 后执行。

任务包括：

- 统一 `load_domains_config`；
- 统一 `get_domain`；
- 修复 `interaction_count` 语义；
- 标记 `analyze_with_llm` deprecated；
- 统一 LLM 主入口；
- 删除或重命名 `semantic_dedupe_placeholder`；
- 合并重复 CSV upsert 工具；
- 清理模块级无必要全局规则加载。

每项独立小提交，不与 Observation 迁移混合。

---

# 9. T6：新增 clean observations

## 9.1 目标

保留同一 note 在多个关键词下的全部搜索观察。

## 9.2 输出

```text
processed/YYYY-MM-DD_clean_observations.jsonl
```

## 9.3 Observation Schema

```json
{
  "observation_id": "obs_...",
  "run_id": "run_...",
  "date": "2026-06-25",
  "domain_id": "domain",
  "keyword": "keyword",
  "rank": 2,
  "note_global_id": "note_...",
  "note_id": "...",
  "link": "...",
  "title": "...",
  "author": "...",
  "like_count": 0,
  "collect_count": 0,
  "comment_count": 0,
  "crawl_time": "...",
  "source": "search_page"
}
```

## 9.4 要求

- 标准化；
- 不按 note 去重；
- 可按完全重复 observation 去重；
- 保留 keyword/rank；
- 生成稳定 observation_id；
- 保持旧 clean_notes 兼容。

---

# 10. T7：Evidence 跨关键词聚合

## 10.1 输入

优先读取 clean observations。

## 10.2 聚合

```text
group by note_global_id
```

## 10.3 输出字段

```json
{
  "evidence_id": "ev_...",
  "note_global_id": "note_...",
  "date": "...",
  "domain_id": "...",
  "keywords": [],
  "best_rank": null,
  "all_ranks": [],
  "source_observation_ids": [],
  "metrics_snapshot": {},
  "topic": {},
  "content_patterns": [],
  "quality_flags": []
}
```

## 10.4 规则

- keywords 去重；
- all_ranks 保留 keyword/rank 对；
- best_rank 取有效最小值；
- 缺失 rank 不参与 min；
- 同日同 note 一条 evidence；
- 跨日 evidence_id 不同；
- note_global_id 跨日相同；
- 不回写 clean。

## 10.5 测试

- 两关键词；
- 重复关键词；
- 缺失 rank；
- 不同 rank；
- 跨日；
- note_id 缺失；
- link token 变化。

---

# 11. T8：正式 Note/Observation Schema

此任务只在 T6、T7 稳定后执行。

## 11.1 Note

稳定实体字段。

## 11.2 Observation

时点和搜索上下文字段。

## 11.3 Annotation

topic、pattern、entity、manual correction。

## 11.4 迁移顺序

1. evidence；
2. keyword coverage；
3. search visibility；
4. rank trend；
5. signals；
6. memory；
7. report context。

不得一次性修改全部 downstream。

---

# 12. T9：完整 PipelineRunner

仅在共享 registry 和测试稳定后进行。

职责：

- 构建 plan；
- 检查依赖；
- 执行 subprocess；
- success/fail/skipped；
- optional step；
- status；
- GUI callback；
- scheduler；
- run_id；
- artifact manifest。

必须保持单模块 CLI 可独立执行。

---

# 13. T10：Current State / Rollup / Cooling

## 13.1 Current State

新增：

```text
memory/current_state.json
```

Markdown 由 JSON 渲染。

## 13.2 LLM Context

字段改为：

```text
previous_current_state
previous_state_as_of
```

新增：

```text
recent_week_rollup
recent_month_rollup
period_comparison
```

## 13.3 Cooling

使用有效时间序列，不使用单纯 Top N 消失。

---

# 14. 测试命令

遵守项目现有环境和 AGENTS.md。

基础命令：

```powershell
conda run -n pt python -m unittest discover -s tests
```

每个任务还应提供定向测试命令，例如：

```powershell
conda run -n pt python -m unittest tests.test_quality_gate
```

不得声称测试通过，除非实际执行。

---

# 15. 每个任务的停止条件

出现以下情况时停止扩大修改范围，并在报告中说明：

- 需要改变多个未相关 schema；
- 需要重写 GUI 才能完成；
- 需要数据库才能继续；
- 现有测试与代码行为冲突；
- 找不到稳定兼容方式；
- 任务会影响采集主链路；
- 发现历史数据迁移需求。

停止不等于放弃。应提交当前安全部分，并列出后续设计问题。

---

# 16. 第一项任务的完整 Agent Prompt

```text
你正在维护 xhs-trend-analysis 项目。

本次只完成 T1：修复 Data Quality Gate。

目标：
1. generate_market_report.py 必须读取当天 data_quality.json。
2. report_allowed=false 时，不生成普通 market report，不调用普通 LLM 分析。
3. update_memory.py 必须读取 memory_update_allowed。
4. memory_update_allowed=false 时，不更新 current_state、长期 judgment 和长期趋势。
5. low 质量可以生成弱报告，但禁止 current_state 更新。
6. 模块被单独执行时 gate 也必须生效。
7. pipeline status 记录 skipped 和明确原因。
8. 缺失或损坏 quality 文件时行为必须明确并有测试。

约束：
- 不引入数据库。
- 不重构 GUI。
- 不修改 evidence。
- 不修改 clean 数据结构。
- 不修改 Note/Observation 模型。
- 保持现有 CLI 参数兼容。
- 不顺带清理其他技术债。

执行前先输出：
- 涉及文件；
- 当前调用链；
- 计划修改；
- 兼容风险；
- 测试计划。

必须新增 unittest：
- invalid report skip；
- invalid memory skip；
- low weak report；
- low current_state unchanged；
- high normal path；
- missing quality file；
- malformed quality file。

完成后输出：
- 修改文件；
- 核心实现；
- 行为变化；
- 测试命令；
- 测试结果；
- 未解决问题。
```

---

# 17. 完成定义

## T1 完成

- invalid 不生成普通报告；
- low 不更新 current_state；
- 独立运行不能绕过；
- 测试通过。

## T2 完成

- downstream 不覆盖 base clean；
- base hash 稳定；
- 旧输出兼容。

## T3 完成

- 同日重跑无重复副作用；
- atomic write 生效。

## T4 完成

- GUI 和 scheduler 共享步骤定义；
- 无数组魔数。

## T6/T7 完成

- observations 不丢；
- evidence 聚合完整。

## T9/T10 完成

- 统一 Runner；
- current_state 结构化；
- rollup 接通；
- cooling 时间序列化。
