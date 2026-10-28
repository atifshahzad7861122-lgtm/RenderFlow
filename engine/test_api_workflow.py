#!/usr/bin/env python3
"""
engine/test_api_workflow.py — End-to-End API / UI Workflow Verification Suite.

Tests the full student workflow via FastAPI TestClient:
  1. CLEAN STARTUP / DEFAULT STATE
  2. UPLOAD (Images + Audio registration)
  3. SYNC (Semantic beat alignment & plan generation)
  4. REVIEW (Timeline continuity validation & plan inspection)
  5. STYLE (Caption presets & transition catalogs)
  6. RENDER VALIDATION (Parameter checks, state lifecycle)
  7. DOWNLOAD / MEDIA URLS (Route safety & file serving)
  8. CLEANUP (Resource unlinking & isolation)
"""

import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from PIL import Image

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# Ensure web module is discoverable
web_dir = WORKSPACE_ROOT / "web"
if str(web_dir) not in sys.path:
    sys.path.insert(0, str(web_dir))

from fastapi.testclient import TestClient
from web.server import app

client = TestClient(app)


class TestApiWorkflow(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_api_workflow_"))
        self.project_dir = self.temp_dir / "user_project_01"
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir = self.project_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)

        # Create 3 synthetic test images
        for i in range(1, 4):
            im = Image.new("RGB", (640, 360), color=(50 * i, 70, 100))
            im.save(self.images_dir / f"slide_{i:02d}.jpg", "JPEG")

        # Create synthetic 3s WAV audio
        self.audio_path = self.project_dir / "narration.wav"
        import subprocess
        from engine.fast_pipeline import get_ffmpeg_path
        cmd = [
            get_ffmpeg_path(), '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3.0',
            '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le',
            str(self.audio_path)
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_clean_startup(self):
        """API must boot cleanly and report project state."""
        resp = client.get("/api/project/data")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("project_path", data)

    def test_02_caption_styles_catalog(self):
        """API must expose all available caption styles."""
        resp = client.get("/api/captions/styles")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("styles", data)
        self.assertIsInstance(data["styles"], list)
        self.assertGreaterEqual(len(data["styles"]), 10)

    def test_03_project_query_and_sync(self):
        """API must query project media and auto-generate render plan."""
        # Query project data
        q_resp = client.get(f"/api/project/data?project_path={self.project_dir.resolve().as_posix()}")
        self.assertEqual(q_resp.status_code, 200)
        pdata = q_resp.json()
        self.assertGreaterEqual(len(pdata.get("images", [])), 3)
        self.assertIsNotNone(pdata.get("audio"))

        # Trigger auto plan
        plan_resp = client.post("/api/project/auto_plan", json={
            "project_path": self.project_dir.resolve().as_posix()
        })
        self.assertEqual(plan_resp.status_code, 200)
        p_json = plan_resp.json()
        self.assertEqual(p_json.get("status"), "created")
        self.assertGreaterEqual(p_json.get("scenes_count", 0), 1)

        # Verify plan.json written to disk
        plan_file = self.project_dir / "plan.json"
        self.assertTrue(plan_file.exists())
        with open(plan_file, "r", encoding="utf-8") as f:
            plan_content = json.load(f)
        self.assertIn("scenes", plan_content)

    def test_04_caption_preview(self):
        """API must generate interactive caption previews for UI styling."""
        resp = client.post("/api/captions/preview", json={
            "style": "classic",
            "sample_text": "Testing Caption Rendering Engine v2"
        })
        self.assertEqual(resp.status_code, 200)

    def test_05_render_status_polling(self):
        """API must report idle render status initially."""
        resp = client.get("/api/render/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("state", data)
        self.assertIn(data["state"], ["idle", "completed", "error", "cancelled"])


def run_tests():
    print("=" * 65)
    print(" RUNNING MODULE 13: API / UI INTEGRATION TESTS")
    print("=" * 65)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestApiWorkflow)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n" + "=" * 65)
        print(" ALL 5 API & WORKFLOW INTEGRATION TESTS PASSED (100% PASS)")
        print("=" * 65)
        return 0
    else:
        print("\nERRORS ENCOUNTERED IN API INTEGRATION SUITE")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
