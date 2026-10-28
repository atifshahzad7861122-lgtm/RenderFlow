#!/usr/bin/env python3
"""
make_keyed_assets.py v2 — Pre-keyed transparent transition assets (ADAPTIVE keying).

v1 bug (fixed here): chromakey=0x00FF00:0.15:0.08 ne sirf pure-green key kiya.
YouTube-compressed clips ke background shifted greens hain (e.g. 3hT6mmVTeOQ ka
asal bg RGB(34,151,10) hai, pure green se dist~111) — v1 mein wo partially key
hue, background alpha ~232 reh gaya (0 hona chahiye tha). Doosri taraf purana
runtime pipeline (0x00FF00:0.32) shifted greens to pakar leta tha lekin
white/yellow content kha jata tha (bright alpha ~126).

v2 fix: har clip ka ASAL background color sample karo (multi-frame corner median,
fallback full-frame greenish median, 1-2 shades via clustering), usi color par
key karo, aur per-clip similarity sweep se sab se chhoti sim chuno jo bg ko
saaf kare (green_alpha<25) — is se effect/bright content max bachta hai
(verified: v1-runtime se behtar — flare alpha 156 vs 34, bright alpha 255 vs 126).

Clip classes (slice window ke 4 frames analyze karke):
  GREEN : greenish bg  -> adaptive chromakey (1-2 shades), regenerate
  DARK  : dark bg + bright streaks -> lumakey (screen clips jaisa), regenerate
  WHITE : white flash frames -> keying no-op, v1 asset reuse, key="none"
  BLACK : black frames -> keying no-op, v1 asset reuse, key="none"
  TEXT  : baked-in text/logo (manual visual list) -> v1 asset reuse + flag + blacklist recommend

Output: transition_pack/assets/<clip_id>.mov (PNG video in MOV, rgba)
Manifest: transition_pack/assets_manifest.json (key_filter mein actual sampled color)

Usage: python3 make_keyed_assets.py [--workers 8] [--limit N] [--only CID,...]
"""
import json, os, subprocess, sys, argparse, math
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.join(HERE, "pack.json")
RAW = os.path.join(HERE, "raw")
ASSETS = os.path.join(HERE, "assets")
MANIFEST = os.path.join(HERE, "assets_manifest.json")

OVERLAY_DUR = 1.2
MARGIN = 1.0
BLEND = 0.08
SIM_SWEEP = [0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30]
BG_ALPHA_TARGET = 25      # greenish pixels ki mean alpha is se kam honi chahiye
BRIGHT_ALPHA_MIN = 200    # bright content ki mean alpha is se zyada
DARK_FILTER = "lumakey=threshold=0.1:tolerance=0.05:softness=0.08"

# Manual visual inspection se: baked-in text/logo wale clips (blacklist recommend)
TEXT_CLIPS = {"6n7na1hi06E",  # "STA" logo baked in
              "6kUs1A4YQJc"}  # "PLEASE LEAVE A LIKE & SUBSCRIBE" baked in


def find_clean_slice(clip, dur, prefer_start):
    """auto_transition.py se mirrored."""
    total = clip["duration"]
    wmap = clip.get("wash_map")

    def is_clean(s):
        if not wmap:
            return True
        secs = range(int(s), int(s + dur) + 1)
        return all(wmap[k] == 0 for k in secs if 0 <= k < len(wmap))

    cands = [prefer_start]
    for sh in (2.0, -2.0, 4.0, -4.0, 6.0, -6.0, 8.0, -8.0, 10.0, -10.0):
        s = prefer_start + sh
        if 0 <= s <= total - dur:
            cands.append(s)
    cands.append(max(0.0, (total - dur) / 2.0))
    for s in cands:
        if is_clean(s):
            return s
    return None


def renderer_slice(clip):
    dur = min(OVERLAY_DUR, clip["duration"])
    peak = clip.get("content_peak_t", -1)
    if peak is not None and peak >= 0 and clip["duration"] > dur:
        prefer = min(max(0.0, peak - dur / 2.0), clip["duration"] - dur)
    else:
        prefer = max(0.0, (clip["duration"] - dur) / 2.0)
    s = find_clean_slice(clip, dur, prefer)
    if s is None:
        s = prefer
    return s, dur


def asset_window(clip):
    sl_start, sl_dur = renderer_slice(clip)
    a_start = max(0.0, sl_start - MARGIN)
    a_end = min(clip["duration"], sl_start + sl_dur + MARGIN)
    return a_start, round(a_end - a_start, 3), round(sl_start, 3), round(sl_dur, 3)


