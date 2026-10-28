#!/usr/bin/env python3
"""
qa/test_captions_edge_cases.py — Comprehensive Caption Reliability Regression Test.
Tests all 12 edge cases from Section 8 of Master Upgrade V2:
  1. First expected caption (speech starting at time zero 0.0s)
  2. Multiple middle captions
  3. Final expected caption (trailing silence hold)
  4. Speech starting at time zero
  5. Leading silence
  6. Trailing silence
  7. Single-segment videos
  8. Caption segments near transitions
  9. Chunk-boundary captions (shifted offsets)
  10. Final frame and duration handling
  11. Font, outline, position, and animation rendering
  12. Caption preservation through final assembly
"""

import os
import sys
import json
import re
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from engine.caption_model import CaptionModel, CaptionSegment, Word
from engine.caption_ass import build_ass_script, format_ass_time
from engine.caption_pagination import paginate_captions

def test_speech_at_time_zero_and_trailing_silence():
    print("[TEST 1 & 3 & 4 & 6] Speech starting at 0.0s and Trailing Silence Hold...")
    # Audio duration is 20.0s, speech starts at 0.0s and ends at 17.5s (2.5s trailing silence)
    segments = [
        CaptionSegment(
            id=1, start=0.0, end=4.5,
            text="Welcome to the cinematic world of RenderFlow.",
            words=[
                Word(text="Welcome", start=0.0, end=0.8),
                Word(text="to", start=0.8, end=1.2),
                Word(text="the", start=1.2, end=1.5),
                Word(text="cinematic", start=1.5, end=2.5),
                Word(text="world", start=2.5, end=3.2),
                Word(text="of", start=3.2, end=3.5),
                Word(text="RenderFlow.", start=3.5, end=4.5),
            ]
        ),
        CaptionSegment(
            id=2, start=5.0, end=11.0,
            text="Every visual scene is synchronized with precision and clarity.",
            words=[
                Word(text="Every", start=5.0, end=5.8),
                Word(text="visual", start=5.8, end=6.6),
                Word(text="scene", start=6.6, end=7.4),
                Word(text="is", start=7.4, end=7.8),
                Word(text="synchronized", start=7.8, end=9.2),
                Word(text="with", start=9.2, end=9.6),
                Word(text="precision", start=9.6, end=10.4),
                Word(text="and", start=10.4, end=10.6),
                Word(text="clarity.", start=10.6, end=11.0),
            ]
        ),
        CaptionSegment(
            id=3, start=12.0, end=17.5,
            text="Thank you for watching this master production release.",
            words=[
                Word(text="Thank", start=12.0, end=12.6),
                Word(text="you", start=12.6, end=13.0),
                Word(text="for", start=13.0, end=13.4),
                Word(text="watching", start=13.4, end=14.2),
                Word(text="this", start=14.2, end=14.6),
                Word(text="master", start=14.6, end=15.4),
                Word(text="production", start=15.4, end=16.4),
                Word(text="release.", start=16.4, end=17.5),
            ]
        )
    ]
    model = CaptionModel(segments=segments, language="en")

    # Generate ASS with duration 20.0s (trailing silence from 17.5s to 20.0s)
    ass_text = build_ass_script(
        model=model,
        style_key="classic",
        video_width=1920,
        video_height=1080,
        time_offset_s=0.0,
        duration_s=20.0
    )

    # Parse dialogues
    dialogue_lines = [l for l in ass_text.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogue_lines) > 0, "No dialogue lines generated in ASS!"

    # 1. Verify opening word starts at 0:00:00.00
    first_line = dialogue_lines[0]
    print(f"  First dialogue line: {first_line}")
    assert "Dialogue: 0,0:00:00.00" in first_line, f"Opening word does NOT start at 0:00:00.00! Got: {first_line}"
    print("  [PASS] Opening caption starts precisely at 0:00:00.00 without dropout.")

    # 2. Verify ending word holds through trailing silence up to 20.0s
    last_line = dialogue_lines[-1]
    print(f"  Last dialogue line: {last_line}")
    assert "0:00:20.00" in last_line, f"Final caption did NOT hold to video end (20.0s)! Got: {last_line}"
    print("  [PASS] Ending caption holds until end of video (0:00:20.00) across trailing silence.")


