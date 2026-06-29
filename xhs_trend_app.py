from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from analysis.llm_analyzer import DEFAULT_DEEPSEEK_MODEL, expand_keywords_with_llm
from pipeline.common import load_domains_config
from pipeline.runner import PipelineRunner
from pipeline.step_registry import build_step_plan
from storage.paths import (
    evidence_dir,
    get_project_root,
    market_report_dir,
    memory_dir,
    memory_trends_dir,
    memory_wiki_dir,
    normalize_date,
    processed_dir,
)


ROOT = get_project_root()
DOMAINS_PATH = ROOT / "config" / "domains.yaml"


def safe_id(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_\-]+", "_", text.strip().lower())
    return cleaned.strip("_") or "project"


def read_domains() -> list[dict[str, Any]]:
    config = load_domains_config(DOMAINS_PATH)
    return config.get("domains", []) or []


def write_domains(domains: list[dict[str, Any]]) -> None:
    DOMAINS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOMAINS_PATH.write_text(
        yaml.safe_dump({"domains": domains}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def keyword_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def default_conservative_collection() -> dict[str, Any]:
    return {
        "keyword_delay_min_seconds": 45,
        "keyword_delay_max_seconds": 120,
        "scroll_wait_min_ms": 2500,
        "scroll_wait_max_ms": 7000,
        "scroll_px_min": 700,
        "scroll_px_max": 1800,
        "risk_control_keywords": [
            "验证码",
            "安全验证",
            "访问频繁",
            "操作频繁",
            "请稍后再试",
            "当前环境异常",
            "账号异常",
            "网络环境异常",
            "滑块验证",
            "人机验证",
        ],
        "circuit_breaker_failure_threshold": 2,
    }


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path, limit: int = 10) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
        if len(records) >= limit:
            break
    return records


STATUS_LABELS = {
    "success": "成功",
    "failed": "失败",
    "running": "运行中",
    "pending": "等待中",
    "skipped": "跳过",
    "unknown": "未知",
}

QUALITY_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "invalid": "无效",
    "unknown": "未知",
}

WARNING_LABELS = {
    "publish_date_present_rate_low": "发布时间缺失较多，近期趋势判断已降级",
    "clean_count_low": "清洗后样本较少",
    "raw_count_low": "原始样本较少",
    "duplicate_rate_high": "重复样本比例较高",
    "missing_like_rate_high": "互动数字缺失较多",
}

RECOMMENDATION_LABELS = {
    "content_pattern_rules_need_expansion": "内容打法规则需要扩充",
    "topic_taxonomy_need_expansion": "主题分类规则需要扩充",
    "topic_taxonomy_low_coverage": "主题规则覆盖率偏低",
}

PIPELINE_STEP_LABELS = {
    "run_daily": "采集搜索页",
    "clean_notes": "清洗与去重",
    "apply_manual_corrections": "应用人工纠错",
    "sample_detail_pages": "生成详情页抽样清单",
    "analyze_images": "下载封面图",
    "compute_metrics": "计算基础指标",
    "compute_search_page_signals": "计算搜索页信号",
    "evaluate_rules": "评估规则覆盖",
    "suggest_rule_candidates": "生成规则候选",
    "generate_evidence": "生成证据索引",
    "evaluate_data_quality": "评估数据质量",
    "merge_history_clean": "合并历史清洗数据",
    "generate_market_report": "生成市场局势报告",
    "update_memory": "更新分层记忆",
    "update_rollups": "更新周/月汇总",
    "update_knowledge_base": "更新知识库",
}


def label_value(value: Any, labels: dict[str, str]) -> str:
    key = str(value or "unknown")
    return labels.get(key, key)


def bool_label(value: Any) -> str:
    return "是" if bool(value) else "否"


def translated_list(values: list[Any], labels: dict[str, str]) -> str:
    translated = [label_value(value, labels) for value in values if str(value).strip()]
    return "、".join(translated) or "无"