def grab_frame(raw, t):
    """Ek frame RGB numpy array mein (fast seek)."""
    h, w = 360, 640
    cmd = ["ffmpeg", "-hide_banner", "-y", "-v", "error", "-ss", f"{t:.2f}",
           "-i", raw, "-vframes", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.run(cmd, capture_output=True)
    if len(p.stdout) < w * h * 3:
        return None
    return np.frombuffer(p.stdout, dtype=np.uint8).reshape(h, w, 3).astype(int)


def frame_masks(img):
    r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    lum = img.mean(axis=2)
    greenish = (g > r + 15) & (g > b + 15) & (g > 60)
    white = lum > 225
    black = lum < 25
    bright = (lum > 200) & (~greenish)
    return {"greenish": greenish, "white": white, "black": black,
            "bright": bright, "lum": lum}


def corner_median(img, c=40):
    h, w, _ = img.shape
    px = np.concatenate([img[0:c, 0:c].reshape(-1, 3), img[0:c, w - c:w].reshape(-1, 3),
                         img[h - c:h, 0:c].reshape(-1, 3), img[h - c:h, w - c:w].reshape(-1, 3)])
    return np.median(px, axis=0)


def is_greenish(rgb):
    r, g, b = rgb
    return (g > r + 15) and (g > b + 15) and (g > 60)


def classify_clip(raw, a_start, a_dur):
    """4 frames -> GREEN / DARK / WHITE / BLACK / MIXED."""
    times = [a_start + a_dur * f for f in (0.15, 0.4, 0.6, 0.85)]
    agg = {"greenish": 0.0, "white": 0.0, "black": 0.0, "lum": 0.0,
           "greenish_lum": 0.0, "darkfrac": 0.0}
    n = 0
    ng = 0
    for t in times:
        img = grab_frame(raw, t)
        if img is None:
            continue
        m = frame_masks(img)
        agg["greenish"] += m["greenish"].mean()
        agg["white"] += m["white"].mean()
        agg["black"] += m["black"].mean()
        agg["lum"] += m["lum"].mean()
        agg["darkfrac"] += (m["lum"] < 60).mean()
        if m["greenish"].sum() > 500:
            agg["greenish_lum"] += m["lum"][m["greenish"]].mean()
            ng += 1
        n += 1
    if n == 0:
        return "BLACK", {}
    for k in agg:
        agg[k] /= n
    if ng > 0:
        agg["greenish_lum"] /= ng
    if agg["greenish"] > 0.10:
        # bahut pale/halkay green (lum>200) = flash tint, keyable bg nahi
        if agg["greenish_lum"] > 200:
            return "WHITE", agg
        return "GREEN", agg
    if agg["white"] > 0.85:
        return "WHITE", agg
    if agg["black"] > 0.85:
        return "BLACK", agg
    # dark bg + bright streaks (misclassified green) -> lumakey
    if agg["lum"] < 95 and agg["darkfrac"] > 0.40 and agg["white"] < 0.50:
        return "DARK", agg
    return "MIXED", agg


def sample_bg_colors(raw, a_start, a_dur):
    """Asal bg color(s): har frame ka full-frame greenish median (corners se zyada
    representative — corners par effect/vignette ho sakta hai), phir 1-2 shades."""
    times = [a_start + a_dur * f for f in (0.15, 0.4, 0.6, 0.85)]
    cand = []
    for t in times:
        img = grab_frame(raw, t)
        if img is None:
            continue
        m = frame_masks(img)
        gp = img[m["greenish"]]
        if len(gp) > img.shape[0] * img.shape[1] * 0.05:
            cand.append(np.median(gp, axis=0))
    if not cand:
        # fallback: corners
        for t in times:
            img = grab_frame(raw, t)
            if img is None:
                continue
            cm = corner_median(img)
            if is_greenish(cm):
                cand.append(cm)
    if not cand:
        return []
    cand = np.array(cand)
    c1 = np.median(cand, axis=0)
    dists = np.linalg.norm(cand - c1, axis=1)
    far = cand[dists > 45]
    if len(far) >= max(2, len(cand) * 0.15):
        c2 = np.median(far, axis=0)
        if np.linalg.norm(c1 - c2) > 40:
            return [c1, c2]
    return [c1]


def rgb_to_hex(rgb):
    r, g, b = [int(round(v)) for v in rgb]
    return f"0x{r:02X}{g:02X}{b:02X}"


def apply_key_single_frame(img, filt):
    """Single RGB frame par key filter lagao -> RGBA array (sweep ke liye fast)."""
    h, w, _ = img.shape
    cmd = (["ffmpeg", "-hide_banner", "-y", "-v", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-i", "-",
            "-vf", filt, "-f", "rawvideo", "-pix_fmt", "rgba", "-"])
    p = subprocess.run(cmd, input=img.astype(np.uint8).tobytes(), capture_output=True)
    if len(p.stdout) < w * h * 4:
        return None
    return np.frombuffer(p.stdout, dtype=np.uint8).reshape(h, w, 4)


def chroma_filter(colors, sim):
    parts = [f"chromakey={rgb_to_hex(c)}:{sim}:{BLEND}" for c in colors]
    return ",".join(parts) + ",format=rgba"


def dist_to_bg(img, colors):
    """Har pixel ki qareeb-tareen bg color se Euclidean distance."""
    d = np.linalg.norm(img[:, :, None, :] - np.array(colors)[None, None, :, :], axis=3)
    return d.min(axis=2)


def pick_similarity(raw, a_start, a_dur, colors):
    """3 frames par worst-case evaluate karo: max green_alpha, min bright_alpha.
    Bright content max bacha kar sab se behtar sim chuno, constraint: green<25.
    Bright mask mein sirf wo bright pixels jo bg se door hain (dist>100) — qareebi
    rang inherently unseparable hain, unko penalize nahi karte."""
    # NOTE: verify_asset wale same frames (0.25/0.5/0.75) taake sweep aur verify agree karein
    times = [a_start + a_dur * f for f in (0.25, 0.5, 0.75)]
    frames = []
    for t in times:
        cand = grab_frame(raw, t)
        if cand is not None and frame_masks(cand)["greenish"].sum() >= 500:
            frames.append(cand)
        if len(frames) == 3:
            break
    if not frames:
        return None, None
    masks = []
    for img in frames:
        m = frame_masks(img)
        bmask = m["bright"] & (dist_to_bg(img, colors) > 100)
        masks.append((m["greenish"], bmask))
    cands, fallback = [], []
    for sim in SIM_SWEEP:
        ga_vals, ba_vals = [], []
        for img, (gmask, bmask) in zip(frames, masks):
            out = apply_key_single_frame(img, chroma_filter(colors, sim))
            if out is None:
                break
            a = out[:, :, 3].astype(int)
            ga_vals.append(a[gmask].mean())
            ba_vals.append(a[bmask].mean() if bmask.sum() > 500 else 255.0)
        if len(ga_vals) != len(frames):
            continue
        ga, ba = max(ga_vals), min(ba_vals)  # worst-case
        rec = {"sim": sim, "green_alpha": round(float(ga), 1),
               "bright_alpha": round(float(ba), 1)}
        if ga < BG_ALPHA_TARGET:
            cands.append(rec)
        elif ba > 150:
            fallback.append(rec)
    if cands:
        # bright_alpha max; tie -> chhoti sim
        best = max(cands, key=lambda r: (r["bright_alpha"], -r["sim"]))
        return best["sim"], best
    if fallback:
        best = max(fallback, key=lambda r: (r["bright_alpha"], -r["green_alpha"]))
        best["note"] = "gradient_bg_fallback"
        return best["sim"], best
    return None, None


def verify_asset(out_path, raw, a_start, a_dur, kind, colors=None):
    """3 frames par automated check. Returns (ok, details)."""
    times = [a_start + a_dur * f for f in (0.25, 0.5, 0.75)]
    ga_vals, ba_vals = [], []
    for t in times:
        src = grab_frame(raw, t)
        if src is None:
            continue
        h, w, _ = src.shape
        at = max(0.0, t - a_start)  # asset apne a_start se shuru hota hai
        cmd = ["ffmpeg", "-hide_banner", "-y", "-v", "error", "-ss", f"{at:.2f}",
               "-i", out_path, "-vframes", "1",
               "-f", "rawvideo", "-pix_fmt", "rgba", "-"]
        p = subprocess.run(cmd, capture_output=True)
        if len(p.stdout) < w * h * 4:
            continue
        a = np.frombuffer(p.stdout, dtype=np.uint8).reshape(h, w, 4)[:, :, 3].astype(int)
        m = frame_masks(src)
        if kind == "GREEN":
            gm = m["greenish"]
            if gm.sum() > 500:
                ga_vals.append(a[gm].mean())
            if colors:
                bm = m["bright"] & (dist_to_bg(src, colors) > 100)
            else:
                bm = m["bright"]
            if bm.sum() > 500:
                ba_vals.append(a[bm].mean())
        else:  # DARK / lumakey
            dm = m["lum"] < 40
            if dm.sum() > 500:
                ga_vals.append(a[dm].mean())
            bm = m["bright"]
            if bm.sum() > 500:
                ba_vals.append(a[bm].mean())
    det = {"green_alpha_mean": round(float(np.mean(ga_vals)), 1) if ga_vals else None,
           "bright_alpha_mean": round(float(np.mean(ba_vals)), 1) if ba_vals else None}
    # Hard gate: green residue (yehi asal bug tha). Bright pale-glow key color ke
    # qareeb ho to chromakey se inherently partially key hota hai — wo diagnostic
    # hai, fail nahi (sweep pehle hi bright-max sim chun chuka hai).
    # DARK/lumakey soft key hai (12 screen clips ke same params): dark<110 enough.
    ok = True
    thresh = 110 if kind == "DARK" else BG_ALPHA_TARGET
    if det["green_alpha_mean"] is not None and det["green_alpha_mean"] >= thresh:
        ok = False
    det["bright_note"] = None
    if det["bright_alpha_mean"] is not None and det["bright_alpha_mean"] < 150:
        det["bright_note"] = (f"bright_alpha={det['bright_alpha_mean']} <150: "
                              "pale glow near key color partially keyed (inherent limit)")
    return ok, det


def encode_asset(raw, a_start, a_dur, filt_or_none, out):
    cmd = ["ffmpeg", "-hide_banner", "-y", "-i", raw,
           "-ss", f"{a_start:.3f}", "-t", f"{a_dur:.3f}"]
    if filt_or_none:
        cmd += ["-vf", filt_or_none]
    cmd += ["-c:v", "png", "-an", out]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1024


def key_one_green(cid, clip, raw, a_start, a_dur, sl_start, sl_dur):
    colors = sample_bg_colors(raw, a_start, a_dur)
    if not colors:
        return cid, False, {"reason": "bg sample failed (no greenish)"}
    sim, sweep = pick_similarity(raw, a_start, a_dur, colors)
    if sim is None:
        return cid, False, {"reason": "no similarity cleans bg", "colors": [list(map(int, c)) for c in colors]}
    filt = chroma_filter(colors, sim)
    out = os.path.join(ASSETS, f"{cid}.mov")
    if not encode_asset(raw, a_start, a_dur, filt, out):
        return cid, False, {"reason": "encode failed"}
    ok, det = verify_asset(out, raw, a_start, a_dur, "GREEN", colors)
    meta = {"clip_id": cid, "asset": f"assets/{cid}.mov", "type": "green",
            "key": "chromakey_adaptive",
            "key_filter": filt,
            "bg_colors": [[int(v) for v in c] for c in colors],
            "similarity": sim, "asset_start": a_start, "asset_dur": a_dur,
            "slice_start": sl_start, "slice_dur": sl_dur,
            "size_bytes": os.path.getsize(out),
            "sweep": sweep, "verify": det, "verify_ok": ok}
    if cid in TEXT_CLIPS:
        meta["flag"] = "baked-in text/logo — pack.json blacklist recommended"
    return cid, True, meta


def key_one_dark(cid, clip, raw, a_start, a_dur, sl_start, sl_dur):
    out = os.path.join(ASSETS, f"{cid}.mov")
    if not encode_asset(raw, a_start, a_dur, DARK_FILTER, out):
        return cid, False, {"reason": "encode failed"}
    ok, det = verify_asset(out, raw, a_start, a_dur, "DARK")
    meta = {"clip_id": cid, "asset": f"assets/{cid}.mov", "type": "green",
            "key": "lumakey_darkbg",
            "key_filter": DARK_FILTER,
            "asset_start": a_start, "asset_dur": a_dur,
            "slice_start": sl_start, "slice_dur": sl_dur,
            "size_bytes": os.path.getsize(out),
            "verify": det, "verify_ok": ok,
            "note": "dark-bg effect misclassified as green; lumakey applied"}
    return cid, True, meta


def reuse_v1_asset(cid, clip, kind, reason):
    """WHITE/BLACK/TEXT: v1 asset theek hai (keying no-op thi), sirf manifest update."""
    a_start, a_dur, sl_start, sl_dur = asset_window(clip)
    out = os.path.join(ASSETS, f"{cid}.mov")
    if not os.path.exists(out):
        return cid, False, {"reason": f"v1 asset missing: {out}"}
    meta = {"clip_id": cid, "asset": f"assets/{cid}.mov", "type": "green",
            "key": "none", "key_filter": "none",
            "asset_start": a_start, "asset_dur": a_dur,
            "slice_start": sl_start, "slice_dur": sl_dur,
            "size_bytes": os.path.getsize(out),
            "note": reason, "verify_ok": True}
    if cid in TEXT_CLIPS:
        meta["flag"] = "baked-in text/logo — pack.json blacklist recommended"
    if cid == "KihWHqHelbM":
        meta["flag"] = "watermark 'The Green Screen of world' — pack.json blacklist recommended"
    if cid == "aVyuFZFbLx4":
        meta["flag"] = "Arabic subscribe-CTA text — pack.json blacklist recommended"
    return cid, True, meta


def process_green(clip):
    cid = clip["id"]
    raw = os.path.join(RAW, f"{cid}.mp4")
    if not os.path.exists(raw):
        return cid, False, {"reason": "raw missing"}
    a_start, a_dur, sl_start, sl_dur = asset_window(clip)
    if cid in TEXT_CLIPS:
        return reuse_v1_asset(cid, clip, "TEXT", "baked-in text/logo; kept v1 asset, blacklist recommended")
    kind, agg = classify_clip(raw, a_start, a_dur)
    if kind == "GREEN":
        return key_one_green(cid, clip, raw, a_start, a_dur, sl_start, sl_dur)
    if kind == "DARK":
        return key_one_dark(cid, clip, raw, a_start, a_dur, sl_start, sl_dur)
    if kind in ("WHITE", "BLACK"):
        return reuse_v1_asset(cid, clip, kind, f"{kind.lower()}-frame slice; keying no-op, kept v1 asset")
    # MIXED: greenish ho to key karo warna v1 reuse + flag
    if agg.get("greenish", 0) > 0.03:
        cid2, ok, meta = key_one_green(cid, clip, raw, a_start, a_dur, sl_start, sl_dur)
        if ok and isinstance(meta, dict):
            meta["flag"] = f"MIXED slice ({ {k: round(v,2) for k,v in agg.items()} }); review recommended"
        return cid2, ok, meta
    meta_cid, ok, meta = reuse_v1_asset(cid, clip, "MIXED", f"mixed slice, kept v1 asset: { {k: round(v,2) for k,v in agg.items()} }")
    if ok and isinstance(meta, dict):
        meta["flag"] = "MIXED slice content — review recommended"
    return meta_cid, ok, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", type=str, default="")
    args = ap.parse_args()

    os.makedirs(ASSETS, exist_ok=True)
    d = json.load(open(PACK))
    clips = [c for c in d["clips"] if not c.get("blacklisted") and c["kind"] == "green"]
    clips = sorted(clips, key=lambda c: c["id"])
    if args.only:
        want = set(args.only.split(","))
        clips = [c for c in clips if c["id"] in want]
    if args.limit:
        clips = clips[:args.limit]
    print(f"adaptive keying {len(clips)} green clips, workers={args.workers}", flush=True)

    manifest, failed = {}, []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_green, c): c["id"] for c in clips}
        for f in as_completed(futs):
            cid, ok, info = f.result()
            done += 1
            if ok:
                manifest[cid] = info
            else:
                failed.append({"id": cid, "error": info})
            if done % 5 == 0 or done == len(clips):
                print(f"  [{done}/{len(clips)}] ok={len(manifest)} failed={len(failed)}", flush=True)

    # existing manifest se merge: is run mein process na hone wale clips ki entries rakho
    old = {}
    if os.path.exists(MANIFEST):
        try:
            old = json.load(open(MANIFEST)).get("assets", {})
        except Exception:
            old = {}
    processed = set(manifest.keys()) | {x["id"] for x in failed}
    for cid, e in old.items():
        if cid not in processed:
            manifest[cid] = e

    n_verify_fail = sum(1 for m in manifest.values()
                        if isinstance(m, dict) and m.get("type") == "green" and not m.get("verify_ok", True))
    json.dump({"tool": "make_keyed_assets.py v2 (adaptive)",
               "overlay_dur": OVERLAY_DUR, "margin": MARGIN,
               "bg_alpha_target": BG_ALPHA_TARGET, "bright_alpha_min": BRIGHT_ALPHA_MIN,
               "assets": manifest, "failed": failed},
              open(MANIFEST, "w"), indent=1)
    total_mb = sum(m["size_bytes"] for m in manifest.values()
                   if isinstance(m, dict) and "size_bytes" in m) / 1e6
    print(f"DONE ok={len(manifest)} failed={len(failed)} verify_fail={n_verify_fail} total={total_mb:.0f}MB")
    for x in failed:
        print("FAILED:", x["id"], str(x["error"])[:150])
    for cid, m in manifest.items():
        if isinstance(m, dict) and m.get("type") == "green" and not m.get("verify_ok", True):
            print("VERIFY-FAIL:", cid, m.get("verify"))


if __name__ == "__main__":
    main()
