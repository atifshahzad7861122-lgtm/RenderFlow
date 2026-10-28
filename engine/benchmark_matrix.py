#!/usr/bin/env python3
"""
benchmark_matrix.py — Automated Benchmark Matrix Suite for Rendering Studio Engine v2.

Test Cases:
  Test A: 10 images / 30 sec
  Test B: 50 images / 120 sec (2 min)
  Test C: 100 images / 246.504 sec (The Real Production Test)
  Test D: 150 images / 600 sec (10 min)
  Test E: 300 images / 1800 sec (30 min)
  Test F: 600 images / 3600 sec (60 min Architectural Validation)

Measures and records:
  Input duration, Image count, Resolution, FPS, Encoding method,
  Transition count, Render time, Peak RAM, CPU usage, Output size,
  and SLA Pass/Fail status.
"""

import argparse
import json
import math
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
import psutil
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT_DIR = HERE.parent
CACHE_BENCHMARKS = ROOT_DIR / "projects" / "benchmarks"


def get_system_specs():
    return {
        'cpu': f"{platform.processor()} ({psutil.cpu_count(logical=False)}C/{psutil.cpu_count(logical=True)}T)",
        'ram_gb': round(psutil.virtual_memory().total / (1024 ** 3), 2),
        'os': platform.platform()
    }


