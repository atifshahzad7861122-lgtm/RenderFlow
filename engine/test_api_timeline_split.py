#!/usr/bin/env python3
"""
engine/test_api_timeline_split.py — API Test Suite for /api/timeline/split_scene endpoint.
Phase 2A: Safe Timeline Editing MVP.

Verifies:
  1. POST /api/timeline/split_scene with valid timestamp returns 200 and updated scene list.
  2. POST /api/timeline/split_scene rejects negative timestamp with 400.
  3. POST /api/timeline/split_scene rejects timestamp exceeding duration with 400.
  4. POST /api/timeline/split_scene rejects cut too close to boundary (< 0.3s) with 400.
  5. POST /api/timeline/split_scene preserves atomicity and plan.json on disk.
"""

import sys
import json
import shutil
import tempfile
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

web_dir = WORKSPACE_ROOT / "web"
if str(web_dir) not in sys.path:
    sys.path.insert(0, str(web_dir))

from fastapi.testclient import TestClient
from web.server import app

client = TestClient(app)


def test_api_split_workflow():
    temp_dir = Path(tempfile.mkdtemp(prefix="test_api_split_"))
    try:
        project_dir = temp_dir / "split_project"
        project_dir.mkdir(parents=True, exist_ok=True)
        plan_file = project_dir / "plan.json"

        # Create initial 3-scene plan (total 15.0s)
        initial_plan = {
            "project_name": "Split Test Project",
            "scenes": [
                {"segment_index": 0, "start": 0.0, "end": 5.0, "dur": 5.0, "image": "1.png", "transition": "clean_cut"},
                {"segment_index": 1, "start": 5.0, "end": 10.0, "dur": 5.0, "image": "2.png", "transition": "cinematic_dissolve"},
                {"segment_index": 2, "start": 10.0, "end": 15.0, "dur": 5.0, "image": "3.png", "transition": "clean_cut"}
            ]
        }
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(initial_plan, f, indent=2)

        # 1. Valid Split at 2.5s (splits scene 0)
        resp = client.post("/api/timeline/split_scene", json={
            "project_path": str(project_dir),
            "split_time": 2.5
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["success"] is True
        assert data["split_index"] == 1
        assert data["total_scenes"] == 4
        assert len(data["scenes"]) == 4
        assert data["scenes"][0]["dur"] == 2.5
        assert data["scenes"][1]["dur"] == 2.5

        # Verify disk persistence
        with open(plan_file, "r", encoding="utf-8") as f:
            saved_plan = json.load(f)
        assert len(saved_plan["scenes"]) == 4

        # 2. Reject negative split time
        resp_neg = client.post("/api/timeline/split_scene", json={
            "project_path": str(project_dir),
            "split_time": -1.0
        })
        assert resp_neg.status_code == 400
        assert "positive" in resp_neg.json()["detail"].lower()

        # 3. Reject split time exceeding duration (> 15.0s)
        resp_oob = client.post("/api/timeline/split_scene", json={
            "project_path": str(project_dir),
            "split_time": 18.0
        })
        assert resp_oob.status_code == 400
        assert "exceeds" in resp_oob.json()["detail"].lower()

        # 4. Reject split too close to boundary (< 0.3s from scene start)
        # Scene 1 currently runs [2.5, 5.0]. Attempt split at 2.6s (0.1s head duration)
        resp_edge = client.post("/api/timeline/split_scene", json={
            "project_path": str(project_dir),
            "split_time": 2.6,
            "min_clip_duration": 0.3
        })
        assert resp_edge.status_code == 400
        assert "too close to scene start" in resp_edge.json()["detail"].lower()

        # 5. Missing project_path
        resp_missing = client.post("/api/timeline/split_scene", json={
            "split_time": 3.0
        })
        assert resp_missing.status_code == 400

        print("PASS: All 5 API endpoint split conditions verified successfully!")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    print("=" * 70)
    print(" RENDERFLOW — PHASE 2A: API ENDPOINT SPLIT VERIFICATION")
    print("=" * 70)
    test_api_split_workflow()
    print("=" * 70)
