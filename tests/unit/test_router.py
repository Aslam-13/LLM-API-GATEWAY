import pytest

from app.providers.base import (
    BaseProvider,
    ProviderAuthError,
    ProviderServerError,
)
from app.providers.router import ProviderRouter
from app.providers.schemas import Choice, Message, NormalizedRequest, NormalizedResponse, Usage


def _req(content="hi"):
    return NormalizedRequest(
        model="x", messages=[Message(role="user", content=content)]
    )


def _ok_resp(provider_name: str) -> NormalizedResponse:
    return NormalizedResponse(
        id="id", model="x", provider=provider_name,
        choices=[Choice(index=0, message=Message(role="assistant", content="ok"), finish_reason="stop")],
        usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


class Server(BaseProvider):
    name = "p1"

    def __init__(self):
        self.calls = 0

    async def complete(self, req):
        self.calls += 1
        raise ProviderServerError("boom")

    async def embed(self, texts, model):
        raise NotImplementedError


class Auth(BaseProvider):
    name = "p1"

    async def complete(self, req):
        raise ProviderAuthError("bad key")

    async def embed(self, texts, model):
        raise NotImplementedError


class Ok(BaseProvider):
    name = "p2"

    async def complete(self, req):
        return _ok_resp(self.name)

    async def embed(self, texts, model):
        raise NotImplementedError


@pytest.mark.asyncio
async def test_retries_then_falls_over_to_next_provider(monkeypatch):
    # patch retry config to keep test fast
    monkeypatch.setenv("PROVIDER_RETRY_ATTEMPTS", "1")
    monkeypatch.setenv("PROVIDER_RETRY_DELAY_SECONDS", "0")
    from app.config import get_settings
    get_settings.cache_clear()

    failing, healthy = Server(), Ok()
    router = ProviderRouter(providers={"p1": failing, "p2": healthy}, order=["p1", "p2"])
    resp = await router.complete(_req())
    assert resp.provider == "p2"
    assert failing.calls >= 2  # retried then exhausted


@pytest.mark.asyncio
async def test_auth_error_is_fatal_no_fallback():
    auth_broken, healthy = Auth(), Ok()
    router = ProviderRouter(providers={"p1": auth_broken, "p2": healthy}, order=["p1", "p2"])
    with pytest.raises(ProviderAuthError):
        await router.complete(_req())


@pytest.mark.asyncio
async def test_all_retryable_exhausted_raises_last_error(monkeypatch):
    monkeypatch.setenv("PROVIDER_RETRY_ATTEMPTS", "0")
    monkeypatch.setenv("PROVIDER_RETRY_DELAY_SECONDS", "0")
    from app.config import get_settings
    get_settings.cache_clear()

    a, b = Server(), Server()
    router = ProviderRouter(providers={"a": a, "b": b}, order=["a", "b"])
    with pytest.raises(ProviderServerError):
        await router.complete(_req())
    assert a.calls >= 1 and b.calls >= 1
