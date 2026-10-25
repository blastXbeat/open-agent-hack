"""Dynamic 3-agent sliding-window pool for literature traversal.

Agent 1 discovers papers (Zetaris, or a fixture when no corpus table exists).
Agent 2 infers edges with citation quotes and writes a Markovian checkpoint.
Agent 3 synthesizes the interactive graph JSON.

The window is always those three roles. Each hop advances the frontier; H-Mem
keeps bounded checkpoints so context does not grow with tree depth.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from literature_tree.config import Settings, load_settings, model_ready
from literature_tree.graph import Edge, Evidence, LiteratureGraph, Node
from literature_tree.llm import ModelNotConfigured, chat
from literature_tree.memory import Checkpoint, HMem
from literature_tree.tools_zetaris import ZetarisTools

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_papers.json"


class DiscoveryAgent:
    name = "discovery"

    def __init__(self, tools: ZetarisTools | None, fixture: dict[str, Any] | None) -> None:
        self.tools = tools
        self.fixture = fixture

    def run(self, query: str, frontier: list[str]) -> tuple[list[dict[str, Any]], str | None]:
        if self.tools and self.tools.settings.papers_table:
            try:
                rows = self.tools.fetch_papers(query)
                if frontier:
                    rows.extend(self.tools.fetch_abstracts(frontier))
                if rows:
                    return _normalize_rows(rows), None
                return [], "papers table returned no rows"
            except Exception as error:  # ZetarisError and identifier errors
                return [], f"Zetaris discovery failed: {error}"
        papers = list((self.fixture or {}).get("papers") or [])
        if not papers:
            return [], "no fixture and no LITERATURE_PAPERS_TABLE"
        needle = query.lower()
        matched = [
            paper
            for paper in papers
            if needle in paper.get("title", "").lower()
            or needle in paper.get("abstract", "").lower()
            or paper.get("paper_id") in frontier
        ]
        related_ids = {rid for paper in matched for rid in paper.get("related", [])}
        extra = [paper for paper in papers if paper.get("paper_id") in related_ids]
        found = {paper["paper_id"]: paper for paper in matched + extra}
        return list(found.values()), "using bundled fixture (no literature table on instance)"


class InferenceAgent:
    name = "inference"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(
        self,
        query: str,
        hop: int,
        papers: list[dict[str, Any]],
        prior: Checkpoint | None,
    ) -> tuple[list[Edge], Checkpoint, str | None]:
        warning = None
        edges: list[Edge] = []
        if model_ready(self.settings) and papers:
            try:
                edges = self._from_model(query, papers)
            except ModelNotConfigured as error:
                warning = str(error)
            except Exception as error:
                warning = f"LLM inference failed, using extractive edges: {error}"
        if not edges:
            edges = _extractive_edges(papers)
        checkpoint = Checkpoint(
            hop=hop,
            seed_query=query,
            frontier=[str(p.get("paper_id")) for p in papers],
            papers=[{"paper_id": p.get("paper_id"), "title": p.get("title")} for p in papers],
            edges=[edge.as_dict() for edge in edges],
            open_questions=[f"What follows {p.get('paper_id')}?" for p in papers[-3:]],
            notes=(prior.notes if prior else "")[:200],
        ).bound()
        return edges, checkpoint, warning

    def _from_model(self, query: str, papers: list[dict[str, Any]]) -> list[Edge]:
        payload = json.dumps(
            [
                {
                    "paper_id": p.get("paper_id"),
                    "title": p.get("title"),
                    "year": p.get("year"),
                    "abstract": (p.get("abstract") or "")[:400],
                    "related": p.get("related", []),
                }
                for p in papers
            ],
            ensure_ascii=False,
        )
        text = chat(
            self.settings,
            [
                {
                    "role": "system",
                    "content": (
                        "Infer citation-backed relationships among papers. "
                        "Reply with JSON only: {\"edges\":[{\"from\",\"to\",\"relation\",\"quote\"}]}. "
                        "Every edge needs a short quote copied from an abstract."
                    ),
                },
                {"role": "user", "content": f"Seed query: {query}\nPapers: {payload}"},
            ],
        )
        data = _parse_json_object(text)
        edges: list[Edge] = []
        by_id = {str(p.get("paper_id")): p for p in papers}
        for raw in data.get("edges") or []:
            src, dst = str(raw.get("from")), str(raw.get("to"))
            quote = str(raw.get("quote") or "").strip()
            if src not in by_id or dst not in by_id or not quote:
                continue
            edges.append(
                Edge(
                    source=src,
                    target=dst,
                    relation=str(raw.get("relation") or "related"),
                    evidence=[Evidence(paper_id=src, quote=quote, source="nemotron")],
                )
            )
        return edges


class GraphSynthesizer:
    name = "synthesizer"

    def run(
        self,
        graph: LiteratureGraph,
        papers: list[dict[str, Any]],
        edges: list[Edge],
        checkpoint: Checkpoint,
    ) -> LiteratureGraph:
        for paper in papers:
            graph.add_node(
                Node(
                    id=str(paper.get("paper_id")),
                    title=str(paper.get("title") or paper.get("paper_id")),
                    year=str(paper.get("year")) if paper.get("year") is not None else None,
                    abstract=paper.get("abstract"),
                    source=str(paper.get("source") or "zetaris"),
                )
            )
        for edge in edges:
            graph.add_edge(edge)
        graph.checkpoints.append(
            {
                "hop": checkpoint.hop,
                "frontier": checkpoint.frontier,
                "notes": checkpoint.notes,
            }
        )
        return graph


class SlidingWindowPool:
    """Always three live workers; hops slide the frontier, not extra agents."""

    window = 3

    def __init__(
        self,
        settings: Settings | None = None,
        tools: ZetarisTools | None = None,
        use_fixture: bool = False,
    ) -> None:
        self.settings = settings or load_settings()
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8")) if use_fixture or not self.settings.papers_table else None
        self.discovery = DiscoveryAgent(None if use_fixture else tools, fixture)
        self.inference = InferenceAgent(self.settings)
        self.synthesizer = GraphSynthesizer()

    def run(self, query: str, hops: int = 3, tree_id: str | None = None, resume: bool = False) -> LiteratureGraph:
        hops = max(1, min(hops, 8))
        tree_id = tree_id or re.sub(r"[^a-z0-9]+", "-", query.lower())[:40].strip("-") or "tree"
        memory = HMem(tree_id)
        graph = LiteratureGraph(seed_query=query, tree_id=tree_id)
        prior = memory.load_latest() if resume else None
        frontier = prior.frontier if prior else []
        current_query = query
        start = (prior.hop + 1) if prior else 1
        for hop in range(start, start + hops):
            papers, discover_warning = self.discovery.run(current_query, frontier)
            if discover_warning:
                graph.warnings.append(discover_warning)
            edges, checkpoint, infer_warning = self.inference.run(query, hop, papers, prior)
            if infer_warning:
                graph.warnings.append(infer_warning)
            memory.save(checkpoint)
            self.synthesizer.run(graph, papers, edges, checkpoint)
            frontier = checkpoint.frontier
            current_query = papers[-1]["title"] if papers else query
            prior = checkpoint
            if not papers:
                break
        return graph


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    papers = []
    for row in rows:
        paper_id = str(row.get("paper_id") or row.get("id") or row.get("c0") or "")
        if not paper_id:
            continue
        papers.append(
            {
                "paper_id": paper_id,
                "title": row.get("title") or row.get("c1") or paper_id,
                "year": row.get("year") or row.get("c2"),
                "abstract": row.get("abstract") or row.get("c3") or "",
                "related": row.get("related") or [],
                "source": "zetaris",
            }
        )
    return papers


def _extractive_edges(papers: list[dict[str, Any]]) -> list[Edge]:
    by_id = {str(p.get("paper_id")): p for p in papers}
    edges: list[Edge] = []
    for paper in papers:
        src = str(paper.get("paper_id"))
        quote = (paper.get("abstract") or paper.get("title") or src)[:240]
        for dst in paper.get("related") or []:
            if str(dst) not in by_id:
                continue
            edges.append(
                Edge(
                    source=src,
                    target=str(dst),
                    relation="cites_or_extends",
                    evidence=[Evidence(paper_id=src, quote=quote, source="abstract")],
                )
            )
    if not edges and len(papers) >= 2:
        src, dst = papers[0], papers[1]
        quote = (src.get("abstract") or src.get("title") or src["paper_id"])[:240]
        edges.append(
            Edge(
                source=str(src.get("paper_id")),
                target=str(dst.get("paper_id")),
                relation="co_retrieved",
                evidence=[Evidence(paper_id=str(src.get("paper_id")), quote=quote, source="abstract")],
            )
        )
    return edges


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
