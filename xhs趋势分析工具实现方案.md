# 小红书趋势分析工具实现方案

## 1. 实现目标

实现一个本地运行的小红书趋势分析工具。工具每天围绕指定领域的关键词采集小红书搜索结果页数据，保存历史样本，进行清洗、降重、图片解析、主题聚类、指标计算，并输出日报和周报。

默认不进入详情页，不做点赞、收藏、评论、发布等互动动作。

第一版目标：

- 支持配置领域和关键词。
- 支持每日批量采集多个关键词。
- 保存原始数据和处理后数据。
- 完成硬降重。
- 计算基础趋势指标。
- 生成 Markdown + Excel 报告。
- 为后续 OCR、多模态、大模型分析预留接口。

## 2. 技术栈

运行环境：

```text
Windows
conda 环境：pt
Python 3.10+
```

核心依赖：

```text
playwright
pandas
openpyxl
pyyaml
numpy
scikit-learn
```

第二阶段可选依赖：

```text
pillow
requests
opencv-python
pytesseract 或 paddleocr
openai
```

安装命令：

```powershell
conda activate pt
pip install playwright pandas openpyxl pyyaml numpy scikit-learn pillow requests
python -m playwright install chromium
```

## 3. 推荐目录结构

在当前项目目录中创建：

```text
config/
  domains.yaml
  analysis_config.yaml

collector/
  __init__.py
  browser_session.py
  search_page_collector.py
  extractors.py

pipeline/
  __init__.py
  run_daily.py
  merge_raw.py
  clean_notes.py
  compute_metrics.py
  generate_report.py

analysis/
  __init__.py
  dedupe.py
  metrics.py
  keyword_miner.py
  topic_cluster.py
  llm_analyzer.py
  image_analyzer.py

storage/
  __init__.py
  paths.py
  raw_store.py
  processed_store.py

projects/
  camping/
    browser_profile/
    raw/
    processed/
    images/
    snapshots/
    reports/
      daily/
      weekly/
    knowledge-base/
      domain_profile.md
      keyword_pool.md
      topic_taxonomy.md
      title_patterns.md
      cover_patterns.md

tests/
  test_time_parse.py
  test_dedupe.py
  test_metrics.py
```

保留当前已有文件：

```text
xhs_trend_app.py
manual_collect_keyword.py
README.md
xhs趋势分析设计方案.md
```

采集核心放在 `collector/search_page_collector.py`，Qt 界面和 CLI 调试入口都复用这一套采集逻辑。

## 4. 配置文件

### 4.1 `config/domains.yaml`

示例：

```yaml
domains:
  - id: camping
    name: 露营装备
    description: 小红书露营装备、新手露营、露营生活方式趋势分析
    seed_keywords:
      - 露营装备
      - 新手露营
      - 露营清单
      - 露营避坑
      - 露营车
      - 天幕
      - 帐篷
      - 折叠椅
      - 蛋卷桌
      - 营地灯
    collection:
      keywords_per_day: 10
      notes_per_keyword: 50
      max_daily_notes: 500
      login_timeout: 180
      slow_mo: 0
      headless: false
```

### 4.2 `config/analysis_config.yaml`

示例：

```yaml
analysis:
  trend_min_days: 3
  high_like_threshold: 1000
  semantic_similarity_threshold: 0.88
  recent_publish_days: 7
  top_topics: 10
  top_cases: 10
  enable_ocr: false
  enable_multimodal: false
  enable_llm_report: false
  enable_detail_cases: false
  max_detail_cases: 0
```

## 5. 数据格式

### 5.1 原始采集表 `raw_notes`

每次关键词采集生成一份 Excel 和 JSONL。

字段：

```text
crawl_date
crawl_time
domain_id
domain_name
keyword
rank
title
author
publish_time
publish_date
link
note_id
cover_url
like_count
collect_count
comment_count
interaction_count
data_attrs
visible_text
extract_method
quality_flags
source_file
```

