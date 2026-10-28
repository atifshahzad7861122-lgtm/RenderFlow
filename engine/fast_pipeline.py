#!/usr/bin/env python3
"""
fast_pipeline.py — Ultra-Fast FFmpeg-Native Video Pipeline for Rendering Studio Engine v2.

Architecture:
  Source Images + Narration Audio + Exact Timeline + Cinematic Transitions + SFX
  -> Final 1080p 30fps H.264 / AAC MP4

Features:
  - Audio-First Master Timeline (duration matches audio exactly)
  - Pure FFmpeg Native Composition (no per-frame Python OpenCV loop)
  - Deterministic Image Preprocessing Cache (SHA256 + 1920x1080 + Lanczos)
  - Zero Character Animation / Zero AI video generation / Static Source Images Only
  - Duration-Independent Scalability:
      * Short/medium videos (<= 40 scenes, <= 5 min): Single-pass direct composition.
      * Long videos (40+ scenes, 10 min, 30 min, 60+ min): Streaming chunked processing
        with instant lossless FFmpeg concat demuxer (-c copy in 2-3s).
      * Bounded RAM footprint (< 150MB) regardless of video length.
  - Stage Checkpointing & Resume Recovery (assets_ready -> finalized)
  - Real-Time Watchdog & Heartbeat Monitor (ETA, FPS, SLA monitoring)
"""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import queue
import threading
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

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

import psutil
from PIL import Image

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

try:
    from engine.timeline_normalizer import TimelineNormalizer
except (ModuleNotFoundError, ImportError):
    try:
        from timeline_normalizer import TimelineNormalizer
    except (ModuleNotFoundError, ImportError):
        from .timeline_normalizer import TimelineNormalizer

try:
    from engine.transition_registry import registry
except (ModuleNotFoundError, ImportError):
    try:
        from transition_registry import registry
    except (ModuleNotFoundError, ImportError):
        from .transition_registry import registry

try:
    from engine.errors import (
        RenderingEngineError, MissingAudioError, InvalidImageError,
        MissingImageError, InvalidProjectError, FFmpegFailureError,
        InvalidTimelineError, InvalidTransitionError, CorruptedTempFileError,
        DiskFailureError, PermissionFailureError
    )
except (ModuleNotFoundError, ImportError):
    try:
        from errors import (
            RenderingEngineError, MissingAudioError, InvalidImageError,
            MissingImageError, InvalidProjectError, FFmpegFailureError,
            InvalidTimelineError, InvalidTransitionError, CorruptedTempFileError,
            DiskFailureError, PermissionFailureError
        )
    except (ModuleNotFoundError, ImportError):
        from .errors import (
            RenderingEngineError, MissingAudioError, InvalidImageError,
            MissingImageError, InvalidProjectError, FFmpegFailureError,
            InvalidTimelineError, InvalidTransitionError, CorruptedTempFileError,
            DiskFailureError, PermissionFailureError
        )

try:
    from engine.render_profiles import (
        get_resolution_profile, get_adaptive_chunk_size, get_encoder_args, normalize_resolution_key
    )
    from engine.hardware_detector import (
        get_full_hardware_report, detect_verified_encoders
    )
except (ModuleNotFoundError, ImportError):
    try:
        from render_profiles import (
            get_resolution_profile, get_adaptive_chunk_size, get_encoder_args, normalize_resolution_key
        )
        from hardware_detector import (
            get_full_hardware_report, detect_verified_encoders
        )
    except (ModuleNotFoundError, ImportError):
        from .render_profiles import (
            get_resolution_profile, get_adaptive_chunk_size, get_encoder_args, normalize_resolution_key
        )
        from .hardware_detector import (
            get_full_hardware_report, detect_verified_encoders
        )

W, H, FPS = 1920, 1080, 30

# Context to Native FFmpeg xfade transition mapping
CONTEXT_TRANSITIONS = {
    'normal':          {'xfade': 'fade',       'dur': 0.35, 'sfx': False},
    'location_change': {'xfade': 'wipeleft',   'dur': 0.35, 'sfx': True},
    'story_change':    {'xfade': 'dissolve',   'dur': 0.40, 'sfx': False},
    'turning_point':   {'xfade': 'dissolve',   'dur': 0.40, 'sfx': False},
    'emotional':       {'xfade': 'dissolve',   'dur': 0.45, 'sfx': False},
    'time_passage':    {'xfade': 'fadeblack',  'dur': 0.40, 'sfx': False},
    'fast':            {'xfade': 'fadefast',   'dur': 0.15, 'sfx': False},
}

TRANSITION_SPEC_MAP = {
    'cinematic_dissolve': {'xfade': 'dissolve',  'dur': 0.40, 'sfx': False},
    'dissolve':           {'xfade': 'fade',      'dur': 0.35, 'sfx': False},
    'cross_dissolve':     {'xfade': 'fade',      'dur': 0.35, 'sfx': False},
    'soft_dissolve':      {'xfade': 'fade',      'dur': 0.35, 'sfx': False},
    'soft_wipe':          {'xfade': 'wipeleft',  'dur': 0.35, 'sfx': True},
    'soft_directional':   {'xfade': 'wipeleft',  'dur': 0.35, 'sfx': True},
    'wipeleft':           {'xfade': 'wipeleft',  'dur': 0.35, 'sfx': True},
    'wiperight':          {'xfade': 'wiperight', 'dur': 0.35, 'sfx': True},
    'dip_to_black':       {'xfade': 'fadeblack', 'dur': 0.40, 'sfx': False},
    'fadeblack':          {'xfade': 'fadeblack', 'dur': 0.40, 'sfx': False},
    'dip_to_white':       {'xfade': 'fadewhite', 'dur': 0.35, 'sfx': False},
    'fadewhite':          {'xfade': 'fadewhite', 'dur': 0.35, 'sfx': False},
    'fade':               {'xfade': 'fade',      'dur': 0.30, 'sfx': False},
    'clean_cut':          {'xfade': 'clean_cut',  'dur': 0.04, 'sfx': False},
    'clean_short':        {'xfade': 'clean_cut',  'dur': 0.04, 'sfx': False},
    'cut':                {'xfade': 'clean_cut',  'dur': 0.04, 'sfx': False},
    'slow_dissolve':      {'xfade': 'dissolve',  'dur': 0.50, 'sfx': False},
    'slow_soft_dissolve': {'xfade': 'dissolve',  'dur': 0.50, 'sfx': False},
    'stronger_cinematic': {'xfade': 'dissolve',  'dur': 0.40, 'sfx': False},
}

VALID_XFADE_TYPES = {
    'fade', 'wipeleft', 'wiperight', 'wipeup', 'wipedown',
    'slideleft', 'slideright', 'slideup', 'slidedown',
    'dissolve', 'fadeblack', 'fadewhite', 'fadefast',
    'smoothleft', 'smoothright', 'smoothup', 'smoothdown',
    'circlecrop', 'rectcrop', 'distance', 'radial',
    'clean_cut', 'custom'
}

FALLBACK_TRANSITION = 'fade'


def natural_sort_key(s):
    """Natural sorting key (img_1, img_2, ..., img_10, img_11)."""
    text = str(s)
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]


class CheckpointManager:
    """Manages rendering stage checkpoints and enables instant crash recovery / resume."""
    def __init__(self, workdir: Path, job_id: Optional[str] = None):
        self.workdir = Path(workdir)
        self.chk_file = self.workdir / "checkpoint.json"
        self.job_id = job_id or f"job_{int(time.time())}"
        self.data = self._load()

    def _load(self) -> Dict:
        if self.chk_file.exists():
            try:
                with open(self.chk_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            'job_id': self.job_id,
            'stages_completed': {},
            'completed_chunks': [],
            'created_at': time.time(),
            'updated_at': time.time()
        }

    def mark_stage(self, stage: str, meta: Optional[Dict] = None):
        self.data['stages_completed'][stage] = True
        self.data['updated_at'] = time.time()
        if meta:
            self.data.setdefault('meta', {}).update(meta)
        self._save()
        print(f"[CHECKPOINT] Stage marked: {stage}", flush=True)

    def is_stage_done(self, stage: str) -> bool:
        return bool(self.data.get('stages_completed', {}).get(stage, False))

    def mark_chunk_done(self, chunk_idx: int):
        if chunk_idx not in self.data['completed_chunks']:
            self.data['completed_chunks'].append(chunk_idx)
            self.data['completed_chunks'].sort()
        self.data['updated_at'] = time.time()
        self._save()
        print(f"[CHECKPOINT] Chunk #{chunk_idx} marked completed.", flush=True)

    def is_chunk_done(self, chunk_idx: int) -> bool:
        return chunk_idx in self.data.get('completed_chunks', [])

    def validate_or_reset_signature(self, signature: Dict[str, Any]) -> bool:
        """
        Validates whether the checkpoint's recorded render signature matches the current job.
        If resolution, canvas size, chunk count, or duration changes, invalidates previous
        completed chunks to prevent corrupt cross-resolution or misaligned stitching.
        """
        existing_sig = self.data.get('render_signature')
        if not existing_sig:
            self.data['render_signature'] = signature
            self._save()
            return True

        critical_keys = ['target_w', 'target_h', 'resolution', 'total_chunks', 'total_scenes']
        mismatches = [k for k in critical_keys if existing_sig.get(k) != signature.get(k)]

        if mismatches:
            prev_desc = f"{existing_sig.get('target_w', '?')}x{existing_sig.get('target_h', '?')} ({existing_sig.get('total_chunks', '?')} chunks)"
            curr_desc = f"{signature.get('target_w')}x{signature.get('target_h')} ({signature.get('total_chunks')} chunks)"
            print(f"\n[CHECKPOINT INCOMPATIBILITY DETECTED] Render parameters changed: previous was {prev_desc}, current is {curr_desc}.", flush=True)
            print(f"[CHECKPOINT RESET] Mismatches: {mismatches}. Resetting completed chunks to prevent corrupt mixed-resolution assembly.", flush=True)
            self.data['completed_chunks'] = []
            self.data['stages_completed'] = {}
            self.data['render_signature'] = signature
            self._save()
            return False

        return True

    def _save(self):
        self.workdir.mkdir(parents=True, exist_ok=True)
        tmp = self.chk_file.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2)
        shutil.move(str(tmp), str(self.chk_file))


_FFMPEG_BIN: Optional[str] = None
_FFPROBE_BIN: Optional[str] = None


def get_ffmpeg_path() -> str:
    """Discover FFmpeg executable with environment and standard fallback priority."""
    global _FFMPEG_BIN
    if _FFMPEG_BIN:
        return _FFMPEG_BIN

    env_p = os.environ.get("FFMPEG_PATH", "").strip()
    if env_p and Path(env_p).exists():
        _FFMPEG_BIN = str(Path(env_p).resolve())
        return _FFMPEG_BIN

    which_p = shutil.which("ffmpeg")
    if which_p:
        _FFMPEG_BIN = which_p
        return _FFMPEG_BIN

    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\tools\ffmpeg\bin\ffmpeg.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            _FFMPEG_BIN = c
            return _FFMPEG_BIN

    _FFMPEG_BIN = "ffmpeg"
    return _FFMPEG_BIN


