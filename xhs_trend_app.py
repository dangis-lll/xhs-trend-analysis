from __future__ import annotations

import json
import os
import re
import subprocess
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
from analysis.pipeline_status import init_status, update_step
from pipeline.common import load_domains_config
from storage.paths import (
    evidence_dir,
    get_project_root,
    memory_dir,
    memory_trends_dir,
    memory_wiki_dir,
    normalize_date,
    processed_dir,
    report_dir,
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


class CommandWorker(QThread):
    line = Signal(str)
    finished_ok = Signal(bool)

    def __init__(
        self,
        commands: list[tuple[str, list[str]]],
        env: dict[str, str],
        *,
        domain_id: str,
        date_str: str,
    ) -> None:
        super().__init__()
        self.commands = commands
        self.env = env
        self.domain_id = domain_id
        self.date_str = date_str

    def run(self) -> None:
        ok = True
        init_status(self.domain_id, self.date_str, [step for step, _ in self.commands])
        for step, command in self.commands:
            update_step(self.domain_id, self.date_str, step, status="running")
            self.line.emit("> " + " ".join(command))
            process = subprocess.Popen(
                command,
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self.env,
            )
            assert process.stdout is not None
            for line in process.stdout:
                self.line.emit(line.rstrip())
            code = process.wait()
            if code != 0:
                self.line.emit(f"命令失败，退出码：{code}")
                update_step(self.domain_id, self.date_str, step, status="failed", exit_code=code, error=f"exit_code={code}")
                ok = False
                break
            update_step(self.domain_id, self.date_str, step, status="success", exit_code=0)
        self.finished_ok.emit(ok)


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
        tabs = QTabWidget()
        tabs.addTab(self._build_project_tab(), "项目与关键词")
        tabs.addTab(self._build_run_tab(), "采集与报告")
        self.setCentralWidget(tabs)

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
        run_btn = QPushButton("运行完整流程")
        run_btn.clicked.connect(self.run_pipeline)
        report_btn = QPushButton("打开日报")
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

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        right_panel = QSplitter(Qt.Orientation.Vertical)
        self.status_view = QTextBrowser()
        self.report_view = QTextBrowser()
        right_panel.addWidget(self.status_view)
        right_panel.addWidget(self.report_view)
        right_panel.setSizes([220, 560])
        splitter.addWidget(self.log_view)
        splitter.addWidget(right_panel)
        splitter.setSizes([480, 780])
        layout.addWidget(splitter)
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
        self.keywords_per_day.setValue(int(collection.get("keywords_per_day") or 10))
        self.notes_per_keyword.setValue(int(collection.get("notes_per_keyword") or 50))
        self.max_daily_notes.setValue(int(collection.get("max_daily_notes") or 500))
        self.login_timeout.setValue(int(collection.get("login_timeout") or 180))
        self.slow_mo.setValue(int(collection.get("slow_mo") or 0))
        self.headless.setChecked(bool(collection.get("headless") or False))

    def new_domain(self) -> None:
        self.domain_id.setText("")
        self.domain_name.setText("")
        self.research_brief.setPlainText("")
        self.seed_keywords.setPlainText("")
        self.keywords_per_day.setValue(10)
        self.notes_per_keyword.setValue(50)
        self.max_daily_notes.setValue(500)
        self.login_timeout.setValue(180)
        self.slow_mo.setValue(0)
        self.headless.setChecked(False)
        self.domain_list.clearSelection()

    def build_domain_from_form(self) -> dict[str, Any]:
        name = self.domain_name.text().strip()
        domain_id = self.domain_id.text().strip() or safe_id(name)
        return {
            "id": domain_id,
            "name": name or domain_id,
            "description": self.research_brief.toPlainText().strip(),
            "seed_keywords": keyword_lines(self.seed_keywords.toPlainText()),
            "collection": {
                "keywords_per_day": self.keywords_per_day.value(),
                "notes_per_keyword": self.notes_per_keyword.value(),
                "max_daily_notes": self.max_daily_notes.value(),
                "login_timeout": self.login_timeout.value(),
                "slow_mo": self.slow_mo.value(),
                "headless": self.headless.isChecked(),
            },
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
        py = sys.executable
        commands = [
            ("run_daily", [py, "-m", "pipeline.run_daily", "--domain", domain_id, "--date", date_value]),
            ("clean_notes", [py, "-m", "pipeline.clean_notes", "--domain", domain_id, "--date", date_value]),
            ("apply_manual_corrections", [py, "-m", "pipeline.apply_manual_corrections", "--domain", domain_id, "--date", date_value]),
            ("sample_detail_pages", [py, "-m", "pipeline.sample_detail_pages", "--domain", domain_id, "--date", date_value]),
            ("analyze_images", [py, "-m", "pipeline.analyze_images", "--domain", domain_id, "--date", date_value]),
            ("compute_metrics", [py, "-m", "pipeline.compute_metrics", "--domain", domain_id, "--date", date_value]),
            ("compute_search_page_signals", [py, "-m", "pipeline.compute_search_page_signals", "--domain", domain_id, "--date", date_value]),
            ("generate_evidence", [py, "-m", "pipeline.generate_evidence", "--domain", domain_id, "--date", date_value]),
            ("evaluate_data_quality", [py, "-m", "pipeline.evaluate_data_quality", "--domain", domain_id, "--date", date_value]),
            ("merge_history_clean", [py, "-m", "pipeline.merge_history_clean", "--domain", domain_id, "--date", date_value, "--days", "30"]),
        ]
        if self.run_download_images.isChecked():
            commands[4][1].append("--download")
        if self.run_detail_sampling.isChecked():
            commands[3][1].append("--enable")
        if self.run_rule_analysis.isChecked():
            insert_at = 7
            commands[insert_at:insert_at] = [
                ("evaluate_rules", [py, "-m", "pipeline.evaluate_rules", "--domain", domain_id, "--date", date_value]),
                ("suggest_rule_candidates", [py, "-m", "pipeline.suggest_rule_candidates", "--domain", domain_id, "--date", date_value]),
            ]
        if self.run_market_report.isChecked():
            commands.append(("generate_market_report", [py, "-m", "pipeline.generate_market_report", "--domain", domain_id, "--date", date_value]))
        if self.run_update_memory.isChecked():
            commands.extend(
                [
                    ("update_memory", [py, "-m", "pipeline.update_memory", "--domain", domain_id, "--date", date_value]),
                    ("update_rollups", [py, "-m", "pipeline.update_rollups", "--domain", domain_id, "--date", date_value]),
                ]
            )
        commands.append(("generate_report", [py, "-m", "pipeline.generate_report", "--domain", domain_id, "--date", date_value]))
        if self.run_update_kb.isChecked():
            commands.append(("update_knowledge_base", [py, "-m", "pipeline.update_knowledge_base", "--domain", domain_id, "--date", date_value]))
        self.log_view.clear()
        self.append_log(f"开始运行项目：{domain_id}")
        self.load_run_status()
        self.worker = CommandWorker(commands, env, domain_id=domain_id, date_str=date_str)
        self.worker.line.connect(self.append_log)
        self.worker.finished_ok.connect(self.on_pipeline_finished)
        self.worker.start()

    def on_pipeline_finished(self, ok: bool) -> None:
        self.append_log("流程完成。" if ok else "流程中断。")
        self.load_run_status()
        if ok:
            self.load_report()

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
                    f"- 等级：`{quality.get('quality_level', 'unknown')}`",
                    f"- raw_count：`{quality.get('raw_count', 0)}`",
                    f"- clean_count：`{quality.get('clean_count', 0)}`",
                    f"- memory_update_allowed：`{quality.get('memory_update_allowed', False)}`",
                    f"- warnings：`{', '.join(quality.get('warnings', [])) or '无'}`",
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
                    f"- content_pattern covered_rate：`{pattern.get('covered_rate', 0):.2%}`",
                    f"- content_pattern other_rate：`{pattern.get('other_rate', 0):.2%}`",
                    f"- topic covered_rate：`{topic.get('covered_rate', 0):.2%}`",
                    f"- topic taxonomy_rule_rate：`{topic.get('taxonomy_rule_rate', 0):.2%}`",
                    f"- recommendations：`{', '.join(rule_effectiveness.get('recommendations', [])) or '无'}`",
                    "",
                ]
            )
        if rule_candidates:
            summary = rule_candidates.get("summary", {})
            lines.extend(
                [
                    "## 规则候选",
                    "",
                    f"- content_pattern candidates：`{summary.get('content_pattern_candidate_count', 0)}`",
                    f"- topic candidates：`{summary.get('topic_candidate_count', 0)}`",
                    "",
                ]
            )

        lines.extend(["## Pipeline", ""])
        if status:
            lines.append(f"- overall_status：`{status.get('overall_status', 'unknown')}`")
            for step in status.get("steps", []):
                name = step.get("name", "")
                step_status = step.get("status", "")
                error = step.get("error", "")
                suffix = f"，error: {error}" if error else ""
                lines.append(f"- `{name}`：{step_status}{suffix}")
        else:
            lines.append("- 暂无 pipeline_status 文件。")
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
        market_path = ROOT / "projects" / str(domain_id) / "reports" / "market" / f"{date_str}_小红书市场局势报告.md"
        path = market_path if market_path.exists() else report_dir(date_str, domain_id) / f"{date_str}_小红书趋势日报.md"
        if not path.exists():
            QMessageBox.warning(self, "找不到日报", f"日报不存在：{path}")
            return
        self.report_view.setMarkdown(path.read_text(encoding="utf-8"))


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