### 5.2 处理后表 `clean_notes`

字段：

```text
crawl_date
domain_id
keyword
canonical_id
note_id
link
title
author
publish_date
like_count
cover_url
visible_text
hard_duplicate_key
duplicate_group_id
topic_cluster_id
quality_score
```

### 5.3 每日主题指标表 `topic_daily_metrics`

字段：

```text
date
domain_id
topic_cluster_id
topic_name
note_count
new_note_count
total_likes
avg_likes
median_likes
p90_likes
high_like_count
high_like_rate
recent_publish_ratio
topic_score
growth_rate_3d
representative_titles
representative_note_ids
```

## 6. 实现步骤

## 阶段 1：配置和每日采集

### Step 1. 创建配置目录和配置文件

创建：

```text
config/domains.yaml
config/analysis_config.yaml
```

验收标准：

- 能从 YAML 读取领域配置。
- 能读取关键词列表和每词采集数量。

### Step 2. 创建路径管理模块

文件：

```text
storage/paths.py
```

功能：

- 根据日期创建数据目录。
- 生成原始数据、处理数据、报告路径。

建议函数：

```python
def get_project_root() -> Path
def get_today_str() -> str
def raw_dir(date: str) -> Path
def processed_dir() -> Path
def report_dir(date: str) -> Path
def ensure_dirs() -> None
```

验收标准：

- 运行后自动创建 `projects/<domain>/raw/YYYY-MM-DD/`。
- 运行后自动创建 `projects/<domain>/reports/daily/`。

### Step 3. 改造采集脚本为可复用函数

当前已有：

```text
collector/search_page_collector.py
manual_collect_keyword.py
```

需要保留手动 CLI，同时暴露函数：

```python
async def collect_keyword(...)
def save_outputs(...)
```

如果已经存在，补齐这些能力：

- 加入 `crawl_date`
- 加入 `crawl_time`
- 加入 `domain_id`
- 加入 `domain_name`
- 加入 `extract_method`
- 加入 `quality_flags`

验收标准：

- 原命令仍可运行。
- 新 pipeline 可以 import 并调用采集函数。

### Step 4. 实现每日采集入口

文件：

```text
pipeline/run_daily.py
```

命令：

```powershell
conda run -n pt python -m pipeline.run_daily --domain camping
```

功能：

1. 读取 `config/domains.yaml`。
2. 找到 `domain_id=camping` 的配置。
3. 获取当天要采集的关键词。
4. 逐个调用搜索页采集函数。
5. 每个关键词保存一份原始 Excel/JSON。
6. 合并当天原始结果为 `projects/<domain>/raw/YYYY-MM-DD/all_raw.xlsx`。

验收标准：

- 运行一次后，`projects/<domain>/raw/YYYY-MM-DD/` 下存在多个关键词文件。
- 存在 `all_raw.xlsx`。
- 不同关键词的结果都带 `keyword` 字段。

## 阶段 2：清洗和硬降重

### Step 5. 实现数字解析

文件：

```text
analysis/metrics.py
```

函数：

```python
def parse_count(value: str | int | float | None) -> int | None
```

支持：

```text
123
1,234
1.2万
3万
赞 268
```

验收标准：

```text
parse_count("1.2万") == 12000
parse_count("赞 268") == 268
parse_count("") is None
```

### Step 6. 实现硬降重

文件：

```text
analysis/dedupe.py
```

函数：

```python
def build_hard_duplicate_key(row) -> str
def hard_dedupe(df: pd.DataFrame) -> pd.DataFrame
```

规则：

1. 优先用 `note_id`。
2. 其次用规范化后的 `link`。
3. 再用 `author + normalized_title`。
4. 保留点赞数最高的一条。

注意：

- 跨天同一笔记不要完全删除，应保留每日快照。
- 当天同一批数据里重复结果可以合并。

验收标准：

- 同一个 `note_id` 当天只保留一条。
- 保留点赞数较高的记录。