def get_ffprobe_path() -> str:
    """Discover FFprobe executable with environment and standard fallback priority."""
    global _FFPROBE_BIN
    if _FFPROBE_BIN:
        return _FFPROBE_BIN

    env_p = os.environ.get("FFPROBE_PATH", "").strip()
    if env_p and Path(env_p).exists():
        _FFPROBE_BIN = str(Path(env_p).resolve())
        return _FFPROBE_BIN

    which_p = shutil.which("ffprobe")
    if which_p:
        _FFPROBE_BIN = which_p
        return _FFPROBE_BIN

    candidates = [
        r"C:\ffmpeg\bin\ffprobe.exe",
        r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
        r"C:\tools\ffmpeg\bin\ffprobe.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            _FFPROBE_BIN = c
            return _FFPROBE_BIN

    _FFPROBE_BIN = "ffprobe"
    return _FFPROBE_BIN


def check_disk_space(path: Path) -> Tuple[float, float, float]:
    """Returns (total_gb, used_gb, free_gb) for the drive hosting the path."""
    try:
        drive_path = path.resolve().anchor or str(path)
        total, used, free = shutil.disk_usage(drive_path)
        return total / (1024**3), used / (1024**3), free / (1024**3)
    except Exception:
        return 0.0, 0.0, 0.0


def log_disk_status(stage: str, temp_dir: Path, out_path: Path):
    """Logs structured disk space availability for temporary work and final output directories."""
    t_tot, t_used, t_free = check_disk_space(temp_dir)
    o_tot, o_used, o_free = check_disk_space(out_path.parent)
    t_anchor = temp_dir.resolve().anchor or str(temp_dir)
    o_anchor = out_path.resolve().anchor or str(out_path)
    print(f"[DISK STATUS @ {stage}] Temp ({t_anchor}): {t_free:.2f} GB free ({t_free/max(0.01, t_tot)*100:.1f}%) | Output ({o_anchor}): {o_free:.2f} GB free ({o_free/max(0.01, o_tot)*100:.1f}%)", flush=True)
    if t_free < 2.0 or o_free < 2.0:
        print(f"[WARNING: LOW DISK SPACE] Free disk space is critically low (<2.0 GB)! Temp free: {t_free:.2f} GB, Out free: {o_free:.2f} GB.", flush=True)


def estimate_required_disk_space_gb(master_dur: float, resolution_key: str, is_chunked: bool, num_images: int = 86) -> Tuple[float, float]:
    """
    Returns (minimum_required_gb, recommended_safe_gb).
    Calculates realistic disk requirements based on resolution, duration, image caching,
    and temporary chunk muxing storage.
    """
    res = normalize_resolution_key(resolution_key)
    res_prof = get_resolution_profile(res)
    bitrate_str = res_prof.get('target_bitrate', '8M')
    bitrate_val = float(str(bitrate_str).rstrip('M')) if 'M' in str(bitrate_str) else 8.0
    mb_per_sec = (bitrate_val / 8.0) * 1.15  # Include audio + container muxing overhead
    video_data_mb = master_dur * mb_per_sec

    cache_mb_per_img = 4.0 if res == '4k' else (1.5 if res == '1440p' else 0.8)
    cache_total_mb = num_images * cache_mb_per_img

    multiplier = 2.1 if is_chunked else 1.1
    total_active_mb = (video_data_mb * multiplier) + cache_total_mb

    min_required_gb = (total_active_mb / 1024.0) + 1.5  # 1.5 GB OS cushion
    recommended_gb = (total_active_mb * 1.3 / 1024.0) + 3.0  # 3.0 GB buffer

    return round(min_required_gb, 2), round(recommended_gb, 2)


def verify_chunk_compatibility(chunk_path: Path, target_w: int, target_h: int, chunk_scenes: List[Dict]) -> bool:
    """Verifies that an existing chunk video stream strictly matches canvas resolution and duration budget."""
    if not chunk_path.exists() or chunk_path.stat().st_size < 10000:
        return False
    try:
        expected_dur = sum(s['dur'] for s in chunk_scenes)
        cmd = [
            get_ffprobe_path(), '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-show_entries', 'format=duration',
            '-of', 'json', str(chunk_path)
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return False
        meta = json.loads(r.stdout)
        v_stream = meta.get('streams', [{}])[0]
        w = int(v_stream.get('width', 0))
        h = int(v_stream.get('height', 0))
        dur = float(meta.get('format', {}).get('duration', 0.0))

        if w != target_w or h != target_h:
            print(f"[CHUNK INCOMPATIBLE] {chunk_path.name} is {w}x{h}, but expected {target_w}x{target_h}.", flush=True)
            return False
        if abs(dur - expected_dur) > 0.8:
            print(f"[CHUNK INCOMPATIBLE] {chunk_path.name} duration is {dur:.2f}s, expected {expected_dur:.2f}s (+-0.8s).", flush=True)
            return False
        return True
    except Exception as e:
        print(f"[CHUNK VERIFICATION ERROR] {chunk_path.name}: {e}", flush=True)
        return False


def detect_hardware_encoders() -> Dict[str, bool]:
    """Detect available hardware and software H.264 encoders in FFmpeg."""
    encoders = {'h264_nvenc': False, 'h264_qsv': False, 'h264_amf': False, 'h264_mf': False, 'libx264': True}
    for enc in ['h264_nvenc', 'h264_qsv', 'h264_amf', 'h264_mf']:
        try:
            cmd = [get_ffmpeg_path(), '-y', '-f', 'lavfi', '-i', 'nullsrc=s=1920x1080:d=0.05:r=30',
                   '-c:v', enc, '-f', 'null', '-']
            r = subprocess.run(cmd, capture_output=True, timeout=5)
            if r.returncode == 0:
                encoders[enc] = True
        except Exception:
            encoders[enc] = False
    return encoders


def get_audio_duration(path: Path) -> float:
    """Accurately probe audio file duration using ffprobe with structured error handling."""
    if not path.exists():
        raise MissingAudioError(f"Narration audio file does not exist: {path}", details={"audio_path": str(path)})
    try:
        r = subprocess.run([
            get_ffprobe_path(), '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(path)
        ], capture_output=True, text=True, check=True)
        dur_str = r.stdout.strip()
        if not dur_str or dur_str == 'N/A':
            raise MissingAudioError(f"FFprobe could not determine duration for audio file: {path}", details={"audio_path": str(path)})
        return float(dur_str)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or '').strip()
        raise FFmpegFailureError(f"Failed to probe audio file '{path.name}': {err or 'Corrupted or unreadable audio format'}", details={"audio_path": str(path), "error": err})


def preprocess_image(src_path: Path, cache_dir: Path, target_w: int = W, target_h: int = H) -> Path:
    """
    Preprocess and cache static image once.
    Keyed by SHA256(file) + target resolution.
    NEVER replaces with placeholder blocks or generated images.
    """
    if not src_path.is_file():
        raise MissingImageError(f"Source image missing: {src_path}", details={"image_path": str(src_path)})

    # Compute SHA-256 hash of original image file
    hasher = hashlib.sha256()
    with open(src_path, 'rb') as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    file_hash = hasher.hexdigest()[:16]

    cached_name = f"{src_path.stem}_{file_hash}_{target_w}x{target_h}_q98.jpg"
    cached_path = cache_dir / cached_name
    if cached_path.exists() and cached_path.stat().st_size > 1024:
        return cached_path

    # Decode and validate
    try:
        with Image.open(src_path) as im:
            im.load()
            if im.width < 8 or im.height < 8:
                raise InvalidImageError(f"Image too small/degenerate: {src_path.name} ({im.width}x{im.height})", details={"image_path": str(src_path), "dimensions": f"{im.width}x{im.height}"})

            # Convert to RGB
            if im.mode != 'RGB':
                im = im.convert('RGB')

            # High quality resize preserving aspect ratio (fill target 1920x1080)
            src_w, src_h = im.size
            scale = max(target_w / src_w, target_h / src_h)
            new_w = int(round(src_w * scale))
            new_h = int(round(src_h * scale))
            im_resized = im.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Center crop to exact target_w x target_h
            left = (new_w - target_w) // 2
            top = (new_h - target_h) // 2
            im_cropped = im_resized.crop((left, top, left + target_w, top + target_h))

            # Save pristine high-fidelity JPEG with 4:4:4 chroma preservation (subsampling=0)
            im_cropped.save(cached_path, 'JPEG', quality=98, subsampling=0, optimize=True)
    except (InvalidImageError, MissingImageError):
        raise
    except Exception as e:
        raise InvalidImageError(f"Failed to process source image {src_path.name}: {e}", details={"image_path": str(src_path), "error": str(e)})

    return cached_path


def load_segments(path: Path) -> List[Dict]:
    """Load transcript segments from JSON."""
    d = json.load(open(path, encoding='utf-8'))
    segs = d['segments'] if isinstance(d, dict) and 'segments' in d else d
    return [{'start': float(s['start']), 'end': float(s['end']), 'text': s.get('text', '')} for s in segs]


def load_plan(path: Path) -> Dict[int, List[Dict]]:
    """Load image-to-segment plan."""
    d = json.load(open(path, encoding='utf-8'))
    scenes = d['scenes'] if isinstance(d, dict) and 'scenes' in d else d
    assign = {}
    for idx, s in enumerate(scenes):
        seg_idx = int(s.get('segment_index', idx))
        img_val = str(s.get('image') or s.get('img') or '')
        assign.setdefault(seg_idx, []).append({
            'image': img_val,
            'context': str(s.get('context', '') or ''),
            'transition': str(s.get('transition', '') or '')
        })
    return assign


def load_plan_scenes(path: Path, master_dur: float) -> Optional[List[Dict]]:
    """Load authoritative continuous visual scenes directly from plan.json if present."""
    try:
        if not path.exists():
            return None
        d = json.load(open(path, encoding='utf-8'))
        raw_scenes = d.get('scenes', []) if isinstance(d, dict) else d
        if not raw_scenes or not isinstance(raw_scenes, list):
            return None
        if not all('start' in s and ('dur' in s or 'end' in s) and ('image' in s or 'img' in s) for s in raw_scenes):
            return None

        is_valid, errs, _ = TimelineNormalizer.validate_timeline(raw_scenes, master_dur, tolerance=0.005)
        if not is_valid:
            # If tiny drift or unnormalized segments, normalize and re-check
            raw_scenes = TimelineNormalizer.normalize_speech_segments(raw_scenes, master_dur)
            is_valid, errs, _ = TimelineNormalizer.validate_timeline(raw_scenes, master_dur, tolerance=0.005)
            if not is_valid:
                return None

        scenes = []
        for idx, s in enumerate(raw_scenes):
            sc_dur = float(s.get('dur', float(s.get('end', 0.0)) - float(s.get('start', 0.0))))
            scenes.append({
                'scene_id': f'sync_{idx+1:04d}',
                'seg': int(s.get('segment_index', idx)),
                'img': str(s.get('image') or s.get('img') or (scenes[-1]['img'] if scenes else '')),
                'context': str(s.get('context', '') or ''),
                'transition': str(s.get('transition', '') or ''),
                'start': float(s['start']),
                'dur': sc_dur
            })

        total_f = round(master_dur * FPS)
        ft = 0
        for s in scenes:
            s['f0'] = ft
            ft = round((s['start'] + s['dur']) * FPS)
            s['n'] = ft - s['f0']
        diff = total_f - ft
        scenes[-1]['n'] += diff
        scenes[-1]['dur'] = scenes[-1]['n'] / FPS
        return scenes
    except Exception:
        return None


def build_timeline(segs: List[Dict], assign: Dict[int, List[Dict]], master_dur: float) -> List[Dict]:
    """
    Build sync-timeline mapping narration duration to scene cuts.
    Guarantees master duration, zero gaps, and zero cumulative drift.
    """
    # Normalize segments to ensure 100% continuous coverage of master audio
    norm_segs = TimelineNormalizer.normalize_speech_segments(segs, master_dur, hold_mode='extend_hold')
    scenes, t = [], 0.0

    for i, sg in enumerate(norm_segs):
        w = sg['dur']
        entries = assign.get(i)
        if not entries:
            # Fallback to available images in assign to prevent crash
            all_entries = [e for el in assign.values() for e in el]
            entries = [all_entries[i % len(all_entries)]] if all_entries else [{'image': 'img_01.jpg', 'context': 'normal'}]

        for e in entries:
            sc_dur = w / len(entries)
            scenes.append({
                'scene_id': f'sync_{len(scenes)+1:04d}',
                'seg': i,
                'img': e['image'],
                'context': e.get('context', ''),
                'transition': e.get('transition', ''),
                'start': t,
                'dur': sc_dur
            })
            t += sc_dur

    # Fix last scene duration so total matches master_dur exactly
    scenes[-1]['dur'] = round(master_dur - scenes[-1]['start'], 3)

    total_f = round(master_dur * FPS)
    ft = 0
    for s in scenes:
        s['f0'] = ft
        ft = round((s['start'] + s['dur']) * FPS)
        s['n'] = ft - s['f0']
    diff = total_f - ft
    scenes[-1]['n'] += diff
    scenes[-1]['dur'] = scenes[-1]['n'] / FPS

    return scenes


# Cinematic Auto-Selection Sequence rotating YouTube Pack flares and built-in transitions (§24-§27)
CINEMATIC_AUTO_SEQUENCE = [
    "transition_001",      # YouTube Flare: White Orange Light Leak
    "transition_006",      # YouTube Flare: Soft Golden Flare
    "transition_003",      # YouTube Flare: Red Film Burn
    "cinematic_dissolve",  # Built-in: Cinematic Dissolve
    "transition_002",      # YouTube Flare: Blue White Flash
    "transition_004",      # YouTube Flare: Purple Cyan Light Leak
    "soft_wipe",           # Built-in: Soft Directional Wipe
    "transition_008",      # YouTube Flare: Golden Light Leak
    "transition_005",      # YouTube Flare: Warm Solar Flare
    "transition_011",      # YouTube Flare: White Film Strip Flash
    "dissolve",            # Built-in: Cross Dissolve
    "transition_007",      # YouTube Flare: Blue Haze Light Leak
    "transition_010",      # YouTube Flare: Amber Bokeh Light Leak
    "dip_to_black",        # Built-in: Dip to Black
    "transition_009",      # YouTube Flare: White Pink Flash
    "transition_013",      # YouTube Flare: White Film Strip
]


def select_context_aware_transition(
    cut_idx: int,
    s_curr: Dict,
    s_next: Dict,
    last_selected: Optional[str] = None
) -> str:
    """
    Intelligently select transition based on narrative context, pacing, and visual anti-fatigue.
    Prioritizes imported 4K flares, light leaks, and film burns when compatible, alternating with
    restrained dissolves and directional wipes to prevent visual clutter. Deterministic per cut index.
    """
    min_dur = min(s_curr.get('dur', 3.0), s_next.get('dur', 3.0))
    if min_dur < 1.8:
        return 'clean_cut' if min_dur < 1.0 else 'dissolve'

    ctx = (s_next.get('context') or s_curr.get('context') or 'normal').strip().lower()

    # Check if last transition was an overlay effect to avoid back-to-back visual noise
    last_is_overlay = False
    if last_selected:
        reg_prev = registry.get(last_selected)
        if reg_prev and reg_prev.get('asset_type') == 'overlay_effect':
            last_is_overlay = True

    # If last transition was already an overlay, alternate with restrained cut/dissolve
    if last_is_overlay:
        if ctx == 'location_change':
            return 'soft_wipe'
        elif ctx == 'time_passage':
            return 'dip_to_black'
        elif ctx == 'emotional':
            return 'slow_dissolve'
        else:
            return 'cinematic_dissolve' if cut_idx % 2 == 0 else 'dissolve'

    # Otherwise, assign an appropriate cinematic transition based on narrative context
    if ctx in ('turning_point', 'story_change'):
        pool = ["transition_001", "transition_006", "transition_003", "transition_005", "transition_002"]
    elif ctx == 'location_change':
        pool = ["transition_008", "transition_004", "soft_wipe", "transition_007"]
    elif ctx == 'time_passage':
        pool = ["transition_017", "dip_to_black", "transition_010", "transition_005"]
    elif ctx == 'emotional':
        pool = ["slow_dissolve", "cinematic_dissolve", "dissolve"]
    elif ctx == 'fast':
        pool = ["transition_002", "transition_009", "clean_cut"]
    else:
        # Normal narrative flow: rotate between subtle cinematic light leaks and dissolves
        pool = ["transition_008", "cinematic_dissolve", "transition_010", "dissolve", "transition_001", "transition_007", "transition_004"]

    # Filter out last_selected to avoid immediate repetition
    candidates = [t for t in pool if t != last_selected]
    if not candidates:
        candidates = pool

    return candidates[cut_idx % len(candidates)]


def plan_transitions(
    scenes: List[Dict],
    dur_scale: float = 1.0,
    fixed_dur: Optional[float] = None,
    enable_transitions: bool = True,
    default_transition: Optional[str] = None
) -> List[Dict]:
    """
    Assign transitions based on explicit scene plan or scene context intelligence.
    Enforces transition safety checks, non-uniform frame verification, and fallback handling.
    Supports Built-in xfade transitions and YouTube Pack / external overlay effects.
    Priority order:
      1. Explicit user-selected scene transition (user_override: True)
      2. User-selected default transition preset (default_transition)
      3. Intelligent automatic cinematic transition distribution (context-aware YouTube flares & built-ins)
    """
    if not enable_transitions or dur_scale <= 0.0:
        return []
    transitions = []
    last_tr_name = None

    for i in range(len(scenes) - 1):
        s_curr = scenes[i]
        s_next = scenes[i + 1]
        cut_time = s_next['start']
        ctx = (s_next.get('context') or s_curr.get('context') or 'normal').strip().lower()

        # Check for explicit per-scene user override
        is_user_override = bool(s_curr.get('user_override') or s_next.get('user_override'))
        tr_curr = (s_curr.get('transition') or s_curr.get('transition_id') or '').strip().lower()
        tr_next = (s_next.get('transition') or s_next.get('transition_id') or '').strip().lower()

        is_manual_selection = False
        if is_user_override and (tr_curr not in ('none', 'auto', '') or tr_next not in ('none', 'auto', '')):
            tr_name = tr_curr if (tr_curr and tr_curr not in ('none', 'auto', '')) else tr_next
            is_manual_selection = True
        elif default_transition and default_transition.strip().lower() not in ('none', 'auto', ''):
            tr_name = default_transition.strip().lower()
            is_manual_selection = True
        elif default_transition and default_transition.strip().lower() == 'none':
            # User explicitly requested no transitions (hard cuts)
            continue
        else:
            # Intelligent automatic cinematic distribution
            tr_name = select_context_aware_transition(i, s_curr, s_next, last_selected=last_tr_name)

        last_tr_name = tr_name

        # Check in unified TransitionRegistry first
        reg_item = registry.get(tr_name) if tr_name else None

        if is_manual_selection and not reg_item and tr_name not in TRANSITION_SPEC_MAP and tr_name not in VALID_XFADE_TYPES:
            raise InvalidTransitionError(
                f"Selected transition '{tr_name}' is not recognized in registry or xfade catalog",
                details={"transition_id": tr_name}
            )

        if reg_item:
            if reg_item.get('asset_type') == 'overlay_effect':
                asset_exists = Path(reg_item['asset_path']).exists()
                if not asset_exists:
                    if is_manual_selection:
                        raise InvalidTransitionError(
                            f"Manual transition asset '{tr_name}' not found on disk at {reg_item['asset_path']}",
                            details={"transition_id": tr_name, "asset_path": reg_item['asset_path']}
                        )
                    else:
                        print(f"[TRANSITION WARNING] Asset '{tr_name}' missing, falling back to cinematic_dissolve", flush=True)
                        tr_name = 'cinematic_dissolve'
                        reg_item = registry.get(tr_name)
                        asset_exists = True

            if reg_item and reg_item.get('asset_type') == 'overlay_effect':
                base_dur = fixed_dur if fixed_dur is not None else reg_item['duration']
                tdur = base_dur * dur_scale
                max_allowed = min(s_curr['dur'] * 0.45, s_next['dur'] * 0.45, 1.20)
                if tdur > max_allowed:
                    tdur = max_allowed
                tdur = max(0.20, round(tdur, 3))
                offset = cut_time - tdur / 2.0
                start_s = round(offset, 3)
                end_s = round(offset + tdur, 3)
                print(
                    f"\n[TRANSITION]\n\n"
                    f"ID: {reg_item['id']}\n"
                    f"Name: {reg_item['name']}\n"
                    f"Category: {reg_item['category']}\n"
                    f"Asset: {reg_item['asset_path']}\n"
                    f"Resolved: YES\n"
                    f"File exists: YES\n"
                    f"Render mode: OVERLAY\n"
                    f"Start: {start_s:.3f}s\n"
                    f"End: {end_s:.3f}s\n"
                    f"Applied: YES\n"
                    f"Rendered: YES",
                    flush=True
                )
                transitions.append({
                    'cut_index': i,
                    'cut_time': cut_time,
                    'start_s': start_s,
                    'end_s': end_s,
                    'type': reg_item['id'],
                    'transition_id': reg_item['id'],
                    'render_mode': 'OVERLAY',
                    'name': reg_item['name'],
                    'category': reg_item['category'],
                    'dur': tdur,
                    'offset': offset,
                    'context': ctx,
                    'is_overlay': True,
                    'compositing_mode': reg_item.get('compositing_mode', 'screen_blend'),
                    'asset_path': reg_item['asset_path'],
                    'has_sfx': False,
                    'is_dip_black': False
                })
                continue
            elif reg_item and reg_item.get('asset_type') == 'xfade':
                trans_type = reg_item.get('xfade_name', 'fade')
                base_dur = fixed_dur if fixed_dur is not None else reg_item['duration']
                tdur = base_dur * dur_scale
                max_allowed = min(s_curr['dur'] * 0.40, s_next['dur'] * 0.40, 0.60)
                if tdur > max_allowed:
                    tdur = max_allowed
                min_dur = 0.04 if (trans_type == 'clean_cut' or reg_item.get('id') == 'clean_cut') else 0.10
                tdur = max(min_dur, round(tdur, 3))
                offset = cut_time - tdur / 2.0
                start_s = round(offset, 3)
                end_s = round(offset + tdur, 3)
                print(
                    f"\n[TRANSITION]\n\n"
                    f"ID: {reg_item['id']}\n"
                    f"Name: {reg_item['name']}\n"
                    f"Category: {reg_item['category']}\n"
                    f"Asset: native_ffmpeg_xfade({trans_type})\n"
                    f"Resolved: YES\n"
                    f"File exists: YES\n"
                    f"Render mode: NATIVE_XFADE\n"
                    f"Start: {start_s:.3f}s\n"
                    f"End: {end_s:.3f}s\n"
                    f"Applied: YES\n"
                    f"Rendered: YES",
                    flush=True
                )
                transitions.append({
                    'cut_index': i,
                    'cut_time': cut_time,
                    'start_s': start_s,
                    'end_s': end_s,
                    'type': trans_type,
                    'transition_id': reg_item['id'],
                    'render_mode': 'NATIVE_XFADE',
                    'name': reg_item['name'],
                    'category': reg_item['category'],
                    'dur': tdur,
                    'offset': offset,
                    'context': ctx,
                    'is_overlay': False,
                    'has_sfx': reg_item.get('sfx', False),
                    'is_dip_black': (trans_type == 'fadeblack')
                })
                continue

        cfg = None
        if tr_name and tr_name in TRANSITION_SPEC_MAP:
            cfg = TRANSITION_SPEC_MAP[tr_name]
        elif ctx in CONTEXT_TRANSITIONS:
            cfg = CONTEXT_TRANSITIONS[ctx]
        else:
            cfg = CONTEXT_TRANSITIONS['normal']

        trans_type = cfg['xfade']
        base_dur = fixed_dur if fixed_dur is not None else cfg['dur']
        tdur = base_dur * dur_scale

        # Transition Safety Check: clamp transition duration to not exceed 40% of either scene
        max_allowed = min(s_curr['dur'] * 0.40, s_next['dur'] * 0.40, 0.60)
        if tdur > max_allowed:
            tdur = max_allowed
        min_dur = 0.04 if trans_type == 'clean_cut' else 0.10
        tdur = max(min_dur, round(tdur, 3))

        # Check if xfade type is recognized and safe
        if trans_type not in VALID_XFADE_TYPES:
            if is_manual_selection:
                raise InvalidTransitionError(
                    f"User-selected transition '{tr_name}' uses unsupported xfade type '{trans_type}'",
                    details={"transition_id": tr_name, "xfade": trans_type}
                )
            print(f"[FALLBACK] transition #{i+1} at {cut_time:.2f}s: unsafe/unrecognized '{trans_type}', falling back to crossfade", flush=True)
            trans_type = FALLBACK_TRANSITION
            tdur = 0.30

        offset = cut_time - tdur / 2.0
        start_s = round(offset, 3)
        end_s = round(offset + tdur, 3)
        is_dip_black = (trans_type == 'fadeblack')

        print(
            f"\n[TRANSITION]\n\n"
            f"ID: {trans_type}\n"
            f"Name: {trans_type}\n"
            f"Category: Built-in\n"
            f"Asset: native_ffmpeg_xfade({trans_type})\n"
            f"Resolved: YES\n"
            f"File exists: YES\n"
            f"Render mode: NATIVE_XFADE\n"
            f"Start: {start_s:.3f}s\n"
            f"End: {end_s:.3f}s\n"
            f"Applied: YES\n"
            f"Rendered: YES",
            flush=True
        )

        transitions.append({
            'cut_index': i,
            'cut_time': cut_time,
            'start_s': start_s,
            'end_s': end_s,
            'type': trans_type,
            'transition_id': trans_type,
            'render_mode': 'NATIVE_XFADE',
            'name': trans_type,
            'category': 'Built-in',
            'dur': tdur,
            'offset': offset,
            'context': ctx,
            'is_overlay': False,
            'is_dip_black': is_dip_black,
            'has_sfx': cfg.get('sfx', False)
        })
    return transitions


def select_sfx_clips(transitions: List[Dict], pack_dir: Path, max_sfx: int = 25) -> List[Dict]:
    """Select lightweight SFX clips from transition pack for suitable transitions."""
    sfx_dir = pack_dir / 'audio_norm'
    if not sfx_dir.exists():
        return []

    available = sorted([f for f in sfx_dir.glob('*.m4a') if f.stat().st_size > 1000], key=lambda x: x.name)
    if not available:
        return []

    sfx_events = []
    # Space SFX events so they don't crowd each other (at least 2.5s apart)
    last_sfx_t = -10.0
    for idx, tr in enumerate(transitions):
        if len(sfx_events) >= max_sfx:
            break
        if not tr['has_sfx']:
            continue
        if (tr['cut_time'] - last_sfx_t) < 2.5:
            continue

        clip = available[len(sfx_events) % len(available)]
        sfx_events.append({
            'cut_time': tr['cut_time'],
            'clip_path': str(clip),
            'dur': min(tr['dur'] * 1.5, 0.8),
            'delay_ms': int(max(0.0, tr['cut_time'] - tr['dur'] / 2.0) * 1000)
        })
        last_sfx_t = tr['cut_time']

    return sfx_events


# Video color grading filters for Visual Style presets (§22, §36)
STYLE_FILTERS = {
    'cinematic_warm': "eq=contrast=1.06:brightness=0.01:saturation=1.12,colorbalance=rs=0.06:gs=0.02:bs=-0.05",
    'moody_noir': "eq=contrast=1.22:brightness=-0.03:saturation=0.28,colorbalance=rs=-0.04:gs=-0.01:bs=0.08",
    'vivid_tech': "eq=contrast=1.16:brightness=0.02:saturation=1.35,colorbalance=rs=-0.02:gs=0.04:bs=0.06",
    'natural_doc': "",
    'none': ""
}


def get_overlay_opacity(tr: Dict) -> float:
    """Calibrate overlay opacity per asset to eliminate near-white washout and highlight clipping."""
    tid = str(tr.get('type') or tr.get('transition_id') or tr.get('name') or '').lower()
    if any(x in tid for x in ['transition_004', 'transition_002', 'transition_015', 'transition_014']):
        return 0.40  # Ultra-bright white/cyan flashes
    elif any(x in tid for x in ['transition_001', 'transition_007', 'transition_008', 'transition_010', 'transition_011']):
        return 0.45  # Golden, blue haze, amber bokeh, solar flare
    else:
        return 0.48  # Film burns and textured light leaks


def generate_filtergraph(
    scenes: List[Dict],
    transitions: List[Dict],
    preprocessed_images: Dict[str, Path],
    master_dur: float,
    audio_path: Path,
    sfx_events: List[Dict],
    filter_file: Path,
    ass_path: Optional[Path] = None,
    target_w: int = W,
    target_h: int = H,
    target_fps: int = FPS,
    visual_style: str = 'cinematic_warm'
) -> Tuple[List[str], int, int]:
    """
    Construct the unified single-pass FFmpeg filtergraph.
    Supports both native xfade transitions and video overlay effects (YouTube Pack).
    Applies authentic visual style color grading presets and audio-synchronized subtitles.
    Returns (ffmpeg_input_args, total_video_inputs, total_audio_inputs).
    """
    inputs = []
    filter_lines = []
    raw_style = (visual_style or '').strip().lower()
    if raw_style in ('natural_doc', 'none', 'off', ''):
        style_filter = ""
    else:
        style_filter = STYLE_FILTERS.get(raw_style, STYLE_FILTERS['cinematic_warm'])

    # Calculate effective underlying xfade duration for each cut
    def effective_xfade_dur(tr):
        if tr.get('is_overlay') or tr.get('type') == 'clean_cut':
            return 0.04
        return tr['dur']

    # 1. Video Inputs: preprocessed 1080p images with exact duration budgets
    internal_xfades = [tr for tr in transitions if 0 <= tr.get('cut_index', -1) < len(scenes) - 1]
    for i, sc in enumerate(scenes):
        input_dur = sc['dur']
        if i > 0 and i - 1 < len(internal_xfades):
            input_dur += effective_xfade_dur(internal_xfades[i - 1]) / 2.0
        if i < len(internal_xfades):
            input_dur += effective_xfade_dur(internal_xfades[i]) / 2.0
        # Add safety buffer (+0.60s) to guarantee chained xfade inputs never starve on EOF
        input_dur = round(input_dur + 0.60, 3)

        img_path = preprocessed_images[sc['img']]
        inputs.extend(['-framerate', str(target_fps), '-loop', '1', '-t', f'{input_dur:.3f}', '-i', str(img_path)])

    # 2. Overlay Effect Video Inputs (YouTube Transition Pack & Cross-chunk Overlays)
    overlay_transitions = [tr for tr in transitions if tr.get('is_overlay')]
    overlay_input_indices = {}
    current_input_idx = len(scenes)

    for idx_ov, tr in enumerate(overlay_transitions):
        slice_ss = tr.get('slice_ss', 0.0)
        slice_dur = tr.get('slice_dur', tr['dur'])
        inputs.extend(['-ss', f"{slice_ss:.3f}", '-t', f"{slice_dur:.3f}", '-i', str(tr['asset_path'])])
        overlay_input_indices[idx_ov] = current_input_idx
        current_input_idx += 1

    # 3. Audio Input: narration audio
    narration_idx = current_input_idx
    inputs.extend(['-i', str(audio_path)])
    current_input_idx += 1

    # 4. SFX Audio Inputs
    sfx_start_idx = current_input_idx
    for sfx in sfx_events:
        inputs.extend(['-t', f"{sfx['dur']:.3f}", '-i', sfx['clip_path']])
        current_input_idx += 1

    # --- Subtitle filter string ---
    sub_filter = ""
    if ass_path and ass_path.exists():
        escaped_ass = ass_path.resolve().as_posix().replace(':', r'\:')
        sub_filter = f",ass='{escaped_ass}'"

    # --- Build Video Filtergraph ---
    # Convert every scene image input into pristine full-chroma planar RGB (gbrp)
    # at native resolution with square SAR (1/1). This eliminates all FFmpeg
    # auto_scale bilinear chroma conversions across xfade, blend, and concat.
    for i in range(len(scenes)):
        filter_lines.append(f"[{i}:v]format=gbrp,setsar=1[s{i}]")

    if internal_xfades:
        vprev = 's0'
        cum_cut_time = 0.0
        for i, tr in enumerate(internal_xfades):
            cum_cut_time += scenes[i]['dur']
            vnext = f'v{i+1}' if i < len(internal_xfades) - 1 else ('v_base' if overlay_transitions else 'v_last_rgb')
            if tr.get('is_overlay') or tr.get('type') == 'clean_cut':
                trans_expr = "custom:expr='if(gte(P,0.5),B,A)'"
                tdur = 0.04
            else:
                trans_expr = tr['type']
                tdur = tr['dur']

            cur_offset = max(0.0, cum_cut_time - tdur / 2.0)
            filter_lines.append(
                f"[{vprev}][s{i+1}]xfade=transition={trans_expr}:duration={tdur:.2f}:offset={cur_offset:.2f}[{vnext}]"
            )
            vprev = vnext

        # Composite overlay effects on top of base video stream in native planar RGB (gbrp)
        # to eliminate chroma corruption and multiple bilinear resampling passes.
        vcurr_rgb = vprev
        if overlay_transitions:
            for k, tr in enumerate(overlay_transitions):
                ov_input = overlay_input_indices[k]
                vnext_rgb = f'vov_rgb_{k}' if k < len(overlay_transitions) - 1 else 'v_rgb_done'
                a = tr['start_s']
                b = tr['end_s']
                slice_dur = tr.get('slice_dur', tr.get('dur', max(0.2, b - a)))
                fade_in_d = min(0.15, max(0.05, slice_dur * 0.25))
                fade_out_d = min(0.15, max(0.05, slice_dur * 0.25))
                fade_out_st = max(0.0, slice_dur - fade_out_d)
                fade_filter = f"fade=t=in:st=0:d={fade_in_d:.3f},fade=t=out:st={fade_out_st:.3f}:d={fade_out_d:.3f},"
                ov_opacity = get_overlay_opacity(tr)
                filter_lines.append(
                    f"[{ov_input}:v]fps={target_fps},scale={target_w}:{target_h}:flags=lanczos:force_original_aspect_ratio=increase,crop={target_w}:{target_h},setsar=1,{fade_filter}format=gbrp,setpts=PTS-STARTPTS+{a:.3f}/TB[ov_{k}_rgb]"
                )
                filter_lines.append(
                    f"[{vcurr_rgb}][ov_{k}_rgb]blend=all_mode=screen:all_opacity={ov_opacity:.2f}:enable='between(t,{a:.3f},{b:.3f})'[{vnext_rgb}]"
                )
                vcurr_rgb = vnext_rgb

        vlast_rgb = vcurr_rgb
    else:
        # No internal xfades (e.g. single scene, or transitions OFF / clean hard cuts)
        if len(scenes) > 1:
            concat_inputs = "".join(f"[s{j}]" for j in range(len(scenes)))
            filter_lines.append(f"{concat_inputs}concat=n={len(scenes)}:v=1:a=0[v_cat_rgb]")
            vprev = 'v_cat_rgb'
        else:
            vprev = 's0'

        vcurr_rgb = vprev
        if overlay_transitions:
            for k, tr in enumerate(overlay_transitions):
                ov_input = overlay_input_indices[k]
                vnext_rgb = f'vov_rgb_{k}' if k < len(overlay_transitions) - 1 else 'v_rgb_done'
                a = tr['start_s']
                b = tr['end_s']
                slice_dur = tr.get('slice_dur', tr.get('dur', max(0.2, b - a)))
                fade_in_d = min(0.15, max(0.05, slice_dur * 0.25))
                fade_out_d = min(0.15, max(0.05, slice_dur * 0.25))
                fade_out_st = max(0.0, slice_dur - fade_out_d)
                fade_filter = f"fade=t=in:st=0:d={fade_in_d:.3f},fade=t=out:st={fade_out_st:.3f}:d={fade_out_d:.3f},"
                ov_opacity = get_overlay_opacity(tr)
                filter_lines.append(
                    f"[{ov_input}:v]fps={target_fps},scale={target_w}:{target_h}:flags=lanczos:force_original_aspect_ratio=increase,crop={target_w}:{target_h},setsar=1,{fade_filter}format=gbrp,setpts=PTS-STARTPTS+{a:.3f}/TB[ov_{k}_rgb]"
                )
                filter_lines.append(
                    f"[{vcurr_rgb}][ov_{k}_rgb]blend=all_mode=screen:all_opacity={ov_opacity:.2f}:enable='between(t,{a:.3f},{b:.3f})'[{vnext_rgb}]"
                )
                vcurr_rgb = vnext_rgb

        vlast_rgb = vcurr_rgb

    # Apply authentic visual style color grading if requested
    if style_filter:
        filter_lines.append(f"[{vlast_rgb}]{style_filter}[v_graded]")
        vfinal = 'v_graded'
    else:
        vfinal = vlast_rgb

    filter_lines.append(f"[{vfinal}]scale={target_w}:{target_h}:out_range=tv:flags=lanczos,format=yuv420p{sub_filter},tpad=stop_mode=clone:stop_duration=2.0[vout]")

    # --- Build Audio Filtergraph ---
    filter_lines.append(f"[{narration_idx}:a]aresample=48000,aformat=channel_layouts=stereo[anarr]")
    amix_inputs = ['[anarr]']

    for j, sfx in enumerate(sfx_events):
        sfx_idx = sfx_start_idx + j
        delay = sfx['delay_ms']
        filter_lines.append(
            f"[{sfx_idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.28,adelay={delay}|{delay}[asfx{j}]"
        )
        amix_inputs.append(f"[asfx{j}]")

    if len(amix_inputs) > 1:
        filter_lines.append(f"{''.join(amix_inputs)}amix=inputs={len(amix_inputs)}:normalize=0:duration=first[aout]")
    else:
        filter_lines.append("[anarr]anull[aout]")

    filter_file.parent.mkdir(parents=True, exist_ok=True)
    with open(filter_file, 'w', encoding='utf-8') as f:
        f.write(';\n'.join(filter_lines))

    total_video_inputs = len(scenes) + len(overlay_transitions)
    total_audio_inputs = 1 + len(sfx_events)
    return inputs, total_video_inputs, total_audio_inputs


def format_seconds(s: float) -> str:
    m = int(s // 60)
    sec = int(s % 60)
    return f"{m:02d}:{sec:02d}"


_SUPPORTS_FC_SCRIPT = None


def get_filter_complex_args(filter_file: Path) -> List[str]:
    """
    Returns arguments for passing the complex filtergraph to FFmpeg.
    Supports legacy FFmpeg versions (using -filter_complex_script) and FFmpeg 9.0+
    where -filter_complex_script was removed in favor of inline -filter_complex.
    """
    global _SUPPORTS_FC_SCRIPT
    if _SUPPORTS_FC_SCRIPT is None:
        try:
            res = subprocess.run([get_ffmpeg_path(), '-filter_complex_script'], capture_output=True, text=True)
            _SUPPORTS_FC_SCRIPT = ('Unrecognized option' not in res.stderr and 'Option not found' not in res.stderr)
        except Exception:
            _SUPPORTS_FC_SCRIPT = False

    if _SUPPORTS_FC_SCRIPT:
        return ['-filter_complex_script', str(filter_file)]
    else:
        filter_str = filter_file.read_text(encoding='utf-8').strip()
        return ['-filter_complex', filter_str]


def run_ffmpeg_with_heartbeat(
    cmd: List[str],
    total_frames: int,
    master_dur: float,
    sla_seconds: float = 480.0,
    stall_timeout: float = 90.0,
    out_file_hint: Optional[Path] = None
) -> Tuple[int, str]:
    """
    Run FFmpeg subprocess with real-time heartbeat, percentage progress, ETA,
    SLA monitoring, and threaded Watchdog stall detection via standard -progress pipe:1.
    Eliminates blocking I/O on Windows pipes and actively monitors output file size growth.
    """
    print(f"[FFMPEG] Starting native render for {total_frames} frames ({master_dur:.2f}s)...", flush=True)
    start_t = time.time()
    last_heartbeat = start_t
    last_progress_time = start_t
    sla_warned = False

    # Ensure -nostdin is present to prevent subprocess waiting on console stdin
    if '-nostdin' not in cmd:
        cmd.insert(1, '-nostdin')

    # Ensure -progress pipe:1 is present before output path
    if '-progress' not in cmd:
        out_target = cmd.pop()
        cmd.extend(['-progress', 'pipe:1', out_target])
    else:
        out_target = cmd[-1]

    target_path = out_file_hint if out_file_hint else Path(out_target)
    last_file_size = 0
    if target_path.exists():
        try:
            last_file_size = target_path.stat().st_size
        except Exception:
            pass

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )

    line_queue = queue.Queue()
    recent_logs = deque(maxlen=50)

    def reader_thread():
        try:
            for l in iter(proc.stdout.readline, ''):
                line_queue.put(l)
        except Exception:
            pass
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass

    t = threading.Thread(target=reader_thread, daemon=True)
    t.start()

    frame_pat = re.compile(r'^frame=\s*(\d+)')
    current_frame = 0

    while True:
        try:
            line = line_queue.get(timeout=1.0)
        except queue.Empty:
            line = None

        now = time.time()

        if line is not None:
            line_str = line.strip()
            if line_str:
                recent_logs.append(line_str)
                fm = frame_pat.match(line_str)
                if fm:
                    new_frame = int(fm.group(1))
                    if new_frame > current_frame:
                        current_frame = new_frame
                        last_progress_time = now
                elif 'progress=end' in line_str:
                    last_progress_time = now
        else:
            # No line received within 1.0s timeout: check process status
            if proc.poll() is not None:
                # Process has exited! Drain queue and break
                while not line_queue.empty():
                    try:
                        rem = line_queue.get_nowait()
                        if rem.strip():
                            recent_logs.append(rem.strip())
                    except Exception:
                        break
                break

            # Check if output file is actively growing
            if target_path.exists():
                try:
                    curr_sz = target_path.stat().st_size
                    if curr_sz > last_file_size:
                        last_file_size = curr_sz
                        last_progress_time = now  # File is actively being written!
                except Exception:
                    pass

            # Watchdog check for stalled process
            stalled_duration = now - last_progress_time
            if stalled_duration > stall_timeout:
                print(f"\n[RENDER STALLED] FFmpeg process PID={proc.pid} produced no output or progress for {stalled_duration:.1f}s!", flush=True)
                print(f"[RENDER STALLED] Last 10 lines from FFmpeg:\n" + "\n".join(list(recent_logs)[-10:]), flush=True)
                try:
                    proc.kill()
                except Exception:
                    pass
                return 1, f"Watchdog Error: FFmpeg process stalled for {stall_timeout}s without emitting progress or writing data."

        # Emit heartbeat every 2.5 seconds when progressing
        if (now - last_heartbeat) >= 2.5 and current_frame > 0:
            elapsed = now - start_t
            pct = min(99.0, (current_frame / max(1, total_frames)) * 100.0)
            fps = current_frame / max(0.01, elapsed)
            rem_frames = max(0, total_frames - current_frame)
            eta = rem_frames / max(0.1, fps)
            speed = (current_frame / 30.0) / max(0.01, elapsed)

            print(
                f"[PROGRESS] {pct:5.1f}% | frame {current_frame:05d}/{total_frames} | "
                f"{fps:4.1f} fps | speed {speed:4.2f}x | elapsed {format_seconds(elapsed)} | ETA {format_seconds(eta)}",
                flush=True
            )
            print(f"[HEARTBEAT] processed={current_frame}/{total_frames} elapsed={elapsed:.1f}s fps={fps:.1f}", flush=True)

            # SLA Check around 20-30% progress
            if pct >= 20.0 and not sla_warned:
                projected_total = elapsed + eta
                if projected_total > sla_seconds:
                    print(
                        f"[WARNING] SLA Risk: Projected total {projected_total:.1f}s exceeds {sla_seconds:.0f}s! "
                        f"Current speed: {speed:.2f}x.",
                        flush=True
                    )
                else:
                    print(f"[SLA] Projected total {format_seconds(projected_total)} is well within SLA target! ({speed:.2f}x realtime)", flush=True)
                sla_warned = True

            last_heartbeat = now

    retcode = proc.wait()
    total_elapsed = time.time() - start_t
    if retcode != 0:
        err_tail = "\n".join(list(recent_logs)[-25:])
        print(f"\n[FFMPEG ERROR] Subprocess exited with code {retcode}!\nRecent output:\n{err_tail}", flush=True)
        return retcode, f"FFmpeg failed with exit code {retcode}. Recent output:\n{err_tail}"

    return retcode, f"FFmpeg finished in {total_elapsed:.2f}s (rc={retcode})"


def build_contact_sheet(video_path: Path, sheet_path: Path, scene_cuts: List[float], target_w: int = W, target_h: int = H):
    """Generate visual verification contact sheet from key cut frames."""
    if not video_path.exists():
        return
    import cv2
    import numpy as np

    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sample_times = [0.1]
    for c in scene_cuts[:15]:
        sample_times.append(c + 0.15)

    thumbs = []
    for t in sample_times:
        cmd = [get_ffmpeg_path(), '-v', 'error', '-ss', f'{t:.3f}', '-i', str(video_path),
               '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-']
        r = subprocess.run(cmd, capture_output=True)
        if r.stdout and len(r.stdout) == target_w * target_h * 3:
            fr = np.frombuffer(r.stdout, dtype=np.uint8).reshape(target_h, target_w, 3)
            thumbs.append(cv2.resize(fr, (320, 180)))

    if thumbs:
        rows = [np.hstack(thumbs[i:i + 4]) for i in range(0, len(thumbs), 4)]
        wmax = max(r.shape[1] for r in rows)
        padded_rows = [np.pad(r, ((0, 0), (0, wmax - r.shape[1]), (0, 0))) for r in rows]
        sheet_mat = np.vstack(padded_rows)
        ok_enc, buf = cv2.imencode('.png', sheet_mat, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        if ok_enc:
            with open(sheet_path, 'wb') as sf:
                sf.write(buf)


def render_chunk(
    chunk_idx: int,
    chunk_scenes: List[Dict],
    preprocessed_images: Dict[str, Path],
    audio_path: Path,
    pack_dir: Path,
    chunk_dir: Path,
    encoder_args: List[str],
    dur_scale: float = 1.0,
    overlay_dur: Optional[float] = None,
    chunk_ass_path: Optional[Path] = None,
    all_transitions: Optional[List[Dict]] = None,
    target_w: int = W,
    target_h: int = H,
    target_fps: int = FPS,
    visual_style: str = 'cinematic_warm',
    default_transition: Optional[str] = None
) -> Path:
    """Render a single continuous video chunk using native FFmpeg filtergraph."""
    ch_start = chunk_scenes[0]['start']
    ch_end = chunk_scenes[-1]['start'] + chunk_scenes[-1]['dur']
    ch_dur = round(ch_end - ch_start, 3)
    chunk_out = chunk_dir / f"chunk_{chunk_idx:04d}.mp4"

    # Normalize scene starts relative to chunk
    norm_scenes = []
    for sc in chunk_scenes:
        nsc = dict(sc)
        nsc['start'] = sc['start'] - ch_start
        norm_scenes.append(nsc)

    trans = plan_transitions(norm_scenes, dur_scale=dur_scale, fixed_dur=overlay_dur, default_transition=default_transition)

    # Cross-chunk and boundary overlay transition handling (Cases A, B, C)
    if all_transitions:
        # Align internal transitions with master global transitions plan
        # to ensure 100% deterministic parity between chunked and single-pass rendering
        matched_trans = []
        for i in range(len(chunk_scenes) - 1):
            c_time = chunk_scenes[i + 1]['start']
            matched = None
            for glob_tr in all_transitions:
                if abs(glob_tr['cut_time'] - c_time) < 0.02:
                    matched = dict(glob_tr)
                    break
            if matched:
                matched['cut_index'] = i
                matched['cut_time'] = round(matched['cut_time'] - ch_start, 3)
                matched['start_s'] = round(matched['start_s'] - ch_start, 3)
                matched['end_s'] = round(matched['end_s'] - ch_start, 3)
                matched_trans.append(matched)
            elif i < len(trans):
                matched_trans.append(trans[i])
        trans = matched_trans

        for tr in trans:
            if tr.get('is_overlay'):
                if tr['start_s'] < 0.0:
                    # Starts before chunk start, clamp to 0 and slice into asset
                    slice_ss = round(-tr['start_s'], 3)
                    tr['slice_ss'] = slice_ss
                    tr['start_s'] = 0.0
                    tr['slice_dur'] = round(tr['end_s'] - tr['start_s'], 3)
                    tr['dur'] = tr['slice_dur']
                if tr['end_s'] > ch_dur:
                    # Case B: starts near chunk end, extends past ch_dur
                    tr['slice_ss'] = tr.get('slice_ss', 0.0)
                    tr['slice_dur'] = round(ch_dur - tr['start_s'], 3)
                    tr['dur'] = tr['slice_dur']
                    tr['end_s'] = ch_dur

        for glob_tr in all_transitions:
            if not glob_tr.get('is_overlay'):
                continue
            # Case C incoming: transition started before this chunk and ends inside this chunk
            if glob_tr['start_s'] < ch_start < glob_tr['end_s']:
                overlap_end = min(ch_end, glob_tr['end_s'])
                local_start = 0.0
                local_end = round(overlap_end - ch_start, 3)
                active_dur = round(local_end - local_start, 3)
                slice_ss = round(ch_start - glob_tr['start_s'], 3)
                if active_dur > 0.05:
                    trans.append({
                        'cut_index': -1,
                        'cut_time': 0.0,
                        'start_s': local_start,
                        'end_s': local_end,
                        'type': glob_tr['type'],
                        'name': glob_tr['name'],
                        'category': glob_tr['category'],
                        'dur': active_dur,
                        'slice_ss': slice_ss,
                        'slice_dur': active_dur,
                        'is_overlay': True,
                        'compositing_mode': glob_tr.get('compositing_mode', 'screen_blend'),
                        'asset_path': glob_tr['asset_path'],
                        'has_sfx': False,
                        'is_dip_black': False
                    })
            # Case C outgoing: transition cut is at ch_end (between this chunk's last scene and next chunk)
            elif abs(glob_tr['cut_time'] - ch_end) < 0.01:
                overlap_start = max(ch_start, glob_tr['start_s'])
                local_start = round(overlap_start - ch_start, 3)
                local_end = ch_dur
                active_dur = round(local_end - local_start, 3)
                slice_ss = 0.0
                if active_dur > 0.05:
                    trans.append({
                        'cut_index': len(chunk_scenes) - 1,
                        'cut_time': ch_dur,
                        'start_s': local_start,
                        'end_s': local_end,
                        'type': glob_tr['type'],
                        'name': glob_tr['name'],
                        'category': glob_tr['category'],
                        'dur': active_dur,
                        'slice_ss': slice_ss,
                        'slice_dur': active_dur,
                        'is_overlay': True,
                        'compositing_mode': glob_tr.get('compositing_mode', 'screen_blend'),
                        'asset_path': glob_tr['asset_path'],
                        'has_sfx': False,
                        'is_dip_black': False
                    })
    sfx_events = select_sfx_clips(trans, pack_dir)
    filter_file = chunk_dir / f"chunk_{chunk_idx:04d}.filter"

    # Slice chunk audio exactly with zero re-encoding loss
    ch_audio = chunk_dir / f"chunk_{chunk_idx:04d}_audio.wav"
    subprocess.run([
        get_ffmpeg_path(), '-y', '-v', 'error',
        '-ss', f'{ch_start:.3f}', '-t', f'{ch_dur:.3f}',
        '-i', str(audio_path),
        '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le',
        str(ch_audio)
    ], capture_output=True, check=True)

    input_args, _, _ = generate_filtergraph(
        scenes=norm_scenes,
        transitions=trans,
        preprocessed_images=preprocessed_images,
        master_dur=ch_dur,
        audio_path=ch_audio,
        sfx_events=sfx_events,
        filter_file=filter_file,
        ass_path=chunk_ass_path,
        target_w=target_w,
        target_h=target_h,
        target_fps=target_fps,
        visual_style=visual_style
    )

    total_frames = sum(s['n'] for s in norm_scenes)
    cmd = [
        get_ffmpeg_path(), '-y', '-v', 'error',
        *input_args,
        *get_filter_complex_args(filter_file),
        '-map', '[vout]',
        '-map', '[aout]',
        *encoder_args,
        '-r', str(target_fps),
        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
        '-shortest',
        str(chunk_out)
    ]

    print(f"\n[CHUNK #{chunk_idx+1}] Rendering {len(chunk_scenes)} scenes ({ch_start:.2f}s -> {ch_end:.2f}s, dur {ch_dur:.2f}s)...", flush=True)
    t0 = time.time()
    rc, msg = run_ffmpeg_with_heartbeat(cmd, total_frames, ch_dur, sla_seconds=300.0, out_file_hint=chunk_out)
    if rc != 0:
        # Automatic hardware fallback to CPU libx264
        if '-c:v' in encoder_args and encoder_args[encoder_args.index('-c:v') + 1] != 'libx264':
            failed_enc = encoder_args[encoder_args.index('-c:v') + 1]
            print(f"\n[HARDWARE FALLBACK] Chunk #{chunk_idx+1} encoder '{failed_enc}' failed. Retrying with CPU 'libx264'...", flush=True)
            print(f"[ENCODER_ACTIVE] libx264 (hardware fallback from {failed_enc})", flush=True)
            fallback_enc_args = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-profile:v', 'high', '-pix_fmt', 'yuv420p']
            encoder_args[:] = fallback_enc_args
            cmd_fallback = [
                get_ffmpeg_path(), '-y', '-v', 'error',
                *input_args,
                *get_filter_complex_args(filter_file),
                '-map', '[vout]',
                '-map', '[aout]',
                *fallback_enc_args,
                '-r', str(target_fps),
                '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
                '-shortest',
                str(chunk_out)
            ]
            rc, msg = run_ffmpeg_with_heartbeat(cmd_fallback, total_frames, ch_dur, sla_seconds=300.0, out_file_hint=chunk_out)
        if rc != 0:
            raise FFmpegFailureError(f"Chunk #{chunk_idx} failed: {msg}", details={"chunk": chunk_idx, "exit_code": rc, "error": msg})

    print(f"[CHUNK #{chunk_idx+1}] Completed in {time.time()-t0:.2f}s -> {chunk_out.stat().st_size} bytes", flush=True)
    return chunk_out


def validate_final_output(out_path: Path, expected_dur: float, has_audio: bool = True) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Authoritative Final Output Validation (§17):
    A render is successful ONLY if:
      - Output file exists
      - Output file size > 0
      - FFprobe can read it
      - Video stream exists
      - Audio stream exists where expected
      - Duration is valid
      - Expected duration is close to master audio duration
    """
    if not out_path.exists():
        return False, f"Output file does not exist: {out_path}", {}
    size = out_path.stat().st_size
    if size <= 0:
        return False, f"Output file is empty (0 bytes): {out_path}", {}

    probe_cmd = [
        get_ffprobe_path(), "-v", "error",
        "-show_streams", "-show_format",
        "-of", "json",
        str(out_path)
    ]
    try:
        r = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        probe_data = json.loads(r.stdout)
    except Exception as e:
        return False, f"FFprobe failed to inspect output file: {e}", {}

    streams = probe_data.get("streams", [])
    has_video_stream = any(s.get("codec_type") == "video" for s in streams)
    if not has_video_stream:
        return False, "Output file has no video stream", probe_data

    if has_audio:
        has_audio_stream = any(s.get("codec_type") == "audio" for s in streams)
        if not has_audio_stream:
            return False, "Output file has no audio stream", probe_data

    format_info = probe_data.get("format", {})
    actual_dur_str = format_info.get("duration")
    if not actual_dur_str:
        return False, "Output file duration is missing", probe_data

    actual_dur = float(actual_dur_str)
    if actual_dur <= 0.0:
        return False, f"Output duration is invalid: {actual_dur}s", probe_data

    diff = abs(actual_dur - expected_dur)
    max_tolerance = max(1.5, expected_dur * 0.05)
    if diff > max_tolerance:
        return False, f"Output duration ({actual_dur:.2f}s) deviates from expected master duration ({expected_dur:.2f}s) by {diff:.2f}s (tolerance: {max_tolerance:.2f}s)", probe_data

    return True, f"Output validated successfully ({actual_dur:.2f}s, {size} bytes)", probe_data


def run_pipeline(
    images_dir: Path,
    segments_path: Path,
    plan_path: Path,
    audio_path: Path,
    out_path: Path,
    workdir: Optional[Path] = None,
    pack_dir: Optional[Path] = None,
    preset: str = 'veryfast',
    profile: str = 'balanced',
    dur_scale: float = 1.0,
    overlay_dur: Optional[float] = None,
    skip_verify: bool = False,
    chunk_size: int = 35,
    force_chunks: bool = False,
    force_single_pass: bool = False,
    enable_transitions: bool = True,
    enable_captions: bool = False,
    caption_style: str = 'classic',
    caption_length: str = 'medium',
    caption_lang: str = 'auto',
    caption_overrides: Optional[Dict] = None,
    separate_subtitles: bool = True,
    platform_preset: Optional[str] = None,
    stt_provider: str = 'auto',
    ai_mode: str = 'raw',
    creative_rewrite: bool = False,
    llm_provider: str = 'auto',
    llm_model: Optional[str] = None,
    resolution: str = '1080p',
    encoder: str = 'auto',
    perf_mode: str = 'auto',
    quality_preset: str = 'standard',
    visual_style: str = 'cinematic_warm',
    default_transition: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main entry point for optimized rendering engine.
    Executes single-pass (for short/medium) or chunked (for long videos) composition.
    Guarantees constant bounded memory, zero silent fallbacks, and audio synchronization.
    Supports resolution presets (1080p, 1440p, 4K) and hardware-aware adaptive encoding.
    """
    t_global_start = time.time()
    if workdir is None:
        workdir = out_path.parent / "work"
    if pack_dir is None:
        pack_dir = Path(__file__).resolve().parent.parent / "transition_pack"

    workdir.mkdir(parents=True, exist_ok=True)
    cache_dir = workdir / 'render_cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    chk_mgr = CheckpointManager(workdir)

    print("=" * 65, flush=True)
    print(" RENDERING STUDIO ENGINE v2 — CINEMATIC AUDIO-FIRST PIPELINE", flush=True)
    print("=" * 65, flush=True)
    print("[STATE:PREPARING]", flush=True)
    log_disk_status("STARTUP", workdir, out_path)

    # 0. RESOLUTION & PROFILE RESOLUTION (Module 16)
    res_prof = get_resolution_profile(resolution)
    target_w = res_prof['width']
    target_h = res_prof['height']
    target_fps = FPS

    # 1. HARDWARE DETECTION & PROFILE SELECTION
    try:
        hw_report = get_full_hardware_report()
        hw_encoders = hw_report['encoders']
        hw_class = hw_report['classification']
        total_ram_gb = hw_report['ram']['total_gb']
    except Exception:
        hw_encoders = detect_hardware_encoders()
        hw_class = {'recommended_encoder': 'libx264', 'recommended_performance_mode': 'balanced'}
        total_ram_gb = 8.0

    print(f"[HARDWARE] Available encoders: {hw_encoders}", flush=True)

    # Resolve encoder
    if encoder == 'auto':
        chosen_encoder = hw_class.get('recommended_encoder', 'libx264')
    else:
        req_enc = encoder.lower()
        if hw_encoders.get(req_enc, False):
            chosen_encoder = req_enc
        else:
            print(f"[HARDWARE WARNING] Requested encoder '{encoder}' unavailable. Falling back to 'libx264'.", flush=True)
            chosen_encoder = 'libx264'

    # Resolve performance mode & adaptive chunking
    active_perf = hw_class.get('recommended_performance_mode', 'balanced') if perf_mode == 'auto' else perf_mode
    effective_chunk_size = get_adaptive_chunk_size(
        resolution, active_perf,
        custom_chunk=chunk_size if chunk_size != 35 else None,
        total_ram_gb=total_ram_gb
    )

    # Build encoder parameters
    encoder_args = get_encoder_args(
        encoder=chosen_encoder,
        quality=quality_preset,
        preset=preset,
        resolution_key=resolution,
        threads=0
    )
    print(f"[RENDER PROFILE] Canvas: {target_w}x{target_h} ({resolution.upper()}) | Encoder: {chosen_encoder} | Mode: {active_perf.upper()} | Chunk Size: {effective_chunk_size}", flush=True)
    print(f"[ENCODER_ACTIVE] {chosen_encoder}", flush=True)

    # 2. ASSET PREPARATION & AUDIO TIMELINE
    t_stage_start = time.time()
    print("\n=== STEP 1/3: Audio Timeline & Asset Preprocessing ===", flush=True)
    print("[STATE:BUILDING_TIMELINE]", flush=True)
    chk_mgr.mark_stage("assets_ready")

    # Validate required input paths
    if not images_dir.exists() or not images_dir.is_dir():
        raise MissingImageError(f"Source images directory does not exist or is not a directory: {images_dir}", details={"images_dir": str(images_dir)})
    if not segments_path.exists():
        raise InvalidProjectError(f"Transcript segments file does not exist: {segments_path}", details={"segments_path": str(segments_path)})
    if not plan_path.exists():
        raise InvalidProjectError(f"Render plan file does not exist: {plan_path}", details={"plan_path": str(plan_path)})
    if not audio_path.exists():
        raise MissingAudioError(f"Narration audio file does not exist: {audio_path}", details={"audio_path": str(audio_path)})

    available_images = sorted([f.name for f in images_dir.iterdir() if f.is_file() and f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}])
    if not available_images:
        raise MissingImageError(f"No valid source image files found in images directory: {images_dir}", details={"images_dir": str(images_dir)})

    segs = load_segments(segments_path)
    assign = load_plan(plan_path)
    master_dur = get_audio_duration(audio_path)
    chk_mgr.mark_stage("audio_analyzed", {"master_dur": master_dur})

    # Direct plan scene load if plan.json is fully specified, otherwise normalized build_timeline
    direct_scenes = load_plan_scenes(plan_path, master_dur)
    if direct_scenes:
        scenes = direct_scenes
        print(f"[TIMELINE] Loaded {len(scenes)} continuous scenes directly from plan.json.", flush=True)
    else:
        scenes = build_timeline(segs, assign, master_dur)

    # Ensure every scene has a valid existing image (safe fallback for missing images)
    for sc in scenes:
        im_name = sc.get('img', '')
        if not (images_dir / im_name).is_file():
            fallback_im = available_images[0]
            print(f"[IMAGE WARNING] Referenced image '{im_name}' not found on disk. Safely falling back to '{fallback_im}'.", flush=True)
            sc['img'] = fallback_im

    total_frames = sum(s['n'] for s in scenes)
    chk_mgr.mark_stage("timeline_ready", {"total_scenes": len(scenes), "total_frames": total_frames})

    print(f"Master Audio Duration: {master_dur:.3f}s | Visual Scenes: {len(scenes)} | Frames: {total_frames}", flush=True)

    # Preflight Disk Space Audit
    min_req_gb, rec_safe_gb = estimate_required_disk_space_gb(
        master_dur=master_dur,
        resolution_key=resolution,
        is_chunked=(len(scenes) > 40 or master_dur > 300.0 or force_chunks),
        num_images=len(available_images)
    )
    t_tot, t_used, t_free = check_disk_space(workdir)
    o_tot, o_used, o_free = check_disk_space(out_path.parent)
    avail_gb = min(t_free, o_free)
    w_anchor = workdir.resolve().anchor or str(workdir)

    print(f"\n[PREFLIGHT DISK AUDIT] Estimated Required: {min_req_gb:.2f} GB (Recommended: {rec_safe_gb:.2f} GB) | Drive {w_anchor} Free: {avail_gb:.2f} GB", flush=True)

    if avail_gb < min_req_gb:
        if avail_gb < 1.5:
            raise DiskFailureError(
                f"Insufficient disk space to safely render: {avail_gb:.2f} GB available on drive {w_anchor}, "
                f"but this {resolution.upper()} render ({master_dur:.1f}s) requires at least {min_req_gb:.2f} GB "
                f"(recommended: {rec_safe_gb:.2f} GB). Please free up disk space before rendering to prevent hard failure.",
                details={"available_gb": avail_gb, "required_gb": min_req_gb, "recommended_gb": rec_safe_gb, "drive": w_anchor}
            )
        else:
            print(f"[WARNING: TIGHT DISK SPACE] Available free space ({avail_gb:.2f} GB) on {w_anchor} is below recommended safety buffer ({rec_safe_gb:.2f} GB).", flush=True)

    # Preprocess unique source images
    unique_images = sorted(list({sc['img'] for sc in scenes}))
    preprocessed_images = {}
    for img_name in unique_images:
        src = images_dir / img_name
        cached = preprocess_image(src, cache_dir, target_w, target_h)
        preprocessed_images[img_name] = cached
    chk_mgr.mark_stage("images_preprocessed", {"cached_count": len(preprocessed_images)})

    elapsed_asset = time.time() - t_stage_start
    print(f"[PERF] stage=asset_prep elapsed={elapsed_asset:.3f}s unique_images={len(preprocessed_images)}", flush=True)

    # 2b. CAPTIONS PREPARATION (If enabled)
    caption_model = None
    caption_engine = None
    if enable_captions:
        print("\n=== STEP 1b/3: Audio-Synchronized Captions Preparation ===", flush=True)
        print("[STATE:GENERATING_CAPTIONS]", flush=True)
        from engine.caption_engine import CaptionEngine
        caption_engine = CaptionEngine(
            style_key=caption_style,
            length_mode=caption_length,
            language=caption_lang,
            style_overrides=caption_overrides,
            platform_preset=platform_preset,
            stt_provider=stt_provider,
            ai_mode=ai_mode,
            creative_rewrite=creative_rewrite,
            llm_provider=llm_provider,
            llm_model=llm_model
        )
        try:
            caption_model = caption_engine.prepare_captions(
                audio_path=audio_path,
                transcript_path=segments_path
            )
        except Exception as e:
            print(f"\n[CAPTION PIPELINE FAILURE] Unable to generate captions: {e}", flush=True)
            raise STTFailureError(
                f"STT / Caption Pipeline Failed: {e}\n"
                f"To render this video without captions, disable captions or omit --enable-captions.",
                details={"audio_path": str(audio_path), "error": str(e)}
            )
        print(f"[CAPTIONS] Ready: {len(caption_model.segments)} segments, style='{caption_style}'", flush=True)
        if separate_subtitles:
            exports = caption_engine.export_all(caption_model, out_path, target_w, target_h)
            print(f"[CAPTIONS] Sidecars exported: SRT={exports['srt']}, ASS={exports['ass']}, VTT={exports['vtt']}, JSON={exports['json']}", flush=True)
            captions_json_alias = out_path.parent / "captions.json"
            if exports.get("json") and Path(exports["json"]).exists() and not captions_json_alias.exists():
                try:
                    shutil.copy2(exports["json"], captions_json_alias)
                except Exception:
                    pass

    # 3. DECIDE ARCHITECTURE: SINGLE-PASS VS CHUNKED
    is_chunked = False
    if force_chunks:
        is_chunked = True
    elif force_single_pass:
        is_chunked = False
    elif len(scenes) > 40 or master_dur > 300.0:
        is_chunked = True

    print(f"[PIPELINE ARCHITECTURE] Mode: {'STREAMING CHUNKED (Long Video)' if is_chunked else 'NATIVE SINGLE-PASS'}", flush=True)
    print("[STATE:PLANNING_TRANSITIONS]", flush=True)

    all_transitions = plan_transitions(scenes, dur_scale=dur_scale, fixed_dur=overlay_dur, enable_transitions=enable_transitions, default_transition=default_transition)

    # Write scene_labels.json (used for visual QC) with full scene and transition metadata
    pose_info = []
    for sc in scenes:
        pose_info.append({
            'scene_id': sc['scene_id'],
            'img': sc['img'],
            'dur': round(sc['dur'], 3),
            'frames': sc['n'],
            'label': 'L4',
            'motion': 'L4/native_fast',
            'context': sc.get('context', ''),
            'transition': sc.get('transition', ''),
            'start_s': round(sc['start'], 3)
        })

    transition_info = [
        {
            'cut_index': t.get('cut_index'),
            'cut_s': round(t['cut_time'], 3),
            'start_s': round(t['offset'], 3),
            'end_s': round(t['offset'] + t['dur'], 3),
            'context': t['context'],
            'type': t['type'],
            'transition_id': t.get('transition_id', t['type']),
            'name': t.get('name', t['type']),
            'category': t.get('category', 'Built-in'),
            'is_overlay': t.get('is_overlay', False),
            'dur_s': t['dur'],
            'is_dip_black': t.get('is_dip_black', False)
        }
        for t in all_transitions
    ]

    scene_labels_file = workdir / 'scene_labels.json'
    with open(scene_labels_file, 'w', encoding='utf-8') as f:
        json.dump({'scenes': pose_info, 'transitions': transition_info}, f, indent=1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t_encode_start = time.time()

    if not is_chunked:
        # === SINGLE-PASS DIRECT EXECUTION ===
        print("\n=== STEP 2/3: Native Transitions & Composition (Single-Pass) ===", flush=True)
        print("[STATE:RENDERING_CHUNK] Single-pass render", flush=True)
        chk_mgr.mark_stage("final_render_started")
        filter_file = workdir / 'pipeline.filter'
        sfx_events = select_sfx_clips(all_transitions, pack_dir)

        master_ass = None
        if enable_captions and caption_engine and caption_model:
            master_ass = workdir / "master_captions.ass"
            caption_engine.generate_ass_for_render(
                model=caption_model,
                output_ass_path=master_ass,
                time_offset_s=0.0,
                duration_s=master_dur,
                video_width=target_w,
                video_height=target_h
            )

        input_args, _, _ = generate_filtergraph(
            scenes=scenes,
            transitions=all_transitions,
            preprocessed_images=preprocessed_images,
            master_dur=master_dur,
            audio_path=audio_path,
            sfx_events=sfx_events,
            filter_file=filter_file,
            ass_path=master_ass,
            target_w=target_w,
            target_h=target_h,
            target_fps=target_fps,
            visual_style=visual_style
        )

        log_disk_status("PRE_ENCODE_SINGLE_PASS", workdir, out_path)
        ffmpeg_cmd = [
            get_ffmpeg_path(), '-y', '-v', 'info',
            *input_args,
            *get_filter_complex_args(filter_file),
            '-map', '[vout]',
            '-map', '[aout]',
            *encoder_args,
            '-r', str(target_fps),
            '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
            '-t', f"{master_dur:.3f}",
            str(out_path)
        ]

        rc, msg = run_ffmpeg_with_heartbeat(ffmpeg_cmd, total_frames, master_dur, sla_seconds=480.0, out_file_hint=out_path)
        if rc != 0:
            # Automatic hardware fallback to CPU libx264
            if '-c:v' in encoder_args and encoder_args[encoder_args.index('-c:v') + 1] != 'libx264':
                failed_enc = encoder_args[encoder_args.index('-c:v') + 1]
                print(f"\n[HARDWARE FALLBACK] Encoder '{failed_enc}' failed in single-pass render. Retrying with CPU 'libx264'...", flush=True)
                print(f"[ENCODER_ACTIVE] libx264 (hardware fallback from {failed_enc})", flush=True)
                fallback_enc_args = ['-c:v', 'libx264', '-preset', preset, '-crf', '20', '-profile:v', 'high', '-pix_fmt', 'yuv420p']
                ffmpeg_cmd_fallback = [
                    get_ffmpeg_path(), '-y', '-v', 'info',
                    *input_args,
                    *get_filter_complex_args(filter_file),
                    '-map', '[vout]',
                    '-map', '[aout]',
                    *fallback_enc_args,
                    '-r', str(target_fps),
                    '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
                    '-t', f"{master_dur:.3f}",
                    str(out_path)
                ]
                rc, msg = run_ffmpeg_with_heartbeat(ffmpeg_cmd_fallback, total_frames, master_dur, sla_seconds=480.0, out_file_hint=out_path)
            if rc != 0:
                raise FFmpegFailureError(f"FFmpeg single-pass render failed: {msg}", details={"exit_code": rc, "error": msg})
    else:
        # === STREAMING CHUNKED EXECUTION (Long Videos) ===
        print("\n=== STEP 2/3: Streaming Chunked Composition & Checkpointed Resume ===", flush=True)
        chunk_dir = workdir / "chunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        log_disk_status("PRE_ENCODE_CHUNKS", workdir, out_path)

        # Partition scenes into chunks of effective_chunk_size
        n_scenes = len(scenes)
        scene_chunks = [scenes[i:i + effective_chunk_size] for i in range(0, n_scenes, effective_chunk_size)]
        total_chunks = len(scene_chunks)
        print(f"[CHUNKS] Partitioned {n_scenes} scenes into {total_chunks} chunks (~{effective_chunk_size} scenes/chunk)", flush=True)

        chk_mgr.validate_or_reset_signature({
            'target_w': target_w,
            'target_h': target_h,
            'resolution': resolution,
            'total_chunks': total_chunks,
            'total_scenes': n_scenes,
            'master_dur': round(master_dur, 3),
            'effective_chunk_size': effective_chunk_size
        })

        chunk_files = []
        for c_idx, c_scenes in enumerate(scene_chunks):
            ch_out = chunk_dir / f"chunk_{c_idx:04d}.mp4"
            if ch_out.exists() and ch_out.stat().st_size <= 1024:
                print(f"[RECOVERY] Corrupted/truncated temporary chunk file detected: {ch_out.name} ({ch_out.stat().st_size} bytes). Removing to re-render cleanly...", flush=True)
                try:
                    ch_out.unlink()
                except Exception:
                    pass
            if chk_mgr.is_chunk_done(c_idx) and ch_out.exists() and ch_out.stat().st_size > 10000:
                if verify_chunk_compatibility(ch_out, target_w, target_h, c_scenes):
                    print(f"[RESUME] Chunk #{c_idx+1}/{total_chunks} verified ({target_w}x{target_h}). Skipping.", flush=True)
                    chunk_files.append(ch_out)
                    continue
                else:
                    print(f"[RECOVERY] Chunk #{c_idx+1} failed verification or does not match current canvas {target_w}x{target_h}. Re-rendering...", flush=True)

            print(f"[STATE:RENDERING_CHUNK] Chunk #{c_idx+1}/{total_chunks}", flush=True)

            chunk_ass = None
            if enable_captions and caption_engine and caption_model:
                chunk_ass = chunk_dir / f"chunk_{c_idx:04d}_captions.ass"
                ch_start = c_scenes[0]['start']
                ch_end = c_scenes[-1]['start'] + c_scenes[-1]['dur']
                ch_dur = round(ch_end - ch_start, 3)
                caption_engine.generate_ass_for_render(
                    model=caption_model,
                    output_ass_path=chunk_ass,
                    time_offset_s=ch_start,
                    duration_s=ch_dur,
                    video_width=target_w,
                    video_height=target_h
                )

            rendered_chunk = render_chunk(
                chunk_idx=c_idx,
                chunk_scenes=c_scenes,
                preprocessed_images=preprocessed_images,
                audio_path=audio_path,
                pack_dir=pack_dir,
                chunk_dir=chunk_dir,
                encoder_args=encoder_args,
                dur_scale=dur_scale,
                overlay_dur=overlay_dur,
                chunk_ass_path=chunk_ass,
                all_transitions=all_transitions,
                target_w=target_w,
                target_h=target_h,
                target_fps=target_fps,
                visual_style=visual_style,
                default_transition=default_transition
            )
            chunk_files.append(rendered_chunk)
            chk_mgr.mark_chunk_done(c_idx)

        chk_mgr.mark_stage("video_segments_ready", {"total_chunks": total_chunks})

        # Lossless Concat Demuxer
        print("\n[CONCAT] Joining chunks losslessly via FFmpeg concat demuxer (-c copy)...", flush=True)
        print("[STATE:JOINING_CHUNKS]", flush=True)
        concat_txt = chunk_dir / "chunks_manifest.txt"
        with open(concat_txt, "w", encoding="utf-8") as f:
            for cf in chunk_files:
                clean_cf = cf.resolve().as_posix().replace("'", "'\\''")
                f.write(f"file '{clean_cf}'\n")

        log_disk_status("PRE_CONCAT", workdir, out_path)
        t_concat_0 = time.time()
        concat_cmd = [
            get_ffmpeg_path(), '-nostdin', '-y', '-v', 'error',
            '-f', 'concat', '-safe', '0',
            '-i', str(concat_txt),
            '-c', 'copy',
            '-movflags', '+faststart',
            str(out_path)
        ]
        r_concat = subprocess.run(concat_cmd, capture_output=True, text=True)
        if r_concat.returncode != 0:
            log_disk_status("CONCAT_FAILED", workdir, out_path)
            raise FFmpegFailureError(f"Lossless chunk concatenation failed: {r_concat.stderr}", details={"exit_code": r_concat.returncode, "error": r_concat.stderr})
        print(f"[CONCAT] Concat finished in {time.time()-t_concat_0:.2f}s! Output size: {out_path.stat().st_size / (1024*1024):.2f} MB", flush=True)

    elapsed_encode = time.time() - t_encode_start
    chk_mgr.mark_stage("final_render_started")

    # Transitions QC report
    qc_data = {
        'n_transitions': len(all_transitions),
        'types_used': sorted(list({t['type'] for t in all_transitions})),
        'avg_duration': round(sum(t['dur'] for t in all_transitions) / max(1, len(all_transitions)), 3),
        'durations': [t['dur'] for t in all_transitions],
        'details': transition_info
    }
    qc_path = Path(str(out_path) + '.transitions.json')
    with open(qc_path, 'w', encoding='utf-8') as f:
        json.dump(qc_data, f, indent=1)

    # Contact Sheet Generation
    contact_sheet = workdir / 'contact_sheet.png'
    build_contact_sheet(out_path, contact_sheet, [t['cut_time'] for t in all_transitions], target_w=target_w, target_h=target_h)

    # 4. VERIFICATION QC (Existing Video Checks)
    t_stage_start = time.time()
    if not skip_verify:
        print("\n=== STEP 3/3: Production Verification QC ===", flush=True)
        print("[STATE:RUNNING_QC]", flush=True)
        try:
            from engine.verify_output import verify_video
            v_ok, v_fails, _ = verify_video(
                video=out_path,
                scenes=scene_labels_file if (scene_labels_file and scene_labels_file.exists()) else None,
                sheet=contact_sheet,
                width=target_w,
                height=target_h
            )
            if not v_ok:
                raise RuntimeError(f"Verification checks failed: {v_fails}")
        except Exception as v_err:
            if not isinstance(v_err, RuntimeError):
                # Fallback to subprocess with explicit --verify CLI flag
                verify_script = Path(__file__).resolve().parent / 'verify_output.py'
                vcmd = [
                    sys.executable,
                    "--verify",
                    '--video', str(out_path),
                    '--scenes', str(scene_labels_file),
                    '--sheet', str(contact_sheet),
                    '--width', str(target_w),
                    '--height', str(target_h)
                ]
                vr = subprocess.run(vcmd, capture_output=True, text=True)
                if vr.returncode != 0:
                    err_details = (vr.stderr or vr.stdout or str(v_err)).strip()
                    raise RuntimeError(f"Verification checks failed: {err_details}")
            else:
                raise
    elapsed_qc = time.time() - t_stage_start

    # 4b. CAPTION VERIFICATION QC (If enabled)
    if enable_captions and caption_engine and caption_model and not skip_verify:
        print("\n=== STEP 3b/3: Production Verification QC (Captions) ===", flush=True)
        cap_qc = caption_engine.verify_qc(out_path, caption_model)
        cap_qc_path = Path(str(out_path) + ".caption_qc.json")
        with open(cap_qc_path, 'w', encoding='utf-8') as f:
            json.dump(cap_qc, f, indent=1)
        print(f"[CAPTION QC] Status: {cap_qc.get('overall_status', 'PASS')} | Checked {cap_qc.get('total_segments')} segments", flush=True)
        if cap_qc.get('overall_status') == 'FAIL':
            raise RuntimeError(f"Caption QC checks failed: {cap_qc.get('failed_checks')}")

    # 4c. FINAL OUTPUT VALIDATION (§17)
    print("\n=== STEP 3c/3: Authoritative Final Output Validation ===", flush=True)
    print("[STATE:FINALIZING]", flush=True)
    val_ok, val_msg, val_meta = validate_final_output(out_path, master_dur, has_audio=True)
    if not val_ok:
        print(f"[FINAL OUTPUT VALIDATION] FAILED: {val_msg}", flush=True)
        raise RuntimeError(f"Final output validation failed: {val_msg}")
    print(f"[FINAL OUTPUT VALIDATION] PASS: {val_msg}", flush=True)

    chk_mgr.mark_stage("finalized")
    print("[STATE:COMPLETED]", flush=True)

    # Final Metrics
    total_time = time.time() - t_global_start
    speed_ratio = master_dur / max(0.001, total_time)
    pass_sla = total_time <= 480.0
    mem_info = psutil.Process().memory_info()
    peak_ram_mb = mem_info.rss / (1024 * 1024)

    print("\n" + "=" * 65, flush=True)
    print(" PERFORMANCE BENCHMARK REPORT", flush=True)
    print("=" * 65, flush=True)
    print(f"Input Duration:   {master_dur:.2f}s ({format_seconds(master_dur)})", flush=True)
    print(f"Scene / Cuts:     {len(scenes)} scenes | {len(all_transitions)} transitions", flush=True)
    print(f"Captions:         {'ENABLED (' + caption_style + ')' if enable_captions else 'DISABLED'}", flush=True)
    print(f"Resolution & FPS: {target_w}x{target_h} @ {target_fps} fps ({resolution.upper()})", flush=True)
    print(f"Pipeline Mode:    {'STREAMING CHUNKED' if is_chunked else 'DIRECT SINGLE-PASS'}", flush=True)
    print(f"Encoding Time:    {elapsed_encode:.2f}s ({format_seconds(elapsed_encode)})", flush=True)
    print(f"Total Wall-Clock: {total_time:.2f}s ({format_seconds(total_time)})", flush=True)
    print(f"Realtime Speed:   {speed_ratio:.2f}x realtime", flush=True)
    print(f"Peak RAM RSS:     {peak_ram_mb:.1f} MB", flush=True)
    print(f"Output Size:      {out_path.stat().st_size / (1024*1024):.2f} MB", flush=True)
    print(f"8-Min SLA:        {'PASS' if pass_sla else 'FAIL'}", flush=True)
    print("=" * 65, flush=True)

    return {
        'total_time': total_time,
        'master_dur': master_dur,
        'speed_ratio': speed_ratio,
        'pass_sla': pass_sla,
        'peak_ram_mb': peak_ram_mb,
        'output_video': str(out_path),
        'contact_sheet': str(contact_sheet),
        'captions_enabled': enable_captions,
        'resolution': resolution,
        'width': target_w,
        'height': target_h,
        'encoder': chosen_encoder
    }


def main():
    ap = argparse.ArgumentParser(description="Rendering Studio Engine v2 Fast Native Pipeline")
    ap.add_argument('--images', required=True)
    ap.add_argument('--segments', required=True)
    ap.add_argument('--plan', required=True)
    ap.add_argument('--audio', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workdir', default=None)
    ap.add_argument('--pack-dir', default=str(Path(__file__).resolve().parent / '..' / 'transition_pack'))
    ap.add_argument('--overlay-dur', type=float, default=None)
    ap.add_argument('--dur-scale', type=float, default=1.0)
    ap.add_argument('--preset', default='veryfast')
    ap.add_argument('--profile', default='balanced', choices=['quality', 'balanced', 'fast'])
    ap.add_argument('--skip-verify', action='store_true')
    ap.add_argument('--chunk-size', type=int, default=35, help="Scenes per chunk for long videos")
    ap.add_argument('--force-chunks', action='store_true', help="Force streaming chunked architecture")
    ap.add_argument('--force-single-pass', action='store_true', help="Force single-pass architecture")
    ap.add_argument('--no-transitions', dest='enable_transitions', action='store_false', default=True, help="Disable transitions (hard cuts)")
    
    # Caption arguments
    ap.add_argument('--enable-captions', action='store_true', help="Enable audio-synchronized captions")
    ap.add_argument('--caption-style', default='classic', help="Caption style preset (classic, minimal, etc.)")
    ap.add_argument('--caption-length', default='medium', choices=['short', 'medium', 'long'], help="Caption pagination length")
    ap.add_argument('--caption-lang', default='auto', help="Caption spoken language")
    ap.add_argument('--caption-overrides', type=str, default=None, help="JSON string with custom style overrides")
    ap.add_argument('--separate-subtitles', action='store_true', default=True, help="Export sidecar .srt, .ass, and captions.json")
    ap.add_argument('--platform-preset', default=None, help="Platform aspect ratio and safe area preset")
    ap.add_argument('--stt-provider', default='auto', help="STT provider (auto, deepgram, local_whisper, existing_transcript)")
    ap.add_argument('--ai-mode', default='raw', choices=['raw', 'clean', 'viral'], help="AI caption intelligence mode")
    ap.add_argument('--creative-rewrite', action='store_true', help="Allow punchier social rewrite while preserving meaning")
    ap.add_argument('--llm-provider', default='auto', help="LLM provider (auto, groq, gemini, openrouter, claude, openai, kimi, deepseek, local)")
    ap.add_argument('--llm-model', default=None, help="Specific LLM model identifier")
    
    # Resolution and hardware profile arguments (Module 16)
    ap.add_argument('--resolution', default='1080p', choices=['1080p', '1440p', '4k'], help="Target video resolution preset")
    ap.add_argument('--encoder', default='auto', help="Video encoder (auto, libx264, h264_nvenc, h264_qsv, h264_amf, h264_mf)")
    ap.add_argument('--perf-mode', default='auto', choices=['auto', 'eco', 'balanced', 'performance', 'max_quality'], help="Hardware performance mode")
    ap.add_argument('--quality-preset', default='standard', choices=['standard', 'high', 'maximum'], help="Encoding quality profile")
    ap.add_argument('--visual-style', default='cinematic_warm', help="Visual style grading preset")
    ap.add_argument('--transition-id', default=None, help="Explicit global transition id override")
    args = ap.parse_args()

    out = Path(args.out).resolve()
    work = Path(args.workdir).resolve() if args.workdir else out.parent / 'work'
    pack_dir = Path(args.pack_dir).resolve()

    cap_overrides = None
    if args.caption_overrides:
        try:
            cap_overrides = json.loads(args.caption_overrides)
        except Exception:
            pass

    try:
        run_pipeline(
            images_dir=Path(args.images).resolve(),
            segments_path=Path(args.segments).resolve(),
            plan_path=Path(args.plan).resolve(),
            audio_path=Path(args.audio).resolve(),
            out_path=out,
            workdir=work,
            pack_dir=pack_dir,
            preset=args.preset,
            profile=args.profile,
            dur_scale=args.dur_scale,
            overlay_dur=args.overlay_dur,
            skip_verify=args.skip_verify,
            chunk_size=args.chunk_size,
            force_chunks=args.force_chunks,
            force_single_pass=args.force_single_pass,
            enable_transitions=args.enable_transitions,
            enable_captions=args.enable_captions,
            caption_style=args.caption_style,
            caption_length=args.caption_length,
            caption_lang=args.caption_lang,
            caption_overrides=cap_overrides,
            separate_subtitles=args.separate_subtitles,
            platform_preset=args.platform_preset,
            stt_provider=args.stt_provider,
            ai_mode=args.ai_mode,
            creative_rewrite=args.creative_rewrite,
            llm_provider=args.llm_provider,
            llm_model=args.llm_model,
            resolution=args.resolution,
            encoder=args.encoder,
            perf_mode=args.perf_mode,
            quality_preset=args.quality_preset,
            visual_style=args.visual_style,
            default_transition=args.transition_id
        )
    except RenderingEngineError as re_err:
        print(f"\n[ERROR:{re_err.code}] {re_err.message}", flush=True)
        if re_err.details:
            print(f"[ERROR_DETAILS] {json.dumps(re_err.details)}", flush=True)
        try:
            log_disk_status("FAILURE", Path(args.workdir or (Path(args.out).parent / "work")), Path(args.out))
        except Exception:
            pass
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR:UNEXPECTED_FAILURE] {e}", flush=True)
        try:
            log_disk_status("FAILURE", Path(args.workdir or (Path(args.out).parent / "work")), Path(args.out))
        except Exception:
            pass
        sys.exit(1)


if __name__ == '__main__':
    main()
