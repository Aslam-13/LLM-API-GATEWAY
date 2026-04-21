# LLM API Gateway — v1 Implementation Plan

**Stack (locked):** Python 3.11 · FastAPI · SQLAlchemy 2.0 async · Alembic · PostgreSQL + pgvector · Redis · RabbitMQ · Celery · Nginx · Docker Compose · structlog · Prometheus + Grafana · React + Vite (dashboard) · pytest

**Providers (v1):** OpenAI + Gemini. Anthropic wired but disabled.

**Deploy target:** Single VPS (Hetzner CX22 ~€4/mo, or DigitalOcean $6 droplet). Docker Compose + Nginx + Certbot TLS. Domain with subdomains: `api.yourdomain.com` (gateway) and `dashboard.yourdomain.com` (React app).

**Semantic caching:** IN for v1. Uses pgvector — no new service, just a Postgres extension. Cheap CV win because (a) ties the gateway to your Aelora embedding work, (b) measurably lifts cache hit rate in the README metrics, (c) demonstrates you know the difference between hash-match and semantic-match.

**Streaming responses:** OUT for v1. Adds real complexity in the cache + accounting layer. v1.5 feature.

---

## What semantic caching actually is (since you asked)

Exact-match cache: hash `(model + messages + temperature)` → if a byte-identical request comes in, serve the cached response. Fast, safe, but narrow — "What's the capital of France?" and "Tell me the capital of France" miss each other.

Semantic cache: embed the incoming user prompt → vector-search against past embedded prompts in pgvector → if cosine similarity > 0.97 (tunable), return the cached response from the match. Now both queries above share one cached answer.

Pipeline on every request: exact-match first (cheapest, ~1ms Redis lookup) → semantic-match second (~10–20ms pgvector query + one embedding call) → provider call last (~500–2000ms). Each layer catches what the layer above missed.

---

## Phase 0 — Prerequisites

Before writing any code, get these ready. Takes ~30 min.

1. **Python 3.11** — `winget install Python.Python.3.11` (or download from python.org). Confirm `python --version`.
2. **Docker Desktop** — already on your machine from TinyScale. Confirm `docker --version` and `docker compose version`.
3. **Git + GitHub** — create a new **public** repo `llm-gateway` (brand new, separate from TinyScale). Clone locally.
4. **API keys:**
   - OpenAI: https://platform.openai.com/api-keys — add $5 credit so calls actually work.
   - Gemini: https://aistudio.google.com/apikey — free tier is fine.
5. **Domain name** — buy a cheap domain for the demo. Namecheap/Cloudflare Registrar, ~$10/yr. You'll point subdomains at your VPS later. Don't skip this — "live link on a real domain" is worth the $10.
6. **VPS account** — sign up at Hetzner or DigitalOcean now so you can provision in ~5 min when Phase 17 arrives. Don't create the VPS yet.

---

## Phase 1 — Project scaffolding & venv

Working directory: wherever you keep code. On Windows, something like `C:\dev\llm-gateway`.

```powershell
cd C:\dev\llm-gateway
python -m venv .venv
.\.venv\Scripts\Activate.ps1    # PowerShell
# .\.venv\Scripts\activate.bat  # cmd
# source .venv/Scripts/activate # Git Bash
python -m pip install --upgrade pip
```

