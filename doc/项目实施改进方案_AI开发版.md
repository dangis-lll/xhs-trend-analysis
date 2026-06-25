# 小红书热点追踪调研工具实施改进方案（AI 开发版）

## 1. 项目最终定位

本项目不应定位为“全自动决策工具”，而应定位为：

> 基于小红书搜索页可见数据的市场局势分析工具。

它的核心任务是采集用户关注领域的小红书搜索结果页数据，长期追踪关键词、主题、账号、内容打法和互动结构的变化，并输出低幻觉、证据驱动的局势分析。

本项目可以发展成 agent 形态，但这个 agent 的重点不是“给建议”，而是：

- 自动采集搜索页数据。
- 自动清洗、去重、计算指标。
- 自动沉淀多天记忆。
- 自动复盘历史变化。
- 自动生成当前市场局势分析。
- 明确标注证据、置信度和数据边界。

建议类内容应降权，不应成为报告主体。

## 2. 当前能力判断

当前项目已经具备较好的底座：

- 多领域项目配置能力。
- 小红书搜索页采集能力。
- 搜索页卡片字段提取能力。
- DeepSeek 关键词扩展能力。
- 清洗、去重、基础指标计算能力。
- Markdown 日报生成能力。
- GUI 串联采集、清洗、分析、报告流程。

当前不足：

- 主要基于搜索页，无法稳定采集详情页。
- 不能可靠获取正文、评论、话题标签、完整图片、商品链接。
- 缺少长期记忆系统。
- 缺少账号、竞品、内容打法的结构化沉淀。
- 报告中 AI 解释比重较高，存在幻觉风险。
- 缺少“结论必须绑定证据”的强约束。
- 缺少面向不同领域的压缩记忆和按需召回机制。

## 3. 关键设计原则

### 3.1 搜索页优先，不依赖详情页

小红书详情页风控较强，不应将系统核心能力建立在详情页采集上。

主流程应只依赖搜索页可稳定获得的数据：

- 标题
- 作者
- 链接
- 笔记 ID
- 搜索关键词
- 搜索排名
- 点赞数
- 收藏数
- 评论数
- 分享数
- 图文/视频类型
- 封面 URL
- 搜索页可见文本

详情页只能作为可选增强：

- 默认关闭。
- 每个关键词只抽样前 3-5 条。
- 设置每日详情页总上限。
- 失败不影响主流程。
- 可提供人工详情补录入口。

### 3.2 AI 只做解释，不做自由判断

不能把原始数据整包交给 LLM 自由分析。正确流程应是：

```text
采集数据
-> 程序清洗和计算指标
-> 程序生成结构化分析对象
-> LLM 只基于结构化对象生成文字解释
-> 每条解释绑定证据、置信度和数据边界
```

所有结论必须满足：

```text
结论 = 可计算指标 + 样本证据 + 置信度 + 数据边界
```

如果证据不足，只能输出“待验证信号”，不能输出确定性判断。

### 3.3 多领域隔离

必须保持当前项目已有的多领域保存形式。

所有领域数据和记忆都应按领域隔离：

```text
projects/<domain>/
  raw/
  processed/
  reports/
  memory/
```

分析某个领域时，只读取该领域的记忆，不读取其他领域的详细记忆。

跨领域只允许共享通用规则，例如：

```text
memory_global/
  taxonomy.yaml
  report_schema.yaml
  analysis_rules.md
```

### 3.4 分层记忆和压缩

长期追踪后不能把所有历史塞进上下文。记忆系统必须分层：

- 原始数据层：长期归档，不进 LLM 上下文。
- 每日摘要层：短 JSON，用于中间计算。
- 周/月 rollup 层：压缩历史变化。
- current_state 层：当前领域最重要的压缩记忆。
- evidence 层：证据索引，按需召回。

每次 LLM 分析只读取：

- 当前领域 profile。
- 当前领域 current_state。
- 今日 metrics。
- 今日 top evidence 10-20 条。
- 最近 7 天或最近一个周 rollup。

禁止默认读取全部日报、全部历史 CSV 或全部原始笔记。

### 3.5 Pipeline-first，而不是默认 ReAct

本项目的默认形态应是 pipeline-first 的分析 agent，而不是 ReAct 工具调用型 agent。

默认运行方式应是：

```text
用户配置领域和关键词
-> Python pipeline 采集、清洗、计算、更新记忆
-> LLM 读取 pipeline 传入的结构化信号
-> LLM 输出受约束的 JSON 分析
-> Python 渲染报告并落盘
```

不建议让 LLM 在主流程中自主决定是否调用爬虫、是否读取文件、是否继续搜索、是否修改记忆。这样会降低稳定性，并增加幻觉和不可复现风险。

可以保留少量用户-AI交互入口，但它们应是辅助性的：

