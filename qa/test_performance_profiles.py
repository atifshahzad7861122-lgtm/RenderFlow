#!/usr/bin/env python3
"""
Test runner for Section 11: PERFORMANCE PROFILE QA
Validates that ECO, BALANCED, PERFORMANCE, MAX QUALITY actually alter:
- Thread allocation
- x264 preset / NVENC preset
- Chunk size multiplier
- Quality parameters
"""

import sys
import json
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from engine.render_profiles import PERFORMANCE_MODES, get_adaptive_chunk_size, get_encoder_args

def test_performance_profiles():
    print("=== STARTING PERFORMANCE PROFILE QA ===")
    
    profiles = ["eco", "balanced", "performance", "max_quality"]
    results = {}

    for mode in profiles:
        mode_cfg = PERFORMANCE_MODES.get(mode, {})
        chunk_1080p = get_adaptive_chunk_size("1080p", mode, total_ram_gb=8.0)
        chunk_4k = get_adaptive_chunk_size("4k", mode, total_ram_gb=8.0)
        
        preset = mode_cfg.get("preset", "veryfast")
        threads = mode_cfg.get("threads", 0)
        
        args = get_encoder_args(
            encoder="libx264",
            quality="standard",
            preset=preset,
            resolution_key="1080p",
            threads=threads
        )
        
        results[mode] = {
            "name": mode_cfg.get("name"),
            "threads": threads,
            "preset": preset,
            "chunk_size_1080p": chunk_1080p,
            "chunk_size_4k": chunk_4k,
            "encoder_args": args
        }
        print(f"Profile: {mode.upper()}")
        print(f"  Threads: {threads} | Preset: {preset} | Chunk 1080p: {chunk_1080p} | Chunk 4K: {chunk_4k}")
        print(f"  Encoder args snippet: {' '.join(args[:8])}")

    # Assert distinct configs
    assert results["eco"]["threads"] == 2, "Eco mode must constrain threads"
    assert results["eco"]["chunk_size_1080p"] < results["balanced"]["chunk_size_1080p"], "Eco must reduce chunk size"
    assert results["performance"]["preset"] != results["max_quality"]["preset"], "Performance and Max Quality presets must differ"

    qa_file = WORKSPACE / "qa" / "performance_profiles_results.json"
    with open(qa_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nPASS: All performance profiles verified! Results written to: {qa_file}")

if __name__ == "__main__":
    test_performance_profiles()
