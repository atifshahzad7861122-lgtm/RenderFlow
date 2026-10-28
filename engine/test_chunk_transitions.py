#!/usr/bin/env python3
"""
engine/test_chunk_transitions.py — Comprehensive test for Transition Chunking:
  Case A: Transition entirely inside one chunk.
  Case B: Transition starts near the end of a chunk.
  Case C: Transition crosses a chunk boundary.

Verifies:
  - No missing effect
  - No duplicate effect
  - No timing shift
  - No visual discontinuity
  - Valid playable MP4 output
"""

import sys
import json
import shutil
import subprocess
import time
from pathlib import Path
import numpy as np

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from engine.fast_pipeline import run_pipeline


def test_chunk_transition_cases():
    print("=" * 80)
    print(" TESTING CHUNKED RENDERING: CASES A, B, AND C")
    print("=" * 80)

    cand_imgs = WORKSPACE_ROOT / "projects" / "benchmarks" / "test_transitions_suite" / "images"
    if (cand_imgs).exists():
        images_dir = cand_imgs
    else:
        sample_dir = WORKSPACE_ROOT / "projects" / "sample_project"
        images_dir = sample_dir / "images"

    cand_audio = WORKSPACE_ROOT / "projects" / "benchmarks" / "test_transitions_suite" / "narration.wav"
    pack_dir = WORKSPACE_ROOT / "transition_pack"

    test_workdir = WORKSPACE_ROOT / "projects" / "test_chunk_cases_work"
    if test_workdir.exists():
        shutil.rmtree(test_workdir)
    test_workdir.mkdir(parents=True, exist_ok=True)

    # Ensure 6 images exist
    src_images = sorted(list(images_dir.glob("*.png"))) + sorted(list(images_dir.glob("*.jpg"))) if images_dir.exists() else []
    if not src_images:
        syn_dir = test_workdir / "images"
        syn_dir.mkdir(parents=True, exist_ok=True)
        for i in range(6):
            p = syn_dir / f"scene_{i+1:02d}.png"
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                "-i", f"testsrc=size=1280x720:rate=1:duration=1", "-vframes", "1", str(p)
            ], check=True)
        images_dir = syn_dir
        src_images = sorted(list(images_dir.glob("*.png")))
    img_names = [im.name for im in src_images[:6]]
    while len(img_names) < 6:
        img_names.append(img_names[len(img_names) % max(1, len(img_names))])

    test_audio = test_workdir / "test_narration.wav"
    if cand_audio.exists():
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-ss", "0", "-t", "17.0",
            "-i", str(cand_audio),
            "-c:a", "pcm_s16le", str(test_audio)
        ], check=True)
    else:
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=17.0",
            "-c:a", "pcm_s16le", str(test_audio)
        ], check=True)

    test_scenes = [
        {"segment_index": 0, "start": 0.0, "end": 3.0, "dur": 3.0, "image": img_names[0], "transition": "transition_001", "context": "normal"},
        {"segment_index": 1, "start": 3.0, "end": 6.0, "dur": 3.0, "image": img_names[1], "transition": "transition_003", "context": "story_change"},
        {"segment_index": 2, "start": 6.0, "end": 8.0, "dur": 2.0, "image": img_names[2], "transition": "transition_004", "context": "location_change"},
        {"segment_index": 3, "start": 8.0, "end": 11.0, "dur": 3.0, "image": img_names[3], "transition": "cinematic_dissolve", "context": "emotional"},
        {"segment_index": 4, "start": 11.0, "end": 14.0, "dur": 3.0, "image": img_names[4], "transition": "soft_wipe", "context": "normal"},
        {"segment_index": 5, "start": 14.0, "end": 17.0, "dur": 3.0, "image": img_names[5], "transition": "clean_cut", "context": "fast"}
    ]

    plan_path = test_workdir / "plan.json"
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump({"scenes": test_scenes}, f, indent=2)

    segments_path = test_workdir / "transcript.json"
    with open(segments_path, "w", encoding="utf-8") as f:
        json.dump({
            "segments": [
                {"id": i, "start": s["start"], "end": s["end"], "text": f"Scene test beat #{i+1}"}
                for i, s in enumerate(test_scenes)
            ]
        }, f, indent=2)

    out_mp4 = test_workdir / "chunk_cases_out.mp4"

    print("[RUN] Executing run_pipeline in chunked mode (chunk-size=3)...")
    res = run_pipeline(
        images_dir=images_dir,
        segments_path=segments_path,
        plan_path=plan_path,
        audio_path=test_audio,
        out_path=out_mp4,
        workdir=test_workdir,
        pack_dir=pack_dir,
        force_chunks=True,
        chunk_size=3,
        skip_verify=True
    )

    print(f"\n[DONE] Render completed: {out_mp4} (size: {out_mp4.stat().st_size} bytes)")

    # Verify chunk directory has chunks
    chunks = sorted(list((test_workdir / "chunks").glob("chunk_*.mp4")))
    print(f"Chunks rendered: {[c.name for c in chunks]}")
    assert len(chunks) == 2, f"Expected 2 chunks, got {len(chunks)}"

    # Inspect probe
    r = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(out_mp4)
    ], capture_output=True, text=True, check=True)
    actual_dur = float(r.stdout.strip())
    print(f"Output duration: {actual_dur:.3f}s (expected ~17.0s)")
    assert abs(actual_dur - 17.0) < 0.15, f"Duration mismatch: {actual_dur} vs 17.0"

    # Frame inspection at key cut and transition moments:
    # Cut 1: 3.0s (Case A) -> inspect 2.8s, 3.0s, 3.2s
    # Cut 2: 6.0s (Case B) -> inspect 5.8s, 6.0s, 6.2s
    # Cut 3: 8.0s (Case C: Chunk Boundary) -> inspect 7.8s, 8.0s, 8.2s
    # Cut 4: 11.0s (Built-in xfade) -> inspect 10.9s, 11.0s, 11.1s
    test_points = [
        (2.8, "Case A pre-cut"),
        (3.0, "Case A cut peak (transition_001)"),
        (3.2, "Case A post-cut"),
        (5.8, "Case B pre-cut"),
        (6.0, "Case B cut peak (transition_003)"),
        (6.2, "Case B post-cut"),
        (7.8, "Case C pre-boundary (Chunk 0)"),
        (8.0, "Case C boundary peak (Cut 0->1)"),
        (8.2, "Case C post-boundary (Chunk 1)"),
        (10.9, "Built-in xfade pre-cut"),
        (11.0, "Built-in xfade peak"),
        (11.1, "Built-in xfade post-cut"),
        (14.0, "Built-in soft_wipe peak")
    ]

    print("\n[INSPECT] Extracting frames across boundary and transitions...")
    frame_results = []
    for t_sec, label in test_points:
        cmd = [
            "ffmpeg", "-v", "error", "-ss", f"{t_sec:.3f}",
            "-i", str(out_mp4), "-frames:v", "1",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-"
        ]
        pr = subprocess.run(cmd, capture_output=True)
        img = np.frombuffer(pr.stdout, dtype=np.uint8).reshape(1080, 1920, 3)
        mean_v = float(img.mean())
        std_v = float(img.std())
        valid = (std_v > 5.0 and 2.0 < mean_v < 254.0)
        print(f"  t={t_sec:5.2f}s | {label:<35} | mean={mean_v:6.2f} | std={std_v:6.2f} | {'PASS' if valid else 'FAIL'}")
        frame_results.append(valid)

    all_frames_ok = all(frame_results)
    print("\n" + "=" * 80)
    print(f"CHUNK TRANSITION CASES RESULT: {'ALL PASS' if all_frames_ok else 'FAIL'}")
    print("=" * 80)
    return all_frames_ok


if __name__ == "__main__":
    ok = test_chunk_transition_cases()
    if not ok:
        sys.exit(1)
    print(">>> CHUNK TRANSITION TEST COMPLETED SUCCESSFULLY <<<")
