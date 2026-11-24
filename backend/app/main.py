"""Sylva FastAPI application. API docs: http://localhost:8000/docs"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from forestwatch.settings import configure_gdal_env, get_settings

from .api.routers import analyses, aois, catalog, datasets, models, products, system, tiles
from .db.init import init_db
from .services.registry import import_cli_models


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_gdal_env()
    init_db()
    import_cli_models()
    yield


app = FastAPI(
    title="Sylva - Forest Change Intelligence API",
    description=(
        "Independent educational/research platform. Retrieves available Copernicus Sentinel-2 L2A acquisitions, "
        "segments tree cover with a U-Net trained from scratch, and flags *potential* forest-cover change between "
        "observation dates. Detected changes are not verified deforestation events."
    ),
    version="1.0.0",
    lifespan=lifespan,
    # when the frontend is served from the same origin, its /docs page must not clash with Swagger,
    # and Swagger must not shadow the GET /api/docs endpoint that lists the methodology documents
    docs_url="/api/swagger" if get_settings().frontend_dist else "/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json" if get_settings().frontend_dist else "/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (system, aois, catalog, products, tiles, datasets, models, analyses):
    app.include_router(r.router, prefix="/api")


_dist = get_settings().frontend_dist
if _dist:
    _dist = Path(_dist).resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        """Serve the built frontend; unknown paths fall back to index.html (client-side routing)."""
        if path.startswith("api/"):
            raise HTTPException(404)
        f = (_dist / path).resolve()
        if path and f.is_file() and f.is_relative_to(_dist):
            return FileResponse(f)
        return FileResponse(_dist / "index.html")
