#!/usr/bin/env python3
"""
build_pack.py — Transition Pack builder (Steps 3-6).

raw/<id>.mp4  ->  classify (green vs screen)
  green  -> raw rehta hai; chromakey RENDER TIME par (libvpx VP9 alpha drop karta hai)
  screen -> as-is (render time par screen-blend)
  audio  -> audio_norm/<id>.m4a (loudnorm I=-18:TP=-1.5:LRA=11), silent flag
  -> pack.json + PACK_README.md

Usage:
  python3 build_pack.py --raw raw --out . [--workers 1]
"""
import argparse, json, os, subprocess, sys, glob
import numpy as np
import cv2
from concurrent.futures import ThreadPoolExecutor

def ffprobe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0

def sample_frames(path, n=5, size=160):
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    frames = []
    idxs = [int(total * (k + 1) / (n + 1)) for k in range(n)] if total > n else list(range(total))
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, f = cap.read()
        if ok:
            f = cv2.resize(f, (size, size))
            frames.append(f)
    cap.release()
    return frames

def classify(path):
    """green: saturated-green background dominant; else screen (dark + bright spots)."""
    frames = sample_frames(path)
    if not frames:
        return "unknown", {}
    green_fracs, dark_fracs, bright_fracs = [], [], []
    for f in frames:
        b, g, r = f[:, :, 0].astype(np.int16), f[:, :, 1].astype(np.int16), f[:, :, 2].astype(np.int16)
        green_mask = (g > r + 40) & (g > b + 40) & (g > 100)
        green_fracs.append(green_mask.mean())
        lum = (0.114 * b + 0.587 * g + 0.299 * r)
        dark_fracs.append((lum < 40).mean())
        bright_fracs.append((lum > 150).mean())
    gf, df, bf = float(np.mean(green_fracs)), float(np.mean(dark_fracs)), float(np.mean(bright_fracs))
    stats = {"green_frac": round(gf, 3), "dark_frac": round(df, 3), "bright_frac": round(bf, 3)}
    if gf > 0.30:
        return "green", stats
    return "screen", stats

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stderr[-2000:]

KEY_COLOR = "0x00FF00"
KEY_SIM, KEY_BLEND = 0.32, 0.12
# NOTE (2026-09-21): is environment ka libvpx-vp9 VP9 alpha plane SILENTLY drop
# kar deta hai (yuva420p in -> yuv420p out, koi warning nahi; -auto-alt-ref 0 /
# -lag-in-frames 0 se bhi fix nahi hua). Is liye green clips PRE-KEY nahi hote:
# raw mp4 manifest mein rehta hai aur chromakey RENDER TIME par lagta hai
# (auto_transition.py). Quality identical, storage bhi kam.

def content_profile(src, kind, n=12):
    """Poori clip par n evenly-spaced samples: har sample par 'content' fraction.
    green: key ke baad opaque fraction. screen: bright-pixel fraction.
    Returns (peak_t, max_frac, fracs). Ek hi ffmpeg call mein saare frames."""
    dur = ffprobe_duration(src)
    if dur <= 0:
        return -1.0, -1.0, []
    if kind == "green":
        vf = (f"fps={n}/{dur:.3f},chromakey={KEY_COLOR}:{KEY_SIM}:{KEY_BLEND},"
              f"format=yuva420p,alphaextract,scale=160:120")
        # opaque = alpha > 16
        def frac(a):
            return float((a > 16).mean())
    else:
        vf = f"fps={n}/{dur:.3f},format=gray,scale=160:120"
        def frac(a):
            return float((a > 100).mean())
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", src, "-vf", vf,
         "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True)
    frame_sz = 160 * 120
    if r.returncode != 0 or len(r.stdout) < frame_sz:
        return -1.0, -1.0, []
    nf = len(r.stdout) // frame_sz
    arr = np.frombuffer(r.stdout[:nf * frame_sz], dtype=np.uint8).reshape(nf, 120, 160)
    fracs = [round(frac(a), 4) for a in arr]
    peak_i = int(np.argmax(fracs))
    peak_t = (peak_i + 0.5) * dur / nf
    return round(peak_t, 2), round(max(fracs), 4), fracs

def extract_audio(src, dst, reuse_ok=True):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if reuse_ok and os.path.exists(dst) and os.path.getsize(dst) > 1024:
        pass  # dobara loudnorm nahi — pehle se normalized file reuse karo
    else:
        rc, err = run(["ffmpeg", "-y", "-v", "error", "-i", src,
                       "-vn", "-af", "loudnorm=I=-18:TP=-1.5:LRA=11",
                       "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", dst])
        if rc != 0 or not os.path.exists(dst):
            return None, True, None
    # volumedetect
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", dst, "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    import re
    m = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", r.stderr)
    mean_db = float(m.group(1)) if m else None
    silent = (mean_db is None) or (mean_db < -60)
    return dst, silent, mean_db

