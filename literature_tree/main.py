#!/usr/bin/env python3
"""Run the Literature Tree Exploration Agent.

  python3 -m literature_tree.main --query "attention is all you need" --hops 3 --dry-run
  python3 -m literature_tree.main --query "attention is all you need" --hops 3 --fixture
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from literature_tree.config import load_settings, model_ready, require_zetaris
from literature_tree.memory import STORE
from literature_tree.tools_zetaris import ZetarisTools
from literature_tree.workers import SlidingWindowPool


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True, help="seed literature question")
    parser.add_argument("--hops", type=int, default=3, help="bounded traversal hops")
    parser.add_argument("--tree-id", help="H-Mem tree id (default: slugged query)")
    parser.add_argument("--dry-run", action="store_true", help="print plan only; no REST, no LLM")
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="use bundled sample papers instead of LITERATURE_PAPERS_TABLE",
    )
    parser.add_argument("--out", type=Path, help="graph JSON path")
    parser.add_argument("--resume", action="store_true", help="continue H-Mem checkpoints for this tree")
    args = parser.parse_args()

    settings = load_settings()
    plan = [
        "1. Discovery agent: query Zetaris papers table or fixture",
        "2. Inference agent: Meterless Runtime or Nemotron edges with quotes, else extractive abstracts",
        "3. Synthesizer: nodes/edges/evidence JSON + H-Mem checkpoint",
        f"hops={args.hops} fixture={args.fixture} model_ready={model_ready(settings)}",
        f"papers_table={settings.papers_table or '(unset)'}",
        f"env_file={settings.env_file}",
    ]
    print("Plan:")
    for line in plan:
        print(f"  {line}")
    if args.dry_run:
        return 0

    tools = None
    if not args.fixture:
        require_zetaris(settings)
        tools = ZetarisTools(settings)
    pool = SlidingWindowPool(settings=settings, tools=tools, use_fixture=args.fixture)
    graph = pool.run(args.query, hops=args.hops, tree_id=args.tree_id, resume=args.resume)
    out = args.out or (STORE / graph.tree_id / "graph.json")
    graph.write(out)
    print(json.dumps({"tree_id": graph.tree_id, "nodes": len(graph.nodes), "edges": len(graph.edges), "out": str(out), "warnings": graph.warnings}, indent=2))
    print(f"Open literature_tree/viewer/index.html and load {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