- 用户确认领域研究目标。
- 用户人工纠正主题、账号、实体分类。
- 用户手动补录少量详情页正文或评论摘要。
- 用户要求复查某个历史判断。
- 用户触发 memory lint 或 wiki 整理。

这些交互不应阻塞默认自动分析流程。

### 3.6 LLM 默认不调用 tool

涉及 LLM 的地方，默认不需要 tool 调用。

LLM 的默认角色是：

```text
受约束的分析器 / 解释器 / 文字生成器
```

不是：

```text
自主工具调用者 / 自主爬虫控制器 / 自主文件维护者
```

主流程中，所有工具动作都应由 Python 代码完成，包括：

- 文件读取和写入。
- 小红书搜索页采集。
- 数据清洗。
- 指标计算。
- 记忆更新。
- 报告渲染。

LLM 只接收已经整理好的结构化数据，并返回结构化分析结果。只有在开发者手动执行“探索模式”或“wiki 维护模式”时，才可以考虑让 AI agent 使用工具辅助阅读、整理或检查文件。

## 4. 推荐目录结构

```text
projects/<domain>/
  raw/
    YYYY-MM-DD/
  processed/
    YYYY-MM-DD_clean_notes.xlsx
    YYYY-MM-DD_metrics.json
    history_clean_notes.csv
  reports/
    daily/
  images/
    YYYY-MM-DD/
  knowledge-base/
  memory/
    profile.yaml
    current_state.md
    daily/
      YYYY-MM-DD_summary.json
    rollups/
      weekly_YYYY-Www_metrics.json
      weekly_YYYY-Www_summary.md
      monthly_YYYY-MM_metrics.json
      monthly_YYYY-MM_summary.md
    entities/
      authors.csv
      keywords.csv
      topics.csv
      brands_or_ips.csv
      product_candidates.csv
    patterns/
      content_patterns.csv
      title_templates.csv
      visual_patterns.csv
    trends/
      keyword_daily.csv
      topic_daily.csv
      author_daily.csv
      trend_events.jsonl
    evidence/
      YYYY-MM-DD_evidence.jsonl
    judgments/
      judgments.jsonl
    wiki/
      index.md
      log.md
      schema.md
      domain_overview.md
      topics/
      authors/
      patterns/
```

全局规则：

```text
memory_global/
  taxonomy.yaml
  report_schema.yaml
  analysis_rules.md
  wiki_schema.md
```

### 4.1 LLM Wiki 可借鉴结构

`LLM_Wiki.md` 的核心思想可以借鉴，但不能照搬成纯 wiki 系统。本项目应采用：

```text
结构化数据系统 + 压缩记忆层 + LLM Wiki 式知识沉淀
```

可借鉴点：

- raw sources 不可变：原始采集、清洗数据、metrics 是事实源，LLM 不应修改。
- wiki 是中间知识层：用于保存领域概况、主题页、账号页、内容模式页，而不是替代数据表。
- schema 很重要：需要用 `schema.md` 或 `memory_global/wiki_schema.md` 规定 wiki 页面格式、证据格式和更新规则。
- index.md：内容目录，列出 wiki 页面、摘要、更新时间、证据数量。
- log.md：时间线，记录每次 ingest、rollup、lint、重要记忆更新。
- lint：定期检查过期结论、无证据页面、孤立页面、矛盾判断。

不适合照搬点：

- 不让 LLM 自由拥有整个事实层。
- 不用 markdown 页面保存时间序列指标。
- 不默认让 LLM 搜整个 wiki。
- 不把 wiki 当成唯一记忆系统。

正确边界：

```text
raw/processed/metrics 是事实层
memory/entities、patterns、trends 是结构化记忆层
memory/wiki 是 LLM 可读知识层
current_state.md 是压缩召回层
```

### 4.2 evidence_id 规范

`evidence_id` 是报告、记忆、wiki 之间的关键外键，必须由程序统一生成，禁止各模块自行拼接。

推荐格式：

```text
ev_<date>_<domain>_<source>_<short_hash>
```

示例：

```text
ev_20260624_ai_peripheral_search_a1b2c3d4
```

字段含义：

- `date`：采集日期，格式 `YYYYMMDD`。
- `domain`：领域 ID，使用项目中的 `domain_id`，过长时可截断。
- `source`：证据来源，第一阶段固定为 `search`，后续可扩展 `detail`、`manual`。
- `short_hash`：由 `date + domain_id + keyword + note_id/link/title` 生成的 8-12 位稳定哈希。

存储位置：

```text
projects/<domain>/memory/evidence/YYYY-MM-DD_evidence.jsonl
```

每行字段建议：

