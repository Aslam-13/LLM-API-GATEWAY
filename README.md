# LLM API Gateway

A drop-in OpenAI-compatible proxy for multiple LLM providers, with multi-layer caching,
provider fallback, per-key rate limiting, and a built-in admin dashboard.

> **TL;DR.** Point your existing OpenAI SDK at this gateway. Get caching, fallback,
> rate limits, and cost tracking with **zero code changes**. 65% cache hit rate on
> realistic traffic → ~100× faster on cached requests → zero failures under load.

---

## What it is

```
your app ──▶ ┌────────────────────────────────────┐
            │  LLM API Gateway                    │
            │                                     │
            │  auth → ratelimit → exact cache  ───┼─▶ Redis
            │                  ↓                  │
            │              semantic cache  ───────┼─▶ pgvector (Postgres)
            │                  ↓                  │
            │              router (fallback) ─────┼─▶ Gemini  (primary)
            │                                     ├─▶ OpenAI  (fallback)
            └────────────────────────────────────┘
                              │
                              ▼
                          UsageLog (Postgres) → /admin/stats
```

Same OpenAI request/response shape on the way in. Gateway figures out the rest.

---

## Live demo

| | URL |
|---|---|
| **Dashboard** | `https://<codespace>-80.app.github.dev` |
| **API base**  | `https://<codespace>-80.app.github.dev/v1` |
| **Health**    | `https://<codespace>-80.app.github.dev/health` |

Hosted on GitHub Codespaces; demo environment is started on demand. Ping me before
trying — codespace sleeps after 30 min idle.

Public test API key (rate-limited, swap in your own when running locally):
`sk-gw-live-...` — request via [issues](../../issues/new) or replace with your own.

---

## Why use this

LLM SDKs handle one provider. This gateway adds the things every team ends up
building themselves:

- **Multi-provider, one API.** Same code calls Gemini, OpenAI, or anything
  OpenAI-shape-compatible. Switch providers without changing client code.
- **Caching that actually saves money.** Two layers stack: exact-match Redis
  cache (~10ms) and semantic pgvector cache (~450ms). 65% of typical traffic
  never touches an LLM provider.
- **Failover.** Primary provider down or rate-limited? Retries with exponential
  backoff, then transparently switches to the next configured provider.
- **Per-key auth + rate limiting.** Issue different keys per team/user, rate-limit
  per key (per-minute + per-day windows), revoke any time. Provider keys stay
  hidden behind your gateway keys.
- **Cost & usage observability.** Every request logged — provider, model, tokens,
  cost, latency, cache layer. Dashboard surfaces p50/p95/p99 latency, cost-by-key,
  cache hit rate, errors, rate-limit rejections. All from SQL over a single
  `usage_logs` table — no separate time-series store.
- **Async batch jobs.** `/v1/embeddings/batch` queues work via Celery + RabbitMQ
  for large embedding workloads.

This is the same pattern run by **Helicone, Portkey, OpenRouter, LiteLLM, Kong AI
Gateway, Cloudflare AI Gateway** — proven category, proven demand.

---

## Drop-in OpenAI SDK example

The whole point. Existing code keeps working — only the `base_url` changes.

### Python

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-gw-live-YOUR-GATEWAY-KEY",
    base_url="https://<codespace>-80.app.github.dev/v1",   # not api.openai.com
)

resp = client.chat.completions.create(
    model="gemini-2.5-flash",                              # or any routed model
    messages=[{"role": "user", "content": "What is the capital of France?"}],
)
print(resp.choices[0].message.content)
```

### Node.js

```ts
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "sk-gw-live-YOUR-GATEWAY-KEY",
  baseURL: "https://<codespace>-80.app.github.dev/v1",
});

const r = await client.chat.completions.create({
  model: "gemini-2.5-flash",
  messages: [{ role: "user", content: "What is the capital of France?" }],
});
```

### LangChain (Python)

```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(
    model="gemini-2.5-flash",
    api_key="sk-gw-live-YOUR-GATEWAY-KEY",
    base_url="https://<codespace>-80.app.github.dev/v1",
)
```

### curl

```bash
curl -X POST https://<codespace>-80.app.github.dev/v1/chat/completions \
  -H "Authorization: Bearer sk-gw-live-YOUR-GATEWAY-KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-2.5-flash","messages":[{"role":"user","content":"hi"}]}'
