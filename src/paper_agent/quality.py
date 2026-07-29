from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .models import EvidenceCard, Paper


@dataclass(slots=True)
class EvidenceQuality:
    paper_id: str
    rubric: str
    scores: dict[str, int]
    overall: float
    grade: str
    notes: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def assess_evidence_quality(
    paper: Paper,
    card: EvidenceCard,
) -> EvidenceQuality:
    """Appraise extractability, not scientific truth or risk of bias."""
    methods = card.methods.casefold()
    sample = card.data_or_sample.casefold()
    limitations = " ".join(card.limitations).casefold()
    missing_markers = {
        "",
        "未抽取",
        "未报告",
        "not reported",
        "unknown",
        "摘要未报告",
    }

    scores = {
        "identity_resolvable": 2
        if paper.doi or paper.arxiv_id
        else (1 if paper.url else 0),
        "abstract_available": 2
        if len(paper.abstract) >= 300
        else (1 if paper.abstract else 0),
        "methods_reported": 0
        if methods.strip() in missing_markers
        else (2 if len(methods) >= 80 else 1),
        "sample_reported": 0
        if sample.strip() in missing_markers
        else (2 if re.search(r"\d", sample) else 1),
        "findings_extractable": 2
        if len(card.findings) >= 2
        else (1 if card.findings else 0),
        "limitations_acknowledged": 0
        if not limitations or limitations in missing_markers
        else 2,
    }
    overall = round(sum(scores.values()) / (2 * len(scores)), 3)
    if overall >= 0.8:
        grade = "high"
    elif overall >= 0.5:
        grade = "moderate"
    else:
        grade = "low"
    notes = [
        (
            "Automated appraisal measures evidence extractability from available "
            "metadata/abstracts; it is not a formal risk-of-bias judgment."
        )
    ]
    if not paper.abstract:
        notes.append("Abstract unavailable.")
    if not paper.doi and not paper.arxiv_id:
        notes.append("No DOI or arXiv identifier.")
    if grade == "low":
        notes.append("Read the full text before using this study for a strong claim.")
    return EvidenceQuality(
        paper_id=paper.paper_id,
        rubric="abstract_extractability_v1",
        scores=scores,
        overall=overall,
        grade=grade,
        notes=notes,
    )