```json
{
  "evidence_id": "ev_20260624_ai_peripheral_search_a1b2c3d4",
  "date": "2026-06-24",
  "domain_id": "ai_peripheral",
  "source": "search_page",
  "keyword": "某IP周边",
  "rank": 3,
  "note_id": "xhs_note_id_or_empty",
  "link": "https://...",
  "title": "...",
  "author": "...",
  "like_count": 0,
  "collect_count": 0,
  "comment_count": 0,
  "share_count": 0,
  "topic_cluster_id": "rule_xxx",
  "topic_name": "xxx",
  "content_pattern": ["测评", "避坑"],
  "entity_candidates": ["..."],
  "quality_flags": []
}
```

规则：

- 同一条笔记在同一领域、同一日期内必须得到稳定的 `evidence_id`。
- 如果有 `note_id`，优先用 `note_id` 参与哈希；没有则用 `link`；再没有才用 `title + author + keyword`。
- LLM 输出的每条重要判断必须引用已有 `evidence_id`，不能创造新的 ID。
- 写入报告前由 Python 校验 `evidence_id` 是否存在于当天 evidence 文件或被召回的历史 evidence 索引中。

## 5. 核心模块改造方案

### 5.1 搜索页增强分析模块

新增模块建议：

```text
analysis/search_page_signals.py
```

职责：

- 从标题、作者、关键词、排名、互动数据中提取结构化信号。
- 不进入详情页。
- 不调用 LLM。
- 使用规则词表、正则、标题分词和可复现的统计逻辑。

输出：

- 标题结构标签
- 内容类型标签
- 需求信号标签
- 商业属性候选
- 竞品/IP/产品词候选
- 账号重复出现情况

第一阶段实现原则：

- 内容类型识别使用关键词规则和标题模式规则，不调用 LLM。
- 可保留批量模型分类作为后续可选增强，但默认 pipeline 不启用。
- 每个标签输出 `confidence` 和 `matched_rules`，方便调试。
- 低置信度结果保留为候选，不写成确定结论。

topic 来源必须单独定义，不能和内容类型混用：

- `topic` 表示讨论对象或需求主题，例如“某IP周边”“AI写作”“AI绘画”“桌搭收纳”。
- `content_pattern` 表示内容打法或标题类型，例如“测评”“避坑”“清单”“教程”。
- 第一阶段 topic 来自 `analysis/topic_cluster.py` 这类规则聚类：领域词表、关键词、标题高频词、人工维护的同义词表。
- LLM 可以在报告中解释 topic 格局，但不能直接改写 `topic_cluster_id`、`topic_name`。
- `topic_daily.csv` 只保存 topic 指标，不保存内容打法指标；内容打法进入 `patterns/content_patterns.csv`。

建议识别的内容类型：

- 开箱
- 测评
- 避坑
- 平替
- 同款
- 清单
- 教程
- 对比
- 自制
- 价格
- 购买决策
- 省钱
- 情绪价值
- 效率提升

### 5.2 账号和前排占位分析模块

新增模块建议：

```text
analysis/author_intelligence.py
```

职责：

- 统计作者在不同关键词下的出现频次。
- 统计作者是否反复进入前排。
- 统计作者最高互动、平均互动、代表标题。
- 给出账号类型候选，但必须标注置信度。

不要直接断言作者身份。只能输出：

```text
疑似商家号
疑似达人号
疑似测评号
疑似普通用户
疑似品牌号
```

每个判断必须绑定原因，例如：

- 标题中多次出现价格/下单/同款。
- 多个关键词前排重复出现。
- 高收藏笔记集中。
- 内容模式集中在测评/清单/开箱。

### 5.3 竞品/IP/产品候选模块

新增模块建议：

```text
analysis/entity_miner.py
```

职责：

- 从标题和可见文本中提取品牌、IP、产品词、品类词。
- 生成候选，不做确定性实体识别。
- 统计候选实体的出现次数、关联关键词、代表标题、互动表现。

输出示例：

```json
{
  "entity": "某IP",
  "entity_type": "ip_candidate",
  "count": 12,
  "keywords": ["某IP周边", "某IP自制"],
  "evidence_titles": ["..."],
  "confidence": "medium"
}
```

### 5.4 内容打法分析模块

新增模块建议：

```text
analysis/content_pattern_analyzer.py
```

职责：

- 按标题、互动结构、内容类型识别内容打法。
- 判断哪些打法更偏收藏型、评论型、高赞型。

核心指标：

- 样本数
- 平均点赞
- 中位点赞
- P90 点赞
- 收藏/点赞比
- 评论/点赞比
- 前排出现次数
- 代表标题

输出不应写“建议采用某打法”，而应写：

```text
当前搜索页前排中，某打法更常见或互动更高。
```

### 5.5 市场局势报告模块

新增或改造：

```text
pipeline/generate_market_report.py
```

报告主体应从“建议型日报”改为“局势分析报告”。

推荐结构：