def process_one(vid, raw_dir, out_dir, titles):
    raw = os.path.join(raw_dir, vid + ".mp4")
    if not os.path.exists(raw):
        cands = glob.glob(os.path.join(raw_dir, vid + ".*"))
        raw = cands[0] if cands else None
    if not raw:
        return {"id": vid, "error": "raw missing"}
    dur = ffprobe_duration(raw)
    kind, stats = classify(raw)
    entry = {"id": vid, "title": titles.get(vid, ""), "duration": round(dur, 2),
             "kind": kind, "classify_stats": stats}
    if kind == "green":
        # pre-key NAHI: render-time chromakey (libvpx VP9 alpha drop ki wajah se)
        entry["video"] = raw
        entry["key"] = {"color": KEY_COLOR, "similarity": KEY_SIM, "blend": KEY_BLEND,
                        "applied": "render-time"}
    else:
        entry["video"] = raw
    # content profile: sab se ziyaada active lamha (transition slice wahin se)
    peak_t, max_frac, fracs = content_profile(raw, kind)
    entry["content_peak_t"] = peak_t
    entry["content_max_frac"] = max_frac
    if max_frac < 0.005:
        entry["key_suspect"] = True  # poori clip mein koi visible content nahi
    # audio
    adst = os.path.join(out_dir, "audio_norm", vid + ".m4a")
    apath, silent, mean_db = extract_audio(raw, adst)
    entry["audio"] = apath
    entry["silent"] = silent
    entry["audio_mean_db"] = mean_db
    if silent and apath and os.path.exists(apath):
        os.remove(apath)
        entry["audio"] = None
    return entry

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--titles", default="/tmp/pl_ids.txt")
    args = ap.parse_args()

    titles = {}
    if os.path.exists(args.titles):
        for line in open(args.titles):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                titles[parts[0]] = parts[1]

    vids = sorted({os.path.splitext(os.path.basename(p))[0]
                   for p in glob.glob(os.path.join(args.raw, "*"))
                   if not p.endswith(".part")})
    print(f"videos: {len(vids)}, workers: {args.workers}", flush=True)

    entries = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_one, v, args.raw, args.out, titles): v for v in vids}
        done = 0
        for f in futs:
            try:
                e = f.result()
            except Exception as ex2:
                e = {"id": futs[f], "error": str(ex2)}
            entries.append(e)
            done += 1
            if done % 10 == 0 or done == len(vids):
                print(f"  {done}/{len(vids)}", flush=True)

    ok = [e for e in entries if "error" not in e]
    manifest = {"pack": "lens-flare-transitions", "clips": sorted(ok, key=lambda e: e["id"]),
                "errors": [e for e in entries if "error" in e]}
    with open(os.path.join(args.out, "pack.json"), "w") as fh:
        json.dump(manifest, fh, indent=1)

    n_green = sum(1 for e in ok if e["kind"] == "green")
    n_screen = sum(1 for e in ok if e["kind"] == "screen")
    n_silent = sum(1 for e in ok if e.get("silent"))
    n_suspect = sum(1 for e in ok if e.get("key_suspect"))
    print(f"OK: {len(ok)} (green={n_green}, screen={n_screen}, silent_audio={n_silent}, "
          f"key_suspect={n_suspect}), errors={len(manifest['errors'])}")
    with open(os.path.join(args.out, "PACK_SUMMARY.txt"), "w") as fh:
        fh.write(f"ok={len(ok)} green={n_green} screen={n_screen} "
                 f"silent={n_silent} suspect={n_suspect} errors={len(manifest['errors'])}\n")
    write_readme(args.out)


def write_readme(out_dir):
    readme = """# Lens Flare Transition Pack

YouTube playlist se banaya gaya transition pack (green-screen lens flare overlays).

## Layout
- `raw/` — original downloads (reference; green clips bhi yahin se render-time key hote hain)
- `audio_norm/` — loudnormed audio slices (I=-18 LUFS, TP=-1.5, LRA=11); silent clips dropped
- `pack.json` — manifest: [{id, title, duration, kind, video, audio, silent, key, ...}]
- `auto_transition.py` — automatic transition engine

## Kinds
- `green` — green background; render time par `chromakey=0x00FF00:0.32:0.12` + overlay with alpha.
  Pre-keyed webm NAHI banaye gaye kyunke is environment ka libvpx-vp9 alpha plane
  silently drop kar deta hai (verified 2026-09-21).
- `screen` — dark/black background flare; render time par `blend=all_mode=screen`

## Usage
```
python3 auto_transition.py --scenes scene_labels.json --pack pack.json \\
    --base base_clean.mp4 --out output.mp4 --overlay-dur 1.2
```
Har scene cut par automatically ek transition pick hota hai (deterministic rotation,
last-5 mein repeat nahi, duration >= overlay_dur prefer). Slice clip ke sab se
active lamhe (content_peak_t, pack build time par mapa gaya) par centered hota hai
taake transition waqai nazar aaye. Transition cut ke 0.6s pehle se 0.6s baad tak
visible rehta hai. Non-silent clips ki audio narration ke saath mix hoti hai
(moderate level).
"""
    open(os.path.join(out_dir, "PACK_README.md"), "w").write(readme)


if __name__ == "__main__":
    main()

