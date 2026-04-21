from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from app.api.v1.chat import router as chat_router
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


app.include_router(chat_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    return ""
