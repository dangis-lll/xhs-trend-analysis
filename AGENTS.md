# Python 开发约定

## Python 环境

- 需要运行 Python 代码时，默认使用 `conda` 的 `pt` 虚拟环境。
- 推荐命令形式：

```powershell
conda run -n pt python path\to\script.py
```

- 检查语法或导入时也使用 `pt` 环境：

```powershell
conda run -n pt python -m py_compile path\to\script.py
```

## 依赖版本

- 优先使用 `pt` 环境中已经安装的依赖版本。
- 不要随意升级、降级或重新安装 Python 包。
- 只有在现有版本明确无法满足任务时，才考虑变更依赖，并在说明中写清楚原因、影响和风险。

# 小红书趋势分析项目约定

## 项目核心边界

- 本项目是 pipeline-first 的小红书搜索页趋势分析工具，不默认实现 ReAct/tool-calling agent。
- 核心分析不得依赖详情页采集；详情页、OCR、封面图分析只能作为可选增强，失败不得阻塞主流程。
- LLM 只解释 Python pipeline 生成的结构化数据，不直接分析完整 raw/clean DataFrame，不直接写入事实层 CSV/JSON。
- 报告必须明确数据边界，使用“搜索页样本显示”“当前样本中可见”等措辞，不得推断销量、成交、真实投放、全市场结论。
- 多领域数据必须隔离在 `projects/<domain>/` 下；全局目录只放通用 schema、通用规则和默认配置。
- `topic` 表示讨论对象或需求主题；`content_pattern` 表示内容打法，二者不得混写。
- 重要判断必须能追溯到 `evidence_id`。
- 低质量数据不得覆盖长期记忆或输出强趋势判断。

## 数据与记忆约束

- 事实层和结构化记忆层只能由程序写入，LLM 可以生成候选解释、报告文本、wiki 摘要，但写入前必须由 Python 校验。
- `current_state.md` 是覆盖式压缩记忆，不做无限追加。
- 多天追踪时必须保留领域隔离、证据可追溯和数据质量标记。
- 搜索页样本、指标、证据、记忆更新应按 `domain_id` 和日期显式读写。

## Windows / 中文编码

- 所有中文 Markdown、YAML、JSON、CSV 文本文件按 UTF-8 读写。
- 修改中文文件时显式指定 UTF-8，避免 PowerShell 默认编码导致乱码。
- 不使用 PowerShell `echo > file` 或默认 `Out-File` 写中文内容。
- 优先使用 `apply_patch` 做文本编辑。

## 开发原则

- 利用第一性原理，以实现任务和功能为导向

## 大模型API-KEY

- 系统环境变量：DEEPSEEK_API_KEY
