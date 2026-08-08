"""Read-only public observatory for the Vercel deployment.

The full Asteria workbench is local-first and persists to SQLite. Vercel's
filesystem is ephemeral, so the public deployment seeds a deterministic demo
inside /tmp and rejects mutations. This keeps the showcase useful without
pretending to provide durable research storage or accepting user API keys.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi import Request
from fastapi.responses import JSONResponse

from paper_agent import database as database_module
from paper_agent import workbench as workbench_module
from paper_agent.api import create_app
from paper_agent.config import Settings
from paper_agent.domain import ReviewProtocol
from paper_agent.llm import DemoLLM
from paper_agent.retrievers import bundled_demo_retriever

RUNTIME_ROOT = (
    Path("/tmp/asteria-observatory-v2")
    if os.getenv("VERCEL")
    else Path(tempfile.gettempdir()) / "asteria-observatory-v2"
)


def _public_id(prefix: str) -> str:
    return f"{prefix}_public_observatory"


# Every serverless instance must expose the same public routes. These modules
# import new_id directly, so patch their local reference only for this Vercel
# entrypoint; the installed/local Asteria package keeps random UUID-based IDs.
database_module.new_id = _public_id
workbench_module.new_id = _public_id

settings = Settings(
    model="demo",
    language="zh-CN",
    output_root=RUNTIME_ROOT / "runs",
    data_root=RUNTIME_ROOT / "data",
    database_path=RUNTIME_ROOT / "workbench.db",
    dblp_enabled=False,
    cors_origins=(),
)

app = create_app(settings)


def _seed_observatory() -> None:
    workbench = app.state.workbench
    if workbench.database.list_projects():
        return
    project = workbench.create_project(
        name="CS Agent 检索复现审计",
        topic="reproducible literature search for computer science research agents",
        research_question=(
            "How reproducible are agentic literature searches in computer science?"
        ),
        review_type="systematic",
        language="zh-CN",
    )
    workbench.database.update_protocol(
        project.id,
        ReviewProtocol(
            review_type="systematic",
            population=["computer science research agents"],
            intervention=["agentic literature search"],
            comparison=["manual or conventional search workflows"],
            outcomes=["reproducibility", "citation grounding", "auditability"],
            include_keywords=["research agent", "literature search", "reproducibility"],
            exclude_keywords=["editorial", "non-scholarly demo"],
            year_from=2020,
            languages=["en", "zh-CN"],
            study_types=["evaluation", "benchmark", "system study"],
            notes="Synthetic public protocol for interface evaluation only.",
        ),
        amendment_reason=(
            "合成样例：试检索后补充复现性、引用约束与审计关键词。"
        ),
    )
    run = workbench.create_run(project.id, agent_id="deep_review")
    workbench.execute_run(
        run.id,
        llm=DemoLLM(project.topic),
        retrievers=[bundled_demo_retriever()],
        stop_for_screening=False,
        agent_id="deep_review",
    )


_seed_observatory()


@app.middleware("http")
async def public_demo_guard(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        return JSONResponse(
            status_code=403,
            content={
                "detail": (
                    "Asteria Observatory is a read-only public sample. "
                    "Run the local workbench for persistent research and model connections."
                )
            },
        )
    response = await call_next(request)
    response.headers["X-Asteria-Mode"] = "public-read-only"
    return response
