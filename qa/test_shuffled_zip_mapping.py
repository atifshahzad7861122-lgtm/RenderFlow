#!/usr/bin/env python3
"""
qa/test_shuffled_zip_mapping.py — Regression Test for AI Semantic Image Mapping.
Validates Non-Negotiable Principle:
  "Narration meaning determines visual order. Filenames and archive order do not determine visual order."
"""

import os
import sys
import shutil
import zipfile
import numpy as np
from PIL import Image
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from engine.sync_engine_v3 import AIImageSyncEngineV3, SyncConfig
from engine.sync_v3_intelligence import MappingMode
from engine.visual_analyzer import VisualContentAnalyzer

def create_test_images(staging_dir: Path):
    """Create semantically distinctive images with deliberately misleading filenames."""
    staging_dir.mkdir(parents=True, exist_ok=True)

    # 1. Blue Seascape (ocean, water, waves) -> Named img_99_forest_trees.jpg
    blue_img = np.zeros((400, 600, 3), dtype=np.uint8)
    blue_img[:, :] = [30, 90, 210]  # Deep azure ocean blue
    blue_path = staging_dir / "img_99_forest_trees.jpg"
    Image.fromarray(blue_img).save(blue_path, "JPEG")

    # 2. Green Nature (forest, trees, vegetation) -> Named scene_01_vast_ocean.png
    green_img = np.zeros((400, 600, 3), dtype=np.uint8)
    green_img[:, :] = [34, 160, 48]  # Lush emerald green
    green_path = staging_dir / "scene_01_vast_ocean.png"
    Image.fromarray(green_img).save(green_path, "PNG")

    # 3. Red Earth / Desert (sand, canyon, mars) -> Named final_0007_arctic_glacier.webp
    red_img = np.zeros((400, 600, 3), dtype=np.uint8)
    red_img[:, :] = [215, 65, 30]   # Scorching terracotta red
    red_path = staging_dir / "final_0007_arctic_glacier.webp"
    Image.fromarray(red_img).save(red_path, "WEBP")

    return blue_path, green_path, red_path