### Step 7. 实现清洗入口

文件：

```text
pipeline/clean_notes.py
```

命令：

```powershell
conda run -n pt python -m pipeline.clean_notes --date 2026-06-22 --domain camping
```

功能：

1. 读取 `all_raw.xlsx`。
2. 标准化点赞数。
3. 标准化日期。
4. 生成硬降重 key。
5. 输出当天 `clean_notes.xlsx` 和 `clean_notes.csv`。

验收标准：

- `projects/<domain>/processed/YYYY-MM-DD_clean_notes.xlsx` 存在。
- 有 `like_count_num` 字段。
- 有 `hard_duplicate_key` 字段。

## 阶段 3：基础指标和日报

### Step 8. 计算每日指标

文件：

```text
pipeline/compute_metrics.py
```

命令：

```powershell
conda run -n pt python -m pipeline.compute_metrics --date 2026-06-22 --domain camping
```

功能：

计算：

- 原始样本数
- 去重后样本数
- 去重率
- 有发布时间样本占比
- 近 7 天发布占比
- 平均点赞
- 中位数点赞
- P90 点赞
- 高赞笔记数
- 高赞率
- Top 关键词贡献
- Top 作者
- 高频标题词
- Top 高赞笔记

输出：

```text
projects/<domain>/processed/YYYY-MM-DD_metrics.json
projects/<domain>/processed/YYYY-MM-DD_top_notes.xlsx
```

验收标准：

- 指标 JSON 可读。
- Top 高赞笔记表按点赞数降序。

### Step 9. 生成 Markdown 日报

文件：

```text
pipeline/generate_report.py
```

命令：

```powershell
conda run -n pt python -m pipeline.generate_report --date 2026-06-22 --domain camping
```

报告路径：

```text
projects/<domain>/reports/daily/2026-06-22_小红书趋势日报.md
```

报告结构：

```text
# 小红书趋势日报：露营装备

## 今日结论
## 数据概览
## 高赞笔记 Top 10
## 热门关键词
## 高频标题词
## 近 7 天内容
## 值得关注的案例
## 明日关键词建议
```

第一版不接大模型，使用规则模板生成。

验收标准：

- 报告能打开。
- 每个结论后有数据证据。
- 高赞案例包含标题、点赞、作者、链接。

## 阶段 4：连续三天趋势分析

### Step 10. 汇总历史数据

文件：

```text
pipeline/merge_raw.py
```

功能：

- 合并最近 N 天 `clean_notes`。
- 输出 `projects/<domain>/processed/history_clean_notes.csv`。

验收标准：

- 三天数据能合并。
- 同一 `note_id` 不同日期的快照保留。

### Step 11. 计算 3 日趋势

文件：

```text
analysis/keyword_miner.py
analysis/topic_cluster.py
```

第一版先不做 embedding，用规则主题：

- 从标题和 OCR 文本提取高频词。
- 按关键词、产品词、需求词聚合。
- 统计最近 3 天出现次数和点赞数变化。

趋势指标：

```text
keyword_note_count_3d
keyword_like_total_3d
keyword_growth_rate
new_keyword_count
```

验收标准：

- 第三天以后报告出现“近 3 天上升词”。
- 每个上升词有样本数和代表笔记。

## 阶段 5：图片下载和 OCR

### Step 12. 下载封面图

文件：

```text
analysis/image_analyzer.py
```

函数：

```python
def download_cover_images(df: pd.DataFrame, date: str) -> pd.DataFrame
```

保存路径：

```text
projects/<domain>/images/YYYY-MM-DD/<note_id>.jpg
```

验收标准：

- 有 `cover_url` 的记录能下载图片。
- 下载失败写入 `quality_flags`，不中断流程。

### Step 13. OCR 提取封面文字

第一版可先做接口占位：

```python
def extract_ocr_text(image_path: Path) -> str:
    return ""
```

第二版接入 PaddleOCR 或多模态模型。

输出字段：

