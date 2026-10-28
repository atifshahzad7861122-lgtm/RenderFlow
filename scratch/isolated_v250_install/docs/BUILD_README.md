# Rendering Studio — Engine v2 (2026-09-21)

Sync-timeline video engine: narration-synced scenes + automatic lens-flare
transitions + transition SFX + 2.5D camera-depth motion.

## Scope (Atif, 2026-09-21)
- KEPT: audio-synced timeline, narration-beat hard cuts, transitions,
  transition SFX (moderate), camera push/pull/drift motion.
- REMOVED: face/hand/body/lip-sync/puppet-warp/object-action animation.
  Legacy animation code is NOT in this build (originals stay in
  `~/workspace/rendering-studio/`, archived, untouched).

## Layout
```
engine/
  run_pipeline.py      # full chain: base render -> transitions -> verify
  render_base.py       # sync-timeline base renderer (no SFX)
  verify_output.py     # ffprobe + audio + cut checks + contact sheet
  requirements.txt
transition_pack/
  pack.json            # 136 clips manifest (82 blacklisted -> 54 clean usable)
  auto_transition.py   # automatic transition overlay engine (deterministic)
  build_pack.py        # pack rebuild script (playlist -> pack.json)
  make_keyed_assets.py # pre-keyed transparent asset builder (re-runnable)
  PACK_README.md
  raw/                 # 136 transition clips (green/screen) — legacy runtime chromakey
  assets/              # 54 PRE-KEYED transparent clips (PNG-in-MOV, rgba) — NEW
  assets_manifest.json # clip_id -> asset path, keying params, slice offsets — NEW
  audio_norm/          # loudnormed SFX audio (I=-18:TP=-1.5:LRA=11)
docs/
  BUILD_README.md      # yeh file
  REPORT_PACK_V1_2026-09-21.md   # pack v1 verification report
archive/
  README.md            # kya exclude/archive hua aur kyun
```

## Requirements
- Python 3.10+, `pip install -r engine/requirements.txt`
- ffmpeg + ffprobe on PATH (`ffmpeg -version`)

## Chalana (full pipeline)
```bash
cd <unzipped build>
pip install -r engine/requirements.txt
python3 engine/run_pipeline.py \
  --images  my_images/ \
  --segments transcript.json \
  --plan    plan.json \
  --audio   narration.wav \
  --out     final.mp4
```

## Inputs
- `my_images/`: JPG/PNG stills (koi bhi resolution; 1920x1080 par fit hongi).
- `transcript.json`: `{"segments": [{"start": 0.0, "end": 2.5}, ...]}`
  (faster-whisper ke `analysis.json` jaisa format; seconds mein).
- `plan.json`: `{"scenes": [{"segment_index": 0, "image": "img_01.jpg"}, ...]}`
  - har segment ke liye 1 entry = poora segment us image par
  - 2 entries = segment aadha-aadha (beech mein hard cut)
  - `"image"` images dir ka filename hai
- `narration.wav`: master narration audio (timeline isi ki duration par banti hai).

## Output
- `final.mp4`: 1920x1080, 30fps, H.264 yuv420p, AAC 48kHz stereo,
  duration == narration audio. Har scene cut par 1.2s flare/flash
  transition + (jahan clip audio usable ho) moderate SFX mix.
- `work/scene_labels.json`: per-scene cuts/motion (auto_transition input).
- `work/contact_sheet.png`: visual QA sheet.

## Step-by-step (manual)
```bash
# 1. base (sync timeline + camera motion, no SFX)
python3 engine/render_base.py --images my_images/ --segments transcript.json \
  --plan plan.json --audio narration.wav --out work/base.mp4 --workdir work

# 2. transitions (pack dir se chalana ZAROORI hai — clip paths relative hain)
cd transition_pack
python3 auto_transition.py --scenes ../work/scene_labels.json --pack pack.json \
  --base ../work/base.mp4 --out ../final.mp4 --overlay-dur 1.2
cd ..

# 3. verify
python3 engine/verify_output.py --video final.mp4 \
  --scenes work/scene_labels.json --sheet work/contact_sheet.png
```

## Pack rebuild (optional)
Nayi playlist se pack dobara banana ho to:
```bash
cd transition_pack
yt-dlp -f 18 --write-info-json ... -o "raw/%(id)s.%(ext)s" "<playlist>"
python3 build_pack.py --raw raw --out .
```
Detail `PACK_README.md` mein.

## Pre-keyed assets (NEW — 2026-09-21, v3 update)
`transition_pack/assets/` mein **47 clean** clips ke **pehle se keyed transparent
assets** hain (PNG video in MOV, `rgba` — alpha verified, not dropped):
- Keying: **adaptive per-clip background sampling** (v2 fix) — har clip ka asal
  bg color sample karke usi par chromakey + per-clip similarity sweep. V1 ka fixed
  `0x00FF00:0.15` compression-shifted greens par fail ho raha tha (alpha residue
  232); adaptive se bg alpha ~5, 91%+ transparent. White/yellow content mehfooz.
- Black-bg clips: `lumakey` se black→transparent (uniform alpha compositing).
- Har asset sirf wohi 3.2s window hai jo renderer ka 1.2s slice use karta hai
  (+1s margin each side).
- `assets_manifest.json`: clip_id → asset path, keying params, `asset_start`
  (renderer is offset se seek karega), `slice_start`, size. Removed clips
  `"removed"` list mein reason ke saath documented hain.
- Assets **video-only** hain; SFX audio `audio_norm/` se aayegi (wiring next step).
- Dobara banana ho: `cd transition_pack && python3 make_keyed_assets.py`.

## Removed clips (user instruction 2026-09-21 — koi text/logo/watermark/CTA nahi)
4 user-flagged + 3 visual-sweep finds — assets deleted, `pack.json` blacklisted:
- `KihWHqHelbM` — "The Green Screen of world" watermark
- `6kUs1A4YQJc` — baked-in "LIKE & SUBSCRIBE" CTA
- `6n7na1hi06E` — baked-in "STA" logo
- `aVyuFZFbLx4` — baked-in Arabic subscribe-CTA text
- `JwcVCRxsC_0` — baked-in large 3D text/logo intro (sweep find)
- `Kpf4njh5VDs` — "G" logo watermark bottom-right (sweep find)
- `vsN2ChU4fqo` — "SR" logo watermark near center (sweep find)
Sweep method: 50 assets x 4 frames (10/40/65/90% — CTA aksar end mein aata hai),
5 contact sheets, har frame aankhon se inspect kiya.

## Caveats (imaandaar)
- Pack ke 136 clips 640x360 (YouTube format 18) hain; upscale hokar overlay hote hain.
- 89 clips blacklist hain (end-screens/CTAs/logos/watermarks: 82 purane + 7 is round
  mein removed — details `pack.json` blacklist_reason mein) — 47 clean clips
  active rotation mein.
- Pre-keyed assets ab `assets/` mein hain — renderer wiring (assets ko
  auto_transition mein use karna) agla step hai, is build mein nahi.
- VP9/AV1/ffv1 is environment mein alpha drop karte hain — is liye assets PNG-in-MOV
  (rgba) hain: 54 assets = ~258MB (raw 136 clips = ~348MB; keyed windows chhote hain
  is liye total raw se kam hai).
- 11 playlist entries YouTube 429/bot-check par download nahi ho saki thin.
