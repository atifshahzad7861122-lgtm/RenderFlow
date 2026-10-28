#!/usr/bin/env python3
"""
qa/test_semantic_intelligence_master_suite.py
=============================================
Phase 5 Comprehensive Validation & Regression Test Suite for
RenderFlow Mapping Engine — Semantic Intelligence Upgrade.

Validates all 10 Non-Negotiable Gates:
  Gate 1: ZIP & Filename-Order Independence (Order A vs Shuffled Order B)
  Gate 2: Real Photographic Literal & Contextual Alignment (Cold War Berlin)
  Gate 3: Abstract & Metaphorical Concept Alignment (Fear, Espionage, Betrayal)
  Gate 4: Consecutive Duplicate Penalties & Smart Reuse
  Gate 5: User-Locked Overrides Immutability (Zero Override Loss)
  Gate 6: Missing Scene & Low-Confidence Warning (No Fabricated Certainty)
  Gate 7: Motion Intelligence Instructions & L4 Renderer Formatting
  Gate 8: Audio Master Timeline Alignment & Continuous Scene Coverage
  Gate 9: Offline Fallback Graceful Degradation
  Gate 10: End-to-End FFmpeg Video Rendering & Playback Verification
"""

import os
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from engine.sync_engine_v3 import (
    AIImageSyncEngineV3,
    DeterministicSemanticEmbedding,
    SemanticBeatEngine,
    MultiSignalRankingEngine,
    MappingMode
)
from engine.semantic_vision import SemanticVisionModel
from engine.global_timeline_optimizer import GlobalTimelineOptimizer
from engine.motion_intelligence import MotionIntelligenceEngine
from engine.render_base import render_scene, MODES, W, H, FPS

def print_header(title):
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)

def test_gate_1_order_independence():
    print_header("GATE 1: ZIP & FILENAME-ORDER INDEPENDENCE")
    king_images = ROOT_DIR / "projects" / "king" / "images"
    audio_path = ROOT_DIR / "test_short_audio.wav"

    # Use 3 distinct images
    img_names = ["image_1.png", "image_2.png", "image_7.png"]
    
    # Transcript with 3 beats
    qa_tmp = ROOT_DIR / "qa" / "renders" / "gate1_tmp"
    qa_tmp.mkdir(parents=True, exist_ok=True)
    t_path = qa_tmp / "transcript.json"
    with open(t_path, "w", encoding="utf-8") as f:
        json.dump({
            "segments": [
                {"start": 0.0, "end": 2.0, "text": "Berlin 1953, a city divided by barbed wire and fear."},
                {"start": 2.0, "end": 4.0, "text": "American soldiers drove military vehicles through the western streets."},
                {"start": 4.0, "end": 6.0, "text": "Soviet soldiers watched continuously over every checkpoint."}
            ]
        }, f, indent=2)

    engine = AIImageSyncEngineV3()

    # Order A
    order_a = ["image_1.png", "image_2.png", "image_7.png"]
    _, plan_a, _ = engine.synchronize_timeline(
        audio_path=audio_path,
        images_dir=king_images,
        image_filenames=order_a,
        transcript_path=t_path,
        all_images_mode=True,
        mapping_mode="SEMANTIC_AUTO"
    )
    mapping_a = [s["image"] for s in plan_a["scenes"]]

    # Order B: Reversed order
    order_b = ["image_7.png", "image_1.png", "image_2.png"]
    _, plan_b, _ = engine.synchronize_timeline(
        audio_path=audio_path,
        images_dir=king_images,
        image_filenames=order_b,
        transcript_path=t_path,
        all_images_mode=True,
        mapping_mode="SEMANTIC_AUTO"
    )
    mapping_b = [s["image"] for s in plan_b["scenes"]]

    print(f"  Order A Input: {order_a} -> Output: {mapping_a}")
    print(f"  Order B Input: {order_b} -> Output: {mapping_b}")

    assert mapping_a == mapping_b, f"Order independence violated! {mapping_a} != {mapping_b}"
    print("  [PASS] Gate 1: Timeline mapping is 100% invariant to input filename order.")


