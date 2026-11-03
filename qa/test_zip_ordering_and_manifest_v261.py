"""
qa/test_zip_ordering_and_manifest_v261.py — Validation of Deterministic ZIP Ordering,
Manifest Schema, Ambiguity Detection, and Timeline Separation
=====================================================================================
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
import zipfile
import numpy as np
from PIL import Image
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from web.zip_processor import (
    process_zip_archive,
    create_ordered_image_zip,
    detect_filename_sequence_ambiguity,
    natural_sort_key
)


class TestZipOrderingAndManifestV261(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="rf_zip_test_"))
        self.images_dir = self.temp_dir / "images"
        self.images_dir.mkdir(parents=True)
        self.work_dir = self.temp_dir / "work"
        self.work_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_sample_image(self, path: Path, color=(100, 150, 200)):
        path.parent.mkdir(parents=True, exist_ok=True)
        arr = np.zeros((100, 100, 3), dtype=np.uint8)
        arr[:, :] = color
        Image.fromarray(arr).save(path)
        return path

    def test_deterministic_zip_generation_with_manifest(self):
        """create_ordered_image_zip generates manifest.json with valid schema and hashes."""
        img1 = self._create_sample_image(self.temp_dir / "source" / "sunset.jpg", (200, 50, 50))
        img2 = self._create_sample_image(self.temp_dir / "source" / "beach.jpg", (50, 150, 250))
        img3 = self._create_sample_image(self.temp_dir / "source" / "forest.jpg", (50, 200, 50))

        entries = [
            {"file_path": img1, "query": "vibrant sunset", "original_index": 0},
            {"file_path": img2, "query": "sunny beach", "original_index": 1},
            {"file_path": img3, "query": "deep green forest", "original_index": 2},
        ]

        out_zip = self.temp_dir / "generated_bundle.zip"
        res_zip = create_ordered_image_zip(entries, out_zip, job_id="job_test_123")
        self.assertTrue(res_zip.exists())

        # Inspect manifest inside zip
        with zipfile.ZipFile(res_zip, 'r') as zf:
            self.assertIn("manifest.json", zf.namelist())
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            self.assertEqual(manifest["job_id"], "job_test_123")
            self.assertEqual(manifest["total_images"], 3)
            self.assertEqual(len(manifest["images"]), 3)
            self.assertEqual(manifest["images"][0]["sequence_index"], 1)
            self.assertEqual(manifest["images"][1]["sequence_index"], 2)
            self.assertEqual(manifest["images"][2]["sequence_index"], 3)
            self.assertTrue(len(manifest["images"][0]["sha256"]) == 64)

    def test_extraction_orders_strictly_by_manifest(self):
        """Extraction must follow manifest.json sequence even if filenames sort differently."""
        # Create 3 images where natural sort would be: A (zebra), B (banana), C (apple)
        # But manifest specifies order: apple -> zebra -> banana
        img_apple = self._create_sample_image(self.temp_dir / "raw" / "apple.png", (255, 0, 0))
        img_banana = self._create_sample_image(self.temp_dir / "raw" / "banana.png", (255, 255, 0))
        img_zebra = self._create_sample_image(self.temp_dir / "raw" / "zebra.png", (0, 0, 0))

        zip_path = self.temp_dir / "manifest_test.zip"
        manifest_data = {
            "manifest_schema_version": "1.0",
            "images": [
                {"sequence_index": 1, "archive_filename": "zebra.png"},
                {"sequence_index": 2, "archive_filename": "apple.png"},
                {"sequence_index": 3, "archive_filename": "banana.png"}
            ]
        }

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(img_apple, arcname="apple.png")
            zf.write(img_banana, arcname="banana.png")
            zf.write(img_zebra, arcname="zebra.png")
            zf.writestr("manifest.json", json.dumps(manifest_data))

        res = process_zip_archive(zip_path, self.images_dir, self.work_dir, replace_existing=True)
        self.assertTrue(res["success"])
        self.assertEqual(res["ordering_source"], "manifest")
        self.assertFalse(res["ordering_ambiguous"])
        # Expected sequence: zebra.png, apple.png, banana.png
        self.assertEqual(res["files"], ["zebra.png", "apple.png", "banana.png"])

    def test_third_party_sequential_zip_natural_sort(self):
        """Third party archive with numbered files applies natural sort without ambiguity."""
        img1 = self._create_sample_image(self.temp_dir / "raw" / "img_2.jpg", (10, 10, 10))
        img2 = self._create_sample_image(self.temp_dir / "raw" / "img_1.jpg", (20, 20, 20))
        img3 = self._create_sample_image(self.temp_dir / "raw" / "img_10.jpg", (30, 30, 30))

        zip_path = self.temp_dir / "sequential.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(img1, arcname="img_2.jpg")
            zf.write(img2, arcname="img_1.jpg")
            zf.write(img3, arcname="img_10.jpg")

        res = process_zip_archive(zip_path, self.images_dir, self.work_dir, replace_existing=True)
        self.assertTrue(res["success"])
        self.assertEqual(res["ordering_source"], "natural_sort")
        self.assertFalse(res["ordering_ambiguous"])
        self.assertEqual(res["files"], ["img_1.jpg", "img_2.jpg", "img_10.jpg"])

    def test_third_party_random_hash_zip_detected_ambiguous(self):
        """Third party archive with random hash filenames is flagged as ordering_ambiguous."""
        h1 = self._create_sample_image(self.temp_dir / "raw" / "9f2d3b1a8c4e0f52.jpg")
        h2 = self._create_sample_image(self.temp_dir / "raw" / "1a4c8e0f529f2d3b.jpg")
        h3 = self._create_sample_image(self.temp_dir / "raw" / "e0f529f2d3b1a4c8.jpg")

        zip_path = self.temp_dir / "hashes.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(h1, arcname="9f2d3b1a8c4e0f52.jpg")
            zf.write(h2, arcname="1a4c8e0f529f2d3b.jpg")
            zf.write(h3, arcname="e0f529f2d3b1a4c8.jpg")

        res = process_zip_archive(zip_path, self.images_dir, self.work_dir, replace_existing=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["ordering_ambiguous"])
        self.assertEqual(res["ordering_source"], "natural_sort_ambiguous")
        self.assertIn("review", res["ordering_message"].lower())

    def test_non_destructive_append_preserves_existing_media(self):
        """replace_existing=False must NOT wipe previously existing images in library."""
        # Pre-populate library with existing image
        existing_img = self._create_sample_image(self.images_dir / "existing_hero.png", (100, 100, 100))

        new_img = self._create_sample_image(self.temp_dir / "raw" / "new_scene.png", (200, 200, 200))
        zip_path = self.temp_dir / "addon.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(new_img, arcname="new_scene.png")

        res = process_zip_archive(zip_path, self.images_dir, self.work_dir, replace_existing=False)
        self.assertTrue(res["success"])
        # Both images must exist in images_dir
        self.assertTrue((self.images_dir / "existing_hero.png").exists())
        self.assertTrue((self.images_dir / "new_scene.png").exists())


if __name__ == '__main__':
    unittest.main()

