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
from pipeline.common import load_domains_config
from storage.paths import get_project_root, normalize_date, processed_dir, report_dir


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


class CommandWorker(QThread):
    line = Signal(str)
    finished_ok = Signal(bool)

    def __init__(self, commands: list[list[str]], env: dict[str, str]) -> None:
        super().__init__()
        self.commands = commands
        self.env = env

    def run(self) -> None:
        ok = True
        for command in self.commands:
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
                ok = False
                break
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
        self.run_update_kb = QCheckBox("更新知识库")
        run_btn = QPushButton("运行完整流程")
        run_btn.clicked.connect(self.run_pipeline)
        report_btn = QPushButton("打开日报")
        report_btn.clicked.connect(self.load_report)
        top.addWidget(QLabel("项目"))
        top.addWidget(self.run_domain)
        top.addWidget(QLabel("日期"))
        top.addWidget(self.run_date)
        top.addWidget(self.run_download_images)
        top.addWidget(self.run_update_kb)
        top.addWidget(run_btn)
        top.addWidget(report_btn)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.report_view = QTextBrowser()
        splitter.addWidget(self.log_view)
        splitter.addWidget(self.report_view)
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
        py = sys.executable
        commands = [
            [py, "-m", "pipeline.run_daily", "--domain", domain_id, "--date", date_value],
            [py, "-m", "pipeline.clean_notes", "--domain", domain_id, "--date", date_value],
            [py, "-m", "pipeline.analyze_images", "--domain", domain_id, "--date", date_value],
            [py, "-m", "pipeline.compute_metrics", "--domain", domain_id, "--date", date_value],
            [py, "-m", "pipeline.merge_raw", "--domain", domain_id, "--date", date_value, "--days", "30"],
            [py, "-m", "pipeline.generate_report", "--domain", domain_id, "--date", date_value],
        ]
        if self.run_download_images.isChecked():
            commands[2].append("--download")
        if self.run_update_kb.isChecked():
            commands.append([py, "-m", "pipeline.update_knowledge_base", "--domain", domain_id, "--date", date_value])
        self.log_view.clear()
        self.append_log(f"开始运行项目：{domain_id}")
        self.worker = CommandWorker(commands, env)
        self.worker.line.connect(self.append_log)
        self.worker.finished_ok.connect(self.on_pipeline_finished)
        self.worker.start()

    def on_pipeline_finished(self, ok: bool) -> None:
        self.append_log("流程完成。" if ok else "流程中断。")
        if ok:
            self.load_report()

    def load_report(self) -> None:
        domain_id = self.run_domain.currentData()
        if not domain_id:
            return
        date_str = normalize_date(self.run_date.text().strip() or "today")
        path = report_dir(date_str, domain_id) / f"{date_str}_小红书趋势日报.md"
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
