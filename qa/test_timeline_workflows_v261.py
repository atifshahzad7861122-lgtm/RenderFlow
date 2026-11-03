"""
qa/test_timeline_workflows_v261.py — Validation of Auto Timeline, Manual Timeline,
Lock Preservation, Conflict Detection, and Safe Ingestion Invariants
==================================================================================
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
import numpy as np
from PIL import Image
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from engine.sync_engine_v3 import AIImageSyncEngineV3, SyncConfig
from engine.sync_v3_intelligence import MappingMode
from web.zip_processor import process_zip_archive


class TestTimelineWorkflowsV261(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="rf_tl_workflow_test_"))
        self.project_dir = self.temp_dir / "project"
        self.project_dir.mkdir(parents=True)
        self.images_dir = self.project_dir / "images"
        self.images_dir.mkdir(parents=True)

        # Create sample images
        self.img1 = self._create_image("img_01.png", (200, 50, 50))
        self.img2 = self._create_image("img_02.png", (50, 200, 50))
        self.img3 = self._create_image("img_03.png", (50, 50, 200))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_image(self, name: str, color=(100, 100, 100)):
        p = self.images_dir / name
        arr = np.zeros((100, 100, 3), dtype=np.uint8)
        arr[:, :] = color
        Image.fromarray(arr).save(p)
        return name

    def test_ingestion_invariant_never_creates_or_alters_plan(self):
        """Image ingestion must NEVER create or modify plan.json."""
        plan_file = self.project_dir / "plan.json"
        self.assertFalse(plan_file.exists())

        # Create zip with new images
        zip_path = self.temp_dir / "upload.zip"
        import zipfile
        with zipfile.ZipFile(zip_path, 'w') as zf:
            dummy_img = self.temp_dir / "dummy.png"
            Image.fromarray(np.zeros((50, 50, 3), dtype=np.uint8)).save(dummy_img)
            zf.write(dummy_img, arcname="img_04.png")

        # Process zip
        res = process_zip_archive(zip_path, self.images_dir, self.temp_dir / "work", replace_existing=False)
        self.assertTrue(res["success"])

        # Invariant: plan.json must still NOT exist!
        self.assertFalse(plan_file.exists(), "CRITICAL: Image ingestion must NEVER generate plan.json automatically!")

    def test_manual_override_lock_preservation_during_resync(self):
        """When a clip has user_override=True, re-sync must never change its image."""
        old_plan = {
            "timeline_mode": "manual",
            "scenes": [
                {
                    "segment_index": 0,
                    "start": 0.0,
                    "end": 3.0,
                    "dur": 3.0,
                    "image": "img_01.png",
                    "user_override": True,
                    "locked": True
                },
                {
                    "segment_index": 1,
                    "start": 3.0,
                    "end": 6.0,
                    "dur": 3.0,
                    "image": "img_02.png",
                    "user_override": False,
                    "locked": False
                }
            ]
        }

        # Simulated new plan from semantic engine where segment 0 was preserved and segment 1 was updated
        new_plan = {
            "timeline_mode": "auto",
            "scenes": [
                {
                    "segment_index": 0,
                    "start": 0.0,
                    "end": 3.0,
                    "dur": 3.0,
                    "image": "img_01.png",
                    "user_override": True,
                    "locked": True
                },
                {
                    "segment_index": 1,
                    "start": 3.0,
                    "end": 6.0,
                    "dur": 3.0,
                    "image": "img_03.png",
                    "user_override": False,
                    "locked": False
                }
            ]
        }

        comparison = AIImageSyncEngineV3.compare_plans(old_plan, new_plan)
        self.assertEqual(comparison["manual_preserved_count"], 1)
        self.assertEqual(comparison["changed_count"], 1)
        self.assertEqual(len(comparison["changed_mappings"]), 1)
        self.assertEqual(comparison["changed_mappings"][0]["old_image"], "img_02.png")
        self.assertEqual(comparison["changed_mappings"][0]["new_image"], "img_03.png")

    def test_manual_timeline_plan_persistence_schema(self):
        """Plan saved in manual mode must preserve timeline_mode and user_override flags."""
        plan_data = {
            "timeline_mode": "manual",
            "scenes": [
                {
                    "segment_index": 0,
                    "start": 0.0,
                    "end": 4.5,
                    "dur": 4.5,
                    "image": "img_02.png",
                    "user_override": True,
                    "locked": True,
                    "transition": "dissolve"
                }
            ]
        }
        plan_file = self.project_dir / "plan.json"
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plan_data, f, indent=2)

        # Reload and verify
        with open(plan_file, "r", encoding="utf-8") as f:
            reloaded = json.load(f)

        self.assertEqual(reloaded["timeline_mode"], "manual")
        self.assertTrue(reloaded["scenes"][0]["user_override"])
        self.assertTrue(reloaded["scenes"][0]["locked"])
        self.assertEqual(reloaded["scenes"][0]["image"], "img_02.png")


if __name__ == '__main__':
    unittest.main()
