#!/usr/bin/env python3
"""
caption_export.py — Exporters for SRT, ASS, WebVTT (.vtt), and Metadata-Preserving JSON Captions.
"""

from pathlib import Path
from typing import Optional, Dict, Any, List
import math
import json

from .caption_model import CaptionModel
from .caption_ass import build_ass_script


def format_srt_time(seconds: float) -> str:
    """Format seconds into standard SRT timestamp: HH:MM:SS,mmm"""
    sec = max(0.0, float(seconds))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - math.floor(sec)) * 1000))
    if ms >= 1000:
        ms = 999
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_vtt_time(seconds: float) -> str:
    """Format seconds into standard WebVTT timestamp: HH:MM:SS.mmm"""
    sec = max(0.0, float(seconds))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - math.floor(sec)) * 1000))
    if ms >= 1000:
        ms = 999
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def export_srt(model: CaptionModel, output_path: Path) -> Path:
    """Export CaptionModel as standard UTF-8 SRT file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    lines = []
    for idx, seg in enumerate(model.segments):
        t_start = format_srt_time(seg.start)
        t_end = format_srt_time(seg.end)
        txt = seg.text.strip()
        lines.append(f"{idx + 1}")
        lines.append(f"{t_start} --> {t_end}")
        lines.append(txt)
        lines.append("")

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def export_vtt(model: CaptionModel, output_path: Path) -> Path:
    """Export CaptionModel as standard WebVTT (.vtt) file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["WEBVTT", ""]
    for idx, seg in enumerate(model.segments):
        t_start = format_vtt_time(seg.start)
        t_end = format_vtt_time(seg.end)
        txt = seg.text.strip()
        lines.append(f"{idx + 1}")
        lines.append(f"{t_start} --> {t_end}")
        lines.append(txt)
        lines.append("")

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def export_ass(
    model: CaptionModel,
    output_path: Path,
    style_key: str = "classic",
    style_overrides: Optional[Dict[str, Any]] = None,
    video_width: int = 1920,
    video_height: int = 1080
) -> Path:
    """Export CaptionModel as Advanced Substation Alpha (.ass) file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ass_content = build_ass_script(
        model=model,
        style_key=style_key,
        style_overrides=style_overrides,
        video_width=video_width,
        video_height=video_height
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_content)
    return output_path


def export_json(
    model: CaptionModel,
    output_path: Path,
    metadata: Optional[Dict[str, Any]] = None
) -> Path:
    """
    Export CaptionModel as rich metadata JSON preserving source timing,
    words, emphasis, style, language, provider, and model versions.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    meta = metadata or {}
    export_payload = {
        "version": "2.1",
        "language": model.language,
        "style": meta.get("style", "classic"),
        "stt_provider": meta.get("stt_provider", "local_whisper"),
        "llm_provider": meta.get("llm_provider", "none"),
        "llm_model": meta.get("llm_model", "none"),
        "total_segments": len(model.segments),
        "total_duration_s": model.total_duration,
        "segments": [s.to_dict() for s in model.segments]
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_payload, f, indent=2, ensure_ascii=False)
    return output_path


def export_all_caption_formats(
    model: CaptionModel,
    base_output_path: Optional[Path] = None,
    out_video_path: Optional[Path] = None,
    style_key: str = "classic",
    style_overrides: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    video_width: int = 1920,
    video_height: int = 1080,
    width: Optional[int] = None,
    height: Optional[int] = None
) -> Dict[str, Path]:
    """Export SRT, ASS, VTT, and rich JSON in one call."""
    target = base_output_path or out_video_path
    if not target:
        raise ValueError("Either base_output_path or out_video_path must be provided.")
    base = Path(target)
    if base.suffix in [".srt", ".ass", ".vtt", ".json", ".mp4", ".mov", ".mkv"]:
        base = base.with_suffix("")
    
    eff_w = width if width is not None else video_width
    eff_h = height if height is not None else video_height
    
    srt_p = export_srt(model, Path(str(base) + ".srt"))
    ass_p = export_ass(
        model,
        Path(str(base) + ".ass"),
        style_key=style_key,
        style_overrides=style_overrides,
        video_width=video_width,
        video_height=video_height
    )
    vtt_p = export_vtt(model, Path(str(base) + ".vtt"))
    json_p = export_json(model, Path(str(base) + ".json"), metadata=metadata)
    
    return {
        "srt": srt_p,
        "ass": ass_p,
        "vtt": vtt_p,
        "json": json_p
    }
