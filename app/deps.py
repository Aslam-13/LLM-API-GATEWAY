from __future__ import annotations

from functools import lru_cache

from app.providers.base import BaseProvider
from app.providers.gemini_provider import GeminiProvider
from app.providers.router import ProviderRouter


@lru_cache
def get_router() -> ProviderRouter:
    return ProviderRouter()


@lru_cache
def get_embedder() -> BaseProvider:
    return GeminiProvider()
