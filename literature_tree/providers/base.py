"""Shared provider types. Status strings match the Meterless contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

ONLINE = "online"
UNAUTHORIZED = "unauthorized"
OFFLINE = "offline"


@dataclass(frozen=True)
class ProviderStatus:
    id: str
    name: str
    state: str  # online | unauthorized | offline
    base_url: str | None = None
    models: tuple[str, ...] = ()
    paste_token_field: str | None = None
    detail: str = ""


class Provider(Protocol):
    id: str
    name: str

    def status(self) -> ProviderStatus: ...

    def complete(
        self,
        prompt: str | list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> str: ...