```text
# <领域> 小红书搜索页市场局势分析

## 数据边界
- 数据来源
- 采集日期
- 样本量
- 搜索页限制
- 不包含正文/评论/成交/真实转化

## 市场声量
- 关键词样本量
- 近 3/7/30 天变化
- 升温、降温、稳定主题

## 主题格局
- 主题占比
- 新出现主题
- 连续出现主题
- 高互动主题

## 前排占位
- 高频作者
- 前排作者
- 疑似账号类型
- 重复出现情况

## 内容打法
- 常见标题结构
- 高收藏内容模式
- 高评论内容模式
- 图文/视频比例

## 用户需求信号
- 价格
- 颜值
- 教程
- 避坑
- 效率
- 情绪价值
- 购买决策

## 竞品/IP/产品候选
- 高频候选实体
- 关联关键词
- 代表样本
- 置信度

## 当前局势判断
- 只描述现状，不给强行动建议
- 每条判断绑定证据

## 证据样本
- 标题
- 作者
- 关键词
- 排名
- 互动指标
- 链接

## 不确定性和风险
- 搜索页样本偏差
- 无详情页正文
- 无评论
- 无成交数据
- 风控导致样本不稳定
```

### 5.6 记忆更新模块

新增：

```text
pipeline/update_memory.py
```

职责：

1. 读取当天 clean notes 和 metrics。
2. 生成 daily summary。
3. 更新 authors/topics/keywords/patterns 等结构化表。
4. 生成 trend_events。
5. 更新 weekly/monthly metrics 和 summary。
6. 更新 current_state.md。
7. 执行记忆冲突处理。

更新 current_state 时要压缩，不要不断追加。

current_state 建议控制在 800-1500 中文字左右。

记忆冲突处理规则：

- `current_state` 只保留当前仍被证据支持的判断。
- 新数据与旧判断冲突时，先写入 `judgments.jsonl`，记录旧判断、新证据、冲突类型和处理动作。
- 单日异常不直接覆盖长期判断，除非样本质量为 high 且变化幅度极大。
- 推荐默认规则：连续 3 天 `cooling` 才覆盖上一阶段 `rising`；连续 3 天无新增证据则从 `active` 降为 `watching`；连续 30 天无新增证据降为 `historical`。
- 如果当天 `data_quality.level` 为 `low`，只能新增“不确定/待观察”，不能覆盖长期判断。

`judgments.jsonl` 字段建议：

```json
{
  "judgment_id": "jg_20260624_xxx",
  "date": "2026-06-24",
  "domain_id": "ai_peripheral",
  "target_type": "topic",
  "target_id": "rule_xxx",
  "previous_state": "rising",
  "new_state": "cooling",
  "conflict_type": "trend_reversal",
  "evidence_ids": ["ev_..."],
  "data_quality_level": "medium",
  "action": "watching",
  "reason": "连续 1 天降温，未达到覆盖阈值"
}
```

### 5.7 记忆召回模块

新增：

```text
analysis/memory_context.py
```

职责：

- 根据当前 domain 和日期，读取最小必要上下文。
- 只召回当前领域。
- 限制上下文大小。
- 返回结构化对象给 LLM。

默认召回：

- profile.yaml
- current_state.md
- 最近一个 weekly summary
- 最近一个 weekly metrics
- 今日 metrics
- 今日 top evidence

不要召回：

- 全部日报
- 全部 raw
- 全部 history_clean_notes
- 全部 wiki

## 6. 记忆压缩规则

记忆压缩分为两类：确定性压缩和语义压缩。

### 6.0 压缩职责边界

确定性压缩必须由程序完成，不交给 LLM：

- 每日样本数。
- 关键词频次。
- 主题频次。
- 作者出现次数。
- 前排占位次数。
- 点赞、收藏、评论、分享等互动指标。
- 收藏/点赞比、评论/点赞比。
- 近 3/7/30 天增长。
- active / watching / dormant / historical 状态。
- 过期记忆淘汰。

语义压缩可以由 LLM 辅助，但必须基于程序输出的结构化事实：

- weekly rollup 的自然语言摘要。
- monthly rollup 的长期格局总结。
- current_state 的可读化整理。
- wiki 主题页、账号页、模式页的归纳。
- 历史判断的复盘描述。

推荐实现方式：

```text
Python 先计算事实和状态
-> 生成 compact JSON
-> LLM 基于 compact JSON 写 Markdown 摘要
-> Python 校验摘要字段、证据 ID、长度
-> 写入 memory
```

禁止：

```text
LLM 直接读取全部历史数据后自行决定哪些是事实
LLM 无证据更新 current_state
LLM 无限追加记忆
```

### 6.1 每日 summary

文件：

```text
projects/<domain>/memory/daily/YYYY-MM-DD_summary.json
```

字段建议：

