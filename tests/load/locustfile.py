"""
Load test for the LLM gateway — run AFTER deploy.

Traffic mix:
  - 60% chat completions (varied prompts, ~30% repeated → exercises cache)
  - 20% small-batch embeddings (sync)
  - 10% async batch embeddings (poll the job)
  - 10% admin reads (overview + keys)

Usage:
  # non-headless (web UI)
  locust -f tests/load/locustfile.py --host https://api.yourdomain.com

  # headless with explicit duration
  locust -f tests/load/locustfile.py --host https://api.yourdomain.com \
      --users 50 --spawn-rate 5 --run-time 10m --headless --csv results

Env vars:
  GATEWAY_API_KEY   — required, a non-admin key
  GATEWAY_ADMIN_KEY — optional, needed for /admin endpoints (gives 10% mix weight)
  CHAT_MODEL        — default "gemini-2.5-flash"
  EMBED_MODEL       — default "models/gemini-embedding-001"
  EMBED_PROVIDER    — default "gemini"
"""
from __future__ import annotations

import os
import random
import time
import uuid

from locust import HttpUser, between, task

CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-2.5-flash")
EMBED_MODEL = os.getenv("EMBED_MODEL", "models/gemini-embedding-001")
EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "gemini")

# ~15 seed prompts; each client picks from the same pool, so cache hits are inevitable
_PROMPTS = [
    "What is the capital of France?",
    "Tell me the capital of Germany.",
    "What year did World War II end?",
    "Summarise quicksort in three sentences.",
    "What is the speed of light in km/s?",
    "Explain HTTP/2 in one paragraph.",
    "Name three rivers in South America.",
    "Who painted the Mona Lisa?",
    "Write a haiku about databases.",
    "What is entropy?",
    "Compare SQL and NoSQL briefly.",
    "What is the boiling point of water on Everest?",
    "Summarise the theory of relativity.",
    "Define cosine similarity.",
    "What is the largest planet in our solar system?",
]


def _user_prompt() -> str:
    # 30% chance a brand-new prompt → forces provider call; else pool → caches benefit
    if random.random() < 0.3:
        return f"Random question {uuid.uuid4().hex[:8]}: what is two plus two?"
    return random.choice(_PROMPTS)


class GatewayUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        self.token = os.environ.get("GATEWAY_API_KEY")
        if not self.token:
            raise RuntimeError("GATEWAY_API_KEY env var is required")
        self.admin_token = os.environ.get("GATEWAY_ADMIN_KEY")
        self.client.headers.update({"Authorization": f"Bearer {self.token}"})

    # ---- chat: 60% ----
    @task(6)
    def chat(self):
        body = {
            "model": CHAT_MODEL,
            "messages": [{"role": "user", "content": _user_prompt()}],
        }
        with self.client.post(
            "/v1/chat/completions", json=body, name="/v1/chat/completions", catch_response=True
        ) as r:
            if r.status_code == 200:
                hit = r.json().get("x_cache_hit", "?")
                r.success()
                # emit custom event via request name suffix for filtering in CSV
                self.environment.events.request.fire(
                    request_type="META",
                    name=f"cache_hit:{hit}",
                    response_time=0,
                    response_length=0,
                    exception=None,
                    context={},
                )
            elif r.status_code == 429:
                r.success()  # rate-limit rejections are expected under load
            else:
                r.failure(f"{r.status_code} {r.text[:200]}")

    # ---- sync embeddings: 20% ----
    @task(2)
    def embed_sync(self):
        body = {"model": EMBED_MODEL, "input": [_user_prompt() for _ in range(5)]}
        with self.client.post(
            "/v1/embeddings", json=body, name="/v1/embeddings", catch_response=True
        ) as r:
            if r.status_code in (200, 429):
                r.success()
            else:
                r.failure(f"{r.status_code} {r.text[:200]}")

    # ---- batch embeddings + job poll: 10% ----
    @task(1)
    def embed_batch(self):
        body = {
            "model": EMBED_MODEL,
            "provider": EMBED_PROVIDER,
            "input": [f"doc {i}: " + random.choice(_PROMPTS) for i in range(20)],
        }
        r = self.client.post("/v1/embeddings/batch", json=body, name="/v1/embeddings/batch")
        if r.status_code != 202:
            return
        job_id = r.json().get("job_id")
        if not job_id:
            return
        # poll up to ~15s
        deadline = time.time() + 15
        while time.time() < deadline:
            jr = self.client.get(f"/v1/jobs/{job_id}", name="/v1/jobs/{id}")
            if jr.status_code == 200:
                st = jr.json().get("status")
                if st in ("succeeded", "failed"):
                    return
            time.sleep(1.0)

    # ---- admin reads: 10% (only if admin token configured) ----
    @task(1)
    def admin_overview(self):
        if not self.admin_token:
            return
        self.client.get(
            "/admin/stats/overview",
            name="/admin/stats/overview",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
