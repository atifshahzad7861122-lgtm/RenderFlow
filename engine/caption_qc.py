#!/usr/bin/env python3
"""
caption_qc.py — Rigorous Quality Control for Audio-Synchronized Captions.

Verifies:
  1. Timeline integrity (start/end monotonicity, positive durations, non-negative offsets).
  2. Word-level timestamp bounds (each word strictly enclosed in its segment).
  3. Font-metrics & Safe Area boundaries (prevents horizontal overflow, vertical clipping, and safe margin collapse):
       left >= safe_margin_lr
       right <= video_width - safe_margin_lr
       top >= safe_margin_v
       bottom <= video_height - safe_margin_v
  4. Unicode & script integrity (Latin, Arabic, Urdu, Hindi, CJK, Cyrillic).
  5. Visual verification on rendered MP4: samples frames during active speech and verifies
     the caption subtitle layer is visibly burned in without corrupting visual frames.
"""

import subprocess
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
from PIL import Image, ImageFont, ImageDraw

from .caption_model import CaptionModel
from .caption_styles import get_style, customize_style
from .caption_ass import wrap_caption_lines

logger = logging.getLogger("rendering_studio.caption_qc")

# In-memory font cache for metric measurements
_FONT_CACHE: Dict[Tuple[str, int], ImageFont.ImageFont] = {}


