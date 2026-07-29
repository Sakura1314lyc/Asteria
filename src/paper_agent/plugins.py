from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import entry_points

from .config import Settings
from .retrievers import (
    ArxivRetriever,
    DblpRetriever,
    OpenAlexRetriever,
    Retriever,
    SemanticScholarRetriever,
)

RetrieverFactory = Callable[[Settings], Retriever]


@dataclass(slots=True)
class PluginInfo:
    name: str
    kind: str
    source: str
    available: bool
    error: str = ""


class RetrieverRegistry:
    ENTRY_POINT_GROUP = "paper_agent.retrievers"

    def __init__(self):
        self.factories: dict[str, RetrieverFactory] = {
            "openalex": OpenAlexRetriever,
            "arxiv": ArxivRetriever,
            "dblp": DblpRetriever,
            "semantic_scholar": SemanticScholarRetriever,
        }
        self.info: dict[str, PluginInfo] = {
            name: PluginInfo(
                name=name,
                kind="retriever",
                source="builtin",
                available=True,
            )
            for name in self.factories
        }

    def discover(self) -> RetrieverRegistry:
        discovered = entry_points()
        selected = (
            discovered.select(group=self.ENTRY_POINT_GROUP)
            if hasattr(discovered, "select")
            else discovered.get(self.ENTRY_POINT_GROUP, [])
        )
        for entry in selected:
            try:
                factory = entry.load()
                self.factories[entry.name] = factory
                self.info[entry.name] = PluginInfo(
                    name=entry.name,
                    kind="retriever",
                    source=f"entry-point:{entry.value}",
                    available=True,
                )
            except Exception as exc:  # noqa: BLE001 - isolate broken third-party plugins
                self.info[entry.name] = PluginInfo(
                    name=entry.name,
                    kind="retriever",
                    source=f"entry-point:{entry.value}",
                    available=False,
                    error=str(exc),
                )
        return self

    def create(self, name: str, settings: Settings) -> Retriever:
        try:
            factory = self.factories[name]
        except KeyError as exc:
            raise ValueError(f"Unknown retriever plugin: {name}") from exc
        return factory(settings)

    def list(self) -> list[PluginInfo]:
        return sorted(self.info.values(), key=lambda item: item.name)
