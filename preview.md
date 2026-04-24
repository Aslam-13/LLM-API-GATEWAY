# Project Preview — LLM API Gateway

Exhaustive terse reference. Update on every change. Replaces codebase search.

---

## Stack
Python 3.11 · FastAPI · SQLAlchemy 2.0 async (asyncpg) · Alembic · Postgres 16 + pgvector · Redis 7 · RabbitMQ 3.13 · Celery · structlog · Prometheus + Grafana · React+Vite (dashboard, later) · pytest.

## Providers (v1)
OpenAI + Gemini active. Anthropic wired as stub, disabled via `ENABLE_ANTHROPIC=false`.

## Repo layout
```
app/
  main.py          FastAPI app, lifespan, /health, /metrics stub
  config.py        pydantic-settings Settings + get_settings() lru_cache
  logging.py       structlog: dev=console, prod=JSON; binds request_id, api_key_id
  deps.py          (empty — FastAPI deps land here)
  db/
    session.py     async engine, AsyncSessionLocal, get_db()
    models.py      Base + ApiKey, UsageLog, CachedResponse, SemanticCacheEntry, Job
  api/v1/          chat.py, embeddings.py, jobs.py (empty)
  api/admin/       keys.py, usage.py (empty)
  providers/       base.py, openai_provider.py, gemini_provider.py,
                   anthropic_provider.py, router.py, schemas.py (empty)
  cache/           exact.py (Redis), semantic.py (pgvector), keys.py (empty)
  ratelimit/       sliding_window.py (empty)
  auth/            keys.py, middleware.py (empty)
  metrics/         prometheus.py (empty)
  worker/          celery_app.py, tasks.py (empty)
alembic/           env.py (wired to app.db.models.Base), versions/
alembic.ini
dashboard/         (scaffolded later)
nginx/             nginx.conf, prod.conf (empty)
docker/            Dockerfile, entrypoint.sh (empty)
scripts/           create_api_key.py, seed.py (empty)
tests/             unit/, integration/, conftest.py (empty)
grafana/dashboards/gateway.json (empty)
docker-compose.dev.yml
docker-compose.prod.yml (empty)
.env / .env.example / .gitignore / requirements.txt / requirements-dev.txt / pyproject.toml (empty) / README.md (empty)
plan.md            build roadmap (18 phases)
preview.md         this file
```

## Infra (docker-compose.dev.yml)
- `postgres` → `pgvector/pgvector:pg16`, host port **5433→5432** (5432 taken by host Postgres on this Windows machine), healthcheck `pg_isready`, volume `postgres_data`, container `gateway-postgres`, user/pass/db = `gateway/gateway/gateway`.
- `redis` → `redis:7-alpine`, port 6379, appendonly yes, volume `redis_data`, container `gateway-redis`.
- `rabbitmq` → `rabbitmq:3.13-management`, ports 5672 + 15672 (mgmt UI guest/guest), volume `rabbitmq_data`, container `gateway-rabbitmq`.
- Vars passed via Compose `.env` interpolation only (`${VAR:-default}`). Infra containers use POSTGRES_* and RABBITMQ_USER/PASSWORD. App-level vars not injected (app runs on host in dev).

## Env vars (.env / .env.example)
```
APP_ENV=dev  APP_DEBUG=true  APP_SECRET_KEY=<rotate>
POSTGRES_USER=gateway  POSTGRES_PASSWORD=gateway  POSTGRES_DB=gateway
POSTGRES_HOST=localhost  POSTGRES_PORT=5433
DATABASE_URL=postgresql+asyncpg://gateway:gateway@localhost:5433/gateway
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://guest:guest@localhost:5672//
CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
CELERY_RESULT_BACKEND=redis://localhost:6379/1
OPENAI_API_KEY=…  GEMINI_API_KEY=…  ANTHROPIC_API_KEY=  ENABLE_ANTHROPIC=false
CACHE_TTL_SECONDS=3600  SEMANTIC_CACHE_ENABLED=true  SEMANTIC_CACHE_THRESHOLD=0.97
EMBEDDING_MODEL=text-embedding-004
RATE_LIMIT_REQUESTS_PER_MINUTE=60  RATE_LIMIT_REQUESTS_PER_DAY=10000
PROVIDER_FALLBACK_ORDER=openai,gemini  PROVIDER_RETRY_ATTEMPTS=2  PROVIDER_RETRY_DELAY_SECONDS=1
```
`.env` is git-ignored. `.env.example` committed.

## App config (app/config.py)
`Settings(BaseSettings)` reads `.env`, case-insensitive, extra=ignore. All env vars typed. Helpers: `fallback_providers` (list), `is_dev`. `get_settings()` is `@lru_cache`.

## Logging (app/logging.py)
`configure_logging()` called in FastAPI lifespan. Dev → `ConsoleRenderer` (colors). Prod → `JSONRenderer`. Processors: contextvars merge, log level, ISO UTC timestamp, stack, exc info. Default bound keys: `request_id=None`, `api_key_id=None`. Stdlib logging routed through stdout. `get_logger(name)` for per-module loggers.

