#!/usr/bin/env python3
"""
engine/test_timeline_continuity.py — Comprehensive Timeline Continuity & Normalization Test Suite.

Verifies the 10 mandatory regression scenarios from Master Prompt §13:
  Test 1  — Perfect continuity (100 scenes, zero gaps)
  Test 2  — Floating-point drift (tiny delta < 5ms) -> PASS
  Test 3  — Real silence (genuine 1.2s pause preserved and held)
  Test 4  — Artificial gap (Scene 1 ends at 5.0s, Scene 2 starts at 6.0s) -> detected and normalized
  Test 5  — Overlap (Scene 1 ends at 5.0s, Scene 2 starts at 4.8s) -> detected and resolved
  Test 6  — Long narration (30+ minutes audio, fast bounded processing)
  Test 7  — 100+ scenes (zero unexplained gaps)
  Test 8  — Image shortage (fewer images than beats -> reuse without gaps)
  Test 9  — Excess images (more images than beats -> subdivision without gaps)
  Test 10 — Transitions (transitions are visual effects, zero timeline gaps)
"""

import sys
import time
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Add project root to sys.path
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.timeline_normalizer import TimelineNormalizer


def test_1_perfect_continuity():
    """Test 1 — Perfect continuity: 100 scenes with zero gaps."""
    print("[TEST 1] Perfect continuity (100 scenes, zero gaps)...")
    master_dur = 300.0
    scenes = []
    step = master_dur / 100.0
    t = 0.0
    for i in range(100):
        t_next = master_dur if i == 99 else round(t + step, 3)
        scenes.append({
            'scene_id': f'scene_{i+1:04d}',
            'image': f'img_{i+1:03d}.jpg',
            'start': round(t, 3),
            'end': t_next,
            'dur': round(t_next - t, 3)
        })
        t = t_next

    is_valid, errs, metrics = TimelineNormalizer.validate_timeline(scenes, master_dur, tolerance=0.005)
    assert is_valid, f"Test 1 failed: {errs}"
    assert len(scenes) == 100
    print("  -> PASS: 100 scenes verified with 0 gaps.")


def test_2_floating_point_drift():
    """Test 2 — Floating-point drift: Tiny timestamp differences under 5ms must pass."""
    print("[TEST 2] Floating-point drift (tiny delta < 5ms)...")
    master_dur = 10.0
    scenes = [
        {'scene_id': 's1', 'start': 0.000, 'end': 3.000002, 'dur': 3.000},
        {'scene_id': 's2', 'start': 3.000002, 'end': 6.000001, 'dur': 3.000},
        {'scene_id': 's3', 'start': 6.000001, 'end': 10.000, 'dur': 4.000},
    ]
    is_valid, errs, metrics = TimelineNormalizer.validate_timeline(scenes, master_dur, tolerance=0.005)
    assert is_valid, f"Test 2 failed: {errs}"
    print("  -> PASS: Sub-5ms drift accepted without false error.")


def test_3_real_silence():
    """Test 3 — Real silence: Audio contains 1.2s pause. Pause is preserved and held."""
    print("[TEST 3] Real silence (1.2s pause preserved and held)...")
    master_dur = 15.0
    # Spoken: [0.5, 4.0], pause: [4.0, 5.2] (1.2s), spoken: [5.2, 10.0], pause: [10.0, 15.0]
    raw_segments = [
        {'start': 0.5, 'end': 4.0, 'text': "First speech phrase."},
        {'start': 5.2, 'end': 10.0, 'text': "Second speech phrase after pause."}
    ]

    continuous = TimelineNormalizer.normalize_speech_segments(
        raw_segments=raw_segments,
        master_dur=master_dur,
        hold_mode='extend_hold'
    )

    is_valid, errs, metrics = TimelineNormalizer.validate_timeline(continuous, master_dur, tolerance=0.005)
    assert is_valid, f"Test 3 failed: {errs}"
    assert continuous[0]['start'] == 0.0, "First segment must start at 0.0s (absorb lead-in pause)"
    assert continuous[0]['end'] == continuous[1]['start'], "Scene 1 end must match Scene 2 start"
    assert continuous[-1]['end'] == master_dur, "Last scene must extend to master audio end"
    print(f"  -> PASS: 1.2s pause held seamlessly. Total coverage: {continuous[-1]['end']}s == {master_dur}s.")


