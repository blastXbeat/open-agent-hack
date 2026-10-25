"""Chat completion routing for Meterless Runtime and the existing Nemotron route.

Meterless credentials resolve from provider settings, environment, or the runtime
proxy-token file. The legacy Nemotron route uses MODEL_* settings.
"""

from __future__ import annotations

import os

from literature_tree.config import Settings
from literature_tree.providers.meterless import DEFAULT_MODEL, MeterlessProvider
from literature_tree.providers.store import resolve_token
from literature_tree.providers.nemotron import NemotronProvider


class ModelNotConfigured(RuntimeError):
    pass


def chat(settings: Settings, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
    token = resolve_token()
    if token:
        return MeterlessProvider(token=token).complete(
            messages,
            model=os.environ.get("METERLESS_MODEL") or DEFAULT_MODEL,
            temperature=temperature,
        )
    if not (
        settings.model_base_url and settings.model_api_key_set and settings.nemotron_model
    ):
        raise ModelNotConfigured(
            "Configure Meterless Runtime with a real token, or set MODEL_BASE_URL, "
            "MODEL_API_KEY, and NEMOTRON_MODEL in .env.local."
        )
    try:
        return NemotronProvider(settings).complete(messages, temperature=temperature)
    except ImportError as error:
        raise ModelNotConfigured(
            "Install openai in this environment: pip install -r literature_tree/requirements.txt"
        ) from error