## FastAPI app (app/main.py)
- `app = FastAPI(title="LLM API Gateway", version="0.1.0", lifespan=lifespan)`
- Lifespan: `configure_logging()`, emit `gateway.startup` / `gateway.shutdown`.
- `GET /health` → `{"status":"ok"}`.
- `GET /metrics` → `""` (PlainText, Phase 13 fills in).
- Dev run: `uvicorn app.main:app --reload` (host).

## DB session (app/db/session.py)
`create_async_engine(settings.database_url, echo=app_debug, pool_pre_ping=True)`, `AsyncSessionLocal = async_sessionmaker(expire_on_commit=False, autoflush=False)`, `get_db()` async generator dependency.

## DB models (app/db/models.py)
`Base(DeclarativeBase)`. Enums: `CacheHit{none,exact,semantic}`, `JobKind{batch_embeddings}`, `JobStatus{pending,running,succeeded,failed}`.

Tables:
- **api_keys** — id UUID pk, name, key_hash, key_prefix (unique idx), user_email, is_admin bool, rate_limit_overrides JSONB, created_at, revoked_at.
- **usage_logs** — id int pk, api_key_id FK (idx), request_id (idx), model, provider, prompt/completion/total_tokens, cost_usd float, latency_ms, cache_hit enum, status, error, created_at (idx).
- **cached_responses** — id int pk, request_hash (unique idx), model, messages JSONB, response JSONB, prompt/completion_tokens, created_at, expires_at (idx).
- **semantic_cache_entries** — id int pk, request_hash FK→cached_responses.request_hash (idx), **embedding VECTOR(768)** with IVFFlat cosine idx (lists=100), prompt_text, model (idx), created_at. *(Dim = 768 to match Gemini `text-embedding-004`. Migration `f6db56c81d4e` resizes from 1536 → 768.)*
- **jobs** — id UUID pk, api_key_id FK (idx), kind enum, status enum (idx), input JSONB, result JSONB, error, created_at, started_at, finished_at.

Relationships: ApiKey↔UsageLog, ApiKey↔Job, CachedResponse↔SemanticCacheEntry.

## Alembic
- Async template (`alembic init -t async alembic`).
- `alembic/env.py` sets `sqlalchemy.url` from `get_settings().database_url`; `target_metadata = Base.metadata`.
- First migration: `bbcedf249985_initial_schema.py`. Hand-edits: `CREATE EXTENSION IF NOT EXISTS vector` at top of upgrade; IVFFlat index on `semantic_cache_entries.embedding` using `vector_cosine_ops` with lists=100; `import pgvector.sqlalchemy`; downgrade drops the index.
- Commands: `alembic revision --autogenerate -m "msg"`, `alembic upgrade head`.

## Providers (Phase 7 — done)
Normalized internal schema = OpenAI chat-completion shape.

- `app/providers/schemas.py` — `Message{role,content}` (role=`system|user|assistant`), `NormalizedRequest{model, messages, temperature?, max_tokens?, top_p?, user?}`, `Usage{prompt/completion/total_tokens}`, `Choice{index, message, finish_reason?}`, `NormalizedResponse{id, model, provider, choices[], usage}`.
- `app/providers/base.py` — `BaseProvider(ABC)` with `name`, `complete(req) -> NormalizedResponse`, `embed(texts, model) -> list[list[float]]`. Exception hierarchy: `ProviderError` base; subclasses `ProviderRateLimitError`, `ProviderTimeoutError`, `ProviderBadRequestError`, `ProviderAuthError`, `ProviderServerError`, `ProviderDisabledError`. Each instance has `.provider` set by provider impl.
- `app/providers/openai_provider.py` — uses `AsyncOpenAI(api_key=…)`. Maps `RateLimitError`→RateLimit, `APITimeoutError|APIConnectionError`→Timeout, `AuthenticationError`→Auth, `BadRequestError`→BadRequest, other `APIStatusError`→Server. `embed()` via `/v1/embeddings`.
- `app/providers/gemini_provider.py` — `google.generativeai`. Converts messages: `system` roles merged into `system_instruction`; `assistant` → `model`. Sync SDK calls wrapped in `asyncio.to_thread`. Maps `google.api_core.exceptions`: `ResourceExhausted`→RateLimit, `DeadlineExceeded`→Timeout, `Unauthenticated|PermissionDenied`→Auth, `InvalidArgument`→BadRequest, other `GoogleAPIError`→Server. `id = f"gemini-{uuid}"`. Usage from `response.usage_metadata`. `embed()` loops items through `genai.embed_content`.
- `app/providers/anthropic_provider.py` — stub; `complete`/`embed` raise `ProviderDisabledError`. Instantiated by router only when `ENABLE_ANTHROPIC=true`.
- `app/providers/router.py` — `ProviderRouter(providers?, order?)`. Defaults: instantiates OpenAI + Gemini (+ Anthropic if enabled), `order = settings.fallback_providers` (`PROVIDER_FALLBACK_ORDER` csv, default `openai,gemini`).
  - Retry (tenacity `AsyncRetrying`): `stop_after_attempt(PROVIDER_RETRY_ATTEMPTS + 1)`, `wait_exponential(multiplier=delay, min=delay, max=delay*8)`. Retries only `_RETRYABLE = (RateLimit, Timeout, Server)`. Fatal-no-retry-no-fallback: `_FATAL = (Auth, BadRequest, Disabled)` → break loop and raise.
  - After retries exhaust on one provider, moves to next in order. Raises the last error if all fail.
  - Logs `provider.attempt`, `provider.exhausted`, `provider.fatal`, `provider.missing`.
  - Verified: mocked openai always-Server, gemini OK → gemini serves after 3 openai attempts.