```

Response includes two extra fields beyond OpenAI's spec — useful for debugging:

```json
{
  "id": "...",
  "model": "gemini-2.5-flash",
  "provider": "gemini",
  "x_request_id": "...",
  "x_cache_hit": "exact",       // none | exact | semantic
  "choices": [...],
  "usage": {...}
}
```

---

## Results (measured)

3-minute Locust load test, 5 concurrent users, mixed traffic
(60% chat, 20% sync embed, 10% async batch + poll, 10% admin reads),
running against a 2-vCPU GitHub Codespace.

### Per-cache-layer latency (458 successful chat completions)

| Layer                | Hits      | Share | Avg latency  | p50 latency | p95 latency |
|----------------------|-----------|-------|--------------|-------------|-------------|
| Exact (Redis)        | 253       | 55%   | **13 ms**    | **1 ms**    | 109 ms      |
| Semantic (pgvector)  | 47        | 10%   | 462 ms       | 439 ms      | 569 ms      |
| Miss → provider      | 158       | 35%   | 1,294 ms     | 1,174 ms    | 2,007 ms    |

**Headline:**
- **65% cache hit rate** out of the box — eliminates two thirds of paid LLM calls.
- **~100× faster** average on Redis cache hits vs direct provider (13ms vs 1294ms).
- **~1,000× faster** at p50 — typical cached request is *one* millisecond.
- **0 failures** under sustained ~3.7 RPS load, despite Gemini's free-tier
  rate limits — caching absorbed the burst.

Reproduce: see [`tests/load/locustfile.py`](tests/load/locustfile.py) and
[`tests/README.md`](tests/README.md#load-post-deploy-not-part-of-ci).

---

## Features

| | |
|---|---|
| **OpenAI-compatible API** | Same request/response shape; existing OpenAI SDK works unchanged. |
| **Multi-provider routing** | Gemini + OpenAI today (Anthropic stub, disable-flagged for v1). Per-call `model`. Configurable fallback order. |
| **Exact-match cache** | SHA256 of `(model, messages, temperature, top_p, max_tokens)` → Redis with TTL. ~10ms hit. |
| **Semantic cache** | Embed last user turn → pgvector cosine search (HNSW). Tunable similarity threshold. ~450ms hit, still saves the chat-completion call. |
| **Failover with retry** | tenacity-driven exponential backoff per provider, then fall over to next. Auth/4xx errors marked fatal-no-fallback to avoid silently masking misconfigurations. |
| **Auth (Bearer keys)** | Argon2-hashed at rest. Admin / non-admin role. Soft-revoke. CLI + dashboard for management. |
| **Rate limiting** | Redis sliding-window counters; per-minute + per-day; per-key overrides via JSON column. 429 with `Retry-After`. Cache hits still count. |
| **Async batch jobs** | `/v1/embeddings/batch` enqueues via Celery to RabbitMQ; result polled via `/v1/jobs/{id}`. |
| **Usage logging** | Every request → row in `usage_logs` (provider, model, tokens, cost USD, latency, cache layer, status). |
| **Cost attribution** | Per-key, per-provider, daily. Estimated from a `PROVIDER_PRICING` table. |
| **Admin dashboard** | React + Vite + Tailwind + TanStack Query + Recharts. Login, key management, paginated usage explorer, async-job inspector, ops charts (latency p50/p95/p99, errors+rate-limits, tokens by provider, cost by key). |
| **Prometheus `/metrics`** | Standard text format. Scrape-able from any Prometheus or compatible tool. No Prometheus server required to operate the gateway. |
| **Migrations** | Alembic; pgvector extension auto-installed; embedding column dim selectable per provider (768 for Gemini, 1536 for OpenAI). |

---

## Quickstart (clone & run locally)

Requires: Python 3.11, Node 22+, Docker.

```bash
git clone https://github.com/<you>/LLM-API-GATEWAY
cd LLM-API-GATEWAY

# 1. infra (Postgres + pgvector, Redis, RabbitMQ)
docker compose -f docker-compose.dev.yml up -d

# 2. backend
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env                    # fill in GEMINI_API_KEY at minimum
.venv/bin/alembic upgrade head
PYTHONPATH=. .venv/bin/python -m uvicorn app.main:app --reload

# 3. worker (separate terminal)
PYTHONPATH=. .venv/bin/celery -A app.worker.celery_app worker --pool=solo

# 4. dashboard (separate terminal)
cd dashboard && npm install && npm run dev

