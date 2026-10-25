"""Bounded rolling checkpoints (Markovian Thinking) and tree memory (H-Mem).

Each hop stores a small checkpoint instead of the full transcript. H-Mem
persists those checkpoints under tmp/literature_tree/ so later runs can
resume a tree. tmp/ is gitignored.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "tmp" / "literature_tree"


@dataclass
class Checkpoint:
    hop: int
    seed_query: str
    frontier: list[str]
    papers: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def bound(self, k: int = 8) -> "Checkpoint":
        return Checkpoint(
            hop=self.hop,
            seed_query=self.seed_query,
            frontier=self.frontier[-k:],
            papers=self.papers[-k:],
            edges=self.edges[-k:],
            open_questions=self.open_questions[-k:],
            notes=self.notes[:500],
            created_at=self.created_at,
        )


class HMem:
    def __init__(self, tree_id: str, store: Path = STORE) -> None:
        self.tree_id = _safe_id(tree_id)
        self.dir = store / self.tree_id
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, checkpoint: Checkpoint) -> Path:
        bounded = checkpoint.bound()
        path = self.dir / f"hop-{bounded.hop:03d}.json"
        path.write_text(json.dumps(asdict(bounded), indent=2), encoding="utf-8")
        latest = self.dir / "latest.json"
        latest.write_text(json.dumps(asdict(bounded), indent=2), encoding="utf-8")
        return path

    def load_latest(self) -> Checkpoint | None:
        path = self.dir / "latest.json"
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Checkpoint(**data)

    def history(self) -> list[Checkpoint]:
        items = []
        for path in sorted(self.dir.glob("hop-*.json")):
            items.append(Checkpoint(**json.loads(path.read_text(encoding="utf-8"))))
        return items


def _safe_id(tree_id: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in tree_id.lower())[:80]
    return text or "tree"
