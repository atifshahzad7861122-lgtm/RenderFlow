# Lens Flare Transition Pack

YouTube playlist se banaya gaya transition pack (green-screen lens flare overlays).

## Layout
- `raw/` — original downloads (reference; green clips bhi yahin se render-time key hote hain)
- `audio_norm/` — loudnormed audio slices (I=-18 LUFS, TP=-1.5, LRA=11); silent clips dropped
- `pack.json` — manifest: [{id, title, duration, kind, video, audio, silent, key, ...}]
- `auto_transition.py` — automatic transition engine

## Pre-keyed assets v2 (ADAPTIVE keying) — 2026-09-21
- `assets/` — 54 pre-keyed `.mov` (PNG-in-MOV, RGBA): 42 green + 12 screen.
- `assets_manifest.json` — har asset: {clip_id, asset, type, key, key_filter,
  bg_colors (sampled asal rang), similarity, asset_start/dur, slice_start/dur,
  size_bytes, verify, verify_ok, flag (content flags)}.
- `make_keyed_assets.py` — generator script (v2, adaptive).
- **Codec:** VP9/AV1/FFV1 ne alpha silently drop kiya; QTRLE ~150x bara tha.
  PNG-in-MOV alpha preserve karta hai — isi liye yehi codec hai.
- **Adaptive keying (v1 bug ka fix):** v1 mein fixed `chromakey=0x00FF00` tha —
  asal bg aksar pure green nahi hota (e.g. `(34,150,9)`), jis se green residue
  reh jata tha. v2 har clip ka asal bg color sample karta hai (multi-frame
  greenish-pixel median, 1-2 shades), phir per-clip similarity sweep
  (0.03–0.30, 3 frames worst-case) se wo sim chunta hai jo bright content
  max bachaye aur bg <25 alpha par saaf kare.
- **Dark-bg green clips** (2): `lumakey` (soft key, 12 screen clips wale params).
- **White/black-bg clips** (13): keying no-op hai — asset as-is (screen blend ke liye).
- **Verify:** har asset par automated check (bg alpha <25, bright content alpha);
  54/54 PASS. 4 clips par content flags hain (watermark / baked-in text / CTA) —
  `pack.json` mein blacklist recommended.
- **Scope note:** pack mein 136 clips hain; 54 clean usable assets banaye gaye.
  Blacklisted/low-quality clips (watermark, baked-in text, static) assets mein
  nahi hain.
- **Renderer wiring:** `auto_transition.py` abhi bhi raw clips + render-time
  keying use karta hai. Pre-keyed assets ko runtime input banane ke liye
  renderer rewire + verify baqi hai.

## Kinds
- `green` — green background; render time par `chromakey=0x00FF00:0.32:0.12` + overlay with alpha.
  Pre-keyed webm NAHI banaye gaye kyunke is environment ka libvpx-vp9 alpha plane
  silently drop kar deta hai (verified 2026-09-21).
- `screen` — dark/black background flare; render time par `blend=all_mode=screen`

## Usage
```
python3 auto_transition.py --scenes scene_labels.json --pack pack.json \
    --base base_clean.mp4 --out output.mp4 --overlay-dur 1.2
```
Har scene cut par automatically ek transition pick hota hai (deterministic rotation,
last-5 mein repeat nahi, duration >= overlay_dur prefer). Slice clip ke sab se
active lamhe (content_peak_t, pack build time par mapa gaya) par centered hota hai
taake transition waqai nazar aaye. Transition cut ke 0.6s pehle se 0.6s baad tak
visible rehta hai. Non-silent clips ki audio narration ke saath mix hoti hai
(moderate level).
