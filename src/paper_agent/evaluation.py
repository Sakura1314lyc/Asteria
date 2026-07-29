from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .artifacts import citation_audit, load_state, write_json


@dataclass(slots=True)
class EvaluationResult:
    run_id: str
    stage_complete: bool
    citation_structure: float
    citation_grounding_proxy: float
    citation_grounding_assessability: float
    evidence_completeness: float
    identifier_coverage: float
    section_coverage: float
    cs_evidence_completeness: float
    reproducibility_reporting: float
    overall: float
    failures: list[str]
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


REQUIRED_SECTION_CONCEPTS = (
    ("scope", ("范围", "方法", "method", "scope")),
    ("synthesis", ("综合", "证据", "synthesis", "evidence")),
    ("limitations", ("局限", "限制", "limitation")),
    ("conclusion", ("结论", "conclusion")),
    ("references", ("参考文献", "references", "bibliography")),
)


def evaluate_run(run_dir: Path | str) -> EvaluationResult:
    path = Path(run_dir).resolve()
    state = load_state(path)
    failures: list[str] = []
    audit = citation_audit(state.report, state.papers)
    citation_score = float(audit["paragraph_citation_coverage"])
    if audit["unknown_citations"]:
        citation_score *= 0.5
        failures.append("unknown citations are present")
    if not audit["cited_source_count"]:
        citation_score = 0.0
        failures.append("no known source is cited")
    grounding = audit["grounding_proxy"]
    alignment_rate = grounding.get("alignment_rate")
    assessment_coverage = grounding.get("assessment_coverage")
    if assessment_coverage is None:
        check_count = int(grounding.get("check_count", 0))
        assessment_coverage = (
            int(grounding.get("assessable_count", 0)) / check_count
            if check_count
            else 0.0
        )
    grounding_score = (
        float(alignment_rate) * float(assessment_coverage)
        if alignment_rate is not None
        else 0.0
    )
    if grounding.get("check_count", 0) and assessment_coverage < 0.5:
        failures.append("most citation claims are not assessable by the grounding proxy")
    if (
        grounding["assessable_count"] >= 2
        and alignment_rate is not None
        and float(alignment_rate) < 0.4
    ):
        failures.append("citation claim-source lexical alignment is weak")

    evidence_fields = 0
    evidence_present = 0
    for card in state.evidence:
        values = [
            card.relevance,
            card.objective,
            card.methods,
            card.data_or_sample,
            card.findings,
            card.limitations,
        ]
        evidence_fields += len(values)
        evidence_present += sum(bool(value) for value in values)
    evidence_score = evidence_present / evidence_fields if evidence_fields else 0.0
    if evidence_score < 0.7:
        failures.append("evidence cards are incomplete")

    resolved = sum(
        bool(paper.doi or paper.arxiv_id or paper.url) for paper in state.papers
    )
    identifier_score = resolved / len(state.papers) if state.papers else 0.0
    if identifier_score < 0.8:
        failures.append("too many papers lack a resolvable identifier")

    headings = [
        match.group(1).casefold()
        for match in re.finditer(r"^#{1,6}\s+(.+)$", state.report, re.MULTILINE)
    ]
    covered: dict[str, bool] = {}
    for name, synonyms in REQUIRED_SECTION_CONCEPTS:
        covered[name] = any(
            any(synonym in heading for synonym in synonyms) for heading in headings
        )
    section_score = sum(covered.values()) / len(covered)
    if section_score < 0.8:
        failures.append("report is missing expected scholarly sections")

    cs_fields = (
        "contribution_type",
        "problem",
        "core_contribution",
        "approach",
        "datasets",
        "baselines",
        "metrics",
        "headline_results",
        "ablations",
        "compute",
        "implementation_details",
        "threats_to_validity",
        "evidence_level",
    )
    cs_total = len(state.evidence) * len(cs_fields)
    cs_present = 0
    for card in state.evidence:
        for field in cs_fields:
            value = card.cs_evidence.get(field)
            if not value:
                continue
            if isinstance(value, str) and value in {"unclear", "未报告", "未抽取"}:
                continue
            cs_present += 1
    cs_score = cs_present / cs_total if cs_total else 0.0
    reproducibility_values = [
        float(item.get("overall", 0))
        for item in state.cs_analysis.get("reproducibility", [])
    ]
    reproducibility_score = (
        sum(reproducibility_values) / len(reproducibility_values)
        if reproducibility_values
        else 0.0
    )
    if cs_score < 0.5:
        failures.append("computer-science evidence fields are sparse")
    if reproducibility_score < 0.5:
        failures.append("reproducibility reporting is weak or unavailable")

    stage_complete = state.stage == "completed"
    if not stage_complete:
        failures.append(f"run stage is {state.stage}, not completed")
    overall = round(
        (
            citation_score * 0.2
            + grounding_score * 0.05
            + evidence_score * 0.15
            + identifier_score * 0.1
            + section_score * 0.15
            + cs_score * 0.2
            + reproducibility_score * 0.15
        )
        * (1.0 if stage_complete else 0.75),
        3,
    )
    result = EvaluationResult(
        run_id=state.run_id,
        stage_complete=stage_complete,
        citation_structure=round(citation_score, 3),
        citation_grounding_proxy=round(grounding_score, 3),
        citation_grounding_assessability=round(float(assessment_coverage), 3),
        evidence_completeness=round(evidence_score, 3),
        identifier_coverage=round(identifier_score, 3),
        section_coverage=round(section_score, 3),
        cs_evidence_completeness=round(cs_score, 3),
        reproducibility_reporting=round(reproducibility_score, 3),
        overall=overall,
        failures=failures,
        details={
            "citation_audit": audit,
            "citation_grounding": grounding,
            "covered_sections": covered,
            "paper_count": len(state.papers),
            "evidence_card_count": len(state.evidence),
            "quality_assessment_count": len(state.quality),
        },
    )
    write_json(path / "evaluation.json", result.to_dict())
    return result


def compare_evaluations(
    baseline: EvaluationResult,
    candidate: EvaluationResult,
) -> dict[str, Any]:
    metrics = (
        "citation_structure",
        "citation_grounding_proxy",
        "citation_grounding_assessability",
        "evidence_completeness",
        "identifier_coverage",
        "section_coverage",
        "cs_evidence_completeness",
        "reproducibility_reporting",
        "overall",
    )
    return {
        "baseline_run": baseline.run_id,
        "candidate_run": candidate.run_id,
        "deltas": {
            metric: round(
                getattr(candidate, metric) - getattr(baseline, metric),
                3,
            )
            for metric in metrics
        },
        "regressed": candidate.overall < baseline.overall,
    }