class CommandWorker(QThread):
    line = Signal(str)
    step_progress = Signal(str, int, int, str)
    finished_ok = Signal(bool)

    def __init__(
        self,
        plan,
        env: dict[str, str],
        *,
        domain_id: str,
        date_value: str,
        date_str: str,
    ) -> None:
        super().__init__()
        self.plan = plan
        self.env = env
        self.domain_id = domain_id
        self.date_value = date_value
        self.date_str = date_str

    def run(self) -> None:
        runner = PipelineRunner(
            domain_id=self.domain_id,
            date_value=self.date_value,
            date_str=self.date_str,
            plan=self.plan,
            py=sys.executable,
            env=self.env,
            line_callback=self.line.emit,
            step_callback=lambda step, status, completed, total: self.step_progress.emit(step, completed, total, status),
        )
        self.finished_ok.emit(runner.run() == 0)


class KeywordWorker(QThread):
    finished_keywords = Signal(list, str)
    failed = Signal(str)

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        domain_name: str,
        research_brief: str,
        seed_keywords: list[str],
        target_count: int,
    ) -> None:
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.domain_name = domain_name
        self.research_brief = research_brief
        self.seed_keywords = seed_keywords
        self.target_count = target_count

    def run(self) -> None:
        old_key = os.environ.get("DEEPSEEK_API_KEY")
        old_model = os.environ.get("DEEPSEEK_MODEL")
        os.environ["DEEPSEEK_API_KEY"] = self.api_key
        os.environ["DEEPSEEK_MODEL"] = self.model
        try:
            result = expand_keywords_with_llm(
                domain_name=self.domain_name,
                research_brief=self.research_brief,
                seed_keywords=self.seed_keywords,
                target_count=self.target_count,
                model=self.model,
            )
            items = result.get("keywords", [])
            keywords = []
            for item in items:
                if isinstance(item, dict) and item.get("keyword"):
                    keywords.append(str(item["keyword"]).strip())
                elif isinstance(item, str):
                    keywords.append(item.strip())
            self.finished_keywords.emit(list(dict.fromkeys([k for k in keywords if k])), json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if old_key is None:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            else:
                os.environ["DEEPSEEK_API_KEY"] = old_key
            if old_model is None:
                os.environ.pop("DEEPSEEK_MODEL", None)
            else:
                os.environ["DEEPSEEK_MODEL"] = old_model


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("小红书趋势分析工具")
        self.resize(1280, 820)
        self.worker: CommandWorker | None = None
        self.keyword_worker: KeywordWorker | None = None
        self._build_ui()
        self.load_domains()

    def _build_ui(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_project_tab(), "项目与关键词")
        self.tabs.addTab(self._build_run_tab(), "采集与报告")
        self.setCentralWidget(self.tabs)

    def _build_project_tab(self) -> QWidget:
        root = QWidget()
        layout = QHBoxLayout(root)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("领域项目"))
        self.domain_list = QListWidget()
        self.domain_list.currentRowChanged.connect(self.on_domain_selected)
        left_layout.addWidget(self.domain_list)
        refresh_btn = QPushButton("刷新项目")
        refresh_btn.clicked.connect(self.load_domains)
        left_layout.addWidget(refresh_btn)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        form_box = QGroupBox("项目配置")
        form = QFormLayout(form_box)
        self.domain_id = QLineEdit()
        self.domain_name = QLineEdit()
        self.research_brief = QPlainTextEdit()
        self.research_brief.setPlaceholderText("输入你想调研的内容，例如：我想研究露营装备在小红书上的用户需求、爆款内容、近期热点和选题机会。")
        self.seed_keywords = QPlainTextEdit()
        self.seed_keywords.setPlaceholderText("每行一个关键词")
        self.keywords_per_day = QSpinBox()
        self.keywords_per_day.setRange(1, 200)
        self.notes_per_keyword = QSpinBox()
        self.notes_per_keyword.setRange(1, 500)
        self.max_daily_notes = QSpinBox()
        self.max_daily_notes.setRange(1, 20000)
        self.login_timeout = QSpinBox()
        self.login_timeout.setRange(0, 3600)
        self.slow_mo = QSpinBox()
        self.slow_mo.setRange(0, 2000)
        self.headless = QCheckBox("无头模式")
        form.addRow("项目 ID", self.domain_id)
        form.addRow("项目名称", self.domain_name)
        form.addRow("调研内容", self.research_brief)
        form.addRow("关键词", self.seed_keywords)
        form.addRow("每日关键词数", self.keywords_per_day)
        form.addRow("每词采集数", self.notes_per_keyword)
        form.addRow("每日总上限", self.max_daily_notes)
        form.addRow("登录等待秒数", self.login_timeout)
        form.addRow("操作延迟 ms", self.slow_mo)
        form.addRow("", self.headless)
        right_layout.addWidget(form_box)

        llm_box = QGroupBox("DeepSeek 关键词扩展")
        llm_form = QFormLayout(llm_box)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("不保存；也可用环境变量 DEEPSEEK_API_KEY")
        self.model = QLineEdit(DEFAULT_DEEPSEEK_MODEL)
        self.expand_count = QSpinBox()
        self.expand_count.setRange(5, 100)
        self.expand_count.setValue(30)
        llm_form.addRow("API Key", self.api_key)
        llm_form.addRow("模型", self.model)
        llm_form.addRow("扩展数量", self.expand_count)
        right_layout.addWidget(llm_box)

        buttons = QHBoxLayout()
        new_btn = QPushButton("新建项目")
        new_btn.clicked.connect(self.new_domain)
        save_btn = QPushButton("保存项目")
        save_btn.clicked.connect(self.save_current_domain)
        expand_btn = QPushButton("调用 DeepSeek 扩展关键词")
        expand_btn.clicked.connect(self.expand_keywords)
        buttons.addWidget(new_btn)
        buttons.addWidget(save_btn)
        buttons.addWidget(expand_btn)
        right_layout.addLayout(buttons)
        self.keyword_result = QPlainTextEdit()
        self.keyword_result.setPlaceholderText("关键词扩展原始 JSON 会显示在这里")
        right_layout.addWidget(self.keyword_result)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([260, 900])
        layout.addWidget(splitter)
        return root

    def _build_run_tab(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        top = QHBoxLayout()
        self.run_domain = QComboBox()
        self.run_date = QLineEdit("today")
        self.run_download_images = QCheckBox("下载封面图")
        self.run_detail_sampling = QCheckBox("详情页抽样")
        self.run_rule_analysis = QCheckBox("规则评估")
        self.run_rule_analysis.setChecked(True)
        self.run_market_report = QCheckBox("市场报告")
        self.run_market_report.setChecked(True)
        self.run_update_memory = QCheckBox("更新记忆")
        self.run_update_memory.setChecked(True)
        self.run_update_kb = QCheckBox("更新知识库")
        self.show_run_details = QCheckBox("显示运行详情")
        self.show_run_details.toggled.connect(self.update_run_detail_visibility)
        run_btn = QPushButton("运行完整流程")
        run_btn.clicked.connect(self.run_pipeline)
        report_btn = QPushButton("打开主报告")
        report_btn.clicked.connect(self.load_report)
        status_btn = QPushButton("刷新状态")
        status_btn.clicked.connect(self.load_run_status)
        memory_btn = QPushButton("查看记忆")
        memory_btn.clicked.connect(self.load_current_state)
        wiki_btn = QPushButton("查看Wiki")
        wiki_btn.clicked.connect(self.load_wiki_index)
        evidence_btn = QPushButton("查看证据")
        evidence_btn.clicked.connect(self.load_evidence_samples)
        rules_btn = QPushButton("查看规则候选")
        rules_btn.clicked.connect(self.load_rule_candidates)
        corrections_btn = QPushButton("人工纠错")
        corrections_btn.clicked.connect(self.open_manual_corrections)
        trends_btn = QPushButton("查看趋势表")
        trends_btn.clicked.connect(self.load_trend_tables)
        top.addWidget(QLabel("项目"))
        top.addWidget(self.run_domain)
        top.addWidget(QLabel("日期"))
        top.addWidget(self.run_date)
        top.addWidget(self.run_download_images)
        top.addWidget(self.run_detail_sampling)
        top.addWidget(self.run_rule_analysis)
        top.addWidget(self.run_market_report)
        top.addWidget(self.run_update_memory)
        top.addWidget(self.run_update_kb)
        top.addWidget(self.show_run_details)
        top.addWidget(run_btn)
        top.addWidget(report_btn)
        top.addWidget(status_btn)
        top.addWidget(memory_btn)
        top.addWidget(wiki_btn)
        top.addWidget(evidence_btn)
        top.addWidget(rules_btn)
        top.addWidget(corrections_btn)
        top.addWidget(trends_btn)
        layout.addLayout(top)

        self.run_status_summary = QLabel("未运行")
        self.run_status_summary.setWordWrap(True)
        layout.addWidget(self.run_status_summary)

        self.report_view = QTextBrowser()
        self.report_view.setMarkdown("选择项目和日期后点击“运行完整流程”，这里会显示进度和市场局势报告。")
        layout.addWidget(self.report_view, stretch=1)

        self.detail_panel = QSplitter(Qt.Orientation.Horizontal)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.status_view = QTextBrowser()
        self.detail_panel.addWidget(self.status_view)
        self.detail_panel.addWidget(self.log_view)
        self.detail_panel.setSizes([520, 520])
        layout.addWidget(self.detail_panel)
        self.update_run_detail_visibility(False)
        return root

    def load_domains(self) -> None:
        self.domains = read_domains()
        self.domain_list.clear()
        self.run_domain.clear()
        for domain in self.domains:
            label = f"{domain.get('name', domain.get('id'))} ({domain.get('id')})"
            self.domain_list.addItem(label)
            self.run_domain.addItem(label, domain.get("id"))
        if self.domains:
            self.domain_list.setCurrentRow(0)

    def current_domain_index(self) -> int:
        return self.domain_list.currentRow()

    def on_domain_selected(self, row: int) -> None:
        if row < 0 or row >= len(self.domains):
            return
        domain = self.domains[row]
        collection = domain.get("collection", {}) or {}
        self.domain_id.setText(str(domain.get("id", "")))
        self.domain_name.setText(str(domain.get("name", "")))
        self.research_brief.setPlainText(str(domain.get("description", "")))
        self.seed_keywords.setPlainText("\n".join(domain.get("seed_keywords", []) or []))
        self.keywords_per_day.setValue(int(collection.get("keywords_per_day") or 3))
        self.notes_per_keyword.setValue(int(collection.get("notes_per_keyword") or 20))
        self.max_daily_notes.setValue(int(collection.get("max_daily_notes") or 60))
        self.login_timeout.setValue(int(collection.get("login_timeout") or 180))
        self.slow_mo.setValue(int(collection.get("slow_mo") or 100))
        self.headless.setChecked(bool(collection.get("headless") or False))

    def new_domain(self) -> None:
        self.domain_id.setText("")
        self.domain_name.setText("")
        self.research_brief.setPlainText("")
        self.seed_keywords.setPlainText("")
        self.keywords_per_day.setValue(3)
        self.notes_per_keyword.setValue(20)
        self.max_daily_notes.setValue(60)
        self.login_timeout.setValue(180)
        self.slow_mo.setValue(100)
        self.headless.setChecked(False)
        self.domain_list.clearSelection()

    def build_domain_from_form(self) -> dict[str, Any]:
        name = self.domain_name.text().strip()
        domain_id = self.domain_id.text().strip() or safe_id(name)
        existing_collection: dict[str, Any] = {}
        row = self.current_domain_index()
        if 0 <= row < len(self.domains):
            current = self.domains[row]
            if str(current.get("id") or "") == domain_id:
                existing_collection = dict(current.get("collection", {}) or {})
        collection = default_conservative_collection()
        collection.update(existing_collection)
        collection.update(
            {
                "keywords_per_day": self.keywords_per_day.value(),
                "notes_per_keyword": self.notes_per_keyword.value(),
                "max_daily_notes": self.max_daily_notes.value(),
                "login_timeout": self.login_timeout.value(),
                "slow_mo": self.slow_mo.value(),
                "headless": self.headless.isChecked(),
            }
        )
        return {
            "id": domain_id,
            "name": name or domain_id,
            "description": self.research_brief.toPlainText().strip(),
            "seed_keywords": keyword_lines(self.seed_keywords.toPlainText()),
            "collection": collection,
        }

    def save_current_domain(self) -> None:
        domain = self.build_domain_from_form()
        domains = read_domains()
        for index, item in enumerate(domains):
            if item.get("id") == domain["id"]:
                domains[index] = domain
                break
        else:
            domains.append(domain)
        write_domains(domains)
        self.load_domains()
        QMessageBox.information(self, "已保存", f"项目 {domain['id']} 已保存")

    def get_api_key(self) -> str:
        return self.api_key.text().strip() or os.environ.get("DEEPSEEK_API_KEY", "")

    def expand_keywords(self) -> None:
        api_key = self.get_api_key()
        if not api_key:
            QMessageBox.warning(self, "缺少 API Key", "请在界面输入 DeepSeek API Key，或设置 DEEPSEEK_API_KEY。")
            return
        domain = self.build_domain_from_form()
        self.keyword_result.setPlainText("正在调用 DeepSeek 扩展关键词...")
        self.keyword_worker = KeywordWorker(
            api_key=api_key,
            model=self.model.text().strip() or DEFAULT_DEEPSEEK_MODEL,
            domain_name=domain["name"],
            research_brief=domain["description"],
            seed_keywords=domain["seed_keywords"],
            target_count=self.expand_count.value(),
        )
        self.keyword_worker.finished_keywords.connect(self.on_keywords_expanded)
        self.keyword_worker.failed.connect(lambda msg: self.keyword_result.setPlainText("关键词扩展失败：\n" + msg))
        self.keyword_worker.start()

    def on_keywords_expanded(self, keywords: list[str], raw_json: str) -> None:
        existing = keyword_lines(self.seed_keywords.toPlainText())
        merged = list(dict.fromkeys(existing + keywords))
        self.seed_keywords.setPlainText("\n".join(merged))
        self.keyword_result.setPlainText(raw_json)

    def update_run_detail_visibility(self, checked: bool) -> None:
        if hasattr(self, "detail_panel"):
            self.detail_panel.setVisible(bool(checked))
        if checked and hasattr(self, "status_view"):
            self.load_run_status()

    def set_run_summary(self, text: str) -> None:
        self.run_status_summary.setText(text)

    def show_running_placeholder(self, *, domain_id: str, date_str: str, step: str, completed: int, total: int) -> None:
        step_label = PIPELINE_STEP_LABELS.get(step, step)
        self.set_run_summary(f"运行中｜当前步骤：{step_label}｜进度：{completed}/{total}")
        self.report_view.setMarkdown(
            "\n".join(
                [
                    "# 正在运行分析",
                    "",
                    f"- 项目：`{domain_id}`",
                    f"- 日期：`{date_str}`",
                    f"- 当前步骤：`{step_label}`",
                    f"- 已完成：`{completed} / {total}`",
                    "",
                    "报告生成后会自动显示在这里。",
                ]
            )
        )

    def on_step_progress(self, step: str, completed: int, total: int, status: str) -> None:
        context = self.current_run_context()
        domain_id, date_str = context if context else ("", "")
        step_label = PIPELINE_STEP_LABELS.get(step, step)
        if status == "running":
            self.show_running_placeholder(domain_id=domain_id, date_str=date_str, step=step, completed=completed, total=total)
        elif status == "success":
            self.set_run_summary(f"运行中｜已完成：{completed}/{total}｜刚完成：{step_label}")
        elif status == "failed":
            self.set_run_summary(f"失败｜失败步骤：{step_label}｜进度：{completed}/{total}")

    def append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text)
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    def run_pipeline(self) -> None:
        domain_id = self.run_domain.currentData()
        if not domain_id:
            QMessageBox.warning(self, "缺少项目", "请先选择或创建一个项目。")
            return
        api_key = self.get_api_key()
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        if api_key:
            env["DEEPSEEK_API_KEY"] = api_key
        env["DEEPSEEK_MODEL"] = self.model.text().strip() or DEFAULT_DEEPSEEK_MODEL
        date_value = self.run_date.text().strip() or "today"
        date_str = normalize_date(date_value)
        enabled_optional = set()
        if self.run_download_images.isChecked():
            enabled_optional.add("analyze_images")
        if self.run_detail_sampling.isChecked():
            enabled_optional.add("sample_detail_pages")
        if self.run_rule_analysis.isChecked():
            enabled_optional.update({"evaluate_rules", "suggest_rule_candidates"})
        if self.run_market_report.isChecked():
            enabled_optional.add("generate_market_report")
        if self.run_update_memory.isChecked():
            enabled_optional.update({"update_memory", "update_rollups"})
        if self.run_update_kb.isChecked():
            enabled_optional.add("update_knowledge_base")
        plan = build_step_plan(enabled_optional)
        self.tabs.setCurrentIndex(1)
        self.log_view.clear()
        self.status_view.clear()
        self.show_run_details.setChecked(False)
        self.set_run_summary(f"准备运行｜项目：{domain_id}｜日期：{date_str}｜步骤数：{len(plan)}")
        self.report_view.setMarkdown(
            "\n".join(
                [
                    "# 正在运行分析",
                    "",
                    f"- 项目：`{domain_id}`",
                    f"- 日期：`{date_str}`",
                    f"- 已完成：`0 / {len(plan)}`",
                    "",
                    "流程开始后会显示当前步骤，报告生成后会自动显示在这里。",
                ]
            )
        )
        self.append_log(f"开始运行项目：{domain_id}")
        self.worker = CommandWorker(plan, env, domain_id=domain_id, date_value=date_value, date_str=date_str)
        self.worker.line.connect(self.append_log)
        self.worker.step_progress.connect(self.on_step_progress)
        self.worker.finished_ok.connect(self.on_pipeline_finished)
        self.worker.start()

    def on_pipeline_finished(self, ok: bool) -> None:
        self.append_log("流程完成。" if ok else "流程中断。")
        self.load_run_status()
        if ok:
            self.set_run_summary("完成｜主报告已生成")
            self.load_report()
        else:
            self.show_run_details.setChecked(True)
            self.report_view.setMarkdown(
                "# 流程中断\n\n本次分析没有完整生成报告。已展开运行详情，请查看失败步骤和日志。"
            )

    def current_run_context(self) -> tuple[str, str] | None:
        domain_id = self.run_domain.currentData()
        if not domain_id:
            return None
        date_str = normalize_date(self.run_date.text().strip() or "today")
        return str(domain_id), date_str

    def load_run_status(self) -> None:
        context = self.current_run_context()
        if not context:
            return
        domain_id, date_str = context
        status = load_json_file(processed_dir(domain_id) / f"{date_str}_pipeline_status.json")
        quality = load_json_file(processed_dir(domain_id) / f"{date_str}_data_quality.json")
        rule_effectiveness = load_json_file(processed_dir(domain_id) / f"{date_str}_rule_effectiveness.json")
        rule_candidates = load_json_file(processed_dir(domain_id) / f"{date_str}_rule_candidates.json")
        lines = [f"# 运行状态：{domain_id}", "", f"日期：{date_str}", ""]
        if quality:
            lines.extend(
                [
                    "## 数据质量",
                    "",
                    f"- 质量等级：`{label_value(quality.get('quality_level'), QUALITY_LABELS)}`",
                    f"- 原始样本数：`{quality.get('raw_count', 0)}`",
                    f"- 清洗后样本数：`{quality.get('clean_count', 0)}`",
                    f"- 允许更新长期记忆：`{bool_label(quality.get('memory_update_allowed', False))}`",
                    f"- 风险提示：`{translated_list(quality.get('warnings', []), WARNING_LABELS)}`",
                    "",
                ]
            )
        else:
            lines.extend(["## 数据质量", "", "- 暂无数据质量文件。", ""])

        if rule_effectiveness:
            pattern = rule_effectiveness.get("content_pattern", {})
            topic = rule_effectiveness.get("topic", {})
            lines.extend(
                [
                    "## 规则覆盖",
                    "",
                    f"- 内容打法识别覆盖率：`{pattern.get('covered_rate', 0):.2%}`",
                    f"- 内容打法未识别比例：`{pattern.get('other_rate', 0):.2%}`",
                    f"- 主题识别覆盖率：`{topic.get('covered_rate', 0):.2%}`",
                    f"- 主题规则命中率：`{topic.get('taxonomy_rule_rate', 0):.2%}`",
                    f"- 规则改进提示：`{translated_list(rule_effectiveness.get('recommendations', []), RECOMMENDATION_LABELS)}`",
                    "",
                ]
            )
        if rule_candidates:
            summary = rule_candidates.get("summary", {})
            lines.extend(
                [
                    "## 规则候选",
                    "",
                    f"- 内容打法候选数：`{summary.get('content_pattern_candidate_count', 0)}`",
                    f"- 主题候选数：`{summary.get('topic_candidate_count', 0)}`",
                    "",
                ]
            )

        lines.extend(["## 流程执行", ""])
        if status:
            overall = label_value(status.get("overall_status"), STATUS_LABELS)
            lines.append(f"- 整体状态：`{overall}`")
            for step in status.get("steps", []):
                name = step.get("name", "")
                step_status = step.get("status", "")
                error = step.get("error", "")
                suffix = f"，错误：{error}" if error else ""
                display_name = PIPELINE_STEP_LABELS.get(name, name)
                display_status = label_value(step_status, STATUS_LABELS)
                lines.append(f"- {display_name}：`{display_status}`{suffix}")
            completed = sum(1 for step in status.get("steps", []) if step.get("status") == "success")
            total = len(status.get("steps", []))
            quality_text = label_value(quality.get("quality_level"), QUALITY_LABELS) if quality else "未知"
            clean_count = quality.get("clean_count", 0) if quality else 0
            self.set_run_summary(f"整体状态：{overall}｜数据质量：{quality_text}｜样本：{clean_count}｜步骤：{completed}/{total}")
        else:
            lines.append("- 暂无 pipeline_status 文件。")
            self.set_run_summary("未运行｜暂无流程状态")
        self.status_view.setMarkdown("\n".join(lines))

    def load_current_state(self) -> None:
        context = self.current_run_context()
        if not context:
            return
        domain_id, _date_str = context
        path = memory_dir(domain_id) / "current_state.md"
        if not path.exists():
            QMessageBox.warning(self, "找不到记忆", f"current_state 不存在：{path}")
            return
        self.report_view.setMarkdown(path.read_text(encoding="utf-8"))

    def load_wiki_index(self) -> None:
        context = self.current_run_context()
        if not context:
            return
        domain_id, _date_str = context
        path = memory_wiki_dir(domain_id) / "index.md"
        if not path.exists():
            QMessageBox.warning(self, "找不到 Wiki", f"wiki index 不存在：{path}")
            return
        self.report_view.setMarkdown(path.read_text(encoding="utf-8"))

    def load_evidence_samples(self) -> None:
        context = self.current_run_context()
        if not context:
            return
        domain_id, date_str = context
        path = evidence_dir(domain_id) / f"{date_str}_evidence.jsonl"
        records = read_jsonl(path, limit=20)
        if not records:
            QMessageBox.warning(self, "找不到证据", f"证据文件不存在或为空：{path}")
            return
        lines = [f"# Evidence Samples：{domain_id}", "", f"日期：{date_str}", ""]
        for record in records:
            metrics = []
            for label, key in [("赞", "like_count_num"), ("藏", "collect_count_num"), ("评", "comment_count_num")]:
                if record.get(key) is not None:
                    metrics.append(f"{label}{record.get(key)}")
            lines.extend(
                [
                    f"## {record.get('title', '未命名样本')}",
                    "",
                    f"- evidence_id：`{record.get('evidence_id', '')}`",
                    f"- topic：{record.get('topic_name', '')}",
                    f"- author：{record.get('author', '')}",
                    f"- keywords：{', '.join(record.get('keywords', []))}",
                    f"- metrics：{', '.join(metrics) or '无'}",
                    f"- link：{record.get('link', '')}",
                    "",
                ]
            )
        self.report_view.setMarkdown("\n".join(lines))

    def load_rule_candidates(self) -> None:
        context = self.current_run_context()
        if not context:
            return
        domain_id, date_str = context
        md_path = processed_dir(domain_id) / f"{date_str}_rule_candidates.md"
        json_path = processed_dir(domain_id) / f"{date_str}_rule_candidates.json"
        if md_path.exists():
            self.report_view.setMarkdown(md_path.read_text(encoding="utf-8"))
            return
        if json_path.exists():
            payload = load_json_file(json_path)
            self.report_view.setMarkdown("```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```")
            return
        self.report_view.setMarkdown("暂无规则候选。请先运行“规则评估”。")

    def open_manual_corrections(self) -> None:
        context = self.current_run_context()
        if not context:
            return
        domain_id, _date_str = context
        path = memory_dir(domain_id) / "manual_corrections.jsonl"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                '{"id":"fix_topic_example","enabled":true,"match":{"title_contains":"关键词"},"set":{"topic_name":"人工主题","topic_cluster_id":"manual_人工主题","manual_note":"说明原因"}}\n',
                encoding="utf-8",
            )
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except OSError as exc:
            QMessageBox.warning(self, "无法打开文件", str(exc))
            return
        self.report_view.setMarkdown(
            f"已打开人工纠错文件：\n\n`{path}`\n\n保存后重新运行流程，`apply_manual_corrections` 会自动应用。"
        )

    def load_trend_tables(self) -> None:
        context = self.current_run_context()
        if not context:
            return
        domain_id, _date_str = context
        trends_dir = memory_trends_dir(domain_id)
        files = [
            trends_dir / "topic_daily.csv",
            trends_dir / "author_daily.csv",
            trends_dir / "keyword_daily.csv",
            trends_dir / "pattern_daily.csv",
            trends_dir / "trend_events.jsonl",
            memory_dir(domain_id) / "entities" / "topics.csv",
            memory_dir(domain_id) / "entities" / "authors.csv",
            memory_dir(domain_id) / "entities" / "keywords.csv",
            memory_dir(domain_id) / "entities" / "brands_or_ips.csv",
            memory_dir(domain_id) / "entities" / "entity_comparison.csv",
            memory_dir(domain_id) / "patterns" / "content_patterns.csv",
            memory_dir(domain_id) / "patterns" / "title_templates.csv",
            memory_dir(domain_id) / "patterns" / "demand_signals.csv",
        ]
        lines = [f"# 长期趋势表：{domain_id}", ""]
        for path in files:
            lines.extend([f"## {path.name}", ""])
            if not path.exists():
                lines.extend(["暂无文件。", ""])
                continue
            preview = path.read_text(encoding="utf-8-sig").splitlines()[:12]
            lines.extend(["```text", *preview, "```", ""])
        self.report_view.setMarkdown("\n".join(lines))

    def load_report(self) -> None:
        context = self.current_run_context()
        if not context:
            return
        domain_id, date_str = context
        path = market_report_dir(domain_id) / f"{date_str}_小红书市场局势报告.md"
        if not path.exists():
            QMessageBox.warning(self, "找不到主报告", f"市场局势报告不存在：{path}")
            return
        self.report_view.setMarkdown(path.read_text(encoding="utf-8"))


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
