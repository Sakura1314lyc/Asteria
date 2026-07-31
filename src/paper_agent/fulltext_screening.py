from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .domain import ScreeningStatus
from .screening import ScreeningConsensus, evaluate_consensus

RETRIEVAL_STATUSES = {
    "not_requested",
    "sought",
    "retrieved",
    "not_retrieved",
}

FULLTEXT_EXCLUSION_REASONS = {
    "wrong_topic": "主题或研究问题不符",
    "wrong_study_design": "研究设计不符",
    "wrong_population_or_context": "研究对象或场景不符",
    "wrong_intervention_or_system": "干预、方法或系统不符",
    "wrong_comparator": "对照不符",
    "wrong_outcomes_or_metrics": "结局或评价指标不符",
    "not_primary_research": "不是原始研究",
    "not_full_report": "不是完整研究报告",
    "duplicate_report": "同一研究的重复报告",
    "insufficient_information": "全文信息仍不足",
    "other": "其他预先定义的理由",
}


@dataclass(frozen=True, slots=True)
class FullTextDecision:
    project_id: str
    paper_id: int
    status: str
    reason: str
    exclusion_code: str = ""
    reviewer: str = "human"
    decided_at: str = ""


@dataclass(frozen=True, slots=True)
class FullTextConsensus:
    state: str
    status: str
    exclusion_code: str
    complete: bool
    conflict: bool


def evaluate_fulltext_consensus(
    decisions: Mapping[str, tuple[str, str]],
    reviewers: list[str],
) -> FullTextConsensus:
    base: ScreeningConsensus = evaluate_consensus(
        {reviewer: decision[0] for reviewer, decision in decisions.items()},
        reviewers,
    )
    code = ""
    if base.complete and base.status == ScreeningStatus.EXCLUDED:
        codes = {
            decisions[reviewer][1] for reviewer in reviewers if reviewer in decisions
        }
        if len(codes) != 1:
            return FullTextConsensus(
                state="awaiting_resolution",
                status=ScreeningStatus.MAYBE,
                exclusion_code="",
                complete=True,
                conflict=False,
            )
        code = next(iter(codes))
    return FullTextConsensus(
        state=base.state,
        status=base.status,
        exclusion_code=code,
        complete=base.complete,
        conflict=base.conflict,
    )


def validate_fulltext_decision(
    status: str,
    reason: str,
    exclusion_code: str,
) -> tuple[str, str, str]:
    normalized_status = status.strip().lower()
    normalized_reason = reason.strip()
    normalized_code = exclusion_code.strip().lower()
    if normalized_status not in {
        ScreeningStatus.INCLUDED,
        ScreeningStatus.EXCLUDED,
        ScreeningStatus.MAYBE,
    }:
        raise ValueError("Full-text status must be included, excluded, or maybe")
    if normalized_status == ScreeningStatus.EXCLUDED:
        if normalized_code not in FULLTEXT_EXCLUSION_REASONS:
            raise ValueError("A recognized primary exclusion reason is required")
        if not normalized_reason:
            raise ValueError("A full-text exclusion explanation is required")
    else:
        normalized_code = ""
    return normalized_status, normalized_reason, normalized_code
