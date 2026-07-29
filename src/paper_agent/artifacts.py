from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import Paper, ResearchState


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def checkpoint(run_dir: Path, state: ResearchState) -> None:
    write_json(run_dir / "state.json", state.to_dict())


def load_state(run_dir: Path) -> ResearchState:
    path = run_dir / "state.json"
    if not path.exists():
        raise FileNotFoundError(f"No checkpoint found at {path}")
    return ResearchState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def append_event(run_dir: Path, event: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _bib_escape(value: str) -> str:
    return (
        value.replace("\\", "\\textbackslash{}")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def bibtex(papers: list[Paper]) -> str:
    entries: list[str] = []
    for paper in papers:
        entry_type = "article" if paper.venue and paper.venue != "arXiv" else "misc"
        fields = {
            "title": _bib_escape(paper.title),
            "author": " and ".join(_bib_escape(author) for author in paper.authors),
            "year": str(paper.year or ""),
            "journal": _bib_escape(paper.venue) if entry_type == "article" else "",
            "doi": paper.doi,
            "url": paper.open_access_url or paper.url,
            "note": f"Evidence ID: {paper.paper_id}",
        }
        lines = [f"@{entry_type}{{{paper.paper_id},"]
        for key, value in fields.items():
            if value:
                lines.append(f"  {key} = {{{value}}},")
        lines.append("}")
        entries.append("\n".join(lines))
    return "\n\n".join(entries) + ("\n" if entries else "")


def citation_audit(report: str, papers: list[Paper]) -> dict[str, Any]:
    known = {paper.paper_id for paper in papers}
    cited = set(re.findall(r"\[(P\d{3})\]", report))
    unknown = sorted(cited - known)
    uncited_sources = sorted(known - cited)
    claim_paragraphs = 0
    supported_paragraphs = 0
    unsupported_samples: list[str] = []
    for raw in re.split(r"\n\s*\n", report):
        paragraph = " ".join(line.strip() for line in raw.splitlines()).strip()
        if len(paragraph) < 80 or paragraph.startswith(("#", "- [P", "|")):
            continue
        claim_paragraphs += 1
        if re.search(r"\[P\d{3}\]", paragraph):
            supported_paragraphs += 1
        elif len(unsupported_samples) < 5:
            unsupported_samples.append(paragraph[:240])
    coverage = (
        round(supported_paragraphs / claim_paragraphs, 3) if claim_paragraphs else 1.0
    )
    grounding = citation_grounding_audit(report, papers)
    return {
        "known_source_count": len(known),
        "cited_source_count": len(cited & known),
        "unknown_citations": unknown,
        "uncited_sources": uncited_sources,
        "claim_paragraphs": claim_paragraphs,
        "supported_claim_paragraphs": supported_paragraphs,
        "paragraph_citation_coverage": coverage,
        "unsupported_paragraph_samples": unsupported_samples,
        "passed": not unknown and coverage >= 0.8 and bool(cited & known),
        "grounding_proxy": grounding,
        "note": (
            "This is a structural citation audit. It does not prove that a cited "
            "paper semantically supports each claim."
        ),
    }


def citation_grounding_audit(
    report: str,
    papers: list[Paper],
) -> dict[str, Any]:
    """Estimate lexical claim-source alignment without claiming factual entailment."""
    paper_map = {paper.paper_id: paper for paper in papers}
    checks: list[dict[str, Any]] = []
    for raw in re.split(r"\n\s*\n", report):
        paragraph = " ".join(line.strip() for line in raw.splitlines()).strip()
        citation_ids = re.findall(r"\[(P\d{3})\]", paragraph)
        if len(paragraph) < 50 or not citation_ids:
            continue
        claim = re.sub(r"\[P\d{3}\]", "", paragraph).strip()
        claim_tokens = _lexical_units(claim)
        for paper_id in dict.fromkeys(citation_ids):
            paper = paper_map.get(paper_id)
            if not paper:
                continue
            source = f"{paper.title} {paper.abstract}".strip()
            if not paper.abstract:
                status = "metadata_only"
                overlap = None
            elif _dominant_script(claim) != _dominant_script(source):
                status = "cross_language_unverified"
                overlap = None
            else:
                source_tokens = _lexical_units(source)
                overlap = round(
                    len(claim_tokens & source_tokens) / max(1, len(claim_tokens)),
                    3,
                )
                status = "aligned_proxy" if overlap >= 0.08 else "weak_proxy"
            checks.append(
                {
                    "paper_id": paper_id,
                    "claim_excerpt": claim[:280],
                    "source_title": paper.title,
                    "lexical_overlap": overlap,
                    "status": status,
                }
            )
    assessable = [item for item in checks if item["lexical_overlap"] is not None]
    aligned = [item for item in assessable if item["status"] == "aligned_proxy"]
    assessment_coverage = (
        round(len(assessable) / len(checks), 3) if checks else None
    )
    effective_alignment_rate = (
        round(len(aligned) / len(checks), 3) if checks else None
    )
    return {
        "method": "lexical_claim_source_proxy_v1",
        "check_count": len(checks),
        "assessable_count": len(assessable),
        "aligned_proxy_count": len(aligned),
        "alignment_rate": (
            round(len(aligned) / len(assessable), 3) if assessable else None
        ),
        "assessment_coverage": assessment_coverage,
        "effective_alignment_rate": effective_alignment_rate,
        "checks": checks,
        "note": (
            "This deterministic lexical proxy can flag citations for review. "
            "It is not semantic entailment, factual verification, or a substitute "
            "for reading the cited source. Alignment rate only covers assessable "
            "claims; assessment coverage reports how much of the audit was actually "
            "scored. Cross-language claims are left unscored."
        ),
    }


def _dominant_script(text: str) -> str:
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return "cjk" if cjk > latin else "latin"


def _lexical_units(text: str) -> set[str]:
    stopwords = {
        "about",
        "after",
        "also",
        "and",
        "are",
        "been",
        "being",
        "from",
        "have",
        "into",
        "more",
        "paper",
        "research",
        "that",
        "the",
        "their",
        "this",
        "using",
        "were",
        "with",
    }
    latin = {
        token
        for token in re.findall(r"[a-z][a-z0-9_-]{2,}", text.casefold())
        if token not in stopwords
    }
    cjk_runs = re.findall(r"[\u3400-\u9fff]{2,}", text)
    cjk = {run[index : index + 2] for run in cjk_runs for index in range(len(run) - 1)}
    return latin | cjk


def write_final_artifacts(run_dir: Path, state: ResearchState) -> None:
    (run_dir / "report.md").write_text(state.report, encoding="utf-8")
    (run_dir / "references.bib").write_text(bibtex(state.papers), encoding="utf-8")
    write_json(
        run_dir / "evidence.json",
        {
            "research_question": state.question,
            "evidence": [card.to_dict() for card in state.evidence],
        },
    )
    write_json(run_dir / "audit.json", state.audit)
    write_json(
        run_dir / "citation_grounding.json",
        state.audit.get("grounding_proxy", {}),
    )