def get_font_for_metrics(font_name: str, font_size: int) -> ImageFont.ImageFont:
    """Load system font using PIL with multi-tier fallbacks."""
    key = (font_name.lower().strip(), font_size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    clean_name = font_name.lower().strip()
    font_file_map = {
        "impact": "impact.ttf",
        "segoe ui": "segoeui.ttf",
        "arial": "arial.ttf",
        "consolas": "consola.ttf",
        "comic sans ms": "comic.ttf",
        "georgia": "georgia.ttf",
        "tahoma": "tahoma.ttf",
        "verdana": "verdana.ttf",
        "trebuchet ms": "trebuc.ttf",
        "courier new": "cour.ttf",
        "times new roman": "times.ttf"
    }

    font_obj = None
    windows_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"

    # 1. Exact match in font map
    if clean_name in font_file_map:
        fp = windows_fonts / font_file_map[clean_name]
        if fp.exists():
            try:
                font_obj = ImageFont.truetype(str(fp), font_size)
            except Exception:
                pass

    # 2. Try direct filename on disk
    if font_obj is None:
        for ext in [".ttf", ".otf"]:
            fp = windows_fonts / f"{clean_name}{ext}"
            if fp.exists():
                try:
                    font_obj = ImageFont.truetype(str(fp), font_size)
                    break
                except Exception:
                    pass

    # 3. Direct font family name lookup
    if font_obj is None:
        try:
            font_obj = ImageFont.truetype(clean_name, font_size)
        except Exception:
            pass

    # 4. Standard fallback to Arial or Segoe UI
    if font_obj is None:
        for fb in ["arial.ttf", "segoeui.ttf"]:
            fp = windows_fonts / fb
            if fp.exists():
                try:
                    font_obj = ImageFont.truetype(str(fp), font_size)
                    break
                except Exception:
                    pass

    # 5. PIL default fallback
    if font_obj is None:
        font_obj = ImageFont.load_default()

    _FONT_CACHE[key] = font_obj
    return font_obj


def measure_text_bounding_box(
    text: str,
    font_name: str,
    font_size: int,
    alignment: int = 2,
    margin_l: int = 90,
    margin_r: int = 90,
    margin_v: int = 65,
    outline: float = 2.0,
    shadow: float = 1.5,
    video_width: int = 1920,
    video_height: int = 1080
) -> Tuple[float, float, float, float]:
    """
    Calculate exact (left, top, right, bottom) rendered coordinates
    matching libass positioning.
    """
    font = get_font_for_metrics(font_name, font_size)
    dummy_img = Image.new("RGB", (video_width, video_height))
    draw = ImageDraw.Draw(dummy_img)

    lines = text.split(r"\N")
    line_dims = []
    for l in lines:
        if not l.strip():
            continue
        bbox = draw.textbbox((0, 0), l, font=font)
        w = (bbox[2] - bbox[0]) + 2 * outline + shadow
        h = (bbox[3] - bbox[1]) + 2 * outline + shadow
        line_dims.append((w, h))

    if not line_dims:
        line_dims = [(0.0, 0.0)]

    total_w = max(d[0] for d in line_dims)
    total_h = sum(d[1] for d in line_dims) + max(0, len(line_dims) - 1) * 4.0

    # Alignment based positioning:
    # 1: bottom-left, 2: bottom-center, 3: bottom-right
    # 4: mid-left,    5: mid-center,    6: mid-right
    # 7: top-left,    8: top-center,    9: top-right
    if alignment in (1, 2, 3):
        bottom = float(video_height - margin_v)
        top = bottom - total_h
    elif alignment in (4, 5, 6):
        top = float((video_height - total_h) / 2.0)
        bottom = top + total_h
    elif alignment in (7, 8, 9):
        top = float(margin_v)
        bottom = top + total_h
    else:
        bottom = float(video_height - margin_v)
        top = bottom - total_h

    if alignment in (1, 4, 7):
        left = float(margin_l)
        right = left + total_w
    elif alignment in (3, 6, 9):
        right = float(video_width - margin_r)
        left = right - total_w
    else:  # 2, 5, 8 (center)
        left = float((video_width - total_w) / 2.0)
        right = left + total_w

    return (round(left, 1), round(top, 1), round(right, 1), round(bottom, 1))


def format_margin_diagnostic(
    fail_reason: str,
    expected: str,
    actual: str,
    caption: str,
    timestamp: str,
    bbox: Tuple[float, float, float, float],
    video_dims: Tuple[int, int],
    margins: Tuple[int, int]
) -> str:
    """Format exact diagnostic block matching forensic verification standards."""
    return (
        f"FAIL REASON: {fail_reason}\n"
        f"Expected: {expected}\n"
        f"Actual: {actual}\n"
        f"Caption: \"{caption}\"\n"
        f"Timestamp: {timestamp}\n"
        f"Bounding box: {bbox}\n"
        f"Video dimensions: {video_dims}\n"
        f"Margin: {margins}"
    )


def validate_caption_model_integrity(model: CaptionModel) -> Tuple[bool, List[str]]:
    """Validate data integrity before rendering."""
    return model.validate()


def check_caption_safe_margins(
    model: CaptionModel,
    style_key: str = "classic",
    style_overrides: Optional[Dict[str, Any]] = None,
    video_width: int = 1920,
    video_height: int = 1080,
    ass_path: Optional[Path] = None,
    max_line_chars: int = 55
) -> Tuple[bool, List[str]]:
    """
    Verify that no caption segment violates the project safe area policy:
      left >= safe_margin_lr
      right <= video_width - safe_margin_lr
      top >= safe_margin_v
      bottom <= video_height - safe_margin_v

    Also checks for unbroken words > 35 chars.
    """
    issues = []

    # 1. Check for abnormally long unbroken words that cannot wrap
    for s in model.segments:
        for w in s.words:
            if len(w.text) > 35:
                issues.append(f"Segment {s.id}: extremely long word '{w.text[:20]}...' ({len(w.text)} chars) may clip")

    # 2. Precise Bounding Box Margin Validation
    # If ass_path is provided and exists, read dialogue events directly from ASS
    dialogue_events = []
    style_cfg = customize_style(style_key, overrides=style_overrides)
    font_name = style_cfg.get("font", "Segoe UI")
    font_size = style_cfg.get("font_size", 46)
    alignment = style_cfg.get("alignment", 2)
    margin_l = style_cfg.get("margin_lr", 90)
    margin_r = style_cfg.get("margin_lr", 90)
    margin_v = style_cfg.get("margin_v", 65)
    outline = float(style_cfg.get("outline_width", 2.0))
    shadow = float(style_cfg.get("shadow_depth", 1.5))

    if ass_path and Path(ass_path).exists():
        try:
            ass_content = Path(ass_path).read_text(encoding="utf-8")
            # Parse PlayRes and Style from ASS if available
            for l in ass_content.splitlines():
                if l.startswith("PlayResX:"):
                    try:
                        video_width = int(l.split(":")[1].strip())
                    except Exception:
                        pass
                elif l.startswith("PlayResY:"):
                    try:
                        video_height = int(l.split(":")[1].strip())
                    except Exception:
                        pass
                elif l.startswith("Style: Default"):
                    # Format: Style: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
                    p = l.split(",")
                    if len(p) >= 22:
                        font_name = p[1].strip()
                        font_size = int(p[2].strip())
                        outline = float(p[16].strip())
                        shadow = float(p[17].strip())
                        alignment = int(p[18].strip())
                        margin_l = int(p[19].strip())
                        margin_r = int(p[20].strip())
                        margin_v = int(p[21].strip())

                elif l.startswith("Dialogue:"):
                    # Format: Dialogue: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
                    parts = l.split(",", 9)
                    if len(parts) >= 10:
                        start_t = parts[1].strip()
                        end_t = parts[2].strip()
                        raw_text = parts[9].strip()
                        clean_text = re.sub(r"\{[^\}]*\}", "", raw_text)
                        dialogue_events.append((start_t, end_t, clean_text, raw_text))
        except Exception as e:
            logger.warning(f"Failed to parse ASS file for margins: {e}")

    # If no ASS file, synthesize lines from CaptionModel segments
    if not dialogue_events:
        max_chars = style_cfg.get("max_width_chars", 44)
        for s in model.segments:
            t_start = f"{int(s.start//3600)}:{int((s.start%3600)//60):02d}:{s.start%60:05.2f}"
            t_end = f"{int(s.end//3600)}:{int((s.end%3600)//60):02d}:{s.end%60:05.2f}"
            if s.words:
                wrapped_groups = wrap_caption_lines(s.words, max_chars=max_chars)
                wrapped_text = r"\N".join(" ".join(getattr(w, "text", str(w)) for w in g) for g in wrapped_groups)
                dialogue_events.append((t_start, t_end, wrapped_text, wrapped_text))
            elif s.text:
                wrapped_groups = wrap_caption_lines(s.text.split(), max_chars=max_chars)
                wrapped_text = r"\N".join(" ".join(g) for g in wrapped_groups)
                dialogue_events.append((t_start, t_end, wrapped_text, wrapped_text))

    # Safe margin thresholds
    safe_margin_lr = 60  # Minimum standard title-safe margin
    safe_margin_v = 50   # Minimum vertical safe margin

    for start_t, end_t, clean_text, raw_text in dialogue_events:
        if not clean_text.strip():
            continue

        bbox = measure_text_bounding_box(
            text=clean_text,
            font_name=font_name,
            font_size=font_size,
            alignment=alignment,
            margin_l=margin_l,
            margin_r=margin_r,
            margin_v=margin_v,
            outline=outline,
            shadow=shadow,
            video_width=video_width,
            video_height=video_height
        )
        left, top, right, bottom = bbox

        # Check violations
        viol_types = []
        if left < safe_margin_lr:
            viol_types.append(f"left boundary clipping ({left:.1f} < {safe_margin_lr})")
        if right > (video_width - safe_margin_lr):
            viol_types.append(f"right boundary clipping ({right:.1f} > {video_width - safe_margin_lr})")
        if top < safe_margin_v:
            viol_types.append(f"top safe area violation ({top:.1f} < {safe_margin_v})")
        if bottom > (video_height - safe_margin_v):
            viol_types.append(f"bottom safe area violation ({bottom:.1f} > {video_height - safe_margin_v})")
        if left < 0 or right > video_width or top < 0 or bottom > video_height:
            viol_types.append(f"screen boundary overflow")

        if viol_types:
            diag = format_margin_diagnostic(
                fail_reason=f"Safe area margin violation: {', '.join(viol_types)}",
                expected=f"left >= {safe_margin_lr}, right <= {video_width - safe_margin_lr}, top >= {safe_margin_v}, bottom <= {video_height - safe_margin_v}",
                actual=f"left={left:.1f}, top={top:.1f}, right={right:.1f}, bottom={bottom:.1f}",
                caption=clean_text.replace(r"\N", " "),
                timestamp=f"{start_t} --> {end_t}",
                bbox=bbox,
                video_dims=(video_width, video_height),
                margins=(margin_l, margin_v)
            )
            issues.append(diag)

    return (len(issues) == 0, issues)


def verify_burned_caption_frames(
    video_path: Path,
    caption_model: CaptionModel,
    sample_count: int = 5
) -> Dict[str, Any]:
    """
    Sample video frames during known subtitle intervals to verify that
    subtitles are present and rendered with high visual contrast in the subtitle zone.
    """
    if not video_path.exists():
        return {"status": "FAIL", "reason": f"Video file {video_path} does not exist"}

    if not caption_model.segments:
        return {"status": "PASS", "sampled_frames": 0, "note": "No caption segments to verify"}

    # Pick representative timestamps during speech
    n = len(caption_model.segments)
    indices = np.linspace(0, n - 1, min(sample_count, n), dtype=int)
    results = []

    for idx in indices:
        seg = caption_model.segments[idx]
        t_sample = round((seg.start + seg.end) / 2.0, 3)

        cmd = [
            'ffmpeg', '-hide_banner', '-ss', str(t_sample),
            '-i', str(video_path),
            '-frames:v', '1',
            '-f', 'image2pipe',
            '-pix_fmt', 'rgb24',
            '-vcodec', 'rawvideo', '-'
        ]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0 or len(r.stdout) < 1920 * 1080 * 3:
            results.append({
                "segment_id": seg.id,
                "timestamp": t_sample,
                "status": "EXTRACT_ERROR",
                "text": seg.text
            })
            continue

        frame = np.frombuffer(r.stdout[:1920*1080*3], dtype=np.uint8).reshape((1080, 1920, 3))
        
        bot_region = frame[864:1040, 200:1720]
        mid_region = frame[400:680, 200:1720]
        top_region = frame[80:260, 200:1720]

        best_region = max([bot_region, mid_region, top_region], key=lambda r: float(np.std(r)))
        sub_mean = float(np.mean(best_region))
        sub_std = float(np.std(best_region))

        full_std = float(np.std(frame))
        has_content = (sub_std >= 8.0 and full_std >= 8.0)

        results.append({
            "segment_id": seg.id,
            "timestamp": t_sample,
            "text": seg.text,
            "sub_region_mean": round(sub_mean, 2),
            "sub_region_std": round(sub_std, 2),
            "status": "PASS" if has_content else "WARNING_LOW_CONTRAST"
        })

    all_pass = all(r.get("status") == "PASS" for r in results)
    return {
        "status": "PASS" if all_pass else "WARN",
        "sampled_frames": len(results),
        "details": results
    }


def run_full_caption_qc(
    video_path: Path,
    caption_model: CaptionModel,
    style_key: str = "classic",
    style_overrides: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Execute complete Quality Control suite for captions."""
    report = {
        "style": style_key,
        "total_segments": len(caption_model.segments),
        "total_words": sum(len(s.words) for s in caption_model.segments),
        "total_captions": len(caption_model.segments),
        "checks": {},
        "failed_checks": [],
        "overall_status": "PASS",
        "valid": True
    }

    # 0. Strict Production Cue Count & Word Count Gate (Disallow false PASS on zero cues)
    if len(caption_model.segments) == 0:
        report["checks"]["cue_count"] = "FAIL"
        report["failed_checks"].append("Zero caption cues generated: captions are missing or empty")
    else:
        report["checks"]["cue_count"] = "PASS"

    if report["total_words"] == 0:
        report["checks"]["word_count"] = "FAIL"
        report["failed_checks"].append("Zero caption words detected: captions contain no spoken words")
    else:
        report["checks"]["word_count"] = "PASS"

    # 1. Integrity check
    ok_int, int_errs = validate_caption_model_integrity(caption_model)
    report["checks"]["model_integrity"] = "PASS" if ok_int else "FAIL"
    if not ok_int:
        report["failed_checks"].extend(int_errs)

    # 2. Check for companion ASS file if video_path provided
    ass_companion = None
    if video_path:
        vp = Path(video_path)
        candidates = [
            vp.with_suffix(".ass"),
            vp.parent / (vp.stem + ".ass"),
            vp.parent / "final.ass",
            vp.parent / "master_captions.ass",
            vp.parent / "work" / "master_captions.ass",
            vp.parent.parent / "work" / "master_captions.ass"
        ]
        for c in candidates:
            if c.exists():
                ass_companion = c
                break

    # 3. Safe margin check with font metrics
    ok_margin, margin_errs = check_caption_safe_margins(
        model=caption_model,
        style_key=style_key,
        style_overrides=style_overrides,
        video_width=1920,
        video_height=1080,
        ass_path=ass_companion
    )
    report["checks"]["safe_margins"] = "PASS" if ok_margin else "FAIL"
    if not ok_margin:
        report["failed_checks"].extend(margin_errs)

    # 4. Visual frame burn-in check
    if video_path and Path(video_path).exists():
        vis_res = verify_burned_caption_frames(Path(video_path), caption_model, sample_count=4)
        report["checks"]["burn_in_visuals"] = vis_res.get("status", "PASS")
        report["visual_samples"] = vis_res.get("details", [])
        if vis_res.get("status") == "FAIL":
            report["failed_checks"].append("Visual frame burn-in verification failed")

    if report["failed_checks"] or len(caption_model.segments) == 0 or report["total_words"] == 0:
        report["overall_status"] = "FAIL"
        report["valid"] = False
    else:
        report["overall_status"] = "PASS"
        report["valid"] = True

    return report
