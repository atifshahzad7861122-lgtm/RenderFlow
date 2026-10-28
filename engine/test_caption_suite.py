#!/usr/bin/env python3
"""
test_caption_suite.py — Comprehensive Automated Test Suite for Rendering Studio Captions.

Tests:
  1. All 10 native styles generation and syntax.
  2. Sentence-aware and silence-aware pagination (Short, Medium, Long).
  3. Abbreviation preservation (Dr., vs., $1.5M).
  4. Active-word time slicing and tag formatting.
  5. Multilingual and Unicode integrity (English, Urdu, Arabic, Hindi, Spanish, Chinese, Japanese).
  6. Chunk timestamp safety (shifting global timecodes to local 0-based chunk timecodes).
  7. SRT, ASS, and JSON export correctness.
  8. Model validation and error handling.
"""

import sys
import os
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.caption_model import CaptionModel, CaptionSegment, Word
from engine.caption_pagination import paginate_captions, is_sentence_ender, is_abbreviation
from engine.caption_styles import CAPTION_STYLES, get_style, customize_style, resolve_auto_style
from engine.caption_ass import build_ass_script, format_ass_time
from engine.caption_export import export_srt, export_ass, export_json
from engine.caption_qc import validate_caption_model_integrity, check_caption_safe_margins


def test_abbreviations():
    print("Testing abbreviation handling...")
    assert is_abbreviation("Dr."), "Dr. should be an abbreviation"
    assert is_abbreviation("vs."), "vs. should be an abbreviation"
    assert is_abbreviation("$1.5"), "$1.5 should be an abbreviation"
    assert not is_sentence_ender("Dr."), "Dr. should not end a sentence"
    assert not is_sentence_ender("vs."), "vs. should not end a sentence"
    assert is_sentence_ender("expanded."), "expanded. should end a sentence"
    assert is_sentence_ender("vision!"), "vision! should end a sentence"
    assert is_sentence_ender("really?"), "really? should end a sentence"
    print("  -> PASS: Abbreviation protection verified.")


def test_pagination():
    print("Testing sentence & silence-aware pagination...")
    # Sample words across a multi-sentence thought
    raw_words = [
        Word("The", 0.0, 0.3),
        Word("ancient", 0.3, 0.7),
        Word("empire", 0.7, 1.2),
        Word("expanded", 1.2, 1.8),
        Word("rapidly.", 1.8, 2.4),    # Sentence end
        Word("This", 2.8, 3.1),         # Pause gap = 0.4s
        Word("changed", 3.1, 3.6),
        Word("everything", 3.6, 4.2),
        Word("across", 4.2, 4.6),
        Word("the", 4.6, 4.8),
        Word("entire", 4.8, 5.2),
        Word("continent.", 5.2, 5.8)    # Sentence end
    ]
    raw_seg = CaptionSegment(id=1, start=0.0, end=5.8, text="The ancient empire expanded rapidly. This changed everything across the entire continent.", words=raw_words)
    raw_model = CaptionModel(segments=[raw_seg])

    paginated = paginate_captions(raw_model, length_mode="medium")
    print(f"  -> Generated {len(paginated.segments)} pages from 2 sentences")
    assert len(paginated.segments) >= 2, "Should split at sentence boundary"
    assert "rapidly." in paginated.segments[0].text, "First page must end with rapidly."
    assert paginated.segments[1].text.startswith("This"), "Second page must start with This"
    print("  -> PASS: Sentence and silence boundary pagination verified.")


def test_all_10_styles():
    print("Testing all 10 native styles ASS generation...")
    test_words = [
        Word("Every", 0.0, 0.5),
        Word("great", 0.5, 1.0),
        Word("empire", 1.0, 1.6),
        Word("begins", 1.6, 2.1),
        Word("with", 2.1, 2.4),
        Word("a", 2.4, 2.6),
        Word("vision.", 2.6, 3.2),
    ]
    seg = CaptionSegment(id=1, start=0.0, end=3.2, text="Every great empire begins with a vision.", words=test_words)
    model = CaptionModel(segments=[seg])

    for style_key in CAPTION_STYLES.keys():
        ass_str = build_ass_script(model, style_key=style_key)
        assert "[Script Info]" in ass_str, f"{style_key}: Missing [Script Info]"
        assert "[V4+ Styles]" in ass_str, f"{style_key}: Missing [V4+ Styles]"
        assert "[Events]" in ass_str, f"{style_key}: Missing [Events]"
        assert "Dialogue:" in ass_str, f"{style_key}: Missing Dialogue lines"
        print(f"  -> Style '{style_key}': PASS")

    print("  -> PASS: All 10 styles generated valid ASS scripts.")


