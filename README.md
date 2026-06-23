# 小红书趋势分析工具

这是一个面向小红书搜索结果页的趋势分析工具。它按领域项目管理关键词，自动打开 Chrome 采集搜索页可见信息，清洗去重后计算趋势指标，并生成 Markdown 日报。

工具只分析搜索页能拿到的信息，不进入笔记详情页。

## 主要功能

- 项目化管理多个追踪方向，例如露营、护肤、咖啡等。
- 维护关键词池，并可用 DeepSeek 扩展候选关键词。
- 按每日关键词数、每词采集数、每日总上限自动采集搜索结果。
- 采集搜索页结构化数据和卡片可见信息，包括标题、作者、链接、封面、点赞、收藏、评论、分享、图文/视频类型等。
- 清洗、硬去重、标准化互动数字和发布时间。
- 计算趋势指标：高赞率、近期发布占比、收藏/点赞比、评论/点赞比、视频占比、主题动能、近 3 天上升词等。
- 生成趋势日报，重点输出趋势总览、热点信号、主题动能、内容结构模式、风险和验证计划。
- 可选下载封面图、更新轻量知识库。

## 环境依赖

建议使用 Python 3.10+。不要求特定 conda 环境，venv、conda 或系统 Python 都可以。

需要安装的主要库：

- `playwright`：控制 Chrome 采集搜索页
- `pandas`：数据清洗和指标计算
- `openpyxl`：读写 Excel
- `pyyaml`：读取项目配置
- `PySide6`：图形界面
- `openai`：调用 DeepSeek/OpenAI 兼容接口
- `requests`：可选封面图下载

安装示例：

```powershell
pip install playwright pandas openpyxl pyyaml PySide6 openai requests
python -m playwright install chromium
```

如果你使用 conda，可以先创建并激活自己的环境，再执行上面的 `pip install`。

## 启动界面

```powershell
python xhs_trend_app.py
```

界面里可以完成：

- 新建和保存领域项目
- 编辑调研说明和关键词池
- 设置每日关键词数、每词采集数、每日总上限、登录等待时间
- 调用 DeepSeek 扩展关键词
- 一键运行采集、清洗、封面分析、指标计算、历史合并、日报生成
- 查看生成的 Markdown 日报

DeepSeek API Key 不会保存到项目文件。可以在界面输入，也可以设置环境变量：

```powershell
$env:DEEPSEEK_API_KEY="你的 API Key"
$env:DEEPSEEK_MODEL="deepseek-v4-flash"
python xhs_trend_app.py
```

## 关键词和采集规则

- `关键词`：项目的候选关键词池，每行一个。
- `每日关键词数`：每天从关键词池前面取多少个词采集。
- `每词采集数`：每个关键词目标采集多少条搜索结果。
- `每日总上限`：当天最多采集多少条，达到后停止。
- `DeepSeek 扩展数量`：只控制一次让大模型生成多少个候选关键词，不等于每日采集数。

如果关键词池有 30 个词，每日关键词数设为 10，就只采集前 10 个。  
如果关键词池只有 6 个词，每日关键词数设为 10，就只采集这 6 个。

修改项目配置后需要点击“保存项目”，运行流程才会读取最新配置。

## 命令行使用

图形界面会自动串联这些步骤。需要手动运行时，可以使用下面命令。

```powershell
python -m pipeline.run_daily --domain camping --date today
python -m pipeline.clean_notes --domain camping --date today
python -m pipeline.analyze_images --domain camping --date today
python -m pipeline.compute_metrics --domain camping --date today
python -m pipeline.merge_raw --domain camping --date today --days 30
python -m pipeline.generate_report --domain camping --date today
```

可选步骤：

```powershell
# 下载封面图
python -m pipeline.analyze_images --domain camping --date today --download

# 把候选关键词追加到轻量知识库
python -m pipeline.update_knowledge_base --domain camping --date today
```

单关键词手动采集：

```powershell
python manual_collect_keyword.py "露营装备" -n 50 --project camping
```

首次运行时建议使用可见浏览器。如果小红书要求登录或验证码，请在打开的 Chrome 中手动完成，程序会等待后继续。

## 数据保存位置

每个项目独立保存在 `projects/<domain>/` 下：

```text
projects/<domain>/
  browser_profile/          # Chrome 登录态
  raw/YYYY-MM-DD/           # 原始采集 Excel/JSON
  processed/                # 清洗数据、指标、候选关键词
  images/YYYY-MM-DD/        # 可选封面图
  reports/daily/            # Markdown 日报
  knowledge-base/           # 轻量关键词池和运行记录
```

## 采集字段

主要字段包括：

- 基础信息：采集日期、项目 ID、关键词、搜索排名
- 内容信息：标题、作者、笔记链接、笔记 ID、图文/视频类型
- 作者和链接：作者 ID、头像、`xsec_token`
- 封面信息：封面 URL、宽高、文件 ID
- 互动指标：点赞、收藏、评论、分享、互动兜底字段
- 质量追踪：可见文本、提取方式、缺失字段标记、来源文件

部分发布时间可能为空，因为搜索结果页并不总是展示发布时间。

## 分析边界

本工具默认不进入详情页，因此不会分析：

- 正文全文
- 评论内容
- 详情页话题标签
- IP 属地
- 完整图片列表

日报中的趋势和热点判断只基于搜索页可见字段和历史快照。小红书页面结构和风控策略可能变化，如果字段缺失，可根据原始数据里的 `visible_text`、`extract_method` 和页面结构调整采集逻辑。
