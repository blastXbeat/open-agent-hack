"""Read-only Zetaris REST tools for the literature corpus.

Every POST to /sql-editor/sqls/run sends Bearer auth, X-Org-ID, and a fresh
UUID X-Request-ID. SQL is Lightning SQL: one statement, no trailing semicolon.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from literature_tree.config import Settings, load_settings, require_zetaris

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import zetaris_sql as zetaris_sql  # noqa: E402

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,5}$")


@dataclass
class QueryResult:
    rows: list[list[Any]]
    columns: list[str] | None = None


class ZetarisTools:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        require_zetaris(self.settings)
        self._channel = zetaris_sql.RestChannel()

    def run_sql(self, sql: str) -> QueryResult:
        statement = sql.strip().rstrip(";")
        if not statement:
            raise zetaris_sql.ZetarisError("Empty SQL")
        if ";" in statement:
            raise zetaris_sql.ZetarisError("One Lightning SQL statement per call")
        result = self._channel.run(statement, limit=self.settings.query_limit)
        return QueryResult(rows=result.rows)

    def datasources(self) -> Any:
        return self._channel.datasources()

    def select_one(self) -> bool:
        return self.run_sql("SELECT 1").rows == [["1"]]

    def list_lightning_databases(self) -> list[str]:
        return [str(row[0]) for row in self.run_sql("SHOW LIGHTNING DATABASES").rows if row]

    def show_tables(self, database: str) -> list[str]:
        name = _qualified(database)
        rows = self.run_sql(f"SHOW TABLES IN {name}").rows
        return [str(row[0]) for row in rows if row]

    def describe_table(self, table: str) -> list[list[Any]]:
        return self.run_sql(f"DESCRIBE {_qualified(table)}").rows

    def fetch_papers(self, query: str, table: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
        qualified = table or self.settings.papers_table
        if not qualified:
            return []
        needle = _like(query)
        sql = (
            f"SELECT * FROM {_qualified(qualified)} "
            f"WHERE CAST(title AS STRING) LIKE {needle} "
            f"OR CAST(abstract AS STRING) LIKE {needle} "
            f"LIMIT {int(limit)}"
        )
        return _as_maps(self.run_sql(sql).rows)

    def fetch_citations(self, paper_id: str, table: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        qualified = table or self.settings.citations_table
        if not qualified:
            return []
        pid = _literal(paper_id)
        sql = (
            f"SELECT * FROM {_qualified(qualified)} "
            f"WHERE CAST(src_paper_id AS STRING) = {pid} "
            f"OR CAST(dst_paper_id AS STRING) = {pid} "
            f"LIMIT {int(limit)}"
        )
        return _as_maps(self.run_sql(sql).rows)

    def fetch_abstracts(self, paper_ids: list[str], table: str | None = None) -> list[dict[str, Any]]:
        qualified = table or self.settings.papers_table
        if not qualified or not paper_ids:
            return []
        ids = ", ".join(_literal(pid) for pid in paper_ids[:50])
        sql = (
            f"SELECT * FROM {_qualified(qualified)} "
            f"WHERE CAST(paper_id AS STRING) IN ({ids})"
        )
        return _as_maps(self.run_sql(sql).rows)


def _qualified(name: str) -> str:
    if not IDENT.fullmatch(name):
        raise ValueError(f"Refusing non-identifier SQL name: {name!r}")
    return name


def _literal(value: str) -> str:
    cleaned = value.replace("\x00", "")[:200]
    return "'" + cleaned.replace("'", "''") + "'"


def _like(value: str) -> str:
    cleaned = value.replace("\x00", "")[:200].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "'%" + cleaned.replace("'", "''") + "%'"


def _as_maps(rows: list[list[Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(row)
        else:
            out.append({f"c{i}": cell for i, cell in enumerate(row)})
    return out
