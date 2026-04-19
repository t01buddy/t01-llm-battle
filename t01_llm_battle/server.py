from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import init_db, DB_PATH
from .routers.battles import router as battles_router
from .routers.keys import router as keys_router
from .routers.runs import router as runs_router
from .routers.sources import router as sources_router
from .routers.fighters import router as fighters_router, providers_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


def create_app(db_path=DB_PATH) -> FastAPI:
    app = FastAPI(title="t01-llm-battle", lifespan=lifespan)

    app.include_router(battles_router)
    app.include_router(keys_router)
    app.include_router(runs_router)
    app.include_router(sources_router)
    app.include_router(fighters_router)
    app.include_router(providers_router)

    # Health check
    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    # Mount static files (SPA)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists() and any(static_dir.iterdir()):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
