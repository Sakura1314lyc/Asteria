from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .artifacts import write_json
from .models import ResearchState


def prisma_summary(state: ResearchState) -> dict[str, Any]:
    title_decisions = [
        item
        for item in state.screening
        if str(item.get("stage", "title_abstract")) == "title_abstract"
    ]
    fulltext_decisions = [
        item for item in state.screening if str(item.get("stage", "")) == "full_text"
    ]
    counts = {"included": 0, "excluded": 0, "maybe": 0, "pending": 0}
    reasons: dict[str, int] = {}
    for item in title_decisions:
        status = str(item.get("status", "pending"))
        counts[status] = counts.get(status, 0) + 1
        for reason in item.get("reasons", []):
            normalized = str(reason).strip()
            if normalized:
                reasons[normalized] = reasons.get(normalized, 0) + 1
    identified = len(title_decisions) or len(state.papers)
    title_candidates = counts.get("included", 0) + counts.get("maybe", 0)
    included = title_candidates
    fulltext_reasons: dict[str, int] = {}
    if fulltext_decisions:
        included = sum(
            str(item.get("status")) == "included" for item in fulltext_decisions
        )
        for item in fulltext_decisions:
            if str(item.get("status")) != "excluded":
                continue
            code = str(item.get("exclusion_code") or "other")
            fulltext_reasons[code] = fulltext_reasons.get(code, 0) + 1
    if not title_decisions:
        included = len(state.papers)
    return {
        "identified_records": identified,
        "deduplicated_records": identified,
        "screened_records": identified,
        "excluded_records": counts.get("excluded", 0),
        "pending_records": counts.get("pending", 0),
        "included_in_synthesis": included,
        "exclusion_reasons": reasons,
        "reports_sought_for_retrieval": title_candidates,
        "reports_not_retrieved": sum(
            str(item.get("retrieval_status")) == "not_retrieved"
            for item in fulltext_decisions
        ),
        "reports_assessed_for_eligibility": sum(
            str(item.get("retrieval_status")) == "retrieved"
            for item in fulltext_decisions
        ),
        "reports_excluded_after_fulltext": sum(
            str(item.get("status")) == "excluded" for item in fulltext_decisions
        ),
        "fulltext_exclusion_reasons": fulltext_reasons,
        "note": (
            "PRISMA 2020-style operational counts generated from this run. "
            "They are not a claim of PRISMA compliance."
        ),
    }


def write_review_artifacts(run_dir: Path, state: ResearchState) -> None:
    write_json(run_dir / "review_flow.json", prisma_summary(state))
    cards = {card.paper_id: card for card in state.evidence}
    quality = {str(item.get("paper_id")): item for item in state.quality}
    with (run_dir / "study_matrix.csv").open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "paper_id",
                "title",
                "authors",
                "year",
                "venue",
                "doi",
                "objective",
                "methods",
                "data_or_sample",
                "findings",
                "limitations",
                "evidence_confidence",
                "extractability_grade",
                "extractability_score",
            ],
        )
        writer.writeheader()
        for paper in state.papers:
            card = cards.get(paper.paper_id)
            appraisal = quality.get(paper.paper_id, {})
            writer.writerow(
                {
                    "paper_id": paper.paper_id,
                    "title": paper.title,
                    "authors": "; ".join(paper.authors),
                    "year": paper.year or "",
                    "venue": paper.venue,
                    "doi": paper.doi,
                    "objective": card.objective if card else "",
                    "methods": card.methods if card else "",
                    "data_or_sample": card.data_or_sample if card else "",
                    "findings": " | ".join(card.findings) if card else "",
                    "limitations": " | ".join(card.limitations) if card else "",
                    "evidence_confidence": card.confidence if card else "",
                    "extractability_grade": appraisal.get("grade", ""),
                    "extractability_score": appraisal.get("overall", ""),
                }
            )