# 5. issue an admin key
PYTHONPATH=. python scripts/create_api_key.py --admin --name me
```

- API: http://localhost:8000
- Dashboard: http://localhost:5173 (paste the printed admin key)

### Run as a single deployable stack (production-style)

```bash
cp .env.prod.example .env.prod          # fill in real keys
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec api \
  python scripts/create_api_key.py --admin --name me
```

Open http://localhost (port 80, served by the included nginx → React + reverse-proxied API).

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      web (nginx)                             │
│  serves dashboard SPA + reverse-proxies /v1, /admin, /health │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────┐  ┌────────────────────┐  ┌────────────────┐
│  api (FastAPI)     │  │  worker (Celery)   │  │ migrate (one-  │
│  gunicorn x N      │  │  prefork x N       │  │ shot, alembic) │
└─┬───────────┬───┬──┘  └──┬─────────────────┘  └─┬──────────────┘
  │           │   │        │                      │
  │           │   │        │                      │
  ▼           ▼   ▼        ▼                      ▼
┌───────┐  ┌─────┐  ┌────────────────────┐  ┌──────────────────┐
│Postgres│  │Redis│  │RabbitMQ (broker)   │  │ Postgres (same)  │
│+pgvect.│  │     │  │                    │  │                  │
└───────┘  └─────┘  └────────────────────┘  └──────────────────┘
   │          │            │
   │          │            │
 usage_logs   exact-cache  task queue
 cached_resp  rate-limit
 semantic_*   windows
 jobs
 api_keys
```

Every service auto-restarts (`unless-stopped`). `migrate` runs once via
`service_completed_successfully` dependency, then `api`/`worker` start.

---

## Tech-choice rationale

| Choice | Why |
|---|---|
| **FastAPI** | Async-first, type-driven validation, OpenAPI spec free, fast. |
| **SQLAlchemy 2.0 async + asyncpg** | Async DB access without ceremony, mature ecosystem. |
| **Postgres + pgvector** | Avoids a separate vector DB. One service, one backup story, one query language. |
| **Redis** | Right tool for the exact-match cache + rate-limit windows. Sub-ms reads. |
| **RabbitMQ + Celery** | Standard durable async-task setup. Retries, prefork concurrency, dead-lettering ready. |
| **Argon2 (passlib)** | Memory-hard hash; resistant to GPU brute-force. |
| **structlog** | JSON in prod, console in dev; bound contextvars per request (`request_id`, `api_key_id`). |
| **prometheus_client** | Standard `/metrics` text format. Zero-cost to expose; scrape if/when needed. |
| **React + Vite + Tailwind** | Fast dev server, hot reload, minimal config. Boring & fast. |
| **TanStack Query** | Server state + auto-refresh; covers what Redux/Zustand would otherwise do for free. |
| **Recharts** | Lightweight, React-native chart components. |
| **GitHub Codespaces** | Free demo environment. SSL + edge fronted by GitHub. No VPS or DNS to manage. |

### Deliberately *not* in v1

- **Streaming responses** — adds complexity in cache + accounting layer. v1.5 feature.
- **Multi-tenant / orgs / billing** — internal-tool framing for v1; v2 if it ever pivots to SaaS.
- **Local Grafana + Prometheus servers** — replaced by SQL-over-Postgres dashboards. The same `/metrics` endpoint stays exposed for external scrapers when scale demands.
- **Custom embedder per provider** — single embedder for the semantic cache (one vector space). Currently Gemini `text-embedding-001` (768 dim).
- **Anthropic provider** — wired as a stub, hidden behind `ENABLE_ANTHROPIC=false`.

---

## Project structure