```json
{
  "date": "YYYY-MM-DD",
  "domain": "domain_id",
  "sample_count": 0,
  "clean_count": 0,
  "top_keywords": [],
  "top_topics": [],
  "rising_topics": [],
  "cooling_topics": [],
  "repeated_authors": [],
  "top_patterns": [],
  "entity_candidates": [],
  "evidence_ids": [],
  "data_quality": {
    "publish_date_present_rate": 0,
    "missing_like_rate": 0,
    "dedupe_rate": 0
  }
}
```

### 6.2 weekly rollup

weekly rollup 拆成结构化指标和可读摘要两份，避免用 Markdown 保存时间序列数据。

结构化指标文件：

```text
projects/<domain>/memory/rollups/weekly_YYYY-Www_metrics.json
```

保留：

- 本周稳定主题
- 本周升温主题
- 本周降温主题
- 高频作者
- 高频内容模式
- 重要实体候选
- 数据质量问题
- 证据索引

字段建议：

```json
{
  "week": "2026-W26",
  "domain_id": "ai_peripheral",
  "date_range": ["2026-06-22", "2026-06-28"],
  "sample_count": 0,
  "clean_count": 0,
  "data_quality_level": "medium",
  "stable_topics": [],
  "rising_topics": [],
  "cooling_topics": [],
  "high_frequency_authors": [],
  "top_patterns": [],
  "entity_candidates": [],
  "evidence_ids": []
}
```

可读摘要文件：

```text
projects/<domain>/memory/rollups/weekly_YYYY-Www_summary.md
```

可读摘要由 LLM 基于 `weekly_YYYY-Www_metrics.json` 生成，只用于召回和阅读，不作为指标事实源。

不要保留完整样本列表。

### 6.3 current_state

文件：

```text
projects/<domain>/memory/current_state.md
```

只保留当前仍有用的压缩认知：

- 当前领域概况
- 稳定主题
- 升温信号
- 前排账号
- 内容模式
- 高频实体候选
- 不确定事项
- 最近证据索引

过期规则：

- 30 天无新证据的主题降级为 historical。
- 60 天无新证据的主题移出 current_state，只保留在月 rollup。
- 被新数据反复削弱的判断写入 judgments，但不保留在主状态中。

### 6.4 数据质量降级策略

数据质量由程序计算，并影响报告措辞、记忆写入和冲突覆盖。

建议输出位置：

```text
projects/<domain>/processed/YYYY-MM-DD_data_quality.json
```

字段建议：

```json
{
  "date": "2026-06-24",
  "domain_id": "ai_peripheral",
  "level": "medium",
  "raw_count": 0,
  "clean_count": 0,
  "missing_like_rate": 0,
  "publish_date_present_rate": 0,
  "dedupe_rate": 0,
  "extract_error_rate": 0,
  "risk_flags": [],
  "actions": []
}
```

默认规则：

- `clean_count < 10`：报告可以生成，但必须标记 `low_sample`，禁止输出强趋势判断，不更新 `current_state` 中的趋势状态。
- `clean_count < 3`：只生成数据质量报告，不生成市场局势报告。
- `missing_like_rate > 0.5`：互动指标降级，只保留标题/作者/关键词类信号。
- `publish_date_present_rate < 0.3`：近期性判断降级，不输出 rising/cooling，只输出 stable/uncertain。
- `dedupe_rate > 0.7`：提示搜索结果重复严重，减少前排占位判断权重。
- 连续采集失败或异常样本过多：触发熔断，本日停止继续抓取该领域，保留错误摘要。

缺字段处理：

- 标题、关键词缺失：该条样本不可用于主题/内容模式识别。
- 点赞、收藏、评论缺失：该条样本仍保留，但不可用于互动表现排序。
- 作者缺失：该条样本仍保留，但不可用于作者占位分析。
- 链接和 note_id 均缺失：仍可保留标题证据，但 `evidence_id` 必须使用 `title + author + keyword` 哈希，并添加 `weak_identity` 标记。

## 7. LLM 使用规范

本项目默认不使用 LLM tool calling，也不默认使用 ReAct 交互。

LLM 的主职责是：

- 解释结构化指标。
- 归纳结构化信号。
- 生成报告文字。
- 整理 wiki 知识页。
- 对历史判断做证据复盘。

LLM 不负责：

- 自主发起爬取。
- 自主读取全部项目文件。
- 自主决定是否访问详情页。
- 自主修改事实层数据。
- 自主把未验证信息写成确定事实。

只有在明确进入“开发者探索模式”或“wiki 维护模式”时，才允许 AI agent 使用工具辅助检索文件、检查 wiki、生成维护建议。该模式不属于默认业务流程。

### 7.1 LLM 输入

LLM 输入必须是结构化后的结果，而不是完整原始数据。

输入建议：

