# Archive / Excluded notes — Engine v2 build (2026-09-21)

Is build mein SIRF active pipeline hai. Neeche wali cheezein EXCLUDE hain
(delete nahi hui — originals `~/workspace/rendering-studio/` mein mehfooz hain):

## Excluded (legacy / out of scope)
- `execution/` (12 system packages), `app.py`, `ui/`, `run_studio.bat` —
  purana animation engine + UI. Atif ne 2026-09-21 ko character/face/hand/
  body/object animation scope se nikaal diya; sirf sync+transitions+SFX+
  camera-motion active hai.
- `audio_analysis_test/final_sync_v1/archive_parts/` — puppet-warp aur
  legacy whoosh/impact SFX stage (pehle hi archive ho chuke thay).
- `audio_analysis_test/final_pack_v1/archive_parts/` — legacy SFX stage archive.
- `transition_pack/curate/`, `*.log`, `download*.log`, `playlist_ids.txt`,
  `ids_only.txt`, `PACK_SUMMARY.txt`, `__pycache__` — build-time working files.
- `transition_pack/raw/*.part` — stale incomplete downloads (deleted in build).
- Test fixtures (`gemini_images/`, `clip_2min.wav`, whisper `analysis.json`,
  `ai_sync_plan.json`, scene mp4s) — ye build generic CLI leta hai, fixture
  hardcode nahi.

## Kya generalize kiya gaya
- `final_sync_v1/render_sync_v1.py` + `final_pack_v1/render_clean_base.py`
  (dono test-fixture hardcoded thay) -> `engine/render_base.py`
  (generic CLI: --images/--segments/--plan/--audio/--out).
  Algorithm same hai (verified renders se liya gaya): whisper-scale timeline,
  1-ya-2 images per segment, push/pull/drift camera motion, concat + mux.
- `transition_pack/auto_transition.py` unchanged (pehle se generic CLI tha).
- `engine/verify_output.py` naya: ffprobe + audio + cut-diff + contact sheet.
- `engine/run_pipeline.py` naya: teenon steps ko jorta hai.
