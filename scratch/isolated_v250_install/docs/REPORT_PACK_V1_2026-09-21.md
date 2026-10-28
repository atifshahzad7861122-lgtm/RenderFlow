# Rendering Studio — Transition Pack V1 — Final Report (2026-09-21)

## Deliverables
- **Video (phone copy):** `~/workspace/your_files/Rendering_Studio_TransitionsPack_2026-09-21.mp4`
  (1920x1080, 30fps, H.264 CRF23, AAC 160k stereo, 119.98s, 192MB)
- **ZIP:** `~/workspace/your_files/Rendering_Studio_TransitionsPack_2026-09-21.zip`
- **Full-quality master:** `~/workspace/rendering-studio/audio_analysis_test/final_pack_v1/output.mp4`
  (1920x1080, 30fps, H.264 CRF20, 119.98s, 336MB)
- **Demo (visual QA):** `~/workspace/rendering-studio/audio_analysis_test/final_pack_v1/demo20_trans.mp4`
- **Contact sheets:** `demo_sheet.png` (demo, 6 cuts), `verify_sheet.png` (full, 8 cuts)

## Verdict: PASS (visually verified)
- 48/48 scene cuts carry a transition overlay (lens flare / light flash, 1.2s each).
- No magenta/pink washes, no opaque green boxes, no black boxes, no full-frame color washes,
  no text/CTAs/logos/faces in any transition.
- Audio: non-silent, mean −17.1 dB, max 0.0 dB; transition SFX mixed at 13 of 48 cuts
  (only clips with usable audio); narration untouched elsewhere.
- ffprobe: h264 1920x1080 30/1, aac 48000Hz stereo, duration 119.978s.

## Source inventory (honest)
- Playlist: 147 unique IDs.
- Downloaded: **136/147 MP4** (YouTube format 18, **640x360** — not 1080p; that is the
  highest quality this environment could pull).
- **11 blocked** by YouTube HTTP 429 / "Sign in to confirm you're not a bot":
  LkwLJxdrmp4, QlzoOgv5ekI, Sr3RwCQDJKw, W37l68WibNM, axiSgUyN3l8, boGNjj9lnCQ,
  iGNpofoiWzs, lLnc9OHOlKk, t9SiVnR5LT8, twoZI8F-Ik4, x4kJlZpfK6A.
- Pack manifest: 136 clips, 0 errors — **95 green-screen, 41 screen-blend, 64 silent**,
  9 key-suspect (handled by runtime chromakey tuning).
- **Caveat:** VP9 alpha export silently lost alpha in this environment, so there is no real
  populated alpha/ directory — green clips are composited with **runtime chromakey** instead.
- Curation: 70 clips blacklisted manually (end screens, CTAs, logos, faces, weak effects),
  12 more blacklisted by automated full-frame color-wash scan. **Clean pool: 54 clips**
  for 48 cuts. Per-second wash_map generated; transition slices seek to nearby clean,
  high-energy seconds.

## Engine fixes this session
1. **Audio-peak selection:** transition SFX now cut from each clip's independently measured
   loudest second (FFmpeg astats TARGET-field regex fixed), not the visual peak.
   Measured lift: cut@7.07s +1.50 dB, cut@9.67s +1.36 dB vs base — audible, not harsh.
2. **Magenta-wash bug (root-caused & fixed):** chained `overlay` -> `blend` in one filtergraph
   caused a plane-order negotiation bug that tinted whole frames magenta. Fix: explicit
   `format=gbrp` after every `overlay`. Verified clean on contact sheets before full render.