Create `requirements.txt`:

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
gunicorn==23.0.0
pydantic==2.9.2
pydantic-settings==2.5.2
sqlalchemy[asyncio]==2.0.35
asyncpg==0.29.0
alembic==1.13.3
pgvector==0.3.6
redis[hiredis]==5.1.1
celery[librabbitmq]==5.4.0
kombu==5.4.2
openai==1.54.3
google-generativeai==0.8.3
httpx==0.27.2
structlog==24.4.0
prometheus-client==0.21.0
python-jose[cryptography]==3.3.0
passlib[argon2]==1.7.4
python-multipart==0.0.12
tenacity==9.0.0
```

Create `requirements-dev.txt`:

```
-r requirements.txt
pytest==8.3.3
pytest-asyncio==0.24.0
pytest-cov==5.0.0
httpx==0.27.2
ruff==0.7.1
mypy==1.13.0
locust==2.32.1
```

Install:

```powershell
pip install -r requirements-dev.txt
```

Create `.gitignore` (Python + VSCode + Docker standard entries — search "gitignore python" and paste the GitHub template, add `.env`, `.venv/`, `dashboard/node_modules/`, `dashboard/dist/`).

---

## Phase 2 — Folder structure

Create this exact tree up front. Empty files are fine; they get filled in later phases.

```
llm-gateway/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entry
│   ├── config.py                # pydantic-settings
│   ├── logging.py               # structlog setup
│   ├── deps.py                  # FastAPI dependencies (db, redis, auth)
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py           # async engine + session
│   │   └── models.py            # SQLAlchemy models
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── chat.py          # /v1/chat/completions
│   │   │   ├── embeddings.py    # /v1/embeddings + /v1/embeddings/batch
│   │   │   └── jobs.py          # /v1/jobs/{id}
│   │   └── admin/
│   │       ├── __init__.py
│   │       ├── keys.py          # create/list/revoke API keys
│   │       └── usage.py         # usage stats for dashboard
│   │
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py              # BaseProvider interface
│   │   ├── openai_provider.py
│   │   ├── gemini_provider.py
│   │   ├── anthropic_provider.py  # stub, disabled via config
│   │   ├── router.py            # fallback + retry logic
│   │   └── schemas.py           # normalized request/response models
│   │
│   ├── cache/
│   │   ├── __init__.py
│   │   ├── exact.py             # Redis hash-match cache
│   │   ├── semantic.py          # pgvector similarity cache
│   │   └── keys.py              # key-building helpers
│   │
│   ├── ratelimit/
│   │   ├── __init__.py
│   │   └── sliding_window.py    # Redis-backed per-key limiter
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── keys.py              # hash, verify, lookup API keys
│   │   └── middleware.py        # FastAPI dependency
│   │
│   ├── metrics/
│   │   ├── __init__.py
│   │   └── prometheus.py        # counters, histograms
│   │
│   └── worker/
│       ├── __init__.py
│       ├── celery_app.py        # Celery factory
│       └── tasks.py             # batch embeddings, long jobs
│
├── alembic/
│   ├── env.py
│   ├── versions/
│   └── script.py.mako
├── alembic.ini
│
├── dashboard/                   # React + Vite app (Phase 13)
│   └── (scaffolded later)
│
├── nginx/
│   ├── nginx.conf               # dev (docker-compose)
│   └── prod.conf                # template for VPS (filled by certbot)
│
├── docker/
│   ├── Dockerfile               # multi-stage, shared by api + worker
│   └── entrypoint.sh
│
├── scripts/
│   ├── create_api_key.py        # CLI: python scripts/create_api_key.py
│   └── seed.py                  # demo data
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   └── integration/
│
├── grafana/
│   └── dashboards/
│       └── gateway.json         # prebuilt dashboard
│
├── docker-compose.dev.yml
├── docker-compose.prod.yml
├── .env.example
├── .env                         # git-ignored
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml               # ruff + pytest config
└── README.md
```

Create `.env.example` (this goes in git, no real secrets):

```dotenv
# App
APP_ENV=dev
APP_DEBUG=true
APP_SECRET_KEY=change-me-generate-with-secrets-token-urlsafe-32

# Database
POSTGRES_USER=gateway
POSTGRES_PASSWORD=gateway
POSTGRES_DB=gateway
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://gateway:gateway@localhost:5432/gateway

# Redis
REDIS_URL=redis://localhost:6379/0

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672//
CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# LLM Providers
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=
ENABLE_ANTHROPIC=false

# Cache
CACHE_TTL_SECONDS=3600
SEMANTIC_CACHE_ENABLED=true
SEMANTIC_CACHE_THRESHOLD=0.97
EMBEDDING_MODEL=text-embedding-3-small

# Rate limiting
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_REQUESTS_PER_DAY=10000

