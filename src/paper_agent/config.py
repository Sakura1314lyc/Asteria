from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path


def load_dotenv(path: Path | str = ".env") -> None:
    """Load a small, dependency-free subset of dotenv syntax."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be >= 1")
    return value


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _csv(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(slots=True)
class Settings:
    model: str = "gpt-5.6-terra"
    base_url: str = "https://api.openai.com/v1"
    language: str = "zh-CN"
    max_papers: int = 12
    results_per_query: int = 6
    max_queries: int = 5
    reasoning_effort: str = "medium"
    request_timeout: float = 45.0
    max_retries: int = 2
    output_root: Path = Path("runs")
    data_root: Path = Path(".paper-agent")
    database_path: Path = Path(".paper-agent/workbench.db")
    dblp_enabled: bool = True
    max_upload_mb: int = 50
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    web_dist: Path | None = None

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        return cls(
            model=os.getenv("PAPER_AGENT_MODEL", "gpt-5.6-terra"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip(
                "/"
            ),
            language=os.getenv("PAPER_AGENT_LANGUAGE", "zh-CN"),
            max_papers=_positive_int("PAPER_AGENT_MAX_PAPERS", 12),
            results_per_query=_positive_int("PAPER_AGENT_RESULTS_PER_QUERY", 6),
            max_queries=_positive_int("PAPER_AGENT_MAX_QUERIES", 5),
            reasoning_effort=os.getenv("PAPER_AGENT_REASONING_EFFORT", "medium"),
            output_root=Path(os.getenv("PAPER_AGENT_OUTPUT_ROOT", "runs")),
            data_root=Path(os.getenv("PAPER_AGENT_DATA_ROOT", ".paper-agent")),
            database_path=Path(
                os.getenv(
                    "PAPER_AGENT_DATABASE",
                    ".paper-agent/workbench.db",
                )
            ),
            dblp_enabled=_boolean("PAPER_AGENT_DBLP_ENABLED", True),
            max_upload_mb=_positive_int("PAPER_AGENT_MAX_UPLOAD_MB", 50),
            cors_origins=_csv(
                "PAPER_AGENT_CORS_ORIGINS",
                (
                    "http://127.0.0.1:5173",
                    "http://localhost:5173",
                ),
            ),
            web_dist=(
                Path(value)
                if (value := os.getenv("PAPER_AGENT_WEB_DIST", "").strip())
                else None
            ),
        )

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["output_root"] = str(self.output_root)
        data["data_root"] = str(self.data_root)
        data["database_path"] = str(self.database_path)
        data["cors_origins"] = list(self.cors_origins)
        data["web_dist"] = str(self.web_dist) if self.web_dist else None
        return data
