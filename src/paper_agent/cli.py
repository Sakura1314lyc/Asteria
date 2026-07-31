from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .artifacts import load_state
from .config import Settings
from .database import DatabaseError
from .llm import DemoLLM, LLMError, OpenAIResponsesLLM
from .retrievers import FixtureRetriever
from .workbench import ResearchWorkbench, WorkbenchError
from .workflow import ResearchAgent, WorkflowError


def _progress(stage: str, message: str) -> None:
    print(f"[{stage:>10}] {message}", flush=True)


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _percent(value: object) -> str:
    if value is None:
        return "—"
    return f"{round(float(value) * 100)}%"


def _print_projects(values: list[dict[str, object]]) -> None:
    if not values:
        print("还没有研究项目。")
        return
    for value in values:
        stats = value.get("stats") or {}
        print(f"{value['name']}  [{value['id']}]")
        print(
            f"  {value.get('review_type', 'narrative')} · {value.get('language', '—')}"
        )
        print(f"  问题：{value.get('research_question') or value.get('topic')}")
        if isinstance(stats, dict):
            print(
                "  论文："
                f"{stats.get('total', 0)} "
                f"· 纳入 {stats.get('included', 0)} "
                f"· 待筛 {stats.get('pending', 0)}"
            )


def _print_project(value: dict[str, object]) -> None:
    print(f"{value['name']}  [{value['id']}]")
    print(f"主题：{value.get('topic', '—')}")
    print(f"问题：{value.get('research_question') or value.get('topic', '—')}")
    print(
        f"类型：{value.get('review_type', 'narrative')} · {value.get('language', '—')}"
    )
    stats = value.get("stats") or {}
    if isinstance(stats, dict):
        print(
            "论文："
            f"{stats.get('total', 0)} "
            f"· 纳入 {stats.get('included', 0)} "
            f"· 排除 {stats.get('excluded', 0)} "
            f"· 待筛 {stats.get('pending', 0)}"
        )
    print(
        f"运行：{len(value.get('runs') or [])} "
        f"· 报告：{len(value.get('reports') or [])}"
    )


def _print_screening(values: list[dict[str, object]]) -> None:
    if not values:
        print("没有符合条件的论文。")
        return
    for value in values:
        paper = value.get("paper") or {}
        if not isinstance(paper, dict):
            continue
        evidence_id = value.get("evidence_id") or paper.get("paper_id") or "—"
        year = paper.get("year") or "—"
        status = value.get("screening_status") or "pending"
        database_id = str(value.get("paper_id") or value.get("id") or "—")
        print(f"{database_id:>3}  {evidence_id}  {status}  {year}")
        print(f"     {paper.get('title', 'Untitled')}")
        authors = paper.get("authors") or []
        if authors:
            print(f"     {', '.join(str(author) for author in authors[:4])}")
        reason = value.get("screening_reason")
        if reason:
            print(f"     理由：{reason}")


def _print_document_hits(values: list[dict[str, object]]) -> None:
    if not values:
        print("没有找到全文片段。")
        return
    for index, value in enumerate(values, start=1):
        content = " ".join(str(value.get("content", "")).split())
        excerpt = content[:180] + ("…" if len(content) > 180 else "")
        print(
            f"{index}. {value.get('filename', 'document')} · p.{value.get('page', '—')}"
        )
        print(f"   {excerpt}")


def _print_bibliography_import(value: dict[str, object]) -> None:
    print(
        f"已读取 {value.get('filename', 'bibliography')} "
        f"· {value.get('format', 'unknown')}"
    )
    print(
        f"新增 {value.get('added', 0)} "
        f"· 已存在 {value.get('already_present', 0)} "
        f"· 补全元数据 {value.get('enriched', 0)} "
        f"· 文件内重复 {value.get('duplicates_in_file', 0)} "
        f"· 跳过 {value.get('skipped', 0)}"
    )
    evidence_ids = value.get("evidence_ids") or []
    if evidence_ids:
        print(f"证据 ID：{', '.join(str(item) for item in evidence_ids)}")
    warnings = value.get("warnings") or []
    if warnings:
        print(f"警告：{len(warnings)} 条（使用 --json 查看详情）")


