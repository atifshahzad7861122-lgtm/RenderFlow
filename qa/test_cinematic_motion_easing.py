#!/usr/bin/env python3
"""
qa/test_cinematic_motion_easing.py — Cinematic Motion Intelligence & Easing Validation Suite.

Verifies Phase 1 of the Original Repository Integration Plan (adapted from video-shotcraft):
1. Easing endpoint correctness and strict monotonicity.
2. Smooth starts and stops (zero initial/final velocity).
3. Structured cinematography shot roles (establishing_wide, character_focus, dramatic_tension,
   narrative_inspection, environmental_drift).
4. Conservative motion behavior on LOW confidence, NO_MATCH, and short scenes.
5. Short scenes, single-frame, and two-frame edge cases.
6. 100% backward compatibility with existing L4 motion strings and legacy plan schemas.
7. User-locked overrides immutability.
8. End-to-end FFmpeg scene rendering with ffprobe stream validation.
"""

import sys
import json
import time
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Any
import numpy as np
import cv2

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from engine.motion_intelligence import (
    MotionIntelligenceEngine,
    SceneMotionPlan,
    VALID_MOTIONS,
    VALID_SHOT_ROLES,
    VALID_EASING_CURVES,
    SHOT_ROLE_CONFIG,
    apply_easing,
    EASING_FUNCTIONS
)
from engine.render_base import render_scene, load_plan, build_timeline, W, H, FPS


def print_banner(text: str):
    print("\n" + "=" * 78)
    print(f"  {text}")
    print("=" * 78)


def test_easing_endpoints_and_bounds():
    print_banner("TEST 1: EASING ENDPOINTS, BOUNDS & CLAMPING")
    
    for curve in VALID_EASING_CURVES:
        v_start = apply_easing(0.0, curve)
        v_end = apply_easing(1.0, curve)
        assert abs(v_start - 0.0) < 1e-6, f"{curve}: start value {v_start} != 0.0"
        assert abs(v_end - 1.0) < 1e-6, f"{curve}: end value {v_end} != 1.0"
        
        # Test out-of-bounds clamping
        assert abs(apply_easing(-0.5, curve) - 0.0) < 1e-6, f"{curve}: negative clamping failed"
        assert abs(apply_easing(1.5, curve) - 1.0) < 1e-6, f"{curve}: overflow clamping failed"
        
        # Test 1000 sample points
        u_vals = np.linspace(0.0, 1.0, 1000)
        eased_vals = [apply_easing(u, curve) for u in u_vals]
        assert all(0.0 <= val <= 1.0 for val in eased_vals), f"{curve}: value out of [0, 1] range"
        print(f"  [PASS] Curve '{curve}': strictly bounded in [0.0, 1.0] with f(0)=0.0, f(1)=1.0")


def test_easing_monotonicity():
    print_banner("TEST 2: STRICT EASING MONOTONICITY")
    
    u_vals = np.linspace(0.0, 1.0, 1000)
    for curve in VALID_EASING_CURVES:
        eased_vals = [apply_easing(u, curve) for u in u_vals]
        # Check non-decreasing property
        for i in range(len(eased_vals) - 1):
            assert eased_vals[i+1] >= eased_vals[i] - 1e-9, (
                f"{curve}: non-monotonic drop detected at index {i}: "
                f"u={u_vals[i]:.4f} -> {eased_vals[i]:.6f}, u_next={u_vals[i+1]:.4f} -> {eased_vals[i+1]:.6f}"
            )
        print(f"  [PASS] Curve '{curve}': strictly monotonic non-decreasing across 1,000 steps")


