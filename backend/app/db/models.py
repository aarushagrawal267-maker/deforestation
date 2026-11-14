from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .session import Base


def now() -> datetime:
    return datetime.now(UTC)


def short_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


class AOI(Base):
    __tablename__ = "aois"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: short_id("aoi_"))
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    bbox: Mapped[list] = mapped_column(JSON)
    geometry: Mapped[dict] = mapped_column(JSON)
    grid: Mapped[dict] = mapped_column(JSON)
    area_km2: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Product(Base):
    """An analysis-ready observation (single scene, same-day mosaic or composite) on an AOI grid."""

    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: short_id("obs_"))
    aoi_id: Mapped[str] = mapped_column(ForeignKey("aois.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String)
    scene_ids: Mapped[list] = mapped_column(JSON)
    acquired: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acquired_list: Mapped[list] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String)
    collection: Mapped[str] = mapped_column(String)
    platform: Mapped[str | None] = mapped_column(String, nullable=True)
    scene_cloud_cover: Mapped[float | None] = mapped_column(Float, nullable=True)
    valid_fraction: Mapped[float] = mapped_column(Float)
    quality_summary: Mapped[dict] = mapped_column(JSON)
    path: Mapped[str] = mapped_column(String)
    meta: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    aoi: Mapped[AOI] = relationship()


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: short_id("exp_"))
    name: Mapped[str] = mapped_column(String)
    config: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="created")
    job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    checkpoint: Mapped[str | None] = mapped_column(String, nullable=True)
    checkpoint_sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    best_val_miou: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_epoch: Mapped[int | None] = mapped_column(Integer, nullable=True)
    n_params: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device: Mapped[str | None] = mapped_column(String, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    epochs: Mapped[list[EpochMetric]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", order_by="EpochMetric.epoch"
    )


class EpochMetric(Base):
    __tablename__ = "epoch_metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    epoch: Mapped[int] = mapped_column(Integer)
    train_loss: Mapped[float] = mapped_column(Float)
    val_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    val_miou: Mapped[float | None] = mapped_column(Float, nullable=True)
    val_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    val_per_class_iou: Mapped[list] = mapped_column(JSON, default=list)
    lr: Mapped[float] = mapped_column(Float)
    seconds: Mapped[float] = mapped_column(Float)
    experiment: Mapped[Experiment] = relationship(back_populates="epochs")


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: short_id("eval_"))
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    regions: Mapped[list] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    path: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="queued")
    job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SegmentationRun(Base):
    __tablename__ = "segmentation_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: short_id("seg_"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"))
    status: Mapped[str] = mapped_column(String, default="queued")
    job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    path: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    product: Mapped[Product] = relationship()


class ChangeRun(Base):
    __tablename__ = "change_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: short_id("chg_"))
    aoi_id: Mapped[str] = mapped_column(ForeignKey("aois.id", ondelete="CASCADE"))
    before_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    after_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    extra_ids: Mapped[list] = mapped_column(JSON, default=list)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="queued")
    job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    path: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    aoi: Mapped[AOI] = relationship()
    before: Mapped[Product] = relationship(foreign_keys=[before_id])
    after: Mapped[Product] = relationship(foreign_keys=[after_id])
    regions: Mapped[list[ChangeRegion]] = relationship(back_populates="run", cascade="all, delete-orphan")


class ChangeRegion(Base):
    __tablename__ = "change_regions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("change_runs.id", ondelete="CASCADE"))
    change_type: Mapped[str] = mapped_column(String)
    evidence_level: Mapped[str] = mapped_column(String)
    area_ha: Mapped[float] = mapped_column(Float)
    area_uncertainty_ha: Mapped[float] = mapped_column(Float)
    centroid_lon: Mapped[float] = mapped_column(Float)
    centroid_lat: Mapped[float] = mapped_column(Float)
    properties: Mapped[dict] = mapped_column(JSON)
    geometry: Mapped[dict] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String, default="unreviewed")
    analyst_notes: Mapped[str] = mapped_column(Text, default="")
    run: Mapped[ChangeRun] = relationship(back_populates="regions")


class Export(Base):
    __tablename__ = "exports"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: short_id("exp-"))
    source_type: Mapped[str] = mapped_column(String)
    source_id: Mapped[str] = mapped_column(String)
    format: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: short_id("job_"))
    type: Mapped[str] = mapped_column(String)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="queued")  # queued|running|succeeded|failed|cancelled
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")
    log: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict | str | None] = mapped_column(JSON, nullable=True)