def _print_run_summary(value: dict[str, object]) -> None:
    audit = value.get("audit") or {}
    if not isinstance(audit, dict):
        audit = {}
    grounding = audit.get("grounding_proxy") or {}
    if not isinstance(grounding, dict):
        grounding = {}
    check_count = int(grounding.get("check_count", 0))
    assessable_count = int(grounding.get("assessable_count", 0))
    aligned_count = int(grounding.get("aligned_proxy_count", 0))
    assessment_coverage = grounding.get("assessment_coverage")
    effective_alignment = grounding.get("effective_alignment_rate")
    if assessment_coverage is None and check_count:
        assessment_coverage = assessable_count / check_count
    if effective_alignment is None and check_count:
        effective_alignment = aligned_count / check_count
    print(f"运行：{value.get('run_id', '—')} · {value.get('stage', '—')}")
    print(f"主题：{value.get('topic', '—')}")
    print(f"问题：{value.get('question', '—')}")
    print(
        f"论文：{value.get('papers', 0)} "
        f"· 证据卡：{value.get('evidence_cards', 0)} "
        f"· 引用段落覆盖：{_percent(audit.get('paragraph_citation_coverage'))}"
    )
    print(
        "引用可评估："
        f"{_percent(assessment_coverage)} "
        f"· 有效词汇对齐：{_percent(effective_alignment)}"
    )
    search_summary = value.get("search_summary") or {}
    if isinstance(search_summary, dict) and search_summary:
        print(
            "检索账本："
            f"{search_summary.get('succeeded', 0)}/"
            f"{search_summary.get('planned_executions', 0)} 次成功 "
            f"· 去重前 {search_summary.get('records_returned_before_deduplication', 0)} "
            f"· 去重后 {search_summary.get('unique_records_after_deduplication', 0)}"
        )
    warnings = value.get("warnings") or []
    if warnings:
        print(f"警告：{len(warnings)} 条（使用 --json 查看详情）")


def _print_evaluation(value: dict[str, object]) -> None:
    print(f"评测：{value.get('run_id', '—')} · 总分 {_percent(value.get('overall'))}")
    metrics = (
        ("引用结构", "citation_structure"),
        ("有效引用对齐", "citation_grounding_proxy"),
        ("引用可评估", "citation_grounding_assessability"),
        ("证据完整", "evidence_completeness"),
        ("标识符覆盖", "identifier_coverage"),
        ("章节覆盖", "section_coverage"),
        ("CS 证据完整", "cs_evidence_completeness"),
        ("复现报告", "reproducibility_reporting"),
    )
    for label, key in metrics:
        print(f"  {label:<8} {_percent(value.get(key))}")
    failures = value.get("failures") or []
    if failures:
        print("待改进：")
        for failure in failures:
            print(f"  - {failure}")


def _print_cs_analysis(value: dict[str, object]) -> None:
    paper_domains = value.get("paper_domains") or {}
    landscape = value.get("landscape") or {}
    benchmarks = value.get("benchmarks") or []
    reproducibility = value.get("reproducibility") or []
    print("计算机领域证据分析")
    print(
        f"  已分类论文：{len(paper_domains) if isinstance(paper_domains, dict) else 0}"
        f" · benchmark 记录：{len(benchmarks) if isinstance(benchmarks, list) else 0}"
    )
    if isinstance(landscape, dict):
        domains = landscape.get("domains") or landscape.get("domain_counts") or []
        print(f"  研究版图条目：{len(domains) if hasattr(domains, '__len__') else 0}")
    if isinstance(reproducibility, list) and reproducibility:
        scores = [
            float(item.get("overall", 0))
            for item in reproducibility
            if isinstance(item, dict)
        ]
        print(
            f"  复现报告：{len(reproducibility)} "
            f"· 平均 {_percent(sum(scores) / len(scores) if scores else 0)}"
        )
    print("  使用 --json 查看逐论文协议、基准和复现字段。")


def _settings(args: argparse.Namespace) -> Settings:
    settings = Settings.from_env()
    if getattr(args, "language", None):
        settings.language = args.language
    if getattr(args, "max_papers", None):
        settings.max_papers = args.max_papers
    if getattr(args, "output_dir", None):
        settings.output_root = Path(args.output_dir)
    if getattr(args, "model", None):
        settings.model = args.model
    return settings