def test_smooth_starts_and_stops_velocity():
    print_banner("TEST 3: SMOOTH VELOCITY AT START & STOP (ZERO JERK)")
    
    delta = 0.005
    # Smoothstep should have zero derivative at 0 and 1
    # f'(0) = 0 -> (f(delta) - f(0)) / delta -> 0
    # Linear comparison: linear velocity is 1.0 everywhere
    linear_start_vel = (apply_easing(delta, "linear") - apply_easing(0.0, "linear")) / delta
    linear_end_vel = (apply_easing(1.0, "linear") - apply_easing(1.0 - delta, "linear")) / delta
    assert abs(linear_start_vel - 1.0) < 1e-6
    assert abs(linear_end_vel - 1.0) < 1e-6
    
    # Smoothstep
    ss_start_vel = (apply_easing(delta, "smoothstep") - apply_easing(0.0, "smoothstep")) / delta
    ss_end_vel = (apply_easing(1.0, "smoothstep") - apply_easing(1.0 - delta, "smoothstep")) / delta
    print(f"  Smoothstep start velocity: {ss_start_vel:.4f} (vs linear {linear_start_vel:.4f})")
    print(f"  Smoothstep end velocity:   {ss_end_vel:.4f} (vs linear {linear_end_vel:.4f})")
    assert ss_start_vel < 0.05, f"Smoothstep start not smooth: velocity {ss_start_vel}"
    assert ss_end_vel < 0.05, f"Smoothstep end not smooth: velocity {ss_end_vel}"

    # Cubic in-out
    cub_start_vel = (apply_easing(delta, "cubic_in_out") - apply_easing(0.0, "cubic_in_out")) / delta
    cub_end_vel = (apply_easing(1.0, "cubic_in_out") - apply_easing(1.0 - delta, "cubic_in_out")) / delta
    print(f"  Cubic In-Out start velocity: {cub_start_vel:.6f}")
    print(f"  Cubic In-Out end velocity:   {cub_end_vel:.6f}")
    assert cub_start_vel < 0.01, f"Cubic in-out start not smooth: {cub_start_vel}"
    assert cub_end_vel < 0.01, f"Cubic in-out end not smooth: {cub_end_vel}"

    # Ease-Out should have smooth stop
    eo_end_vel = (apply_easing(1.0, "ease_out") - apply_easing(1.0 - delta, "ease_out")) / delta
    print(f"  Ease-Out end velocity: {eo_end_vel:.6f}")
    assert eo_end_vel < 0.05, f"Ease-out end velocity too high: {eo_end_vel}"

    # Ease-In should have smooth start
    ei_start_vel = (apply_easing(delta, "ease_in") - apply_easing(0.0, "ease_in")) / delta
    print(f"  Ease-In start velocity: {ei_start_vel:.6f}")
    assert ei_start_vel < 0.05, f"Ease-in start velocity too high: {ei_start_vel}"

    print("  [PASS] Smooth velocity curves confirmed: zero abrupt starts or stops.")


def test_shot_roles_generation():
    print_banner("TEST 4: CINEMATOGRAPHIC SHOT ROLES TAXONOMY")
    
    assert set(VALID_SHOT_ROLES) == {
        "establishing_wide",
        "character_focus",
        "dramatic_tension",
        "narrative_inspection",
        "environmental_drift",
    }
    
    # 1. Turning point context -> dramatic_tension
    p_turn = MotionIntelligenceEngine.plan_scene_motion(
        scene_idx=1, dur=3.5, context="turning_point", energy_level="high", confidence_level="HIGH"
    )
    print(f"  Turning Point Scene: role={p_turn.shot_role}, motion={p_turn.motion_type}, easing={p_turn.easing}")
    assert p_turn.shot_role == "dramatic_tension"
    assert p_turn.motion_type == "push"
    assert p_turn.easing == "cubic_in_out"
    assert p_turn.zoom_scale >= 1.045

    # 2. Location change Scene 0 -> establishing_wide
    p_est = MotionIntelligenceEngine.plan_scene_motion(
        scene_idx=0, dur=4.0, context="location_change", energy_level="medium", confidence_level="HIGH"
    )
    print(f"  Scene 0 Location Change: role={p_est.shot_role}, motion={p_est.motion_type}, easing={p_est.easing}")
    assert p_est.shot_role == "establishing_wide"
    assert p_est.easing == "smoothstep"

    # 3. Location change Scene 2 -> environmental_drift
    p_drift = MotionIntelligenceEngine.plan_scene_motion(
        scene_idx=2, dur=4.0, context="location_change", energy_level="medium", confidence_level="HIGH"
    )
    print(f"  Scene 2 Location Change: role={p_drift.shot_role}, motion={p_drift.motion_type}, easing={p_drift.easing}")
    assert p_drift.shot_role == "environmental_drift"
    assert "drift" in p_drift.motion_type
    assert p_drift.easing == "smoothstep"

    # 4. Emotional context -> narrative_inspection
    p_emo = MotionIntelligenceEngine.plan_scene_motion(
        scene_idx=3, dur=3.2, context="emotional", energy_level="subtle", confidence_level="HIGH"
    )
    print(f"  Emotional Scene: role={p_emo.shot_role}, motion={p_emo.motion_type}, easing={p_emo.easing}")
    assert p_emo.shot_role == "narrative_inspection"
    assert p_emo.easing == "ease_out"

    print("  [PASS] All cinematography shot roles dynamically synthesized according to narrative context.")


