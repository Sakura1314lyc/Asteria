from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .models import Paper


@dataclass(slots=True)
class GraphEdge:
    source: str
    target: str
    weight: float
    reasons: list[str]


def build_literature_graph(
    papers: list[Paper],
    *,
    similarity_threshold: float = 0.18,
) -> dict[str, object]:
    nodes = [
        {
            "id": paper.paper_id,
            "title": paper.title,
            "year": paper.year,
            "authors": paper.authors,
            "venue": paper.venue,
            "citations": paper.citation_count,
            "score": paper.score,
        }
        for paper in papers
    ]
    edges: list[GraphEdge] = []
    for index, left in enumerate(papers):
        left_terms = _terms(f"{left.title} {left.abstract[:1200]}")
        left_authors = {author.casefold() for author in left.authors}
        for right in papers[index + 1 :]:
            right_terms = _terms(f"{right.title} {right.abstract[:1200]}")
            right_authors = {author.casefold() for author in right.authors}
            union = left_terms | right_terms
            similarity = len(left_terms & right_terms) / len(union) if union else 0.0
            shared_authors = sorted(left_authors & right_authors)
            reasons: list[str] = []
            weight = similarity
            if similarity >= similarity_threshold:
                reasons.append(f"term_similarity:{similarity:.3f}")
            if shared_authors:
                weight += min(0.5, 0.15 * len(shared_authors))
                reasons.append("shared_authors:" + ",".join(shared_authors[:3]))
            if reasons:
                edges.append(
                    GraphEdge(
                        source=left.paper_id,
                        target=right.paper_id,
                        weight=round(weight, 3),
                        reasons=reasons,
                    )
                )
    return {
        "nodes": nodes,
        "edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "weight": edge.weight,
                "reasons": edge.reasons,
            }
            for edge in edges
        ],
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "meaning": (
                "Edges represent lexical similarity or shared authorship, "
                "not direct citation links."
            ),
        },
    }


def write_graph_artifacts(
    graph: dict[str, object],
    json_path: Path,
    graphml_path: Path,
) -> None:
    json_path.write_text(
        json.dumps(graph, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '<key id="title" for="node" attr.name="title" attr.type="string"/>',
        '<key id="weight" for="edge" attr.name="weight" attr.type="double"/>',
        '<graph id="literature" edgedefault="undirected">',
    ]
    for node in nodes if isinstance(nodes, list) else []:
        node_id = html.escape(str(node["id"]), quote=True)
        title = html.escape(str(node["title"]))
        lines.append(f'<node id="{node_id}"><data key="title">{title}</data></node>')
    for index, edge in enumerate(edges if isinstance(edges, list) else []):
        source = html.escape(str(edge["source"]), quote=True)
        target = html.escape(str(edge["target"]), quote=True)
        weight = float(edge["weight"])
        lines.append(
            f'<edge id="e{index}" source="{source}" target="{target}">'
            f'<data key="weight">{weight}</data></edge>'
        )
    lines.extend(["</graph>", "</graphml>"])
    graphml_path.write_text("\n".join(lines), encoding="utf-8")


def _terms(text: str) -> set[str]:
    stop = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "using",
        "study",
        "paper",
        "based",
    }
    return {
        term
        for term in re.findall(r"[a-z0-9\u4e00-\u9fff]{3,}", text.casefold())
        if term not in stop
    }
