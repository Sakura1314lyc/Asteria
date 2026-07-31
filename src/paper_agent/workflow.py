from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .agent_profiles import AgentProfile, get_agent_profile
from .artifacts import (
    append_event,
    checkpoint,
    citation_audit,
    load_state,
    write_final_artifacts,
    write_json,
)
from .config import Settings
from .cs_evidence import write_cs_artifacts
from .cs_profiles import protocols_for_domains
from .cs_taxonomy import CSTaxonomy
from .domain import ReviewProtocol
from .graph import build_literature_graph, write_graph_artifacts
from .llm import LanguageModel
from .models import EvidenceCard, ResearchState
from .prompts import (
    EVIDENCE_SCHEMA,
    PLAN_SCHEMA,
    evidence_prompt,
    plan_prompt,
    report_prompt,
)
from .quality import assess_evidence_quality
from .retrievers import (
    ArxivRetriever,
    DblpRetriever,
    OpenAlexRetriever,
    Retriever,
    SemanticScholarRetriever,
    rank_papers,
    search_all,
)
from .review_artifacts import write_review_artifacts
from .screening import ScreeningEngine


class WorkflowError(RuntimeError):
    pass


ProgressCallback = Callable[[str, str], None]

STAGE_ORDER = {
    "initialized": 0,
    "planned": 1,
    "searched": 2,
    "screened": 3,
    "extracted": 4,
    "assessed": 5,
    "written": 6,
    "completed": 7,
}


