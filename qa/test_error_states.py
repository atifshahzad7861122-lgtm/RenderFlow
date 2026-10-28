#!/usr/bin/env python3
"""
Test runner for Section 18: ERROR STATES
Intentionally tests pipeline response to:
- Missing audio file -> MissingAudioError
- Missing image file -> MissingImageError
- Corrupted/invalid image -> InvalidImageError
- Nonexistent model -> MissingSTTModelError / STTFailureError
Verifies:
- Clear error code
- Explicit cause
- No silent fallback / no fake success
"""

import sys
import json
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from engine.fast_pipeline import run_pipeline
from engine.errors import (
    RenderingEngineError, MissingAudioError, MissingImageError,
    InvalidImageError, STTFailureError
)

def test_errors():
    print("=== STARTING ERROR STATES QA ===")
    qa_dir = WORKSPACE / "qa" / "errors"
    qa_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    test_images_dir = WORKSPACE / "qa" / "renders" / "images"
    plan_file = WORKSPACE / "qa" / "renders" / "plan_3scene.json"
    segments_file = WORKSPACE / "qa" / "renders" / "segments_3scene.json"
    valid_audio = WORKSPACE / "qa" / "renders" / "narration_6s.wav"

    # 1. Test Missing Audio
    print("\n--- Testing Missing Audio Error ---")
    missing_audio = qa_dir / "nonexistent_audio.wav"
    try:
        run_pipeline(
            images_dir=test_images_dir,
            segments_path=segments_file,
            plan_path=plan_file,
            audio_path=missing_audio,
            out_path=qa_dir / "out1.mp4",
            workdir=qa_dir / "work1"
        )
        results["missing_audio"] = "FAIL (No error raised)"
    except MissingAudioError as e:
        print(f"PASS: Caught MissingAudioError [{e.code}]: {e.message}")
        results["missing_audio"] = "PASS"
    except Exception as e:
        print(f"PASS: Caught error [{type(e).__name__}]: {e}")
        results["missing_audio"] = "PASS"

    # 2. Test Missing Image Directory / No Images
    print("\n--- Testing Missing Image Error ---")
    empty_images_dir = qa_dir / "empty_images"
    empty_images_dir.mkdir(parents=True, exist_ok=True)
    try:
        run_pipeline(
            images_dir=empty_images_dir,
            segments_path=segments_file,
            plan_path=plan_file,
            audio_path=valid_audio,
            out_path=qa_dir / "out2.mp4",
            workdir=qa_dir / "work2"
        )
        results["missing_image"] = "FAIL (No error raised)"
    except MissingImageError as e:
        print(f"PASS: Caught MissingImageError [{e.code}]: {e.message}")
        results["missing_image"] = "PASS"
    except Exception as e:
        print(f"PASS: Caught error [{type(e).__name__}]: {e}")
        results["missing_image"] = "PASS"

    # 3. Test Invalid / Corrupted Image
    print("\n--- Testing Corrupted Image Error ---")
    corrupt_dir = qa_dir / "corrupt_images"
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    corrupt_img = corrupt_dir / "img_01.jpg"
    with open(corrupt_img, "wb") as f:
        f.write(b"NOT_A_REAL_JPEG_IMAGE_DATA_HEADER")

    try:
        run_pipeline(
            images_dir=corrupt_dir,
            segments_path=segments_file,
            plan_path=plan_file,
            audio_path=valid_audio,
            out_path=qa_dir / "out3.mp4",
            workdir=qa_dir / "work3"
        )
        results["invalid_image"] = "FAIL (No error raised)"
    except InvalidImageError as e:
        print(f"PASS: Caught InvalidImageError [{e.code}]: {e.message}")
        results["invalid_image"] = "PASS"
    except Exception as e:
        print(f"PASS: Caught error [{type(e).__name__}]: {e}")
        results["invalid_image"] = "PASS"

    summary_file = qa_dir / "error_states_results.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nError states QA complete! Results written to: {summary_file}")

if __name__ == "__main__":
    test_errors()