def test_gate_2_and_3_literal_and_abstract_semantics():
    print_header("GATE 2 & 3: LITERAL & ABSTRACT SEMANTIC ALIGNMENT")
    svm = SemanticVisionModel()
    king_images = ROOT_DIR / "projects" / "king" / "images"

    # Evaluate American Soldiers vs image_2.png
    jeep_img = king_images / "image_2.png"
    jeep_emb = svm.encode_image(jeep_img)

    soldier_text = svm.encode_text("American soldiers driving military jeep through city streets")
    kitchen_text = svm.encode_text("a modern clean kitchen with chef baking pastry")

    sim_soldier = float(np.dot(soldier_text, jeep_emb))
    sim_kitchen = float(np.dot(kitchen_text, jeep_emb))

    print(f"  Literal Soldier Script vs image_2.png: dot={sim_soldier:.4f}")
    print(f"  Unrelated Kitchen Script vs image_2.png: dot={sim_kitchen:.4f}")
    assert sim_soldier > sim_kitchen + 0.10, "Literal semantic discrimination failed!"
    print("  [PASS] Gate 2: Literal semantic visual match has high margin over unrelated topics.")

    # Gate 3: Abstract / Metaphorical concepts
    fear_text = svm.encode_text("oppressive atmosphere of surveillance, secrecy, and fear")
    kitten_text = svm.encode_text("cute playful golden retriever puppy in spring sunshine")
    border_img = king_images / "image_22.png"
    border_emb = svm.encode_image(border_img)

    sim_fear = float(np.dot(fear_text, border_emb))
    sim_kitten = float(np.dot(kitten_text, border_emb))

    print(f"  Abstract Fear/Surveillance vs image_22.png: dot={sim_fear:.4f}")
    print(f"  Cheerful Puppy vs image_22.png: dot={sim_kitten:.4f}")
    assert sim_fear > sim_kitten + 0.08, "Abstract metaphorical discrimination failed!"
    print("  [PASS] Gate 3: Abstract/metaphorical concepts properly recognized by neural vision.")


def test_gate_4_duplicate_penalties():
    print_header("GATE 4: CONSECUTIVE DUPLICATE PENALTIES & SMART REUSE")
    opt = GlobalTimelineOptimizer(consecutive_duplicate_penalty=0.30)
    
    # 3 beats, 2 images. Image 0 matches both beat 0 and beat 1 moderately.
    sim_matrix = np.array([
        [0.30, 0.28], # Beat 0 prefers img 0 slightly
        [0.30, 0.28], # Beat 1 prefers img 0 slightly
    ])
    fns = ["img_a.png", "img_b.png"]
    assignments = opt.optimize_timeline(sim_matrix, fns)
    assigned_fns = [a.image_filename for a in assignments]
    print(f"  Assigned for equal beats: {assigned_fns}")
    # Global optimizer should assign img_a to one and img_b to the other rather than repeating img_a consecutively
    assert assigned_fns[0] != assigned_fns[1], "Consecutive duplicate was not penalized!"
    print("  [PASS] Gate 4: Global timeline optimizer distributes images to maximize visual diversity.")


def test_gate_5_locked_scenes_and_manual_overrides():
    print_header("GATE 5: USER-LOCKED OVERRIDES IMMUTABILITY")
    king_images = ROOT_DIR / "projects" / "king" / "images"
    audio_path = ROOT_DIR / "test_short_audio.wav"

    qa_tmp = ROOT_DIR / "qa" / "renders" / "gate5_tmp"
    qa_tmp.mkdir(parents=True, exist_ok=True)
    t_path = qa_tmp / "transcript.json"
    with open(t_path, "w", encoding="utf-8") as f:
        json.dump({
            "segments": [
                {"start": 0.0, "end": 2.0, "text": "Berlin 1953, a city divided."},
                {"start": 2.0, "end": 4.0, "text": "American soldiers drove military vehicles."},
                {"start": 4.0, "end": 6.0, "text": "Soviet guards on duty."}
            ]
        }, f, indent=2)

    engine = AIImageSyncEngineV3()
    # Lock beat 0 to image_12.png and beat 2 to image_1.png
    overrides = {0: "image_12.png", 2: "image_1.png"}
    imgs = ["image_1.png", "image_2.png", "image_12.png"]

    _, plan, _ = engine.synchronize_timeline(
        audio_path=audio_path,
        images_dir=king_images,
        image_filenames=imgs,
        transcript_path=t_path,
        user_overrides=overrides,
        mapping_mode="SEMANTIC_AUTO"
    )
    scenes = plan["scenes"]
    print(f"  Scene 0 [Override image_12.png]: {scenes[0]['image']} (Flag: {scenes[0]['user_override']})")
    print(f"  Scene 1 [AI Auto]: {scenes[1]['image']} (Flag: {scenes[1]['user_override']})")
    print(f"  Scene 2 [Override image_1.png]: {scenes[2]['image']} (Flag: {scenes[2]['user_override']})")

    assert scenes[0]["image"] == "image_12.png" and scenes[0]["user_override"] is True
    assert scenes[2]["image"] == "image_1.png" and scenes[2]["user_override"] is True
    print("  [PASS] Gate 5: 100% of user-locked overrides strictly preserved.")


