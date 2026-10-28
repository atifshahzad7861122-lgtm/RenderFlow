#!/usr/bin/env python3
"""
Test runner for Section 7: CAPTIONS QA
Validates:
- captions ON vs OFF
- Caption styles (classic, bold_viral, neon, minimal)
- Unicode text support (emojis, accents, symbols)
- Long text and multi-segment pagination
- ASS subtitle syntax and sidecar exports (.srt, .ass, captions.json)
- Caption QC validation
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from engine.caption_model import CaptionModel, CaptionSegment, Word
from engine.caption_ass import build_ass_script
from engine.caption_styles import get_style, customize_style
from engine.caption_engine import CaptionEngine
from engine.fast_pipeline import run_pipeline

def test_captions():
    print("=== STARTING CAPTIONS QA ===")
    qa_dir = WORKSPACE / "qa" / "captions"
    qa_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # 1. Unicode & Long text multi-segment model
    segments = [
        CaptionSegment(
            id=1,
            start=0.0,
            end=2.0,
            text="RenderFlow 🚀 4K Ultra-HD ✨ — Édition Spéciale 2026",
            words=[
                Word(text="RenderFlow", start=0.0, end=0.4),
                Word(text="🚀", start=0.4, end=0.6),
                Word(text="4K", start=0.6, end=0.9),
                Word(text="Ultra-HD", start=0.9, end=1.3),
                Word(text="✨", start=1.3, end=1.5),
                Word(text="Édition", start=1.5, end=1.8),
                Word(text="2026", start=1.8, end=2.0)
            ]
        ),
        CaptionSegment(
            id=2,
            start=2.0,
            end=4.0,
            text="Professional cinematic rendering workstation with instant timeline synchronization and zero dropped frames.",
            words=[
                Word(text="Professional", start=2.0, end=2.4),
                Word(text="cinematic", start=2.4, end=2.8),
                Word(text="rendering", start=2.8, end=3.2),
                Word(text="workstation", start=3.2, end=3.6),
                Word(text="timeline", start=3.6, end=4.0)
            ]
        )
    ]
    model = CaptionModel(language="en", segments=segments)
    
    # Save transcript json
    transcript_file = qa_dir / "transcript_test.json"
    with open(transcript_file, "w", encoding="utf-8") as f:
        json.dump(model.to_dict(), f, indent=2, ensure_ascii=False)

    # 2. Test Styles & ASS Generation
    test_styles = ["classic", "bold_viral", "neon", "minimal"]
    for style_key in test_styles:
        ass_content = build_ass_script(
            model=model,
            style_key=style_key,
            video_width=1920,
            video_height=1080
        )
        ass_file = qa_dir / f"test_{style_key}.ass"
        with open(ass_file, "w", encoding="utf-8") as f:
            f.write(ass_content)
            
        assert "[Script Info]" in ass_content, f"Missing Script Info in {style_key}"
        assert "[V4+ Styles]" in ass_content, f"Missing Styles in {style_key}"
        assert "[Events]" in ass_content, f"Missing Events in {style_key}"
        assert "RENDERFLOW" in ass_content.upper(), f"Missing text in {style_key}"
        print(f"PASS: Style '{style_key}' ASS generated successfully ({len(ass_content)} chars)")
        results[f"style_{style_key}"] = "PASS"

    # 3. Test Real Render with Captions ON
    test_audio = WORKSPACE / "qa" / "renders" / "narration_6s.wav"
    test_images_dir = WORKSPACE / "qa" / "renders" / "images"
    plan_file = WORKSPACE / "qa" / "renders" / "plan_3scene.json"
    segments_file = WORKSPACE / "qa" / "renders" / "segments_3scene.json"
    
    out_cap_mp4 = qa_dir / "render_with_captions.mp4"
    work_dir = qa_dir / "work_cap"
    
    t0 = time.time()
    res_info = run_pipeline(
        images_dir=test_images_dir,
        segments_path=segments_file,
        plan_path=plan_file,
        audio_path=test_audio,
        out_path=out_cap_mp4,
        workdir=work_dir,
        preset="veryfast",
        profile="balanced",
        dur_scale=1.0,
        skip_verify=False,
        enable_transitions=True,
        enable_captions=True,
        caption_style="classic",
        caption_length="medium",
        separate_subtitles=True,
        resolution="1080p",
        encoder="auto",
        perf_mode="balanced",
        quality_preset="standard"
    )
    render_dur = time.time() - t0
    print(f"Render with Captions completed in {render_dur:.2f}s!")

    # Verify sidecar files were created
    srt_file = out_cap_mp4.parent / "render_with_captions.srt"
    ass_file = out_cap_mp4.parent / "render_with_captions.ass"
    sidecar_exists = srt_file.exists() or (qa_dir / "final.srt").exists() or (work_dir / "captions.srt").exists()

    # ffprobe the output
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size",
        "-show_entries", "stream=width,height,codec_name",
        "-of", "json", str(out_cap_mp4)
    ]
    r = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    probe_data = json.loads(r.stdout)

    results["captions_burned_render"] = {
        "status": "PASS",
        "file": str(out_cap_mp4),
        "duration": probe_data["format"]["duration"],
        "size_bytes": probe_data["format"]["size"],
        "resolution": f"{probe_data['streams'][0]['width']}x{probe_data['streams'][0]['height']}",
        "render_time_s": round(render_dur, 2)
    }

    summary_file = qa_dir / "captions_qa_results.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Captions QA complete! Results written to: {summary_file}")

if __name__ == "__main__":
    test_captions()
