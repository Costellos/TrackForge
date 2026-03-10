import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trackforge.config import get_settings
from trackforge.api.v1.router import router as v1_router

settings = get_settings()
log = structlog.get_logger()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(v1_router, prefix="/api/v1")

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()