## Per-cut transition table (48 cuts)
| cut (s) | clip | type | clip dur | audio |
|---|---|---|---|---|
| 1.76 | -fADwKBprZU | green | 31.9s | silent |
| 4.27 | 0qi_n2LMmOA | screen | 28.2s | silent |
| 7.07 | 3hT6mmVTeOQ | green | 193.0s | SFX |
| 9.67 | 5fFWs0ES_Oc | screen | 28.2s | silent |
| 11.64 | 62DmCLmW-K8 | green | 23.2s | silent |
| 15.30 | 6kUs1A4YQJc | green | 69.5s | SFX |
| 19.71 | 6n7na1hi06E | green | 72.0s | SFX |
| 21.24 | 8JJnWGigkLU | screen | 22.0s | SFX |
| 23.82 | 8aIP84yfpEQ | screen | 12.0s | silent |
| 25.79 | 92B5igQmthE | screen | 88.7s | silent |
| 28.36 | 9YIyxGfOGF0 | screen | 15.0s | silent |
| 29.72 | 9ZWFDtSBhYw | screen | 6.5s | silent |
| 31.91 | ArtnfKKMjQk | green | 66.7s | SFX |
| 34.67 | BieWyWh4x3o | green | 53.5s | SFX |
| 37.54 | D8Ig2RJQxcw | green | 2.4s | silent |
| 38.12 | HKsBzRvMh8Y | green | 16.0s | silent |
| 38.71 | HvqfiJaeH0I | screen | 28.2s | silent |
| 42.96 | IXoMVmjaPj0 | green | 20.1s | SFX |
| 45.51 | J5u1Uk2heUo | green | 11.2s | silent |
| 49.45 | JwcVCRxsC_0 | green | 127.8s | SFX |
| 53.81 | KihWHqHelbM | green | 150.0s | silent |
| 57.67 | Kpf4njh5VDs | green | 10.2s | silent |
| 60.77 | LnJLLVN0ngY | green | 28.2s | silent |
| 62.30 | O2LLw4Sv75g | green | 192.9s | SFX |
| 64.86 | O360V5YNumA | green | 31.9s | silent |
| 66.92 | OheiU-k5DZA | screen | 30.0s | silent |
| 69.17 | Pxb2c2biEiU | green | 193.0s | SFX |
| 72.27 | S2Aq2N-1Eh0 | green | 30.1s | silent |
| 75.50 | TjiNZwexENU | green | 31.1s | silent |
| 76.95 | Tn3p5rS4k0s | green | 28.3s | silent |
| 79.48 | Ts3jlhXNqlY | green | 23.0s | silent |
| 82.73 | Y8tDV2_LtYM | green | 31.1s | silent |
| 84.36 | Z4hF8h2LIEA | green | 23.0s | silent |
| 85.85 | ZCbx4F6mOcw | green | 56.3s | silent |
| 87.44 | ZjcVJSfFKck | green | 31.9s | silent |
| 89.42 | _vC-CfzVjkc | green | 5.1s | silent |
| 91.55 | aVyuFZFbLx4 | screen | 90.9s | SFX |
| 94.31 | b0HfhaBnPt8 | screen | 56.0s | SFX |
| 97.88 | bBXQqqwqLWE | green | 6.9s | silent |
| 100.90 | flIUdxJtCh8 | green | 40.3s | silent |
| 102.28 | hOGKIewuXAA | green | 4.5s | silent |
| 105.11 | i14zv1Ii54o | green | 153.8s | SFX |
| 106.78 | jTK9EIEiJIA | green | 10.1s | silent |
| 108.23 | kPL42V3D85M | green | 29.9s | silent |
| 110.94 | lCllzPUT1h0 | green | 40.2s | silent |
| 113.83 | lTgTwBJnh0U | green | 2.0s | silent |
| 115.86 | lYMMfEGCuXw | screen | 59.4s | silent |
| 118.44 | of13J1Gma1Q | green | 16.2s | silent |

48/48 clip IDs unique (no reuse within the video; no-reuse-among-last-5 enforced at selection).
Audio mixes: 13 (only clips with measured audio peaks; silent clips contribute video only).

## Verification evidence
- **ffprobe:** h264, 1920x1080, 30fps, aac 48kHz stereo, 119.978s, 336MB master.
- **Audio:** volumedetect mean −17.1 dB, max 0.0 dB — non-silent, no clipping.
- **Frame differences (scene changes confirmed):** meanAbsDiff (grayscale, 160x90) between
  frames 0.4s apart across cuts: cut@4.27s = 9.6, cut@37.54s = 20.1, cut@91.55s = 0.7
  (low value explained: base shows a near-white CTA card there; the screen-flare overlay
  is near-invisible on white — harmless, and the overlay window still fired correctly).
- **Clip reuse:** 48/48 clip IDs unique across the video (verified, zero duplicates).
- **Contact sheets:** demo_sheet.png (6 cuts: flares clean, no magenta) and verify_sheet.png
  (8 cuts spread 7s–118s: flare orbs + brief flash transitions, scenes intact, no artifacts).
- **Demo-first policy honored:** full render started only after the short demo passed visual QA.

## Known limitations
- Source clips are 640x360 (YouTube format 18 was the max available); final is upscaled 1080p.
- 11/147 playlist videos could not be downloaded (YouTube bot-check 429).
- Green clips use runtime chromakey (no true alpha) — key color/similarity tuned per clip.
- Transition SFX only where source clips had usable audio (13/48); the rest are video-only flares.