def test_4_artificial_gap():
    """Test 4 — Artificial gap: Scene 1 ends at 5.0s, Scene 2 starts at 6.0s."""
    print("[TEST 4] Artificial gap detection and normalization...")
    master_dur = 10.0
    bad_scenes = [
        {'scene_id': 's1', 'start': 0.0, 'end': 5.0, 'dur': 5.0},
        {'scene_id': 's2', 'start': 6.0, 'end': 10.0, 'dur': 4.0}
    ]
    # Validation must detect the 1.0s gap
    is_valid, errs, metrics = TimelineNormalizer.validate_timeline(bad_scenes, master_dur, tolerance=0.005)
    assert not is_valid, "Validator should have rejected 1.0s gap"
    assert any("gap of 1.000s" in e for e in errs), f"Expected gap error, got {errs}"

    # Normalization must close the gap cleanly
    fixed = TimelineNormalizer.normalize_speech_segments(bad_scenes, master_dur)
    is_valid_fixed, errs_fixed, _ = TimelineNormalizer.validate_timeline(fixed, master_dur, tolerance=0.005)
    assert is_valid_fixed, f"Normalization failed to close artificial gap: {errs_fixed}"
    print("  -> PASS: Artificial gap detected by validator and normalized successfully.")


def test_5_overlap():
    """Test 5 — Overlap: Scene 1 ends at 5.0s, Scene 2 starts at 4.8s."""
    print("[TEST 5] Overlap detection and deterministic resolution...")
    master_dur = 10.0
    bad_scenes = [
        {'scene_id': 's1', 'start': 0.0, 'end': 5.0, 'dur': 5.0},
        {'scene_id': 's2', 'start': 4.8, 'end': 10.0, 'dur': 5.2}
    ]
    # Validator must reject the 0.2s overlap
    is_valid, errs, metrics = TimelineNormalizer.validate_timeline(bad_scenes, master_dur, tolerance=0.005)
    assert not is_valid, "Validator should have rejected overlap"
    assert any("[OVERLAP]" in e for e in errs), f"Expected overlap error, got {errs}"

    # Normalization must resolve overlap cleanly
    fixed = TimelineNormalizer.normalize_speech_segments(bad_scenes, master_dur)
    is_valid_fixed, errs_fixed, _ = TimelineNormalizer.validate_timeline(fixed, master_dur, tolerance=0.005)
    assert is_valid_fixed, f"Normalization failed to resolve overlap: {errs_fixed}"
    print("  -> PASS: Overlap detected by validator and resolved cleanly.")


def test_6_long_narration():
    """Test 6 — Long narration: 30+ minute audio (1800s, 600 scenes) bounded processing."""
    print("[TEST 6] Long narration scalability (30+ minutes, 1800s, 600 segments)...")
    master_dur = 1800.0  # 30 minutes
    n_segs = 600

    t0 = time.time()
    raw = []
    t = 0.5
    for i in range(n_segs):
        dur = 2.5
        raw.append({'start': t, 'end': t + dur, 'text': f"Phrase {i+1}"})
        t += dur + 0.4  # 0.4s pauses between phrases

    t_prep = time.time() - t0
    t1 = time.time()
    continuous = TimelineNormalizer.normalize_speech_segments(raw, master_dur)
    t_norm = time.time() - t1

    is_valid, errs, metrics = TimelineNormalizer.validate_timeline(continuous, master_dur, tolerance=0.005)
    assert is_valid, f"Test 6 failed: {errs}"
    assert t_norm < 0.05, f"Normalization took too long: {t_norm:.3f}s"
    print(f"  -> PASS: 30-min narration (600 segments) normalized in {t_norm*1000:.2f}ms with 0 gaps.")


def test_7_100_plus_scenes():
    """Test 7 — 100+ scenes: Zero unexplained gaps across 120 scenes."""
    print("[TEST 7] 100+ scenes continuity verification...")
    master_dur = 250.0
    raw = []
    t = 0.0
    for i in range(120):
        t_next = round(t + 2.083, 3)
        raw.append({'start': t, 'end': t_next, 'text': f"Scene {i+1}"})
        t = t_next

    continuous = TimelineNormalizer.normalize_speech_segments(raw, master_dur)
    is_valid, errs, metrics = TimelineNormalizer.validate_timeline(continuous, master_dur, tolerance=0.005)
    assert is_valid, f"Test 7 failed: {errs}"
    print("  -> PASS: 120 scenes verified with 0 gaps.")


