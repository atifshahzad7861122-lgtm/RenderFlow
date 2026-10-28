#!/usr/bin/env python3
"""
Rendering Studio Engine v2 — sync-timeline base renderer (sync-only, NO SFX).

Kya karta hai:
  1. Narration transcript (whisper-style segments) + image->segment plan se
     audio-synced timeline banata hai. Har narration beat par hard cut.
  2. Har scene par subtle 2.5D camera-depth motion (push/pull/drift cycle).
  3. Scenes concat karke narration audio as-is mux karta hai.

Scope (Atif, 2026-09-21): character/face/hand/body animation REMOVED.
Sirf synced timeline + transitions + transition-SFX + camera-depth motion.
Transitions + unki SFX auto_transition.py lagata hai (is base par).

CLI:
  python3 render_base.py --images IMG_DIR --segments transcript.json \\
      --plan plan.json --audio narration.wav --out base.mp4 [--workdir DIR]

Input formats:
  transcript.json: {"segments": [{"start": 0.0, "end": 2.5, ...}, ...]}
                   (faster-whisper analysis.json jaisa; start/end seconds mein)
  plan.json:       {"scenes": [{"segment_index": 0, "image": "img_01.jpg"}, ...]}
                   - har segment ke liye 1 entry = poora segment us image par
                   - 2 entries = segment aadha-aadha dono images par (hard cut beech mein)
                   - "image" images dir ka filename hai

Output: 1920x1080, 30fps, H.264 yuv420p, AAC 48kHz stereo, duration == audio.
Saath mein <workdir>/scene_labels.json likhta hai (auto_transition.py ke liye).
"""
import argparse, json, subprocess, sys
from pathlib import Path

import numpy as np
import cv2

W, H, FPS = 1920, 1080, 30
MODES = ['push', 'pull', 'drift_right', 'drift_left']

# Cinematographic easing functions (zero initial/final velocity for smooth starts and stops)
EASING_FUNCTIONS = {
    'linear': lambda u: u,
    'smoothstep': lambda u: 3.0 * (u ** 2) - 2.0 * (u ** 3),
    'cubic_in_out': lambda u: 4.0 * (u ** 3) if u < 0.5 else 1.0 - ((-2.0 * u + 2.0) ** 3) / 2.0,
    'ease_out': lambda u: 1.0 - ((1.0 - u) ** 3),
    'ease_in': lambda u: u ** 3,
}

def apply_easing(u: float, curve: str = 'smoothstep') -> float:
    """Evaluates a normalized time parameter u in [0.0, 1.0] under a named easing curve."""
    u_clamped = max(0.0, min(1.0, float(u)))
    fn = EASING_FUNCTIONS.get(curve, EASING_FUNCTIONS['smoothstep'])
    return float(fn(u_clamped))


def load_segments(path):
    d = json.load(open(path))
    segs = d['segments'] if isinstance(d, dict) else d
    segs = [{'start': float(s['start']), 'end': float(s['end'])} for s in segs]
    assert len(segs) >= 1 and segs[0]['start'] >= 0
    return segs


def load_plan(path):
    d = json.load(open(path))
    scenes = d['scenes'] if isinstance(d, dict) else d
    assign = {}
    for s in scenes:
        # optional 'context': normal|story_change|location_change|time_passage|
        #                   turning_point|emotional|fast (transition intelligence)
        entry = {
            'image': str(s['image']),
            'context': str(s.get('context', '') or ''),
            'motion': str(s.get('motion', '') or ''),
            'motion_mode': str(s.get('motion_mode', '') or ''),
            'shot_role': str(s.get('shot_role', '') or ''),
            'easing': str(s.get('easing', '') or ''),
            'zoom_scale': float(s.get('zoom_scale', 0.0) or 0.0),
            'pan_speed': float(s.get('pan_speed', 0.0) or 0.0),
        }
        assign.setdefault(int(s['segment_index']), []).append(entry)
    return assign