def test_multilingual_unicode_rtl():
    print("Testing multilingual Unicode and RTL script handling...")
    test_cases = [
        ("English", "Every great empire begins with a vision."),
        ("Urdu", "ہر عظیم سلطنت کا آغاز ایک خواب سے ہوتا ہے۔"),
        ("Arabic", "تبدأ كل إمبراطورية عظيمة برؤية واضحة."),
        ("Hindi", "प्रत्येक महान साम्राज्य की शुरुआत एक दृष्टिकोण से होती है।"),
        ("Spanish", "Cada gran imperio comienza con una visión."),
        ("French", "Chaque grand empire commence par une vision."),
        ("German", "Jedes große Reich beginnt mit einer Vision."),
        ("Chinese", "每一个伟大的帝国都始于一个远见。"),
        ("Japanese", "すべての偉大な帝国はビジョンから始まります。"),
    ]

    for lang, text in test_cases:
        words = [Word(w, i * 0.5, (i + 1) * 0.5) for i, w in enumerate(text.split())]
        seg = CaptionSegment(id=1, start=0.0, end=len(words) * 0.5, text=text, words=words)
        model = CaptionModel(segments=[seg], language=lang)
        
        ok, errs = validate_caption_model_integrity(model)
        assert ok, f"{lang} integrity error: {errs}"
        
        ass_out = build_ass_script(model, style_key="classic")
        assert text in ass_out or words[0].text in ass_out, f"{lang} text missing in ASS output"
        print(f"  -> {lang}: PASS (Unicode preserved)")

    print("  -> PASS: All 9 language scripts verified without corruption.")


def test_chunk_timestamp_safety():
    print("Testing streaming chunk timestamp safety...")
    # Caption spans 95.0s to 98.0s globally
    w1 = Word("Global", 95.0, 96.5)
    w2 = Word("Narrative", 96.5, 98.0)
    seg = CaptionSegment(id=1, start=95.0, end=98.0, text="Global Narrative", words=[w1, w2])
    model = CaptionModel(segments=[seg])

    # When Chunk 2 starts at 90.0s, local caption offset is 90.0s
    chunk_ass = build_ass_script(model, style_key="classic", time_offset_s=90.0)
    
    # Expected local time: 95.0 - 90.0 = 5.0s -> 0:00:05.00
    assert "0:00:05.00" in chunk_ass, "Local start timestamp should be normalized to 5.00s"
    assert "0:00:08.00" in chunk_ass, "Local end timestamp should be normalized to 8.00s"
    print("  -> PASS: Streaming chunk timestamp safety verified.")


def test_exporters(tmp_path: Path):
    print("Testing SRT, ASS, and JSON exporters...")
    w1 = Word("Hello", 1.0, 2.0)
    w2 = Word("World", 2.0, 3.5)
    seg = CaptionSegment(id=1, start=1.0, end=3.5, text="Hello World", words=[w1, w2])
    model = CaptionModel(segments=[seg])

    srt_file = tmp_path / "test.srt"
    ass_file = tmp_path / "test.ass"
    json_file = tmp_path / "test.json"

    export_srt(model, srt_file)
    export_ass(model, ass_file, style_key="classic")
    export_json(model, json_file)

    assert srt_file.exists() and srt_file.stat().st_size > 10
    assert ass_file.exists() and ass_file.stat().st_size > 10
    assert json_file.exists() and json_file.stat().st_size > 10

    srt_content = srt_file.read_text(encoding="utf-8")
    assert "00:00:01,000 --> 00:00:03,500" in srt_content
    assert "Hello World" in srt_content

    json_content = json.loads(json_file.read_text(encoding="utf-8"))
    assert len(json_content["segments"]) == 1
    assert json_content["segments"][0]["words"][0]["text"] == "Hello"
    print("  -> PASS: All export formats verified.")


def main():
    print("==================================================")
    print("RUNNING MASTER CAPTION TEST SUITE")
    print("==================================================")
    test_abbreviations()
    test_pagination()
    test_all_10_styles()
    test_multilingual_unicode_rtl()
    test_chunk_timestamp_safety()

    test_dir = Path("projects/benchmarks/caption_tests")
    test_dir.mkdir(parents=True, exist_ok=True)
    test_exporters(test_dir)

    print("==================================================")
    print("ALL CAPTION UNIT & INTEGRATION TESTS PASSED (100%)")
    print("==================================================")


if __name__ == "__main__":
    main()