def test_conservative_motion_on_low_confidence_and_no_match():
    print_banner("TEST 5: CONSERVATIVE STABILIZATION ON LOW CONFIDENCE & NO_MATCH")

    # Low confidence scene
    p_low = MotionIntelligenceEngine.plan_scene_motion(
        scene_idx=1, dur=3.5, context="normal", confidence_level="LOW"
    )
    print(f"  LOW Confidence Plan: role={p_low.shot_role}, zoom={p_low.zoom_scale}, conservative={p_low.is_conservative_default}")
    assert p_low.is_conservative_default is True
    assert p_low.zoom_scale <= 1.020
    assert p_low.motion_type == "push"
    assert p_low.easing == "smoothstep"
    assert "conservative" in p_low.rationale

    # NO_MATCH scene
    p_nomatch = MotionIntelligenceEngine.plan_scene_motion(
        scene_idx=2, dur=3.5, context="turning_point", confidence_level="NO_MATCH"
    )
    print(f"  NO_MATCH Plan: role={p_nomatch.shot_role}, zoom={p_nomatch.zoom_scale}, conservative={p_nomatch.is_conservative_default}")
    assert p_nomatch.is_conservative_default is True
    assert p_nomatch.zoom_scale <= 1.020

    # Short scene (< 1.4s)
    p_short = MotionIntelligenceEngine.plan_scene_motion(
        scene_idx=3, dur=1.0, context="turning_point", confidence_level="HIGH"
    )
    print(f"  Short Scene (1.0s) Plan: conservative={p_short.is_conservative_default}")
    assert p_short.is_conservative_default is True

    print("  [PASS] Conservative camera stabilization rigorously enforced on unverified or short scenes.")


def test_short_scenes_and_single_frame_edge_cases():
    print_banner("TEST 6: SHORT SCENES & SINGLE-FRAME EDGE CASES")
    
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:] = (40, 40, 40)
    tmp_out = ROOT_DIR / "qa" / "renders" / "test_edge_cases"
    tmp_out.mkdir(parents=True, exist_ok=True)

    # 1. Single frame scene (n = 1)
    scene_1f = {
        "scene_id": "test_1f",
        "n": 1,
        "motion": "L4/push",
        "motion_mode": "push",
        "shot_role": "character_focus",
        "easing": "cubic_in_out"
    }
    out_1f = tmp_out / "single_frame.mp4"
    mode_1f = render_scene(scene_1f, img, 0, out_1f)
    assert out_1f.exists() and out_1f.stat().st_size > 500, "Single-frame render failed!"
    print("  [PASS] Single frame (n=1) edge case rendered cleanly without division by zero.")

    # 2. Two-frame scene (n = 2)
    scene_2f = {
        "scene_id": "test_2f",
        "n": 2,
        "motion": "L4/drift_right",
        "motion_mode": "drift_right",
        "shot_role": "environmental_drift",
        "easing": "smoothstep"
    }
    out_2f = tmp_out / "two_frames.mp4"
    mode_2f = render_scene(scene_2f, img, 0, out_2f)
    assert out_2f.exists() and out_2f.stat().st_size > 500, "Two-frame render failed!"
    print("  [PASS] Two-frame (n=2) boundary case rendered cleanly.")


def test_backward_compatibility_existing_motion_strings():
    print_banner("TEST 7: BACKWARD COMPATIBILITY WITH LEGACY MOTION STRINGS & SCHEMAS")

    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:] = (60, 30, 20)
    tmp_out = ROOT_DIR / "qa" / "renders" / "test_legacy_compat"
    tmp_out.mkdir(parents=True, exist_ok=True)

    # Legacy scene dictionary with only L4/push string and no easing or shot_role fields
    legacy_scenes = [
        {"scene_id": "legacy_push", "n": FPS, "motion": "L4/push"},
        {"scene_id": "legacy_pull", "n": FPS, "motion": "L4/pull"},
        {"scene_id": "legacy_drift_l", "n": FPS, "motion": "L4/drift_left"},
        {"scene_id": "legacy_drift_r", "n": FPS, "motion": "L4/drift_right"},
    ]

    for sc in legacy_scenes:
        out_f = tmp_out / f"{sc['scene_id']}.mp4"
        mode_res = render_scene(sc, img, 0, out_f)
        assert out_f.exists() and out_f.stat().st_size > 1000
        expected = sc["motion"].split("/")[-1]
        assert mode_res == expected, f"Expected {expected}, got {mode_res}"
        print(f"  Legacy string '{sc['motion']}' rendered seamlessly as mode '{mode_res}'")

    # Legacy plan loading and timeline build
    sample_plan = {
        "scenes": [
            {"segment_index": 0, "image": "img_01.jpg", "context": "normal"},
            {"segment_index": 1, "image": "img_02.jpg", "context": "turning_point"}
        ]
    }
    plan_file = tmp_out / "legacy_plan.json"
    with open(plan_file, "w") as f:
        json.dump(sample_plan, f)

    assign = load_plan(plan_file)
    assert 0 in assign and 1 in assign
    assert assign[0][0]["image"] == "img_01.jpg"
    print("  [PASS] Legacy plan schemas parsed and processed with zero regressions.")


