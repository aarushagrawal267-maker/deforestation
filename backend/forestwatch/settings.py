"""Central configuration for the forestwatch core library and the Sylva backend.

All values can be overridden with environment variables prefixed ``SYLVA_``
(see ``.env.example`` at the repository root).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SYLVA_",
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = REPO_ROOT / "data"
    database_url: str | None = None

    # Imagery provider
    stac_url: str = "https://earth-search.aws.element84.com/v1"
    stac_collection: str = "sentinel-2-c1-l2a"

    # Optional Copernicus Data Space Ecosystem credentials (never sent to the frontend).
    # SecretStr keeps the password out of repr(), logs and tracebacks; read it with
    # .get_secret_value() only where it is sent to the CDSE token endpoint.
    cdse_username: str | None = None
    cdse_password: SecretStr | None = None

    # Safety limits
    max_aoi_km2: float = 2500.0
    device: str = "auto"  # auto | cpu | cuda

    # Single-port deployment (e.g. a container): serve the built frontend from this directory
    frontend_dist: Path | None = None
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'sylva.sqlite').as_posix()}"

    def path(self, *parts: str) -> Path:
        p = self.data_dir.joinpath(*parts)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s


def configure_gdal_env() -> None:
    """GDAL options for efficient, anonymous reads of public cloud-optimised GeoTIFFs."""
    import os

    defaults = {
        "AWS_NO_SIGN_REQUEST": "YES",
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF,.tiff",
        "GDAL_HTTP_MAX_RETRY": "5",
        "GDAL_HTTP_RETRY_DELAY": "2",
        "GDAL_HTTP_MULTIPLEX": "YES",
        "VSI_CACHE": "TRUE",
    }
    ca = "/root/.ccr/ca-bundle.crt"
    if os.path.exists(ca) and "CURL_CA_BUNDLE" not in os.environ:
        defaults["CURL_CA_BUNDLE"] = ca
    for k, v in defaults.items():
        os.environ.setdefault(k, v)
