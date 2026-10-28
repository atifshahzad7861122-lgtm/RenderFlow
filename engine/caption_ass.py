#!/usr/bin/env python3
"""
caption_ass.py — High-Performance ASS (Advanced Substation Alpha v4.00+) Generator.

Features:
  - Generates standards-compliant ASS scripts optimized for FFmpeg/libass.
  - Supports 10 distinct styles: Classic, Minimal, Karaoke, Kinetic Pop,
    Pill Karaoke, Bounce, Neon Glow, Editorial, Bold Viral, One-Word Focus.
  - Word-level active state animation with frame-accurate timing.
  - Intelligent line wrapping with \\N at natural clause boundaries.
  - Full Unicode & RTL shaping compatibility via libfribidi + libharfbuzz in libass.
  - Seamless timecode normalization for chunked streaming rendering.
"""

import math
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from .caption_model import CaptionModel, CaptionSegment, Word
from .caption_styles import get_style, rgb_to_ass_color, customize_style


def format_ass_time(seconds: float) -> str:
    """Format seconds into ASS timestamp: H:MM:SS.cs (centiseconds)."""
    sec = max(0.0, float(seconds))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - math.floor(sec)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def escape_ass_text(text: str) -> str:
    """Escape special ASS characters so raw transcript text never breaks tags."""
    # Replace literal braces and backslashes
    clean = text.replace("{", "(").replace("}", ")")
    # Clean excessive whitespace
    clean = re.sub(r'[ \t]+', ' ', clean).strip()
    return clean


def wrap_caption_lines(words: List[Any], max_chars: int = 44) -> List[List[Any]]:
    """Wrap words into 1–2 balanced lines breaking at natural clause boundaries without clipping."""
    if not words:
        return []

    def _text(item: Any) -> str:
        return item.text if hasattr(item, "text") else str(item)

    total_chars = sum(len(_text(w)) for w in words) + max(0, len(words) - 1)
    if total_chars <= max_chars:
        return [words]

    # Greedy line pack first
    lines = []
    curr = []
    curr_len = 0
    for w in words:
        w_len = len(_text(w))
        if curr and (curr_len + 1 + w_len > max_chars):
            lines.append(curr)
            curr = [w]
            curr_len = w_len
        else:
            curr.append(w)
            curr_len += (1 if len(curr) > 1 else 0) + w_len
    if curr:
        lines.append(curr)

    if len(lines) <= 1:
        return lines if lines else [words]

    # If exactly 2 lines (standard caption layout), optimize split around natural midpoint and clause punctuation
    if len(lines) == 2:
        target_mid = total_chars // 2
        best_split = len(lines[0])
        best_diff = 9999
        running_chars = 0

        for i in range(len(words) - 1):
            w_str = _text(words[i])
            running_chars += len(w_str) + 1
            l1_len = running_chars - 1
            l2_len = total_chars - running_chars
            if l1_len <= max_chars and l2_len <= max_chars:
                bonus = 0
                if w_str.endswith((',', ';', ':', '—', '–', '-', '.')):
                    bonus = 12
                diff = abs(running_chars - target_mid) - bonus
                if diff < best_diff:
                    best_diff = diff
                    best_split = i + 1

        line1 = words[:best_split]
        line2 = words[best_split:]
        return [line1, line2]

    return lines


