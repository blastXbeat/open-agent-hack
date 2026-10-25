"""Pure URL helpers for Meterless Runtime. Never log connect links or keys."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

DEFAULT_BASE_URL = "http://127.0.0.1:8088/v1"
DETECT_HOSTS = ("127.0.0.1", "localhost", "[::1]")
DETECT_PORTS = (8088, 8090, 8787, 11434)
KNOWN_DISPOSITIONS = ("auto", "fast", "deep", "cheap", "local", "fusion")
STRIP_SUFFIXES = (
    "/v1/chat/completions",
    "/chat/completions",
    "/v1/models",
    "/models",
    "/healthz",
    "/v1",
)


@dataclass(frozen=True)
class ConnectLink:
    base_url: str
    api_key: str
    model: str
    app: str | None
    health_url: str


def parse_connect_link(text: str, default_app: str | None = None) -> ConnectLink | None:
    """A connect link is http(s), path /connect, fragment containing k.

    Anything else (including a pasted base URL) is not a failed link.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    path = parsed.path.rstrip("/") or "/"
    if path != "/connect":
        return None
    fragment = parse_qs(parsed.fragment, keep_blank_values=True)
    keys = fragment.get("k") or []
    if not keys or keys[0] == "":
        return None
    origin = f"{parsed.scheme}://{parsed.netloc}"
    model_values = fragment.get("m") or []
    app_values = fragment.get("n") or []
    return ConnectLink(
        base_url=origin + "/v1",
        api_key=unquote(keys[0]),
        model=unquote(model_values[0]) if model_values and model_values[0] else "meterless/auto",
        app=unquote(app_values[0]) if app_values and app_values[0] else default_app,
        health_url=origin + "/healthz",
    )


def normalize_base_url(raw: str | None) -> str:
    """Accept host, /v1, chat/completions, /models or /healthz. Return <origin>/v1."""
    text = (raw or "").strip()
    if not text:
        return DEFAULT_BASE_URL
    link = parse_connect_link(text)
    if link:
        return link.base_url
    if text.startswith("//"):
        text = "http:" + text
    elif "://" not in text:
        text = "http://" + text
    parsed = urlparse(text)
    if not parsed.netloc or parsed.scheme not in ("http", "https"):
        return DEFAULT_BASE_URL
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path or ""
    while True:
        lowered = path.lower()
        if lowered.endswith("/") and lowered != "/":
            lowered = lowered[:-1]
            path = path[:-1]
        matched = False
        for suffix in STRIP_SUFFIXES:
            if lowered.endswith(suffix):
                path = path[: len(path) - len(suffix)]
                matched = True
                break
        if not matched:
            break
    return origin + "/v1"


def origin_from_base(base_url: str) -> str:
    base = normalize_base_url(base_url)
    if base.endswith("/v1"):
        return base[:-3]
    return base


def healthz_url(base_url: str) -> str:
    return origin_from_base(base_url) + "/healthz"


def models_url(base_url: str) -> str:
    return normalize_base_url(base_url) + "/models"


def chat_url(base_url: str) -> str:
    return normalize_base_url(base_url) + "/chat/completions"