# Fallback
PROVIDER_FALLBACK_ORDER=openai,gemini
PROVIDER_RETRY_ATTEMPTS=2
PROVIDER_RETRY_DELAY_SECONDS=1
```

Copy to `.env` and fill in real keys.

Commit and push the scaffolding. `git commit -m "chore: project scaffolding"`.

---

## Phase 3 — Local infra via docker-compose

Goal: `docker compose -f docker-compose.dev.yml up -d` gives you Postgres (with pgvector), Redis, and RabbitMQ running locally. No app container yet — you'll run the app with `uvicorn` on your host for fast dev reloads.

Key things in `docker-compose.dev.yml`:
- Postgres image: `pgvector/pgvector:pg16` (Postgres + pgvector extension pre-installed)
- Redis image: `redis:7-alpine`
- RabbitMQ image: `rabbitmq:3.13-management` (the management UI is included — visit `http://localhost:15672`, guest/guest)
- Named volumes for data persistence
- Port maps: 5432, 6379, 5672, 15672

**Done when:** `docker compose ps` shows all three healthy, you can `psql` into the db and run `CREATE EXTENSION IF NOT EXISTS vector;` successfully.

---

## Phase 4 — FastAPI skeleton

Implement in this order:

1. `app/config.py` — `pydantic-settings` Settings class that reads `.env`. Every env var gets a typed field.
2. `app/logging.py` — structlog setup: JSON in prod, pretty console in dev. Bind `request_id` and `api_key_id` as default keys.
3. `app/main.py` — FastAPI instance with lifespan for startup/shutdown, `/health` endpoint, `/metrics` endpoint (empty for now).
4. Run it: `uvicorn app.main:app --reload`. Hit `http://localhost:8000/health`. Commit.

**Done when:** `curl http://localhost:8000/health` returns `{"status":"ok"}` and logs are structured JSON.

---

## Phase 5 — Database layer & migrations

1. `app/db/session.py` — create async engine with `asyncpg`, async sessionmaker, FastAPI dependency `get_db()`.
2. `app/db/models.py` — SQLAlchemy models:
   - `ApiKey` (id UUID, name, key_hash, key_prefix, user_email, created_at, revoked_at, rate_limit_overrides JSON, is_admin bool)
   - `UsageLog` (id, api_key_id FK, request_id, model, provider, prompt_tokens, completion_tokens, total_tokens, cost_usd, latency_ms, cache_hit enum[none|exact|semantic], status, error, created_at)
   - `CachedResponse` (id, request_hash UNIQUE, model, messages JSONB, response JSONB, prompt_tokens, completion_tokens, created_at, expires_at) — used by semantic cache for storing the *answer*; exact cache stores only in Redis for speed
   - `SemanticCacheEntry` (id, request_hash FK→CachedResponse, embedding VECTOR(1536), prompt_text, model, created_at) — pgvector index on embedding
   - `Job` (id UUID, api_key_id FK, kind enum, status enum[pending|running|succeeded|failed], input JSONB, result JSONB, error, created_at, started_at, finished_at)
3. `alembic init alembic`, edit `alembic/env.py` to use your async engine and import `models.Base.metadata`. Autogenerate the first migration: `alembic revision --autogenerate -m "initial schema"`. Hand-edit it to add `CREATE EXTENSION IF NOT EXISTS vector;` before the vector columns, and an IVFFlat index on the embedding column.
4. `alembic upgrade head`.

**Done when:** `\dt` in psql shows all five tables and `\d semantic_cache_entries` shows the vector column with an index.

---

## Phase 6 — API key auth

1. `app/auth/keys.py` — functions:
   - `generate_key() -> (plaintext, prefix, hash)` — plaintext like `sk-gw-live-{32 random chars}`; prefix is `sk-gw-live-{first 6}` for display; hash is argon2
   - `verify_key(plaintext, hash) -> bool`
   - `lookup_by_prefix(db, prefix) -> ApiKey | None`