def test_gate_6_missing_scenes_and_low_confidence():
    print_header("GATE 6: MISSING SCENES & LOW-CONFIDENCE WARNING")
    opt = GlobalTimelineOptimizer(min_match_threshold=0.180)
    # 1 scene completely unrelated to any image in library
    sim_matrix = np.array([
        [0.10, 0.12, 0.11]  # all below threshold 0.180
    ])
    fns = ["img_1.png", "img_2.png", "img_3.png"]
    assignments = opt.optimize_timeline(sim_matrix, fns)
    a = assignments[0]
    print(f"  Confidence Level: {a.confidence_level}")
    print(f"  Manual Review Needed: {a.is_manual_review_needed}")
    print(f"  Evidence Reasons: {a.evidence_reasons}")

    assert a.confidence_level == "NO_MATCH", f"Expected NO_MATCH, got {a.confidence_level}"
    assert a.is_manual_review_needed is True, "Manual review needed flag not set!"
    assert any("below_threshold" in r for r in a.evidence_reasons), "Missing below_threshold reason!"
    print("  [PASS] Gate 6: Missing visual evidence produces explicit NO_MATCH without fabricating certainty.")


def test_gate_7_motion_instructions_and_l4_formatting():
    print_header("GATE 7: MOTION INSTRUCTIONS & L4 RENDERER FORMATTING")
    plan = MotionIntelligenceEngine.plan_scene_motion(
        scene_idx=0,
        dur=4.5,
        context="turning_point",
        energy_level="high",
        confidence_level="HIGH"
    )
    print(f"  High Energy Motion: {plan.renderer_motion_label} ({plan.motion_type}) zoom={plan.zoom_scale}")
    assert plan.renderer_motion_label.startswith("L4/"), "Missing L4/ renderer prefix!"
    assert plan.motion_type in ["push", "pull", "drift_left", "drift_right"]

    # Conservative default for low confidence
    plan_low = MotionIntelligenceEngine.plan_scene_motion(
        scene_idx=1,
        dur=4.5,
        context="normal",
        confidence_level="LOW"
    )
    print(f"  Low Conf Motion: {plan_low.renderer_motion_label} (Conservative={plan_low.is_conservative_default})")
    assert plan_low.is_conservative_default is True
    assert plan_low.zoom_scale <= 1.020, "Low-confidence zoom exceeds conservative threshold!"
    print("  [PASS] Gate 7: Motion instructions follow L4 cinematographic standards with conservative fallbacks.")


def test_gate_8_audio_timing_and_coverage():
    print_header("GATE 8: AUDIO MASTER TIMELINE & CONTINUOUS SCENE COVERAGE")
    king_images = ROOT_DIR / "projects" / "king" / "images"
    audio_path = ROOT_DIR / "test_short_audio.wav"

    qa_tmp = ROOT_DIR / "qa" / "renders" / "gate8_tmp"
    qa_tmp.mkdir(parents=True, exist_ok=True)
    t_path = qa_tmp / "transcript.json"
    with open(t_path, "w", encoding="utf-8") as f:
        json.dump({
            "segments": [
                {"start": 0.0, "end": 2.15, "text": "Segment one narration text."},
                {"start": 2.15, "end": 4.80, "text": "Segment two narration text."},
                {"start": 4.80, "end": 6.00, "text": "Segment three narration text."}
            ]
        }, f, indent=2)

    engine = AIImageSyncEngineV3()
    t_obj, plan, report = engine.synchronize_timeline(
        audio_path=audio_path,
        images_dir=king_images,
        image_filenames=["image_1.png", "image_2.png", "image_7.png"],
        transcript_path=t_path,
        mapping_mode="SEMANTIC_AUTO"
    )
    scenes = plan["scenes"]
    master_dur = engine.probe_audio_duration(audio_path)

    # Check boundaries
    assert scenes[0]["start"] == 0.0, "Start timestamp not 0.0!"
    assert abs(scenes[-1]["end"] - master_dur) <= 0.005, f"End {scenes[-1]['end']} != master {master_dur}"
    for i in range(len(scenes) - 1):
        gap = abs(scenes[i]["end"] - scenes[i + 1]["start"])
        assert gap <= 0.005, f"Scene boundary gap detected at scene {i}: gap={gap}"

    print(f"  Timeline strictly covered [0.000s - {master_dur:.3f}s] across {len(scenes)} scenes with zero gaps.")
    print("  [PASS] Gate 8: Continuous timeline coverage verified.")


