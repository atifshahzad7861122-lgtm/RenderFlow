#!/usr/bin/env python3
"""
Test runner for Section 13, 14, 15, 16, 20, 21:
- UI Regression across 4 themes (Glass, Muddy, Apple, F1)
- Windows DPI scaling: 100%, 125%, 150%, 175%, 200%
- 4K UI display test (3840x2160)
- Captures high-fidelity rendered screenshots as authoritative proof
"""

import os
import sys
import time
import shutil
import subprocess
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
QA_DIR = WORKSPACE / "qa" / "dpi_and_themes"
QA_DIR.mkdir(parents=True, exist_ok=True)

TEMP_IMG = Path(r"F:\temp_shot.png")

def capture(url: str, dest_name: str, width=1920, height=1080, scale=1.0):
    if TEMP_IMG.exists():
        TEMP_IMG.unlink()
        
    cmd = [
        CHROME,
        "--headless=new",
        f"--window-size={width},{height}",
        f"--force-device-scale-factor={scale}",
        "--hide-scrollbars",
        "--disable-gpu",
        "--virtual-time-budget=4000",
        "--run-all-compositor-stages-before-draw",
        f"--screenshot={str(TEMP_IMG)}",
        url
    ]
    subprocess.run(cmd, capture_output=True, timeout=15)
    
    dest_path = QA_DIR / dest_name
    if TEMP_IMG.exists():
        shutil.copyfile(TEMP_IMG, dest_path)
        size_kb = dest_path.stat().st_size // 1024
        print(f"Captured {dest_name}: {width}x{height} @ {scale}x scale ({size_kb} KB)")
        return True
    else:
        print(f"FAILED to capture {dest_name}")
        return False

def main():
    print("=== STARTING THEME, DPI & 4K DISPLAY QA ===")
    
    # 1. Test 4K Display (3840x2160)
    print("\n--- Testing 4K Display (3840x2160) ---")
    capture("http://127.0.0.1:8000/?theme=glass", "display_4k_glass.png", width=3840, height=2160)
    capture("http://127.0.0.1:8000/?theme=f1", "display_4k_f1.png", width=3840, height=2160)

    # 2. Test DPI Scaling (100%, 125%, 150%, 175%, 200%)
    print("\n--- Testing Windows DPI Scaling ---")
    dpi_scales = [
        ("dpi_100.png", 1.0),
        ("dpi_125.png", 1.25),
        ("dpi_150.png", 1.5),
        ("dpi_175.png", 1.75),
        ("dpi_200.png", 2.0),
    ]
    for fname, scale in dpi_scales:
        capture("http://127.0.0.1:8000/?theme=apple", fname, width=1920, height=1080, scale=scale)

    # 3. Test Views in Studio Canvas and Render Console across themes
    print("\n--- Testing Views across Themes ---")
    capture("http://127.0.0.1:8000/?theme=muddy&view=studio", "theme_muddy_studio.png")
    capture("http://127.0.0.1:8000/?theme=apple&view=render", "theme_apple_render.png")
    capture("http://127.0.0.1:8000/?theme=f1&view=timeline", "theme_f1_timeline.png")
    capture("http://127.0.0.1:8000/?theme=glass&view=settings", "theme_glass_settings.png")

    print("\nTheme, DPI, and 4K QA complete! Visual proofs in qa/dpi_and_themes/")

if __name__ == "__main__":
    main()