## Cache + chat pipeline (Phases 8, 9, 10 — done)

### app/cache/keys.py
- `build_request_hash(req)` — SHA256 of canonical JSON over `{model, messages[{role,content}], temperature, top_p, max_tokens}`, `sort_keys=True`, separators=`(,`,`:)`. Returns 64-char hex.
- `last_user_message(req)` — last `role="user"` message content, else None.

### app/cache/exact.py (Redis)
- `redis.asyncio` client, lazy global via `get_redis()`, `decode_responses=True`.
- Key prefix `cache:exact:{hash}`.
- `get(hash) -> NormalizedResponse | None` (json → pydantic).
- `set(hash, response, ttl)` — `SETEX` with `CACHE_TTL_SECONDS`.

### app/cache/semantic.py (pgvector)
- `lookup(db, model, embedding, threshold) -> (NormalizedResponse, request_hash, distance) | None`
  - `max_dist = 1 - threshold` (cosine distance; pgvector `<=>` via `embedding.cosine_distance(q)`).
  - ORDER BY distance LIMIT 1 WHERE `model = :model`. Hit iff `distance <= max_dist`.
  - Joins to `CachedResponse` by `request_hash` to retrieve response JSON.
- `store(db, hash, req, response, embedding, ttl_seconds)`
  - Idempotent `CachedResponse` insert on `request_hash` (skip if exists), always append `SemanticCacheEntry` row.
  - `expires_at = now() + ttl`.
  - Single commit per call.

### app/providers/pricing.py
`PROVIDER_PRICING: {"{provider}:{model}": (prompt_$/1k, completion_$/1k)}`.
Seeded: openai(gpt-4o, gpt-4o-mini, gpt-3.5-turbo, text-embedding-3-small), gemini(1.5-flash, 1.5-pro, 2.0-flash).
`estimate_cost(provider, model, pt, ct)` → 0.0 for unknown model.

### app/metrics/prometheus.py (counters declared; `/metrics` exposes them in Phase 13)
- `gateway_requests_total{endpoint,status,provider,cache_hit}`
- `gateway_request_duration_seconds{endpoint}` (Histogram)
- `gateway_tokens_total{provider,kind}`
- `gateway_cost_usd_total{provider,api_key_prefix}`
- `gateway_provider_errors_total{provider,error_type}`
- `gateway_rate_limit_rejections_total{api_key_prefix}`
- `gateway_cache_exact_hits_total` / `..._misses_total`
- `gateway_cache_semantic_hits_total` / `..._misses_total`

### app/ratelimit/sliding_window.py
`check_and_consume(api_key)` — stub returning None (Phase 11 real impl).

### app/deps.py
`@lru_cache get_router()` → single `ProviderRouter()`. `@lru_cache get_embedder()` → single `GeminiProvider()` (produces 768-dim vectors).

### app/api/v1/chat.py — `POST /v1/chat/completions`
- Dep: `require_api_key`, `get_db`.
- Request body: `NormalizedRequest` (FastAPI 422 on validation fail).
- Flow:
  1. bind `request_id` (uuid4 hex) contextvar, `t0 = perf_counter()`.
  2. `check_and_consume(api_key)` (stub).
  3. `request_hash = build_request_hash(req)`.
  4. **Exact cache** → `exact_cache.get` → hit: `response`, `hit=exact`, increment `cache_exact_hits_total`; miss → `cache_exact_misses_total`.
  5. **Semantic cache** (iff `SEMANTIC_CACHE_ENABLED` and exact miss and `last_user_message` present):
     - embed via `get_embedder().embed([user_text], EMBEDDING_MODEL)` (OpenAI).
     - embed errors: log `semantic.embed_failed`, skip to provider.
     - `semantic_cache.lookup(db, model, embedding, SEMANTIC_CACHE_THRESHOLD)` → hit: `response`, `hit=semantic`, log distance; miss → miss counter.
  6. **Provider** (if still no response): `get_router().complete(req)`.
     - `ProviderError` → 502, write `UsageLog(status="error")`, increment `provider_errors_total{provider,error_type}` + `requests_total{status=error}`.
     - Success → `exact_cache.set(hash, response, ttl)` (failure logged, not fatal) and, if semantic enabled + embedding present, `semantic_cache.store(...)` (failure logged, not fatal).
  7. **Usage + metrics** (always on success):
     - cache hit: `prompt=completion=0, cost=0.0` (accurate cost accounting — cache = free).
     - cache miss: `response.usage.*` tokens, `estimate_cost(...)`.
     - insert `UsageLog(status="success", cache_hit=hit)`.
     - increment `tokens_total{provider,kind}` for both prompt+completion, `cost_usd_total{provider, api_key_prefix}`, `requests_total{status=success}`, observe `request_duration_seconds`.
  8. Return OpenAI-shaped dict: `{id, object="chat.completion", created, model, provider, x_request_id, x_cache_hit, choices[], usage}`.