def main():
    print("=" * 70)
    print("RUNNING QA TEST: SHUFFLED ZIP SEMANTIC IMAGE MAPPING")
    print("=" * 70)

    qa_dir = ROOT_DIR / "qa" / "renders" / "test_shuffled_sync"
    if qa_dir.exists():
        shutil.rmtree(qa_dir, ignore_errors=True)
    qa_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create images
    blue_p, green_p, red_p = create_test_images(qa_dir / "images")
    print(f"Created blue ocean image: {blue_p.name} (Misleading name!)")
    print(f"Created green forest image: {green_p.name} (Misleading name!)")
    print(f"Created red desert image: {red_p.name} (Misleading name!)")

    # 2. Package into a deliberately shuffled ZIP archive
    zip_path = qa_dir / "shuffled_assets.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        # Deliberate reverse order in archive
        zf.write(blue_p, arcname="img_99_forest_trees.jpg")
        zf.write(red_p, arcname="final_0007_arctic_glacier.webp")
        zf.write(green_p, arcname="scene_01_vast_ocean.png")
    print(f"Packaged into shuffled ZIP archive: {zip_path.name}")

    # 3. Create a synthetic test audio with 3 distinct narrative beats
    # Audio duration 9.0s: 0-3s Ocean, 3-6s Forest, 6-9s Desert
    audio_path = ROOT_DIR / "qa" / "renders" / "narration_6s.wav"
    if not audio_path.exists():
        audio_path = ROOT_DIR / "test_short_audio.wav"

    transcript_path = qa_dir / "transcript.json"
    import json
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump({
            "segments": [
                {"id": 1, "start": 0.0, "end": 3.0, "text": "Deep beneath the rolling waves of the blue ocean, marine waters stretch endlessly across the horizon."},
                {"id": 2, "start": 3.0, "end": 6.0, "text": "Venturing inland into the lush green forest, towering trees and fertile vegetation blanket the natural landscape."},
                {"id": 3, "start": 6.0, "end": 9.0, "text": "Finally arriving at the scorching red desert canyon, the dry earth and barren terrain glow beneath the fiery sun."}
            ]
        }, f, indent=2)

    # 4. Run AI Image Sync Engine v3 in SEMANTIC_AUTO mode
    engine = AIImageSyncEngineV3()
    
    # Test with Order A: [scene_01_vast_ocean.png, img_99_forest_trees.jpg, final_0007_arctic_glacier.webp]
    order_a = ["scene_01_vast_ocean.png", "img_99_forest_trees.jpg", "final_0007_arctic_glacier.webp"]
    print("\nRunning Order A...")
    t_obj_a, plan_a, report_a = engine.synchronize_timeline(
        audio_path=audio_path,
        images_dir=qa_dir / "images",
        image_filenames=order_a,
        transcript_path=transcript_path,
        all_images_mode=True,
        mapping_mode="SEMANTIC_AUTO"
    )

    scenes_a = plan_a["scenes"]
    print("\nOrder A Mapped Plan:")
    for i, sc in enumerate(scenes_a):
        print(f"  Scene {i+1} [{sc['start']:.1f}s - {sc['end']:.1f}s]: {sc['image']} (Conf: {sc['confidence_level']} {sc['confidence']:.2f}, Why: {sc['match_reason']})")

    # Assertions for Order A:
    # Beat 1 (Ocean) MUST be blue image (img_99_forest_trees.jpg), NOT scene_01_vast_ocean.png (which is green)!
    assert scenes_a[0]["image"] == "img_99_forest_trees.jpg", f"FAIL: Expected blue image for ocean beat, got {scenes_a[0]['image']}"
    # Beat 2 (Forest) MUST be green image (scene_01_vast_ocean.png), NOT img_99!
    assert scenes_a[1]["image"] == "scene_01_vast_ocean.png", f"FAIL: Expected green image for forest beat, got {scenes_a[1]['image']}"
    # Beat 3 (Desert) MUST be red image (final_0007_arctic_glacier.webp)
    assert scenes_a[2]["image"] == "final_0007_arctic_glacier.webp", f"FAIL: Expected red image for desert beat, got {scenes_a[2]['image']}"

    print("\n[PASS] Order A Passed: Content determined placement regardless of misleading filenames!")

    # Test with Shuffled Order B: [final_0007_arctic_glacier.webp, scene_01_vast_ocean.png, img_99_forest_trees.jpg]
    order_b = ["final_0007_arctic_glacier.webp", "scene_01_vast_ocean.png", "img_99_forest_trees.jpg"]
    print("\nRunning Shuffled Order B...")
    t_obj_b, plan_b, report_b = engine.synchronize_timeline(
        audio_path=audio_path,
        images_dir=qa_dir / "images",
        image_filenames=order_b,
        transcript_path=transcript_path,
        all_images_mode=True,
        mapping_mode="SEMANTIC_AUTO"
    )

    scenes_b = plan_b["scenes"]
    print("\nOrder B Mapped Plan:")
    for i, sc in enumerate(scenes_b):
        print(f"  Scene {i+1} [{sc['start']:.1f}s - {sc['end']:.1f}s]: {sc['image']}")

    # Assertions for Order B:
    assert scenes_b[0]["image"] == "img_99_forest_trees.jpg", f"FAIL: Shuffled archive changed ocean assignment to {scenes_b[0]['image']}"
    assert scenes_b[1]["image"] == "scene_01_vast_ocean.png", f"FAIL: Shuffled archive changed forest assignment to {scenes_b[1]['image']}"
    assert scenes_b[2]["image"] == "final_0007_arctic_glacier.webp", f"FAIL: Shuffled archive changed desert assignment to {scenes_b[2]['image']}"

    print("\n[PASS] Order B Passed: Shuffling input archive produces identical semantic mapping!")

    # Test Manual Override preservation
    print("\nTesting User Manual Override Preservation...")
    user_overrides = {0: "final_0007_arctic_glacier.webp"} # Force red image to beat 1
    t_obj_c, plan_c, report_c = engine.synchronize_timeline(
        audio_path=audio_path,
        images_dir=qa_dir / "images",
        image_filenames=order_a,
        transcript_path=transcript_path,
        all_images_mode=True,
        user_overrides=user_overrides,
        mapping_mode="SEMANTIC_AUTO"
    )
    scenes_c = plan_c["scenes"]
    assert scenes_c[0]["image"] == "final_0007_arctic_glacier.webp", "FAIL: User manual override was not preserved!"
    assert scenes_c[0]["user_override"] is True, "FAIL: user_override flag not set!"
    print(f"[PASS] Manual Override Passed: Scene 1 respected user lock ({scenes_c[0]['image']})")

    print("\n" + "=" * 70)
    print("ALL SHUFFLED ZIP SEMANTIC MAPPING ACCEPTANCE TESTS PASSED!")
    print("=" * 70)


def test_shuffled_zip_mapping():
    main()


if __name__ == "__main__":
    main()
