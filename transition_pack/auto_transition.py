#!/usr/bin/env python3
"""
auto_transition.py — FULLY AUTOMATIC transition overlay engine for Rendering Studio.

Har scene cut par automatically pack se ek transition clip pick karta hai
(deterministic rotation, last-5 mein repeat nahi), use cut ke around overlay
karta hai, aur uski audio (agar non-silent) narration ke saath mix karta hai.

Kinds:
  green  -> raw mp4, RENDER-TIME chromakey=0x00FF00:0.32:0.12, overlay with alpha
           (pre-keyed webm nahi: is env ka libvpx-vp9 alpha silently drop karta hai)
  screen -> dark-background flare, blend=all_mode=screen (no opaque box)

CLI:
  python3 auto_transition.py --scenes scene_labels.json --pack pack.json \
      --base base.mp4 --out out.mp4 --overlay-dur 1.2

Output: 1920x1080, 30fps, H.264 yuv420p, AAC 48kHz stereo, duration == base.
"""
import argparse, json, subprocess, sys, os, math
import numpy as np

W, H, FPS = 1920, 1080, 30

# ---------------------------------------------------------------------------
# TRANSITION INTELLIGENCE v2 (spec 2026-09-24 §8/§9/§10)
# Har cut ka context -> (style, duration, opacity).
# Duration hamesha 0.15-0.60s ke andar (spec §10). Opacity < 1.0 = subtle.
# ---------------------------------------------------------------------------
# style: 'pack' = pack clip overlay | 'dip_black'/'dip_white' = solid fade
CONTEXT_MAP = {
    # context         style          kind_pref           dur    opacity
    'normal':         ('pack',      ['screen', 'green'], 0.30,  0.55),
    'story_change':   ('pack',      ['green', 'screen'], 0.50,  0.65),
    'location_change':('pack',      ['screen', 'green'], 0.40,  0.70),
    'time_passage':   ('dip_black', None,                0.50,  1.00),
    'turning_point':  ('pack',      ['green', 'screen'], 0.60,  1.00),
    'emotional':      ('pack',      ['screen', 'green'], 0.60,  0.45),
    'fast':           ('pack',      ['screen', 'green'], 0.15,  0.50),
}
STYLE_LABEL = {
    'normal': 'soft_dissolve', 'story_change': 'cinematic_dissolve',
    'location_change': 'soft_directional', 'time_passage': 'dip_to_black',
    'turning_point': 'stronger_cinematic', 'emotional': 'slow_soft_dissolve',
    'fast': 'clean_short',
}
MIN_TDUR, MAX_TDUR = 0.15, 0.60

def infer_context(scene):
    """plan.json mein explicit 'context' ho to wahi; warna duration se infer."""
    ctx = (scene.get('context') or '').strip().lower()
    if ctx in CONTEXT_MAP:
        return ctx
    # fast narration = chhote scenes
    try:
        if float(scene.get('dur', 0)) < 1.5:
            return 'fast'
    except (TypeError, ValueError):
        pass
    return 'normal'

def clamp_dur(d):
    return min(MAX_TDUR, max(MIN_TDUR, float(d)))

def slice_is_wash(video, kind, start, dur):
    """Legacy fallback (cv2 seek imprecise hai) — wash_map use karo jab available ho."""
    return False

def find_clean_slice(clip, dur, prefer_start):
    """wash_map (per-second, pack build time par accurate ffmpeg se) use karke
    clean (non-wash) slice dhoondo. prefer_start ke qareeb tareen clean window."""
    total = clip["duration"]
    wmap = clip.get("wash_map")
    def is_clean(s):
        if not wmap:
            return True
        # window ke andar har second clean hona chahiye
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
    return None  # koi clean slice nahi mili

def load_scenes(path):
    d = json.load(open(path))
    if isinstance(d, dict) and "scenes" in d:
        scenes = d["scenes"]
    elif isinstance(d, list):
        scenes = d
    else:
        raise ValueError("scene_labels.json: top-level list ya {'scenes': [...]} hona chahiye")
    return scenes