### main.py
`app.include_router(chat_router)` added. Routes: `/v1/chat/completions`, `/health`, `/metrics`, plus openapi/docs.

### Cache-accounting decision
Cache hits recorded with **zero** prompt/completion tokens and **zero** cost in `UsageLog` (reflects real spend). Compute "cost saved" in Phase 18 by multiplying cache-hit count × avg miss cost.

## Auth (Phase 6 — done)
`Authorization: Bearer sk-gw-live-{32 chars}`.

- `app/auth/keys.py`
  - `KEY_PREFIX = "sk-gw-live-"`, random = `secrets.token_urlsafe(32)[:32]`.
  - `generate_key() -> GeneratedKey(plaintext, prefix, hash)`. `prefix` = first `len(KEY_PREFIX)+6` chars of plaintext (stored plain, unique-indexed). `hash` = argon2 via `passlib.CryptContext(schemes=["argon2"])`.
  - `verify_key(plaintext, key_hash) -> bool` (catches all errors → False).
  - `extract_prefix(plaintext)` returns None if not prefixed `sk-gw-live-`.
  - `lookup_by_prefix(db, prefix)` → `ApiKey | None`.
- `app/auth/middleware.py`
  - `require_api_key(request, authorization, db)` FastAPI dep. 401 if header missing or non-Bearer. 403 if prefix invalid / not found / revoked / hash mismatch. On success: `request.state.api_key = api_key` and `structlog.contextvars.bind_contextvars(api_key_id=str(api_key.id))`.
  - `require_admin_key(api_key = Depends(require_api_key))` → 403 if `not is_admin`.
- `scripts/create_api_key.py` — argparse CLI `--name --email --admin`. Run with `PYTHONPATH=. .venv/Scripts/python.exe scripts/create_api_key.py …`. Prints plaintext once (unrecoverable).
- Verified: 401 missing, 401 wrong scheme, 403 bad/revoked, 200 valid, 403 user→admin-only, 200 admin→admin-only.
- Test note: FastAPI `TestClient` creates a new asyncio loop per request, clashing with the engine's asyncpg pool. Use `httpx.AsyncClient(transport=httpx.ASGITransport(app=a))` inside one `asyncio.run` for multi-request checks. (Address properly in Phase 16 via per-test engine fixture.)

## Rate limiting (Phase 11 — done)
`app/ratelimit/sliding_window.py` — Redis-backed per-key sliding window.

- Keys: `ratelimit:{api_key_id}:minute` and `ratelimit:{api_key_id}:day` (sorted sets, score=timestamp ms).
- Flow per request: read both windows (drop entries older than window via `ZREMRANGEBYSCORE`, `ZCARD` for count), **gate first on both, then consume once** (single member added to both sets — correct 1-request = 1-slot accounting).
- Limits: `RATE_LIMIT_REQUESTS_PER_MINUTE` (60) and `RATE_LIMIT_REQUESTS_PER_DAY` (10000). Overrides from `ApiKey.rate_limit_overrides` JSON: `{"per_minute": int, "per_day": int}`.
- Limit=0 disables the window.
- 429 response with `Retry-After` header (60 / 86400). Increments `gateway_rate_limit_rejections_total{api_key_prefix}`.
- Applied from chat + embeddings endpoints; cache hits still count (honest accounting).

## Celery (Phase 12 — done)
`app/worker/celery_app.py`

- `Celery("gateway", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)` with `include=["app.worker.tasks"]`.
- JSON-only serialization. `task_acks_late=True`, `worker_prefetch_multiplier=1` (fairness for long tasks), `broker_connection_retry_on_startup=True`.

`app/worker/tasks.py`

- `@celery_app.task(name="batch_embeddings")` → `batch_embeddings_task(job_id, provider, model, texts)`.
- Sync Celery task wraps `asyncio.run(_run_batch_embeddings(...))` and disposes the async engine on exit (per-worker-task loop hygiene).
- `_run_batch_embeddings` uses `AsyncSessionLocal`: fetches `Job`, marks `running` + `started_at`, batches through provider `embed()` (`OPENAI_BATCH=512`, `GEMINI_BATCH=32`), stores `result={model, provider, count, dimensions, vectors}`, sets `succeeded` or `failed` + `error`, sets `finished_at`. One commit per state change.

`app/api/v1/embeddings.py`

