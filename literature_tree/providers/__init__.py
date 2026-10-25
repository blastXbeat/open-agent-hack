"""OpenAI-compatible providers used by the literature tree agent.

Existing: Nemotron (cloud / Meterless-hosted model route).
Added: Meterless Runtime (local hotspot, contract v4).
"""

from __future__ import annotations

from literature_tree.providers.base import Provider, ProviderStatus
from literature_tree.providers.meterless import MeterlessProvider
from literature_tree.providers.nemotron import NemotronProvider

PROVIDERS: tuple[type[Provider], ...] = (MeterlessProvider, NemotronProvider)


def all_providers() -> list[Provider]:
    return [cls() for cls in PROVIDERS]


__all__ = [
    "MeterlessProvider",
    "NemotronProvider",
    "Provider",
    "ProviderStatus",
    "all_providers",
]
