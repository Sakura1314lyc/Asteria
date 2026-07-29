from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .artifacts import write_json
from .cs_taxonomy import CSTaxonomy
from .models import EvidenceCard, Paper, ResearchState


@dataclass(slots=True)
class ReproducibilityAssessment:
    paper_id: str
    rubric: str
    scores: dict[str, int]
    overall: float
    grade: str
    missing: list[str]
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_reproducibility(
    paper: Paper,
    card: EvidenceCard,
) -> ReproducibilityAssessment:
    cs = card.cs_evidence
    code_urls = [
        *paper.code_urls,
        *[str(value) for value in cs.get("code_urls", [])],
    ]
    dataset_urls = [
        *paper.dataset_urls,
        *[str(value) for value in cs.get("dataset_urls", [])],
    ]
    datasets = [str(value) for value in cs.get("datasets", [])]
    metrics = [str(value) for value in cs.get("metrics", [])]
    baselines = [str(value) for value in cs.get("baselines", [])]
    ablations = [str(value) for value in cs.get("ablations", [])]
    threats = [str(value) for value in cs.get("threats_to_validity", [])]
    compute = str(cs.get("compute", "")).casefold()
    implementation = str(cs.get("implementation_details", "")).casefold()
    unclear = {"", "unknown", "unclear", "未报告", "未抽取", "not reported"}

    scores = {
        "problem_and_task": _text_score(
            f"{cs.get('problem', '')} {' '.join(cs.get('tasks', []))}"
        ),
        "datasets": 2 if dataset_urls else (1 if datasets else 0),
        "baselines": 2 if len(baselines) >= 2 else (1 if baselines else 0),
        "metrics": 2 if len(metrics) >= 2 else (1 if metrics else 0),
        "implementation": 0
        if implementation.strip() in unclear
        else (2 if len(implementation) >= 100 else 1),
        "compute": 0
        if compute.strip() in unclear
        else (2 if re.search(r"\d|gpu|cpu|tpu|hour|day", compute) else 1),
        "ablations": 2 if len(ablations) >= 2 else (1 if ablations else 0),
        "code": 2 if code_urls else (1 if cs.get("code_availability") == "yes" else 0),
        "threats_to_validity": 2 if len(threats) >= 2 else (1 if threats else 0),
        "identifier": 2 if paper.doi or paper.arxiv_id else (1 if paper.url else 0),
    }
    overall = round(sum(scores.values()) / (2 * len(scores)), 3)
    grade = "high" if overall >= 0.8 else "moderate" if overall >= 0.5 else "low"
    missing = [name for name, value in scores.items() if value == 0]
    return ReproducibilityAssessment(
        paper_id=paper.paper_id,
        rubric="cs_reproducibility_v1",
        scores=scores,
        overall=overall,
        grade=grade,
        missing=missing,
        note=(
            "Automated score reflects what is stated in available metadata and "
            "abstract-level evidence. It does not prove that code runs or results "
            "reproduce."
        ),
    )


def analyze_cs_evidence(state: ResearchState) -> dict[str, Any]:
    taxonomy = CSTaxonomy.load()
    card_map = {card.paper_id: card for card in state.evidence}
    reproducibility = []
    domain_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    contribution_counter: Counter[str] = Counter()
    evidence_counter: Counter[str] = Counter()
    venue_counter: Counter[str] = Counter()
    dataset_counter: Counter[str] = Counter()
    metric_counter: Counter[str] = Counter()
    baseline_counter: Counter[str] = Counter()

    paper_domains: dict[str, list[dict[str, Any]]] = {}
    for paper in state.papers:
        domains = taxonomy.classify_paper(paper)
        paper_domains[paper.paper_id] = [item.to_dict() for item in domains]
        if domains:
            domain_counter[domains[0].domain_id] += 1
        category_counter.update(paper.categories)
        if paper.venue:
            venue_counter[paper.venue] += 1
        card = card_map.get(paper.paper_id)
        if not card:
            continue
        cs = card.cs_evidence
        contribution_counter[str(cs.get("contribution_type", "unclear"))] += 1
        evidence_counter[str(cs.get("evidence_level", "unclear"))] += 1
        dataset_counter.update(str(item) for item in cs.get("datasets", []) if item)
        metric_counter.update(str(item) for item in cs.get("metrics", []) if item)
        baseline_counter.update(str(item) for item in cs.get("baselines", []) if item)
        reproducibility.append(assess_reproducibility(paper, card).to_dict())

    average_reproducibility = (
        round(
            sum(item["overall"] for item in reproducibility) / len(reproducibility),
            3,
        )
        if reproducibility
        else 0.0
    )
    benchmark_catalog = {
        "datasets": _counter_records(dataset_counter),
        "metrics": _counter_records(metric_counter),
        "baselines": _counter_records(baseline_counter),
    }
    gaps = _research_gaps(state.papers, state.evidence, reproducibility)
    return {
        "taxonomy": {
            "version": taxonomy.version,
            "sources": taxonomy.sources,
        },
        "paper_domains": paper_domains,
        "landscape": {
            "domains": dict(domain_counter.most_common()),
            "arxiv_categories": dict(category_counter.most_common()),
            "contribution_types": dict(contribution_counter.most_common()),
            "evidence_levels": dict(evidence_counter.most_common()),
            "venues": dict(venue_counter.most_common()),
            "average_reproducibility": average_reproducibility,
        },
        "benchmark_catalog": benchmark_catalog,
        "reproducibility": reproducibility,
        "research_agenda": gaps,
    }


