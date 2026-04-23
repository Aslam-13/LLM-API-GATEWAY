"""
End-to-end chat endpoint: auth gating, cache miss → exact hit, provider mocked.
"""
import pytest  # noqa: F401

from app.providers.schemas import (
    Choice,
    Message,
    NormalizedRequest,
    NormalizedResponse,
    Usage,
)


class MockRouter:
    def __init__(self):
        self.calls = 0

    async def complete(self, req: NormalizedRequest) -> NormalizedResponse:
        self.calls += 1
        return NormalizedResponse(
            id="mock-id",
            model=req.model,
            provider="mock",
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content="mocked answer"),
                    finish_reason="stop",
                )
            ],
            usage=Usage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
        )


BODY = {
    "model": "gpt-test",
    "messages": [{"role": "user", "content": "integration-test-hello"}],
}


@pytest.mark.asyncio
async def test_missing_auth_returns_401(client):
    r = await client.post("/v1/chat/completions", json=BODY)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_invalid_key_returns_403(client):
    r = await client.post(
        "/v1/chat/completions",
        json=BODY,
        headers={"Authorization": "Bearer sk-gw-live-" + "x" * 32},
    )
    assert r.status_code == 403


async def test_success_then_exact_cache_hit(client, test_key, monkeypatch):
    _, plaintext = test_key
    mock = MockRouter()
    monkeypatch.setattr("app.api.v1.chat.get_router", lambda: mock)
    headers = {"Authorization": f"Bearer {plaintext}"}

    r1 = await client.post("/v1/chat/completions", json=BODY, headers=headers)
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["provider"] == "mock"
    assert data1["x_cache_hit"] == "none"
    assert data1["choices"][0]["message"]["content"] == "mocked answer"

    r2 = await client.post("/v1/chat/completions", json=BODY, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["x_cache_hit"] == "exact"
    assert mock.calls == 1  # second served from Redis, not the provider


@pytest.mark.asyncio
async def test_validation_error_returns_422(client, test_key):
    _, plaintext = test_key
    r = await client.post(
        "/v1/chat/completions",
        json={"messages": []},  # missing model, empty messages
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r.status_code == 422