```text
cover_ocr_text
```

验收标准：

- 即使 OCR 未启用，流程也能运行。
- OCR 启用后，报告中出现封面高频词。

## 阶段 6：大模型分析

### Step 14. 大模型报告解释

文件：

```text
analysis/llm_analyzer.py
```

输入：

- metrics JSON
- Top 笔记
- 高频词
- 近 3 天趋势词
- 代表案例

输出：

```json
{
  "summary": [],
  "topic_insights": [],
  "case_analysis": [],
  "keyword_suggestions": [],
  "content_suggestions": []
}
```

原则：

- 大模型只解释程序算出的数据。
- 大模型不能伪造指标。
- 每条结论必须引用样本标题或指标。

验收标准：

- 没有 API Key 时，自动跳过大模型分析。
- 有 API Key 时，在报告中追加“AI 解释”章节。

### Step 15. 大模型扩展关键词

文件：

```text
analysis/keyword_miner.py
```

输入：

- 当前关键词池
- 高频标题词
- 高赞标题
- OCR 文本
- 领域描述

输出：

```text
candidate_keywords.csv
```

字段：

```text
keyword
dimension
reason
priority
source
first_seen_date
```

验收标准：

- 每日报告给出 5 到 20 个候选关键词。
- 候选关键词不直接自动加入核心池，先进入待审核状态。

## 阶段 7：语义聚类

### Step 16. 文本向量和语义降重

文件：

```text
analysis/topic_cluster.py
```

第一版可用 TF-IDF + KMeans / DBSCAN。

第二版接入 embedding API。

输入文本：

```text
title + visible_text + cover_ocr_text + image_summary
```

输出字段：

```text
topic_cluster_id
topic_name
semantic_duplicate_group_id
```

验收标准：

- 相似标题能分到同一簇。
- 每个簇有代表标题。
- 日报能按主题展示 Top 主题。

## 阶段 8：知识库沉淀

### Step 17. 更新知识库

文件：

```text
pipeline/update_knowledge_base.py
```

更新：

```text
projects/<domain>/knowledge-base/keyword_pool.md
projects/<domain>/knowledge-base/topic_taxonomy.md
projects/<domain>/knowledge-base/title_patterns.md
projects/<domain>/knowledge-base/cover_patterns.md
```

规则：

- 只写入稳定结论。
- 候选关键词标注来源和日期。
- 不覆盖人工编辑内容，追加到指定区域。

验收标准：

- 每周报告后知识库有新增内容。
- 人工修改的文件不会被全量重写。

## 7. 入口设计

### Qt 图形界面

主入口：

```powershell
conda run -n pt python xhs_trend_app.py
```

界面负责：

- 新建/编辑领域项目。
- 输入调研内容。
- 调用 DeepSeek 扩展关键词。
- 调整每日关键词数、每词采集数、每日总量、登录等待时间等参数。
- 运行采集、清洗、图片占位、指标、历史合并、报告生成。
- 浏览 Markdown 日报。

DeepSeek API Key 不写入项目文件。界面可临时输入，也可从环境变量 `DEEPSEEK_API_KEY` 读取。

### CLI 调试入口

单关键词采集：

```powershell
conda run -n pt python manual_collect_keyword.py "露营装备" -n 50 --project camping
```

单步调试每日流程：

```powershell
conda run -n pt python -m pipeline.run_daily --domain camping
conda run -n pt python -m pipeline.clean_notes --date today --domain camping
conda run -n pt python -m pipeline.compute_metrics --date today --domain camping
conda run -n pt python -m pipeline.merge_raw --date today --domain camping --days 30
conda run -n pt python -m pipeline.generate_report --date today --domain camping
```

## 8. 定时运行方案

当前阶段不再使用 PowerShell 封装脚本，优先通过 Qt 界面手动运行和确认验证码。后续如果要做无人值守定时任务，应单独实现 Python 调度入口，并保留验证码停止机制。

## 9. 测试方案

