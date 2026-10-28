#!/usr/bin/env python3
"""
engine/test_timeline_split.py — Focused Unit & Regression Test Suite for Split-at-Playhead.
Phase 2A: Safe Timeline Editing MVP.

Verifies:
  1. Valid split within middle of a scene (boundary continuity, integer-ms normalization).
  2. Sub-second fractional timestamps (precision preservation).
  3. Strict total duration preservation against master audio duration.
  4. Consecutive continuity (scene[k].start == scene[k-1].end).
  5. Rejection of negative or zero split positions.
  6. Rejection of split positions exceeding master duration.
  7. Rejection of split positions too close to scene start (< min_clip_duration).
  8. Rejection of split positions too close to scene end (< min_clip_duration).
  9. Rejection of split positions directly on existing cut boundaries.
 10. Single-scene project split into two contiguous scenes.
 11. Multi-split sequence (successive splits on resulting clips).
 12. Backward compatibility with plan.json serialization.
"""

import sys
import os
import math
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from engine.timeline_normalizer import TimelineNormalizer
from engine.errors import InvalidTimelineError


def create_fixture_scenes():
    """Create a standard 4-scene project spanning [0.0, 20.0s]."""
    return [
        {"segment_index": 0, "start": 0.0, "end": 5.0, "dur": 5.0, "image": "img1.png", "transition": "clean_cut"},
        {"segment_index": 1, "start": 5.0, "end": 10.0, "dur": 5.0, "image": "img2.png", "transition": "cinematic_dissolve"},
        {"segment_index": 2, "start": 10.0, "end": 15.0, "dur": 5.0, "image": "img3.png", "transition": "soft_wipe"},
        {"segment_index": 3, "start": 15.0, "end": 20.0, "dur": 5.0, "image": "img4.png", "transition": "clean_cut"},
    ]


def test_valid_middle_split():
    """Test 1: Split a 5.0s scene at 2.5s -> [0.0, 2.5] and [2.5, 5.0]."""
    scenes = create_fixture_scenes()
    master_dur = 20.0
    new_scenes, new_idx = TimelineNormalizer.split_scene_at(scenes, split_time=2.5, master_dur=master_dur)

    assert len(new_scenes) == 5, f"Expected 5 scenes, got {len(new_scenes)}"
    assert new_idx == 1, f"Expected new clip at index 1, got {new_idx}"
    assert new_scenes[0]["start"] == 0.0
    assert new_scenes[0]["end"] == 2.5
    assert new_scenes[0]["dur"] == 2.5
    assert new_scenes[1]["start"] == 2.5
    assert new_scenes[1]["end"] == 5.0
    assert new_scenes[1]["dur"] == 2.5
    assert new_scenes[2]["start"] == 5.0

    valid, errs, _ = TimelineNormalizer.validate_timeline(new_scenes, master_dur)
    assert valid, f"Validation failed: {errs}"
    print("PASS: test_valid_middle_split")


def test_fractional_split_precision():
    """Test 2: Split with fractional millisecond accuracy at 7.345s."""
    scenes = create_fixture_scenes()
    master_dur = 20.0
    new_scenes, new_idx = TimelineNormalizer.split_scene_at(scenes, split_time=7.345, master_dur=master_dur)

    assert len(new_scenes) == 5
    assert new_idx == 2
    assert new_scenes[1]["start"] == 5.0
    assert new_scenes[1]["end"] == 7.345
    assert new_scenes[1]["dur"] == 2.345
    assert new_scenes[2]["start"] == 7.345
    assert new_scenes[2]["end"] == 10.0
    assert new_scenes[2]["dur"] == 2.655

    valid, errs, _ = TimelineNormalizer.validate_timeline(new_scenes, master_dur)
    assert valid, f"Validation failed: {errs}"
    print("PASS: test_fractional_split_precision")