```json
{
  "data_boundary": "...",
  "current_state": "...",
  "today_metrics": {},
  "topic_signals": [],
  "author_signals": [],
  "pattern_signals": [],
  "entity_candidates": [],
  "data_quality": {},
  "evidence_cases": []
}
```

### 7.2 LLM 输出

LLM 输出必须是 JSON，再由报告模块渲染 Markdown。

输出字段建议：

```json
{
  "market_state": [],
  "topic_landscape": [],
  "front_rank_occupation": [],
  "content_patterns": [],
  "demand_signals": [],
  "entity_signals": [],
  "uncertainties": [],
  "evidence_map": []
}
```

### 7.3 禁止 LLM 输出

没有证据时，禁止输出：

- 用户一定愿意付费。
- 这个赛道一定有机会。
- 某账号一定是商家。
- 某品牌正在投放。
- 某产品销量很好。
- 某方向适合立刻进入。
- 厂家广告需求旺盛。

只能写：

- 搜索页样本显示。
- 当前样本中可见。
- 候选信号。
- 需要其他数据验证。
- 置信度 low/medium/high。

## 8. 数据指标体系

### 8.1 基础指标

- raw_count
- clean_count
- dedupe_rate
- publish_date_present_rate
- recent_publish_ratio
- avg_likes
- median_likes
- p90_likes
- total_likes
- total_collects
- total_comments
- collect_like_ratio
- comment_like_ratio
- share_like_ratio
- video_rate
- image_note_rate

### 8.2 关键词指标

- keyword_sample_count
- keyword_front_rank_count
- keyword_avg_likes
- keyword_collect_like_ratio
- keyword_comment_like_ratio
- keyword_recent_ratio
- keyword_3d_growth
- keyword_7d_growth

### 8.3 主题指标

- topic_sample_count
- topic_share
- topic_front_rank_count
- topic_p90_likes
- topic_collect_like_ratio
- topic_comment_like_ratio
- topic_recent_ratio
- topic_status: rising/stable/cooling/uncertain

### 8.4 作者指标

- author_appear_count
- author_keyword_count
- author_front_rank_count
- author_max_likes
- author_max_collects
- author_avg_rank
- author_representative_titles
- author_type_candidate
- confidence

### 8.5 内容模式指标

- pattern_sample_count
- pattern_share
- pattern_avg_likes
- pattern_p90_likes
- pattern_collect_like_ratio
- pattern_comment_like_ratio
- pattern_representative_titles

## 9. GUI 改造建议

当前 GUI 可以保持双 tab 基础结构，但建议增加：

### 9.1 项目配置页

新增字段：

- 领域分析目标
- 数据边界说明
- 是否启用 LLM 报告
- 是否启用记忆更新
- 是否启用详情页抽样
- 详情页每日上限
- 报告模式：日报 / 市场局势 / 记忆复盘

### 9.2 运行页

新增选项：

- 更新领域记忆
- 生成市场局势报告
- 生成 weekly rollup
- 仅使用规则分析
- 使用 LLM 解释结构化结果

### 9.3 报告展示

支持查看：

- 当日报告
- current_state
- weekly summary
- weekly metrics
- evidence samples

### 9.4 Pipeline 状态反馈

运行页需要展示每个步骤的状态，避免用户只能从日志里猜失败原因。

建议状态：

```text
pending / running / success / skipped / failed
```

建议步骤：

- 采集搜索页
- 合并原始/清洗历史
- 清洗去重
- 可选封面图分析
- 计算基础指标
- 计算搜索页信号
- 生成 evidence
- 评估数据质量
- 更新记忆
- 生成报告

每个步骤至少展示：

- 开始时间
- 结束时间
- 输入文件
- 输出文件
- 样本数量
- 错误摘要

失败处理：

- 可跳过步骤显示 `skipped`，例如详情页抽样、封面图分析。
- 核心步骤失败显示 `failed` 并中止后续依赖步骤。
- 报告页提供“查看错误摘要”入口，读取当日 `pipeline_status.json`。

### 9.5 采集频率和调度

第一阶段以手动触发为主，避免风控和调试复杂度同时上升。

推荐机制：

- GUI 手动触发：默认方式。
- Windows 任务计划程序：可选，用于固定时间打开命令行运行指定 domain。
- 每个 domain 可配置 `schedule_enabled`、`preferred_time`、`max_keywords_per_run`。
- 同一 domain 默认每天最多完整采集一次；重复运行需要用户手动确认或使用 `--force`。
- 如果前一次运行失败且触发熔断，当天自动调度应跳过该 domain。

## 10. 推荐 pipeline 顺序

```text
pipeline.run_daily
pipeline.merge_raw
pipeline.clean_notes
pipeline.analyze_images --optional
pipeline.compute_metrics
pipeline.compute_search_page_signals
pipeline.generate_evidence
pipeline.evaluate_data_quality
pipeline.update_memory
pipeline.generate_market_report
```