def load_pack(path):
    d = json.load(open(path))
    clips = d["clips"] if isinstance(d, dict) else d
    # blacklisted clips (end screens, CTAs, logos, faces...) kabhi use nahi honge
    clips = [c for c in clips if not c.get("blacklisted")]
    # deterministic order
    clips = sorted(clips, key=lambda c: c["id"])
    return clips

def pick_transitions(cut_times, clips, contexts, dur_scale=1.0):
    """Context-aware selection; last-5 mein repeat nahi; duration 0.15-0.60s.

    cut_times[i] ka context contexts[i] se aata hai (incoming scene ka).
    Har pick: {cut, clip|None, style, context, dur, opacity, slice_start,
               slice_dur, audio_start}
    """
    picks = []
    recent = []
    idx = 0
    # kind se grouped pools (deterministic rotation per kind-pref)
    for ci, cut in enumerate(cut_times):
        context = contexts[ci] if ci < len(contexts) else 'normal'
        if context not in CONTEXT_MAP:
            context = 'normal'
        method, kind_pref, base_dur, opacity = CONTEXT_MAP[context]
        dur = clamp_dur(base_dur * dur_scale)

        if method in ('dip_black', 'dip_white'):
            picks.append({'cut': cut, 'clip': None, 'style': method,
                          'context': context, 'label': STYLE_LABEL[context],
                          'dur': dur, 'opacity': opacity,
                          'slice_start': 0.0, 'slice_dur': dur,
                          'audio_start': 0.0})
            continue

        # pack clip: kind preference order mein pool banao
        pool = []
        for k in kind_pref:
            pool.extend([c for c in clips if c.get('kind') == k])
        # koi kind missing ho to baqi clips append
        seen_ids = {c['id'] for c in pool}
        pool.extend([c for c in clips if c['id'] not in seen_ids])

        chosen = None
        chosen_slice = None
        for k in range(len(pool)):
            c = pool[(idx + k) % len(pool)]
            if c["id"] in recent:
                continue
            cdur = min(dur, c["duration"])
            peak = c.get("content_peak_t", -1)
            if peak is not None and peak >= 0 and c["duration"] > cdur:
                prefer = min(max(0.0, peak - cdur / 2.0), c["duration"] - cdur)
            else:
                prefer = max(0.0, (c["duration"] - cdur) / 2.0)
            s = find_clean_slice(c, cdur, prefer)
            if s is None:
                continue  # wash-only clip, agla try karo
            chosen, chosen_slice = c, s
            idx = (idx + k + 1) % len(pool)
            break
        if chosen is None:
            # fallback: pehla non-recent clip bina wash-check ke
            for k in range(len(pool)):
                c = pool[(idx + k) % len(pool)]
                if c["id"] not in recent:
                    chosen = c
                    cdur = min(dur, c["duration"])
                    chosen_slice = max(0.0, (c["duration"] - cdur) / 2.0)
                    idx = (idx + k + 1) % len(pool)
                    break
        if chosen is None:
            # aakhri fallback: silent dip (koi clip usable nahi)
            picks.append({'cut': cut, 'clip': None, 'style': 'dip_black',
                          'context': context, 'label': 'dip_to_black_fallback',
                          'dur': clamp_dur(0.3), 'opacity': 0.6,
                          'slice_start': 0.0, 'slice_dur': 0.3,
                          'audio_start': 0.0})
            continue
        recent.append(chosen["id"])
        recent = recent[-5:]
        cdur = min(dur, chosen["duration"])
        start = chosen_slice
        # AUDIO slice (independent): audio ke sab se loud lamhe par center
        apeak = chosen.get("audio_peak_t", -1)
        if apeak is not None and apeak >= 0 and chosen["duration"] > cdur:
            astart = min(max(0.0, apeak - cdur / 2.0), chosen["duration"] - cdur)
        else:
            astart = start
        picks.append({"cut": cut, "clip": chosen, "style": "pack",
                      "context": context, "label": STYLE_LABEL[context],
                      "dur": cdur, "opacity": opacity,
                      "slice_start": start, "slice_dur": cdur,
                      "audio_start": astart})
    return picks