def _agent(args: argparse.Namespace, topic: str) -> ResearchAgent:
    settings = _settings(args)
    llm = DemoLLM(topic) if args.demo else OpenAIResponsesLLM(settings)
    retrievers = [FixtureRetriever(args.fixture)] if args.fixture else None
    return ResearchAgent(
        settings=settings,
        llm=llm,
        retrievers=retrievers,
        progress=_progress,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper-agent",
        description="证据优先、可恢复的论文科研 Agent",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="启动新的研究任务")
    run.add_argument("topic", help="研究主题")
    run.add_argument("--question", default="", help="更具体的研究问题")
    run.add_argument("--language", default=None, help="报告语言，如 zh-CN / en")
    run.add_argument("--max-papers", type=int, default=None, help="最多保留论文数")
    run.add_argument("--output-dir", default=None, help="运行产物根目录")
    run.add_argument("--model", default=None, help="覆盖模型 ID")
    run.add_argument("--demo", action="store_true", help="使用离线演示模型")
    run.add_argument("--fixture", type=Path, help="从本地 JSON 读取演示论文")

    resume = subparsers.add_parser("resume", help="从 state.json 恢复任务")
    resume.add_argument("run_dir", type=Path, help="已有运行目录")
    resume.add_argument("--model", default=None, help="覆盖模型 ID")
    resume.add_argument("--demo", action="store_true", help="使用离线演示模型")
    resume.add_argument("--fixture", type=Path, help="从本地 JSON 读取论文")
    resume.add_argument("--language", default=None, help=argparse.SUPPRESS)
    resume.add_argument("--max-papers", type=int, default=None, help=argparse.SUPPRESS)
    resume.add_argument("--output-dir", default=None, help=argparse.SUPPRESS)

    inspect = subparsers.add_parser("inspect", help="查看任务状态")
    inspect.add_argument("run_dir", type=Path)
    inspect.add_argument("--json", action="store_true", help="输出完整 JSON")

    project = subparsers.add_parser("project", help="管理长期科研项目")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    project_create = project_commands.add_parser("create", help="创建项目")
    project_create.add_argument("name")
    project_create.add_argument("--topic", required=True)
    project_create.add_argument("--question", default="")
    project_create.add_argument(
        "--type",
        choices=["narrative", "scoping", "systematic", "thesis"],
        default="narrative",
    )
    project_create.add_argument("--language", default="zh-CN")
    project_list = project_commands.add_parser("list", help="列出项目")
    project_list.add_argument("--json", action="store_true", help="输出完整 JSON")
    project_show = project_commands.add_parser("show", help="查看项目")
    project_show.add_argument("project_id")
    project_show.add_argument("--json", action="store_true", help="输出完整 JSON")
    project_export = project_commands.add_parser("export", help="导出可移植归档")
    project_export.add_argument("project_id")
    project_export.add_argument("destination", type=Path)

    research = subparsers.add_parser("research", help="运行项目研究工作流")
    research_commands = research.add_subparsers(
        dest="research_command",
        required=True,
    )
    research_start = research_commands.add_parser("start", help="启动研究")
    research_start.add_argument("project_id")
    research_start.add_argument("--demo", action="store_true")
    research_start.add_argument("--fixture", type=Path)
    research_start.add_argument(
        "--complete",
        action="store_true",
        help="跳过人工筛选暂停，直接完成所有阶段",
    )
    research_continue = research_commands.add_parser(
        "continue",
        help="人工筛选后继续",
    )
    research_continue.add_argument("run_id")
    research_continue.add_argument("--demo", action="store_true")
    research_continue.add_argument("--fixture", type=Path)

    screen = subparsers.add_parser("screen", help="人工纳排")
    screen_commands = screen.add_subparsers(dest="screen_command", required=True)
    screen_list = screen_commands.add_parser("list", help="列出待筛论文")
    screen_list.add_argument("project_id")
    screen_list.add_argument("--status", default=None)
    screen_list.add_argument("--json", action="store_true", help="输出完整 JSON")
    screen_decide = screen_commands.add_parser("decide", help="记录纳排决定")
    screen_decide.add_argument("project_id")
    screen_decide.add_argument("paper_id", type=int, help="数据库论文 ID")
    screen_decide.add_argument(
        "status",
        choices=["included", "excluded", "maybe"],
    )
    screen_decide.add_argument("--reason", default="")
    screen_decide.add_argument("--reviewer", default="human")
    screen_configure = screen_commands.add_parser(
        "configure",
        help="配置单人或独立双人筛选",
    )
    screen_configure.add_argument("project_id")
    screen_configure.add_argument(
        "--mode",
        choices=["single", "dual"],
        default="dual",
    )
    screen_configure.add_argument(
        "--reviewer",
        action="append",
        default=[],
        help="双人模式需重复两次",
    )
    screen_configure.add_argument(
        "--open",
        action="store_true",
        help="关闭盲审；仅双方完成后可用",
    )
    screen_status = screen_commands.add_parser(
        "status",
        help="查看个人队列或揭盲后的共识",
    )
    screen_status.add_argument("project_id")
    screen_status.add_argument("--reviewer", default="")
    screen_status.add_argument("--json", action="store_true")
    screen_resolve = screen_commands.add_parser(
        "resolve",
        help="仲裁双人筛选分歧",
    )
    screen_resolve.add_argument("project_id")
    screen_resolve.add_argument("paper_id", type=int)
    screen_resolve.add_argument(
        "status",
        choices=["included", "excluded"],
    )
    screen_resolve.add_argument("--reason", required=True)
    screen_resolve.add_argument("--reviewer", required=True, help="仲裁人标识")
    screen_fulltext = screen_commands.add_parser(
        "fulltext",
        help="管理全文获取与最终纳排",
    )
    fulltext_commands = screen_fulltext.add_subparsers(
        dest="fulltext_command",
        required=True,
    )
    fulltext_configure = fulltext_commands.add_parser(
        "configure",
        help="启用、揭盲或关闭未开始的全文筛选",
    )
    fulltext_configure.add_argument("project_id")
    fulltext_configure.add_argument("--disable", action="store_true")
    fulltext_configure.add_argument(
        "--open",
        action="store_true",
        help="双方完成后揭盲",
    )
    fulltext_status = fulltext_commands.add_parser(
        "status",
        help="查看全文获取与筛选队列",
    )
    fulltext_status.add_argument("project_id")
    fulltext_status.add_argument("--reviewer", default="")
    fulltext_status.add_argument("--json", action="store_true")
    fulltext_retrieve = fulltext_commands.add_parser(
        "retrieve",
        help="记录全文获取状态",
    )
    fulltext_retrieve.add_argument("project_id")
    fulltext_retrieve.add_argument("paper_id", type=int)
    fulltext_retrieve.add_argument(
        "status",
        choices=["not_requested", "sought", "retrieved", "not_retrieved"],
    )
    fulltext_retrieve.add_argument("--reason", default="")
    fulltext_retrieve.add_argument("--reviewer", default="human")
    fulltext_decide = fulltext_commands.add_parser(
        "decide",
        help="记录全文纳排决定",
    )
    fulltext_decide.add_argument("project_id")
    fulltext_decide.add_argument("paper_id", type=int)
    fulltext_decide.add_argument(
        "status",
        choices=["included", "excluded", "maybe"],
    )
    fulltext_decide.add_argument("--reason", default="")
    fulltext_decide.add_argument("--reason-code", default="")
    fulltext_decide.add_argument("--reviewer", default="human")
    fulltext_resolve = fulltext_commands.add_parser(
        "resolve",
        help="仲裁全文纳排或主要排除理由分歧",
    )
    fulltext_resolve.add_argument("project_id")
    fulltext_resolve.add_argument("paper_id", type=int)
    fulltext_resolve.add_argument(
        "status",
        choices=["included", "excluded"],
    )
    fulltext_resolve.add_argument("--reason", required=True)
    fulltext_resolve.add_argument("--reason-code", default="")
    fulltext_resolve.add_argument("--reviewer", required=True)

    document = subparsers.add_parser("document", help="全文文档与检索")
    document_commands = document.add_subparsers(
        dest="document_command",
        required=True,
    )
    document_add = document_commands.add_parser("add", help="导入 PDF/TXT/MD")
    document_add.add_argument("project_id")
    document_add.add_argument("path", type=Path)
    document_add.add_argument("--paper-id", type=int, default=None)
    document_add.add_argument("--json", action="store_true", help="输出完整 JSON")
    document_search = document_commands.add_parser("search", help="全文检索")
    document_search.add_argument("project_id")
    document_search.add_argument("query")
    document_search.add_argument("--limit", type=int, default=10)
    document_search.add_argument("--json", action="store_true", help="输出完整 JSON")

    bibliography = subparsers.add_parser(
        "bibliography",
        help="导入标准文献库文件",
    )
    bibliography_commands = bibliography.add_subparsers(
        dest="bibliography_command",
        required=True,
    )
    bibliography_import = bibliography_commands.add_parser(
        "import",
        help="导入 RIS、BibTeX 或 CSL JSON",
    )
    bibliography_import.add_argument("project_id")
    bibliography_import.add_argument("path", type=Path)
    bibliography_import.add_argument(
        "--json",
        action="store_true",
        help="输出完整 JSON",
    )

    serve = subparsers.add_parser("serve", help="启动本地 REST API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    evaluate = subparsers.add_parser("evaluate", help="评价一次完成的运行")
    evaluate.add_argument("run_dir", type=Path)
    evaluate.add_argument("--json", action="store_true", help="输出完整 JSON")

    subparsers.add_parser("plugins", help="列出检索器插件")

    taxonomy = subparsers.add_parser("taxonomy", help="计算机学科分类")
    taxonomy_commands = taxonomy.add_subparsers(
        dest="taxonomy_command",
        required=True,
    )
    taxonomy_commands.add_parser("list", help="列出所有 CS 方向")
    taxonomy_classify = taxonomy_commands.add_parser(
        "classify",
        help="判断主题所属方向",
    )
    taxonomy_classify.add_argument("text")
    taxonomy_classify.add_argument("--limit", type=int, default=3)

    cs_inspect = subparsers.add_parser("cs-inspect", help="查看运行的 CS 专属分析")
    cs_inspect.add_argument("run_dir", type=Path)
    cs_inspect.add_argument("--json", action="store_true", help="输出完整 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "taxonomy":
            from dataclasses import asdict

            from .cs_taxonomy import CSTaxonomy

            taxonomy = CSTaxonomy.load()
            if args.taxonomy_command == "list":
                values = [asdict(domain) for domain in taxonomy.domains]
            else:
                values = [
                    item.to_dict()
                    for item in taxonomy.classify_text(
                        args.text,
                        limit=args.limit,
                    )
                ]
            print(json.dumps(values, ensure_ascii=False, indent=2))
            return 0
        if args.command == "cs-inspect":
            state = load_state(args.run_dir.resolve())
            if args.json:
                _print_json(state.cs_analysis)
            else:
                _print_cs_analysis(state.cs_analysis)
            return 0
        if args.command == "evaluate":
            from .evaluation import evaluate_run

            result = evaluate_run(args.run_dir)
            value = result.to_dict()
            if args.json:
                _print_json(value)
            else:
                _print_evaluation(value)
            return 0 if result.overall >= 0.7 else 3
        if args.command == "plugins":
            from dataclasses import asdict

            from .plugins import RetrieverRegistry

            values = [asdict(item) for item in RetrieverRegistry().discover().list()]
            print(json.dumps(values, ensure_ascii=False, indent=2))
            return 0
        if args.command == "serve":
            try:
                import uvicorn
            except ImportError as exc:
                raise RuntimeError(
                    "请先安装 API 依赖：pip install 'paper-research-agent[api]'"
                ) from exc
            if args.host not in {"127.0.0.1", "localhost", "::1"}:
                print(
                    "警告：该 API 默认无身份认证，请勿直接暴露到公网。",
                    file=sys.stderr,
                )
            uvicorn.run(
                "paper_agent.api:create_app",
                factory=True,
                host=args.host,
                port=args.port,
            )
            return 0
        if args.command in {
            "project",
            "research",
            "screen",
            "document",
            "bibliography",
        }:
            settings = Settings.from_env()
            workbench = ResearchWorkbench(settings)
            if args.command == "bibliography":
                result = workbench.import_bibliography(
                    args.project_id,
                    data=args.path.read_bytes(),
                    filename=args.path.name,
                )
                value = result.to_dict()
                if args.json:
                    _print_json(value)
                else:
                    _print_bibliography_import(value)
                return 0
            if args.command == "project":
                if args.project_command == "create":
                    project = workbench.create_project(
                        name=args.name,
                        topic=args.topic,
                        research_question=args.question,
                        review_type=args.type,
                        language=args.language,
                    )
                    print(json.dumps(project.to_dict(), ensure_ascii=False, indent=2))
                elif args.project_command == "list":
                    values = [
                        {
                            **project.to_dict(),
                            "stats": workbench.database.project_stats(project.id),
                        }
                        for project in workbench.database.list_projects()
                    ]
                    if args.json:
                        _print_json(values)
                    else:
                        _print_projects(values)
                elif args.project_command == "show":
                    project = workbench.database.require_project(args.project_id)
                    value = {
                        **project.to_dict(),
                        "stats": workbench.database.project_stats(project.id),
                        "runs": workbench.database.list_runs(project.id),
                        "reports": workbench.database.list_reports(project.id),
                    }
                    if args.json:
                        _print_json(value)
                    else:
                        _print_project(value)
                else:
                    from .exporter import export_project

                    path = export_project(
                        workbench.database,
                        args.project_id,
                        args.destination,
                    )
                    print(str(path))
                return 0
            if args.command == "research":
                if args.research_command == "start":
                    project = workbench.database.require_project(args.project_id)
                    llm = (
                        DemoLLM(project.topic)
                        if args.demo
                        else OpenAIResponsesLLM(settings)
                    )
                    retrievers = (
                        [FixtureRetriever(args.fixture)] if args.fixture else None
                    )
                    run = workbench.create_run(project.id)
                    run_dir = workbench.execute_run(
                        run.id,
                        llm=llm,
                        retrievers=retrievers,
                        stop_for_screening=False if args.complete else None,
                    )
                    print(
                        json.dumps(
                            {
                                "run_id": run.id,
                                "run_dir": str(run_dir),
                                "status": workbench.database.get_run(run.id)["status"],
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                else:
                    run = workbench.database.get_run(args.run_id)
                    if not run:
                        raise WorkbenchError(f"Run not found: {args.run_id}")
                    project = workbench.database.require_project(run["project_id"])
                    llm = (
                        DemoLLM(project.topic)
                        if args.demo
                        else OpenAIResponsesLLM(settings)
                    )
                    retrievers = (
                        [FixtureRetriever(args.fixture)] if args.fixture else None
                    )
                    run_dir = workbench.continue_after_screening(
                        args.run_id,
                        llm=llm,
                        retrievers=retrievers,
                    )
                    print(str(run_dir))
                return 0
            if args.command == "screen":
                if args.screen_command == "list":
                    rows = workbench.database.list_project_papers(
                        args.project_id,
                        status=args.status,
                    )
                    values = [
                        {
                            **{
                                key: value
                                for key, value in row.items()
                                if key != "paper"
                            },
                            "paper": row["paper"].to_dict(),
                        }
                        for row in rows
                    ]
                    if args.json:
                        _print_json(values)
                    else:
                        _print_screening(values)
                elif args.screen_command == "decide":
                    workbench.record_screening(
                        project_id=args.project_id,
                        paper_id=args.paper_id,
                        status=args.status,
                        reason=args.reason,
                        reviewer=args.reviewer,
                    )
                    print("已保存筛选决定。")
                elif args.screen_command == "configure":
                    reviewers = args.reviewer
                    if args.open:
                        current = workbench.database.get_screening_config(
                            args.project_id
                        )
                        reviewers = current["reviewers"]
                    value = workbench.configure_screening(
                        args.project_id,
                        mode=args.mode,
                        reviewers=reviewers,
                        blind=args.mode == "dual" and not args.open,
                    )
                    _print_json(value)
                elif args.screen_command == "status":
                    value = workbench.screening_workspace(
                        args.project_id,
                        reviewer=args.reviewer,
                    )
                    serializable = {
                        **value,
                        "papers": [
                            {
                                **{
                                    key: item
                                    for key, item in paper.items()
                                    if key != "paper"
                                },
                                "paper": paper["paper"].to_dict(),
                            }
                            for paper in value["papers"]
                        ],
                    }
                    if args.json:
                        _print_json(serializable)
                    else:
                        print(
                            f"模式：{value['config']['mode']} "
                            f"· 盲审：{'是' if value['config']['blind'] else '否'}"
                        )
                        print(
                            f"进度：{value['summary'].get('reviewer_completed', 0)}"
                            f" / {value['summary']['total']}"
                        )
                        _print_screening(serializable["papers"])
                elif args.screen_command == "resolve":
                    value = workbench.resolve_screening(
                        args.project_id,
                        args.paper_id,
                        status=args.status,
                        reason=args.reason,
                        resolved_by=args.reviewer,
                    )
                    _print_json(value)
                else:
                    if args.fulltext_command == "configure":
                        value = workbench.configure_fulltext_screening(
                            args.project_id,
                            enabled=not args.disable,
                            blind=not args.open,
                        )
                        _print_json(value)
                    elif args.fulltext_command == "status":
                        value = workbench.fulltext_screening_workspace(
                            args.project_id,
                            reviewer=args.reviewer,
                        )
                        serializable = {
                            **value,
                            "papers": [
                                {
                                    **{
                                        key: item
                                        for key, item in paper.items()
                                        if key != "paper"
                                    },
                                    "screening_status": paper["fulltext_status"],
                                    "screening_reason": paper["fulltext_reason"],
                                    "paper": paper["paper"].to_dict(),
                                }
                                for paper in value["papers"]
                            ],
                        }
                        if args.json:
                            _print_json(serializable)
                        else:
                            summary = value["summary"]
                            print(
                                "全文候选："
                                f"{summary.get('total_candidates', 0)} "
                                f"· 已获取 {summary.get('retrieved', 0)} "
                                f"· 未获取 {summary.get('not_retrieved', 0)}"
                            )
                            _print_screening(serializable["papers"])
                    elif args.fulltext_command == "retrieve":
                        value = workbench.record_fulltext_retrieval(
                            args.project_id,
                            args.paper_id,
                            status=args.status,
                            reason=args.reason,
                            updated_by=args.reviewer,
                        )
                        _print_json(value)
                    elif args.fulltext_command == "decide":
                        workbench.record_fulltext_screening_batch(
                            project_id=args.project_id,
                            decisions=[
                                {
                                    "paper_id": args.paper_id,
                                    "status": args.status,
                                    "reason": args.reason,
                                    "exclusion_code": args.reason_code,
                                    "reviewer": args.reviewer,
                                }
                            ],
                        )
                        print("已保存全文筛选决定。")
                    else:
                        value = workbench.resolve_fulltext_screening(
                            args.project_id,
                            args.paper_id,
                            status=args.status,
                            reason=args.reason,
                            exclusion_code=args.reason_code,
                            resolved_by=args.reviewer,
                        )
                        _print_json(value)
                return 0
            if args.document_command == "add":
                record = workbench.documents.ingest(
                    project_id=args.project_id,
                    source=args.path,
                    paper_id=args.paper_id,
                )
                from dataclasses import asdict

                value = asdict(record)
                if args.json:
                    _print_json(value)
                else:
                    print(f"已导入：{value['filename']} · {value['page_count']} 页")
                    print(f"文档 ID：{value['id']}")
            else:
                values = workbench.documents.search(
                    args.project_id,
                    args.query,
                    limit=args.limit,
                )
                if args.json:
                    _print_json(values)
                else:
                    _print_document_hits(values)
            return 0
        if args.command == "inspect":
            state = load_state(args.run_dir.resolve())
            summary = {
                "run_id": state.run_id,
                "stage": state.stage,
                "topic": state.topic,
                "question": state.question,
                "papers": len(state.papers),
                "evidence_cards": len(state.evidence),
                "search_summary": state.search_log.get("summary", {}),
                "audit": state.audit,
                "warnings": state.warnings,
            }
            if args.json:
                _print_json(summary)
            else:
                _print_run_summary(summary)
            return 0
        if args.command == "run":
            agent = _agent(args, args.topic)
            run_dir = agent.run(args.topic, args.question)
        else:
            state = load_state(args.run_dir.resolve())
            agent = _agent(args, state.topic)
            run_dir = agent.resume(args.run_dir)
        print(f"\n完成：{run_dir}")
        print(f"报告：{run_dir / 'report.md'}")
        print(f"审计：{run_dir / 'audit.json'}")
        return 0
    except (
        FileNotFoundError,
        RuntimeError,
        ValueError,
        LLMError,
        WorkflowError,
        WorkbenchError,
        DatabaseError,
    ) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已中断；可使用 resume 命令从检查点继续。", file=sys.stderr)
        return 130
