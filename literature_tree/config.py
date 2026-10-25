"""Load `.env.local` only (never `.env`) and expose Zetaris + model settings.

Secrets stay in the environment. This module never prints values.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import zetaris_sql as zetaris_sql  # noqa: E402

PLACEHOLDER = re.compile(r"^<.*>$|^YOUR_|CHANGE_ME|changeme", re.I)


@dataclass(frozen=True)
class Settings:
    env_file: Path | None
    zetaris_rest_url: str
    zetaris_org_id: str
    zetaris_api_key_set: bool
    model_base_url: str | None
    model_api_key_set: bool
    nemotron_model: str | None
    papers_table: str | None
    citations_table: str | None
    query_limit: int


def load_settings() -> Settings:
    env_file = zetaris_sql.load_env()
    return Settings(
        env_file=env_file,
        zetaris_rest_url=os.environ.get("ZETARIS_REST_URL", zetaris_sql.DEFAULT_REST_URL).rstrip("/"),
        zetaris_org_id=os.environ.get("ZETARIS_ORG_ID", "1"),
        zetaris_api_key_set=_present("ZETARIS_API_KEY"),
        model_base_url=_optional("MODEL_BASE_URL"),
        model_api_key_set=_present("MODEL_API_KEY"),
        nemotron_model=_optional("NEMOTRON_MODEL"),
        papers_table=_optional("LITERATURE_PAPERS_TABLE"),
        citations_table=_optional("LITERATURE_CITATIONS_TABLE"),
        query_limit=int(os.environ.get("ZETARIS_QUERY_LIMIT", "100")),
    )


def require_zetaris(settings: Settings) -> None:
    missing = []
    if not settings.zetaris_api_key_set:
        missing.append("ZETARIS_API_KEY")
    if not settings.zetaris_rest_url:
        missing.append("ZETARIS_REST_URL")
    if missing:
        raise RuntimeError(
            "Missing in .env.local: " + ", ".join(missing) + ". Do not put keys in source files."
        )


def model_ready(settings: Settings) -> bool:
    from literature_tree.providers.store import resolve_token

    meterless_token = resolve_token()
    return bool(
        meterless_token
        or (settings.model_base_url and settings.model_api_key_set and settings.nemotron_model)
    )


def _optional(name: str) -> str | None:
    value = (os.environ.get(name) or "").strip()
    if not value or PLACEHOLDER.match(value):
        return None
    return value


def _present(name: str) -> bool:
    return _optional(name) is not None
