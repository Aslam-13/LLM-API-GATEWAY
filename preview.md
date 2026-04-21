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

## Cache pipeline (planned flow, not yet wired)
per request: exact (Redis, ~1ms hash-match on (model+messages+temp)) → semantic (embed user msg, pgvector cosine search, threshold `SEMANTIC_CACHE_THRESHOLD` default 0.97) → provider (router with fallback order + tenacity retry). Write both `CachedResponse` row and `SemanticCacheEntry` on miss→success.

## Auth (planned)
`Authorization: Bearer sk-gw-live-{32}`. Key format: `sk-gw-live-{first6}…`; prefix stored plain for lookup, full key argon2-hashed. `require_api_key()` and `require_admin_key()` FastAPI dependencies. CLI: `scripts/create_api_key.py` prints plaintext once.

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
```

## Phase progress
- [x] 0 prerequisites
- [x] 1 scaffolding + venv (requirements*, .gitignore)
- [x] 2 folder structure + .env.example
- [x] 3 docker-compose.dev.yml (pg+redis+rabbit)
- [x] 4 FastAPI skeleton (config, logging, main, /health, /metrics stub)
- [x] 5 DB layer + alembic initial migration (5 tables + pgvector + IVFFlat idx)
- [ ] 6 API key auth
- [ ] 7 Provider layer (openai, gemini, anthropic stub, router)
- [ ] 8 Exact cache (Redis)
- [ ] 9 Semantic cache (pgvector)
- [ ] 10 /v1/chat/completions
- [ ] 11 Rate limiting
- [ ] 12 Celery worker + jobs
- [ ] 13 Prometheus + Grafana
- [ ] 14 Dashboard (React+Vite)
- [ ] 15 Nginx + prod Dockerfile + prod compose
- [ ] 16 Tests
- [ ] 17 VPS deploy + TLS
- [ ] 18 Load test + README
