from __future__ import annotations

import hashlib
import json

from app.providers.schemas import NormalizedRequest


def build_request_hash(req: NormalizedRequest) -> str:
    canonical = {
        "model": req.model,
        "messages": [{"role": m.role, "content": m.content} for m in req.messages],
        "temperature": req.temperature,
        "top_p": req.top_p,
        "max_tokens": req.max_tokens,
    }
    s = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def last_user_message(req: NormalizedRequest) -> str | None:
    for m in reversed(req.messages):
        if m.role == "user":
            return m.content
    return None