def test_8_image_shortage():
    """Test 8 — Image shortage: Fewer images than beats (e.g. 5 images for 20 beats)."""
    print("[TEST 8] Image shortage (5 images for 20 beats)...")
    master_dur = 60.0
    raw = [{'start': i * 3.0, 'end': (i + 1) * 3.0, 'text': f"Seg {i}"} for i in range(20)]
    continuous = TimelineNormalizer.normalize_speech_segments(raw, master_dur)

    # 5 images reused across 20 beats
    images = [f"img_{k+1}.jpg" for k in range(5)]
    scenes = []
    for idx, beat in enumerate(continuous):
        assigned_img = images[idx % len(images)]
        scenes.append({
            'scene_id': f'sc_{idx+1}',
            'image': assigned_img,
            'start': beat['start'],
            'end': beat['end'],
            'dur': beat['dur']
        })

    is_valid, errs, metrics = TimelineNormalizer.validate_timeline(scenes, master_dur, tolerance=0.005)
    assert is_valid, f"Test 8 failed: {errs}"
    assert len({s['image'] for s in scenes}) == 5
    print("  -> PASS: Image shortage handled via reuse with zero timeline gaps.")


def test_9_excess_images():
    """Test 9 — Excess images: More images than beats (e.g. 50 images for 10 speech segments)."""
    print("[TEST 9] Excess images (50 images for 10 speech segments)...")
    master_dur = 100.0
    raw = [{'start': i * 10.0 + 0.5, 'end': (i + 1) * 10.0 - 0.5, 'text': f"Speech {i}"} for i in range(10)]
    continuous = TimelineNormalizer.normalize_speech_segments(raw, master_dur)

    # Subdivide into 50 visual beats
    beats = TimelineNormalizer.partition_into_visual_beats(continuous, target_beats=50, master_dur=master_dur)
    assert len(beats) == 50, f"Expected 50 beats, got {len(beats)}"

    is_valid, errs, metrics = TimelineNormalizer.validate_timeline(beats, master_dur, tolerance=0.005)
    assert is_valid, f"Test 9 failed: {errs}"
    print(f"  -> PASS: 10 speech segments subdivided into 50 contiguous beats with 0 gaps.")


def test_10_transitions():
    """Test 10 — Transitions: Transitions must not create unexplained timeline gaps."""
    print("[TEST 10] Transitions continuity verification...")
    master_dur = 20.0
    scenes = [
        {'scene_id': 's1', 'start': 0.0, 'end': 5.0, 'dur': 5.0, 'transition': 'cinematic_dissolve'},
        {'scene_id': 's2', 'start': 5.0, 'end': 11.0, 'dur': 6.0, 'transition': 'clean_cut'},
        {'scene_id': 's3', 'start': 11.0, 'end': 16.0, 'dur': 5.0, 'transition': 'dip_to_black'},
        {'scene_id': 's4', 'start': 16.0, 'end': 20.0, 'dur': 4.0, 'transition': 'soft_wipe'}
    ]

    is_valid, errs, metrics = TimelineNormalizer.validate_timeline(scenes, master_dur, tolerance=0.005)
    assert is_valid, f"Test 10 failed: {errs}"

    # Verify that transition offsets do not create temporal gaps in scene timeline
    for i in range(len(scenes) - 1):
        assert scenes[i]['end'] == scenes[i + 1]['start'], f"Discontinuity at scene {i}"
    print("  -> PASS: Transitions operate as visual blends without timeline gaps.")