- `POST /v1/embeddings` (sync). Body: `{model?, input: str | list[str]}`. 400 if `>100` inputs. Runs `get_embedder().embed(...)` directly. Returns OpenAI-shaped `{object:"list", model, data:[{object:"embedding", index, embedding}]}`. `ProviderError` → 502.
- `POST /v1/embeddings/batch` (202). Body: `{model?, input: list[str], provider: "gemini"|"openai"}`. Inserts a `Job(kind=batch_embeddings, status=pending, input={model,provider,count})`, commits, calls `batch_embeddings_task.delay(...)`, returns `{job_id, status}`.

`app/api/v1/jobs.py`

- `GET /v1/jobs/{job_id}?include_result=true`. Auth: owner or admin (else 403). 404 if missing. Returns id, kind, status, input, result, error, created/started/finished timestamps.

### Run the worker (Windows dev)
```
PYTHONPATH=. .venv/Scripts/celery.exe -A app.worker.celery_app worker -l info --pool=solo
```
Prod linux: `--pool=prefork` (or `--pool=gevent` for I/O-bound).

### Routes now mounted
`/v1/chat/completions`, `/v1/embeddings`, `/v1/embeddings/batch`, `/v1/jobs/{job_id}`, `/admin/me`, `/admin/keys` (GET/POST), `/admin/keys/{id}` (DELETE), `/admin/usage`, `/admin/stats/overview`, `/admin/stats/latency`, `/admin/stats/errors`, `/admin/stats/tokens`, `/admin/stats/cost-by-key`, `/admin/stats/rate-limits`, `/admin/jobs`, `/health`, `/metrics` (Prometheus text).

## Admin endpoints (Phase 14 backend)
All require `require_admin_key`.

- `GET /admin/me` — echo admin profile.
- `GET /admin/keys` — list all ApiKeys w/ `last_used_at` derived from `max(usage_logs.created_at)` per key.
- `POST /admin/keys` — body `{name, email?, admin?}` → returns row + `plaintext` (single exposure).
- `DELETE /admin/keys/{id}` — soft revoke (sets `revoked_at`).
- `GET /admin/usage?api_key_id=&from=&to=&limit=&offset=` — rows + `{aggregate: requests/tokens/cost_usd/avg_latency_ms}` + daily series.
- `GET /admin/stats/overview` — 24h totals (requests, cost, tokens, cache_hit_rate, p95 latency via `percentile_cont`), 24h cache breakdown, 1h requests-per-minute series, 24h hourly stacked cache series.
- `GET /admin/stats/latency` — 24h hourly p50/p95/p99 of `latency_ms` (success only).
- `GET /admin/stats/errors` — 24h hourly `{errors, rate_limited, total, error_rate}`.
- `GET /admin/stats/tokens` — 7d daily tokens **stacked by provider**; response includes `providers[]` + normalized per-day buckets with zero-fill.
- `GET /admin/stats/cost-by-key` — top-10 API keys by 7d cost (LEFT JOIN api_keys so zero-usage keys still appear at bottom).
- `GET /admin/stats/rate-limits` — 24h hourly rejection count (status='rate_limited').
- `GET /admin/jobs?status=&limit=&offset=` — paginated Jobs list.

### Rate-limit logging
`check_and_consume` raises 429. `chat.py` + `embeddings.py` (both sync + batch) catch HTTPException with status=429, insert a `UsageLog(status='rate_limited', provider='ratelimit', model='...')` row before re-raising. Feeds the errors + rate-limits charts.

### /metrics (Prometheus text)
`GET /metrics` → `prometheus_client.generate_latest()` with `CONTENT_TYPE_LATEST`. Serves all counters/histograms registered in `app/metrics/prometheus.py`. No Prometheus server runs locally; endpoint is scrape-able by anyone who wants to run one.

## CORS (main.py)
`CORSMiddleware` allows `http://localhost:5173`, `http://127.0.0.1:5173` (dashboard dev). Prod will add the production domain once deployed.

## Dashboard (Phase 14 — done)
React 19 + TypeScript + Vite + Tailwind v3 + TanStack Query v5 + React Router v7 + Axios + Recharts. Dark admin UI. Hosted static bundle in prod; Vite dev server on :5173 with proxy to api :8000 in dev.

### Auth
Admin paste key → stored in `localStorage["llm-gw-admin-key"]` → axios interceptor adds `Authorization: Bearer …`. 401/403 response → clear + redirect to `/login`.

### Pages (under `Protected` guard)
- `/login` — single password input; calls `/admin/me` to verify.
- `/` **Overview** — SQL-over-`usage_logs` operations dashboard. Auto-refresh 10s for live stats, 30s/60s for slower charts. Charts:
  - Stat cards: 24h requests, cache hit rate, p95 latency, cost + tokens.
  - Line: requests / minute (1h).
  - Stacked bar: cache hits / hour (24h) — exact / semantic / none.
  - Line: p50 / p95 / p99 latency (24h hourly).
  - Stacked bar: errors + rate-limited per hour (24h).
  - Stacked bar: tokens by provider (7d daily).
  - Table: top-10 cost by API key (7d).
  - Line: rate-limit rejections per hour (24h).
