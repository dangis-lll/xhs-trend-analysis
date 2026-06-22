# 小红书搜索结果导出

用 Chrome 打开小红书搜索页，按关键词抓取搜索结果卡片中能直接看到的公开信息，并保存为 Excel。

## 环境

本机已检测到 `conda` 环境 `pt` 里有需要的核心包：

- `playwright`
- `pandas`
- `openpyxl`

如果换机器运行，先安装：

```powershell
conda activate pt
pip install playwright pandas openpyxl pyyaml
python -m playwright install chromium
```

## 使用

### Qt 图形界面

启动界面：

```powershell
conda run -n pt python xhs_trend_app.py
```

界面可以完成：

- 新建/编辑领域项目
- 输入调研内容
- 调用 DeepSeek 扩展关键词
- 调整每日关键词数、每词采集数、每日上限、登录等待时间等参数
- 运行采集、清洗、指标、历史合并、报告生成
- 在界面中浏览 Markdown 日报

DeepSeek API Key 不会写入项目文件。可以在界面输入，也可以先设置环境变量：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek Key"
$env:DEEPSEEK_MODEL="deepseek-v4-flash"
conda run -n pt python xhs_trend_app.py
```

### 按配置每日采集

先在 `config/domains.yaml` 中配置领域、关键词和每个关键词采集数量，然后运行：

```powershell
conda run -n pt python -m pipeline.run_daily --domain camping
```

小规模测试可以覆盖配置参数：

```powershell
conda run -n pt python -m pipeline.run_daily --domain camping --keywords-per-day 1 --notes-per-keyword 5 --max-daily-notes 5
```

每日采集结果会保存到：

```text
projects/<domain>/raw/YYYY-MM-DD/
```

其中每个关键词会生成一份 Excel 和 JSON，当天全部结果会合并为 `all_raw.xlsx` 和 `all_raw.json`。

采集后继续运行清洗、指标、历史合并和日报：

```powershell
conda run -n pt python -m pipeline.clean_notes --domain camping --date today
conda run -n pt python -m pipeline.compute_metrics --domain camping --date today
conda run -n pt python -m pipeline.merge_raw --domain camping --date today --days 30
conda run -n pt python -m pipeline.generate_report --domain camping --date today
```

后处理结果会保存到：

```text
projects/<domain>/processed/
projects/<domain>/reports/daily/
projects/<domain>/knowledge-base/
```

### 手动单关键词采集

首次运行建议不要用无头模式，因为小红书通常需要登录或验证码：

```powershell
conda run -n pt python manual_collect_keyword.py "露营装备" -n 50
```

程序会打开 Chrome。如果页面要求登录或验证码，请在浏览器里手动完成，脚本会继续等待并抓取。

默认结果会保存到：

```text
projects/manual/raw/YYYY-MM-DD/<关键词>/
```

如果要把手动采集也归到某个行业项目里：

```powershell
conda run -n pt python manual_collect_keyword.py "露营装备" -n 50 --project camping
```

指定输出文件：

```powershell
conda run -n pt python manual_collect_keyword.py "护肤" -n 100 --project skincare -o projects\skincare\raw\2026-06-22\护肤\hufu.xlsx
```

复用登录态：

默认登录态保存在对应项目目录的 `browser_profile`，例如 `projects/camping/browser_profile`。后续运行会复用这个目录。

## 导出字段

- `crawl_date`：采集日期
- `crawl_time`：采集时间
- `domain_id`：领域配置 ID
- `domain_name`：领域名称
- `keyword`：搜索关键词
- `rank`：搜索结果页当前解析顺序
- `title`：搜索卡片上能直接解析到的标题
- `author`：搜索卡片上能直接解析到的发布人
- `publish_time`：卡片上能直接看到的发布时间；如果搜索结果页不展示，则为空
- `publish_date`：根据 `publish_time` 换算出的标准日期，格式为 `YYYY-MM-DD`
- `link`：笔记链接
- `note_id`：从链接里解析的笔记 ID
- `cover_url`：搜索卡片封面图链接
- `like_count`：卡片上能直接解析到的点赞数
- `collect_count`：卡片上能直接解析到的收藏数
- `comment_count`：卡片上能直接解析到的评论数
- `interaction_count`：能从卡片文本兜底解析到的互动数字
- `data_attrs`：卡片 DOM 上可见的 `data-*` 属性，JSON 字符串
- `visible_text`：该搜索卡片的可见文本，便于页面结构变化时回溯
- `extract_method`：采集方式，第一阶段固定为 `search_page_card`
- `quality_flags`：缺失字段标记，例如缺标题、缺链接、缺发布时间等
- `source_file`：该条记录来自的原始文件路径

## 主要命令

```powershell
# 按配置采集当天原始数据
conda run -n pt python -m pipeline.run_daily --domain camping

# 清洗和硬降重
conda run -n pt python -m pipeline.clean_notes --domain camping --date today

# 计算基础指标
conda run -n pt python -m pipeline.compute_metrics --domain camping --date today

# 合并最近 30 天历史快照
conda run -n pt python -m pipeline.merge_raw --domain camping --date today --days 30

# 生成日报
conda run -n pt python -m pipeline.generate_report --domain camping --date today

# 可选：添加图片分析占位字段；加 --download 会尝试下载封面图
conda run -n pt python -m pipeline.analyze_images --domain camping --date today

# 可选：把候选关键词追加到知识库
conda run -n pt python -m pipeline.update_knowledge_base --domain camping --date today
```

如果运行环境里设置了 `DEEPSEEK_API_KEY`，日报会追加 DeepSeek 生成的 AI 解释、主题洞察、案例分析和内容建议。

## 项目化保存结构

每个行业或追踪方向建议配置成一个 `domain_id`，同时也会作为项目 ID。比如 `camping` 的所有数据都会保存在：

```text
projects/camping/
  browser_profile/
  raw/YYYY-MM-DD/
  processed/
  images/YYYY-MM-DD/
  reports/daily/
  knowledge-base/
```

这样你可以同时追踪多个行业，例如：

```text
projects/camping/
projects/skincare/
projects/coffee/
```

它们的采集结果、处理结果、报告、图片和知识库都会互相隔离。

## 注意

这个脚本不进入笔记详情页，只读取搜索结果页卡片中直接可见的内容。小红书页面结构和风控策略可能变化；如果后续字段提取不完整，可以根据 `visible_text` 和页面 HTML 调整选择器。
