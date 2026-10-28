#!/usr/bin/env python3
"""
semantic_sync.py — Audio-First Semantic Timeline & Image Synchronization Engine.

Architecture:
  AUDIO / NARRATION (Master Timeline)
          ↓
  SPEECH & SILENCE ANALYSIS (or Transcript Segments)
          ↓
  SEMANTIC BEATS & DYNAMIC DURATIONS (1.5s - 6.0s+)
          ↓
  IMAGE RELEVANCE MAPPING (Keywords + Natural Narrative Ordering)
          ↓
  CONTEXT-AWARE CINEMATIC TRANSITIONS
          ↓
  STANDARDIZED TIMELINE & SCENE PLAN PREVIEW
"""

import json
import math
import os
import subprocess
import re
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger("rendering_studio.semantic_sync")

try:
    from engine.timeline_normalizer import TimelineNormalizer
except (ModuleNotFoundError, ImportError):
    try:
        from timeline_normalizer import TimelineNormalizer
    except (ModuleNotFoundError, ImportError):
        from .timeline_normalizer import TimelineNormalizer

# Transition styles, durations, and human-readable labels
CONTEXT_MAP = {
    'normal':          {'xfade': 'fade',       'dur': 0.35, 'label': 'cinematic_dissolve'},
    'location_change': {'xfade': 'wipeleft',   'dur': 0.35, 'label': 'soft_wipe'},
    'story_change':    {'xfade': 'dissolve',   'dur': 0.40, 'label': 'cinematic_dissolve'},
    'turning_point':   {'xfade': 'dissolve',   'dur': 0.40, 'label': 'cinematic_dissolve'},
    'emotional':       {'xfade': 'dissolve',   'dur': 0.45, 'label': 'slow_dissolve'},
    'time_passage':    {'xfade': 'fadeblack',  'dur': 0.40, 'label': 'dip_to_black'},
    'fast':            {'xfade': 'fadefast',   'dur': 0.15, 'label': 'clean_cut'},
}

# Semantic keyword indicators for context and topic inference
LOCATION_KEYWORDS = {
    'where', 'here', 'there', 'city', 'country', 'town', 'river', 'mountain', 'palace',
    'castle', 'empire', 'rome', 'paris', 'london', 'world', 'land', 'sea', 'ocean',
    'location', 'travel', 'arrived', 'went', 'entered', 'borders', 'territory', 'capital',
    'valley', 'forest', 'island', 'desert', 'kingdom', 'province', 'station'
}
TURNING_KEYWORDS = {
    'suddenly', 'however', 'war', 'battle', 'attack', 'destroyed', 'crashed', 'broke',
    'victory', 'defeat', 'climax', 'crisis', 'shock', 'strike', 'rebellion', 'turning',
    'unexpected', 'danger', 'fate', 'moment', 'destiny', 'revolution', 'assassination',
    'confrontation', 'struggle', 'clash', 'disaster', 'explosion', 'downfall'
}
EMOTIONAL_KEYWORDS = {
    'sorrow', 'tragedy', 'love', 'grief', 'hope', 'peace', 'cried', 'loss', 'heart',
    'remember', 'memory', 'beautiful', 'sadness', 'despair', 'solemn', 'spirit', 'tears',
    'sacrifice', 'soul', 'passion', 'suffering', 'devotion', 'longing'
}
TIME_KEYWORDS = {
    'years', 'months', 'decades', 'centuries', 'later', 'meanwhile', 'eventually',
    'after', 'before', 'passed', 'dawn', 'night', 'era', 'generation', 'future', 'past',
    'ancient', 'modern', 'period', 'timeline', 'history', 'chronicle'
}
STOPWORDS = {
    'the', 'and', 'for', 'that', 'this', 'with', 'from', 'have', 'were', 'which',
    'then', 'they', 'their', 'been', 'what', 'when', 'will', 'more', 'about', 'into',
    'some', 'them', 'than', 'also', 'upon', 'over', 'scene', 'image', 'picture'
}


def natural_sort_key(s):
    """Natural alphanumeric sort key (e.g. img_1, img_2, ..., img_10)."""
    text = str(s)
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]


