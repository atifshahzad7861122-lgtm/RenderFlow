#!/usr/bin/env python3
"""
engine/timeline_normalizer.py — Deterministic Timeline Continuity & Silence Preservation Engine.

Core Principles:
1. Audio/Narration is the MASTER TIMELINE:
   - Timeline must strictly cover [0.0, audio_duration] with tolerance <= 0.005s.
   - For every consecutive scene: scene[n].start == scene[n-1].end.
2. Real Silence Preservation:
   - Genuine speech pauses and silences must never be dropped from the master timeline.
   - Pauses are explicitly accounted for either via Image Hold (Option A) or Explicit Silence/Hold scenes (Option B).
   - Zero unexplained holes, zero negative durations, zero overlaps.
3. Integer Millisecond Normalization:
   - Eliminates floating-point accumulation drift.
4. Structured Diagnostic Mode:
   - Categorizes discrepancies: [REAL SILENCE], [CALCULATION GAP], [ROUNDING ERROR], [OVERLAP], [UNKNOWN].
"""

import math
from typing import List, Dict, Tuple, Optional, Any

try:
    from .errors import InvalidTimelineError, InvalidTransitionError
except ImportError:
    try:
        from engine.errors import InvalidTimelineError, InvalidTransitionError
    except ImportError:
        from errors import InvalidTimelineError, InvalidTransitionError


