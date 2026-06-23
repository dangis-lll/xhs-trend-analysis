from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


def llm_enabled() -> bool:
    return bool(os.getenv("DEEPSEEK_API_KEY"))


def get_deepseek_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY")
    return OpenAI(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
    )


def call_deepseek(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.2,
) -> str:
    client = get_deepseek_client()
    response = client.chat.completions.create(
        model=model or os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL),
        messages=messages,
        temperature=temperature,
        stream=False,
    )
    return response.choices[0].message.content or ""


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def expand_keywords_with_llm(
    *,
    domain_name: str,
    research_brief: str,
    seed_keywords: list[str],
    target_count: int = 30,
    model: str | None = None,
) -> dict[str, Any]:
    prompt = {
        "domain_name": domain_name,
        "research_brief": research_brief,
        "seed_keywords": seed_keywords,
        "target_count": target_count,
        "role": "你是小红书趋势调研的关键词规划师，目标是生成可搜索、可验证、可分组追踪的关键词池。",
        "method": {
            "step_1_topic_frame": [
                "主题对象：人 / 产品 / 场景 / 问题 / 竞品 / 内容形式",
                "主题动作：测评 / 对比 / 避坑 / 清单 / 教程 / 复盘 / 吐槽 / 观点",
                "主题情绪：焦虑 / 省钱 / 爽感 / 争议 / 共鸣 / 反差",
                "主题收益：省钱 / 省时间 / 少踩坑 / 决策更清楚 / 更好看 / 更好玩",
            ],
            "step_2_signal_mix": [
                "平台侧信号：高互动内容、近期反复出现的标题句式、封面信息层级、收藏型内容",
                "需求侧信号：用户正在纠结什么、反复踩什么坑、想比较什么、想买前确认什么",
                "项目侧信号：研究目标、目标人群、可持续追踪的内容支柱",
            ],
            "step_3_expand_angles": [
                "每个核心词至少扩展人群、场景、产品、需求、痛点、情绪、决策、内容形式 8 类角度",
                "优先生成小红书用户真的会搜索的口语化词，不要只给行业大词",
                "为后续趋势分析保留可对比的同义词和上下游词",
            ],
        },
        "requirements": [
            "围绕小红书搜索调研扩展关键词",
            "覆盖人群、场景、产品、需求、痛点、情绪、决策词",
            "避免过宽泛、过抽象、无搜索价值的词",
            "不要生成需要进入详情页才能验证的关键词",
            "不要生成违法、灰产、规避平台风控相关关键词",
            "每个关键词必须说明搜索意图和为什么值得纳入每日追踪",
            "关键词要能分层：核心词、长尾词、竞品/品牌词、痛点词、内容形式词",
            "只输出 JSON",
        ],
        "output_schema": {
            "keywords": [
                {
                    "keyword": "关键词",
                    "dimension": "核心词/人群/场景/产品/需求/痛点/情绪/决策/竞品/内容形式/季节热点",
                    "search_intent": "用户搜索这个词想解决什么问题",
                    "signal_type": "platform/need/project/seasonal/competitor",
                    "reason": "为什么值得搜索",
                    "priority": "high/medium/low",
                    "expected_use": "用于趋势监测/选题发现/竞品观察/痛点验证/爆款结构分析",
                    "risk_note": "可能太宽泛/太窄/容易跑偏/无风险",
                }
            ],
            "keyword_groups": [
                {
                    "group_name": "分组名",
                    "keywords": ["关键词1", "关键词2"],
                    "tracking_goal": "这个分组每天观察什么变化",
                }
            ],
            "negative_keywords": ["建议排除或暂不追踪的词"],
        },
    }
    content = call_deepseek(
        [
            {
                "role": "system",
                "content": "你是小红书趋势研究和搜索关键词规划专家。你擅长把模糊调研目标拆成可搜索、可追踪、可复盘的关键词池。你必须输出严格 JSON，不要输出 Markdown。",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        model=model,
        temperature=0.3,
    )
    return extract_json_object(content)


def analyze_with_llm(
    metrics: dict[str, Any],
    top_notes: list[dict[str, Any]],
    terms: list[dict[str, Any]],
    trends: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not llm_enabled():
        return {
            "enabled": False,
            "trend_overview": [],
            "hotspot_signals": [],
            "topic_momentum": [],
            "content_patterns": [],
            "evidence_cases": [],
            "anomaly_risks": [],
            "validation_plan": [],
            "low_priority_content_ideas": [],
        }

    payload = {
        "metrics": metrics,
        "top_notes": top_notes[:20],
        "top_collected_notes": metrics.get("top_collected_notes", [])[:10],
        "top_discussed_notes": metrics.get("top_discussed_notes", [])[:10],
        "terms": terms[:30],
        "trends": (trends or [])[:30],
        "data_scope": {
            "source": "小红书搜索结果页",
            "search_page_only": True,
            "allowed_fields": [
                "标题",
                "作者",
                "关键词",
                "搜索排名",
                "点赞/收藏/评论/分享数",
                "图文或视频类型",
                "封面图片地址和尺寸",
                "搜索卡片可见文本",
            ],
            "forbidden_assumptions": [
                "不要分析详情页正文、评论内容、话题标签、IP 属地、完整图片列表",
                "不要说用户评论区具体在讨论什么，除非输入数据里有评论文本",
                "不要把搜索页排名等同于全站热度，只能作为搜索样本信号",
            ],
        },
        "analysis_framework": {
            "logic_order": [
                "先判断数据质量和样本边界",
                "再识别趋势方向：升温、降温、稳定、弱信号",
                "再解释热点由什么信号支撑：样本量、近期占比、高赞率、收藏/点赞比、评论/点赞比、重复标题词",
                "最后给验证动作；选题建议只作为附属产物，不要喧宾夺主",
            ],
            "trend_signal_types": [
                "volume_signal：样本数、关键词覆盖、主题样本量",
                "engagement_signal：点赞分布、高赞率、P90、收藏/点赞、评论/点赞、分享/点赞",
                "freshness_signal：近 N 天发布占比、近 3 天上升词",
                "structure_signal：反复出现的标题句式、内容类型、图文/视频比例",
                "risk_signal：样本不足、发布时间缺失、单条爆款带偏、搜索页不可见字段缺失",
            ],
            "classification_rules": [
                "趋势：至少需要多个样本、主题聚合或历史上升词支撑",
                "热点：可以由少数高互动样本触发，但必须标注事件型/结构型/需求型/弱信号",
                "内容模式：只分析标题、卡片和互动指标能支持的结构，不分析正文细节",
                "选题建议：数量少于趋势/热点结论，且放在 low_priority_content_ideas",
            ],
        },
        "requirements": [
            "只基于输入数据做分析，不要编造不存在的指标",
            "每条结论必须引用样本标题、关键词、主题指标或具体数字作为 evidence",
            "不要把单条高赞事件直接当成长期趋势，必须标注 signal_type 和 confidence",
            "优先输出趋势、热点、主题动能和验证计划；降低选题建议占比",
            "如果样本不足、发布时间缺失或搜索页字段不完整，要写入 anomaly_risks",
            "输出 JSON，字段必须包括 trend_overview、hotspot_signals、topic_momentum、content_patterns、evidence_cases、anomaly_risks、validation_plan、low_priority_content_ideas",
            "所有字段必须都是数组；数组元素必须是对象，不要返回单个字符串",
        ],
        "output_schema": {
            "trend_overview": [
                {
                    "trend": "趋势名称",
                    "direction": "rising/stable/cooling/uncertain",
                    "why": "为什么这样判断",
                    "evidence": "指标数字或历史上升词",
                    "confidence": "high/medium/low",
                }
            ],
            "hotspot_signals": [
                {
                    "hotspot": "热点或强信号",
                    "signal_type": "event/structure/need/seasonal/weak_signal",
                    "trigger": "由什么触发关注",
                    "evidence": "样本标题/关键词/互动指标",
                    "confidence": "high/medium/low",
                }
            ],
            "topic_momentum": [
                {
                    "topic": "主题名",
                    "momentum": "strong/medium/weak",
                    "drivers": "样本量、高赞率、近期占比、收藏/评论比等驱动",
                    "evidence": "主题指标或代表标题",
                    "next_validation": "下一步验证方式",
                }
            ],
            "content_patterns": [
                {
                    "pattern": "可复用模式名",
                    "observed_in": "哪些标题或关键词体现",
                    "signal_value": "它代表收藏型/评论型/点击型/搜索型中的哪类",
                    "evidence": "证据标题或数据",
                    "risk_note": "过度复用风险",
                }
            ],
            "evidence_cases": [
                {
                    "title": "样本标题",
                    "case_type": "high_like/high_collect/high_comment/recent_rising",
                    "why_it_matters": "为什么是证据样本",
                    "metrics": "点赞/收藏/评论/关键词等",
                }
            ],
            "anomaly_risks": [
                {
                    "risk": "风险或异常",
                    "impact": "会怎样影响趋势判断",
                    "evidence": "证据",
                    "mitigation": "如何规避或补采",
                }
            ],
            "validation_plan": [
                {
                    "action": "验证动作",
                    "why": "为什么优先做",
                    "expected_signal": "预期看到什么信号",
                }
            ],
            "low_priority_content_ideas": [
                {
                    "idea": "少量选题或内容方向",
                    "based_on_signal": "基于哪个趋势或热点",
                    "priority": "medium/low",
                    "risk_note": "风险",
                }
            ],
        },
    }
    try:
        content = call_deepseek(
            [
                {
                    "role": "system",
                    "content": "你是小红书搜索页趋势雷达分析师。你优先判断趋势、热点、信号强弱、证据链和验证计划；选题建议只放在次要位置。你只能基于搜索结果页可得字段分析，必须输出严格 JSON，不要输出 Markdown。",
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.2,
        )
        result = extract_json_object(content)
        result["enabled"] = True
        return result
    except Exception as exc:
        return {
            "enabled": False,
            "error": str(exc),
            "trend_overview": [],
            "hotspot_signals": [],
            "topic_momentum": [],
            "content_patterns": [],
            "evidence_cases": [],
            "anomaly_risks": [],
            "validation_plan": [],
            "low_priority_content_ideas": [],
        }


def save_llm_input(path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
