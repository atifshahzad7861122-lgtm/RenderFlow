#!/usr/bin/env python3
"""
Rendering Studio Engine v2 — Centralized Render Profiles Configuration.

Defines standardized presets for:
- Resolution profiles (1080p Full HD, 1440p QHD / 2K, 4K UHD)
- Hardware-adaptive performance profiles (Eco, Balanced, Performance, Max Quality)
- Encoder-specific quality/speed parameter mappings
- Adaptive chunking & memory limits
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# --- 1. RESOLUTION PRESETS ---
RESOLUTION_PROFILES: Dict[str, Dict[str, Any]] = {
    "1080p": {
        "name": "1080p Full HD",
        "description": "Standard high-definition output. Fast encoding, highly compatible.",
        "width": 1920,
        "height": 1080,
        "aspect_ratio": "16:9",
        "scale_factor": 1.0,
        "caption_font_scale": 1.0,
        "default_chunk_size": 35,
        "crf_default": 20,
        "target_bitrate": "8M",
        "max_bitrate": "12M",
        "bufsize": "16M",
        "estimated_ram_mb": 150,
        "recommended_hardware": "Any modern PC (2+ cores, 4+ GB RAM)"
    },
    "1440p": {
        "name": "1440p QHD / 2K",
        "description": "Crisp 2.5K high quality. Great for high-DPI monitors and YouTube VP9 unlock.",
        "width": 2560,
        "height": 1440,
        "aspect_ratio": "16:9",
        "scale_factor": 1.3333,
        "caption_font_scale": 1.3333,
        "default_chunk_size": 28,
        "crf_default": 19,
        "target_bitrate": "16M",
        "max_bitrate": "24M",
        "bufsize": "32M",
        "estimated_ram_mb": 250,
        "recommended_hardware": "Mid-range PC (4+ cores, 8+ GB RAM)"
    },
    "4k": {
        "name": "4K UHD Maximum Quality",
        "description": "Ultra-High Definition 3840x2160. Maximum cinematic clarity and fidelity.",
        "width": 3840,
        "height": 2160,
        "aspect_ratio": "16:9",
        "scale_factor": 2.0,
        "caption_font_scale": 2.0,
        "default_chunk_size": 20,
        "crf_default": 18,
        "target_bitrate": "35M",
        "max_bitrate": "50M",
        "bufsize": "70M",
        "estimated_ram_mb": 450,
        "recommended_hardware": "High-end PC (6+ cores, 16+ GB RAM or dedicated GPU)"
    }
}

# Aliases
RESOLUTION_ALIASES = {
    "1920x1080": "1080p",
    "fhd": "1080p",
    "2560x1440": "1440p",
    "2k": "1440p",
    "qhd": "1440p",
    "3840x2160": "4k",
    "uhd": "4k",
    "4k_uhd": "4k"
}

# --- 2. PERFORMANCE MODES ---
PERFORMANCE_MODES: Dict[str, Dict[str, Any]] = {
    "auto": {
        "name": "Auto (Recommended)",
        "description": "Automatically adapts encoder, chunk size, and thread count to host hardware."
    },
    "eco": {
        "name": "Eco / Low-End",
        "description": "Optimized for laptops, dual-core CPUs, and 8GB RAM. Bounded memory and lower thread utilization.",
        "chunk_multiplier": 0.7,
        "threads": 2,
        "preset": "veryfast"
    },
    "balanced": {
        "name": "Balanced",
        "description": "Optimal balance between encoding speed and compression quality.",
        "chunk_multiplier": 1.0,
        "threads": 0,  # auto
        "preset": "veryfast"
    },
    "performance": {
        "name": "Performance",
        "description": "Throughput-oriented pipeline utilizing verified hardware encoder and parallel chunking.",
        "chunk_multiplier": 1.3,
        "threads": 0,
        "preset": "fast"
    },
    "max_quality": {
        "name": "Max Quality",
        "description": "Maximum visual fidelity, highest Lanczos filter precision, lower CRF compression.",
        "chunk_multiplier": 0.9,
        "threads": 0,
        "preset": "medium"
    }
}

# --- 3. QUALITY LEVELS ---
QUALITY_LEVELS: Dict[str, Dict[str, Any]] = {
    "standard": {
        "libx264_crf": 20,
        "nvenc_cq": 23,
        "qsv_gq": 23,
        "amf_qp": 23,
        "bitrate_scale": 1.0
    },
    "high": {
        "libx264_crf": 18,
        "nvenc_cq": 19,
        "qsv_gq": 19,
        "amf_qp": 19,
        "bitrate_scale": 1.25
    },
    "maximum": {
        "libx264_crf": 16,
        "nvenc_cq": 16,
        "qsv_gq": 16,
        "amf_qp": 16,
        "bitrate_scale": 1.6
    }
}


def normalize_resolution_key(res: str) -> str:
    """Normalize input resolution string to canonical key ('1080p', '1440p', '4k')."""
    if not res:
        return "1080p"
    clean = str(res).strip().lower()
    if clean in RESOLUTION_PROFILES:
        return clean
    if clean in RESOLUTION_ALIASES:
        return RESOLUTION_ALIASES[clean]
    # Check for direct dimensions like 3840x2160
    if "3840" in clean or "2160" in clean or "4k" in clean:
        return "4k"
    if "2560" in clean or "1440" in clean or "2k" in clean:
        return "1440p"
    return "1080p"


def get_resolution_profile(res_key: str = "1080p") -> Dict[str, Any]:
    """Retrieve resolution profile dictionary for given key."""
    canonical = normalize_resolution_key(res_key)
    return RESOLUTION_PROFILES[canonical]


def get_adaptive_chunk_size(
    resolution_key: str = "1080p",
    performance_mode: str = "balanced",
    custom_chunk: Optional[int] = None,
    total_ram_gb: float = 8.0
) -> int:
    """
    Compute safe, hardware-aware chunk size (scene count per chunk).
    Ensures memory safety regardless of resolution (1080p, 1440p, or 4K).
    """
    if custom_chunk and custom_chunk > 0:
        return custom_chunk

    res_prof = get_resolution_profile(resolution_key)
    base_chunk = res_prof["default_chunk_size"]

    mode_info = PERFORMANCE_MODES.get(performance_mode, PERFORMANCE_MODES["balanced"])
    multiplier = mode_info.get("chunk_multiplier", 1.0)

    # Scale down chunk size if RAM is constrained (<8 GB) on high resolutions or integrated GPUs
    if total_ram_gb < 8.0:
        if resolution_key == "4k":
            multiplier = min(multiplier, 0.6)
        elif resolution_key == "1440p":
            multiplier = min(multiplier, 0.8)
        else:
            multiplier = min(multiplier, 0.85)

    chunk = int(round(base_chunk * multiplier))
    # Safe bounds: minimum 10 scenes, maximum 60 scenes
    return max(10, min(60, chunk))


def get_encoder_args(
    encoder: str = "libx264",
    quality: str = "standard",
    preset: str = "veryfast",
    resolution_key: str = "1080p",
    threads: int = 0
) -> List[str]:
    """
    Construct safe, encoder-specific FFmpeg encoding parameter list.
    Supports: libx264, h264_nvenc, h264_qsv, h264_amf, h264_mf.
    """
    res_prof = get_resolution_profile(resolution_key)
    q_info = QUALITY_LEVELS.get(quality, QUALITY_LEVELS["standard"])

    enc = encoder.lower()

    if enc == "h264_nvenc":
        cq = q_info["nvenc_cq"]
        p_map = {"ultrafast": "p1", "superfast": "p2", "veryfast": "p3", "fast": "p4", "medium": "p5"}
        nv_preset = p_map.get(preset, "p4")
        args = [
            "-c:v", "h264_nvenc",
            "-preset", nv_preset,
            "-rc", "vbr",
            "-cq", str(cq),
            "-b:v", res_prof["target_bitrate"],
            "-maxrate", res_prof["max_bitrate"],
            "-bufsize", res_prof["bufsize"],
            "-pix_fmt", "yuv420p"
        ]
    elif enc == "h264_qsv":
        gq = q_info["qsv_gq"]
        args = [
            "-c:v", "h264_qsv",
            "-global_quality", str(gq),
            "-b:v", res_prof["target_bitrate"],
            "-maxrate", res_prof["max_bitrate"],
            "-bufsize", res_prof["bufsize"],
            "-pix_fmt", "nv12"  # QSV native format; will be converted if needed
        ]
    elif enc == "h264_amf":
        qp = q_info["amf_qp"]
        args = [
            "-c:v", "h264_amf",
            "-rc", "cqp",
            "-qp_i", str(qp),
            "-qp_p", str(qp + 2),
            "-pix_fmt", "yuv420p"
        ]
    elif enc == "h264_mf":
        # Windows Media Foundation H.264
        # Use quality-based rate control to prevent macroblock starvation on static slides
        q_val = 96 if quality == "maximum" else (94 if quality == "high" else 90)
        args = [
            "-c:v", "h264_mf",
            "-rate_control", "quality",
            "-quality", str(q_val),
            "-pix_fmt", "yuv420p"
        ]
    else:
        # Default: software libx264
        crf = q_info["libx264_crf"]
        args = [
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", str(crf),
            "-profile:v", "high",
            "-pix_fmt", "yuv420p"
        ]

    if threads > 0 and enc == "libx264":
        args += ["-threads", str(threads)]

    return args


def export_profiles_json(output_path: Optional[Path] = None) -> Path:
    """Export profiles to JSON configuration file."""
    if output_path is None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        output_path = CONFIG_DIR / "render_profiles.json"
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": "2.2.0",
        "resolutions": RESOLUTION_PROFILES,
        "performance_modes": PERFORMANCE_MODES,
        "quality_levels": QUALITY_LEVELS
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return output_path


# Auto-export JSON configuration on module import if config directory exists
try:
    export_profiles_json()
except Exception:
    pass


if __name__ == "__main__":
    out_file = export_profiles_json()
    print(f"Render profiles exported successfully to: {out_file}")
    for k, v in RESOLUTION_PROFILES.items():
        print(f"- {k.upper()}: {v['width']}x{v['height']} | Scale {v['scale_factor']}x | Default Chunk {v['default_chunk_size']}")
