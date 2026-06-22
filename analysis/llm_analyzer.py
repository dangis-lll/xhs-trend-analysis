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
            "summary": [],
            "topic_insights": [],
            "case_analysis": [],
            "pattern_library": [],
            "keyword_suggestions": [],
            "content_suggestions": [],
            "risk_notes": [],
            "next_actions": [],
        }

    payload = {
        "metrics": metrics,
        "top_notes": top_notes[:20],
        "terms": terms[:30],
        "trends": (trends or [])[:30],
        "analysis_framework": {
            "describe_before_explain": "先描述数据看到了什么，再解释可能原因，不把单条爆款直接等同于稳定趋势",
            "signal_types": [
                "平台侧信号：关键词样本量、点赞分布、高赞率、近期发布占比、重复标题句式",
                "内容侧信号：标题钩子、清单/避坑/测评/观点/故事等结构",
                "需求侧信号：用户想省钱、避坑、比较、决策、获得情绪共鸣",
                "风险侧信号：样本不足、近期占比低、单个事件带偏、标题党或争议过高",
            ],
            "case_dimensions": [
                "标题钩子",
                "场景/人群",
                "内容结构",
                "互动机制",
                "可复用点",
                "不可复用或需谨慎处",
            ],
            "topic_output_rule": "不要只说热，要说明为什么热、证据是什么、下一步怎么验证",
        },
        "requirements": [
            "只基于输入数据做分析，不要编造不存在的指标",
            "每条结论必须引用样本标题、关键词或指标数字作为证据",
            "不要把单条高赞事件直接当成长期趋势，必须标注是事件型/结构型/需求型信号",
            "如果数据不足或近期样本少，要明确写出置信度和限制",
            "输出 JSON，字段包括 summary、topic_insights、case_analysis、pattern_library、keyword_suggestions、content_suggestions、risk_notes、next_actions",
            "summary、topic_insights、case_analysis、pattern_library、keyword_suggestions、content_suggestions、risk_notes、next_actions 必须都是数组，不要返回单个字符串",
            "数组元素必须使用对象，例如 {\"conclusion\":\"...\", \"evidence\":\"...\", \"confidence\":\"high/medium/low\"}",
            "case_analysis 需要分析突出帖子为什么值得关注",
            "content_suggestions 必须包含可执行标题方向、内容结构、互动钩子和风险提示",
            "keyword_suggestions 必须说明新增关键词的维度和验证目标",
        ],
        "output_schema": {
            "summary": [
                {
                    "conclusion": "一句关键结论",
                    "evidence": "对应指标或样本标题",
                    "confidence": "high/medium/low",
                }
            ],
            "topic_insights": [
                {
                    "topic": "主题或关键词",
                    "insight": "洞察",
                    "evidence": "样本数/高赞率/代表标题",
                    "signal_type": "event/structure/need/seasonal/weak_signal",
                    "next_validation": "下一步如何验证",
                }
            ],
            "case_analysis": [
                {
                    "title": "样本标题",
                    "why_it_matters": "为什么突出",
                    "hook": "标题或封面钩子",
                    "reusable_pattern": "可复用模式",
                    "risk_note": "风险或不适合复用处",
                }
            ],
            "pattern_library": [
                {
                    "pattern": "可复用模式名",
                    "fit_conditions": "适用条件",
                    "evidence": "证据标题或数据",
                    "template": "可复用标题/内容骨架",
                }
            ],
            "keyword_suggestions": [
                {
                    "keyword": "建议新增关键词",
                    "dimension": "场景/痛点/产品/内容形式/竞品/季节",
                    "reason": "为什么纳入",
                    "tracking_goal": "每天观察什么",
                    "priority": "high/medium/low",
                }
            ],
            "content_suggestions": [
                {
                    "title_direction": "标题方向",
                    "structure": "三段式结构",
                    "interaction_hook": "评论区互动问题",
                    "evidence": "来自哪个指标或样本",
                    "risk_note": "风险",
                }
            ],
            "risk_notes": [
                {
                    "risk": "风险",
                    "evidence": "证据",
                    "mitigation": "规避方式",
                }
            ],
            "next_actions": [
                {
                    "action": "下一步动作",
                    "why": "原因",
                    "expected_output": "产出",
                }
            ],
        },
    }
    try:
        content = call_deepseek(
            [
                {
                    "role": "system",
                    "content": "你是小红书趋势分析师和内容运营策略师。你擅长把平台数据拆成趋势信号、用户需求、可复用内容模式和下一步动作。必须输出严格 JSON，不要输出 Markdown。",
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
            "summary": [],
            "topic_insights": [],
            "case_analysis": [],
            "pattern_library": [],
            "keyword_suggestions": [],
            "content_suggestions": [],
            "risk_notes": [],
            "next_actions": [],
        }


def save_llm_input(path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