其中 `compute_search_page_signals`、`generate_evidence`、`evaluate_data_quality` 和 `update_memory` 是新增核心步骤。

说明：

- `run_daily` 负责按关键词采集搜索页原始结果。
- `merge_raw` 应放在清洗前或并入 `run_daily`，用于合并同日多关键词原始结果；如果保留现有“合并历史 clean 数据”的含义，应改名为 `merge_history_clean`，并放在 `compute_metrics` 之后、`generate_market_report` 之前。
- `clean_notes` 依赖采集/合并后的原始数据。
- `analyze_images` 目前是可选增强，只能补充封面图/OCR/视觉模式字段；失败不应阻塞主流程。
- `compute_metrics` 依赖清洗后的数据。
- `compute_search_page_signals` 依赖清洗数据和基础指标。
- `generate_evidence` 统一生成 evidence 文件和 evidence_id。
- `evaluate_data_quality` 影响记忆更新和报告强弱措辞。
- `update_memory` 依赖 metrics、signals、evidence 和 data_quality。
- `generate_market_report` 只读取结构化结果和召回记忆。

详情页抽样如要加入，应放在 `run_daily` 后，并且失败不阻塞后续流程：

```text
pipeline.sample_detail_pages --optional
```

## 11. AI 开发容易出现的问题和规避方式

### 11.1 过度依赖 LLM

问题：

AI 开发者可能直接把 DataFrame 或日报丢给 LLM，让 LLM 自由总结。

规避：

- 所有关键指标必须由 Python 计算。
- LLM 输入必须是结构化信号。
- 报告结论必须引用 evidence_id。

### 11.2 把搜索页信号写成全站事实

问题：

搜索页结果不等于全站热度，更不等于市场销量。

规避：

- 所有报告固定写入数据边界。
- 用“搜索页样本显示”，不用“市场证明”。
- 不允许输出成交、付费、真实销量判断。

### 11.3 破坏多领域隔离

问题：

AI 开发者可能把记忆写到全局目录，导致多个领域混在一起。

规避：

- 所有领域记忆必须写入 `projects/<domain>/memory/`。
- 读写函数必须显式接收 `domain_id`。
- 测试中增加跨领域隔离用例。

### 11.4 记忆无限增长

问题：

daily summary、wiki、current_state 不断追加，最后上下文爆炸。

规避：

- current_state 覆盖更新，不无限追加。
- daily summary 只保存结构化短摘要。
- weekly/monthly rollup 做压缩。
- 召回模块限制 token/字符数。

### 11.5 误判账号类型

问题：

仅凭搜索页作者名就断言商家号或品牌号。

规避：

- 只输出“候选类型”。
- 必须有 confidence。
- 必须有 evidence。
- 没有证据时输出 unknown。

### 11.6 详情页采集导致主流程不稳定

问题：

强行抓详情页会触发风控，导致整个 pipeline 失败。

规避：

- 详情页默认关闭。
- 抽样限量。
- 失败跳过。
- 不影响搜索页主流程。

### 11.7 报告建议过多

问题：

LLM 容易输出大量“建议你做什么”。

规避：

- 报告 schema 中建议字段不作为主体。
- 系统提示中明确“只分析现有局势，少给行动建议”。
- 如保留建议，放在最后的低优先级附录。

### 11.8 修改已有中文文件时产生乱码

问题：

当前项目部分文件显示过乱码风险。AI 修改时可能进一步破坏编码。

规避：

- 所有文件按 UTF-8 读取和写入。
- 修改前检查文件实际编码和显示效果。
- 不做无关大规模重写。
- 新增文件使用 UTF-8。

### 11.9 改动过大，破坏现有可运行流程

问题：

AI 可能一次性重构 GUI、pipeline、分析模块，导致无法运行。

规避：

- 新增模块优先，不直接重写旧流程。
- 保持原 `run_pipeline` 可用。
- 新流程可以通过新增勾选项启用。
- 每次改动后运行单元测试。

### 11.10 缺少测试

问题：

标题分类、实体候选、记忆压缩容易被后续改坏。

规避：

新增测试：

- 标题模式识别测试。
- 作者统计测试。
- 实体候选提取测试。
- memory/current_state 压缩测试。
- 多领域隔离测试。
- LLM 输出 normalize 测试。

### 11.11 把业务流程做成过重 ReAct

问题：

AI 开发者可能把默认运行流程做成“LLM 思考一步、调用一个工具、再思考一步”的 ReAct agent，导致流程慢、不可复现、容易跑偏。

规避：

- 默认业务流程保持 pipeline-first。
- LLM 不直接调爬虫和文件工具。
- 工具动作由 Python 显式编排。
- ReAct 只作为开发者探索或 wiki lint 的辅助模式。