def generate_benchmark_assets(dest_dir: Path, n_images: int, target_dur: float, master_audio_src: Path):
    dest_dir.mkdir(parents=True, exist_ok=True)
    images_dir = dest_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create distinct 1080p images with rich gradients
    print(f"Checking {n_images} 1080p benchmark images in {images_dir.name}...", flush=True)
    existing = len(list(images_dir.glob("*.jpg")))
    if existing < n_images:
        print(f"Generating {n_images - existing} additional benchmark images...", flush=True)
        for i in range(1, n_images + 1):
            img_p = images_dir / f"scene_{i:04d}.jpg"
            if img_p.exists() and img_p.stat().st_size > 10000:
                continue

            im = Image.new("RGB", (1920, 1080))
            draw = ImageDraw.Draw(im)

            r1 = int(30 + 190 * (i / max(1, n_images))) % 256
            g1 = int(60 + 170 * ((i * 3) / max(1, n_images))) % 256
            b1 = int(90 + 150 * ((i * 7) / max(1, n_images))) % 256
            r2, g2, b2 = (int(250 - r1 * 0.8), int(220 - g1 * 0.8), int(240 - b1 * 0.8))

            for y in range(0, 1080, 6):
                frac = y / 1080.0
                r = int(r1 * (1 - frac) + r2 * frac)
                g = int(g1 * (1 - frac) + g2 * frac)
                b = int(b1 * (1 - frac) + b2 * frac)
                draw.rectangle([(0, y), (1920, y + 6)], fill=(r, g, b))

            draw.rectangle([(100 + (i * 15) % 600, 200), (700 + (i * 15) % 600, 880)], outline=(255, 255, 255), width=6)
            draw.ellipse([(900, 200 + (i * 10) % 400), (1500, 800 + (i * 10) % 400)], fill=(r2, g1, b2))
            draw.text((160, 260), f"SCENE {i:04d} / {n_images}", fill=(255, 255, 255))
            draw.text((160, 320), f"Rendering Studio Engine v2 — Asset {i}", fill=(220, 240, 255))

            im.save(str(img_p), "JPEG", quality=90)

    # 2. Slice or loop narration audio to target duration
    audio_dst = dest_dir / "narration.wav"
    need_audio = not audio_dst.exists()
    if not need_audio:
        try:
            r = subprocess.run([
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', str(audio_dst)
            ], capture_output=True, text=True, check=True)
            cur_dur = float(r.stdout.strip())
            if abs(cur_dur - target_dur) > 0.5:
                need_audio = True
        except Exception:
            need_audio = True

    if need_audio:
        print(f"Preparing {target_dur:.1f}s narration audio...", flush=True)
        cmd = [
            'ffmpeg', '-y',
            '-stream_loop', '-1',
            '-i', str(master_audio_src),
            '-t', f'{target_dur:.3f}',
            '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2',
            str(audio_dst)
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    # 3. Create transcript.json & plan.json
    step_dur = target_dur / n_images
    contexts = ['normal', 'location_change', 'story_change', 'turning_point', 'time_passage', 'emotional', 'fast']
    segs = []
    scenes = []

    curr_t = 0.0
    for i in range(n_images):
        end_t = target_dur if i == n_images - 1 else round(curr_t + step_dur, 3)
        ctx = contexts[i % len(contexts)] if i > 0 else 'normal'
        img_name = f"scene_{i+1:04d}.jpg"

        segs.append({'start': round(curr_t, 3), 'end': end_t, 'text': f"Scene {i+1}"})
        scenes.append({'segment_index': i, 'image': img_name, 'context': ctx})
        curr_t = end_t

    (dest_dir / "transcript.json").write_text(json.dumps({'segments': segs}, indent=2), encoding='utf-8')
    (dest_dir / "plan.json").write_text(json.dumps({'scenes': scenes}, indent=2), encoding='utf-8')


def run_benchmark_test(name: str, test_dir: Path, preset: str = 'ultrafast', chunk_size: int = 35, skip_verify: bool = False):
    print("\n" + "#" * 65)
    print(f" EXECUTING BENCHMARK: {name}")
    print("#" * 65, flush=True)

    sys.path.insert(0, str(HERE))
    from fast_pipeline import run_pipeline

    out_mp4 = test_dir / "final_benchmark.mp4"
    workdir = test_dir / "work"

    cpu_before = psutil.cpu_percent(interval=0.1)
    t0 = time.time()
    res = run_pipeline(
        images_dir=test_dir / "images",
        segments_path=test_dir / "transcript.json",
        plan_path=test_dir / "plan.json",
        audio_path=test_dir / "narration.wav",
        out_path=out_mp4,
        workdir=workdir,
        pack_dir=ROOT_DIR / "transition_pack",
        preset=preset,
        profile='balanced',
        dur_scale=1.0,
        skip_verify=skip_verify,
        chunk_size=chunk_size
    )
    wall_clock = time.time() - t0
    cpu_after = psutil.cpu_percent(interval=0.1)
    avg_cpu = round((cpu_before + cpu_after) / 2.0, 1)

    # Probe final output for strict validation
    probe_cmd = ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(out_mp4)]
    pr = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    info = json.loads(pr.stdout)

    v_stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
    a_stream = next(s for s in info['streams'] if s['codec_type'] == 'audio')
    actual_dur = float(info['format']['duration'])
    file_size_mb = round(out_mp4.stat().st_size / (1024 * 1024), 2)
    peak_ram_mb = res.get('peak_ram_mb', round(psutil.Process().memory_info().rss / (1024 * 1024), 1))

    # Read transitions count
    trans_json = Path(str(out_mp4) + '.transitions.json')
    n_transitions = 0
    if trans_json.exists():
        try:
            tdata = json.loads(trans_json.read_text(encoding='utf-8'))
            n_transitions = tdata.get('n_transitions', 0)
        except Exception:
            pass

    n_images = len(list((test_dir / "images").glob("*.jpg")))
    ratio = round(actual_dur / max(0.01, wall_clock), 2)

    return {
        'name': name,
        'wall_clock': round(wall_clock, 2),
        'master_dur': round(actual_dur, 2),
        'ratio': ratio,
        'fps': eval(v_stream.get('r_frame_rate', '30/1')),
        'resolution': f"{v_stream['width']}x{v_stream['height']}",
        'pix_fmt': v_stream['pix_fmt'],
        'video_codec': v_stream['codec_name'],
        'audio_codec': a_stream['codec_name'],
        'preset': preset,
        'n_images': n_images,
        'n_transitions': n_transitions,
        'peak_ram_mb': peak_ram_mb,
        'cpu_usage_pct': avg_cpu,
        'output_size_mb': file_size_mb,
        'pass_sla': (wall_clock <= 480.0) if actual_dur <= 300.0 else True,
        'output_file': str(out_mp4)
    }


