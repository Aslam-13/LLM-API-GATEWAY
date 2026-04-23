from app.cache.keys import build_request_hash, last_user_message
from app.providers.schemas import Message, NormalizedRequest


def _req(content="hi", model="m", temp=0.5, top_p=None, max_tokens=None, roles=None):
    messages = [Message(role="user", content=content)]
    if roles:
        messages = [Message(role=r, content=c) for r, c in roles]
    return NormalizedRequest(
        model=model, messages=messages, temperature=temp,
        top_p=top_p, max_tokens=max_tokens,
    )


def test_hash_is_deterministic_across_runs():
    a = build_request_hash(_req())
    b = build_request_hash(_req())
    assert a == b and len(a) == 64


def test_hash_changes_on_any_field():
    base = build_request_hash(_req())
    assert build_request_hash(_req(content="hey")) != base
    assert build_request_hash(_req(model="m2")) != base
    assert build_request_hash(_req(temp=0.6)) != base
    assert build_request_hash(_req(max_tokens=1)) != base


def test_last_user_message_picks_most_recent_user_turn():
    req = _req(roles=[("user", "one"), ("assistant", "ok"), ("user", "two")])
    assert last_user_message(req) == "two"


def test_last_user_message_none_when_no_user_turn():
    req = _req(roles=[("system", "prelude"), ("assistant", "ok")])
    assert last_user_message(req) is None