2. `app/auth/middleware.py` — FastAPI dependency `require_api_key()` that reads `Authorization: Bearer sk-gw-live-...`, splits prefix, looks up, verifies hash, attaches `ApiKey` to request state. Separate `require_admin_key()` that also checks `is_admin`.
3. `scripts/create_api_key.py` — CLI that inserts a key and prints the plaintext *once* (you can't recover it after). Run it to create one admin key and one user key for your own testing.

**Done when:** a request without `Authorization` returns 401, with a wrong key returns 403, with a valid key reaches the handler with `request.state.api_key` populated.

---

## Phase 7 — Provider layer

1. `app/providers/schemas.py` — internal normalized schema. Use OpenAI's chat completion shape as the canonical format (it's the industry default most clients expect).
   - `NormalizedRequest`: model, messages[{role, content}], temperature, max_tokens, user
   - `NormalizedResponse`: id, model, provider, choices[{message, finish_reason}], usage{prompt_tokens, completion_tokens, total_tokens}
2. `app/providers/base.py` — `BaseProvider` ABC with `async def complete(req) -> NormalizedResponse` and `async def embed(texts) -> list[list[float]]`.
3. `app/providers/openai_provider.py` — implements `BaseProvider` using the `openai` SDK. Handles rate-limit / timeout / transient errors by raising typed exceptions (`ProviderRateLimitError`, `ProviderTimeoutError`, etc).
4. `app/providers/gemini_provider.py` — same, using `google-generativeai`. Handle Gemini's message format difference (system prompt → system_instruction, assistant → model).
5. `app/providers/anthropic_provider.py` — stub that raises `NotImplementedError` if called; only instantiated when `ENABLE_ANTHROPIC=true`.
6. `app/providers/router.py` — `ProviderRouter` class that takes a `NormalizedRequest` and tries providers in `PROVIDER_FALLBACK_ORDER`, using `tenacity` for retry with exponential backoff. Logs every attempt with structlog.

**Done when:** unit test sends a request, OpenAI provider returns a normalized response, you can force-fail OpenAI and see Gemini pick up automatically.

---

## Phase 8 — Exact-match Redis cache

1. `app/cache/keys.py` — `build_request_hash(model, messages, temperature, top_p, ...)` — SHA256 of canonical JSON.
2. `app/cache/exact.py` — `get(hash) -> NormalizedResponse | None`, `set(hash, response, ttl)`. Uses a Redis hash or plain string with msgpack/JSON serialization.
3. Wire into the chat endpoint (Phase 10) as the *first* cache layer.
4. Prometheus counter: `gateway_cache_exact_hits_total`, `gateway_cache_exact_misses_total`.

**Done when:** two identical requests back-to-back → second one has `cache_hit=exact` in the usage log and responds in <5ms.

---

## Phase 9 — Semantic cache (pgvector)

Layer on top of exact-match. Flow on a chat request:

1. Build the exact-match hash. Lookup Redis. Hit → return.
2. Miss → extract the *user message* from `messages` (last user turn is usually the signal). Embed it via OpenAI `text-embedding-3-small` (1536 dims, ~$0.02 per 1M tokens — negligible).
3. pgvector query: `SELECT request_hash FROM semantic_cache_entries WHERE model = :model ORDER BY embedding <=> :query_embedding LIMIT 1` combined with a threshold check on cosine distance.
4. If distance < `(1 - SEMANTIC_CACHE_THRESHOLD)` → fetch the `CachedResponse` row, return it. Mark `cache_hit=semantic`.
5. Miss → call provider. On success, write both the `CachedResponse` row and a `SemanticCacheEntry` with the embedding.

Files: `app/cache/semantic.py`. Add counters for semantic hits/misses. Guard the whole path with `SEMANTIC_CACHE_ENABLED` so you can benchmark on/off.

**Done when:** "What's the capital of France?" and "Tell me the capital of France" share a cache hit when semantic cache is on, and don't when it's off. Record both in the README metrics later.

---

## Phase 10 — /v1/chat/completions endpoint

`app/api/v1/chat.py` — the main endpoint. Flow:

