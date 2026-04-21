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
EMBEDDING_MODEL=text-embedding-3-small
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
- **semantic_cache_entries** — id int pk, request_hash FK→cached_responses.request_hash (idx), **embedding VECTOR(1536)** with IVFFlat cosine idx (lists=100), prompt_text, model (idx), created_at.
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
`@lru_cache get_router()` → single `ProviderRouter()`. `@lru_cache get_embedder()` → single `OpenAIProvider()` used only for `embed()`.

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

## Rate limiting (planned)
Redis sliding-window sorted set `ratelimit:{api_key_id}:{window}`, score=timestamp. Per-minute + per-day. Overrides from `rate_limit_overrides` JSON. Applied before cache check. 429 + `Retry-After`.

## Celery (planned)
`app/worker/celery_app.py` with RabbitMQ broker + Redis result backend. Tasks: `batch_embeddings_task`. Windows dev: `celery … --pool=solo`. Prod linux: `--pool=prefork`.

## Prometheus (planned)
Counters: `gateway_requests_total{endpoint,status,provider,cache_hit}`, `gateway_tokens_total{provider,kind}`, `gateway_cost_usd_total{provider,api_key_prefix}`, `gateway_provider_errors_total`, `gateway_rate_limit_rejections_total`, `gateway_cache_exact_hits_total/misses_total`. Histogram: `gateway_request_duration_seconds`.

## Decisions / notes
- Postgres host port = **5433** (host machine has native Postgres on 5432).
- `pgvector/pgvector:pg16` pre-installs the extension; still need `CREATE EXTENSION vector` per-db.
- App runs on host in dev (fast reloads); containerized only in prod (Phase 15).
- `expire_on_commit=False` on session to keep ORM objects usable after commit.
- SQLAlchemy `echo` tied to `APP_DEBUG`.
- `msgpack` not yet chosen for Redis cache serialization — TBD in Phase 8.
- Streaming responses: OUT for v1.
- Anthropic provider: stub only until Phase pushes `ENABLE_ANTHROPIC=true`.

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
- [ ] 11 Rate limiting
- [ ] 12 Celery worker + jobs
- [ ] 13 Prometheus + Grafana
- [ ] 14 Dashboard (React+Vite)
- [ ] 15 Nginx + prod Dockerfile + prod compose
- [ ] 16 Tests
- [ ] 17 VPS deploy + TLS
- [ ] 18 Load test + README