def test_total_duration_preserved():
    """Test 3: Total visual coverage matches master audio duration exactly."""
    scenes = create_fixture_scenes()
    master_dur = 20.0
    new_scenes, _ = TimelineNormalizer.split_scene_at(scenes, split_time=12.123, master_dur=master_dur)

    total_dur = sum(s["dur"] for s in new_scenes)
    assert abs(total_dur - master_dur) < 0.005, f"Total duration drifted: {total_dur} vs {master_dur}"
    assert new_scenes[-1]["end"] == master_dur
    print("PASS: test_total_duration_preserved")


def test_consecutive_continuity():
    """Test 4: Consecutive continuity: scene[n].start == scene[n-1].end for all scenes."""
    scenes = create_fixture_scenes()
    master_dur = 20.0
    new_scenes, _ = TimelineNormalizer.split_scene_at(scenes, split_time=17.5, master_dur=master_dur)

    for i in range(1, len(new_scenes)):
        prev_end = new_scenes[i - 1]["end"]
        curr_start = new_scenes[i]["start"]
        assert prev_end == curr_start, f"Discontinuity at #{i}: prev_end={prev_end} != curr_start={curr_start}"
    print("PASS: test_consecutive_continuity")


def test_reject_negative_or_zero_split():
    """Test 5: Rejection of negative or zero split positions."""
    scenes = create_fixture_scenes()
    master_dur = 20.0

    # Zero
    try:
        TimelineNormalizer.split_scene_at(scenes, split_time=0.0, master_dur=master_dur)
        assert False, "Failed to reject split_time=0.0"
    except ValueError as e:
        assert "positive" in str(e).lower()

    # Negative
    try:
        TimelineNormalizer.split_scene_at(scenes, split_time=-1.5, master_dur=master_dur)
        assert False, "Failed to reject split_time=-1.5"
    except ValueError as e:
        assert "positive" in str(e).lower()
    print("PASS: test_reject_negative_or_zero_split")


def test_reject_split_exceeding_duration():
    """Test 6: Rejection of split positions exceeding master audio duration."""
    scenes = create_fixture_scenes()
    master_dur = 20.0

    try:
        TimelineNormalizer.split_scene_at(scenes, split_time=20.5, master_dur=master_dur)
        assert False, "Failed to reject split_time=20.5"
    except ValueError as e:
        assert "exceeds" in str(e).lower()

    try:
        TimelineNormalizer.split_scene_at(scenes, split_time=20.0, master_dur=master_dur)
        assert False, "Failed to reject split_time=20.0 (at end boundary)"
    except ValueError as e:
        assert "exceeds" in str(e).lower()
    print("PASS: test_reject_split_exceeding_duration")


def test_reject_split_too_close_to_start():
    """Test 7: Rejection when head clip would be < min_clip_duration."""
    scenes = create_fixture_scenes()
    master_dur = 20.0

    # Scene 1 starts at 5.0. Split at 5.15s with min_clip_duration=0.3s -> head duration 0.15s (rejected)
    try:
        TimelineNormalizer.split_scene_at(scenes, split_time=5.15, master_dur=master_dur, min_clip_duration=0.3)
        assert False, "Failed to reject split too close to scene start"
    except ValueError as e:
        assert "too close to scene start" in str(e).lower()
    print("PASS: test_reject_split_too_close_to_start")


def test_reject_split_too_close_to_end():
    """Test 8: Rejection when tail clip would be < min_clip_duration."""
    scenes = create_fixture_scenes()
    master_dur = 20.0

    # Scene 1 ends at 10.0. Split at 9.85s with min_clip_duration=0.3s -> tail duration 0.15s (rejected)
    try:
        TimelineNormalizer.split_scene_at(scenes, split_time=9.85, master_dur=master_dur, min_clip_duration=0.3)
        assert False, "Failed to reject split too close to scene end"
    except ValueError as e:
        assert "too close to scene end" in str(e).lower()
    print("PASS: test_reject_split_too_close_to_end")


def test_reject_split_on_existing_boundary():
    """Test 9: Rejection of split position exactly on cut boundary (e.g. 5.0s)."""
    scenes = create_fixture_scenes()
    master_dur = 20.0

    try:
        TimelineNormalizer.split_scene_at(scenes, split_time=5.0, master_dur=master_dur)
        assert False, "Failed to reject split on exact cut boundary"
    except ValueError as e:
        assert "cut boundary" in str(e).lower() or "does not fall strictly" in str(e).lower()
    print("PASS: test_reject_split_on_existing_boundary")


