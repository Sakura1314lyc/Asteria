from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .artifacts import write_json
from .models import ResearchState


def prisma_summary(state: ResearchState) -> dict[str, Any]:
    decisions = state.screening
    counts = {"included": 0, "excluded": 0, "maybe": 0, "pending": 0}
    reasons: dict[str, int] = {}
    for item in decisions:
        status = str(item.get("status", "pending"))
        counts[status] = counts.get(status, 0) + 1
        for reason in item.get("reasons", []):
            normalized = str(reason).strip()
            if normalized:
                reasons[normalized] = reasons.get(normalized, 0) + 1
    identified = len(decisions) or len(state.papers)
    included = counts.get("included", 0) + counts.get("maybe", 0)
    if not decisions:
        included = len(state.papers)
    return {
        "identified_records": identified,
        "deduplicated_records": identified,
        "screened_records": identified,
        "excluded_records": counts.get("excluded", 0),
        "pending_records": counts.get("pending", 0),
        "included_in_synthesis": included,
        "exclusion_reasons": reasons,
        "note": (
            "PRISMA-style operational counts generated from this run. "
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
