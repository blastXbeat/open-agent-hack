"""Compile nodes, edges, and cited evidence into the viewer JSON schema."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Evidence:
    paper_id: str
    quote: str
    sql: str | None = None
    source: str = "corpus"


@dataclass
class Node:
    id: str
    title: str
    year: str | None = None
    source: str = "zetaris"
    abstract: str | None = None


@dataclass
class Edge:
    source: str
    target: str
    relation: str
    evidence: list[Evidence] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "from": self.source,
            "to": self.target,
            "relation": self.relation,
            "evidence": [asdict(item) for item in self.evidence],
        }


@dataclass
class LiteratureGraph:
    seed_query: str
    tree_id: str
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_node(self, node: Node) -> None:
        if any(existing.id == node.id for existing in self.nodes):
            return
        self.nodes.append(node)

    def add_edge(self, edge: Edge) -> None:
        if not edge.evidence:
            self.warnings.append(f"Dropped edge {edge.source}->{edge.target}: no cited evidence")
            return
        self.edges.append(edge)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed_query": self.seed_query,
            "tree_id": self.tree_id,
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [edge.as_dict() for edge in self.edges],
            "checkpoints": self.checkpoints,
            "warnings": self.warnings,
        }

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path
