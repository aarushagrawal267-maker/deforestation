"""API tests on an isolated database, using the real Sentinel-2 fixture observations."""

import json
import shutil

import torch
from fastapi.testclient import TestClient

from forestwatch.ml.unet import UNet
from forestwatch.preprocessing.bands import BAND_NAMES


def _client():
    from app.main import app

    return TestClient(app)


def _register_fixture_products(tmp_data_dir, fixture_products, aoi_id):
    from app.db.session import SessionLocal
    from app.jobs.tasks import _register_product

    ids = []
    with SessionLocal() as db:
        for i, fp in enumerate(fixture_products):
            dst = tmp_data_dir / "products" / aoi_id / f"obs_fx{i}"
            shutil.copytree(fp, dst)
            meta = json.loads((dst / "meta.json").read_text())
            _register_product(db, aoi_id, f"obs_fx{i}", dst, meta, "earth-search")
            ids.append(f"obs_fx{i}")
    return ids


def _register_model(tmp_data_dir):
    from app.db.init import set_setting
    from app.db.models import Experiment
    from app.db.session import SessionLocal

    m = UNet(10, 5, 8, 2)
    p = tmp_data_dir / "models" / "tiny" / "best.pt"
    p.parent.mkdir(parents=True)
    torch.save(
        {
            "state_dict": m.state_dict(),
            "model_config": m.config,
            "bands": BAND_NAMES,
            "norm_stats": {"mean": [0.05] * 10, "std": [0.05] * 10},
            "class_names": list("abcde"),
            "temperature": 1.0,
        },
        p,
    )
    with SessionLocal() as db:
        e = Experiment(name="tiny-untrained-test-model", config={"bands": BAND_NAMES, "test_regions": [], "train_regions": []}, status="completed", checkpoint=str(p))
        db.add(e)
        db.commit()
        set_setting(db, "active_experiment_id", e.id)
        return e.id


def test_health_system_and_docs(tmp_data_dir):
    with _client() as c:
        assert c.get("/api/health").json() == {"status": "ok"}
        s = c.get("/api/system").json()
        assert s["device"] in ("cpu", "cuda") and "gdal_version" in s
        assert c.get("/docs").status_code == 200
        assert c.get("/openapi.json").json()["info"]["title"].startswith("Sylva")


def test_default_aoi_and_validation(tmp_data_dir):
    with _client() as c:
        aois = c.get("/api/aois").json()
        assert len(aois) == 1 and "Novo Progresso" in aois[0]["name"]
        assert aois[0]["grid"]["crs"] == "EPSG:32721"
        r = c.post("/api/aois", json={"name": "too big", "bbox": [-60, -10, -55, -5]})
        assert r.status_code == 422 and "limit" in r.json()["detail"]
        r = c.post("/api/aois", json={"name": "inverted", "bbox": [-55, -7, -56, -8]})
        assert r.status_code == 422
        r = c.post("/api/aois", json={"name": "ok", "bbox": [-55.4, -7.1, -55.35, -7.05]})
        assert r.status_code == 201 and r.json()["area_km2"] > 20


def test_no_model_blocks_analysis(tmp_data_dir, fixture_products):
    with _client() as c:
        aoi = c.get("/api/aois").json()[0]["id"]
        ids = _register_fixture_products(tmp_data_dir, fixture_products, aoi)
        r = c.post("/api/change-runs", json={"aoi_id": aoi, "before_id": ids[0], "after_id": ids[1]})
        assert r.status_code == 409 and "model" in r.json()["detail"].lower()


def test_experiment_rejects_spatial_leakage(tmp_data_dir):
    with _client() as c:
        r = c.post("/api/experiments", json={"name": "leak", "train_regions": ["a"], "val_regions": ["a"], "start": False})
        assert r.status_code == 422 and "both" in r.json()["detail"]