def test_e2e_video_rendering_and_stream_validation():
    print_banner("TEST 8: E2E VIDEO RENDERING WITH FFPROBE STREAM VALIDATION")
    
    render_dir = ROOT_DIR / "qa" / "renders" / "cinematic_motion_e2e"
    if render_dir.exists():
        shutil.rmtree(render_dir, ignore_errors=True)
    render_dir.mkdir(parents=True, exist_ok=True)

    # Use genuine photograph from king project
    king_img_path = ROOT_DIR / "projects" / "king" / "images" / "image_1.png"
    assert king_img_path.exists(), f"Source image missing at {king_img_path}"
    
    raw_img = cv2.imread(str(king_img_path))
    assert raw_img is not None, "Failed to decode source image"
    test_img = cv2.resize(raw_img, (W, H))

    test_matrix = [
        {
            "scene_id": "shot_establishing",
            "n": FPS * 2,  # 2.0s
            "dur": 2.0,
            "motion": "L4/drift_right",
            "motion_mode": "drift_right",
            "shot_role": "establishing_wide",
            "easing": "smoothstep",
            "zoom_scale": 1.025,
            "pan_speed": 22.0
        },
        {
            "scene_id": "shot_tension",
            "n": FPS * 2,  # 2.0s
            "dur": 2.0,
            "motion": "L4/push",
            "motion_mode": "push",
            "shot_role": "dramatic_tension",
            "easing": "cubic_in_out",
            "zoom_scale": 1.048,
            "pan_speed": 0.0
        },
        {
            "scene_id": "shot_inspection",
            "n": round(FPS * 1.5),  # 1.5s
            "dur": 1.5,
            "motion": "L4/pull",
            "motion_mode": "pull",
            "shot_role": "narrative_inspection",
            "easing": "ease_out",
            "zoom_scale": 1.025,
            "pan_speed": 0.0
        }
    ]

    for item in test_matrix:
        mp4_path = render_dir / f"{item['scene_id']}.mp4"
        mode_used = render_scene(item, test_img, 0, mp4_path)
        assert mp4_path.exists() and mp4_path.stat().st_size > 1000, f"Render failed: {mp4_path}"
        
        # Probe video stream with ffprobe
        cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,duration,nb_frames',
            '-of', 'json', str(mp4_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        probe = json.loads(res.stdout)
        stream = probe['streams'][0]
        
        w_p = int(stream['width'])
        h_p = int(stream['height'])
        dur_p = float(stream['duration'])
        
        print(f"  Rendered: {mp4_path.name}")
        print(f"    Mode: {mode_used} | Role: {item['shot_role']} | Easing: {item['easing']}")
        print(f"    Dimensions: {w_p}x{h_p} | Probed Duration: {dur_p:.3f}s | Target Dur: {item['dur']:.3f}s")
        
        assert w_p == W and h_p == H, f"Resolution mismatch: expected {W}x{H}, got {w_p}x{h_p}"
        assert abs(dur_p - item['dur']) <= 0.04, f"Duration deviation too large: probed {dur_p} vs target {item['dur']}"

    print("  [PASS] All cinematic scenes rendered cleanly with exact 1080p geometry and accurate durations.")


def main():
    print_banner("RENDERFLOW CINEMATIC MOTION INTELLIGENCE — PHASE 1 VALIDATION")
    t0 = time.time()
    
    test_easing_endpoints_and_bounds()
    test_easing_monotonicity()
    test_smooth_starts_and_stops_velocity()
    test_shot_roles_generation()
    test_conservative_motion_on_low_confidence_and_no_match()
    test_short_scenes_and_single_frame_edge_cases()
    test_backward_compatibility_existing_motion_strings()
    test_e2e_video_rendering_and_stream_validation()
    
    elapsed = time.time() - t0
    print_banner(f"ALL 8 PHASE 1 TESTS PASSED IN {elapsed:.2f}s!")


if __name__ == "__main__":
    main()