def test_11_transition_timeline_validation():
    """Test 11 — Transitions timeline validator checks cut times, durations, and bounds."""
    print("[TEST 11] Detailed transitions timeline validator...")
    master_dur = 20.0
    scenes = [
        {'scene_id': 's1', 'start': 0.0, 'end': 5.0, 'dur': 5.0},
        {'scene_id': 's2', 'start': 5.0, 'end': 11.0, 'dur': 6.0},
        {'scene_id': 's3', 'start': 11.0, 'end': 16.0, 'dur': 5.0},
        {'scene_id': 's4', 'start': 16.0, 'end': 20.0, 'dur': 4.0}
    ]
    # Valid transitions at cut points 5.0, 11.0, 16.0
    valid_transitions = [
        {'cut_index': 0, 'cut_time': 5.0, 'dur': 0.40, 'start_s': 4.80, 'end_s': 5.20},
        {'cut_index': 1, 'cut_time': 11.0, 'dur': 0.35, 'start_s': 10.825, 'end_s': 11.175},
        {'cut_index': 2, 'cut_time': 16.0, 'dur': 0.45, 'start_s': 15.775, 'end_s': 16.225}
    ]
    is_valid, errs, metrics = TimelineNormalizer.validate_transitions_timeline(scenes, valid_transitions, master_dur)
    assert is_valid, f"Expected valid transitions to pass: {errs}"

    # Invalid transition: cut_time mismatch
    invalid_transitions = [
        {'cut_index': 0, 'cut_time': 6.5, 'dur': 0.40, 'start_s': 6.30, 'end_s': 6.70}
    ]
    is_valid, errs, _ = TimelineNormalizer.validate_transitions_timeline(scenes, invalid_transitions, master_dur)
    assert not is_valid, "Expected mismatched cut_time to fail"
    assert any("does not match" in e for e in errs)
    print("  -> PASS: Valid transitions verified and cut mismatches detected.")


def test_12_audio_master_alignment():
    """Test 12 — Video starts at 0.0, ends at master_dur, and frame budget matches master audio."""
    print("[TEST 12] Audio master alignment and frame budget validation...")
    master_dur = 47.653
    fps = 30
    total_frames = round(master_dur * fps)

    raw_segments = [
        {'start': 0.4, 'end': 8.2, 'text': "Intro section"},
        {'start': 9.5, 'end': 24.1, 'text': "Main technical discussion"},
        {'start': 26.0, 'end': 46.8, 'text': "Closing thoughts and summary"}
    ]
    continuous = TimelineNormalizer.normalize_speech_segments(raw_segments, master_dur)

    # 1. Start boundary check
    assert continuous[0]['start'] == 0.0, f"Expected 0.0, got {continuous[0]['start']}"
    # 2. End boundary check
    assert abs(continuous[-1]['end'] - master_dur) < 0.005, f"Expected {master_dur}, got {continuous[-1]['end']}"
    # 3. Sum of durations equals master duration
    sum_dur = sum(s['dur'] for s in continuous)
    assert abs(sum_dur - master_dur) < 0.005, f"Sum of durations {sum_dur} != master {master_dur}"

    # 4. Partition into 15 scenes
    beats = TimelineNormalizer.partition_into_visual_beats(continuous, target_beats=15, master_dur=master_dur)
    is_valid, errs, metrics = TimelineNormalizer.validate_timeline(beats, master_dur)
    assert is_valid, f"Partition failed timeline validation: {errs}"

    # 5. Frame count budget check
    f_total = 0
    for b in beats:
        n_frames = round(b['dur'] * fps)
        f_total += n_frames
    # Discrepancy before budget absorption should be at most a few frames
    assert abs(f_total - total_frames) <= 3
    print(f"  -> PASS: Master timeline strictly covers [0.0s -> {master_dur}s] across 15 scenes.")


def run_all_continuity_tests():
    print("\n" + "=" * 65)
    print(" RENDERING STUDIO — TIMELINE CONTINUITY REGRESSION SUITE")
    print("=" * 65 + "\n")

    test_1_perfect_continuity()
    test_2_floating_point_drift()
    test_3_real_silence()
    test_4_artificial_gap()
    test_5_overlap()
    test_6_long_narration()
    test_7_100_plus_scenes()
    test_8_image_shortage()
    test_9_excess_images()
    test_10_transitions()
    test_11_transition_timeline_validation()
    test_12_audio_master_alignment()

    print("\n" + "=" * 65)
    print(" ALL 12 TIMELINE CONTINUITY TESTS PASSED (100%)")
    print("=" * 65 + "\n")


if __name__ == '__main__':
    run_all_continuity_tests()
