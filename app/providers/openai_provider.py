from __future__ import annotations

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

from app.config import get_settings
from app.providers.base import (
    BaseProvider,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
)
from app.providers.schemas import Choice, Message, NormalizedRequest, NormalizedResponse, Usage


class OpenAIProvider(BaseProvider):
    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def complete(self, req: NormalizedRequest) -> NormalizedResponse:
        payload: dict = {
            "model": req.model,
            "messages": [m.model_dump() for m in req.messages],
        }
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        if req.max_tokens is not None:
            payload["max_tokens"] = req.max_tokens
        if req.top_p is not None:
            payload["top_p"] = req.top_p
        if req.user is not None:
            payload["user"] = req.user

        try:
            resp = await self._client.chat.completions.create(**payload)
        except RateLimitError as e:
            raise _wrap(ProviderRateLimitError, e) from e
        except (APITimeoutError, APIConnectionError) as e:
            raise _wrap(ProviderTimeoutError, e) from e
        except AuthenticationError as e:
            raise _wrap(ProviderAuthError, e) from e
        except BadRequestError as e:
            raise _wrap(ProviderBadRequestError, e) from e
        except APIStatusError as e:
            raise _wrap(ProviderServerError, e) from e

        return NormalizedResponse(
            id=resp.id,
            model=resp.model,
            provider=self.name,
            choices=[
                Choice(
                    index=c.index,
                    message=Message(role=c.message.role, content=c.message.content or ""),
                    finish_reason=c.finish_reason,
                )
                for c in resp.choices
            ],
            usage=Usage(
                prompt_tokens=resp.usage.prompt_tokens if resp.usage else 0,
                completion_tokens=resp.usage.completion_tokens if resp.usage else 0,
                total_tokens=resp.usage.total_tokens if resp.usage else 0,
            ),
        )

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        try:
            resp = await self._client.embeddings.create(model=model, input=texts)
        except RateLimitError as e:
            raise _wrap(ProviderRateLimitError, e) from e
        except (APITimeoutError, APIConnectionError) as e:
            raise _wrap(ProviderTimeoutError, e) from e
        except AuthenticationError as e:
            raise _wrap(ProviderAuthError, e) from e
        except BadRequestError as e:
            raise _wrap(ProviderBadRequestError, e) from e
        except APIStatusError as e:
            raise _wrap(ProviderServerError, e) from e
        return [d.embedding for d in resp.data]


def _wrap(exc_cls: type[ProviderError], original: Exception) -> ProviderError:
    err = exc_cls(str(original))
    err.provider = "openai"
    return err