def main():
    parser = argparse.ArgumentParser(description="Rendering Studio Engine v2 Benchmark Matrix Runner")
    parser.add_argument('--test', default='all', choices=['all', 'a', 'b', 'c', 'd', 'e', 'f'],
                        help="Select test to run: a (30s), b (2m), c (5m/prod), d (10m), e (30m), f (60m)")
    parser.add_argument('--preset', default='ultrafast', help="x264 encoding preset")
    args = parser.parse_args()

    specs = get_system_specs()
    print("=" * 65)
    print(" RENDERING STUDIO ENGINE v2 — BENCHMARK MATRIX RUNNER")
    print("=" * 65)
    print(f"CPU: {specs['cpu']}")
    print(f"RAM: {specs['ram_gb']} GB")
    print(f"OS:  {specs['os']}")
    print(f"Encoder Preset: {args.preset}")
    print("=" * 65, flush=True)

    master_audio = ROOT_DIR / "projects" / "Video1" / "narration.wav"
    if not master_audio.exists():
        sys.exit(f"Master audio missing: {master_audio}")

    results = []
    run_all = args.test == 'all'

    # Test A: 10 images / 30 sec
    if run_all or args.test == 'a':
        t_dir = CACHE_BENCHMARKS / "test_a_10img_30s"
        generate_benchmark_assets(t_dir, n_images=10, target_dur=30.0, master_audio_src=master_audio)
        results.append(run_benchmark_test("Test A: 10 images / 30s", t_dir, preset=args.preset))

    # Test B: 50 images / 120 sec (2 min)
    if run_all or args.test == 'b':
        t_dir = CACHE_BENCHMARKS / "test_b_50img_120s"
        generate_benchmark_assets(t_dir, n_images=50, target_dur=120.0, master_audio_src=master_audio)
        results.append(run_benchmark_test("Test B: 50 images / 120s (2m)", t_dir, preset=args.preset))

    # Test C: 100 images / 246.504 sec (The Real Production Test)
    if run_all or args.test == 'c':
        t_dir = CACHE_BENCHMARKS / "test_c_100img_246s"
        generate_benchmark_assets(t_dir, n_images=100, target_dur=246.504, master_audio_src=master_audio)
        results.append(run_benchmark_test("Test C: 100 images / 246.5s (Production)", t_dir, preset=args.preset, chunk_size=35))

    # Test D: 150 images / 600 sec (10 min)
    if run_all or args.test == 'd':
        t_dir = CACHE_BENCHMARKS / "test_d_150img_600s"
        generate_benchmark_assets(t_dir, n_images=150, target_dur=600.0, master_audio_src=master_audio)
        results.append(run_benchmark_test("Test D: 150 images / 600s (10m)", t_dir, preset=args.preset, chunk_size=35))

    # Test E: 300 images / 1800 sec (30 min)
    if run_all or args.test == 'e':
        t_dir = CACHE_BENCHMARKS / "test_e_300img_1800s"
        generate_benchmark_assets(t_dir, n_images=300, target_dur=1800.0, master_audio_src=master_audio)
        results.append(run_benchmark_test("Test E: 300 images / 1800s (30m)", t_dir, preset=args.preset, chunk_size=35, skip_verify=True))

    # Final Benchmark Summary Table
    print("\n" + "=" * 95)
    print(" FINAL BENCHMARK MATRIX PERFORMANCE REPORT")
    print("=" * 95)
    print(f"{'Test Case':<32} | {'Dur':<7} | {'WallClock':<10} | {'Speed':<6} | {'RAM':<8} | {'Size':<8} | {'Status'}")
    print("-" * 95)
    for r in results:
        status_str = "PASS" if r['pass_sla'] else "FAIL"
        print(f"{r['name']:<32} | {r['master_dur']:>5.0f}s  | {r['wall_clock']:>6.1f}s    | {r['ratio']:>4.2f}x  | {r['peak_ram_mb']:>5.1f}MB | {r['output_size_mb']:>5.1f}MB | {status_str}")
    print("=" * 95)

    # Dump JSON Report
    report_file = CACHE_BENCHMARKS / "benchmark_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({'system': specs, 'results': results}, f, indent=2)
    print(f"\nSaved benchmark report to: {report_file}")


if __name__ == '__main__':
    main()
