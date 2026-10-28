#!/usr/bin/env python3
"""
Test runner for Section 10: HARDWARE QA - ENCODER FALLBACK
Requests 'h264_nvenc' on a machine without NVIDIA hardware.
Verifies graceful fallback to CPU 'libx264' with clear diagnostic logging.
"""

import sys
import json
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from engine.fast_pipeline import run_pipeline

def test_fallback():
    print("=== STARTING ENCODER FALLBACK QA ===")
    
    qa_dir = WORKSPACE / "qa" / "hardware"
    qa_dir.mkdir(parents=True, exist_ok=True)

    test_audio = WORKSPACE / "qa" / "renders" / "narration_6s.wav"
    test_images_dir = WORKSPACE / "qa" / "renders" / "images"
    plan_file = WORKSPACE / "qa" / "renders" / "plan_3scene.json"
    segments_file = WORKSPACE / "qa" / "renders" / "segments_3scene.json"
    
    out_mp4 = qa_dir / "fallback_render.mp4"
    work_dir = qa_dir / "work_fallback"
    if out_mp4.exists():
        out_mp4.unlink()

    t0 = time.time()
    res = run_pipeline(
        images_dir=test_images_dir,
        segments_path=segments_file,
        plan_path=plan_file,
        audio_path=test_audio,
        out_path=out_mp4,
        workdir=work_dir,
        preset="veryfast",
        resolution="1080p",
        encoder="h264_nvenc",  # Requesting NVENC intentionally
        perf_mode="balanced",
        skip_verify=False,
        enable_transitions=True,
        enable_captions=False
    )
    elapsed = time.time() - t0

    assert out_mp4.exists(), "Output video must exist after fallback"
    assert res["encoder"] == "libx264", f"Expected encoder libx264 fallback, got {res['encoder']}"
    print(f"PASS: NVENC request safely fell back to '{res['encoder']}' and rendered in {elapsed:.2f}s!")

    summary = {
        "requested_encoder": "h264_nvenc",
        "resolved_encoder": res["encoder"],
        "fallback_status": "PASS",
        "render_time_s": round(elapsed, 2),
        "output_file": str(out_mp4)
    }
    with open(qa_dir / "encoder_fallback_results.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    test_fallback()
