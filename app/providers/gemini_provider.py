from __future__ import annotations

import asyncio
import uuid

import google.generativeai as genai
from google.api_core import exceptions as gexc

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


class GeminiProvider(BaseProvider):
    name = "gemini"

    def __init__(self) -> None:
        settings = get_settings()
        genai.configure(api_key=settings.gemini_api_key)

    async def complete(self, req: NormalizedRequest) -> NormalizedResponse:
        system_instruction, contents = _convert_messages(req.messages)
        gen_config: dict = {}
        if req.temperature is not None:
            gen_config["temperature"] = req.temperature
        if req.max_tokens is not None:
            gen_config["max_output_tokens"] = req.max_tokens
        if req.top_p is not None:
            gen_config["top_p"] = req.top_p

        model = genai.GenerativeModel(
            model_name=req.model,
            system_instruction=system_instruction,
            generation_config=gen_config or None,
        )

        try:
            resp = await asyncio.to_thread(model.generate_content, contents)
        except gexc.ResourceExhausted as e:
            raise _wrap(ProviderRateLimitError, e) from e
        except gexc.DeadlineExceeded as e:
            raise _wrap(ProviderTimeoutError, e) from e
        except (gexc.Unauthenticated, gexc.PermissionDenied) as e:
            raise _wrap(ProviderAuthError, e) from e
        except gexc.InvalidArgument as e:
            raise _wrap(ProviderBadRequestError, e) from e
        except gexc.GoogleAPIError as e:
            raise _wrap(ProviderServerError, e) from e

        text = resp.text or ""
        usage = getattr(resp, "usage_metadata", None)
        finish = None
        if resp.candidates:
            fr = getattr(resp.candidates[0], "finish_reason", None)
            finish = str(fr) if fr is not None else None

        return NormalizedResponse(
            id=f"gemini-{uuid.uuid4().hex[:16]}",
            model=req.model,
            provider=self.name,
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content=text),
                    finish_reason=finish,
                )
            ],
            usage=Usage(
                prompt_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                completion_tokens=getattr(usage, "candidates_token_count", 0) or 0,
                total_tokens=getattr(usage, "total_token_count", 0) or 0,
            ),
        )

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        try:
            out: list[list[float]] = []
            for t in texts:
                r = await asyncio.to_thread(
                    genai.embed_content,
                    model=model,
                    content=t,
                    output_dimensionality=768,
                )
                out.append(r["embedding"])
            return out
        except gexc.ResourceExhausted as e:
            raise _wrap(ProviderRateLimitError, e) from e
        except gexc.DeadlineExceeded as e:
            raise _wrap(ProviderTimeoutError, e) from e
        except (gexc.Unauthenticated, gexc.PermissionDenied) as e:
            raise _wrap(ProviderAuthError, e) from e
        except gexc.InvalidArgument as e:
            raise _wrap(ProviderBadRequestError, e) from e
        except gexc.GoogleAPIError as e:
            raise _wrap(ProviderServerError, e) from e


def _convert_messages(messages: list[Message]) -> tuple[str | None, list[dict]]:
    system_parts: list[str] = []
    contents: list[dict] = []
    for m in messages:
        if m.role == "system":
            system_parts.append(m.content)
        else:
            role = "user" if m.role == "user" else "model"
            contents.append({"role": role, "parts": [m.content]})
    system_instruction = "\n".join(system_parts) if system_parts else None
    return system_instruction, contents


def _wrap(exc_cls: type[ProviderError], original: Exception) -> ProviderError:
    err = exc_cls(str(original))
    err.provider = "gemini"
    return err
