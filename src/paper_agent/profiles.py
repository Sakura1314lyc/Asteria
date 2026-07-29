from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReviewProfile:
    name: str
    description: str
    requires_manual_screening: bool
    default_sections: tuple[str, ...]
    evidence_warning: str


PROFILES = {
    "narrative": ReviewProfile(
        name="narrative",
        description="Broad evidence-grounded narrative review.",
        requires_manual_screening=False,
        default_sections=("背景", "主题综合", "争议", "局限", "未来方向"),
        evidence_warning="Narrative coverage is not exhaustive.",
    ),
    "scoping": ReviewProfile(
        name="scoping",
        description="Map concepts, methods, evidence types, and research gaps.",
        requires_manual_screening=True,
        default_sections=("范围与方法", "概念图谱", "方法分布", "证据空白", "结论"),
        evidence_warning="Scoping reviews map evidence and do not necessarily estimate effects.",
    ),
    "systematic": ReviewProfile(
        name="systematic",
        description="Protocol-led search and human screening workflow.",
        requires_manual_screening=True,
        default_sections=("研究方案", "纳排流程", "研究特征", "证据综合", "局限"),
        evidence_warning="Human screening and formal risk-of-bias assessment are required.",
    ),
    "thesis": ReviewProfile(
        name="thesis",
        description="Thesis-oriented landscape, gap, and proposal development.",
        requires_manual_screening=False,
        default_sections=(
            "研究背景",
            "理论基础",
            "相关工作",
            "研究空白",
            "研究设计建议",
        ),
        evidence_warning="Research proposals must be validated with domain supervision.",
    ),
}


def get_profile(name: str) -> ReviewProfile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown review profile {name!r}; choose from {', '.join(PROFILES)}"
        ) from exc