def test_full_change_workflow(tmp_data_dir, fixture_products):
    from app.db.session import SessionLocal
    from app.jobs.queue import claim_next
    from app.jobs.worker import run_job

    with _client() as c:
        aoi = c.get("/api/aois").json()[0]["id"]
        ids = _register_fixture_products(tmp_data_dir, fixture_products, aoi)
        _register_model(tmp_data_dir)

        prods = c.get(f"/api/products?aoi_id={aoi}").json()
        assert [p["id"] for p in prods] == ids
        assert c.post("/api/change-runs", json={"aoi_id": aoi, "before_id": ids[1], "after_id": ids[0]}).status_code == 422

        run = c.post(
            "/api/change-runs",
            json={"aoi_id": aoi, "before_id": ids[0], "after_id": ids[1], "params": {"min_mapping_unit_ha": 0.1}},
        ).json()
        assert run["status"] == "queued"
        job = claim_next()
        run_job(job)  # execute synchronously, exactly as the worker does

        jr = c.get(f"/api/jobs/{run['job_id']}").json()
        assert jr["status"] == "succeeded", jr.get("error")
        full = c.get(f"/api/change-runs/{run['id']}").json()
        assert full["status"] == "succeeded"
        s = full["summary"]
        assert abs(sum(a["fraction"] for a in s["category_areas"].values()) - 1) < 1e-9

        fc = c.get(f"/api/change-runs/{run['id']}/regions").json()
        assert fc["type"] == "FeatureCollection"
        assert len(fc["features"]) == full["headline"]["n_loss_regions"] + full["headline"]["n_gain_regions"]

        # tiles from every source
        for url in (
            f"/api/tiles/product/{ids[0]}/14/5672/8513.png?render=truecolor",
            f"/api/tiles/product/{ids[0]}/14/5672/8513.png?render=ndvi",
            f"/api/tiles/product/{ids[0]}/14/5672/8513.png?render=band&band=B11",
            f"/api/tiles/change/{run['id']}/14/5672/8513.png",
            f"/api/tiles/change/{run['id']}/14/5672/8513.png?render=delta",
            f"/api/tiles/change/{run['id']}/14/5672/8513.png?render=prob_after",
            f"/api/tiles/product/{ids[0]}/3/1/1.png",  # outside -> transparent
        ):
            r = c.get(url)
            assert r.status_code == 200 and r.content[:4] == b"\x89PNG", url

        # pixel inspector
        px = c.get(f"/api/products/{ids[0]}/pixel", params={"lon": fc["features"][0]["properties"]["centroid_lon"] if fc["features"] else -55.33, "lat": fc["features"][0]["properties"]["centroid_lat"] if fc["features"] else -7.05})
        assert px.status_code in (200, 404)

        if fc["features"]:
            rid = fc["features"][0]["properties"]["id"]
            d = c.get(f"/api/regions/{rid}").json()
            assert d["before"]["id"] == ids[0] and d["after"]["id"] == ids[1]
            rv = c.put(f"/api/regions/{rid}/review", json={"review_status": "uncertain", "analyst_notes": "test"})
            assert rv.json()["review_status"] == "uncertain"

        # exports
        for fmt in ("geojson", "csv", "geotiff", "bundle"):
            x = c.post("/api/exports", json={"source_type": "change_run", "source_id": run["id"], "format": fmt})
            assert x.status_code == 201, x.text
            dl = c.get(x.json()["download_url"])
            assert dl.status_code == 200 and dl.content[:2] == b"PK"

        hist = c.get("/api/history").json()
        types = {h["type"] for h in hist}
        assert {"observation", "change_run", "export", "experiment"} <= types

        ov = c.get(f"/api/overview?aoi_id={aoi}").json()
        assert ov["latest_change"]["id"] == run["id"]
        assert ov["n_observations"] == 2

    with SessionLocal() as db:
        from app.db.models import ChangeRegion

        assert db.query(ChangeRegion).count() == len(fc["features"])


def test_bundled_model_installed_on_fresh_start(tmp_data_dir, monkeypatch):
    """A fresh install registers and activates the U-Net shipped in models/ (no retraining needed)."""
    import app.services.registry as registry

    src = tmp_data_dir / "bundle" / "tiny-v1"
    src.mkdir(parents=True)
    torch.save({"state_dict": UNet(10, 5, 8, 2).state_dict(), "train_config": {"name": "tiny-v1", "bands": list(BAND_NAMES)}},
               src / "best.pt")
    (src / "result.json").write_text(json.dumps({"status": "completed", "best_val_miou": 0.5, "history": []}))
    monkeypatch.setattr(registry, "BUNDLED_MODELS", tmp_data_dir / "bundle")
    with _client() as c:
        exps = c.get("/api/experiments").json()
        assert [e["name"] for e in exps] == ["tiny-v1"]
        assert c.get("/api/settings").json()["active_experiment_id"] == exps[0]["id"]
    assert (tmp_data_dir / "models" / "tiny-v1" / "best.pt").exists()
