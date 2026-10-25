"""Meterless Runtime provider (OpenAI-compatible, provider contract v4)."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from literature_tree.providers.base import OFFLINE, ONLINE, UNAUTHORIZED, ProviderStatus
from literature_tree.providers.store import (
    APP_ID,
    TOKEN_KEY,
    apply_connect_or_url,
    resolve_base_url,
    resolve_token,
    save_meterless,
)
from literature_tree.providers.urls import (
    DETECT_HOSTS,
    DETECT_PORTS,
    models_url,
    normalize_base_url,
)

DEFAULT_MODEL = "meterless/auto"
REQUEST_TIMEOUT = 180
DETECT_TIMEOUT = 2


class MeterlessProvider:
    id = "meterless"
    name = "Meterless Runtime"

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        state_dir: str | os.PathLike[str] | None = None,
        timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        self.base_url = resolve_base_url(base_url)
        self.token = resolve_token(token, state_dir=state_dir)
        self.state_dir = state_dir
        self.timeout = timeout

    def status(self) -> ProviderStatus:
        code, payload = self._get_models(timeout=min(self.timeout, 5))
        if code in (401, 403):
            return ProviderStatus(
                id=self.id,
                name=self.name,
                state=UNAUTHORIZED,
                base_url=self.base_url,
                paste_token_field=TOKEN_KEY,
                detail="Paste a valid Meterless Runtime token.",
            )
        if code != 200:
            return ProviderStatus(
                id=self.id,
                name=self.name,
                state=OFFLINE,
                base_url=self.base_url,
                detail="Meterless Runtime did not return a successful models response.",
            )
        model_ids = _meterless_model_ids(payload)
        if not model_ids:
            return ProviderStatus(
                id=self.id,
                name=self.name,
                state=OFFLINE,
                base_url=self.base_url,
                detail="The models response did not contain any meterless/* routing ids.",
            )
        return ProviderStatus(
            id=self.id,
            name=self.name,
            state=ONLINE,
            base_url=self.base_url,
            models=tuple(model_ids),
        )

    @classmethod
    def from_connection_input(
        cls,
        text: str,
        *,
        state_dir: str | os.PathLike[str] | None = None,
    ) -> MeterlessProvider:
        base_url, token = apply_connect_or_url(text)
        return cls(base_url=base_url, token=token, state_dir=state_dir)

    def list_models(self) -> list[str]:
        code, payload = self._get_models(timeout=min(self.timeout, 5))
        if code in (401, 403):
            raise PermissionError("Meterless Runtime rejected the token.")
        if code != 200:
            raise ConnectionError("Could not read Meterless Runtime models.")
        return _meterless_model_ids(payload)

    def complete(
        self,
        prompt: str | list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        if not self.token:
            raise RuntimeError(
                f"Set a real Meterless token in {TOKEN_KEY} or the runtime proxy-token file."
            )
        messages = [{"role": "user", "content": prompt}] if isinstance(prompt, str) else prompt
        body = json.dumps(
            {
                "model": model or os.environ.get("METERLESS_MODEL") or DEFAULT_MODEL,
                "messages": messages,
                "temperature": temperature,
            }
        ).encode("utf-8")
        request = Request(
            normalize_base_url(self.base_url) + "/chat/completions",
            data=body,
            headers=self._headers(chat=True),
            method="POST",
        )
        code, payload = _request_json(request, timeout=self.timeout)
        if code in (401, 403):
            raise PermissionError("Meterless Runtime rejected the token.")
        if code != 200:
            raise ConnectionError(f"Meterless Runtime chat request failed with HTTP {code}.")
        try:
            content: Any = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError("Meterless Runtime returned an invalid chat response.") from error
        if content is None:
            return ""
        if not isinstance(content, str):
            raise ValueError("Meterless Runtime returned non-text chat content.")
        return content

    @classmethod
    def auto_detect(
        cls,
        token: str | None = None,
        *,
        state_dir: str | os.PathLike[str] | None = None,
        timeout: float = DETECT_TIMEOUT,
    ) -> ProviderStatus | None:
        for host in DETECT_HOSTS:
            for port in DETECT_PORTS:
                base_url = f"http://{host}:{port}/v1"
                provider = cls(
                    base_url=base_url,
                    token=token,
                    state_dir=state_dir,
                    timeout=timeout,
                )
                result = provider.status()
                if result.state in (ONLINE, UNAUTHORIZED):
                    save_meterless(base_url=base_url)
                    return result
        return None

    def _headers(self, *, chat: bool = False) -> dict[str, str]:
        headers = {"meterless-app": APP_ID}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if chat:
            headers["meterless-scope"] = "user"
            headers["Content-Type"] = "application/json"
        return headers

    def _get_models(self, *, timeout: float) -> tuple[int, dict[str, Any] | None]:
        request = Request(models_url(self.base_url), headers=self._headers(), method="GET")
        return _request_json(request, timeout=timeout)


def _request_json(
    request: Request, *, timeout: float
) -> tuple[int, dict[str, Any] | None]:
    try:
        with _open_without_redirects(request, timeout=timeout) as response:
            code = response.status
            raw = response.read()
    except HTTPError as error:
        return error.code, None
    except (URLError, OSError, TimeoutError):
        return 0, None
    if code != 200:
        return code, None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return code, None
    return code, payload if isinstance(payload, dict) else None


def _open_without_redirects(request: Request, *, timeout: float):
    class NoRedirectHandler(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            _ = req, fp, code, msg, headers, newurl
            return None

    return build_opener(NoRedirectHandler).open(request, timeout=timeout)


def _meterless_model_ids(payload: dict[str, Any] | None) -> list[str]:
    if not payload:
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    result: list[str] = []
    for item in data:
        if isinstance(item, dict):
            model_id = item.get("id")
            if isinstance(model_id, str) and model_id.startswith("meterless/"):
                result.append(model_id)
    return result