def build_cmd(args, picks, out_path):
    # inputs: 0 = base; phir pack-clip slices; phir solid-dip color sources
    cmd = ["ffmpeg", "-y", "-v", "error"]
    cmd += ["-i", args.base]
    pack_picks = [p for p in picks if p["style"] == "pack"]
    dip_picks = [p for p in picks if p["style"] in ("dip_black", "dip_white")]
    # input index per pick (inputs grouped: pack pehle, phir dips)
    input_idx = {}
    _vi = 1
    for p in pack_picks:
        cmd += ["-ss", f"{p['slice_start']:.3f}", "-t", f"{p['slice_dur']:.3f}",
                "-i", p["clip"]["video"]]
        input_idx[id(p)] = _vi; _vi += 1
    for p in dip_picks:
        color = "black" if p["style"] == "dip_black" else "white"
        cmd += ["-f", "lavfi", "-i",
                f"color={color}:s={W}x{H}:d={p['dur']:.3f}:r={FPS}"]
        input_idx[id(p)] = _vi; _vi += 1
    # audio inputs for non-silent pack clips (independent slice)
    audio_picks = [p for p in pack_picks
                   if not p["clip"].get("silent", False) and p["clip"].get("audio")]
    for p in audio_picks:
        cmd += ["-ss", f"{p['audio_start']:.3f}", "-t", f"{p['slice_dur']:.3f}",
                "-i", p["clip"]["audio"]]

    fc = []
    fc.append("[0:v]format=gbrp,fps=30,scale=1920:1080:flags=lanczos,setsar=1[v0]")
    vcur = "v0"
    for i, p in enumerate(picks):
        vi = input_idx[id(p)]
        c = p["cut"]
        dur = p["dur"]
        op = p.get("opacity", 1.0)
        a, b = c - dur / 2.0, c + dur / 2.0
        en = f"between(t,{a:.3f},{b:.3f})"
        if p["style"] == "pack":
            kind = p["clip"]["kind"]
            # setpts: overlay input ko cut time par align karo (robust timing)
            pts = f"setpts=PTS-STARTPTS+{a:.3f}/TB,"
            if kind == "green":
                op_f = f",colorchannelmixer=aa={op:.2f}" if op < 1.0 else ""
                key = p["clip"].get("key", {})
                kc = key.get("color", "0x00FF00")
                ks = key.get("similarity", 0.32)
                kb = key.get("blend", 0.12)
                fc.append(f"[{vi}:v]{pts}fps=30,scale=1920:1080:flags=lanczos,"
                          f"chromakey={kc}:{ks}:{kb},format=rgba{op_f},setsar=1[t{i}]")
                fc.append(f"[{vcur}][t{i}]overlay=0:0:enable='{en}',format=gbrp[v{i+1}]")
                # NOTE: overlay ke baad explicit format=gbrp ZAROORI hai — warna
                # overlay ka auto-negotiated format + agle blend ka gbrp milne par
                # plane-order bug se poori frame magenta ho jati hai
            else:  # screen: blend filter ka native opacity use karo
                fc.append(f"[{vi}:v]{pts}fps=30,scale=1920:1080:flags=lanczos,format=gbrp,setsar=1[t{i}]")
                fc.append(f"[{vcur}][t{i}]blend=all_mode=screen:all_opacity={op:.2f}:enable='{en}'[v{i+1}]")
        else:  # dip_black / dip_white: solid color, fade in/out (alpha)
            # NOTE: setpts ke baad timestamps a..a+dur hain, is liye fade st bhi wahi
            half = dur / 2.0
            fc.append(f"[{vi}:v]setpts=PTS-STARTPTS+{a:.3f}/TB,"
                      f"format=gbrap,scale=1920:1080:flags=lanczos,"
                      f"fade=t=in:st={a:.3f}:d={half:.3f}:alpha=1,"
                      f"fade=t=out:st={a+half:.3f}:d={half:.3f}:alpha=1,"
                      f"setsar=1[t{i}]")
            fc.append(f"[{vcur}][t{i}]overlay=0:0:enable='{en}',format=gbrp[v{i+1}]")
        vcur = f"v{i+1}"
    fc.append(f"[{vcur}]format=yuv420p[vout]")

    # audio: base + delayed pack-clip slices, amix normalize=0
    a_base = 1 + len(pack_picks) + len(dip_picks)
    fc.append("[0:a]aresample=48000,aformat=channel_layouts=stereo[a0]")
    amix_ins = ["[a0]"]
    for j, p in enumerate(audio_picks):
        ai = a_base + j
        delay_ms = int(max(0.0, p["cut"] - p["dur"] / 2.0) * 1000)
        fc.append(f"[{ai}:a]aresample=48000,aformat=channel_layouts=stereo,"
                  f"volume=1.0,adelay={delay_ms}|{delay_ms}[a{j+1}]")
        amix_ins.append(f"[a{j+1}]")
    n_ins = len(amix_ins)
    fc.append("".join(amix_ins) + f"amix=inputs={n_ins}:normalize=0[aout]")

    cmd += ["-filter_complex", ";".join(fc),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", args.preset, "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
            "-shortest", out_path]
    return cmd, picks, audio_picks

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", required=True)
    ap.add_argument("--pack", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--overlay-dur", type=float, default=None,
                    help="legacy: sab transitions ki fixed duration (0.15-0.60 clamp). "
                         "Default: context intelligence se per-cut duration.")
    ap.add_argument("--dur-scale", type=float, default=1.0,
                    help="intelligence durations ka multiplier (default 1.0)")
    ap.add_argument("--max-cuts", type=int, default=None,
                    help="sirf pehle N cuts par lagao (demo ke liye)")
    ap.add_argument("--preset", default="veryfast",
                    help="x264 preset (speed ke liye veryfast)")
    ap.add_argument("--qc-out", default=None,
                    help="transitions QC JSON ka path (default: <out>.transitions.json)")
    args = ap.parse_args()

    scenes = load_scenes(args.scenes)
    clips = load_pack(args.pack)
    if not clips:
        sys.exit("pack mein koi clip nahi")
    usable = [c for c in clips if os.path.exists(c["video"])]
    if not usable:
        sys.exit("pack videos files nahi mili")
    clips = usable

    cuts = [s["start_s"] for s in scenes[1:]]
    contexts = [infer_context(s) for s in scenes[1:]]
    if args.max_cuts:
        cuts = cuts[:args.max_cuts]
        contexts = contexts[:args.max_cuts]

    if args.overlay_dur is not None:
        # legacy fixed-duration mode: sab cuts par ek hi duration
        fixed = clamp_dur(args.overlay_dur)
        picks = pick_transitions(cuts, clips, contexts, dur_scale=1.0)
        for p in picks:
            p["dur"] = fixed
            p["slice_dur"] = fixed
            p["label"] = p.get("label", "fixed") + "_fixed"
    else:
        picks = pick_transitions(cuts, clips, contexts, args.dur_scale)

    cmd, picks, audio_picks = build_cmd(args, picks, args.out)
    print(f"cuts: {len(cuts)}, video overlays: {len(picks)}, audio mixes: {len(audio_picks)}")
    for p in picks:
        cid = p["clip"]["id"] if p.get("clip") else "-"
        kind = p["clip"]["kind"] if p.get("clip") else "-"
        print(f"  cut@{p['cut']:.2f}s [{p['context']}] -> {p['label']} "
              f"({kind} {cid}, dur={p['dur']:.2f}s, op={p['opacity']:.2f})")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed rc={r.returncode}")

    # QC: transitions report (§20)
    qc = {
        "n_transitions": len(picks),
        "types_used": sorted({p["label"] for p in picks}),
        "avg_duration": round(sum(p["dur"] for p in picks) / max(1, len(picks)), 3),
        "durations": [round(p["dur"], 3) for p in picks],
        "details": [
            {"cut_s": round(p["cut"], 3), "context": p["context"],
             "style": p["style"], "label": p["label"],
             "clip_id": (p["clip"]["id"] if p.get("clip") else None),
             "dur_s": round(p["dur"], 3), "opacity": round(p["opacity"], 2)}
            for p in picks
        ],
    }
    qc_path = args.qc_out or (args.out + ".transitions.json")
    json.dump(qc, open(qc_path, "w"), indent=1)
    print("transitions QC:", qc_path)
    print("OK:", args.out)

if __name__ == "__main__":
    main()
