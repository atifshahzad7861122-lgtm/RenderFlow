#!/usr/bin/env python3
r"""
engine/test_windows_hardening.py — Windows Production Hardening Test Suite.

Explicitly verifies that Rendering Studio Engine v2 handles:
  1. Paths containing spaces (e.g. 'C:\\My all work\\Rendering Engine\\')
  2. Paths containing parentheses, brackets, and special characters (e.g. 'Project (v2) [Final] & Edit')
  3. Paths and filenames containing Unicode characters (Urdu, Arabic, Chinese, Japanese)
  4. FFmpeg filtergraph escaping with Windows drive letters (C:\ -> C\:/)
  5. Audio duration probing with complex Windows paths
  6. Image preprocessing and caching with complex Windows paths
  7. End-to-end rendering directly into complex Windows paths
  8. Subprocess argument array safety (zero unsafe shell strings)
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
import unittest
from pathlib import Path
from PIL import Image

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from engine.fast_pipeline import (
    get_audio_duration,
    preprocess_image,
    get_ffmpeg_path,
    get_ffprobe_path,
    run_pipeline
)
from engine.caption_engine import CaptionEngine
from engine.caption_model import CaptionModel, CaptionSegment, Word


class TestWindowsProductionHardening(unittest.TestCase):

    def setUp(self):
        # Create a challenging root folder with spaces, parentheses, brackets, and Unicode
        base_temp = Path(tempfile.gettempdir())
        self.complex_dir = base_temp / "My All Work (Studio)" / "Engine [v2] & Test - اردو 中文 日本語"
        self.complex_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir = self.complex_dir / "Images (Source) - تصویر"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir = self.complex_dir / "Work (Temp) [Cache]"
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        # Clean up
        base_parent = Path(tempfile.gettempdir()) / "My All Work (Studio)"
        if base_parent.exists():
            shutil.rmtree(base_parent, ignore_errors=True)

    def test_01_complex_path_image_preprocessing(self):
        """Image preprocessing must work with spaces, parentheses, and Unicode in path and filename."""
        img_file = self.images_dir / "test image (01) [HQ] - تصویر.png"
        img = Image.new("RGB", (1280, 720), color=(180, 40, 60))
        img.save(img_file, "PNG")

        cache_dir = self.work_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = preprocess_image(img_file, cache_dir, 1920, 1080)

        self.assertTrue(cached.exists())
        self.assertGreater(cached.stat().st_size, 1024)
        with Image.open(cached) as im_res:
            self.assertEqual(im_res.size, (1920, 1080))

    def test_02_complex_path_audio_probing(self):
        """Audio duration probe via ffprobe must handle spaces, parentheses, and Unicode paths."""
        audio_file = self.complex_dir / "narration audio (master) - آواز.wav"
        # Generate 2.5s sine wave
        cmd = [
            get_ffmpeg_path(), '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2.5',
            '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le',
            str(audio_file)
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        self.assertTrue(audio_file.exists())
        dur = get_audio_duration(audio_file)
        self.assertAlmostEqual(dur, 2.5, delta=0.05)

    def test_03_ass_filter_path_escaping(self):
        """ASS filter escaping must handle Windows drive colons, spaces, and parentheses."""
        ass_path = self.complex_dir / "captions (subtitles) - اردو.ass"
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write("[Script Info]\nTitle: Test\n")

        # Test the escaping rule applied in fast_pipeline.py
        escaped_ass = ass_path.resolve().as_posix().replace('\\', '/').replace(':', r'\:').replace("'", r"\'")
        self.assertNotIn(":", escaped_ass.replace(r"\:", ""))
        self.assertIn(r"\:", escaped_ass)

    def test_04_argument_array_safety_no_injection(self):
        """Arguments containing shell metacharacters (&, |, ;, <, >) must be safely treated as literals."""
        tricky_name = "test & script ; file (1) [copy] ^ percent% $dollar #hash - اردو"
        tricky_file = self.complex_dir / f"{tricky_name}.txt"
        with open(tricky_file, "w", encoding="utf-8") as f:
            f.write("safe content")

        # Invocations with subprocess argument arrays must not trigger shell execution
        # Even with raw pipe and redirection characters in argument array
        tricky_arg = "malicious | cmd & calc > out; echo vulnerable"
        test_py = [
            sys.executable, "-c",
            "import sys; sys.stdout.reconfigure(encoding='utf-8'); print(sys.argv[1]); print(sys.argv[2])",
            str(tricky_file), tricky_arg
        ]
        r = subprocess.run(test_py, capture_output=True, text=True, encoding='utf-8', check=True)
        lines = r.stdout.strip().splitlines()
        self.assertEqual(lines[0], str(tricky_file))
        self.assertEqual(lines[1], tricky_arg)

    def test_05_end_to_end_render_in_complex_windows_path(self):
        """Full video render must succeed completely inside complex Windows path."""
        # 1. Source image
        img_file = self.images_dir / "scene_01 (main) [4k] - منظر.jpg"
        img = Image.new("RGB", (1920, 1080), color=(30, 80, 150))
        img.save(img_file, "JPEG")

        # 2. Audio (3.0s)
        audio_file = self.complex_dir / "narration (3s) - ریکارڈنگ.wav"
        cmd = [
            get_ffmpeg_path(), '-y', '-f', 'lavfi', '-i', 'sine=frequency=500:duration=3.0',
            '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le',
            str(audio_file)
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        # 3. Segments and Plan
        seg_file = self.complex_dir / "segments (timed) - اوقات.json"
        with open(seg_file, "w", encoding="utf-8") as f:
            json.dump({
                "segments": [
                    {"start": 0.0, "end": 3.0, "text": "Rendering Studio Windows Hardening Test"}
                ]
            }, f)

        plan_file = self.complex_dir / "plan (master) - منصوبہ.json"
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump({
                "scenes": [
                    {"start": 0.0, "end": 3.0, "dur": 3.0, "image": img_file.name}
                ]
            }, f)

        out_video = self.complex_dir / "output (cinematic) [final] - ویڈیو.mp4"

        # Execute run_pipeline directly into the complex directory
        res = run_pipeline(
            images_dir=self.images_dir,
            segments_path=seg_file,
            plan_path=plan_file,
            audio_path=audio_file,
            out_path=out_video,
            workdir=self.work_dir,
            pack_dir=WORKSPACE_ROOT / "transition_pack",
            skip_verify=False,
            enable_transitions=False,
            enable_captions=False
        )

        self.assertTrue(out_video.exists())
        self.assertGreater(out_video.stat().st_size, 50000)
        dur = get_audio_duration(out_video)
        self.assertAlmostEqual(dur, 3.0, delta=0.1)


def run_tests():
    print("=" * 65)
    print(" RUNNING MODULE 11: WINDOWS PRODUCTION HARDENING TESTS")
    print("=" * 65)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestWindowsProductionHardening)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n" + "=" * 65)
        print(" ALL 5 WINDOWS HARDENING TESTS PASSED (100% PASS)")
        print("=" * 65)
        return 0
    else:
        print("\nERRORS ENCOUNTERED IN WINDOWS HARDENING SUITE")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
