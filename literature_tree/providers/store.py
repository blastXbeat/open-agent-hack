"""Persist Meterless settings. Token lives under meterless_runtime_token. Never log it."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from literature_tree.providers.urls import DEFAULT_BASE_URL, normalize_base_url, parse_connect_link

ROOT = Path(__file__).resolve().parent.parent.parent
SETTINGS_PATH = ROOT / "tmp" / "literature_tree" / "provider-settings.json"
TOKEN_KEY = "meterless_runtime_token"
PLACEHOLDER_TOKEN = "rt-local"
APP_ID = "literature-tree"


def settings_path() -> Path:
    return SETTINGS_PATH


def load_saved() -> dict[str, Any]:
    path = SETTINGS_PATH
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_saved(data: dict[str, Any]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2)
    SETTINGS_PATH.write_text(payload, encoding="utf-8")
    try:
        os.chmod(SETTINGS_PATH, 0o600)
    except OSError:
        pass


def meterless_block() -> dict[str, Any]:
    block = load_saved().get("meterless")
    return block if isinstance(block, dict) else {}


def save_meterless(*, base_url: str | None = None, token: str | None = None) -> None:
    data = load_saved()
    block = dict(data.get("meterless") or {})
    if base_url is not None:
        block["base_url"] = normalize_base_url(base_url)
    if token is not None:
        reject_placeholder(token)
        block[TOKEN_KEY] = token
    data["meterless"] = block
    save_saved(data)


def reject_placeholder(token: str | None) -> str:
    value = (token or "").strip()
    if not value or value == PLACEHOLDER_TOKEN:
        raise ValueError(
            f"Rejected placeholder token. Paste a real token into {TOKEN_KEY} "
            "(the runtime writes it to <stateDir>/proxy-token)."
        )
    return value


def read_proxy_token(state_dir: str | Path | None = None) -> str | None:
    for path in _proxy_token_paths(state_dir):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        text = lines[0].strip() if lines else ""
        if text and text != PLACEHOLDER_TOKEN:
            return text
    return None


def _usable(token: str | None) -> str | None:
    value = (token or "").strip()
    if not value or value == PLACEHOLDER_TOKEN:
        return None
    return value


def resolve_token(
    explicit: str | None = None,
    *,
    connect_text: str | None = None,
    state_dir: str | Path | None = None,
) -> str | None:
    if connect_text:
        link = parse_connect_link(connect_text, default_app=APP_ID)
        if link:
            return reject_placeholder(link.api_key)
    if explicit is not None and explicit != "":
        return reject_placeholder(explicit)
    env_token = os.environ.get("METERLESS_RUNTIME_TOKEN")
    if env_token:
        return reject_placeholder(env_token)
    for candidate in (
        meterless_block().get(TOKEN_KEY),
        read_proxy_token(state_dir or os.environ.get("METERLESS_STATE_DIR")),
    ):
        usable = _usable(str(candidate) if candidate is not None else None)
        if usable:
            return usable
    return None


def resolve_base_url(explicit: str | None = None, connect_text: str | None = None) -> str:
    if connect_text:
        link = parse_connect_link(connect_text, default_app=APP_ID)
        if link:
            return link.base_url
    if explicit:
        return normalize_base_url(explicit)
    env = (os.environ.get("METERLESS_BASE_URL") or "").strip()
    if env:
        return normalize_base_url(env)
    stored = (meterless_block().get("base_url") or "").strip()
    if stored:
        return normalize_base_url(stored)
    return DEFAULT_BASE_URL


def apply_connect_or_url(text: str) -> tuple[str, str | None]:
    """Paste a connect link or a base URL. Never log `text`."""
    link = parse_connect_link(text, default_app=APP_ID)
    if link:
        save_meterless(base_url=link.base_url, token=link.api_key)
        return link.base_url, link.api_key
    base = normalize_base_url(text)
    save_meterless(base_url=base)
    return base, None


def _proxy_token_paths(state_dir: str | Path | None) -> list[Path]:
    paths: list[Path] = []
    if state_dir:
        paths.append(Path(state_dir) / "proxy-token")
    env_dir = os.environ.get("METERLESS_STATE_DIR")
    if env_dir:
        paths.append(Path(env_dir) / "proxy-token")
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        paths.append(Path(xdg) / "meterless" / "proxy-token")
    home = Path.home()
    paths.extend(
        [
            home / ".local" / "state" / "meterless" / "proxy-token",
            home / ".meterless" / "proxy-token",
            home / "Library" / "Application Support" / "Meterless" / "proxy-token",
        ]
    )
    appdata = os.environ.get("APPDATA")
    if appdata:
        paths.append(Path(appdata) / "Meterless" / "proxy-token")
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique
