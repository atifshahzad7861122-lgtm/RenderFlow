#!/usr/bin/env python3
"""
test_minimal_captions_suite.py — Forensic Verification of Caption Boundaries & Margins.

Executes Controlled Tests:
  Test A: Short caption
  Test B: Long caption
  Test C: Two-line caption
  Test D: Caption near bottom safe area
  Test E: Caption near top safe area
  Test F: Maximum-width caption
  Test G: Multilingual caption
  Test H: RTL caption

For each test records:
  - PASS / FAIL
  - bounding box (left, top, right, bottom)
  - margin values (margin_lr, margin_v)
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from engine.caption_model import CaptionModel, CaptionSegment, Word
from engine.caption_styles import get_style, customize_style
from engine.caption_ass import build_ass_script, wrap_caption_lines
from engine.caption_qc import (
    measure_text_bounding_box,
    check_caption_safe_margins,
    validate_caption_model_integrity
)


def run_minimal_caption_tests() -> Dict[str, Any]:
    print("=" * 75)
    print(" CONTROLLED MINIMAL CAPTION TEST SUITE (1920x1080 @ 30 FPS)")
    print("=" * 75)

    W, H = 1920, 1080
    safe_margin_lr = 60
    safe_margin_v = 50

    tests = [
        {
            "id": "Test A",
            "name": "Short caption",
            "text": "Focus now.",
            "style": "classic",
            "overrides": {"position": "bottom", "margin_v": 65, "margin_lr": 120},
        },
        {
            "id": "Test B",
            "name": "Long caption",
            "text": "Architects planned monumental structures across the entire desert valley over several centuries.",
            "style": "classic",
            "overrides": {"position": "bottom", "margin_v": 65, "margin_lr": 120},
        },
        {
            "id": "Test C",
            "name": "Two-line caption",
            "text": "Every great empire begins with a vision\\Nand determination across generations.",
            "style": "classic",
            "overrides": {"position": "bottom", "margin_v": 65, "margin_lr": 120},
        },
        {
            "id": "Test D",
            "name": "Caption near bottom safe area",
            "text": "Positioned precisely above the bottom safe line.",
            "style": "classic",
            "overrides": {"position": "bottom", "margin_v": 65, "margin_lr": 120},
        },
        {
            "id": "Test E",
            "name": "Caption near top safe area",
            "text": "Positioned near the top boundary zone.",
            "style": "classic",
            "overrides": {"position": "top", "margin_v": 65, "margin_lr": 120},
        },
        {
            "id": "Test F",
            "name": "Maximum-width caption",
            "text": "A comprehensive exploration of architectural marvels and archaeological discoveries.",
            "style": "classic",
            "overrides": {"position": "bottom", "margin_v": 65, "margin_lr": 120},
        },
        {
            "id": "Test G",
            "name": "Multilingual caption (Spanish / Hindi)",
            "text": "Cada gran imperio comienza con una visión.",
            "style": "classic",
            "overrides": {"position": "bottom", "margin_v": 65, "margin_lr": 120},
        },
        {
            "id": "Test H",
            "name": "RTL caption (Urdu / Arabic)",
            "text": "ہر عظیم سلطنت کا آغاز ایک خواب سے ہوتا ہے۔",
            "style": "classic",
            "overrides": {"position": "bottom", "margin_v": 65, "margin_lr": 120},
        },
    ]

    results = []
    all_passed = True

    for t in tests:
        cfg = customize_style(t["style"], overrides=t.get("overrides"))
        raw_text = t["text"]
        
        # Format lines with wrap if needed
        if "\\N" not in raw_text:
            word_list = raw_text.split()
            wrapped_groups = wrap_caption_lines(word_list, max_chars=cfg.get("max_width_chars", 48))
            text_wrapped = r"\N".join([" ".join(grp) for grp in wrapped_groups])
        else:
            text_wrapped = raw_text

        bbox = measure_text_bounding_box(
            text=text_wrapped,
            font_name=cfg["font"],
            font_size=cfg["font_size"],
            alignment=cfg["alignment"],
            margin_l=cfg["margin_lr"],
            margin_r=cfg["margin_lr"],
            margin_v=cfg["margin_v"],
            outline=cfg["outline_width"],
            shadow=cfg["shadow_depth"],
            video_width=W,
            video_height=H
        )

        left, top, right, bottom = bbox
        is_left_ok = left >= safe_margin_lr
        is_right_ok = right <= (W - safe_margin_lr)
        is_top_ok = top >= safe_margin_v
        is_bottom_ok = bottom <= (H - safe_margin_v)
        is_screen_ok = 0 <= left < right <= W and 0 <= top < bottom <= H

        passed = is_left_ok and is_right_ok and is_top_ok and is_bottom_ok and is_screen_ok
        if not passed:
            all_passed = False

        status_str = "PASS" if passed else "FAIL"

        res_record = {
            "test_id": t["id"],
            "name": t["name"],
            "status": status_str,
            "text": raw_text.replace("\\N", " "),
            "bounding_box": bbox,
            "margin_values": {"margin_lr": cfg["margin_lr"], "margin_v": cfg["margin_v"]},
            "alignment": cfg["alignment"],
            "checks": {
                "left_ge_safe": is_left_ok,
                "right_le_safe": is_right_ok,
                "top_ge_safe": is_top_ok,
                "bottom_le_safe": is_bottom_ok,
                "in_screen": is_screen_ok
            }
        }
        results.append(res_record)

        print(f"[{status_str}] {t['id']}: {t['name']}")
        print(f"       Text:         \"{raw_text.replace(chr(92)+'N', ' / ')}\"")
        print(f"       Bounding Box: left={left:.1f}, top={top:.1f}, right={right:.1f}, bottom={bottom:.1f}")
        print(f"       Margins:      margin_lr={cfg['margin_lr']}, margin_v={cfg['margin_v']}, align={cfg['alignment']}")
        if not passed:
            print(f"       Violations:   {res_record['checks']}")
        print("-" * 75)

    print("\n" + "=" * 75)
    print(f" MINIMAL CAPTION TEST MATRIX: {'ALL 8 TESTS PASSED (100%)' if all_passed else 'SOME TESTS FAILED'}")
    print("=" * 75)

    return {
        "overall_status": "PASS" if all_passed else "FAIL",
        "tests": results
    }


if __name__ == "__main__":
    res = run_minimal_caption_tests()
    sys.exit(0 if res["overall_status"] == "PASS" else 1)
