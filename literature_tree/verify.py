#!/usr/bin/env python3
"""Verify Zetaris REST and the 3-agent pool on a sample literature query.

Read-only. Does not CREATE sources. Uses the bundled fixture for the pool when
LITERATURE_PAPERS_TABLE is unset (this instance currently has no paper corpus).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from literature_tree.config import load_settings, model_ready, require_zetaris
from literature_tree.memory import STORE
from literature_tree.tools_zetaris import ZetarisTools
from literature_tree.workers import SlidingWindowPool

SAMPLE = "attention is all you need"


def report(ok: bool, label: str, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {label}" + (f": {detail}" if detail else ""))
    return ok


def verify_rest() -> bool:
    settings = load_settings()
    try:
        require_zetaris(settings)
        tools = ZetarisTools(settings)
    except Exception as error:
        return report(False, "REST client", str(error))
    ok = True
    try:
        ds = tools.datasources()
        names = ds if isinstance(ds, list) else (ds or {}).get("data", [])
        ok &= report(True, "GET /datasource/datasources", f"HTTP 200, {len(names)} listed")
    except Exception as error:
        ok &= report(False, "GET /datasource/datasources", str(error))
    try:
        ok &= report(tools.select_one(), "SELECT 1")
    except Exception as error:
        ok &= report(False, "SELECT 1", str(error))
    try:
        dbs = tools.list_lightning_databases()
        ok &= report(True, "SHOW LIGHTNING DATABASES", ", ".join(dbs) if dbs else "none")
    except Exception as error:
        ok &= report(False, "SHOW LIGHTNING DATABASES", str(error))
    if settings.papers_table:
        try:
            rows = tools.describe_table(settings.papers_table)
            ok &= report(True, "DESCRIBE papers table", f"{len(rows)} fields")
        except Exception as error:
            ok &= report(False, "DESCRIBE papers table", str(error))
    else:
        print("[INFO] LITERATURE_PAPERS_TABLE unset; live paper queries skipped")
    return ok


def verify_pool() -> bool:
    settings = load_settings()
    print(f"[INFO] LLM provider configured: {model_ready(settings)}")
    pool = SlidingWindowPool(settings=settings, tools=None, use_fixture=True)
    graph = pool.run(SAMPLE, hops=2, tree_id="verify-sample")
    out = STORE / graph.tree_id / "graph.json"
    graph.write(out)
    ok = True
    ok &= report(len(graph.nodes) >= 2, "pool nodes", str(len(graph.nodes)))
    ok &= report(len(graph.edges) >= 1, "pool edges", str(len(graph.edges)))
    ok &= report(
        all(edge.evidence for edge in graph.edges),
        "every edge has cited evidence",
    )
    ok &= report(len(graph.checkpoints) >= 1, "H-Mem checkpoints", str(len(graph.checkpoints)))
    ok &= report(out.is_file(), "graph JSON", str(out))
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-rest", action="store_true")
    parser.add_argument("--skip-pool", action="store_true")
    args = parser.parse_args()
    ok = True
    if not args.skip_rest:
        ok &= verify_rest()
    if not args.skip_pool:
        ok &= verify_pool()
    print("READY" if ok else "NOT READY")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