### 单元测试

```text
tests/test_time_parse.py
tests/test_dedupe.py
tests/test_metrics.py
```

测试点：

- 发布时间标准化。
- 点赞数字解析。
- 硬降重。
- 指标计算。

运行：

```powershell
conda run -n pt python -m pytest tests
```

如果未安装 pytest：

```powershell
conda activate pt
pip install pytest
```

### 手工验收

1. 搜索 1 个关键词，采集 10 条。
2. 检查 Excel 字段是否完整。
3. 检查是否生成 `publish_date`。
4. 检查点赞数是否转成数字。
5. 检查重复链接是否合并。
6. 检查日报是否包含 Top 笔记和数据概览。

## 10. 风控规则

默认策略：

- 不进入详情页。
- 不自动点赞、收藏、评论、关注、发布。
- 不并发打开多个浏览器。
- 单关键词 50 到 100 条。
- 每天总量 500 到 2000 条。
- 命中验证码后停止。
- 使用真实 Chrome 持久化登录态。

详情页能力：

- 第一版不实现。
- 后续如实现，必须默认关闭。
- 每天最多 3 到 5 个案例。
- 需要人工确认。
- 命中验证码立即停止。

## 11. 里程碑

### M1：基础可跑

完成：

- 配置文件
- 每日多关键词采集
- 合并原始数据
- 清洗和硬降重
- 基础指标
- Markdown 日报

验收：

- 一个命令跑完当天流程。
- 生成 Excel 和 Markdown 报告。

### M2：趋势分析

完成：

- 三天历史合并
- 近 3 天趋势词
- 高赞标题模式
- 关键词候选池

验收：

- 第三天以后报告能展示上升主题和数据证据。

### M3：图片理解

完成：

- 封面下载
- OCR 占位或接入
- 多模态占位或接入
- 封面高频词分析

验收：

- 报告能展示封面文字趋势。

### M4：大模型增强

完成：

- AI 趋势解释
- AI 案例拆解
- AI 关键词建议
- 知识库追加

验收：

- 报告有 AI 解释章节。
- 每条 AI 结论引用数据或样本。

## 12. AI 实现提示词

后续让 AI 实现时，可以使用下面提示词：

```text
你是资深 Python 工程师。请在当前项目中实现“小红书趋势分析工具”。

请严格阅读并遵循：
1. xhs趋势分析设计方案.md
2. xhs趋势分析工具实现方案.md
3. 现有 collector/search_page_collector.py

实现要求：
- 默认不进入详情页。
- 不实现点赞、收藏、评论、发布等互动功能。
- 使用 conda 环境 pt。
- 优先复用现有 collector/search_page_collector.py 的 Playwright 搜索页采集逻辑。
- 按阶段实现，先完成 M1。
- 每个模块都要有清晰 CLI 命令。
- 数据必须按项目保存到 `projects/<domain>/`。
- 报告必须包含可验证的数据证据。
- 不要伪造任何抓取字段。
- 如果字段缺失，用空值和 quality_flags 标注。

第一步请实现：
1. config/domains.yaml
2. config/analysis_config.yaml
3. storage/paths.py
4. pipeline/run_daily.py
5. pipeline/clean_notes.py
6. analysis/dedupe.py
7. analysis/metrics.py
8. pipeline/compute_metrics.py
9. pipeline/generate_report.py

完成后运行基础测试和一个小规模采集示例。
```

## 13. 我的实现建议

实现时不要一次性把所有高级能力塞进去。先把数据链路跑通：

```text
采集 -> 保存 -> 清洗 -> 降重 -> 指标 -> 报告
```

只要这条链路稳定，后面的 OCR、多模态、embedding、大模型都是增强模块。

最重要的工程原则：

- 原始数据永远保留。
- 处理数据可以重算。
- 报告必须可追溯到样本。
- 大模型只解释，不替代计算。
- 缺失字段不要硬猜。
- 默认低频、低风险、不进详情页。
