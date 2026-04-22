from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.admin.jobs import router as admin_jobs_router
from app.api.admin.keys import router as admin_keys_router
from app.api.admin.stats import router as admin_stats_router
from app.api.admin.usage import router as admin_usage_router
from app.api.v1.chat import router as chat_router
from app.api.v1.embeddings import router as embeddings_router
from app.api.v1.jobs import router as jobs_router
from app.config import get_settings
from app.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log = get_logger(__name__)
    settings = get_settings()
    log.info("gateway.startup", env=settings.app_env, debug=settings.app_debug)
    yield
    log.info("gateway.shutdown")


app = FastAPI(
    title="LLM API Gateway",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(embeddings_router)
app.include_router(jobs_router)
app.include_router(admin_keys_router)
app.include_router(admin_usage_router)
app.include_router(admin_stats_router)
app.include_router(admin_jobs_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    return ""
