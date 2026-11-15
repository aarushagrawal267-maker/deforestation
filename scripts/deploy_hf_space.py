"""Deploy Sylva to a Hugging Face Space (Docker SDK).

Stages the tracked repository files, the Docker recipe in deploy/huggingface/ and a copy of the
local demo data (observations, segmentation/change runs, evaluations and the SQLite database,
with paths rewritten for the container), then uploads it with huggingface_hub.

Usage (from the repository root, with a Hugging Face token in HF_TOKEN or a logged-in CLI):
    backend/.venv/bin/python scripts/deploy_hf_space.py --repo <user>/sylva --private

Training regions (about 1 GB) are not uploaded; the bundled models in models/ are.
No credentials are written into the Space: .env is untracked and never staged.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DEMO_DIRS = ["products", "changes", "segmentations", "evaluations", "reference"]
CONTAINER_DATA = "/app/data"

FRONTMATTER = """---
title: Sylva
emoji: 🌳
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Sentinel-2 forest-change analysis with a U-Net trained from scratch
---

"""


def stage_repo(dst: Path) -> None:
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    for f in files:
        if f.startswith(".github/"):
            continue
        (dst / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, dst / f)
    shutil.copy2(ROOT / "deploy/huggingface/Dockerfile", dst / "Dockerfile")
    (dst / "README.md").write_text(FRONTMATTER + (ROOT / "README.md").read_text(encoding="utf-8"), encoding="utf-8")
    (dst / ".dockerignore").write_text("**/node_modules\n**/.venv\n**/__pycache__\n")


def stage_demo_data(dst: Path) -> None:
    out = dst / "demo_data"
    out.mkdir()
    for d in DEMO_DIRS:
        if (DATA / d).exists():
            shutil.copytree(DATA / d, out / d, ignore=shutil.ignore_patterns("work", "parts"))
    db = out / "sylva.sqlite"
    with sqlite3.connect(DATA / "sylva.sqlite") as src, sqlite3.connect(db) as tgt:
        src.backup(tgt)
    bundled = {p.name for p in (ROOT / "models").iterdir() if (p / "best.pt").exists()}
    con = sqlite3.connect(db)
    # experiments: keep those whose checkpoint is a bundled model (same SHA-256); point them at the bundle
    import hashlib

    sha = {hashlib.sha256((ROOT / "models" / n / "best.pt").read_bytes()).hexdigest(): n for n in bundled}
    for eid, ck_sha in con.execute("select id, checkpoint_sha256 from experiments").fetchall():
        if ck_sha in sha:
            con.execute("update experiments set checkpoint=? where id=?", (f"{CONTAINER_DATA}/models/{sha[ck_sha]}/best.pt", eid))
        else:
            con.execute("delete from epoch_metrics where experiment_id=?", (eid,))
            con.execute("delete from experiments where id=?", (eid,))
    # rewrite absolute local data paths in every text column
    local = str(DATA)
    for (t,) in con.execute("select name from sqlite_master where type='table'").fetchall():
        for col in [r[1] for r in con.execute(f"pragma table_info({t})")]:
            con.execute(f"update {t} set {col}=replace({col}, ?, ?) where cast({col} as text) like ?", (local, CONTAINER_DATA, f"%{local}%"))
    con.commit()
    con.execute("vacuum")
    con.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="<user>/<space-name>")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--stage-only", type=Path, help="write the staged folder here and do not upload")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        stage = a.stage_only or Path(tmp) / "space"
        stage.mkdir(parents=True, exist_ok=True)
        stage_repo(stage)
        stage_demo_data(stage)
        size = sum(f.stat().st_size for f in stage.rglob("*") if f.is_file()) / 1e6
        print(f"Staged {stage} ({size:.0f} MB)")
        if a.stage_only:
            return
        from huggingface_hub import HfApi

        api = HfApi()
        api.create_repo(a.repo, repo_type="space", space_sdk="docker", private=a.private, exist_ok=True)
        api.upload_folder(repo_id=a.repo, repo_type="space", folder_path=stage, commit_message="Deploy Sylva")
        print(f"https://huggingface.co/spaces/{a.repo}")


if __name__ == "__main__":
    main()
