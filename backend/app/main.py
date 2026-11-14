"""Sylva FastAPI application. API docs: http://localhost:8000/docs"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (system, aois, catalog, products, tiles, datasets, models, analyses):
    app.include_router(r.router, prefix="/api")