def probe_audio_duration(path: Path) -> float:
    """Accurately probe audio file duration using ffprobe."""
    try:
        from engine.fast_pipeline import get_ffprobe_path
        ffprobe_bin = get_ffprobe_path()
    except Exception:
        ffprobe_bin = "ffprobe"
    r = subprocess.run([
        ffprobe_bin, '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', str(path)
    ], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def detect_speech_and_silences(
    audio_path: Path,
    noise_db: float = -30.0,
    min_silence_dur: float = 0.35
) -> Tuple[List[Dict], List[Dict]]:
    """
    Analyze narration audio for silences and speech phrases using FFmpeg silencedetect.
    Returns (speech_segments, silence_intervals).
    """
    try:
        from engine.fast_pipeline import get_ffmpeg_path
        ffmpeg_bin = get_ffmpeg_path()
    except Exception:
        ffmpeg_bin = "ffmpeg"
    cmd = [
        ffmpeg_bin, '-hide_banner',
        '-i', str(audio_path),
        '-af', f'silencedetect=noise={noise_db}dB:d={min_silence_dur}',
        '-f', 'null', '-'
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)

    silence_starts = [float(x) for x in re.findall(r'silence_start:\s*([\d\.]+)', r.stderr)]
    silence_ends = [float(x) for x in re.findall(r'silence_end:\s*([\d\.]+)', r.stderr)]

    silences = []
    for s_start, s_end in zip(silence_starts, silence_ends):
        if s_end > s_start:
            silences.append({'start': s_start, 'end': s_end, 'dur': round(s_end - s_start, 3)})

    total_dur = probe_audio_duration(audio_path)
    speech_segments = []
    curr = 0.0

    for sil in silences:
        # Place cut point at the silence midpoint, holding previous image across start of pause
        cut_point = round((sil['start'] + sil['end']) / 2.0, 3)
        if cut_point > curr + 1.2:
            speech_segments.append({
                'start': round(curr, 3),
                'end': cut_point,
                'dur': round(cut_point - curr, 3),
                'is_silence': False
            })
            curr = cut_point

    if curr < total_dur:
        speech_segments.append({
            'start': round(curr, 3),
            'end': round(total_dur, 3),
            'dur': round(total_dur - curr, 3),
            'is_silence': False
        })

    return speech_segments, silences


def extract_keywords_and_topic(text: str) -> Tuple[List[str], str, float]:
    """Extract descriptive keywords, classify topic, and calculate semantic importance."""
    words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', text)]
    kw_set = [w for w in words if w not in STOPWORDS]
    keywords = sorted(list(dict.fromkeys(kw_set)))[:6]

    topic = "General Narration"
    importance = 0.5
    kw_overlap = set(words)

    if kw_overlap & TURNING_KEYWORDS:
        topic = "Climax & Conflict"
        importance = 0.9
    elif kw_overlap & EMOTIONAL_KEYWORDS:
        topic = "Emotional & Reflection"
        importance = 0.8
    elif kw_overlap & LOCATION_KEYWORDS:
        topic = "Location & Exploration"
        importance = 0.7
    elif kw_overlap & TIME_KEYWORDS:
        topic = "Time & Historical Context"
        importance = 0.6

    return keywords, topic, round(importance, 2)


def infer_segment_context(
    text: str,
    dur: float,
    silence_dur: float = 0.0,
    is_major_silence: bool = False
) -> str:
    """Infer cinematic transition context from narration text and speech characteristics."""
    # Only prolonged dramatic silences (>= 2.0s) indicate time passage / chapter reset
    if is_major_silence or silence_dur >= 2.0:
        return 'time_passage'

    words = set(re.findall(r'\b[a-zA-Z]{3,}\b', text.lower()))
    if words & TURNING_KEYWORDS:
        return 'turning_point'
    if words & EMOTIONAL_KEYWORDS:
        return 'emotional'
    if words & LOCATION_KEYWORDS:
        return 'location_change'
    if words & TIME_KEYWORDS:
        return 'time_passage'
    if dur < 2.0:
        return 'fast'
    if dur > 5.5:
        return 'story_change'

    return 'normal'


def tokenize_name(name: str) -> List[str]:
    """Extract semantic tokens from image filename (e.g. scene_01_napoleon_battle.jpg -> ['napoleon', 'battle'])."""
    stem = Path(name).stem.lower()
    tokens = re.split(r'[_ \-\.\d]+', stem)
    stopwords = {'scene', 'act', 'img', 'image', 'pic', 'shot', 'v', 'ver', 'final', 'test'}
    return [t for t in tokens if len(t) >= 3 and t not in stopwords]


def score_image_affinity(
    img_name: str,
    img_idx: int,
    total_imgs: int,
    seg_text: str,
    seg_idx: int,
    total_segs: int
) -> float:
    """
    Score match affinity between source image and narration segment.
    Balances keyword semantic overlap + natural narrative sequence progress.
    """
    score = 0.0
    tokens = tokenize_name(img_name)
    text_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', seg_text.lower()))

    # Semantic keyword match bonus
    match_count = sum(1 for t in tokens if t in text_words)
    score += match_count * 2.5

    # Narrative sequence alignment affinity
    if total_segs > 0 and total_imgs > 0:
        img_prog = img_idx / float(total_imgs)
        seg_prog = seg_idx / float(total_segs)
        dist = abs(img_prog - seg_prog)
        seq_bonus = max(0.0, 1.0 - dist)
        score += seq_bonus

    return score


try:
    from engine.sync_engine_v3 import AIImageSyncEngineV3, SyncConfig, SyncQualityReport
except (ModuleNotFoundError, ImportError):
    try:
        from sync_engine_v3 import AIImageSyncEngineV3, SyncConfig, SyncQualityReport
    except (ModuleNotFoundError, ImportError):
        from .sync_engine_v3 import AIImageSyncEngineV3, SyncConfig, SyncQualityReport


def build_semantic_timeline(
    audio_path: Path,
    images: List[str],
    transcript_path: Optional[Path] = None,
    all_images_mode: bool = True,
    min_hold: float = 1.5,
    max_hold: float = 7.5,
    user_overrides: Optional[Dict[int, str]] = None,
    profile: Optional[str] = None,
    sync_mode: Optional[str] = None,
    project_dir: Optional[Path] = None,
    mapping_mode: str = "SEMANTIC_AUTO",
    music_path: Optional[Path] = None,
    pacing_bias: Optional[float] = None,
    broll_path: Optional[Path] = None
) -> Tuple[Dict, Dict]:
    """
    Construct Audio-First Semantic Timeline & Scene Plan using AI Image Sync Engine v3 (Phase 3).
    Guarantees:
      - Master duration strictly matches audio duration (§4).
      - Zero unexplained gaps between consecutive scenes (scene[k].start == scene[k-1].end).
      - Dynamic visual durations based on speech cadence and beats (§21).
      - Adaptive content profiles, entity tracking, visual continuity, user correction memory (§4-§18).
      - Global Hungarian bipartite sequence optimization in SEMANTIC_AUTO mode.
      - Explicit user overrides preserved (§20).
      - Deterministic fallback if anything fails (§33, §34).
    """
    resolved_audio = Path(audio_path).resolve() if audio_path else None
    if resolved_audio and resolved_audio.exists() and resolved_audio.stat().st_size > 0:
        try:
            master_dur = probe_audio_duration(resolved_audio)
        except Exception as e:
            logger.warning(f"Could not probe audio duration for {resolved_audio}: {e}")
            master_dur = float(len(images) * 3.0)
    else:
        resolved_audio = None
        master_dur = float(len(images) * 3.0)

    if not images:
        raise ValueError("No images provided for timeline mapping.")

    # 1. Determine images directory and filenames
    first_img = Path(images[0])
    if first_img.exists():
        images_dir = first_img.resolve().parent
    else:
        if resolved_audio:
            project_images_dir = resolved_audio.parent / "images"
        elif project_dir:
            project_images_dir = Path(project_dir) / "images"
        else:
            project_images_dir = Path.cwd() / "images"

        if project_images_dir.exists() and any(project_images_dir.glob("*.*")):
            images_dir = project_images_dir
        else:
            images_dir = Path.cwd()
    img_filenames = [Path(img).name for img in images]

    # Determine project directory
    p_dir = project_dir or (resolved_audio.parent if resolved_audio else images_dir.parent)

    # 2. Execute AI Image Sync Engine v3
    if resolved_audio:
        try:
            v3_engine = AIImageSyncEngineV3()
            transcript_obj, plan_obj, report = v3_engine.synchronize_timeline(
                audio_path=resolved_audio,
                images_dir=images_dir,
                image_filenames=img_filenames,
                transcript_path=transcript_path,
                all_images_mode=all_images_mode,
                user_overrides=user_overrides,
                profile=profile,
                sync_mode=sync_mode,
                project_dir=p_dir,
                mapping_mode=mapping_mode,
                music_path=music_path,
                pacing_bias=pacing_bias,
                broll_path=broll_path
            )
            plan_obj["sync_report"] = asdict(report) if hasattr(report, "__dataclass_fields__") else report
            return transcript_obj, plan_obj
        except Exception as exc:
            logger.warning(f"AI Image Sync Engine v3 encountered error, using deterministic fallback: {exc}")

    # --- DETERMINISTIC FALLBACK (§33, §34) ---
    sorted_images = [Path(img).name for img in sorted(images, key=natural_sort_key)]
    n_imgs = len(sorted_images)

    raw_segments = []
    if transcript_path and transcript_path.exists():
        try:
            with open(transcript_path, 'r', encoding='utf-8') as f:
                d = json.load(f)
            raw = d.get('segments', []) if isinstance(d, dict) else d
            raw_segments = [{'start': float(s['start']), 'end': float(s['end']), 'text': s.get('text', '')} for s in raw]
        except Exception:
            raw_segments = []

    if not raw_segments:
        if resolved_audio and resolved_audio.exists():
            try:
                speech_segs, _ = detect_speech_and_silences(resolved_audio)
                if speech_segs:
                    raw_segments = speech_segs
            except Exception as d_err:
                logger.warning(f"Speech silence detection fallback failed: {d_err}")
        if not raw_segments:
            n_target = n_imgs
            step = master_dur / max(1, n_target)
            t = 0.0
            for i in range(n_target):
                end_t = master_dur if i == n_target - 1 else round(t + step, 3)
                raw_segments.append({'start': round(t, 3), 'end': end_t, 'text': f"Scene {i+1}"})
                t = end_t

    continuous_segs = TimelineNormalizer.normalize_speech_segments(
        raw_segments=raw_segments,
        master_dur=master_dur,
        hold_mode='extend_hold'
    )

    scenes = []
    final_segments = []

    if all_images_mode and n_imgs > len(continuous_segs):
        beat_items = TimelineNormalizer.partition_into_visual_beats(
            continuous_segments=continuous_segs,
            target_beats=n_imgs,
            master_dur=master_dur
        )
        for idx, beat in enumerate(beat_items):
            assigned_img = sorted_images[idx % n_imgs]
            seg_text = beat.get('text', '')
            kws, topic, importance = extract_keywords_and_topic(seg_text)
            ctx = infer_segment_context(seg_text, beat['dur'], silence_dur=beat.get('silence_dur', 0.0), is_major_silence=beat.get('is_silence', False))
            final_segments.append({
                'start': beat['start'], 'end': beat['end'], 'dur': beat['dur'],
                'text': seg_text, 'keywords': kws, 'topic': topic, 'importance': importance
            })
            scenes.append({
                'scene_id': f"scene_{idx+1:04d}",
                'segment_index': idx,
                'image': assigned_img,
                'image_id': f"img_{idx % n_imgs + 1:03d}",
                'context': ctx,
                'transition': CONTEXT_MAP.get(ctx, CONTEXT_MAP['normal'])['label'],
                'start': beat['start'],
                'end': beat['end'],
                'dur': beat['dur'],
                'confidence': 0.70,
                'confidence_level': 'MEDIUM',
                'match_reason': ['deterministic_fallback'],
                'source': 'deterministic_fallback',
                'user_override': False,
                'narration_text': seg_text
            })
    else:
        for i, sg in enumerate(continuous_segs):
            seg_text = sg.get('text', '')
            dur = sg['dur']
            ctx = infer_segment_context(seg_text, dur, silence_dur=sg.get('silence_dur', 0.0), is_major_silence=sg.get('is_silence', False))
            kws, topic, importance = extract_keywords_and_topic(seg_text)

            best_img = sorted_images[i % n_imgs]
            best_score = -1.0
            for k, candidate in enumerate(sorted_images):
                sc = score_image_affinity(candidate, k, n_imgs, seg_text, i, len(continuous_segs))
                if sc > best_score:
                    best_score = sc
                    best_img = candidate

            final_segments.append({
                'start': sg['start'], 'end': sg['end'], 'dur': dur,
                'text': seg_text, 'keywords': kws, 'topic': topic, 'importance': importance
            })
            scenes.append({
                'scene_id': f"scene_{i+1:04d}",
                'segment_index': i,
                'image': best_img,
                'image_id': f"img_{i % n_imgs + 1:03d}",
                'context': ctx,
                'transition': CONTEXT_MAP.get(ctx, CONTEXT_MAP['normal'])['label'],
                'start': sg['start'],
                'end': sg['end'],
                'dur': dur,
                'confidence': 0.75,
                'confidence_level': 'MEDIUM',
                'match_reason': ['deterministic_affinity_fallback'],
                'source': 'deterministic_fallback',
                'user_override': False,
                'narration_text': seg_text
            })

    if scenes:
        scenes[0]['start'] = 0.0
        scenes[-1]['end'] = round(master_dur, 3)
        scenes[-1]['dur'] = round(master_dur - scenes[-1]['start'], 3)
        final_segments[0]['start'] = 0.0
        final_segments[-1]['end'] = round(master_dur, 3)

    return {'segments': final_segments}, {'scenes': scenes, 'sync_report': {
        'total_images': n_imgs,
        'total_beats': len(scenes),
        'high_confidence': 0,
        'medium_confidence': len(scenes),
        'low_confidence': 0,
        'average_confidence': 0.72,
        'fallback_used': 1,
        'engine_version': 'AI Image Sync Engine v3 (Fallback Mode)'
    }}


def validate_timeline_coverage(
    transcript_obj: Dict,
    plan_obj: Dict,
    master_dur: float,
    images_dir: Optional[Path] = None,
    tolerance: float = 0.005
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Validate that visual timeline strictly covers narration audio with ZERO gaps and ZERO overlaps.
    Strict tolerance <= 0.005s per Section 1 & Section 9.
    """
    scenes = plan_obj.get('scenes', [])
    return TimelineNormalizer.validate_timeline(
        scenes=scenes,
        master_dur=master_dur,
        tolerance=tolerance,
        images_dir=images_dir
    )


def format_preview_summary(transcript_obj: Dict, plan_obj: Dict, max_preview: int = 15) -> List[Dict]:
    """
    Format timeline auto-map preview for human inspection in UI.
    Matches Master Prompt §27, §28, §42 format.
    """
    scenes = plan_obj.get('scenes', [])
    segs = transcript_obj.get('segments', [])
    seg_map = {i: s for i, s in enumerate(segs)}

    preview = []
    for sc in scenes[:max_preview]:
        seg_idx = sc.get('segment_index', 0)
        seg = seg_map.get(seg_idx, {})
        start_m, start_s = divmod(int(sc['start']), 60)
        end_m, end_s = divmod(int(sc['end']), 60)

        preview.append({
            'narration_range': f"{start_m:02d}:{start_s:02d}–{end_m:02d}:{end_s:02d}",
            'image': sc['image'],
            'transition': sc.get('transition', 'soft_dissolve').replace('_', ' ').title(),
            'duration': f"{sc['dur']:.1f} sec",
            'context': sc.get('context', 'normal'),
            'topic': seg.get('topic', 'General Narration'),
            'text': sc.get('narration_text', seg.get('text', '')),
            'confidence': sc.get('confidence', 0.85),
            'confidence_level': sc.get('confidence_level', 'HIGH'),
            'match_reason': sc.get('match_reason', ['semantic_match']),
            'source': sc.get('source', 'ai_semantic'),
            'user_override': sc.get('user_override', False),
            'candidates': sc.get('candidates', [])
        })
    return preview