class ResearchAgent:
    def __init__(
        self,
        *,
        settings: Settings,
        llm: LanguageModel,
        retrievers: list[Retriever] | None = None,
        progress: ProgressCallback | None = None,
        protocol: ReviewProtocol | None = None,
        agent_profile: AgentProfile | None = None,
    ):
        self.settings = settings
        self.llm = llm
        self.retrievers = retrievers or self._default_retrievers()
        self.progress = progress
        self.protocol = protocol
        self.agent_profile = agent_profile or get_agent_profile("deep_review")

    def _agent_instructions(self, instructions: str) -> str:
        return (
            f"{instructions}\n\nSelected research agent: {self.agent_profile.name}\n"
            f"Agent specialization: {self.agent_profile.instructions}"
        )

    def _default_retrievers(self) -> list[Retriever]:
        retrievers: list[Retriever] = [
            OpenAlexRetriever(self.settings),
            ArxivRetriever(self.settings),
        ]
        if self.settings.dblp_enabled:
            retrievers.append(DblpRetriever(self.settings))
        if os.getenv("S2_API_KEY"):
            retrievers.append(SemanticScholarRetriever(self.settings))
        return retrievers

    def _emit(
        self,
        run_dir: Path,
        stage: str,
        message: str,
        *,
        state: ResearchState | None = None,
    ) -> None:
        event = {
            "time": datetime.now(UTC).isoformat(),
            "stage": stage,
            "message": message,
        }
        append_event(run_dir, event)
        if state is not None:
            state.touch()
            checkpoint(run_dir, state)
        if self.progress:
            self.progress(stage, message)

    def run(
        self,
        topic: str,
        question: str = "",
        *,
        stop_after: str = "completed",
    ) -> Path:
        topic = topic.strip()
        question = question.strip() or topic
        if not topic:
            raise ValueError("topic must not be empty")
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        digest = hashlib.sha1(topic.encode("utf-8")).hexdigest()[:8]
        run_dir = self.settings.output_root.resolve() / f"{timestamp}-{digest}"
        run_dir.mkdir(parents=True, exist_ok=False)
        state = ResearchState(
            run_id=run_dir.name,
            topic=topic,
            question=question,
            language=self.settings.language,
            settings=self.settings.to_dict(),
        )
        checkpoint(run_dir, state)
        self._emit(run_dir, "initialized", "研究任务已创建。", state=state)
        return self._advance(run_dir, state, stop_after=stop_after)

    def resume(
        self,
        run_dir: Path | str,
        *,
        stop_after: str = "completed",
    ) -> Path:
        path = Path(run_dir).resolve()
        state = load_state(path)
        self._emit(
            path,
            state.stage,
            f"从阶段 {state.stage} 恢复任务。",
            state=state,
        )
        return self._advance(path, state, stop_after=stop_after)

    def _advance(
        self,
        run_dir: Path,
        state: ResearchState,
        *,
        stop_after: str = "completed",
    ) -> Path:
        if state.stage not in STAGE_ORDER:
            raise WorkflowError(f"Unknown checkpoint stage: {state.stage}")
        if stop_after not in STAGE_ORDER:
            raise ValueError(
                f"Unknown stop stage {stop_after!r}; choose from "
                f"{', '.join(STAGE_ORDER)}"
            )
        if STAGE_ORDER[state.stage] < STAGE_ORDER["planned"]:
            self._plan(run_dir, state)
            if stop_after == "planned":
                return run_dir
        if STAGE_ORDER[state.stage] < STAGE_ORDER["searched"]:
            self._search(run_dir, state)
            if stop_after == "searched":
                return run_dir
        if STAGE_ORDER[state.stage] < STAGE_ORDER["screened"]:
            self._screen(run_dir, state)
            if stop_after == "screened":
                return run_dir
        if STAGE_ORDER[state.stage] < STAGE_ORDER["extracted"]:
            self._extract(run_dir, state)
            if stop_after == "extracted":
                return run_dir
        if STAGE_ORDER[state.stage] < STAGE_ORDER["assessed"]:
            self._assess(run_dir, state)
            if stop_after == "assessed":
                return run_dir
        if STAGE_ORDER[state.stage] < STAGE_ORDER["written"]:
            self._write(run_dir, state)
            if stop_after == "written":
                return run_dir
        if STAGE_ORDER[state.stage] < STAGE_ORDER["completed"]:
            self._audit(run_dir, state)
        return run_dir

    def _plan(self, run_dir: Path, state: ResearchState) -> None:
        input_question = state.question.strip()
        self._emit(run_dir, "planning", "正在生成多视角检索计划。")
        taxonomy = CSTaxonomy.load()
        initial_domains = taxonomy.classify_text(
            f"{state.topic}\n{state.question}",
            limit=3,
        )
        instructions, user = plan_prompt(
            state.topic,
            state.question,
            state.language,
            ", ".join(
                f"{item.name_en} ({'/'.join(item.arxiv_categories)})"
                for item in initial_domains
            ),
        )
        state.plan = self.llm.json(
            name="research_plan",
            schema=PLAN_SCHEMA,
            instructions=self._agent_instructions(instructions),
            user_input=user,
        )
        query_items = [
            {
                "query": str(item.get("query", "")),
                "purpose": str(item.get("purpose", "")),
            }
            for item in state.plan.get("queries", [])
            if isinstance(item, dict) and item.get("query")
        ]
        expanded_queries, domains = taxonomy.expand_queries(
            state.topic,
            query_items,
            max_queries=max(self.settings.max_queries, 5),
        )
        state.plan["queries"] = expanded_queries
        state.plan["computer_science"] = {
            "taxonomy_version": taxonomy.version,
            "sources": taxonomy.sources,
            "domains": [item.to_dict() for item in domains],
            "evidence_protocols": protocols_for_domains(domains),
        }
        refined_question = str(
            state.plan.get("refined_question") or input_question
        ).strip()
        state.plan["input_question"] = input_question
        state.plan["refined_question"] = refined_question
        if input_question.casefold() == state.topic.strip().casefold():
            state.question = refined_question or input_question
            state.plan["question_policy"] = "topic_refined"
        else:
            state.question = input_question
            state.plan["question_policy"] = "explicit_preserved"
        state.touch("planned")
        write_json(run_dir / "plan.json", state.plan)
        self._emit(
            run_dir,
            "planned",
            f"计划完成，共 {len(state.plan.get('queries', []))} 个检索式。",
            state=state,
        )

    def _screen(self, run_dir: Path, state: ResearchState) -> None:
        self._emit(run_dir, "screening", "正在生成透明的纳排建议。")
        protocol_data = state.settings.get("protocol")
        protocol = self.protocol or ReviewProtocol.from_dict(
            protocol_data if isinstance(protocol_data, dict) else None
        )
        suggestions = ScreeningEngine().suggest_many(state.papers, protocol)
        state.screening = [suggestion.to_dict() for suggestion in suggestions]
        included_ids = {
            suggestion.paper_id
            for suggestion in suggestions
            if suggestion.status != "excluded"
        }
        state.papers = [
            paper for paper in state.papers if paper.paper_id in included_ids
        ]
        if not state.papers:
            raise WorkflowError("All retrieved papers were excluded by screening rules")
        state.touch("screened")
        write_json(
            run_dir / "screening.json",
            {
                "mode": "automatic_suggestion",
                "requires_human_review": True,
                "decisions": state.screening,
            },
        )
        self._emit(
            run_dir,
            "screened",
            f"自动建议后保留 {len(state.papers)} 篇；正式综述仍需人工确认。",
            state=state,
        )

    def _search(self, run_dir: Path, state: ResearchState) -> None:
        query_items = state.plan.get("queries") or []
        queries = [
            str(item.get("query", "")).strip()
            for item in query_items
            if isinstance(item, dict) and item.get("query")
        ][: self.settings.max_queries]
        if not queries:
            queries = [state.topic]
        self._emit(
            run_dir,
            "searching",
            f"正在并行执行 {len(queries)} 个检索式。",
        )
        raw_papers, warnings, executions = search_all(
            self.retrievers,
            queries,
            self.settings,
        )
        state.warnings.extend(warnings)
        records_returned = sum(item.result_count for item in executions)
        protocol_data = (
            self.protocol.to_dict()
            if self.protocol is not None
            else state.settings.get("protocol", {})
        )
        if not isinstance(protocol_data, dict):
            protocol_data = {}
        state.search_log = {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "topic": state.topic,
            "question": state.question,
            "configured_restrictions": {
                "year_from": protocol_data.get("year_from"),
                "year_to": protocol_data.get("year_to"),
                "languages": protocol_data.get("languages", []),
                "study_types": protocol_data.get("study_types", []),
                "max_queries": self.settings.max_queries,
                "results_per_query": self.settings.results_per_query,
                "max_papers_after_ranking": self.settings.max_papers,
            },
            "summary": {
                "planned_executions": len(executions),
                "succeeded": sum(
                    item.status == "succeeded" for item in executions
                ),
                "failed": sum(item.status == "failed" for item in executions),
                "records_returned_before_deduplication": records_returned,
                "unique_records_after_deduplication": len(raw_papers),
                "duplicates_removed": max(0, records_returned - len(raw_papers)),
                "records_selected_after_ranking": 0,
            },
            "executions": [item.to_dict() for item in executions],
            "warnings": warnings,
            "reporting_note": (
                "Execution-level audit trail. Configured restrictions are review "
                "protocol settings and may be applied after source retrieval."
            ),
        }
        write_json(run_dir / "search_log.json", state.search_log)
        if not raw_papers:
            details = "\n".join(warnings[-5:])
            raise WorkflowError(f"No papers were retrieved.\n{details}")
        state.papers = rank_papers(
            raw_papers,
            " ".join([state.topic, state.question, *queries]),
            self.settings.max_papers,
        )
        state.search_log["summary"]["records_selected_after_ranking"] = len(
            state.papers
        )
        write_json(run_dir / "search_log.json", state.search_log)
        state.touch("searched")
        write_json(
            run_dir / "search_results.json",
            {
                "queries": queries,
                "papers": [paper.to_dict() for paper in state.papers],
                "warnings": warnings,
            },
        )
        self._emit(
            run_dir,
            "searched",
            f"检索去重并排序后保留 {len(state.papers)} 篇论文。",
            state=state,
        )

    def _assess(self, run_dir: Path, state: ResearchState) -> None:
        self._emit(run_dir, "assessing", "正在执行摘要级证据可提取性评价。")
        card_map = {card.paper_id: card for card in state.evidence}
        quality = []
        for paper in state.papers:
            card = card_map.get(paper.paper_id)
            if card is None:
                continue
            quality.append(assess_evidence_quality(paper, card).to_dict())
        state.quality = quality
        state.touch("assessed")
        write_json(
            run_dir / "quality.json",
            {
                "rubric": "abstract_extractability_v1",
                "formal_risk_of_bias": False,
                "assessments": quality,
            },
        )
        graph = build_literature_graph(state.papers)
        write_graph_artifacts(
            graph,
            run_dir / "literature_graph.json",
            run_dir / "literature_graph.graphml",
        )
        state.cs_analysis = write_cs_artifacts(run_dir, state)
        self._emit(
            run_dir,
            "assessed",
            f"已评价 {len(quality)} 篇论文并生成文献关系图。",
            state=state,
        )

    def _extract(self, run_dir: Path, state: ResearchState) -> None:
        self._emit(run_dir, "extracting", "正在从题录与摘要构建证据卡。")
        instructions, user = evidence_prompt(
            state.question,
            state.papers,
            state.language,
        )
        payload = self.llm.json(
            name="evidence_cards",
            schema=EVIDENCE_SCHEMA,
            instructions=self._agent_instructions(instructions),
            user_input=user,
        )
        known_ids = {paper.paper_id for paper in state.papers}
        cards: list[EvidenceCard] = []
        seen: set[str] = set()
        for item in payload.get("cards", []):
            if not isinstance(item, dict):
                continue
            card = EvidenceCard.from_dict(item)
            if card.paper_id in known_ids and card.paper_id not in seen:
                cards.append(card)
                seen.add(card.paper_id)
        for paper in state.papers:
            if paper.paper_id not in seen:
                cards.append(
                    EvidenceCard(
                        paper_id=paper.paper_id,
                        relevance="模型未返回该记录的证据卡。",
                        objective="未抽取",
                        methods="未抽取",
                        data_or_sample="未抽取",
                        findings=[],
                        limitations=["需要人工阅读原文并补充。"],
                        confidence="low",
                        cs_evidence={
                            "contribution_type": "unclear",
                            "problem": "未抽取",
                            "core_contribution": "未抽取",
                            "approach": "未抽取",
                            "datasets": [],
                            "tasks": [],
                            "baselines": [],
                            "metrics": [],
                            "headline_results": [],
                            "ablations": [],
                            "compute": "未抽取",
                            "implementation_details": "未抽取",
                            "code_availability": "unclear",
                            "code_urls": [],
                            "dataset_urls": [],
                            "threats_to_validity": ["需要人工全文复核"],
                            "security_ethics": [],
                            "evidence_level": "unclear",
                        },
                    )
                )
        state.evidence = cards
        state.touch("extracted")
        write_json(
            run_dir / "evidence.json",
            {"evidence": [card.to_dict() for card in cards]},
        )
        self._emit(
            run_dir,
            "extracted",
            f"已生成 {len(cards)} 张证据卡。",
            state=state,
        )

    def _write(self, run_dir: Path, state: ResearchState) -> None:
        self._emit(run_dir, "writing", "正在基于证据卡撰写引用型研究简报。")
        instructions, user = report_prompt(
            state.topic,
            state.question,
            state.plan,
            state.papers,
            state.evidence,
            state.language,
            state.quality,
            state.cs_analysis,
        )
        state.report = self.llm.text(
            instructions=self._agent_instructions(instructions),
            user_input=user,
        )
        if not state.report:
            raise WorkflowError("Model returned an empty report")
        state.touch("written")
        (run_dir / "report.md").write_text(state.report, encoding="utf-8")
        self._emit(run_dir, "written", "研究简报已生成。", state=state)

    def _audit(self, run_dir: Path, state: ResearchState) -> None:
        self._emit(run_dir, "auditing", "正在执行引用完整性审计。")
        state.audit = citation_audit(state.report, state.papers)
        if not state.audit["passed"]:
            state.warnings.append(
                "引用结构审计未完全通过，请检查 audit.json 并人工复核。"
            )
        state.touch("completed")
        write_final_artifacts(run_dir, state)
        write_review_artifacts(run_dir, state)
        self._emit(
            run_dir,
            "completed",
            (
                "任务完成；段落引用覆盖率 "
                f"{state.audit['paragraph_citation_coverage']:.0%}。"
            ),
            state=state,
        )