def write_cs_artifacts(run_dir: Path, state: ResearchState) -> dict[str, Any]:
    analysis = analyze_cs_evidence(state)
    write_json(run_dir / "cs_landscape.json", analysis["landscape"])
    write_json(run_dir / "benchmark_catalog.json", analysis["benchmark_catalog"])
    write_json(
        run_dir / "reproducibility.json",
        {
            "rubric": "cs_reproducibility_v1",
            "assessments": analysis["reproducibility"],
        },
    )
    write_json(run_dir / "research_agenda.json", analysis["research_agenda"])
    write_json(
        run_dir / "cs_classification.json",
        {
            "taxonomy": analysis["taxonomy"],
            "paper_domains": analysis["paper_domains"],
        },
    )
    _write_cs_matrix(run_dir / "cs_evidence_matrix.csv", state, analysis)
    return analysis


def _write_cs_matrix(
    path: Path,
    state: ResearchState,
    analysis: dict[str, Any],
) -> None:
    cards = {card.paper_id: card for card in state.evidence}
    repro = {item["paper_id"]: item for item in analysis["reproducibility"]}
    domains = analysis["paper_domains"]
    fields = [
        "paper_id",
        "title",
        "year",
        "venue",
        "cs_domains",
        "arxiv_categories",
        "contribution_type",
        "evidence_level",
        "problem",
        "core_contribution",
        "approach",
        "datasets",
        "tasks",
        "baselines",
        "metrics",
        "headline_results",
        "ablations",
        "compute",
        "implementation_details",
        "code_availability",
        "code_urls",
        "dataset_urls",
        "threats_to_validity",
        "security_ethics",
        "reproducibility_grade",
        "reproducibility_score",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for paper in state.papers:
            card = cards.get(paper.paper_id)
            cs = card.cs_evidence if card else {}
            assessment = repro.get(paper.paper_id, {})
            writer.writerow(
                {
                    "paper_id": paper.paper_id,
                    "title": paper.title,
                    "year": paper.year or "",
                    "venue": paper.venue,
                    "cs_domains": "; ".join(
                        item["name_en"] for item in domains.get(paper.paper_id, [])
                    ),
                    "arxiv_categories": "; ".join(paper.categories),
                    "contribution_type": cs.get("contribution_type", ""),
                    "evidence_level": cs.get("evidence_level", ""),
                    "problem": cs.get("problem", ""),
                    "core_contribution": cs.get("core_contribution", ""),
                    "approach": cs.get("approach", ""),
                    "datasets": _join(cs.get("datasets", [])),
                    "tasks": _join(cs.get("tasks", [])),
                    "baselines": _join(cs.get("baselines", [])),
                    "metrics": _join(cs.get("metrics", [])),
                    "headline_results": _join(cs.get("headline_results", [])),
                    "ablations": _join(cs.get("ablations", [])),
                    "compute": cs.get("compute", ""),
                    "implementation_details": cs.get("implementation_details", ""),
                    "code_availability": cs.get("code_availability", ""),
                    "code_urls": _join([*paper.code_urls, *cs.get("code_urls", [])]),
                    "dataset_urls": _join(
                        [*paper.dataset_urls, *cs.get("dataset_urls", [])]
                    ),
                    "threats_to_validity": _join(cs.get("threats_to_validity", [])),
                    "security_ethics": _join(cs.get("security_ethics", [])),
                    "reproducibility_grade": assessment.get("grade", ""),
                    "reproducibility_score": assessment.get("overall", ""),
                }
            )


def _research_gaps(
    papers: list[Paper],
    cards: list[EvidenceCard],
    reproducibility: list[dict[str, Any]],
) -> dict[str, Any]:
    total = max(len(cards), 1)
    card_gaps = {
        "missing_baselines": sum(
            not card.cs_evidence.get("baselines") for card in cards
        ),
        "missing_metrics": sum(not card.cs_evidence.get("metrics") for card in cards),
        "missing_ablations": sum(
            not card.cs_evidence.get("ablations") for card in cards
        ),
        "missing_compute": sum(
            str(card.cs_evidence.get("compute", "")).casefold()
            in {"", "未报告", "未抽取", "not reported", "unclear"}
            for card in cards
        ),
        "missing_code": sum(
            card.cs_evidence.get("code_availability") != "yes"
            and not card.cs_evidence.get("code_urls")
            for card in cards
        ),
        "missing_threats_to_validity": sum(
            not card.cs_evidence.get("threats_to_validity") for card in cards
        ),
    }
    priorities = []
    labels = {
        "missing_baselines": "建立一致、强度足够的基线比较",
        "missing_metrics": "统一任务定义与评价指标",
        "missing_ablations": "增加组件级消融与敏感性分析",
        "missing_compute": "报告硬件、时间、能耗与成本",
        "missing_code": "发布代码、配置、随机种子与环境锁定文件",
        "missing_threats_to_validity": "系统报告内部/外部/构念效度威胁",
    }
    for key, count in sorted(
        card_gaps.items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        rate = round(count / total, 3)
        if count:
            priorities.append(
                {
                    "gap": key,
                    "affected_papers": count,
                    "rate": rate,
                    "recommended_research": labels[key],
                }
            )
    low_repro = sum(item["grade"] == "low" for item in reproducibility)
    return {
        "paper_count": len(papers),
        "field_completeness_gaps": card_gaps,
        "low_reproducibility_count": low_repro,
        "priorities": priorities,
        "note": (
            "Agenda items are derived from missing or weakly reported evidence "
            "fields. They are candidate directions, not claims of novelty."
        ),
    }


def _text_score(value: str) -> int:
    normalized = value.strip().casefold()
    if normalized in {"", "unknown", "unclear", "未报告", "未抽取"}:
        return 0
    return 2 if len(normalized) >= 100 else 1


def _counter_records(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"name": name, "paper_count": count} for name, count in counter.most_common()
    ]


def _join(values: Any) -> str:
    return " | ".join(str(value) for value in values if value)
