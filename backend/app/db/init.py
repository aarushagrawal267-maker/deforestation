"""Database initialisation and default records."""

from __future__ import annotations

from sqlalchemy import select

from forestwatch.geo.grid import Grid, bbox_geojson, geodesic_area_km2

from .models import AOI, Setting
from .session import Base, SessionLocal, get_engine

DEFAULT_AOI = {
    "name": "Novo Progresso (BR-163), Para, Brazil",
    "description": "Default monitoring area on the BR-163 deforestation frontier. Held out from U-Net training "
    "(the overlapping 2021 region is a test region).",
    "bbox": [-55.47, -7.14, -55.29, -6.96],
}


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)

    Base.metadata.create_all(get_engine())
    with SessionLocal() as db:
        if not db.scalars(select(AOI).limit(1)).first():
            bbox = tuple(DEFAULT_AOI["bbox"])
            geom = bbox_geojson(bbox)
            aoi = AOI(
                name=DEFAULT_AOI["name"],
                description=DEFAULT_AOI["description"],
                bbox=list(bbox),
                geometry=geom,
                grid=Grid.from_bbox_lonlat(bbox).to_dict(),
                area_km2=geodesic_area_km2(geom),
            )
            db.add(aoi)
            db.flush()
            db.merge(Setting(key="active_aoi_id", value=aoi.id))
        db.commit()


def get_setting(db, key: str, default=None):
    s = db.get(Setting, key)
    return s.value if s else default


def set_setting(db, key: str, value) -> None:
    db.merge(Setting(key=key, value=value))
    db.commit()