### 11.12 让 LLM 直接维护事实层

问题：

AI 开发者可能让 LLM 直接改 `authors.csv`、`topic_daily.csv`、`metrics.json` 等事实或结构化记忆文件。

规避：

- 事实层和结构化记忆层只能由程序写入。
- LLM 只生成候选解释或 wiki 文本。
- 写入前由 Python 校验 evidence_id、字段 schema、长度和置信度。

### 11.13 把 LLM Wiki 当成数据库

问题：

AI 开发者可能只用 markdown wiki 保存所有记忆，导致趋势无法精确计算、召回成本变高。

规避：

- 时间序列和实体统计必须存 CSV/JSONL。
- wiki 只保存可读知识沉淀。
- index/log/schema 用于导航和维护，不替代指标表。

### 11.14 evidence_id 不统一

问题：

AI 开发者可能在不同模块里临时拼接 `evidence_id`，导致报告、记忆、wiki 无法互相校验。

规避：

- 只允许 `generate_evidence` 或统一工具函数生成 `evidence_id`。
- 所有引用 evidence 的模块只读取已有 ID。
- 报告生成前校验所有 `evidence_id` 是否存在。
- 测试覆盖同一笔记重复运行时 ID 稳定。

### 11.15 topic 和内容打法混用

问题：

AI 开发者可能把“测评/避坑/清单”写入 `topic_daily.csv`，导致主题趋势和内容打法趋势混在一起。

规避：

- topic 只表示讨论对象或需求主题。
- content_pattern 只表示内容打法。
- 两套指标分开存储、分开报告。
- 报告中可以并列展示，但数据表不能混写。

### 11.16 忽略数据质量降级

问题：

风控、缺字段、样本过少时，系统仍输出强趋势判断，造成低质量结论。

规避：

- 每日生成 `data_quality.json`。
- `low` 质量数据只允许生成弱判断。
- `clean_count < 3` 时不生成市场局势报告。
- 低质量日不覆盖 `current_state` 中的长期判断。

## 12. 优先实现清单（面向 AI 开发）

不按人类排期，而按依赖关系：

0. 新增全局前置配置：`memory_global/analysis_rules.md`、`wiki_schema.md`、`report_schema.yaml`、topic/content_pattern 词表。
1. 新增领域记忆目录创建逻辑，包括 `memory/wiki/index.md`、`log.md`、`schema.md`。
2. 新增统一 `evidence_id` 生成器和 `generate_evidence` 模块。
3. 修正 pipeline 顺序，明确 `merge_raw` 的含义；如表示历史合并则改名为 `merge_history_clean`。
4. 新增 `data_quality.json` 和降级策略。
5. 新增标题内容模式识别，使用规则，不默认调用 LLM。
6. 明确 topic 规则聚类，和 content_pattern 分表保存。
7. 新增作者/前排占位统计。
8. 新增实体候选提取。
9. 新增 topic/keyword/author/pattern 长期 CSV 更新。
10. 新增 daily summary 生成。
11. 新增 trend_events.jsonl 和 judgments.jsonl。
12. 新增记忆冲突处理规则。
13. 新增 weekly/monthly metrics JSON 与 summary Markdown 拆分逻辑。
14. 新增程序侧确定性压缩逻辑。
15. 新增 LLM 语义压缩逻辑，但只输入 compact JSON。
16. 新增 current_state 覆盖式更新。
17. 新增 memory_context 召回模块。
18. 改造 LLM prompt，使其只解释结构化结果，不默认 tool calling。
19. 新增市场局势报告生成器。
20. 新增 memory wiki index/log 更新逻辑。
21. 新增 memory lint 检查命令。
22. GUI 增加 pipeline 步骤状态、错误摘要、“更新记忆”和“生成市场局势报告”选项。
23. 新增手动触发优先、Windows 任务计划可选的调度设计。
24. 可选增加详情页抽样模块，但默认关闭。

## 13. 成功标准

改进后的系统应满足：

- 一个领域连续运行多天后，可以看到主题、作者、内容打法的变化。
- 报告能清楚说明“当前搜索页局势是什么”。
- 每条重要判断能找到样本证据。
- 报告不会把搜索页样本夸大成全市场结论。
- 多领域之间记忆互不污染。
- 长期运行后 LLM 上下文仍可控。
- 不依赖详情页也能生成有价值的市场局势分析。
- 详情页失败不会影响主流程。
- AI 建议内容占比低，局势分析占比高。

## 14. 核心一句话

本项目后续开发的核心方向是：

> 用程序负责事实、指标和记忆压缩，用 LLM 负责受约束的证据解释，最终形成按领域隔离、可长期追踪、低幻觉的小红书搜索页市场局势分析 agent。