1. Auth dependency attaches `api_key`.
2. Rate limit check (Phase 11 adds this; stub it returning True for now).
3. Validate request body against `NormalizedRequest` Pydantic model (accept OpenAI-shaped input).
4. Exact cache → semantic cache → provider router.
5. Write `UsageLog` row with tokens, cost (estimated from a pricing table `PROVIDER_PRICING`), latency, cache hit kind.
6. Return response in OpenAI-compatible shape so existing OpenAI client libraries "just work" against your gateway.

**Done when:** `curl` against `http://localhost:8000/v1/chat/completions` with a valid key and OpenAI-shaped body returns a completion. Repeat same request → cached response. Slightly rephrase → semantic cached response.

---

## Phase 11 — Rate limiting

`app/ratelimit/sliding_window.py` — Redis sliding-window counter per API key. Use a sorted set keyed by `ratelimit:{api_key_id}:{window}` where score = timestamp. On each request: drop entries older than window, count remaining, reject if over limit with HTTP 429 including `Retry-After`. Implement both per-minute and per-day limits. Per-key overrides from the `rate_limit_overrides` JSON column.

Wire into the chat endpoint *before* the cache check — a cached response still counts against your limit (simpler and honest).

**Done when:** running a loop of 70 requests/min against a 60/min key starts returning 429 after request 60.

---

## Phase 12 — Celery worker + async jobs

1. `app/worker/celery_app.py` — Celery instance with RabbitMQ broker and Redis result backend.
2. `app/worker/tasks.py` — `batch_embeddings_task(job_id, api_key_id, texts, model)`. Marks job running, calls provider embeddings in batches (OpenAI supports up to 2048 inputs per call), writes results, marks done/failed.
3. `app/api/v1/embeddings.py` — `POST /v1/embeddings` for synchronous small batches, `POST /v1/embeddings/batch` creates a `Job` row, dispatches the Celery task, returns `{job_id, status: pending}`.
4. `app/api/v1/jobs.py` — `GET /v1/jobs/{job_id}` returns status + result when done. Auth check: job must belong to the requesting API key.
5. Run the worker: `celery -A app.worker.celery_app worker -l info --pool=solo` (on Windows use `--pool=solo` to avoid fork issues; prod Linux uses `--pool=prefork`).

**Done when:** you can POST a batch of 500 texts, get back a job_id, see RabbitMQ management UI show the message, watch the worker process it, poll the job endpoint until `status=succeeded` and retrieve embeddings.

---

## Phase 13 — Observability: Prometheus + Grafana

1. `app/metrics/prometheus.py` — counters and histograms:
   - `gateway_requests_total{endpoint, status, provider, cache_hit}`
   - `gateway_request_duration_seconds` histogram
   - `gateway_tokens_total{provider, kind}` (prompt/completion)
   - `gateway_cost_usd_total{provider, api_key_prefix}`
   - `gateway_provider_errors_total{provider, error_type}`
   - `gateway_rate_limit_rejections_total{api_key_prefix}`
2. Expose `/metrics` (no auth, standard Prometheus scrape pattern — protect at nginx level in prod).
3. Add Prometheus + Grafana services to `docker-compose.dev.yml`.
4. Prometheus config `prometheus.yml` scrapes `app:8000/metrics` every 15s.
5. `grafana/dashboards/gateway.json` — panels: RPS, p50/p95/p99 latency, cache hit rate stacked (none/exact/semantic), tokens/min per provider, cost/day per key, error rate per provider. Import via Grafana's provisioning.

**Done when:** `http://localhost:3000` shows Grafana, the gateway dashboard loads, metrics update as you fire requests.

---

## Phase 14 — Dashboard (React + Vite)

Scaffold in `dashboard/`:

```powershell
cd dashboard
npm create vite@latest . -- --template react-ts
npm install
npm install axios recharts @tanstack/react-query tailwindcss @tailwindcss/vite
```

Pages:
- **Login** — enter an admin API key, stored in localStorage, sent as `Authorization: Bearer ...`
- **API Keys** — list, create, revoke (admin endpoints from `app/api/admin/keys.py`)
- **Usage** — per-key usage charts (requests/day, tokens/day, cost/day) via admin usage endpoints
- **Cache** — cache hit rate over time, semantic vs exact split, estimated cost saved