- `/keys` **API Keys** — table (name, prefix, email, role, created, last_used, status). Create modal → success modal shows plaintext + copy button. Revoke with confirm.
- `/usage` — filters (api_key dropdown populated from `/admin/keys`, last N days). Stat cards (aggregate). Daily bar chart. Paginated table with cache-hit pills.
- `/jobs` — filter by status, auto-refresh 5s. Click row → slide-in drawer with full JSON input + error.

### Folder layout
```
dashboard/src/
  main.tsx           QueryClient + BrowserRouter + App
  App.tsx            Routes + Protected guard
  index.css          Tailwind + dark scrollbar
  auth.ts            localStorage token helpers
  api.ts             axios client + typed endpoints + types
  components/
    Shell.tsx        sidebar layout
    ui.tsx           Card, StatCard, Pill, Button, Input, Select, Th, Td
    Modal.tsx        centered modal
  pages/
    Login.tsx  Overview.tsx  Keys.tsx  Usage.tsx  Jobs.tsx
```

### Commands
```
cd dashboard
npm install
npm run dev      # http://localhost:5173 (proxies /admin /v1 → :8000)
npm run build    # → dist/
```

## Prometheus (planned)
Counters: `gateway_requests_total{endpoint,status,provider,cache_hit}`, `gateway_tokens_total{provider,kind}`, `gateway_cost_usd_total{provider,api_key_prefix}`, `gateway_provider_errors_total`, `gateway_rate_limit_rejections_total`, `gateway_cache_exact_hits_total/misses_total`. Histogram: `gateway_request_duration_seconds`.

## Decisions / notes
- Embedder = Gemini `models/gemini-embedding-001` with `output_dimensionality=768`. OpenAI-family (via GitHub Models) reserved for chat fallback only; added later.
- `SEMANTIC_CACHE_THRESHOLD` tuned 0.97 → 0.90 for Gemini embeddings (different embedding space, lower baseline similarity for rephrasings).
- Postgres host port = **5433** (host machine has native Postgres on 5432).
- **Observability stack = SQL-over-Postgres + Prometheus-format `/metrics` endpoint. No Prometheus server, no Grafana.** Rationale:
  - At current scale (single service, <1000 rps), `usage_logs` IS the time-series. `date_trunc` + `percentile_cont` produce every operational chart Grafana would.
  - Running Grafana locally adds portal-based dashboard authoring pain (same UX on cloud, ruled out).
  - `/metrics` still serves standard Prometheus text (via `prometheus_client.generate_latest`) — external scrapers can consume when scale demands.
  - No `psutil` / system metrics endpoint — internal tool, rarely needed.
  - Scale-out plan when it matters: add nightly Celery Beat rollup of `usage_logs` → `usage_daily`, delete raw >30d.
- Phase 13 (Prometheus + Grafana) **deliberately skipped**; replaced by Phase 14 dashboard extensions.

## CV framing lines (copy into README/resume when Phase 18 lands)
- **Short:** *"real-time ops dashboard over structured request logs."*
- **Longer:** *"Designed a single-service observability stack using request-level structured logs as the source of truth — p50/p95/p99 latency, error + rate-limit rates, per-provider token breakdown, and cost attribution — avoiding the operational cost of a separate time-series database at current scale."*
- **Signal sentence to tack on:** *"Exposes standard Prometheus `/metrics`; designed to be scraped externally when scale demands it."*
- `pgvector/pgvector:pg16` pre-installs the extension; still need `CREATE EXTENSION vector` per-db.
- App runs on host in dev (fast reloads); containerized only in prod (Phase 15).
- `expire_on_commit=False` on session to keep ORM objects usable after commit.
- SQLAlchemy `echo` tied to `APP_DEBUG`.
- `msgpack` not yet chosen for Redis cache serialization — TBD in Phase 8.
- Streaming responses: OUT for v1.
- Anthropic provider: stub only until Phase pushes `ENABLE_ANTHROPIC=true`.

## Production deploy (Phases 15 + 17 — Codespaces target)

### Strategy
Single GitHub Codespace running the full stack via `docker-compose.prod.yml`. No VPS / nginx-on-host / certbot — Codespaces auto-fronts forwarded ports with HTTPS. Demo URL: `https://<codespace-name>-80.app.github.dev` (port visibility set to public). Codespace sleeps after ~30 min idle; this is acceptable for a CV demo (start before showing).

### Files
- `docker/Dockerfile` — multi-stage. **Stage 1 (builder)**: `python:3.11-slim`, build-essential, `pip wheel` to `/wheels`. **Stage 2 (runtime)**: slim, non-root user `app` (uid 1000), `pip install --no-index --find-links=/wheels`. Healthcheck on `/health`. EXPOSE 8000. Same image for API and worker (branched by `entrypoint.sh`).
- `docker/entrypoint.sh` — `case` on `$1` (or `$ROLE`):
  - `api` → `gunicorn -k uvicorn.workers.UvicornWorker -w $WEB_CONCURRENCY -b 0.0.0.0:8000 app.main:app`
  - `worker` → `celery -A app.worker.celery_app worker --pool=prefork --concurrency=$CELERY_CONCURRENCY`
  - `migrate` → `alembic upgrade head` (one-shot)