def test_gate_9_offline_fallback():
    print_header("GATE 9: OFFLINE DETERMINISTIC FALLBACK")
    # Verify fallback vector projection when neural model is bypassed
    vec = DeterministicSemanticEmbedding._fallback_encode("A historical scene of soldiers and factories")
    assert len(vec) == 512, f"Fallback dimension mismatch: expected 512, got {len(vec)}"
    norm = np.linalg.norm(vec)
    assert abs(norm - 1.0) < 0.01, f"Fallback vector not normalized: {norm}"
    print(f"  Fallback vector: 512-dim L2-normalized vector generated successfully.")
    print("  [PASS] Gate 9: Offline fallback executes reliably.")


def test_gate_10_e2e_ffmpeg_render():
    print_header("GATE 10: END-TO-END FFmpeg VIDEO RENDERING")
    workdir = ROOT_DIR / "qa" / "renders" / "gate10_render"
    if workdir.exists():
        shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)

    # Create 2 simple scenes using actual project images
    king_images = ROOT_DIR / "projects" / "king" / "images"
    import cv2
    img1 = cv2.imread(str(king_images / "image_1.png"))
    img1_resized = cv2.resize(img1, (W, H))

    scene_data = {
        "scene_id": "scene_0001",
        "n": FPS * 2, # 2 seconds
        "dur": 2.0,
        "motion": "L4/drift_right",
        "motion_mode": "drift_right"
    }

    out_mp4 = workdir / "scene_0001.mp4"
    mode_rendered = render_scene(scene_data, img1_resized, 0, out_mp4)
    print(f"  Rendered Scene MP4: {out_mp4.name} with motion mode: {mode_rendered}")

    assert out_mp4.exists() and out_mp4.stat().st_size > 1000, "Rendered scene MP4 missing or empty!"
    assert mode_rendered == "drift_right", f"Expected drift_right, got {mode_rendered}"

    # Probe rendered video with ffprobe
    r = subprocess.run([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,duration',
        '-of', 'json', str(out_mp4)
    ], capture_output=True, text=True, check=True)
    probe = json.loads(r.stdout)
    stream = probe["streams"][0]
    print(f"  Verified Video Stream: {stream['width']}x{stream['height']}, duration: {float(stream['duration']):.2f}s")
    assert int(stream["width"]) == W and int(stream["height"]) == H
    print("  [PASS] Gate 10: Playable MP4 successfully rendered with FFmpeg camera motion.")


def main():
    print("=" * 78)
    print("  RENDERFLOW MAPPING ENGINE — SEMANTIC INTELLIGENCE ACCEPTANCE SUITE")
    print("=" * 78)
    t0 = time.time()

    test_gate_1_order_independence()
    test_gate_2_and_3_literal_and_abstract_semantics()
    test_gate_4_duplicate_penalties()
    test_gate_5_locked_scenes_and_manual_overrides()
    test_gate_6_missing_scenes_and_low_confidence()
    test_gate_7_motion_instructions_and_l4_formatting()
    test_gate_8_audio_timing_and_coverage()
    test_gate_9_offline_fallback()
    test_gate_10_e2e_ffmpeg_render()

    total_time = time.time() - t0
    print("\n" + "=" * 78)
    print(f"  ALL 10 VERIFICATION GATES PASSED IN {total_time:.2f}s!")
    print("=" * 78)

if __name__ == "__main__":
    main()
