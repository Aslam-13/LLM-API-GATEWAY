from __future__ import annotations

from app.providers.base import BaseProvider, ProviderDisabledError
from app.providers.schemas import NormalizedRequest, NormalizedResponse


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    async def complete(self, req: NormalizedRequest) -> NormalizedResponse:
        raise ProviderDisabledError("anthropic provider disabled in v1")

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        raise ProviderDisabledError("anthropic provider disabled in v1")