- `dashboard/Dockerfile` — node:22-alpine builds `dist/`; nginx:1.27-alpine serves `dist/` AND reverse-proxies `/v1` `/admin` `/health` `/metrics` to `api:8000`. Build step strips any `.env*` so the bundle uses same-origin relative paths (no CORS in prod).
- `nginx/prod.conf` — single vhost on :80. Hashed `/assets/` → 30d immutable cache. SPA fallback `try_files $uri $uri/ /index.html`. `client_max_body_size 20m` for batch embeddings.
- `docker-compose.prod.yml` — services: postgres, redis, rabbitmq (data volumes + healthchecks) → migrate (one-shot via `service_completed_successfully`) → api + worker (env_file `.env.prod`) → web (nginx, only port published: `80:80`). API is **internal-only** (`expose: 8000`) — exposed via web/nginx.
- `.env.prod.example` — committed template; service-name hosts (`postgres`, `redis`, `rabbitmq`), `APP_ENV=prod`, `APP_DEBUG=false`, runtime knobs (`WEB_CONCURRENCY`, `CELERY_CONCURRENCY`).
- `.env.prod` — git-ignored real secrets. Copy from example before `up`.
- `.devcontainer/devcontainer.json` — Codespaces config. Base ubuntu-22.04 + Python 3.11 + Node 22 + docker-in-docker features. Port forwards: 80 (public), 8000 / 5173 / 15672 (private). `postCreateCommand` creates venv + pip install + dashboard `npm ci`.

### Codespaces deploy commands
```bash
# inside codespace, one-time:
cp .env.prod.example .env.prod
nano .env.prod                 # paste real GEMINI_API_KEY etc.

# build + start everything:
docker compose -f docker-compose.prod.yml up -d --build

# create an admin key:
docker compose -f docker-compose.prod.yml exec api \
  python scripts/create_api_key.py --name "demo-admin" --admin

# tail logs:
docker compose -f docker-compose.prod.yml logs -f api worker

# Then in Codespaces UI → Ports tab → port 80 → set Visibility = Public.
# Open the forwarded URL → dashboard loads, API responds.
```

### What changed vs the original VPS plan
- No host-side nginx, no certbot, no UFW — Codespaces handles SSL + edge.
- No SSH / `adduser` / DNS — N/A.
- Single port published (80). 8000 internal-only via `expose:`.
- Migration runs once via dedicated `migrate` service with `service_completed_successfully` dependency.

### CV framing
*"Containerized full stack (Python + React) with multi-stage builds, single-image API/worker via entrypoint role-branching, Postgres + Redis + RabbitMQ orchestration via Docker Compose, deployed on a free dev container with same-origin nginx routing."*

## CI / CD (GitHub Actions)

### Honest constraint
Codespaces is a dev environment, not a deploy target. True "auto-deploy on merge" requires a real server. Current setup: **CI on every push + GHCR image publish on main merge + manual pull-in-codespace**. A real deploy-on-merge step slots in when there's a VPS.

### `.github/workflows/ci.yml`
- Triggers: all pushes to `main` + all PRs.
- Job `backend`: spins up `pgvector/pgvector:pg16` + `redis:7-alpine` service containers. Installs `requirements-dev.txt`, runs `ruff check .`, runs `alembic upgrade head`, runs `pytest -q`.
- Job `dashboard`: Node 22, `npm install`, `npm run build` (type-checks + bundles).
- Concurrency: cancels superseded runs on the same ref.
- Env in CI: `SEMANTIC_CACHE_ENABLED=false`, dummy `GEMINI_API_KEY` / `OPENAI_API_KEY` (embedders never hit external APIs in tests).

### `.github/workflows/publish.yml`
- Triggers: push to `main`, or manual `workflow_dispatch`.
- Matrix builds two images → `ghcr.io/<owner>/<repo>/gateway-api` and `gateway-web`.
- Tags: git SHA + `latest`. Uses `docker/build-push-action` with GHA cache (`type=gha`) for fast rebuilds.
- `permissions: packages: write` — uses built-in `GITHUB_TOKEN`, no PAT needed.

### `scripts/deploy.sh`
One-shot run inside the Codespace (or any Docker host with this repo):
1. `git pull --ff-only`
2. assert `.env.prod` exists
3. `docker compose -f docker-compose.prod.yml up -d --build`
4. run `migrate` service (idempotent)
5. `docker compose ps`

### Portfolio story
- *"CI runs ruff + alembic + pytest on every PR, containers built and pushed to GHCR on main; deploy is a one-command script."*
- When there's a VPS: add a deploy job using `appleboy/ssh-action` that runs the same `deploy.sh` on the server. ~10 lines.

## Tests (Phase 16 — core only, not exhaustive)
`pytest-asyncio 1.3.0` (session-scoped test loop + fixture loop, configured via `pyproject.toml`).

