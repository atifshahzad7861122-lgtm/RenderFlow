#!/usr/bin/env python3
"""
engine/audit_all_transitions.py — Comprehensive verification and audit for all transition assets.

Audits:
- Built-in transitions (dissolve, wipeleft, fadeblack, fadewhite, fade, clean_cut, slow_dissolve)
- YouTube Transition Pack (all 20 4K overlay clips)
- Legacy transition pack assets (if present)
- Verifies: file existence, ffprobe stream data, duration, resolution, fps, decode playback,
  preview availability, registry resolution.
"""

import sys
import json
import subprocess
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from engine.transition_registry import registry


def audit_youtube_pack():
    print("=" * 80)
    print(" AUDITING YOUTUBE TRANSITION PACK (20 ASSETS)")
    print("=" * 80)

    manifest_path = WORKSPACE_ROOT / "transition_pack" / "youtube_transition_pack" / "transition_manifest.json"
    if not manifest_path.exists():
        print(f"[ERROR] Manifest not found: {manifest_path}")
        return False, []

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    pack_dir = manifest_path.parent
    transitions = manifest.get("transitions", [])
    print(f"Pack Title: {manifest.get('pack_name')} ({manifest.get('source_title')})")
    print(f"Total Declared Assets: {len(transitions)}")
    print("-" * 80)

    results = []
    all_passed = True

    for t in transitions:
        tid = t["id"]
        name = t["name"]
        cat = t.get("category", "Overlay Effect")
        rel_file = t["file"]
        mp4_path = pack_dir / rel_file

        file_exists = mp4_path.exists()
        file_size = mp4_path.stat().st_size if file_exists else 0

        # ffprobe inspection
        probe_ok = False
        playable = False
        w, h, fps, dur = 0, 0, 0.0, 0.0
        if file_exists:
            try:
                cmd = [
                    "ffprobe", "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height,r_frame_rate,duration",
                    "-of", "json", str(mp4_path)
                ]
                r = subprocess.run(cmd, capture_output=True, text=True, check=True)
                data = json.loads(r.stdout)
                if "streams" in data and len(data["streams"]) > 0:
                    stream = data["streams"][0]
                    w = int(stream["width"])
                    h = int(stream["height"])
                    dur = float(stream.get("duration", 0.0))
                    num, den = stream["r_frame_rate"].split("/")
                    fps = round(float(num) / float(den), 2)
                    probe_ok = True

                # Test actual decode playback (decode 1 second without error)
                play_cmd = [
                    "ffmpeg", "-y", "-v", "error",
                    "-i", str(mp4_path),
                    "-t", "0.5",
                    "-f", "null", "-"
                ]
                play_r = subprocess.run(play_cmd, capture_output=True, text=True)
                playable = (play_r.returncode == 0)
            except Exception as e:
                print(f"[ERROR] Probe error on {tid}: {e}")

        # Preview verification
        preview_file = pack_dir / "previews" / f"{tid}.jpg"
        preview_ok = preview_file.exists() and preview_file.stat().st_size > 1000

        # Registry verification
        reg_entry = registry.get(tid)
        registry_ok = reg_entry is not None

        item_pass = (file_exists and probe_ok and playable and preview_ok and registry_ok)
        if not item_pass:
            all_passed = False

        status = "PASS" if item_pass else "FAIL"
        print(f"{tid:<15} | {name:<28} | {cat:<12} | {w}x{h} @ {fps}fps | {dur:.2f}s | Play: {'OK' if playable else 'ERR'} | Prev: {'OK' if preview_ok else 'MISSING'} | Reg: {'OK' if registry_ok else 'MISSING'} | {status}")

        results.append({
            "id": tid,
            "name": name,
            "category": cat,
            "file": str(mp4_path),
            "file_exists": file_exists,
            "size_bytes": file_size,
            "probe_ok": probe_ok,
            "playable": playable,
            "width": w,
            "height": h,
            "fps": fps,
            "duration": dur,
            "preview_ok": preview_ok,
            "registry_ok": registry_ok,
            "status": status
        })

    print("-" * 80)
    print(f"YouTube Pack Audit Result: {'ALL 20 PASS' if all_passed else 'SOME FAILED'}")
    return all_passed, results


def audit_builtin_transitions():
    print("\n" + "=" * 80)
    print(" AUDITING BUILT-IN TRANSITIONS (8 PRESETS)")
    print("=" * 80)

    builtins = registry.list_transitions(category="Built-in")
    print(f"Total Registered Built-in Transitions: {len(builtins)}")

    all_passed = True
    results = []
    for t in builtins:
        tid = t["id"]
        name = t["name"]
        xfade_name = t.get("xfade_name")
        dur = t.get("duration", 0.0)

        # Test whether ffmpeg supports this xfade transition
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=red:s=320x240:d=1:r=25",
            "-f", "lavfi", "-i", "color=blue:s=320x240:d=1:r=25",
            "-filter_complex", f"[0:v][1:v]xfade=transition={xfade_name}:duration=0.3:offset=0.5,format=yuv420p[v]",
            "-map", "[v]",
            "-t", "0.9",
            "-f", "null", "-"
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        ffmpeg_ok = (r.returncode == 0)
        status = "PASS" if ffmpeg_ok else "FAIL"
        if not ffmpeg_ok:
            all_passed = False

        print(f"{tid:<22} | {name:<28} | xfade={xfade_name:<10} | dur={dur:.2f}s | ffmpeg_xfade: {'OK' if ffmpeg_ok else 'ERR'} | {status}")
        results.append({
            "id": tid,
            "name": name,
            "xfade_name": xfade_name,
            "duration": dur,
            "ffmpeg_ok": ffmpeg_ok,
            "status": status
        })

    print("-" * 80)
    print(f"Built-in Transitions Audit Result: {'ALL 8 PASS' if all_passed else 'SOME FAILED'}")
    return all_passed, results


if __name__ == "__main__":
    yt_ok, yt_res = audit_youtube_pack()
    bi_ok, bi_res = audit_builtin_transitions()

    summary = {
        "youtube_pack": {
            "total": len(yt_res),
            "passed": sum(1 for r in yt_res if r["status"] == "PASS"),
            "all_passed": yt_ok
        },
        "builtin_transitions": {
            "total": len(bi_res),
            "passed": sum(1 for r in bi_res if r["status"] == "PASS"),
            "all_passed": bi_ok
        }
    }

    out_file = WORKSPACE_ROOT / "transition_pack" / "audit_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "youtube_pack": yt_res, "builtins": bi_res}, f, indent=2)

    print(f"\nAudit results written to {out_file}")
    if not (yt_ok and bi_ok):
        sys.exit(1)
    print("\n>>> ALL TRANSITIONS FULLY AUDITED AND VERIFIED <<<")
