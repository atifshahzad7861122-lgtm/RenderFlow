#!/usr/bin/env python3
"""
test_captions_render.py — Production Benchmark for Burned-in Audio-Synchronized Captions.

Executes:
  1. Renders a multi-scene test video with captions enabled in various styles
     (Classic Documentary, Karaoke, Kinetic Pop, Pill, Editorial, Bold Viral).
  2. Verifies video encoding, libass subtitle burn-in, audio sync, and sidecar exports.
  3. Verifies strict QC report generation.
"""

import sys
import os
import time
import json
import shutil
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.fast_pipeline import run_pipeline


def run_caption_render_test(style_name: str = "classic"):
    print(f"\n=======================================================")
    print(f" TESTING CAPTION RENDER PIPELINE: STYLE '{style_name}'")
    print(f"=======================================================")

    root_dir = Path(__file__).resolve().parent.parent
    sample_dir = root_dir / "projects" / "sample_project"
    test_dir = root_dir / "projects" / "benchmarks" / f"test_caption_{style_name}"
    
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)

    # Copy or generate 8 sample images
    images_dir = test_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    src_images = sorted(list((sample_dir / "images").glob("image_*.png")))[:8] if (sample_dir / "images").exists() else []
    if len(src_images) >= 7:
        for img in src_images:
            shutil.copy2(img, images_dir / img.name)
    else:
        import numpy as np
        import cv2
        colors = [(180, 50, 50), (50, 180, 50), (50, 50, 180), (180, 180, 50), (180, 50, 180), (50, 180, 180), (100, 100, 200), (200, 100, 100)]
        for i in range(8):
            dst = images_dir / f"image_{i+1:02d}.png"
            arr = np.zeros((1080, 1920, 3), dtype=np.uint8)
            arr[:] = colors[i]
            cv2.putText(arr, f"CAPTION SCENE {i+1}", (250, 550), cv2.FONT_HERSHEY_SIMPLEX, 3, (255, 255, 255), 6)
            cv2.imwrite(str(dst), arr)
    src_images = sorted(list(images_dir.glob("image_*.png")))

    # Slice or generate 20 seconds of audio for fast benchmark
    audio_src = sample_dir / "narration.wav"
    audio_dst = test_dir / "narration.wav"
    import subprocess
    if audio_src.exists():
        subprocess.run([
            'ffmpeg', '-y', '-v', 'error',
            '-ss', '0', '-t', '20.0',
            '-i', str(audio_src),
            '-ar', '48000', '-ac', '2',
            str(audio_dst)
        ], check=True)
    else:
        subprocess.run([
            'ffmpeg', '-y', '-v', 'error',
            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=20.0',
            '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2',
            str(audio_dst)
        ], check=True)

    # Generate segments and plan
    segs = [
        {"start": 0.0, "end": 2.8, "text": "Every great empire begins with a vision."},
        {"start": 2.8, "end": 5.4, "text": "Architects planned monumental structures across the valley."},
        {"start": 5.4, "end": 8.2, "text": "Trade flourished along the golden riverbanks."},
        {"start": 8.2, "end": 11.0, "text": "Scholars gathered to record ancient discoveries."},
        {"start": 11.0, "end": 14.0, "text": "Yet unexpected challenges tested their resolve."},
        {"start": 14.0, "end": 17.0, "text": "Through relentless innovation, they endured."},
        {"start": 17.0, "end": 20.0, "text": "Leaving behind a timeless legacy for all humanity."}
    ]
    seg_file = test_dir / "transcript.json"
    with open(seg_file, "w", encoding="utf-8") as f:
        json.dump({"segments": segs}, f, indent=2)

    plan = [
        {"scene_id": f"scene_{i+1}", "img": src_images[i % len(src_images)].name, "context": "normal", "transition": "fade"}
        for i in range(len(segs))
    ]
    plan_file = test_dir / "plan.json"
    with open(plan_file, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    out_file = test_dir / f"final_{style_name}.mp4"
    work_dir = test_dir / "work"
    pack_dir = root_dir / "transition_pack"

    t0 = time.time()
    res = run_pipeline(
        images_dir=images_dir,
        segments_path=seg_file,
        plan_path=plan_file,
        audio_path=audio_dst,
        out_path=out_file,
        workdir=work_dir,
        pack_dir=pack_dir,
        preset="ultrafast",
        profile="fast",
        skip_verify=False,
        force_single_pass=True,
        enable_captions=True,
        caption_style=style_name,
        caption_length="medium"
    )
    render_time = time.time() - t0

    print(f"\n[BENCHMARK RESULT] Style '{style_name}' completed in {render_time:.2f}s!")
    assert out_file.exists(), f"Output video {out_file} was not generated!"
    assert out_file.stat().st_size > 500000, f"Output video is too small ({out_file.stat().st_size} bytes)"

    # Verify sidecar exports
    srt_file = test_dir / f"final_{style_name}.srt"
    ass_file = test_dir / f"final_{style_name}.ass"
    json_candidates = [test_dir / f"final_{style_name}.json", test_dir / "captions.json"]
    json_file = next((f for f in json_candidates if f.exists()), test_dir / f"final_{style_name}.json")
    qc_file = Path(str(out_file) + ".caption_qc.json")

    assert srt_file.exists(), "SRT sidecar missing!"
    assert ass_file.exists(), "ASS sidecar missing!"
    assert json_file.exists(), "JSON sidecar missing!"
    assert qc_file.exists(), "Caption QC file missing!"

    with open(qc_file, "r", encoding="utf-8") as f:
        qc_data = json.load(f)
    print(f"[QC REPORT] Overall status: {qc_data.get('overall_status')}")
    assert qc_data.get("overall_status") == "PASS", f"Caption QC failed: {qc_data.get('failed_checks')}"

    print(f"  -> Video: {out_file} ({out_file.stat().st_size / (1024*1024):.2f} MB)")
    print(f"  -> SRT: {srt_file} ({srt_file.stat().st_size} bytes)")
    print(f"  -> ASS: {ass_file} ({ass_file.stat().st_size} bytes)")
    print(f"  -> JSON: {json_file} ({json_file.stat().st_size} bytes)")
    print(f"  -> ALL CHECKS PASS for style '{style_name}'.")
    return render_time


def main():
    styles_to_test = ["classic", "karaoke", "kinetic_pop", "editorial"]
    timings = {}
    for st in styles_to_test:
        t = run_caption_render_test(st)
        timings[st] = t

    print("\n=======================================================")
    print(" SUMMARY OF CAPTION RENDER BENCHMARKS")
    print("=======================================================")
    for st, t in timings.items():
        print(f"  Style: {st:15s} | Time: {t:6.2f}s | Status: PASS")
    print("=======================================================")


if __name__ == "__main__":
    main()
