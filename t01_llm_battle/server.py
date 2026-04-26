import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import init_db, DB_PATH
from .pricing import get_cache_info, refresh_llm_pricing
from .routers.battles import router as battles_router
from .routers.keys import router as keys_router
from .routers.runs import router as runs_router
from .routers.sources import router as sources_router
from .routers.fighters import router as fighters_router, providers_router
from .routers.providers import router as provider_mgmt_router
from .routers.templates import router as templates_router

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Auto-refresh LLM pricing if no user cache exists
    cache = get_cache_info()
    if cache["age_seconds"] is None:
        asyncio.create_task(_background_pricing_refresh())
    yield


async def _background_pricing_refresh():
    try:
        result = await asyncio.to_thread(refresh_llm_pricing)
        total = sum(result.values())
        log.info("Auto-refreshed LLM pricing: %d models", total)
    except Exception as e:
        log.warning("Failed to auto-refresh LLM pricing: %s", e)


def create_app(db_path=DB_PATH) -> FastAPI:
    app = FastAPI(title="t01-llm-battle", lifespan=lifespan)

    app.include_router(battles_router)
    app.include_router(keys_router)
    app.include_router(runs_router)
    app.include_router(sources_router)
    app.include_router(fighters_router)
    app.include_router(providers_router)
    app.include_router(provider_mgmt_router)
    app.include_router(templates_router)

    # Health check
    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    # Mount static files (SPA)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists() and any(static_dir.iterdir()):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
