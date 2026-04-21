from __future__ import annotations

import structlog
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import (
    BaseProvider,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderDisabledError,
    ProviderError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
)
from app.providers.gemini_provider import GeminiProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.schemas import NormalizedRequest, NormalizedResponse

log = structlog.get_logger(__name__)

# Retry transient failures, do not retry 4xx-ish categories.
_RETRYABLE = (ProviderRateLimitError, ProviderTimeoutError, ProviderServerError)
_FATAL = (ProviderAuthError, ProviderBadRequestError, ProviderDisabledError)


class ProviderRouter:
    def __init__(self, providers: dict[str, BaseProvider] | None = None, order: list[str] | None = None) -> None:
        settings = get_settings()
        if providers is None:
            providers = {"openai": OpenAIProvider(), "gemini": GeminiProvider()}
            if settings.enable_anthropic:
                providers["anthropic"] = AnthropicProvider()
        self._providers = providers
        self._order = order or settings.fallback_providers
        self._attempts = settings.provider_retry_attempts
        self._delay = settings.provider_retry_delay_seconds

    @property
    def order(self) -> list[str]:
        return list(self._order)

    async def complete(self, req: NormalizedRequest) -> NormalizedResponse:
        last_err: Exception | None = None
        for name in self._order:
            provider = self._providers.get(name)
            if provider is None:
                log.warning("provider.missing", provider=name)
                continue
            try:
                return await self._run_with_retry(provider, req)
            except _FATAL as e:
                log.warning("provider.fatal", provider=name, error=str(e))
                last_err = e
                break
            except ProviderError as e:
                log.warning("provider.exhausted", provider=name, error=str(e))
                last_err = e
                continue
        raise last_err or ProviderError("no providers configured")

    async def _run_with_retry(self, provider: BaseProvider, req: NormalizedRequest) -> NormalizedResponse:
        try:
            async for attempt in AsyncRetrying(
                reraise=True,
                stop=stop_after_attempt(self._attempts + 1),
                wait=wait_exponential(multiplier=self._delay, min=self._delay, max=self._delay * 8),
                retry=retry_if_exception_type(_RETRYABLE),
            ):
                with attempt:
                    log.info("provider.attempt", provider=provider.name, attempt=attempt.retry_state.attempt_number)
                    return await provider.complete(req)
        except RetryError as e:
            raise e.last_attempt.exception() or ProviderError("retry failed")
        raise ProviderError("unreachable")