Build admin endpoints in `app/api/admin/`:
- `POST /admin/keys`, `GET /admin/keys`, `DELETE /admin/keys/{id}`
- `GET /admin/usage?api_key_id=&from=&to=` aggregates UsageLog
- `GET /admin/cache/stats` pulls from Prometheus or aggregates from UsageLog

Local dev: run dashboard with `npm run dev` at `http://localhost:5173`, proxy API calls to `http://localhost:8000`.

**Done when:** you can log in with your admin key, see the user key you created in Phase 6, see real usage data from requests you've fired.

---

## Phase 15 — Nginx + production Dockerfile

1. `docker/Dockerfile` — multi-stage:
   - Stage 1 (`builder`): install build deps, compile wheels
   - Stage 2 (`runtime`): slim python:3.11-slim, copy wheels, non-root user, `CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8000", "app.main:app"]`
   - Same image used for both API and worker; entrypoint script decides based on `ROLE` env var.
2. `docker/entrypoint.sh` — branches on `ROLE`: api → gunicorn; worker → celery; migrate → alembic upgrade head then exit.
3. `nginx/nginx.conf` (dev) — reverse proxy to `app:8000`, rate limit zone (defense in depth), gzip, access/error logs.
4. `nginx/prod.conf` — placeholder; Certbot will rewrite parts of it for TLS in Phase 17.
5. `docker-compose.prod.yml` — everything: nginx, api (scale 2), worker (scale 2), beat (optional, for scheduled cache cleanup), postgres, redis, rabbitmq, prometheus, grafana. Healthchecks on every service. Restart policy `unless-stopped`.

**Done when:** on your laptop, `docker compose -f docker-compose.prod.yml up -d --build` brings up the full stack, `curl http://localhost/health` via nginx works, all services are healthy after 30s.

---

## Phase 16 — Tests

In `tests/`:
- `conftest.py` — fixtures: event loop, test db (separate Postgres schema or testcontainers-python), test redis, FastAPI TestClient.
- `tests/unit/test_cache_exact.py` — hash determinism, get/set, ttl expiry.
- `tests/unit/test_cache_semantic.py` — mock embedding, verify threshold behavior, pgvector integration with a test db.
- `tests/unit/test_router.py` — mock providers, force failures, assert fallback order.
- `tests/unit/test_ratelimit.py` — inject time, verify sliding window correctness.
- `tests/integration/test_chat_completions.py` — end-to-end with mocked provider, covers auth, rate limit, cache hit/miss paths.

Aim for ~70% coverage — that's enough to show testing discipline without becoming the project. Run: `pytest --cov=app`.

**Done when:** `pytest` passes clean, coverage report is in the repo.

---

## Phase 17 — Deploy to VPS with TLS

This is the final-boss phase. Budget one full evening.

1. **Provision VPS.** Hetzner CX22 (€4.15/mo, 2 vCPU, 4GB RAM) or DO basic droplet ($6/mo). Ubuntu 24.04. SSH key auth only — disable password login.
2. **DNS.** Point `api.yourdomain.com` and `dashboard.yourdomain.com` A records to the VPS IP. Wait for propagation (usually 5–30 min — verify with `nslookup api.yourdomain.com`).
3. **Server prep:**
   ```bash
   ssh root@<ip>
   adduser deploy && usermod -aG sudo deploy
   apt update && apt upgrade -y
   apt install -y docker.io docker-compose-plugin git ufw
   usermod -aG docker deploy
   ufw default deny incoming && ufw default allow outgoing
   ufw allow OpenSSH && ufw allow http && ufw allow https && ufw enable
   ```
4. **Clone repo as deploy user:**
   ```bash
   su - deploy
   git clone https://github.com/<you>/llm-gateway.git
   cd llm-gateway
   cp .env.example .env
   nano .env   # fill real prod values, strong secret key, real API keys
   ```
5. **Build dashboard for production:**
   ```bash
   cd dashboard && npm install && npm run build && cd ..
   # dist/ gets mounted into nginx static root
   ```