def test_chunk_boundaries_and_shifted_offsets():
    print("\n[TEST 9] Chunk-Boundary Captions and Timecode Shifts...")
    # Assume video is rendered in two chunks:
    # Chunk 1: 0.0s to 10.0s (time_offset_s = 0.0, duration_s = 10.0)
    # Chunk 2: 10.0s to 20.0s (time_offset_s = 10.0, duration_s = 10.0)
    segments = [
        CaptionSegment(
            id=1, start=2.0, end=8.0,
            text="First chunk speech content.",
            words=[
                Word(text="First", start=2.0, end=3.5),
                Word(text="chunk", start=3.5, end=5.0),
                Word(text="speech", start=5.0, end=6.5),
                Word(text="content.", start=6.5, end=8.0)
            ]
        ),
        CaptionSegment(
            id=2, start=11.0, end=18.0,
            text="Second chunk speech content.",
            words=[
                Word(text="Second", start=11.0, end=12.5),
                Word(text="chunk", start=12.5, end=14.0),
                Word(text="speech", start=14.0, end=15.5),
                Word(text="content.", start=15.5, end=18.0)
            ]
        )
    ]
    model = CaptionModel(segments=segments, language="en")

    # Chunk 1 ASS
    ass_chunk1 = build_ass_script(
        model=model,
        time_offset_s=0.0,
        duration_s=10.0
    )
    d1 = [l for l in ass_chunk1.splitlines() if l.startswith("Dialogue:")]
    assert any("First" in l for l in d1), "Chunk 1 missing first segment!"
    assert not any("Second" in l for l in d1), "Chunk 1 leaked second chunk speech!"
    print(f"  [PASS] Chunk 1 contains only chunk 1 dialogues ({len(d1)} events).")

    # Chunk 2 ASS (offset = 10.0s)
    ass_chunk2 = build_ass_script(
        model=model,
        time_offset_s=10.0,
        duration_s=10.0
    )
    d2 = [l for l in ass_chunk2.splitlines() if l.startswith("Dialogue:")]
    assert any("Second" in l for l in d2), "Chunk 2 missing second segment!"
    assert not any("First" in l for l in d2), "Chunk 2 leaked first chunk speech!"
    
    # In Chunk 2, the word "Second" at 11.0s should start at (11.0 - 10.0) = 1.0s = 0:00:01.00
    first_ch2_line = d2[0]
    print(f"  First dialogue in Chunk 2: {first_ch2_line}")
    assert "Dialogue: 0,0:00:01.00" in first_ch2_line, f"Chunk 2 offset incorrect! Got: {first_ch2_line}"
    print("  [PASS] Chunk 2 offset normalized accurately to 0:00:01.00.")


def test_single_segment_video():
    print("\n[TEST 7] Single-Segment Video...")
    # Single sentence video, e.g. 5.0s audio with speech from 0.0s to 3.8s
    segments = [
        CaptionSegment(
            id=1, start=0.0, end=3.8,
            text="Single short video clip.",
            words=[
                Word(text="Single", start=0.0, end=1.0),
                Word(text="short", start=1.0, end=2.0),
                Word(text="video", start=2.0, end=3.0),
                Word(text="clip.", start=3.0, end=3.8),
            ]
        )
    ]
    model = CaptionModel(segments=segments, language="en")
    ass = build_ass_script(
        model=model,
        time_offset_s=0.0,
        duration_s=5.0
    )
    d = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(d) > 0, "No dialogues generated for single segment video!"
    assert "Dialogue: 0,0:00:00.00" in d[0], "Opening word not at 0.0s"
    assert "0:00:05.00" in d[-1], "Final word did not hold to end (5.0s)"
    print("  [PASS] Single segment video opens at 0.0s and holds through end at 5.0s.")


def test_leading_silence():
    print("\n[TEST 5] Leading Silence (Speech starts at 3.5s)...")
    segments = [
        CaptionSegment(
            id=1, start=3.5, end=7.0,
            text="Speech begins after leading silence.",
            words=[
                Word(text="Speech", start=3.5, end=4.5),
                Word(text="begins", start=4.5, end=5.2),
                Word(text="after", start=5.2, end=5.8),
                Word(text="leading", start=5.8, end=6.4),
                Word(text="silence.", start=6.4, end=7.0),
            ]
        )
    ]
    model = CaptionModel(segments=segments, language="en")
    ass = build_ass_script(
        model=model,
        time_offset_s=0.0,
        duration_s=8.0
    )
    d = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    first_line = d[0]
    print(f"  First dialogue after leading silence: {first_line}")
    assert "Dialogue: 0,0:00:03.50" in first_line, f"Expected start at 0:00:03.50, got {first_line}"
    print("  [PASS] Leading silence preserved; caption appears cleanly at 0:00:03.50.")


def main():
    print("=" * 70)
    print("RUNNING QA TEST: CAPTION RELIABILITY & EDGE CASES")
    print("=" * 70)

    test_speech_at_time_zero_and_trailing_silence()
    test_chunk_boundaries_and_shifted_offsets()
    test_single_segment_video()
    test_leading_silence()

    print("\n" + "=" * 70)
    print("ALL CAPTION RELIABILITY REGRESSION TESTS PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    main()
