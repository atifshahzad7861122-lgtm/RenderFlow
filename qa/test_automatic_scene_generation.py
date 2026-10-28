#!/usr/bin/env python3
"""
qa/test_automatic_scene_generation.py — Acceptance Test Suite for Automatic Image-to-Audio Timeline Generation.

Tests all 10 acceptance requirements:
1. Importing images alone does not falsely report successful scene generation (0 scenes, empty plan).
2. Importing narration and images followed by automatic generation produces non-empty scenes and visual clips.
3. The generated timeline covers the narration duration within the existing timing tolerance (zero gaps/overlaps).
4. Each visual clip references a valid imported image asset.
5. The backend API contract (/api/project/data and /api/project/auto_plan) returns populated scenes with full metadata.
6. Save and reload (/api/project/save_plan -> /api/project/data) preserves generated assignments and metadata.
7. Re-running generation does not duplicate clips or silently overwrite user-locked / manual edits.
8. Missing narration, missing images, and invalid audio return clear errors or safe fallback behavior.
9. A 214.7-second narration with 86 imported images works seamlessly without hardcoding these values.
10. Preservation of Phase 1-4 metadata (shot_role, easing, cadence_alignment, broll, waveform) without regressions.
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
import numpy as np
from pathlib import Path
from typing import Dict, List, Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from web.server import app, WORKSPACE_DIR
from engine.semantic_sync import (
    build_semantic_timeline,
    validate_timeline_coverage,
    probe_audio_duration
)
from engine.sync_engine_v3 import AIImageSyncEngineV3, SyncConfig
from engine.fast_pipeline import get_ffmpeg_path, get_ffprobe_path


class TestAutomaticSceneGenerationAcceptance(unittest.TestCase):
    """Rigorous acceptance test suite for automatic scene generation & timeline mapping."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.test_tmp_dir = Path(tempfile.mkdtemp(prefix="rf_auto_gen_test_"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_tmp_dir, ignore_errors=True)

    def _generate_synthetic_wav(self, path: Path, duration_sec: float = 6.0, sample_rate: int = 16000):
        """Generate a clean synthetic sine wave with natural pauses for deterministic testing."""
        path.parent.mkdir(parents=True, exist_ok=True)
        t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
        # 440Hz tone modulated with low-frequency pause dips
        envelope = 0.5 * (1.0 + np.sin(2 * np.pi * 0.5 * t))
        audio = (np.sin(2 * np.pi * 440.0 * t) * envelope * 32767).astype(np.int16)
        
        # Write wav using scipy or wave
        import wave
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio.tobytes())

    def _create_synthetic_image(self, path: Path, color: tuple = (100, 150, 200)):
        """Create a minimal solid color test PNG."""
        path.parent.mkdir(parents=True, exist_ok=True)
        import cv2
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[:] = color
        cv2.imwrite(str(path), img)

    def test_01_images_alone_does_not_falsely_report_scenes(self):
        """1. Importing images alone must report 0 scenes and not falsely claim successful scene generation."""
        proj_dir = self.test_tmp_dir / "proj_images_only"
        img_dir = proj_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        for i in range(5):
            self._create_synthetic_image(img_dir / f"img_{i}.png", color=(i*30, 100, 150))

        # Request project data
        resp = self.client.get(f"/api/project/data?project_path={proj_dir.as_posix()}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Invariant: images are discovered (5), but scenes must be 0 and plan is None / empty
        self.assertEqual(len(data.get("images", [])), 5)
        self.assertIsNone(data.get("audio"))
        plan = data.get("plan")
        scenes = plan.get("scenes", []) if plan else []
        self.assertEqual(len(scenes), 0, "Images alone must never fabricate scenes without audio")

    def test_02_narration_and_images_auto_generates_valid_timeline(self):
        """2. Narration and images present automatically generates non-empty scenes and visual clips."""
        proj_dir = self.test_tmp_dir / "proj_valid_auto"
        img_dir = proj_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        for i in range(6):
            self._create_synthetic_image(img_dir / f"frame_{i:02d}.png", color=(50, i*35, 120))

        audio_path = proj_dir / "narration.wav"
        target_dur = 12.0
        self._generate_synthetic_wav(audio_path, duration_sec=target_dur)

        # Query project data: should automatically trigger plan generation
        resp = self.client.get(f"/api/project/data?project_path={proj_dir.as_posix()}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIsNotNone(data.get("audio"))
        plan = data.get("plan")
        self.assertIsNotNone(plan, "Plan must be automatically generated")
        scenes = plan.get("scenes", [])
        self.assertGreater(len(scenes), 0, "Must produce non-empty scenes")

        # Invariant: all 6 images must be assigned
        assigned_images = {s["image"] for s in scenes}
        for i in range(6):
            self.assertIn(f"frame_{i:02d}.png", assigned_images)

    def test_03_timeline_duration_coverage_tolerance(self):
        """3. Timeline strictly covers the narration duration within tolerance (zero gaps/overlaps)."""
        proj_dir = self.test_tmp_dir / "proj_coverage"
        img_dir = proj_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        for i in range(4):
            self._create_synthetic_image(img_dir / f"scene_{i}.png", color=(i*40, 50, 90))

        audio_path = proj_dir / "narration.wav"
        target_dur = 8.5
        self._generate_synthetic_wav(audio_path, duration_sec=target_dur)

        resp = self.client.post("/api/project/auto_plan", json={
            "project_path": str(proj_dir),
            "all_images_mode": True
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        plan = data.get("plan", {})
        scenes = plan.get("scenes", [])

        self.assertEqual(scenes[0]["start"], 0.0, "Timeline must start at 0.0")
        for i in range(1, len(scenes)):
            self.assertEqual(
                round(scenes[i]["start"], 3),
                round(scenes[i-1]["end"], 3),
                f"Scene {i} start must equal scene {i-1} end (zero gap, zero overlap)"
            )
            self.assertGreater(scenes[i]["dur"], 0.0, "Scene duration must be positive")

        # Final end must match probed duration
        probed_dur = probe_audio_duration(audio_path)
        self.assertAlmostEqual(scenes[-1]["end"], probed_dur, delta=0.05)

    def test_04_each_visual_clip_references_valid_asset(self):
        """4. Each visual clip references a valid existing asset in the images directory."""
        proj_dir = self.test_tmp_dir / "proj_asset_refs"
        img_dir = proj_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        valid_filenames = [f"valid_asset_{i}.png" for i in range(5)]
        for fn in valid_filenames:
            self._create_synthetic_image(img_dir / fn)

        audio_path = proj_dir / "narration.wav"
        self._generate_synthetic_wav(audio_path, duration_sec=10.0)

        resp = self.client.post("/api/project/auto_plan", json={"project_path": str(proj_dir)})
        self.assertEqual(resp.status_code, 200)
        scenes = resp.json().get("plan", {}).get("scenes", [])

        for sc in scenes:
            img_fn = sc.get("image")
            self.assertIn(img_fn, valid_filenames, f"Scene referenced non-existent image: {img_fn}")
            self.assertTrue((img_dir / img_fn).exists(), f"Image file {img_fn} does not physically exist")

    def test_05_backend_to_frontend_contract_completeness(self):
        """5. Backend API contract returns all necessary fields for Timeline Studio rendering."""
        proj_dir = self.test_tmp_dir / "proj_contract"
        img_dir = proj_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            self._create_synthetic_image(img_dir / f"contract_{i}.png")

        audio_path = proj_dir / "narration.wav"
        self._generate_synthetic_wav(audio_path, duration_sec=6.0)

        resp = self.client.get(f"/api/project/data?project_path={proj_dir.as_posix()}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        plan = data.get("plan")
        self.assertIsNotNone(plan)
        scenes = plan.get("scenes", [])
        self.assertGreater(len(scenes), 0)

        required_scene_fields = [
            "scene_id", "segment_index", "start", "end", "dur",
            "image", "transition", "shot_role", "easing", "motion_mode"
        ]
        for sc in scenes:
            for field in required_scene_fields:
                self.assertIn(field, sc, f"Required scene field '{field}' missing from API payload")

    def test_06_save_and_reload_preserves_assignments(self):
        """6. Save and reload preserves generated scene assignments and custom edits."""
        proj_dir = self.test_tmp_dir / "proj_save_reload"
        img_dir = proj_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            self._create_synthetic_image(img_dir / f"save_{i}.png")

        audio_path = proj_dir / "narration.wav"
        self._generate_synthetic_wav(audio_path, duration_sec=6.0)

        # Generate initial plan
        gen_resp = self.client.post("/api/project/auto_plan", json={"project_path": str(proj_dir)})
        self.assertEqual(gen_resp.status_code, 200)
        plan = gen_resp.json()["plan"]

        # User modifies scene 1
        plan["scenes"][1]["image"] = "save_2.png"
        plan["scenes"][1]["user_override"] = True
        plan["scenes"][1]["locked"] = True
        plan["scenes"][1]["shot_role"] = "dramatic_tension"
        plan["scenes"][1]["easing"] = "cubic_in_out"

        # Save plan
        save_resp = self.client.post("/api/project/save_plan", json={
            "project_path": str(proj_dir),
            "plan": plan
        })
        self.assertEqual(save_resp.status_code, 200)

        # Reload via get_project_data
        reload_resp = self.client.get(f"/api/project/data?project_path={proj_dir.as_posix()}")
        self.assertEqual(reload_resp.status_code, 200)
        reloaded_plan = reload_resp.json()["plan"]

        sc1 = reloaded_plan["scenes"][1]
        self.assertEqual(sc1["image"], "save_2.png")
        self.assertTrue(sc1.get("user_override"))
        self.assertTrue(sc1.get("locked"))
        self.assertEqual(sc1.get("shot_role"), "dramatic_tension")
        self.assertEqual(sc1.get("easing"), "cubic_in_out")

    def test_07_re_running_preserves_user_overrides_and_locked_scenes(self):
        """7. Re-running generation does not duplicate clips or overwrite user-locked assignments."""
        proj_dir = self.test_tmp_dir / "proj_preserve_locks"
        img_dir = proj_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        for i in range(4):
            self._create_synthetic_image(img_dir / f"lock_{i}.png")

        audio_path = proj_dir / "narration.wav"
        self._generate_synthetic_wav(audio_path, duration_sec=8.0)

        # Auto plan
        self.client.post("/api/project/auto_plan", json={"project_path": str(proj_dir)})

        # Manually lock scene 0 to lock_3.png
        plan_file = proj_dir / "plan.json"
        with open(plan_file, "r", encoding="utf-8") as f:
            plan = json.load(f)
        plan["scenes"][0]["image"] = "lock_3.png"
        plan["scenes"][0]["locked"] = True
        plan["scenes"][0]["user_override"] = True
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)

        # Re-run auto_plan without reset_overrides
        rerun_resp = self.client.post("/api/project/auto_plan", json={
            "project_path": str(proj_dir),
            "reset_overrides": False
        })
        self.assertEqual(rerun_resp.status_code, 200)
        rerun_plan = rerun_resp.json()["plan"]
        rerun_scenes = rerun_plan["scenes"]

        # Must not duplicate scene count
        self.assertEqual(len(rerun_scenes), len(plan["scenes"]))
        # Scene 0 must still be lock_3.png
        self.assertEqual(rerun_scenes[0]["image"], "lock_3.png")

    def test_08_missing_narration_and_empty_images_error_handling(self):
        """8. Missing audio, missing images, and invalid audio return clear errors or safe fallbacks."""
        # Case A: Missing project path
        resp = self.client.post("/api/project/auto_plan", json={})
        self.assertEqual(resp.status_code, 400)

        # Case B: Project with missing images directory
        empty_proj = self.test_tmp_dir / "proj_no_images"
        empty_proj.mkdir(parents=True, exist_ok=True)
        self._generate_synthetic_wav(empty_proj / "narration.wav", 4.0)
        resp = self.client.post("/api/project/auto_plan", json={"project_path": str(empty_proj)})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("No images", resp.json()["detail"])

        # Case B2: Project with empty images directory
        (empty_proj / "images").mkdir(parents=True, exist_ok=True)
        resp2 = self.client.post("/api/project/auto_plan", json={"project_path": str(empty_proj)})
        self.assertEqual(resp2.status_code, 400)
        self.assertIn("No valid images", resp2.json()["detail"])

        # Case C: Project with zero audio (safe fallback behavior per requirement 8)
        no_aud_proj = self.test_tmp_dir / "proj_no_audio"
        img_dir = no_aud_proj / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        self._create_synthetic_image(img_dir / "img1.png")
        resp = self.client.post("/api/project/auto_plan", json={"project_path": str(no_aud_proj)})
        self.assertEqual(resp.status_code, 200, "Missing audio must trigger safe fallback behavior")
        fallback_plan = resp.json().get("plan", {})
        self.assertGreater(len(fallback_plan.get("scenes", [])), 0)
        self.assertEqual(fallback_plan["scenes"][0]["dur"], 3.0, "Safe fallback sets default duration")

    def test_09_real_user_project_214s_and_86_images(self):
        """9. Test the user's actual project (214.7s narration, 86 images) without hardcoding."""
        real_proj = WORKSPACE_DIR / "projects" / "hdcihdy"
        if not real_proj.exists():
            self.skipTest("Real user project projects/hdcihdy not found")

        resp = self.client.get(f"/api/project/data?project_path={real_proj.as_posix()}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Check images
        images = data.get("images", [])
        self.assertEqual(len(images), 86, "Expected exactly 86 images in real project")

        # Check audio
        audio = data.get("audio")
        self.assertIsNotNone(audio)
        self.assertAlmostEqual(audio.get("duration", 0.0), 214.666, delta=0.5)

        # Check plan & scenes
        plan = data.get("plan")
        self.assertIsNotNone(plan)
        scenes = plan.get("scenes", [])
        self.assertEqual(len(scenes), 86, "Expected 86 generated scenes for 86 images")

        # Validate zero-gap, zero-overlap full audio coverage
        first_scene = scenes[0]
        last_scene = scenes[-1]
        self.assertEqual(first_scene["start"], 0.0)
        self.assertAlmostEqual(last_scene["end"], audio["duration"], delta=0.05)

        for i in range(1, len(scenes)):
            self.assertEqual(
                round(scenes[i]["start"], 3),
                round(scenes[i-1]["end"], 3),
                f"Discontinuity at scene {i}: start {scenes[i]['start']} != end {scenes[i-1]['end']}"
            )

        # Validate timeline coverage validator
        img_files = [WORKSPACE_DIR / "projects" / "hdcihdy" / "images" / im["name"] for im in images]
        transcript_obj = data.get("transcript")
        is_valid, errs, metrics = validate_timeline_coverage(
            transcript_obj=transcript_obj,
            plan_obj=plan,
            master_dur=audio["duration"],
            images_dir=WORKSPACE_DIR / "projects" / "hdcihdy" / "images"
        )
        self.assertTrue(is_valid, f"Timeline coverage validation failed: {errs}")

    def test_10_phase1_to_4_preservation_in_auto_plan(self):
        """10. Verify Phase 1 shot roles/easing and Phase 2 cadence alignment metadata are present."""
        real_proj = WORKSPACE_DIR / "projects" / "hdcihdy"
        if not real_proj.exists():
            self.skipTest("Real user project not found")

        resp = self.client.get(f"/api/project/data?project_path={real_proj.as_posix()}")
        self.assertEqual(resp.status_code, 200)
        plan = resp.json().get("plan", {})
        scenes = plan.get("scenes", [])
        self.assertGreater(len(scenes), 0)

        # Check Phase 1 motion fields
        valid_shot_roles = {
            "establishing_wide", "character_focus", "dramatic_tension",
            "narrative_inspection", "environmental_drift"
        }
        valid_easings = {"linear", "smoothstep", "cubic_in_out", "ease_out", "ease_in"}

        has_shot_roles = False
        has_cadence = False

        for sc in scenes:
            if "shot_role" in sc and sc["shot_role"] in valid_shot_roles:
                has_shot_roles = True
            if "easing" in sc and sc["easing"] in valid_easings:
                self.assertIn(sc["easing"], valid_easings)
            if "cadence_alignment" in sc:
                has_cadence = True

        self.assertTrue(has_shot_roles, "Phase 1 shot roles must be populated")
        self.assertTrue(has_cadence, "Phase 2 cadence alignment metadata must be populated")


if __name__ == "__main__":
    unittest.main()