6. **Start stack:**
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
   docker compose -f docker-compose.prod.yml exec api python scripts/create_api_key.py --admin --name "me"
   ```
7. **TLS with Certbot.** Install certbot on the host (not inside a container — simplest for v1):
   ```bash
   sudo apt install -y certbot python3-certbot-nginx
   # stop the stack's nginx briefly OR use certbot webroot mode
   sudo certbot --nginx -d api.yourdomain.com -d dashboard.yourdomain.com
   ```
   Certbot autoconfigures TLS and sets up auto-renewal via systemd timer.
8. **Smoke test:**
   - `curl https://api.yourdomain.com/health` → 200
   - Open `https://dashboard.yourdomain.com` → login screen
   - Log in with the admin key, create a user key, fire a test completion from your laptop against the prod URL.

**Done when:** you can paste `https://api.yourdomain.com` and `https://dashboard.yourdomain.com` into a message and both work for anyone who clicks them.

---

## Phase 18 — README + metrics collection

Without numbers, this project is half the CV value. Collect them before writing the README.

1. **Write a locust script** `tests/load/locustfile.py` that fires mixed traffic: 60% chat completions (varied prompts, some repeated), 20% embeddings, 10% batch embeddings, 10% admin reads.
2. **Run two scenarios:**
   - With semantic cache off, exact cache on — baseline.
   - With both caches on.
   Each run: 50 concurrent users, 10 min.
3. **Record:**
   - Cache hit rate (split exact vs semantic)
   - p50 / p95 / p99 latency on cache-hit vs cache-miss
   - Requests/sec sustained
   - Cost in $ over the 10-min run, comparing cached vs uncached
   - Failover time when you `docker kill` OpenAI's outbound traffic (use a mock to simulate)
4. **README sections:**
   - Hero image (architecture diagram — draw in Excalidraw, save as PNG)
   - What & why (3 paragraphs max)
   - Live demo links (api + dashboard URLs + a public test API key that's rate-limited)
   - Features list with one-sentence justification each
   - Architecture diagram (same PNG again with callouts)
   - Quickstart (`docker compose up` path for evaluators)
   - **Results section with the numbers from step 3** — this is the bit recruiters screenshot
   - Tech-choice rationale (the "why this stack" table — one row per tech, one sentence why)
   - Roadmap (v1.5: streaming, v2: multi-tenant orgs, Anthropic provider, etc.)

**Done when:** a cold reader can understand what it is, click a live link that works, and see a numbers-backed results section — inside 90 seconds.

---

## Build order as a calendar

Realistic for 2–3 focused weekends + a few weeknights:

- **Weekend 1 Sat:** Phases 0–5. Project up, db + migrations running, one endpoint returning hello.
- **Weekend 1 Sun:** Phases 6–7. Auth + provider layer. You can call OpenAI and Gemini through your own API.
- **Weeknights 1:** Phases 8–9. Both cache layers.
- **Weekend 2 Sat:** Phases 10–11. Chat endpoint complete, rate limiting on.
- **Weekend 2 Sun:** Phase 12. Celery + RabbitMQ worker, batch embeddings.
- **Weeknights 2:** Phase 13. Observability.
- **Weekend 3 Sat:** Phase 14. Dashboard.
- **Weekend 3 Sun half 1:** Phases 15–16. Prod compose + tests.
- **Weekend 3 Sun half 2:** Phase 17. Deploy.
- **Weeknights 3:** Phase 18. Load test, measure, write README.

Total: ~50–60 hours of focused work. Don't pre-optimize, don't rabbit-hole. If a phase runs long, move on and come back — the stack is designed so each layer is independently testable.

---

## Guardrails for yourself

- **No new technology without a one-sentence justification.** If you catch yourself wanting to add Kafka/k8s/whatever mid-build, write the sentence first. If it sounds weak, cut it.
- **Commit after every phase** with a clean message. The git log becomes part of the project story.
- **Feature flags over branches** for anything risky (semantic cache, anthropic provider).
- **Don't polish before deploying.** Ugly-but-live beats pretty-but-local. You can polish against the live version.
- **README last but not least.** The code is table stakes; the README is what recruiters actually read.