```
LLM-API-GATEWAY/
├── app/                          FastAPI backend
│   ├── main.py                   ASGI entry, CORS, /health, /metrics, router mounting
│   ├── config.py                 pydantic-settings; loads .env
│   ├── logging.py                structlog config
│   ├── deps.py                   shared dependencies (get_router, get_embedder)
│   ├── api/
│   │   ├── v1/                   chat, embeddings (sync + batch), jobs
│   │   └── admin/                keys, usage, stats (5 charts), jobs
│   ├── auth/                     argon2 hashing + middleware
│   ├── cache/                    exact (Redis) + semantic (pgvector)
│   ├── providers/                base / openai / gemini / anthropic-stub / router (retry+fallback) / pricing
│   ├── ratelimit/                Redis sliding-window
│   ├── metrics/                  prometheus_client counters & histograms
│   ├── worker/                   Celery app + tasks (batch_embeddings)
│   └── db/                       SQLAlchemy models + session factory
├── alembic/versions/             schema migrations
├── dashboard/                    React + Vite admin UI (5 pages)
├── docker/                       Dockerfile (multi-stage, role-branched entrypoint)
├── nginx/prod.conf               reverse-proxy + SPA fallback
├── docker-compose.dev.yml        local infra only (db/cache/queue)
├── docker-compose.prod.yml       full stack: api + worker + web + db/cache/queue + migrate
├── .devcontainer/                GitHub Codespaces config
├── .github/workflows/            CI (ruff + alembic + pytest + dashboard build) + image publish
├── scripts/                      create_api_key.py, deploy.sh
└── tests/
    ├── unit/                     pure-function tests (cache hash, auth, pricing, router)
    ├── integration/              end-to-end with mocked providers (chat auth + cache flow)
    └── load/locustfile.py        post-deploy load test
```

---

## API surface

### Public

| Method + path                       | Auth   | Purpose |
|------------------------------------|--------|---------|
| `POST /v1/chat/completions`         | Bearer | OpenAI-shaped chat. Cached → routed → logged. |
| `POST /v1/embeddings`               | Bearer | Sync embeddings (≤100 inputs). |
| `POST /v1/embeddings/batch`         | Bearer | Async batch via Celery; returns `{job_id, status}`. |
| `GET  /v1/jobs/{id}`                | Bearer | Poll batch job status + result. |
| `GET  /health`                      | none   | Liveness probe. |
| `GET  /metrics`                     | none   | Prometheus text format. |

### Admin (require admin key)

| Method + path                       | Purpose |
|------------------------------------|---------|
| `GET  /admin/me`                    | Verify admin token / echo profile. |
| `GET  /admin/keys`                  | List all keys + last_used_at. |
| `POST /admin/keys`                  | Create key (returns plaintext **once**). |
| `DELETE /admin/keys/{id}`           | Soft revoke. |
| `GET  /admin/usage`                 | Paginated usage rows + aggregates + daily series. |
| `GET  /admin/stats/overview`        | 24h totals + cache breakdown + 1h RPS series + 24h hourly cache series. |
| `GET  /admin/stats/latency`         | 24h hourly p50/p95/p99 (success only). |
| `GET  /admin/stats/errors`          | 24h hourly errors + rate-limited counts. |
| `GET  /admin/stats/tokens`          | 7d daily tokens stacked by provider. |
| `GET  /admin/stats/cost-by-key`     | Top-10 keys by 7d cost. |
| `GET  /admin/stats/rate-limits`     | 24h hourly rate-limit rejections. |
| `GET  /admin/jobs`                  | Paginated job list with filtering. |

---

## Tests

```bash
# unit (no infra)
pytest tests/unit -q

# integration (needs docker-compose.dev.yml up)
pytest tests/integration -q

# both
pytest -q
```

CI runs ruff + alembic + pytest + dashboard build on every push/PR.
See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

Load test: see [`tests/README.md`](tests/README.md).

---

## CI / CD

- **`ci.yml`** — every push/PR: lint (ruff), apply migrations against ephemeral
  Postgres+Redis, run pytest, build dashboard. ~2 minutes.
- **`publish.yml`** — every merge to `main`: builds and pushes
  `gateway-api` and `gateway-web` images to GHCR (`ghcr.io/<owner>/<repo>/...`)
  tagged with the git SHA + `latest`. Cached via GHA build cache; ~2 min on warm cache.
- **`scripts/deploy.sh`** — one-command pull + rebuild on the target host
  (Codespace today; SSH-able VPS once one's available).

---

## Roadmap

### v1.5

- Streaming responses (`text/event-stream`) — passthrough from provider, with
  caching populated post-stream.
- GitHub Models adapter — same OpenAI-compatible base URL with custom auth, lets
  the gateway use GitHub PATs as an OpenAI-shaped provider.

### v2

- Multi-tenant / orgs / per-org provider credentials (BYO keys).
- PII redaction modes & per-request `cache: false`.
- Per-org cache scoping.
- Stripe billing for managed-key tier.
- VPS-targeted CI deploy job (10-line `appleboy/ssh-action`).

---

## License

MIT.
