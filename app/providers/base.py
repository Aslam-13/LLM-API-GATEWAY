from __future__ import annotations

from abc import ABC, abstractmethod

from app.providers.schemas import NormalizedRequest, NormalizedResponse


class ProviderError(Exception):
    provider: str = "unknown"


class ProviderRateLimitError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderBadRequestError(ProviderError):
    pass


class ProviderAuthError(ProviderError):
    pass


class ProviderServerError(ProviderError):
    pass


class ProviderDisabledError(ProviderError):
    pass


class BaseProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def complete(self, req: NormalizedRequest) -> NormalizedResponse: ...

    @abstractmethod
    async def embed(self, texts: list[str], model: str) -> list[list[float]]: ...
