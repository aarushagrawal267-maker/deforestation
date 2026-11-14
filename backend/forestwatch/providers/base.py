"""Imagery provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class SceneInfo:
    id: str
    provider: str
    collection: str
    datetime: datetime
    platform: str
    cloud_cover: float | None
    mgrs_tile: str | None
    processing_baseline: str | None
    bbox: list[float]
    geometry: dict
    assets: dict[str, str]  # asset key -> href
    thumbnail: str | None = None
    properties: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["datetime"] = self.datetime.isoformat()
        return d


class Provider(ABC):
    name: str

    @abstractmethod
    def search(
        self,
        bbox: tuple[float, float, float, float],
        start: str,
        end: str,
        max_cloud: float = 60.0,
        limit: int = 50,
    ) -> list[SceneInfo]: ...

    @abstractmethod
    def get(self, scene_id: str) -> SceneInfo: ...