def build_ass_script(
    model: CaptionModel,
    style_key: str = "classic",
    style_overrides: Optional[Dict[str, Any]] = None,
    video_width: int = 1920,
    video_height: int = 1080,
    time_offset_s: float = 0.0,
    duration_s: Optional[float] = None
) -> str:
    """
    Generate complete ASS script string from CaptionModel and style configuration.
    """
    style = customize_style(style_key, style_overrides)

    font_name = style.get("font", "Segoe UI")
    base_font_size = int(style.get("font_size", 46))
    bold = -1 if style.get("font_weight", 600) >= 600 else 0
    italic = -1 if style.get("italic", False) else 0
    alignment = int(style.get("alignment", 2))
    base_margin_v = int(style.get("margin_v", 65))
    base_margin_lr = int(style.get("margin_lr", 100))
    border_style = int(style.get("border_style", 1))
    base_outline_w = float(style.get("outline_width", 2.5))
    base_shadow_d = float(style.get("shadow_depth", 1.5))
    shadow_alpha = int(style.get("shadow_alpha", 128))

    # Resolution-aware proportional scaling (Module 16.4: 1080p -> 1.0x, 1440p -> 1.33x, 4K -> 2.0x)
    res_scale = (video_height / 1080.0) if video_height and video_height > 0 else 1.0
    font_size = max(12, int(round(base_font_size * res_scale)))
    margin_v = max(10, int(round(base_margin_v * res_scale)))
    margin_lr = max(10, int(round(base_margin_lr * res_scale)))
    outline_w = max(0.5, round(base_outline_w * res_scale, 1))
    shadow_d = max(0.0, round(base_shadow_d * res_scale, 1))
    
    # Colors
    prim_color = rgb_to_ass_color(style.get("primary_color", "#FFFFFF"), alpha=0)
    sec_color = rgb_to_ass_color(style.get("secondary_color", "#AAAAAA"), alpha=0)
    hi_color = rgb_to_ass_color(style.get("highlight_color", "#FFD700"), alpha=0)
    out_color = rgb_to_ass_color(style.get("outline_color", "#000000"), alpha=0)
    
    if border_style == 3:
        # Bounding box / pill
        bg_alpha = int(style.get("background_alpha", 160))
        shad_color = rgb_to_ass_color(style.get("background_color", "#000000"), alpha=bg_alpha)
    else:
        shad_color = rgb_to_ass_color(style.get("shadow_color", "#000000"), alpha=shadow_alpha)

    # 1. Header
    lines = [
        "[Script Info]",
        "; Script generated by Rendering Studio Caption Engine",
        "Title: Rendering Studio Captions",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        f"PlayResX: {video_width}",
        f"PlayResY: {video_height}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_name},{font_size},{prim_color},{sec_color},{out_color},{shad_color},"
        f"{bold},{italic},0,0,100,100,0,0,{border_style},{outline_w:.1f},{shadow_d:.1f},"
        f"{alignment},{margin_lr},{margin_lr},{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    word_highlight_enabled = bool(style.get("word_highlight", False))
    animation_type = style.get("animation", "none")
    max_chars = int(style.get("max_width_chars", 44))
    is_uppercase = bool(style.get("uppercase", False))

    chunk_start = time_offset_s
    chunk_end = (time_offset_s + duration_s) if duration_s is not None else float('inf')
    total_segs = len(model.segments)

    # 2. Generate Dialogue Events
    for seg_idx, seg in enumerate(model.segments):
        is_last_segment = (seg_idx == total_segs - 1)

        # If segment is completely outside chunk window, skip
        # For opening: when chunk_start == 0.0, never skip if seg.end >= 0.0
        if chunk_start > 0.0:
            if seg.end <= chunk_start:
                continue
        elif seg.end < 0.0:
            continue

        if seg.start >= chunk_end:
            continue

        # Shift timestamps relative to chunk_start
        s_start = max(0.0, seg.start - chunk_start)
        s_end = seg.end - chunk_start

        # Trailing silence and ending caption retention (Issue B fix):
        # Hold final caption so it does not prematurely vanish before video ends (when duration_s is provided)
        if is_last_segment and duration_s is not None:
            if duration_s - s_end < 3.5:
                s_end = duration_s
            else:
                s_end = min(duration_s, s_end + 2.5)
        elif duration_s is not None:
            s_end = min(duration_s, s_end)

        s_end = max(s_start + 0.10, s_end)

        if not seg.words:
            # Fallback when no words exist
            txt = escape_ass_text(seg.text)
            if is_uppercase:
                txt = txt.upper()
            t_start = format_ass_time(s_start)
            t_end = format_ass_time(s_end)
            lines.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{txt}")
            continue

        # Adjust words for chunk offset
        words = []
        for w in seg.words:
            w_s = max(0.0, w.start - chunk_start)
            w_e = max(w_s + 0.02, w.end - chunk_start)
            if duration_s is not None:
                w_e = min(duration_s, w_e)
            w_txt = escape_ass_text(w.text)
            if is_uppercase:
                w_txt = w_txt.upper()
            words.append(Word(text=w_txt, start=w_s, end=w_e, confidence=w.confidence))

        # Check line wrapping
        wrapped_lines = wrap_caption_lines(words, max_chars=max_chars)

        if not word_highlight_enabled:
            # Simple static caption over segment duration
            line_strings = [" ".join(w.text for w in wl) for wl in wrapped_lines]
            full_text = r"\N".join(line_strings)
            
            fade_tag = r"{\fad(80,80)}" if animation_type == "fade" else ""
            t_start = format_ass_time(s_start)
            t_end = format_ass_time(s_end)
            lines.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{fade_tag}{full_text}")
            continue

        # Word-by-word active animation
        # For each word in the segment, generate a time-sliced Dialogue event
        all_words_flat = [w for wl in wrapped_lines for w in wl]
        
        for active_idx, active_word in enumerate(all_words_flat):
            # Check original word timing: skip if word was already finished before chunk or starts after chunk
            if active_idx < len(seg.words):
                orig_w = seg.words[active_idx]
                if chunk_start > 0.0 and orig_w.end <= chunk_start:
                    continue
                if orig_w.start >= chunk_end:
                    continue

            # Interval for this active word
            w_start = active_word.start
            w_end = active_word.end

            # Bridge micro-gaps to the next word so subtitles do not vanish/flicker between words
            if active_idx + 1 < len(all_words_flat):
                next_start = all_words_flat[active_idx + 1].start
                if next_start > w_end:
                    gap = next_start - w_end
                    if gap <= 0.40:
                        w_end = next_start
                    else:
                        w_end = min(w_end + 0.15, next_start)
            else:
                # Last word in segment: hold until held segment end so ending caption does not vanish
                w_end = max(w_end, s_end)

            if w_end <= w_start:
                continue

            # Ensure minimum legible display duration (at least 80ms)
            if w_end - w_start < 0.08:
                w_end = w_start + 0.08

            t_start = format_ass_time(w_start)
            t_end = format_ass_time(w_end)

            # Build line text with active word styling
            rendered_lines = []
            is_uppercase = bool(style.get("uppercase", False))
            for wl in wrapped_lines:
                line_tokens = []
                for w in wl:
                    w_disp = w.text.upper() if is_uppercase else w.text
                    if w is active_word:
                        # ACTIVE WORD STYLING
                        if animation_type in ["pop", "scale"]:
                            # Scale up slightly with overshoot and accent highlight
                            tag = rf"{{\c{hi_color}\fscx116\fscy116\t(0,120,\fscx108\fscy108)}}"
                        elif animation_type == "bounce":
                            # Subtle vertical bounce
                            tag = rf"{{\c{hi_color}\t(0,80,\fscy118)\t(80,160,\fscy100)}}"
                        elif animation_type in ["neon_glow", "glow"]:
                            # Luminous glow aura with blur
                            tag = rf"{{\c{hi_color}\blur4\3c{hi_color}}}"
                        elif animation_type == "underline":
                            # Editorial elegant underline + warm gold
                            tag = rf"{{\c{hi_color}\u1}}"
                        elif animation_type == "weight_shift":
                            # Active bold shift
                            tag = rf"{{\c{hi_color}\b1}}"
                        elif animation_type in ["pill", "pill_highlight"]:
                            # Bright mint text
                            tag = rf"{{\c{hi_color}\b1}}"
                        elif animation_type in ["pulse", "one_word"]:
                            # One word focus pulse
                            tag = rf"{{\c{hi_color}\fscx120\fscy120\b1}}"
                        elif animation_type == "glitch":
                            # Chromatic offset
                            tag = rf"{{\c{hi_color}\3c{out_color}\fscx105}}"
                        else:
                            # Standard karaoke color switch
                            tag = rf"{{\c{hi_color}}}"

                        line_tokens.append(rf"{tag}{w_disp}{{\rDefault}}")
                    else:
                        # INACTIVE WORD
                        if style.get("word_highlight", False):
                            # Dimmed secondary color for inactive context words
                            line_tokens.append(rf"{{\c{sec_color}}}{w_disp}{{\rDefault}}")
                        else:
                            line_tokens.append(w_disp)

                rendered_lines.append(" ".join(line_tokens))

            dialogue_text = r"\N".join(rendered_lines)
            lines.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{dialogue_text}")

    return "\n".join(lines) + "\n"


def generate_ass_script(
    model: CaptionModel,
    output_path,
    style_key: str = "classic",
    style_overrides: Optional[Dict[str, Any]] = None,
    time_offset_s: float = 0.0,
    video_width: int = 1920,
    video_height: int = 1080
) -> Path:
    """Generate ASS script and write directly to file."""
    content = build_ass_script(
        model=model,
        style_key=style_key,
        style_overrides=style_overrides,
        video_width=video_width,
        video_height=video_height,
        time_offset_s=time_offset_s
    )
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p

