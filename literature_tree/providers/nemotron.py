"""Existing OpenAI-compatible Nemotron provider."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from literature_tree.providers.base import OFFLINE, ONLINE, UNAUTHORIZED, ProviderStatus
from literature_tree.providers.meterless import _request_json
from literature_tree.providers.urls import models_url, normalize_base_url
from urllib.request import Request

if TYPE_CHECKING:
    from literature_tree.config import Settings


class NemotronProvider:
    id = "nemotron"
    name = "Nemotron"

    def __init__(self, settings: Settings | None = None) -> None:
        from literature_tree.config import load_settings

        self.settings = settings or load_settings()

    def status(self) -> ProviderStatus:
        base_url = self.settings.model_base_url
        if not base_url or not self.settings.model_api_key_set:
            return ProviderStatus(
                id=self.id,
                name=self.name,
                state=OFFLINE,
                base_url=base_url,
                detail="Set MODEL_BASE_URL and MODEL_API_KEY.",
            )
        from os import environ

        request = Request(
            models_url(normalize_base_url(base_url)),
            headers={"Authorization": f"Bearer {environ.get('MODEL_API_KEY', '')}"},
            method="GET",
        )
        code, payload = _request_json(request, timeout=5)
        if code in (401, 403):
            return ProviderStatus(
                id=self.id,
                name=self.name,
                state=UNAUTHORIZED,
                base_url=normalize_base_url(base_url),
                paste_token_field="MODEL_API_KEY",
                detail="The Nemotron endpoint rejected MODEL_API_KEY.",
            )
        models = payload.get("data", []) if payload else []
        model_ids = tuple(
            item["id"] for item in models
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ) if isinstance(models, list) else ()
        return ProviderStatus(
            id=self.id,
            name=self.name,
            state=ONLINE if code == 200 else OFFLINE,
            base_url=normalize_base_url(base_url),
            models=model_ids,
        )

    def complete(
        self,
        prompt: str | list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        from openai import OpenAI

        if not self.settings.model_base_url or not self.settings.nemotron_model:
            raise RuntimeError("Set MODEL_BASE_URL and NEMOTRON_MODEL.")
        import os

        key = os.environ.get("MODEL_API_KEY") or ""
        if not key:
            raise RuntimeError("MODEL_API_KEY is not set.")
        messages = [{"role": "user", "content": prompt}] if isinstance(prompt, str) else prompt
        client = OpenAI(
            base_url=normalize_base_url(self.settings.model_base_url),
            api_key=key,
            timeout=180,
        )
        response: Any = client.chat.completions.create(
            model=model or self.settings.nemotron_model,
            messages=messages,
            temperature=temperature,
        )
        content = response.choices[0].message.content
        if content is None:
            return ""
        if not isinstance(content, str):
            raise ValueError("Nemotron returned non-text chat content.")
        return content
