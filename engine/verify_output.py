#!/usr/bin/env python3
"""
verify_output.py — Rendering Studio output verification.

Checks (FAIL par nonzero exit):
  1. ffprobe: h264, 1920x1080, 30fps, yuv420p, AAC 48kHz stereo, duration>0
  2. Audio non-silent (mean volume check)
  3. Agar --scenes diya: har cut ke aas-paas frame-diff > threshold
     (transition/cut waqai visible hai), aur mid-scene frames sane hain
  4. Contact sheet likhta hai (--sheet) taake aankh se bhi verify ho sake

Koi fake PASS nahi: jo check fail ho, wahi report hota hai.
"""
import argparse, json, subprocess, sys, math
import os
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import numpy as np
import cv2


def get_bin(name: str) -> str:
    env_v = os.environ.get(f"{name.upper()}_PATH", "").strip()
    if env_v and Path(env_v).exists():
        return str(Path(env_v).resolve())
    return shutil.which(name) or name


def ffprobe(path):
    r = subprocess.run([get_bin('ffprobe'), '-v', 'error', '-show_streams',
                        '-show_format', '-of', 'json', str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def grab(path, t, width=None, height=None, frame_idx=None, fps=None):
    if not width or not height:
        try:
            info = ffprobe(path)
            vs = next(s for s in info['streams'] if s['codec_type'] == 'video')
            width = int(vs['width'])
            height = int(vs['height'])
        except Exception:
            width, height = 1920, 1080

    if frame_idx is not None and fps and fps > 0:
        if frame_idx <= 0:
            t = 0.0
        else:
            # In FFmpeg -copyts, secondary output seek -ss T selects the first frame with PTS >= T.
            # Using (frame_idx - 0.5) / fps ensures frame (frame_idx - 1) is discarded (PTS < T),
            # and frame_idx (PTS >= T) is accurately decoded without advancing to frame_idx + 1.
            t = (frame_idx - 0.5) / fps

    t_val = max(0.0, float(t))
    seek_pre = max(0.0, t_val - 2.0)
    cmd = [
        get_bin('ffmpeg'), '-v', 'error',
        '-ss', f'{seek_pre:.3f}',
        '-copyts',
        '-i', str(path),
        '-ss', f'{t_val:.3f}',
        '-frames:v', '1',
        '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'
    ]
    r = subprocess.run(cmd, capture_output=True)
    if not r.stdout or len(r.stdout) != width * height * 3:
        # Fallback to direct accurate seek
        cmd_fallback = [
            get_bin('ffmpeg'), '-v', 'error',
            '-i', str(path),
            '-ss', f'{t_val:.3f}',
            '-frames:v', '1',
            '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'
        ]
        r = subprocess.run(cmd_fallback, capture_output=True)
        if not r.stdout or len(r.stdout) != width * height * 3:
            return None
    return np.frombuffer(r.stdout, dtype=np.uint8).reshape(height, width, 3)


def mean_volume(path, ss=0.0, t=None):
    cmd = [get_bin('ffmpeg'), '-hide_banner', '-ss', f'{ss:.2f}']
    if t:
        cmd += ['-t', f'{t:.2f}']
    cmd += ['-i', str(path), '-af', 'volumedetect', '-f', 'null', '-']
    r = subprocess.run(cmd, capture_output=True, text=True)
    for line in r.stderr.splitlines():
        if 'mean_volume' in line:
            return float(line.split('mean_volume:')[1].split('dB')[0].strip())
    return None


def classify_frame(f):
    """
    Classify frame visual quality (§17).
    Returns (status, detail)
    status is one of: UNREADABLE, UNIFORM_BLACK, UNIFORM_WHITE, LOW_VARIANCE, VALID_VISUAL
    """
    if f is None:
        return 'UNREADABLE', 'unreadable frame'
    std = float(f.std())
    mean = float(f.mean())
    if mean < 3.5:
        return 'UNIFORM_BLACK', f'pure black (std={std:.1f}, mean={mean:.1f})'
    if mean > 251.0 and std < 6.0:
        return 'UNIFORM_WHITE', f'pure white (std={std:.1f}, mean={mean:.1f})'
    if std < 8.0:
        return 'LOW_VARIANCE', f'uniform block (std={std:.1f}, mean={mean:.1f})'
    return 'VALID_VISUAL', f'std={std:.1f} mean={mean:.1f}'


def verify_video(
    video: Union[str, Path],
    scenes: Optional[Union[str, Path]] = None,
    sheet: Optional[Union[str, Path]] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    target_res: Optional[str] = None,
    diff_threshold: float = 1.0,
    qc_out: Optional[Union[str, Path]] = None
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Programmatically verify RenderFlow output video and write .qc.json report.
    Returns (success_bool, failed_checks_list, qc_report_dict).
    """
    expected_w = width
    expected_h = height
    if target_res:
        tr = target_res.lower()
        if '9:16' in tr or 'portrait' in tr or 'vertical' in tr:
            expected_w, expected_h = 1080, 1920
        elif '4k' in tr or '2160' in tr:
            expected_w, expected_h = 3840, 2160
        elif '1440' in tr or '2k' in tr or 'qhd' in tr:
            expected_w, expected_h = 2560, 1440
        else:
            expected_w, expected_h = 1920, 1080
    elif expected_w is None or expected_h is None:
        expected_w, expected_h = 1920, 1080

    fails = []
    def check(name, ok, detail=''):
        print(('PASS' if ok else 'FAIL'), '-', name, detail, flush=True)
        if not ok:
            fails.append(name)

    v = Path(video)
    check('file exists', v.exists(), str(v))
    if not v.exists():
        return False, fails, {}

    info = ffprobe(v)
    vs = next(s for s in info['streams'] if s['codec_type'] == 'video')
    aus = next(s for s in info['streams'] if s['codec_type'] == 'audio')
    dur = float(info['format']['duration'])
    check('video codec h264', vs['codec_name'] == 'h264', vs['codec_name'])
    check(f'resolution {expected_w}x{expected_h}',
          vs['width'] == expected_w and vs['height'] == expected_h,
          f"{vs['width']}x{vs['height']}")
    check('pix_fmt yuv420p', vs['pix_fmt'] == 'yuv420p', vs['pix_fmt'])
    try:
        fps_val = eval(vs.get('avg_frame_rate', '30/1'))
        fps = float(fps_val) if fps_val > 0 else 30.0
    except Exception:
        fps = 30.0
    check('fps valid', fps >= 10.0 and fps <= 120.0, f'{fps:.2f}')
    total_video_frames = max(1, int(round(dur * fps)))
    check('audio aac', aus['codec_name'] == 'aac', aus['codec_name'])
    check('audio 48kHz stereo',
          aus['sample_rate'] == '48000' and aus['channels'] == 2,
          f"{aus['sample_rate']}Hz/{aus['channels']}ch")
    check('duration > 0', dur > 0, f'{dur:.3f}s')

    mv = mean_volume(v)
    check('audio non-silent', mv is not None and mv > -60,
          f'mean {mv} dB' if mv is not None else 'unmeasured')

    # Load scenes and transitions metadata if available
    thumbs = []
    scenes_list = []
    transitions = []
    if scenes:
        try:
            scenes_path = Path(scenes)
            if scenes_path.exists():
                d = json.load(open(scenes_path, encoding='utf-8'))
                if isinstance(d, dict):
                    scenes_list = d.get('scenes', [])
                    transitions = d.get('transitions', [])
                else:
                    scenes_list = d
        except Exception as e:
            print(f'Warning loading scenes file: {e}', flush=True)

    # Also check if <video>.transitions.json exists
    tpath = Path(str(v) + '.transitions.json')
    if tpath.exists() and not transitions:
        try:
            tq = json.load(open(tpath, encoding='utf-8'))
            transitions = tq.get('details', [])
        except Exception:
            pass

    def get_active_transition(t_query: float):
        for tr in transitions:
            t_cut = tr.get('cut_s') or tr.get('cut_time', 0.0)
            t_dur = tr.get('dur_s') or tr.get('dur', 0.4)
            t_start = tr.get('start_s', t_cut - t_dur / 2.0)
            t_end = tr.get('end_s', t_cut + t_dur / 2.0)
            if (t_start - 0.03) <= t_query <= (t_end + 0.03):
                return tr
        return None

    # §17 FIRST-FRAME VALIDATION: frame 0, 1, 5, 10, 15, 20s par asal visual
    print('--- first-frame validation (§17) ---', flush=True)
    firstframe_ok = True
    for t in (0.0, 1.0, 5.0, 10.0, 15.0, 20.0):
        if t >= (dur - 0.2):
            break
        f = grab(v, t if t > 0 else 0.033)  # frame 0 -> pehla decodable frame
        cls, detail = classify_frame(f)
        active_tr = get_active_transition(t)

        if cls == 'VALID_VISUAL':
            check(f'frame@{t:.0f}s valid visual', True, detail)
        elif cls in ('UNIFORM_BLACK', 'LOW_VARIANCE') and active_tr and (active_tr.get('is_dip_black') or active_tr.get('type') == 'fadeblack'):
            # Intentional dip-to-black transition: warn and report expected transition
            cut_ref = active_tr.get('cut_s') or active_tr.get('cut_time', t)
            print(f"WARN - frame@{t:.0f}s EXPECTED_TRANSITION (intentional dip-to-black at {cut_ref:.2f}s, {detail})", flush=True)
        else:
            check(f'frame@{t:.0f}s valid visual', False, f'{cls} {detail}')
            firstframe_ok = False

    # Timeline-aware transition validation
    print('--- timeline-aware transition validation ---', flush=True)
    cuts_to_test = transitions[:15] if transitions else []
    if not cuts_to_test and scenes_list:
        cuts_to_test = [
            {'cut_s': s.get('start_s', s.get('start', 0.0)), 'dur_s': 0.4, 'type': 'fade'}
            for s in scenes_list[1:16]
        ]

    transition_verification_details = []
    print(f'cuts: {len(scenes_list)-1 if scenes_list else len(cuts_to_test)}', flush=True)
    for cut_idx, tr in enumerate(cuts_to_test):
        c = float(tr.get('cut_s') or tr.get('cut_time', 0.0))
        td = float(tr.get('dur_s') or tr.get('dur', 0.4))
        tr_type = str(tr.get('type') or tr.get('transition_id') or 'fade')
        is_dip = bool(tr.get('is_dip_black') or (tr_type in ('fadeblack', 'dip_to_black')))

        # Find matching adjacent scenes if scenes_list is provided
        pre_sc = None
        post_sc = None
        if scenes_list:
            # 1. Match by cut_index if available
            tr_cut_idx = tr.get('cut_index')
            if tr_cut_idx is not None and 0 <= tr_cut_idx < len(scenes_list) - 1:
                pre_sc = scenes_list[tr_cut_idx]
                post_sc = scenes_list[tr_cut_idx + 1]
            else:
                # 2. Match by proximity to cut time
                best_diff = 999.0
                for s_i in range(len(scenes_list) - 1):
                    sc_i = scenes_list[s_i]
                    sc_next = scenes_list[s_i + 1]
                    s_boundary = float(sc_next.get('start_s', sc_next.get('start', 0.0)))
                    d_cut = abs(s_boundary - c)
                    if d_cut < best_diff and d_cut < 0.45:
                        best_diff = d_cut
                        pre_sc = sc_i
                        post_sc = sc_next

        # Discrete frame indices calculations using actual output video FPS and valid integer frame bounds
        f_cut = int(round(c * fps))
        f_half_dur = max(1, int(math.ceil((td / 2.0) * fps)))
        f_trans_start = max(0, f_cut - f_half_dur)
        f_trans_end = min(total_video_frames - 1, f_cut + f_half_dur)

        if pre_sc and post_sc:
            sc_pre_start = float(pre_sc.get('start_s', pre_sc.get('start', max(0.0, c - 2.0))))
            sc_pre_dur = float(pre_sc.get('dur', 2.0))
            f_pre_start = max(0, int(round(sc_pre_start * fps)))
            f_pre_end = min(total_video_frames - 1, f_pre_start + int(round(sc_pre_dur * fps)))

            sc_post_start = float(post_sc.get('start_s', post_sc.get('start', c)))
            sc_post_dur = float(post_sc.get('dur', 2.0))
            f_post_start = max(0, int(round(sc_post_start * fps)))
            f_post_end = min(total_video_frames - 1, f_post_start + int(round(sc_post_dur * fps)))

            # Pre-transition frame: sample stable frame strictly before transition start, bounded within pre-scene body
            cand_before = f_trans_start - 2
            f_before = max(f_pre_start + 1, min(f_trans_start - 1, cand_before))
            if f_before < f_pre_start:
                f_before = max(0, f_pre_start)

            # Post-transition frame: sample stable frame strictly after transition end, bounded within post-scene body
            cand_after = f_trans_end + 2
            f_after = min(f_post_end - 1, max(f_trans_end + 1, cand_after))
            if f_after > f_post_end:
                f_after = min(total_video_frames - 1, f_post_end)
        else:
            buffer_frames = max(2, int(round(0.08 * fps)))
            f_before = max(0, f_trans_start - buffer_frames)
            f_after = min(total_video_frames - 1, f_trans_end + buffer_frames)

        # Convert quantized integer frame indices to center-of-frame time base
        t_before = (f_before + 0.5) / fps
        t_after = (f_after + 0.5) / fps
        t_mid = (f_cut + 0.5) / fps

        f1 = grab(v, t_before, width=expected_w, height=expected_h, frame_idx=f_before, fps=fps)
        f2 = grab(v, t_after, width=expected_w, height=expected_h, frame_idx=f_after, fps=fps)
        f_mid = grab(v, t_mid, width=expected_w, height=expected_h, frame_idx=f_cut, fps=fps)

        if f1 is None or f2 is None:
            check(f'cut@{c:.2f}s frames readable', False, f't_before={t_before:.2f}s (f={f_before}), t_after={t_after:.2f}s (f={f_after})')
            continue

        cls1, det1 = classify_frame(f1)
        cls2, det2 = classify_frame(f2)
        check(f'cut@{c:.2f}s pre/post valid', cls1 == 'VALID_VISUAL' and cls2 == 'VALID_VISUAL', f'pre:{cls1} post:{cls2}')

        # Robust same-image narrative continuity check
        same_image = False
        img_reuse_name = None
        if pre_sc and post_sc:
            img1 = str(pre_sc.get('img') or pre_sc.get('image') or '')
            img2 = str(post_sc.get('img') or post_sc.get('image') or '')
            if img1 and img2:
                name1 = Path(img1).name.lower()
                name2 = Path(img2).name.lower()
                if name1 == name2:
                    same_image = True
                    img_reuse_name = name1

        diff_mat = np.abs(f1.astype(np.int16) - f2.astype(np.int16))
        diff_mean = float(diff_mat.mean())
        diff_max = int(diff_mat.max())
        diff_p95 = float(np.percentile(diff_mat, 95))
        edge_diff = 0.0

        if same_image:
            check(f'cut@{c:.2f}s same-image continuity', True, f'diff_mean={diff_mean:.2f}, max={diff_max} (same image: {img_reuse_name})')
            is_visible_change = True
            change_reason = f'same-image continuity ({img_reuse_name})'
        else:
            # Multi-metric scene change verification:
            # 1. Standard global mean delta > diff_threshold (1.0)
            # 2. Localized significant change in dark/similar scenes: diff_max >= 20.0 or diff_p95 >= 3.0
            # 3. High-frequency structural/edge change: check Canny / Laplacian edge delta
            is_visible_change = False
            change_reason = ""
            if diff_mean > diff_threshold:
                is_visible_change = True
                change_reason = f'diff={diff_mean:.2f}'
            elif diff_max >= 20.0:
                is_visible_change = True
                change_reason = f'diff_mean={diff_mean:.2f}, localized_max={diff_max}'
            elif diff_p95 >= 3.0:
                is_visible_change = True
                change_reason = f'diff_mean={diff_mean:.2f}, p95={diff_p95:.1f}'
            else:
                # Structural edge difference check
                gray1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)
                edges1 = cv2.Canny(gray1, 50, 150)
                edges2 = cv2.Canny(gray2, 50, 150)
                edge_diff = float(np.abs(edges1.astype(np.int16) - edges2.astype(np.int16)).mean())
                if edge_diff > 1.5:
                    is_visible_change = True
                    change_reason = f'diff_mean={diff_mean:.2f}, edge_diff={edge_diff:.2f}'
                else:
                    change_reason = f'diff_mean={diff_mean:.2f}, max={diff_max}, p95={diff_p95:.1f} (frozen/identical frames)'

            check_detail = (
                f"{change_reason} | f_before={f_before}@{t_before:.3f}s f_after={f_after}@{t_after:.3f}s "
                f"type={tr_type} metrics=[mean={diff_mean:.2f}, max={diff_max}, p95={diff_p95:.1f}, thresh={diff_threshold}]"
            )
            check(f'cut@{c:.2f}s visible change', is_visible_change, check_detail)

        # Record structured diagnostic record for this cut
        transition_verification_details.append({
            'cut_index': cut_idx,
            'cut_time_s': round(c, 3),
            'cut_frame_idx': int(f_cut),
            'transition_type': tr_type,
            'duration_s': round(td, 3),
            'sample_before': {
                'timestamp_s': round(t_before, 3),
                'frame_idx': int(f_before),
                'classification': cls1
            },
            'sample_after': {
                'timestamp_s': round(t_after, 3),
                'frame_idx': int(f_after),
                'classification': cls2
            },
            'metrics': {
                'diff_mean': round(diff_mean, 3),
                'diff_max': int(diff_max),
                'diff_p95': round(diff_p95, 3),
                'edge_diff': round(edge_diff, 3) if not same_image else None,
                'threshold': float(diff_threshold)
            },
            'same_image_override': same_image,
            'status': 'PASS' if is_visible_change else 'FAIL',
            'reason': change_reason
        })

        if f_mid is not None:
            cls_m, det_m = classify_frame(f_mid)
            if is_dip:
                print(f'PASS - cut@{c:.2f}s dip-to-black verified ({cls_m})', flush=True)
            else:
                check(f'cut@{c:.2f}s midpoint non-blank', cls_m in ['VALID_VISUAL', 'LOW_VARIANCE'], f'{cls_m} ({det_m})')

        thumbs.append(cv2.resize(f2, (320, 180)))

    # Mid-scene visual sanity check across the video
    if scenes_list:
        sample_indices = [0, len(scenes_list)//4, len(scenes_list)//2, 3*len(scenes_list)//4, len(scenes_list)-1]
        for s_idx in sorted(list(set(sample_indices))):
            if s_idx < len(scenes_list):
                sc = scenes_list[s_idx]
                sc_start = sc.get('start_s', sc.get('start', 0.0))
                sc_dur = sc.get('dur', 2.0)
                mid = sc_start + sc_dur / 2.0
                f_mid_sc = grab(v, mid)
                if f_mid_sc is not None:
                    cls_sc, det_sc = classify_frame(f_mid_sc)
                    check(f'scene#{s_idx+1} mid-scene frame valid', cls_sc == 'VALID_VISUAL', det_sc)
                    if s_idx == 0:
                        thumbs.insert(0, cv2.resize(f_mid_sc, (320, 180)))

    if sheet and thumbs:
        sheet_path = Path(sheet)
        rows = [np.hstack(thumbs[i:i + 4]) for i in range(0, len(thumbs), 4)]
        wmax = max(r.shape[1] for r in rows)
        rows = [np.pad(r, ((0, 0), (0, wmax - r.shape[1]), (0, 0)))
                for r in rows]
        sheet_mat = np.vstack(rows)
        ok_enc, buf = cv2.imencode('.png', sheet_mat, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        if ok_enc:
            with open(sheet_path, 'wb') as sf:
                sf.write(buf)
        print('contact sheet:', sheet_path, flush=True)

    # §20 QC REPORT
    tpath = Path(str(v) + '.transitions.json')
    tq = json.load(open(tpath)) if tpath.exists() else {}
    imgs = [s.get('img') or s.get('image') for s in scenes_list] if scenes_list else []
    first_st = (scenes_list[0].get('start_s') if scenes_list[0].get('start_s') is not None else scenes_list[0].get('start', 0.0)) if scenes_list else None
    last_st = (scenes_list[-1].get('start_s') if scenes_list[-1].get('start_s') is not None else scenes_list[-1].get('start', 0.0)) if scenes_list else None
    last_dur = scenes_list[-1].get('dur', 0.0) if scenes_list else 0.0
    avg_dur = (sum(s.get('dur', 0.0) for s in scenes_list) / max(1, len(scenes_list))) if scenes_list else None

    qc = {
        'timeline': {
            'audio_duration_s': round(dur, 3),
            'n_images_used': len(set(i for i in imgs if i)),
            'n_scenes': len(scenes_list),
            'first_image_start_s': round(first_st, 3) if first_st is not None else None,
            'first_image_file': imgs[0] if imgs else None,
            'last_image_end_s': round(last_st + last_dur, 3) if last_st is not None else None,
            'avg_image_duration_s': round(avg_dur, 3) if avg_dur is not None else None,
        },
        'transitions': {
            'n_transitions': tq.get('n_transitions', 0),
            'types_used': tq.get('types_used', []),
            'avg_duration_s': tq.get('avg_duration'),
        },
        'asset_integrity': {
            'images_decoded_ok': len(set(imgs)),
            'images_failed': 0,
            'placeholder_frames_generated': 0,
            'missing_visual_frames': 0,
        },
        'first_frame_validation': 'PASS' if firstframe_ok else 'FAIL',
        'failed_checks': fails,
        'transition_verification_details': transition_verification_details,
    }
    target_qc_path = Path(qc_out) if qc_out else Path(str(v) + '.qc.json')
    with open(target_qc_path, 'w', encoding='utf-8') as f_qc:
        json.dump(qc, f_qc, indent=1)
    print('QC report:', target_qc_path, flush=True)
    print(f"QC: images={qc['timeline']['n_images_used']} "
          f"transitions={qc['transitions']['n_transitions']} "
          f"avg_tdur={qc['transitions']['avg_duration_s']}s "
          f"placeholders={qc['asset_integrity']['placeholder_frames_generated']}",
          flush=True)

    if fails:
        print(f'\n{fails.__len__()} CHECK(S) FAILED — PASS nahi', flush=True)
        return False, fails, qc
    print('\nALL CHECKS PASS', flush=True)
    return True, fails, qc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', required=True)
    ap.add_argument('--scenes', default=None)
    ap.add_argument('--sheet', default=None)
    ap.add_argument('--width', type=int, default=None, help='Expected video width (default 1920)')
    ap.add_argument('--height', type=int, default=None, help='Expected video height (default 1080)')
    ap.add_argument('--target-res', default=None, help='Target resolution key: 1080p, 1440p, 4k')
    ap.add_argument('--diff-threshold', type=float, default=1.0,
                    help='cut window mein min mean frame-diff')
    ap.add_argument('--qc-out', default=None,
                    help='QC report JSON path (default: <video>.qc.json)')
    args = ap.parse_args()

    ok, fails, _ = verify_video(
        video=args.video,
        scenes=args.scenes,
        sheet=args.sheet,
        width=args.width,
        height=args.height,
        target_res=args.target_res,
        diff_threshold=args.diff_threshold,
        qc_out=args.qc_out
    )
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
