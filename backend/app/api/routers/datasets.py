from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from forestwatch.labels.classes import CLASSES, DYNAMIC_WORLD_MAP, WORLDCOVER_MAP, WORLDCOVER_NAMES
from forestwatch.labels.reference import DATASET_INFO
from forestwatch.preprocessing.bands import describe_bands
from forestwatch.preprocessing.masking import QUALITY_NAMES, SCL_NAMES
from forestwatch.regions import list_regions, load_region_config
from forestwatch.settings import get_settings

from ...db.models import Product
from ...db.session import get_db
from ...jobs.queue import enqueue
from ...services import serialize as S

router = APIRouter(prefix="/datasets", tags=["datasets"])

SENTINEL2_INFO = {
    "name": "Copernicus Sentinel-2 MSI Level-2A (Collection 1)",
    "provider": "European Space Agency (ESA) / Copernicus; distributed via Earth Search (Element 84, AWS Open Data)",
    "official_source": "https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-2",
    "versions": "Collection 1 L2A (processing baseline 05.xx); legacy L2A used only to fill Collection-1 gaps, baselines harmonised",
    "role": "Primary input imagery for training, segmentation and change detection",
    "access": "STAC API https://earth-search.aws.element84.com/v1, collection sentinel-2-c1-l2a; COG band assets (no credentials)",
    "resolution": "10 m (B2, B3, B4, B8), 20 m (B5, B6, B7, B8A, B11, B12, SCL), 60 m (not used)",
    "crs": "UTM (WGS84) of each MGRS tile; Sylva reprojects onto the AOI's UTM 10 m grid",
    "temporal_coverage": "2015-06-27 to present (about 5-day revisit at the equator with two satellites); "
    "systematic global L2A from late 2018, earlier years via Collection-1 reprocessing where available",
    "licence": "Free, full and open (Copernicus data policy). Attribution: 'Contains modified Copernicus Sentinel data [year]'",
    "radiometry": "Surface reflectance = DN x 1e-4 - 0.1 (Collection 1, processing baseline 05.xx, consistent across the archive)",
    "limitations": [
        "Scene Classification Layer (SCL) cloud and shadow detection is imperfect; masks are dilated by 40 m.",
        "20 m bands resampled to 10 m do not contain 10 m information.",
        "Persistent cloud cover in the humid tropics limits valid observations.",
        "Retrieves available acquisitions; this is not a real-time feed.",
    ],
}


@router.get("")
def datasets(db: Session = Depends(get_db)):
    n_obs = db.scalar(select(func.count()).select_from(Product))
    return {
        "sentinel2": {**SENTINEL2_INFO, "observations_ingested": n_obs},
        "worldcover": DATASET_INFO["worldcover"],
        "hansen": DATASET_INFO["hansen"],
        "dynamic_world": {
            "name": "Dynamic World V1",
            "provider": "Google / World Resources Institute",
            "versions": "GOOGLE/DYNAMICWORLD/V1",
            "resolution": "10 m",
            "licence": "CC BY 4.0",
            "source": "https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1",
            "role": "Optional same-date weak labels (probabilities) used for label agreement filtering",
            "status": "Not configured: requires a Google Earth Engine account. Run scripts/export_dynamic_world.py "
            "and place dynamic_world.tif in a region folder to enable.",
            "limitations": [
                "Derived from Sentinel-2 by a neural network: not independent ground truth.",
                "A model trained to reproduce it cannot claim independent validation.",
            ],
        },
        "bands": describe_bands(),
        "scl_classes": SCL_NAMES,
        "quality_codes": QUALITY_NAMES,
        "classes": CLASSES,
        "worldcover_mapping": [
            {"code": k, "name": WORLDCOVER_NAMES.get(k, "No data"), "sylva_class": v} for k, v in WORLDCOVER_MAP.items()
        ],
        "dynamic_world_mapping": DYNAMIC_WORLD_MAP,
    }


@router.get("/regions")
def regions():
    rd = get_settings().path("regions")
    built = {r["name"]: r for r in list_regions(rd)}
    cfg = load_region_config()
    out = []
    for spec in cfg["regions"]:
        r = built.get(spec["name"])
        out.append({**spec, "built": r is not None, **(r or {})})
    return {"label_year": cfg["label_year"], "size_deg": cfg["size_deg"], "regions": out}


@router.get("/regions/{name}")
def region(name: str):
    for r in list_regions(get_settings().path("regions")):
        if r["name"] == name:
            return r
    raise HTTPException(404, "Region not built")


@router.post("/regions/build", status_code=202)
def build(regions: list[str] | None = None, db: Session = Depends(get_db)):
    """Queue a job that downloads imagery + reference labels for training regions."""
    return S.job(enqueue(db, "build_regions", {"regions": regions or []}))
