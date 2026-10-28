#!/usr/bin/env python3
"""
test_all_transitions.py — Rigorous verification of all required cinematic transition styles:
  1. normal dissolve (fade)
  2. soft directional (wipeleft)
  3. cinematic dissolve (dissolve)
  4. dip to black (fadeblack)
  5. clean cut (fadefast)
  6. slow dissolve (dissolve 0.50s)

Ensures none creates accidental uniform frames, and validates dip-to-black intentionality.
"""
import json
import subprocess
import sys
import time
from pathlib import Path
import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT_DIR = HERE.parent

def test_transition_suite():
    print("=" * 70)
    print(" RUNNING TRANSITION VALIDATION TEST SUITE")
    print("=" * 70)

    test_dir = ROOT_DIR / "projects" / "benchmarks" / "test_transitions_suite"
    test_dir.mkdir(parents=True, exist_ok=True)
    images_dir = test_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # 1. Source images
    sample_imgs_src = list((ROOT_DIR / "projects" / "sample_project" / "images").glob("*.*"))
    if not sample_imgs_src:
        sample_imgs_src = list((ROOT_DIR / "projects" / "Video1" / "images").glob("*.*"))
    
    selected_imgs = []
    colors = [
        (180, 50, 50), (50, 180, 50), (50, 50, 180),
        (180, 180, 50), (180, 50, 180), (50, 180, 180), (100, 100, 100)
    ]
    for i in range(7):
        dst_im = images_dir / f"test_img_{i+1:02d}.jpg"
        if sample_imgs_src:
            src_im = sample_imgs_src[i % len(sample_imgs_src)]
            if not dst_im.exists():
                dst_im.write_bytes(src_im.read_bytes())
        else:
            if not dst_im.exists():
                arr = np.zeros((1080, 1920, 3), dtype=np.uint8)
                arr[:] = colors[i]
                cv2.putText(arr, f"SCENE {i+1}", (300, 550), cv2.FONT_HERSHEY_SIMPLEX, 4, (255, 255, 255), 8)
                cv2.imwrite(str(dst_im), arr)
        selected_imgs.append(dst_im.name)

    # 2. Build 6 transitions:
    # Scene 1 -> 2: normal dissolve (fade, 0.35s)
    # Scene 2 -> 3: soft directional (soft_wipe / wipeleft, 0.35s)
    # Scene 3 -> 4: cinematic dissolve (dissolve, 0.40s)
    # Scene 4 -> 5: dip to black (dip_to_black / fadeblack, 0.40s)
    # Scene 5 -> 6: clean cut (clean_cut / fadefast, 0.10s)
    # Scene 6 -> 7: slow dissolve (slow_dissolve / dissolve, 0.50s)
    transition_specs = [
        {"trans": "dissolve", "label": "normal dissolve"},
        {"trans": "soft_wipe", "label": "soft directional"},
        {"trans": "cinematic_dissolve", "label": "cinematic dissolve"},
        {"trans": "dip_to_black", "label": "dip to black"},
        {"trans": "clean_cut", "label": "clean cut"},
        {"trans": "slow_dissolve", "label": "slow dissolve"}
    ]

    scenes = []
    segments = []
    t = 0.0
    scene_dur = 3.0  # 3 seconds per scene = 21 seconds total
    for i in range(7):
        tr = transition_specs[i]["trans"] if i < len(transition_specs) else "dissolve"
        scenes.append({
            "segment_index": i,
            "image": selected_imgs[i],
            "context": "normal",
            "transition": tr,
            "start": round(t, 3),
            "end": round(t + scene_dur, 3),
            "dur": scene_dur
        })
        segments.append({
            "start": round(t, 3),
            "end": round(t + scene_dur, 3),
            "text": f"Transition test scene {i+1}"
        })
        t += scene_dur

    total_dur = t
    plan_file = test_dir / "plan.json"
    plan_file.write_text(json.dumps({"scenes": scenes}, indent=2), encoding="utf-8")
    
    seg_file = test_dir / "segments.json"
    seg_file.write_text(json.dumps({"segments": segments}, indent=2), encoding="utf-8")

    # 3. Audio file (synthesized 21s tone/narration)
    master_audio = ROOT_DIR / "projects" / "sample_project" / "narration.wav"
    audio_dst = test_dir / "narration.wav"
    if master_audio.exists():
        cmd_audio = [
            'ffmpeg', '-y', '-stream_loop', '-1', '-i', str(master_audio),
            '-t', f'{total_dur:.3f}', '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2',
            str(audio_dst)
        ]
    else:
        cmd_audio = [
            'ffmpeg', '-y', '-f', 'lavfi', '-i', f'sine=frequency=440:duration={total_dur:.3f}',
            '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2',
            str(audio_dst)
        ]
    subprocess.run(cmd_audio, check=True, capture_output=True)

    # 4. Render via fast_pipeline.py
    out_video = test_dir / "test_transitions.mp4"
    work_dir = test_dir / "work"
    cmd_render = [
        sys.executable, str(HERE / "fast_pipeline.py"),
        "--images", str(images_dir),
        "--segments", str(seg_file),
        "--plan", str(plan_file),
        "--audio", str(audio_dst),
        "--out", str(out_video),
        "--workdir", str(work_dir),
        "--force-single-pass"
    ]
    print("Executing render for 6 transition test sequence...", flush=True)
    t0 = time.time()
    res = subprocess.run(cmd_render, capture_output=True, text=True)
    t_render = time.time() - t0
    print(res.stdout)
    if res.returncode != 0:
        print("STDERR:", res.stderr)
        raise RuntimeError(f"Render failed with code {res.returncode}")

    print(f"Render completed in {t_render:.2f}s! Verifying output...", flush=True)

    # 5. Run verify_output.py
    cmd_verify = [
        sys.executable, str(HERE / "verify_output.py"),
        "--video", str(out_video),
        "--scenes", str(work_dir / "scene_labels.json"),
        "--sheet", str(work_dir / "contact_sheet.png")
    ]
    vr = subprocess.run(cmd_verify, capture_output=True, text=True)
    print(vr.stdout)
    if vr.returncode != 0:
        print("VERIFY ERROR:", vr.stderr)
        raise RuntimeError("Transition suite verification failed!")

    print("\n" + "=" * 70)
    print(" ALL 6 TRANSITIONS PASSED VERIFICATION WITH ZERO UNIFORM BUGS!")
    print("=" * 70)
    return True

if __name__ == '__main__':
    test_transition_suite()