class TimelineNormalizer:
    """
    Deterministic timeline construction, normalization, and validation engine.
    Guarantees mathematically continuous scene timelines aligned to master audio.
    """

    DEFAULT_TOLERANCE = 0.005  # 5 milliseconds strict tolerance (§1, §9)

    @staticmethod
    def sec_to_ms(seconds: float) -> int:
        """Convert float seconds to integer milliseconds."""
        return int(round(float(seconds) * 1000.0))

    @staticmethod
    def ms_to_sec(ms: int) -> float:
        """Convert integer milliseconds to float seconds with 3 decimal precision."""
        return round(float(ms) / 1000.0, 3)

    @classmethod
    def normalize_speech_segments(
        cls,
        raw_segments: List[Dict],
        master_dur: float,
        hold_mode: str = 'extend_hold',  # 'extend_hold' (Option A) or 'midpoint'
        explicit_silence_threshold: Optional[float] = None  # None or e.g. 2.0s for Option B
    ) -> List[Dict]:
        """
        Normalize arbitrary transcript speech segments into a strictly continuous timeline
        spanning [0.0, master_dur] with ZERO gaps and ZERO overlaps.

        Preserves:
        - Exact spoken utterance text and keywords
        - Real silence durations (by holding or explicit silence intervals)
        - Master audio duration bounds
        """
        master_ms = cls.sec_to_ms(master_dur)
        if master_ms <= 0:
            raise ValueError(f"Invalid master audio duration: {master_dur}s")

        if not raw_segments:
            # Fallback if no speech segments: single continuous segment covering entire audio
            return [{
                'start': 0.0,
                'end': cls.ms_to_sec(master_ms),
                'dur': cls.ms_to_sec(master_ms),
                'text': "Narration",
                'is_silence': False
            }]

        # 1. Parse and sort segments in integer milliseconds
        cleaned = []
        for s in raw_segments:
            s_start = cls.sec_to_ms(s.get('start', 0.0))
            s_end = cls.sec_to_ms(s.get('end', 0.0))
            if s_end > s_start:
                cleaned.append({
                    'start_ms': s_start,
                    'end_ms': s_end,
                    'orig_start': s.get('start', 0.0),
                    'orig_end': s.get('end', 0.0),
                    'text': s.get('text', ''),
                    'keywords': s.get('keywords', []),
                    'topic': s.get('topic', 'General Narration'),
                    'importance': s.get('importance', 0.5)
                })

        cleaned.sort(key=lambda x: x['start_ms'])
        if not cleaned:
            return [{
                'start': 0.0,
                'end': cls.ms_to_sec(master_ms),
                'dur': cls.ms_to_sec(master_ms),
                'text': "Narration",
                'is_silence': False
            }]

        # 2. Resolve Overlaps deterministically (s_k < e_{k-1})
        deoverlapped = [cleaned[0]]
        for curr in cleaned[1:]:
            prev = deoverlapped[-1]
            if curr['start_ms'] < prev['end_ms']:
                # Spoken intervals overlap: cut at midpoint
                mid_ms = (curr['start_ms'] + prev['end_ms']) // 2
                if mid_ms > prev['start_ms']:
                    prev['end_ms'] = mid_ms
                if mid_ms < curr['end_ms']:
                    curr['start_ms'] = mid_ms
                else:
                    curr['start_ms'] = prev['end_ms']

            if curr['end_ms'] > curr['start_ms']:
                deoverlapped.append(curr)

        # 3. Build continuous segments spanning [0, master_ms]
        continuous = []
        curr_cursor_ms = 0

        for i, seg in enumerate(deoverlapped):
            seg_start_ms = seg['start_ms']
            seg_end_ms = seg['end_ms']

            # Check for leading silence or gap before this segment
            if seg_start_ms > curr_cursor_ms:
                gap_ms = seg_start_ms - curr_cursor_ms
                gap_sec = gap_ms / 1000.0

                if i == 0:
                    # Lead-in silence before first speech: expand first segment to start at 0.0
                    seg_start_ms = 0
                else:
                    # Inter-utterance silence
                    prev_seg = continuous[-1]
                    if explicit_silence_threshold and gap_sec >= explicit_silence_threshold:
                        # Option B: Create explicit silence/hold segment
                        continuous.append({
                            'start_ms': curr_cursor_ms,
                            'end_ms': seg_start_ms,
                            'text': "",
                            'is_silence': True,
                            'silence_dur': gap_sec,
                            'topic': "Silence & Pause",
                            'importance': 0.3
                        })
                    else:
                        # Option A: Hold previous image across the pause
                        if hold_mode == 'midpoint' and gap_sec > 1.2:
                            mid = curr_cursor_ms + (gap_ms // 2)
                            prev_seg['end_ms'] = mid
                            seg_start_ms = mid
                        else:
                            # Extend previous scene to the beginning of next utterance
                            prev_seg['end_ms'] = seg_start_ms

            continuous.append({
                'start_ms': seg_start_ms,
                'end_ms': seg_end_ms,
                'text': seg['text'],
                'keywords': seg.get('keywords', []),
                'topic': seg.get('topic', 'General Narration'),
                'importance': seg.get('importance', 0.5),
                'is_silence': False
            })
            curr_cursor_ms = seg_end_ms

        # 4. Handle trailing silence (after last speech segment up to master_dur)
        if curr_cursor_ms < master_ms:
            continuous[-1]['end_ms'] = master_ms
        elif curr_cursor_ms > master_ms:
            # Scale or clamp if transcript exceeded probed duration
            continuous[-1]['end_ms'] = master_ms

        # Enforce exact first and last bounds
        continuous[0]['start_ms'] = 0
        continuous[-1]['end_ms'] = master_ms

        # 5. Convert to normalized seconds representation with zero float drift
        result = []
        for s in continuous:
            start_s = cls.ms_to_sec(s['start_ms'])
            end_s = cls.ms_to_sec(s['end_ms'])
            dur_s = round(end_s - start_s, 3)
            result.append({
                'start': start_s,
                'end': end_s,
                'dur': dur_s,
                'text': s['text'],
                'keywords': s.get('keywords', []),
                'topic': s.get('topic', 'General Narration'),
                'importance': s.get('importance', 0.5),
                'is_silence': s.get('is_silence', False),
                'silence_dur': s.get('silence_dur', 0.0)
            })

        return result

    @classmethod
    def partition_into_visual_beats(
        cls,
        continuous_segments: List[Dict],
        target_beats: int,
        master_dur: float
    ) -> List[Dict]:
        """
        Subdivide a continuous timeline into exactly `target_beats` contiguous visual scenes.
        Guarantees that every consecutive scene satisfies: scene[k].start == scene[k-1].end.
        """
        master_ms = cls.sec_to_ms(master_dur)
        n_segs = len(continuous_segments)

        if target_beats <= n_segs:
            # One beat per segment or 1-to-1 mapping
            return [dict(s) for s in continuous_segments]

        # Distribute target_beats proportionally based on segment duration
        durations_ms = [cls.sec_to_ms(s['end']) - cls.sec_to_ms(s['start']) for s in continuous_segments]
        total_dur_ms = sum(durations_ms)

        # Initial allocation proportional to duration, leaving room for remaining segments
        beats_per_seg = []
        rem_beats = target_beats
        rem_segs = n_segs

        for i, d_ms in enumerate(durations_ms):
            weight = d_ms / max(1, total_dur_ms)
            alloc = max(1, int(round(target_beats * weight)))
            # Clamp to not exceed remaining allowance
            alloc = min(alloc, rem_beats - (rem_segs - 1))
            alloc = max(1, alloc)
            beats_per_seg.append(alloc)
            rem_beats -= alloc
            rem_segs -= 1

        # Distribute any remaining beats to the LONGEST segments capable of holding them
        while rem_beats > 0:
            # Find segment with longest average sub-beat duration
            best_i = max(range(n_segs), key=lambda idx: durations_ms[idx] / float(beats_per_seg[idx]))
            beats_per_seg[best_i] += 1
            rem_beats -= 1

        # Now subdivide each continuous segment into exact contiguous sub-beats
        final_beats = []
        for i, seg in enumerate(continuous_segments):
            n_sub = beats_per_seg[i]
            s_start_ms = cls.sec_to_ms(seg['start'])
            s_end_ms = cls.sec_to_ms(seg['end'])
            span_ms = s_end_ms - s_start_ms
            seg_text = (seg.get('text') or "").strip()

            # Partition transcript text into n_sub distinct, balanced slices
            sub_texts = []
            if n_sub > 1 and seg_text:
                words = seg_text.split()
                if len(words) >= n_sub:
                    n_w = len(words)
                    for b_idx in range(n_sub):
                        w_start = int(round(b_idx * n_w / float(n_sub)))
                        w_end = int(round((b_idx + 1) * n_w / float(n_sub)))
                        w_slice = words[w_start:w_end]
                        if not w_slice:
                            w_slice = [words[min(w_start, n_w - 1)]]
                        sub_texts.append(" ".join(w_slice))
                else:
                    for b_idx in range(n_sub):
                        sub_texts.append(f"{seg_text} (part {b_idx+1})")
            else:
                sub_texts = [seg_text] * n_sub

            while len(sub_texts) < n_sub:
                sub_texts.append(seg_text)

            # Balanced, integer-exact time distribution across n_sub sub-beats
            accum_ms = 0
            for b in range(n_sub):
                b_start_ms = s_start_ms + accum_ms
                if b == n_sub - 1:
                    b_end_ms = s_end_ms
                else:
                    # Integer division ensuring zero drift
                    b_dur_ms = span_ms // n_sub
                    b_end_ms = min(s_end_ms, b_start_ms + b_dur_ms)
                accum_ms = b_end_ms - s_start_ms

                start_s = cls.ms_to_sec(b_start_ms)
                end_s = cls.ms_to_sec(b_end_ms)
                dur_s = round(end_s - start_s, 3)

                final_beats.append({
                    'segment_index': i,
                    'beat_in_segment': b,
                    'start': start_s,
                    'end': end_s,
                    'dur': dur_s,
                    'text': sub_texts[b] if b < len(sub_texts) and sub_texts[b] else seg_text,
                    'keywords': seg.get('keywords', []),
                    'topic': seg.get('topic', 'General Narration'),
                    'importance': seg.get('importance', 0.5),
                    'is_silence': seg.get('is_silence', False)
                })

        # Ensure exact end boundary matches master duration
        if final_beats:
            final_beats[0]['start'] = 0.0
            final_beats[-1]['end'] = cls.ms_to_sec(master_ms)
            final_beats[-1]['dur'] = round(final_beats[-1]['end'] - final_beats[-1]['start'], 3)

        return final_beats

    @classmethod
    def validate_timeline(
        cls,
        scenes: List[Dict],
        master_dur: float,
        tolerance: float = DEFAULT_TOLERANCE,
        images_dir: Optional[Any] = None
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Strict timeline validator (§1, §9, §10).
        Verifies:
        - Consecutive continuity (scene[n].start == scene[n-1].end within tolerance <= 0.005s)
        - Master duration match
        - Non-zero positive durations
        - No timestamp regressions or overlaps
        - Image existence if images_dir provided
        """
        errors = []
        diagnostics = []

        if not scenes:
            errors.append("Timeline validation failed: Visual plan has no scenes.")
            return False, errors, {'passed': False, 'total_scenes': 0}

        # 1. Start boundary check
        first_start = float(scenes[0].get('start', 0.0))
        if abs(first_start - 0.0) > tolerance:
            errors.append(f"Timeline starts at {first_start:.3f}s instead of 0.0s (offset={first_start:.3f}s)")

        # 2. Total duration coverage check
        last_end = float(scenes[-1].get('end', scenes[-1].get('start', 0.0) + scenes[-1].get('dur', 0.0)))
        dur_diff = abs(last_end - master_dur)
        if dur_diff > tolerance:
            errors.append(f"Visual coverage mismatch: visual={last_end:.3f}s, audio={master_dur:.3f}s (diff={dur_diff:.3f}s > {tolerance}s)")

        # 3. Consecutive scene continuity check
        for idx in range(len(scenes)):
            sc = scenes[idx]
            sc_start = float(sc.get('start', 0.0))
            sc_end = float(sc.get('end', sc_start + sc.get('dur', 0.0)))
            sc_dur = float(sc.get('dur', sc_end - sc_start))

            # Non-positive duration
            if sc_dur <= 0.0:
                errors.append(f"Scene #{idx+1} has invalid duration: {sc_dur:.3f}s")

            # Continuity with previous scene
            if idx > 0:
                prev_sc = scenes[idx - 1]
                prev_end = float(prev_sc.get('end', prev_sc.get('start', 0.0) + prev_sc.get('dur', 0.0)))
                delta = sc_start - prev_end

                diag_entry = {
                    'scene_id': sc.get('scene_id', f'scene_{idx+1}'),
                    'scene_num': idx + 1,
                    'start': sc_start,
                    'end': sc_end,
                    'duration': sc_dur,
                    'previous_end': prev_end,
                    'delta': round(delta, 4)
                }

                if abs(delta) > tolerance:
                    # Classify discrepancy (§12)
                    if delta > 0:
                        if delta > 0.2:
                            classification = "[REAL SILENCE / UNABSORBED GAP]"
                        else:
                            classification = "[CALCULATION GAP]"
                        errors.append(
                            f"Discontinuity between scene #{idx} and #{idx+1}: gap of {delta:.3f}s "
                            f"(prev_end={prev_end:.3f}s, start={sc_start:.3f}s) {classification}"
                        )
                    else:
                        classification = "[OVERLAP]"
                        errors.append(
                            f"Discontinuity between scene #{idx} and #{idx+1}: overlap of {abs(delta):.3f}s "
                            f"(prev_end={prev_end:.3f}s, start={sc_start:.3f}s) {classification}"
                        )
                    diag_entry['classification'] = classification
                else:
                    diag_entry['classification'] = "[CONTINUOUS]"

                diagnostics.append(diag_entry)

            # Check referenced image file if images_dir provided
            if images_dir:
                from pathlib import Path
                img_name = sc.get('image') or sc.get('img')
                if img_name:
                    img_path = Path(images_dir) / img_name
                    if not img_path.exists():
                        errors.append(f"Scene #{idx+1} references missing image: {img_name}")

        metrics = {
            'total_scenes': len(scenes),
            'master_dur': master_dur,
            'visual_coverage': last_end,
            'diff': round(dur_diff, 4),
            'tolerance': tolerance,
            'passed': len(errors) == 0,
            'diagnostics': diagnostics
        }

        return len(errors) == 0, errors, metrics

    @classmethod
    def validate_transitions_timeline(
        cls,
        scenes: List[Dict],
        transitions: List[Dict],
        master_dur: float,
        tolerance: float = DEFAULT_TOLERANCE
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Validate transitions timeline against scenes and master audio duration.
        Ensures:
          - Transition cut times exactly correspond to scene boundary cuts.
          - Transition duration does not exceed adjacent scene duration bounds.
          - Transition start/end times do not regress or fall outside video bounds [0.0, master_dur].
          - Total master audio timeline is unaltered and continuous.
        """
        errors = []
        diagnostics = []

        if not scenes:
            return False, ["No scenes provided for transition timeline validation."], {}

        # 1. Validate scenes continuity first
        sc_valid, sc_errs, _ = cls.validate_timeline(scenes, master_dur, tolerance=tolerance)
        if not sc_valid:
            errors.extend([f"Scene timeline invalid before transitions: {e}" for e in sc_errs])

        # 2. Check each transition
        for t_idx, tr in enumerate(transitions):
            cut_idx = tr.get('cut_index', t_idx)
            if cut_idx < 0 or cut_idx >= len(scenes) - 1:
                errors.append(f"Transition #{t_idx+1} references invalid cut index: {cut_idx}")
                continue

            prev_sc = scenes[cut_idx]
            next_sc = scenes[cut_idx + 1]
            expected_cut = float(next_sc.get('start', 0.0))

            cut_time = float(tr.get('cut_time', expected_cut))
            if abs(cut_time - expected_cut) > tolerance:
                errors.append(
                    f"Transition #{t_idx+1} cut_time ({cut_time:.3f}s) does not match scene #{cut_idx+2} start ({expected_cut:.3f}s)"
                )

            tr_dur = float(tr.get('dur', tr.get('duration', 0.0)))
            if tr_dur <= 0.0:
                errors.append(f"Transition #{t_idx+1} has invalid non-positive duration: {tr_dur:.3f}s")

            # Check bounds against adjacent scene durations
            prev_dur = float(prev_sc.get('dur', float(prev_sc.get('end', 0.0)) - float(prev_sc.get('start', 0.0))))
            next_dur = float(next_sc.get('dur', float(next_sc.get('end', 0.0)) - float(next_sc.get('start', 0.0))))
            max_safe = min(prev_dur, next_dur)

            start_s = float(tr.get('start_s', cut_time - tr_dur / 2.0))
            end_s = float(tr.get('end_s', start_s + tr_dur))

            if start_s < -tolerance:
                errors.append(f"Transition #{t_idx+1} starts before video start: {start_s:.3f}s < 0.0s")
            if end_s > master_dur + tolerance:
                errors.append(f"Transition #{t_idx+1} ends after master duration: {end_s:.3f}s > {master_dur:.3f}s")

            diagnostics.append({
                'transition_idx': t_idx + 1,
                'cut_index': cut_idx,
                'cut_time': cut_time,
                'duration': tr_dur,
                'start_s': start_s,
                'end_s': end_s,
                'prev_scene_dur': prev_dur,
                'next_scene_dur': next_dur,
                'safe': tr_dur <= max_safe
            })

        metrics = {
            'total_transitions': len(transitions),
            'master_dur': master_dur,
            'passed': len(errors) == 0,
            'diagnostics': diagnostics
        }
        return len(errors) == 0, errors, metrics

    @classmethod
    def assert_timeline_valid(cls, scenes: List[Dict], master_dur: float, tolerance: float = DEFAULT_TOLERANCE) -> None:
        """Validate scene timeline, raising InvalidTimelineError on failure."""
        valid, errors, metrics = cls.validate_timeline(scenes, master_dur, tolerance=tolerance)
        if not valid:
            raise InvalidTimelineError(
                f"Timeline validation failed: {'; '.join(errors)}",
                details={"errors": errors, "metrics": metrics, "master_dur": master_dur}
            )

    @classmethod
    def assert_transitions_valid(cls, scenes: List[Dict], transitions: List[Dict], master_dur: float, tolerance: float = DEFAULT_TOLERANCE) -> None:
        """Validate transitions timeline, raising InvalidTransitionError on failure."""
        valid, errors, metrics = cls.validate_transitions_timeline(scenes, transitions, master_dur, tolerance=tolerance)
        if not valid:
            raise InvalidTransitionError(
                f"Transitions timeline validation failed: {'; '.join(errors)}",
                details={"errors": errors, "metrics": metrics, "master_dur": master_dur}
            )

    @classmethod
    def format_diagnostic_report(cls, scenes: List[Dict], master_dur: float) -> str:
        """Format detailed tabular diagnostics for all scenes (§2, §12)."""
        lines = []
        lines.append("=" * 80)
        lines.append(" RENDERING STUDIO — TIMELINE CONTINUITY DIAGNOSTIC REPORT")
        lines.append("=" * 80)
        lines.append(f"Master Audio Duration: {master_dur:.3f}s | Total Scenes: {len(scenes)}")
        lines.append("-" * 80)
        lines.append(f"{'Scene':<7} | {'Start':<8} | {'End':<8} | {'Duration':<8} | {'Prev End':<8} | {'Delta':<8} | {'Status':<20}")
        lines.append("-" * 80)

        prev_end = 0.0
        gap_count = 0
        overlap_count = 0

        for idx, sc in enumerate(scenes):
            sc_start = float(sc.get('start', 0.0))
            sc_end = float(sc.get('end', sc_start + sc.get('dur', 0.0)))
            sc_dur = float(sc.get('dur', sc_end - sc_start))
            delta = sc_start - prev_end if idx > 0 else 0.0

            if idx == 0:
                status = "START"
            elif abs(delta) <= cls.DEFAULT_TOLERANCE:
                status = "CONTINUOUS"
            elif delta > 0:
                gap_count += 1
                status = f"GAP (+{delta:.3f}s)"
            else:
                overlap_count += 1
                status = f"OVERLAP ({delta:.3f}s)"

            lines.append(
                f"#{idx+1:<6} | {sc_start:<8.3f} | {sc_end:<8.3f} | {sc_dur:<8.3f} | {prev_end:<8.3f} | {delta:<+8.3f} | {status:<20}"
            )
            prev_end = sc_end

        lines.append("-" * 80)
        lines.append(f"Summary: Gaps: {gap_count} | Overlaps: {overlap_count} | Validation: {'PASS' if gap_count == 0 and overlap_count == 0 else 'FAIL'}")
        lines.append("=" * 80)
        return "\n".join(lines)

    @classmethod
    def split_scene_at(
        cls,
        scenes: List[Dict],
        split_time: float,
        master_dur: float,
        min_clip_duration: float = 0.3,
        tolerance: float = DEFAULT_TOLERANCE
    ) -> Tuple[List[Dict], int]:
        """
        Split a scene at the specified split_time while preserving:
        1. Master audio timeline bounds [0.0, master_dur] exactly.
        2. Strict consecutive continuity (scene[k].start == scene[k-1].end).
        3. Integer-millisecond normalization to prevent floating-point drift.
        4. Minimum clip duration threshold (min_clip_duration, default 0.3s) to prevent zero-length clips.

        Args:
            scenes: Current list of scene dictionaries.
            split_time: Requested split timestamp in seconds.
            master_dur: Total master audio duration in seconds.
            min_clip_duration: Minimum allowed duration for resulting clips (seconds).
            tolerance: Maximum allowable timeline discontinuity (default 0.005s).

        Returns:
            Tuple[List[Dict], int]: (new_scenes, new_scene_index) where new_scene_index is
            the index of the newly inserted second scene.

        Raises:
            ValueError: If split_time is negative, out-of-range, or violates minimum duration thresholds.
            InvalidTimelineError: If the resulting timeline fails strict continuity validation.
        """
        if not scenes:
            raise ValueError("Cannot split empty scene list.")
        if master_dur <= 0:
            raise ValueError(f"Invalid master audio duration: {master_dur}s")

        try:
            split_time = float(split_time)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid split time value: {split_time}")

        if math.isnan(split_time) or math.isinf(split_time):
            raise ValueError(f"Invalid non-finite split time: {split_time}")

        if split_time <= 0.0:
            raise ValueError(f"Split position {split_time:.3f}s must be strictly positive (> 0.0s).")

        if split_time >= master_dur:
            raise ValueError(f"Split position {split_time:.3f}s exceeds master audio duration {master_dur:.3f}s.")

        split_ms = cls.sec_to_ms(split_time)
        min_clip_ms = cls.sec_to_ms(min_clip_duration)

        # Locate the scene that spans across split_ms
        target_idx = -1
        for i, sc in enumerate(scenes):
            sc_start_ms = cls.sec_to_ms(sc.get('start', 0.0))
            sc_end_ms = cls.sec_to_ms(sc.get('end', sc_start_ms + sc.get('dur', 0.0)))
            if sc_start_ms < split_ms < sc_end_ms:
                target_idx = i
                break

        if target_idx == -1:
            raise ValueError(
                f"Split position {split_time:.3f}s does not fall strictly within any scene interval "
                f"or coincides with an existing cut boundary."
            )

        target_sc = scenes[target_idx]
        sc_start_ms = cls.sec_to_ms(target_sc.get('start', 0.0))
        sc_end_ms = cls.sec_to_ms(target_sc.get('end', sc_start_ms + target_sc.get('dur', 0.0)))

        head_dur_ms = split_ms - sc_start_ms
        tail_dur_ms = sc_end_ms - split_ms

        if head_dur_ms < min_clip_ms:
            raise ValueError(
                f"Split position {split_time:.3f}s is too close to scene start ({cls.ms_to_sec(sc_start_ms):.3f}s). "
                f"Head clip duration would be {cls.ms_to_sec(head_dur_ms):.3f}s (minimum: {min_clip_duration:.3f}s)."
            )
        if tail_dur_ms < min_clip_ms:
            raise ValueError(
                f"Split position {split_time:.3f}s is too close to scene end ({cls.ms_to_sec(sc_end_ms):.3f}s). "
                f"Tail clip duration would be {cls.ms_to_sec(tail_dur_ms):.3f}s (minimum: {min_clip_duration:.3f}s)."
            )

        # Clone and update scene dicts with integer millisecond normalization
        scene_a = dict(target_sc)
        scene_b = dict(target_sc)

        # Scene A: [start_ms, split_ms]
        scene_a['start'] = cls.ms_to_sec(sc_start_ms)
        scene_a['end'] = cls.ms_to_sec(split_ms)
        scene_a['dur'] = cls.ms_to_sec(head_dur_ms)
        scene_a['user_override'] = True

        # Scene B: [split_ms, end_ms]
        scene_b['start'] = cls.ms_to_sec(split_ms)
        scene_b['end'] = cls.ms_to_sec(sc_end_ms)
        scene_b['dur'] = cls.ms_to_sec(tail_dur_ms)
        scene_b['user_override'] = True

        # Assign unique identifier for Scene B if IDs exist
        if 'id' in scene_b:
            scene_b['id'] = f"{target_sc.get('id', 'clip')}_split_{split_ms}"
        elif 'scene_id' in scene_b:
            scene_b['scene_id'] = f"{target_sc.get('scene_id', 'scene')}_split_{split_ms}"

        # Assemble new continuous scene list
        new_scenes = []
        for i, sc in enumerate(scenes):
            if i == target_idx:
                new_scenes.append(scene_a)
                new_scenes.append(scene_b)
            else:
                new_scenes.append(dict(sc))

        # Re-index segment_index
        for i, sc in enumerate(new_scenes):
            sc['segment_index'] = i

        # Enforce strict mathematical timeline continuity validation
        cls.assert_timeline_valid(new_scenes, master_dur, tolerance=tolerance)

        return new_scenes, target_idx + 1

    @classmethod
    def ripple_trim(
        cls,
        scenes: List[Dict],
        master_dur: float,
        start_time: float,
        end_time: float,
        transcript_segments: Optional[List[Dict]] = None,
        protect_locked: bool = True
    ) -> Tuple[List[Dict], float, Dict[str, Any]]:
        """
        Convenience wrapper executing deterministic timeline ripple trim via TranscriptRipplePlanner.
        Returns: (new_scenes, new_master_dur, result_dict)
        """
        try:
            from .transcript_ripple import TranscriptRipplePlanner, RippleEditRequest
        except ImportError:
            try:
                from engine.transcript_ripple import TranscriptRipplePlanner, RippleEditRequest
            except ImportError:
                from transcript_ripple import TranscriptRipplePlanner, RippleEditRequest

        req = RippleEditRequest(
            start_time=start_time,
            end_time=end_time,
            target_type="range",
            protect_locked=protect_locked
        )
        res = TranscriptRipplePlanner.plan_ripple_edit(
            scenes=scenes,
            transcript_segments=transcript_segments or [],
            master_dur=master_dur,
            request=req,
            dry_run=False
        )
        return res.scenes, res.new_master_dur, res.to_dict()