def audio_duration(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                        'format=duration', '-of',
                        'default=noprint_wrappers=1:nokey=1', str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def build_timeline(segs, assign, master_dur):
    t_end = segs[-1]['end']
    scale = master_dur / t_end
    scenes, t = [], 0.0
    for i, sg in enumerate(segs):
        w = (sg['end'] - sg['start']) * scale
        entries = assign.get(i)
        if not entries:
            raise ValueError(f'segment {i}: plan mein koi image nahi')
        if len(entries) > 2:
            raise ValueError(f'segment {i}: max 2 images, mili {len(entries)}')
        for e in entries:
            scenes.append({
                'scene_id': f'sync_{len(scenes)+1:04d}',
                'seg': i,
                'img': e['image'],
                'context': e.get('context', ''),
                'motion': e.get('motion', ''),
                'motion_mode': e.get('motion_mode', ''),
                'shot_role': e.get('shot_role', ''),
                'easing': e.get('easing', ''),
                'zoom_scale': e.get('zoom_scale', 0.0),
                'pan_speed': e.get('pan_speed', 0.0),
                'start': t,
                'dur': w / len(entries)
            })
            t += w / len(entries)
    scenes[-1]['dur'] = master_dur - scenes[-1]['start']
    total_f = round(master_dur * FPS)
    ft = 0
    for s in scenes:
        s['f0'] = ft
        ft = round((s['start'] + s['dur']) * FPS)
        s['n'] = ft - s['f0']
    # frame budget fix: last scene absorb kare
    diff = total_f - ft
    scenes[-1]['n'] += diff
    scenes[-1]['dur'] = scenes[-1]['n'] / FPS
    return scenes


def render_scene(scene, img, idx, out_path):
    """L4 camera motion with non-linear easing curves: push/pull/drift. Koi part animation nahi."""
    n = scene['n']
    raw_mode = scene.get('motion_mode') or scene.get('motion')
    if raw_mode and isinstance(raw_mode, str):
        cleaned_mode = raw_mode.split('/')[-1].strip()
        mode = cleaned_mode if cleaned_mode in MODES else MODES[idx % len(MODES)]
    else:
        mode = MODES[idx % len(MODES)]

    # Extract or default cinematographic easing & scale parameters
    easing_curve = scene.get('easing') or 'smoothstep'
    z_target = float(scene.get('zoom_scale', 0.0) or 0.0)
    pan_target = float(scene.get('pan_speed', 0.0) or 0.0)

    # Base scale parameters if not explicitly overridden
    if z_target <= 1.0:
        z_target = 1.035 if mode in ['push', 'pull'] else 1.030
    if abs(pan_target) < 1e-3:
        pan_target = 24.0

    cmd = ['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
           '-s', f'{W}x{H}', '-framerate', str(FPS), '-i', '-',
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    for t in range(n):
        u_lin = 0.0 if n <= 1 else t / (n - 1)
        u = apply_easing(u_lin, easing_curve)
        if mode == 'push':
            z, tx = 1.0 + (z_target - 1.0) * u, 0.0
        elif mode == 'pull':
            z, tx = z_target - (z_target - 1.0) * u, 0.0
        elif mode == 'drift_right':
            half_p = pan_target / 2.0
            z, tx = z_target, -half_p + (2.0 * half_p) * u
        elif mode == 'drift_left':
            half_p = pan_target / 2.0
            z, tx = z_target, half_p - (2.0 * half_p) * u
        else:  # static
            z, tx = 1.0, 0.0
        M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, z)
        M[0, 2] += tx
        fr = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_REPLICATE)
        proc.stdin.write(fr.tobytes())
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f'scene render failed: {scene["scene_id"]}')
    return mode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--images', required=True)
    ap.add_argument('--segments', required=True)
    ap.add_argument('--plan', required=True)
    ap.add_argument('--audio', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workdir', default=None)
    ap.add_argument('--master-duration', type=float, default=None,
                    help='default: narration audio ki duration')
    args = ap.parse_args()

    img_dir = Path(args.images)
    work = Path(args.workdir) if args.workdir else Path(args.out).parent / 'work'
    scenes_dir = work / 'scenes'
    scenes_dir.mkdir(parents=True, exist_ok=True)

    segs = load_segments(args.segments)
    assign = load_plan(args.plan)
    master_dur = args.master_duration or audio_duration(args.audio)
    scenes = build_timeline(segs, assign, master_dur)
    print(f'scenes: {len(scenes)}, master: {master_dur:.3f}s, '
          f'frames: {sum(s["n"] for s in scenes)}', flush=True)

    img_cache = {}
    failed = []  # PLACEHOLDER PROTECTION (§16): fail list, kabhi substitute nahi
    for sc in scenes:
        name = sc['img']
        if name not in img_cache:
            p = img_dir / name
            im = cv2.imread(str(p)) if p.is_file() else None
            if im is None:
                # HARD RULE: valid source image hai to USE karo; decode fail ho
                # to LOUDLY fail karo — kabhi placeholder/block se replace nahi.
                failed.append(name)
                print(f'!!! IMAGE DECODE FAILED: {p}', flush=True)
                continue
            if im.size == 0 or min(im.shape[:2]) < 8:
                failed.append(name)
                print(f'!!! IMAGE DEGENERATE: {p} shape={im.shape}', flush=True)
                continue
            img_cache[name] = cv2.resize(im, (W, H))
    if failed:
        # fail loudly — placeholder kabhi nahi
        raise RuntimeError(
            f'{len(failed)} image(s) decode nahi hui — placeholder se replace '
            f'nahi kiya (§16). Failed: {failed}')

    pose_info = []
    for idx, sc in enumerate(scenes):
        out = scenes_dir / f"{sc['scene_id']}.mp4"
        mode = render_scene(sc, img_cache[sc['img']], idx, out)
        pose_info.append({'scene_id': sc['scene_id'], 'img': sc['img'],
                          'dur': round(sc['dur'], 3), 'frames': sc['n'],
                          'label': 'L4', 'motion': mode,
                          'transition_in': 'hard_cut',
                          'context': sc.get('context', ''),
                          'start_s': round(sc['start'], 3)})
        print(f"[{idx+1:02d}/{len(scenes)}] {sc['scene_id']} {sc['img']} "
              f"{sc['dur']:.2f}s {sc['n']}f L4/{mode}", flush=True)

    labels = work / 'scene_labels.json'
    json.dump({'scenes': pose_info}, open(labels, 'w'), indent=1)
    print('scene_labels:', labels, flush=True)

    lst = work / 'concat.txt'
    lst.write_text(''.join(f"file '{scenes_dir/sc['scene_id']}.mp4'\n"
                           for sc in scenes))
    silent = work / 'silent_concat.mp4'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0',
                    '-i', str(lst), '-c', 'copy', str(silent)], check=True)
    out = Path(args.out)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(silent),
                    '-i', str(args.audio),
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                    '-ar', '48000', '-ac', '2', '-shortest', str(out)],
                   check=True)
    print('wrote', out, flush=True)


if __name__ == '__main__':
    main()
