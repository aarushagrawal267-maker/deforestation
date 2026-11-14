"""Export Dynamic World probabilities for a training region (optional; needs Google Earth Engine).

Dynamic World is only available through Earth Engine. Requirements:
  * a (free, noncommercial) Earth Engine account and a Google Cloud project
  * pip install earthengine-api ; earthengine authenticate
Usage:
  python scripts/export_dynamic_world.py --region rondonia_ariquemes --project YOUR_GCP_PROJECT

The script finds the Dynamic World image matching the region's Sentinel-2 acquisition date,
exports its 9 probability bands on the region grid to Google Drive (folder 'sylva'),
and you then copy the GeoTIFF to data/regions/<region>/dynamic_world.tif and rebuild labels
(python -m forestwatch.cli build-regions --only <region>).
Dynamic World labels are model outputs, not independent ground truth.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANDS = ["water", "trees", "grass", "flooded_vegetation", "crops", "shrub_and_scrub", "built", "bare", "snow_and_ice"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True)
    ap.add_argument("--project", required=True, help="Google Cloud project registered for Earth Engine")
    a = ap.parse_args()
    try:
        import ee
    except ImportError:
        print("earthengine-api is not installed: pip install earthengine-api", file=sys.stderr)
        return 1
    meta = json.loads((ROOT / "data" / "regions" / a.region / "region.json").read_text())
    ee.Initialize(project=a.project)
    date = meta["acquired"][0][:10]
    minx, miny, maxx, maxy = meta["bbox"]
    geom = ee.Geometry.Rectangle([minx, miny, maxx, maxy])
    col = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterBounds(geom)
        .filterDate(ee.Date(date), ee.Date(date).advance(1, "day"))
        .select(BANDS)
    )
    n = col.size().getInfo()
    if n == 0:
        print(f"No Dynamic World image for {date}; Dynamic World skips some scenes.", file=sys.stderr)
        return 2
    grid = meta["grid"]
    task = ee.batch.Export.image.toDrive(
        image=col.mosaic().toFloat(),
        description=f"sylva_dw_{a.region}",
        folder="sylva",
        fileNamePrefix="dynamic_world",
        crs=grid["crs"],
        crsTransform=grid["transform"],
        dimensions=f"{grid['width']}x{grid['height']}",
        maxPixels=1e9,
    )
    task.start()
    print(f"Export started ({n} image(s) on {date}). Download from Google Drive /sylva when complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