- `tests/conftest.py` — sets `SEMANTIC_CACHE_ENABLED=false` for tests; `reset_state` autouse fixture FLUSHDB + TRUNCATEs `usage_logs`, `jobs`, `cached_responses`, `semantic_cache_entries` between tests; `client` yields `httpx.AsyncClient(transport=ASGITransport(app))`; `test_key` seeds a scoped non-admin ApiKey and deletes it (+ its usage/jobs) on teardown. `api_keys` is otherwise preserved.
- **Unit** (no infra): `test_cache_keys.py` (hash determinism / field sensitivity / last_user_message), `test_auth_keys.py` (generate/verify/extract_prefix), `test_pricing.py` (known/unknown model), `test_router.py` (retry→fallback on server error, auth=fatal-no-fallback, all-exhausted).
- **Integration** (dev Postgres + Redis up): `test_chat_completions.py` — 401 missing auth, 403 bad key, 200 + exact-cache hit on repeat (mocked router via `monkeypatch.setattr("app.api.v1.chat.get_router", ...)` — plain-function call, not FastAPI dep, so `dependency_overrides` does NOT work), 422 validation.
- Current: **18 passed**. Noise: Redis `__del__` "Event loop is closed" at process exit is cosmetic.

## Load (Phase 18 — post-deploy)
`tests/load/locustfile.py`. Mix: 60% chat (~30% unseen prompts to exercise cache), 20% sync `/v1/embeddings`, 10% async batch + job poll, 10% `/admin/stats/overview`. Env: `GATEWAY_API_KEY` (required), `GATEWAY_ADMIN_KEY` (optional), `CHAT_MODEL`, `EMBED_MODEL`, `EMBED_PROVIDER`. Run:
```
locust -f tests/load/locustfile.py --host https://api.yourdomain.com --users 50 --spawn-rate 5 --run-time 10m --headless --csv results
```

## Commands cheatsheet
```
# Infra
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml ps
docker exec -it gateway-postgres psql -U gateway -d gateway

# App
.venv/Scripts/python.exe -m uvicorn app.main:app --reload

# DB
.venv/Scripts/alembic.exe revision --autogenerate -m "msg"
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/alembic.exe downgrade -1

# Keys (scripts need PYTHONPATH=.)
PYTHONPATH=. .venv/Scripts/python.exe scripts/create_api_key.py --name "user" [--email x@y] [--admin]
```

## Seeded keys (dev only — rotate before prod)
- admin: `sk-gw-live-q5O6ES0VSCMOz14eLpHqgqxY1rT4py6y` (id `ad231763-04ae-44ef-9a10-1f0ae9930d6e`, email `dev@glacien.ai`)
- user:  `sk-gw-live-XgoWz0UJEqJ-h24Rcc3L7xZvLqHoqBO7` (id `359c863d-2d2b-41b3-861b-a95ae5ddeb30`)

## Phase progress
- [x] 0 prerequisites
- [x] 1 scaffolding + venv (requirements*, .gitignore)
- [x] 2 folder structure + .env.example
- [x] 3 docker-compose.dev.yml (pg+redis+rabbit)
- [x] 4 FastAPI skeleton (config, logging, main, /health, /metrics stub)
- [x] 5 DB layer + alembic initial migration (5 tables + pgvector + IVFFlat idx)
- [x] 6 API key auth (argon2, Bearer, admin dep, CLI, 2 seeded keys)
- [x] 7 Provider layer (openai, gemini, anthropic stub, router w/ retry+fallback)
- [x] 8 Exact cache (Redis SETEX, json-serialized NormalizedResponse)
- [x] 9 Semantic cache (pgvector cosine_distance lookup + idempotent store)
- [x] 10 /v1/chat/completions (auth→ratelimit stub→exact→semantic→router, UsageLog, metrics, OpenAI-shaped response)
- [x] 11 Rate limiting (Redis sliding-window, per-minute + per-day, overrides)
- [x] 12 Celery worker + jobs (batch_embeddings task, sync `/v1/embeddings`, async `/v1/embeddings/batch`, `/v1/jobs/{id}`)
- [x] 13 Observability (**SQL-over-Postgres dashboards + Prometheus `/metrics` endpoint, no Prometheus server / Grafana** — rationale in Decisions)
- [x] 14 Dashboard + admin endpoints (Vite/React/TS/Tailwind/RQ/Recharts; /admin/keys /admin/usage /admin/stats/overview /admin/jobs)
- [x] 15 Prod stack (Dockerfile + entrypoint + dashboard image + nginx + docker-compose.prod.yml + .env.prod.example)
- [x] 16 Tests — 17 unit + 4 integration (chat auth+cache path mocked). Locust load test staged for post-deploy.
- [x] 17 Codespaces deploy (.devcontainer/devcontainer.json — public port 80, single-origin nginx routing, no VPS/TLS/DNS)
- [x] CI/CD — GH Actions: `ci.yml` (ruff + alembic + pytest + dashboard build) on PR/main; `publish.yml` pushes both images to GHCR on main. `scripts/deploy.sh` pulls + rebuilds in-Codespace.
- [ ] 15 Nginx + prod Dockerfile + prod compose
- [ ] 16 Tests
- [ ] 17 VPS deploy + TLS
- [ ] 18 Load test + README