def test_single_scene_split():
    """Test 10: Single scene covering entire audio split into two scenes."""
    single_scene = [{"segment_index": 0, "start": 0.0, "end": 30.0, "dur": 30.0, "image": "hero.png"}]
    master_dur = 30.0
    new_scenes, new_idx = TimelineNormalizer.split_scene_at(single_scene, split_time=12.0, master_dur=master_dur)

    assert len(new_scenes) == 2
    assert new_idx == 1
    assert new_scenes[0]["start"] == 0.0
    assert new_scenes[0]["end"] == 12.0
    assert new_scenes[1]["start"] == 12.0
    assert new_scenes[1]["end"] == 30.0

    valid, errs, _ = TimelineNormalizer.validate_timeline(new_scenes, master_dur)
    assert valid, f"Validation failed: {errs}"
    print("PASS: test_single_scene_split")


def test_successive_splits():
    """Test 11: Multi-split sequence (split scene, then split the resulting cut)."""
    scenes = create_fixture_scenes()
    master_dur = 20.0

    # Split Scene 0 [0.0..5.0] at 2.0s -> [0.0..2.0] and [2.0..5.0]
    pass1, _ = TimelineNormalizer.split_scene_at(scenes, split_time=2.0, master_dur=master_dur)
    assert len(pass1) == 5

    # Now split the second part [2.0..5.0] at 3.5s -> [2.0..3.5] and [3.5..5.0]
    pass2, _ = TimelineNormalizer.split_scene_at(pass1, split_time=3.5, master_dur=master_dur)
    assert len(pass2) == 6

    # Verify all segments are contiguous
    valid, errs, _ = TimelineNormalizer.validate_timeline(pass2, master_dur)
    assert valid, f"Validation failed: {errs}"
    assert pass2[0]["dur"] == 2.0
    assert pass2[1]["dur"] == 1.5
    assert pass2[2]["dur"] == 1.5
    print("PASS: test_successive_splits")


def test_backward_compatibility_schema():
    """Test 12: Verify all original fields (motion, transition, context) survive split."""
    scenes = [{
        "segment_index": 0,
        "start": 0.0,
        "end": 10.0,
        "dur": 10.0,
        "image": "img.png",
        "transition": "cinematic_dissolve",
        "motion": "L4/push",
        "context": "dramatic",
        "confidence": 0.92,
        "confidence_level": "HIGH",
        "narration_text": "Original speech text here."
    }]
    master_dur = 10.0
    new_scenes, _ = TimelineNormalizer.split_scene_at(scenes, split_time=4.0, master_dur=master_dur)

    for sc in new_scenes:
        assert sc["image"] == "img.png"
        assert sc["transition"] == "cinematic_dissolve"
        assert sc["motion"] == "L4/push"
        assert sc["context"] == "dramatic"
        assert sc["confidence_level"] == "HIGH"
        assert sc["user_override"] is True
        assert "narration_text" in sc
    print("PASS: test_backward_compatibility_schema")


if __name__ == "__main__":
    print("=" * 70)
    print(" RENDERFLOW — PHASE 2A: SPLIT-AT-PLAYHEAD TEST SUITE")
    print("=" * 70)

    test_valid_middle_split()
    test_fractional_split_precision()
    test_total_duration_preserved()
    test_consecutive_continuity()
    test_reject_negative_or_zero_split()
    test_reject_split_exceeding_duration()
    test_reject_split_too_close_to_start()
    test_reject_split_too_close_to_end()
    test_reject_split_on_existing_boundary()
    test_single_scene_split()
    test_successive_splits()
    test_backward_compatibility_schema()

    print("=" * 70)
    print(" ALL 12 SPLIT-AT-PLAYHEAD TESTS PASSED (100% SUCCESS)")
    print("=" * 70)
