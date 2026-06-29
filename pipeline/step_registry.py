from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineStep:
    name: str
    module: str
    order: int
    optional: bool
    requires: tuple[str, ...]
    produces: tuple[str, ...]
    flag_name: str | None = None
    command_args: tuple[str, ...] = ()
    scheduled_command_args: tuple[str, ...] = ()
    scheduled_default: bool = False


PIPELINE_STEPS: tuple[PipelineStep, ...] = (
    PipelineStep("run_daily", "pipeline.run_daily", 10, False, (), ("raw/all_raw.xlsx",), scheduled_command_args=("--scheduled", "--once-per-day")),
    PipelineStep("clean_notes", "pipeline.clean_notes", 20, False, ("raw/all_raw.xlsx",), ("processed/clean_notes",)),
    PipelineStep("apply_manual_corrections", "pipeline.apply_manual_corrections", 30, False, ("processed/clean_notes",), ("processed/clean_notes_corrected",)),
    PipelineStep("sample_detail_pages", "pipeline.sample_detail_pages", 40, True, ("processed/clean_notes",), ("details/detail_sample_targets",), flag_name="detail_sampling", command_args=("--enable",)),
    PipelineStep("analyze_images", "pipeline.analyze_images", 50, True, ("processed/clean_notes",), ("processed/clean_notes_image_enriched",), flag_name="download_images", command_args=("--download",)),
    PipelineStep("compute_metrics", "pipeline.compute_metrics", 60, False, ("processed/clean_notes",), ("processed/metrics",)),
    PipelineStep("compute_search_page_signals", "pipeline.compute_search_page_signals", 70, False, ("processed/clean_notes",), ("processed/search_signals",)),
    PipelineStep("evaluate_rules", "pipeline.evaluate_rules", 80, True, ("processed/clean_notes",), ("processed/rule_effectiveness",), flag_name="rule_analysis", scheduled_default=True),
    PipelineStep("suggest_rule_candidates", "pipeline.suggest_rule_candidates", 90, True, ("processed/rule_effectiveness",), ("processed/rule_candidates",), flag_name="rule_analysis", scheduled_default=True),
    PipelineStep("generate_evidence", "pipeline.generate_evidence", 100, False, ("processed/clean_notes",), ("memory/evidence",)),
    PipelineStep("evaluate_data_quality", "pipeline.evaluate_data_quality", 110, False, ("processed/clean_notes",), ("processed/data_quality",)),
    PipelineStep("merge_history_clean", "pipeline.merge_history_clean", 120, False, ("processed/clean_notes",), ("processed/history_clean_notes",), command_args=("--days", "30")),
    PipelineStep("generate_market_report", "pipeline.generate_market_report", 130, True, ("processed/data_quality",), ("reports/market",), flag_name="market_report", scheduled_default=True),
    PipelineStep("update_memory", "pipeline.update_memory", 140, True, ("processed/data_quality",), ("memory/current_state",), flag_name="update_memory", scheduled_default=True),
    PipelineStep("update_rollups", "pipeline.update_rollups", 150, True, ("memory/daily",), ("memory/rollups",), flag_name="update_memory", scheduled_default=True),
    PipelineStep("update_knowledge_base", "pipeline.update_knowledge_base", 160, True, ("processed/rule_candidates",), ("knowledge-base",), flag_name="update_kb", scheduled_default=True),
)

STEP_BY_NAME = {step.name: step for step in PIPELINE_STEPS}
DEFAULT_SCHEDULED_STEPS = tuple(step.name for step in PIPELINE_STEPS if not step.optional or step.scheduled_default)


def build_step_plan(enabled_optional: set[str] | None = None, *, scheduled_defaults: bool = False) -> list[PipelineStep]:
    enabled = enabled_optional or set()
    plan = [
        step
        for step in PIPELINE_STEPS
        if not step.optional or step.name in enabled or (scheduled_defaults and step.scheduled_default)
    ]
    return sorted(plan, key=lambda step: step.order)


def step_names(plan: list[PipelineStep]) -> list[str]:
    return [step.name for step in plan]


def build_step_command(
    step_name: str,
    *,
    domain_id: str,
    date_value: str,
    py: str,
    scheduled: bool = False,
) -> list[str]:
    step = STEP_BY_NAME[step_name]
    command = [py, "-m", step.module, "--domain", domain_id, "--date", date_value]
    command.extend(step.command_args)
    if scheduled:
        command.extend(step.scheduled_command_args)
    return command
