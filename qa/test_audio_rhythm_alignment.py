#!/usr/bin/env python3
"""
qa/test_audio_rhythm_alignment.py — Phase 2 Audio Rhythm & Cadence Alignment Validation Suite.
Rendering Studio Engine v2 (Phase 2 Clean-Room Implementation)

Test Coverage:
1. Synthetic silence, constant tone, and speech-like energy envelopes.
2. Natural speech pause detection and false-positive handling.
3. Music beat candidate & BPM detection when music is supplied.
4. Speech-only input without fabricated musical BPM or downbeats.
5. Noisy, empty, zero-byte, and very short audio fallbacks.
6. Cut snapping within configurable tolerance (default ±180ms).
7. Protected spoken-word spans (zero cuts inside active words).
8. User-locked scene preservation (manual overrides untouched).
9. Pacing bias bounds (0.5x to 2.0x) and 100% deterministic output.
10. Zero master audio duration drift and timeline continuity.
11. Regression tests for Phase 1 cinematographic shot roles, easing curves, and legacy L4 motion strings.
12. Integration with AIImageSyncEngineV3 and SyncQualityReport.
"""

import os
import sys
import tempfile
import unittest
import numpy as np
from pathlib import Path

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from engine.audio_rhythm import (
    AudioRhythmEngine,
    CadenceBoundaryPlanner,
    PauseCandidate,
    BeatCandidate,
    MusicRhythmProfile,
    AudioRhythmProfile,
    BoundaryAdjustment,
    align_semantic_beats_cadence
)
from engine.motion_intelligence import (
    MotionIntelligenceEngine,
    apply_easing,
    VALID_SHOT_ROLES,
    VALID_EASING_CURVES
)
from engine.sync_engine_v3 import (
    AIImageSyncEngineV3,
    SyncConfig,
    SyncQualityReport,
    SemanticBeat,
    VisualRequirement
)


class TestAudioRhythmEngineDSP(unittest.TestCase):
    """DSP unit tests for energy computation, speech pauses, and music beats."""

    def setUp(self):
        self.sr = 16000

    def test_synthetic_silence_detection(self):
        """Synthetic pure silence should yield is_silent=True and zero pauses."""
        silence_samples = np.zeros(self.sr * 2, dtype=np.float32)  # 2.0s of silence
        times, rms, db, onset = AudioRhythmEngine.compute_short_time_energy(silence_samples, self.sr)
        self.assertTrue(np.all(rms < 1e-5))
        self.assertTrue(np.all(db <= -99.0))

        pauses, sp_level, floor_level, dyn_range = AudioRhythmEngine.detect_speech_pauses(times, db)
        self.assertEqual(len(pauses), 0, "Pure silence must not yield false speech pauses")
        self.assertLess(sp_level, -60.0, "Speech level in pure silence must be below -60 dB")

    def test_synthetic_flat_noise_rejection(self):
        """Synthetic uniform flat noise has low dynamic range and must not fabricate speech pauses."""
        rng = np.random.RandomState(42)
        flat_noise = rng.uniform(-0.1, 0.1, self.sr * 2).astype(np.float32)
        times, rms, db, onset = AudioRhythmEngine.compute_short_time_energy(flat_noise, self.sr)

        pauses, sp_level, floor_level, dyn_range = AudioRhythmEngine.detect_speech_pauses(times, db)
        self.assertLess(dyn_range, 8.0, "Uniform noise dynamic range should be small (< 8 dB)")
        self.assertEqual(len(pauses), 0, "Flat noise should produce 0 speech pause candidates")

    def test_synthetic_speech_like_envelope_and_pauses(self):
        """
        Synthetic speech-like signal:
        0.0s - 1.0s: Speech phrase 1 (voiced burst, high energy)
        1.0s - 1.4s: Silence pause (400ms valley)
        1.4s - 2.5s: Speech phrase 2 (voiced burst, high energy)
        """
        dur = 2.5
        t = np.linspace(0, dur, int(self.sr * dur), endpoint=False)
        signal = np.zeros_like(t)

        # Word 1: 0.0s to 1.0s
        w1_mask = (t >= 0.0) & (t < 1.0)
        signal[w1_mask] = 0.5 * np.sin(2 * np.pi * 300 * t[w1_mask])

        # Word 2: 1.4s to 2.5s
        w2_mask = (t >= 1.4) & (t < 2.5)
        signal[w2_mask] = 0.6 * np.sin(2 * np.pi * 350 * t[w2_mask])

        times, rms, db, onset = AudioRhythmEngine.compute_short_time_energy(signal, self.sr)
        pauses, sp_level, floor_level, dyn_range = AudioRhythmEngine.detect_speech_pauses(times, db)

        self.assertGreater(dyn_range, 25.0, "Speech-like signal must have dynamic range > 25 dB")
        self.assertGreaterEqual(len(pauses), 1, "Must detect speech pause between 1.0s and 1.4s")

        # Check pause position
        detected_pause = pauses[0]
        self.assertAlmostEqual(detected_pause.center, 1.20, delta=0.08)
        self.assertGreaterEqual(detected_pause.duration, 0.30)
        self.assertGreater(detected_pause.confidence, 0.70)
        self.assertLess(detected_pause.min_db, -60.0)

    def test_speech_only_input_without_fabricated_bpm(self):
        """Narration speech audio must return bpm=None and beats=[] when is_music=False."""
        dur = 3.0
        t = np.linspace(0, dur, int(self.sr * dur), endpoint=False)
        speech_synth = np.sin(2 * np.pi * 200 * t) * (np.sin(2 * np.pi * 2.3 * t) ** 2)

        times, rms, db, onset = AudioRhythmEngine.compute_short_time_energy(speech_synth, self.sr)
        prof = AudioRhythmEngine.detect_music_beats(speech_synth, self.sr, onset, times, is_music=False)

        self.assertFalse(prof.is_music)
        self.assertIsNone(prof.bpm, "Speech-only narration must NEVER fabricate a musical BPM")
        self.assertEqual(len(prof.beats), 0)
        self.assertEqual(len(prof.downbeats), 0)

    def test_synthetic_music_beat_and_tempo_estimation(self):
        """Synthetic 120 BPM drum click track must accurately estimate 120 BPM and detect downbeats."""
        dur = 6.0
        bpm_target = 120.0
        beat_interval = 60.0 / bpm_target  # 0.5s per beat
        t = np.linspace(0, dur, int(self.sr * dur), endpoint=False)
        music_audio = np.zeros_like(t)

        # Pulse every 0.5s, with 4/4 meter downbeat on every 4th beat
        for i, beat_t in enumerate(np.arange(0.2, dur - 0.2, beat_interval)):
            idx = int(beat_t * self.sr)
            b_len = int(0.04 * self.sr)
            amp = 0.9 if (i % 4 == 0) else 0.5
            if idx + b_len < len(music_audio):
                music_audio[idx:idx + b_len] = amp * np.sin(2 * np.pi * 440 * np.linspace(0, 0.04, b_len))

        times, rms, db, onset = AudioRhythmEngine.compute_short_time_energy(music_audio, self.sr)
        prof = AudioRhythmEngine.detect_music_beats(music_audio, self.sr, onset, times, is_music=True)

        self.assertTrue(prof.is_music)
        self.assertIsNotNone(prof.bpm)
        self.assertAlmostEqual(prof.bpm, 120.0, delta=3.0, msg="BPM should match 120 target within ±3 BPM")
        self.assertGreater(len(prof.beats), 8)
        self.assertGreater(len(prof.downbeats), 1)

    def test_short_and_empty_audio_resilience(self):
        """Audio files shorter than 250ms or empty arrays must not crash and return fallback profile."""
        empty_samples = np.zeros(0, dtype=np.float32)
        times, rms, db, onset = AudioRhythmEngine.compute_short_time_energy(empty_samples, self.sr)
        self.assertEqual(len(times), 1)
        self.assertEqual(rms[0], 0.0)

        short_samples = np.ones(100, dtype=np.float32) * 0.1  # ~6.25ms
        times, rms, db, onset = AudioRhythmEngine.compute_short_time_energy(short_samples, self.sr)
        self.assertEqual(len(times), 1)


class TestCadenceBoundaryPlanner(unittest.TestCase):
    """Unit tests for scene boundary alignment, word protection, and constraints."""

    def setUp(self):
        self.planner = CadenceBoundaryPlanner(tolerance_sec=0.180, pacing_bias=1.0)

    def test_cut_snapping_within_configured_tolerance(self):
        """A cut placed near a natural speech pause must snap into the pause center/valley."""
        # Speech pause centered at 2.60s (span 2.50s to 2.70s)
        pause = PauseCandidate(
            start=2.50, end=2.70, center=2.60, min_energy_time=2.62,
            duration=0.20, min_db=-70.0, confidence=0.95
        )
        orig_cut = 2.55  # 50ms before center, well within ±180ms
        adj = self.planner.align_single_boundary(
            cut_index=1,
            original_cut=orig_cut,
            prev_boundary=0.0,
            next_boundary=5.0,
            pauses=[pause]
        )

        self.assertEqual(adj.adjustment_type, "speech_pause")
        self.assertIn(adj.aligned_time, [2.60, 2.62])
        self.assertAlmostEqual(abs(adj.delta_ms), 50.0, delta=25.0)
        self.assertLessEqual(abs(adj.aligned_time - orig_cut), 0.180)

    def test_cut_outside_tolerance_remains_unadjusted(self):
        """A pause outside the configured tolerance window (e.g. > 250ms away) must not be snapped to."""
        pause = PauseCandidate(
            start=3.00, end=3.20, center=3.10, min_energy_time=3.12,
            duration=0.20, min_db=-70.0, confidence=0.95
        )
        orig_cut = 2.50  # 600ms away, outside ±180ms window
        adj = self.planner.align_single_boundary(
            cut_index=1,
            original_cut=orig_cut,
            prev_boundary=0.0,
            next_boundary=5.0,
            pauses=[pause]
        )

        self.assertEqual(adj.adjustment_type, "none")
        self.assertEqual(adj.aligned_time, orig_cut)
        self.assertEqual(adj.delta_ms, 0.0)
        self.assertIn("retained_original", adj.reason)

    def test_protected_spoken_word_spans_prevention(self):
        """A cut candidate falling inside an active spoken word must be strictly rejected."""
        # Speech pause at 2.60s, but words active from 2.52s to 2.68s
        pause = PauseCandidate(
            start=2.50, end=2.70, center=2.60, min_energy_time=2.60,
            duration=0.20, min_db=-70.0, confidence=0.95
        )
        word_spans = [(2.0, 2.45), (2.52, 2.68), (2.75, 3.2)]  # 2.60s is inside word (2.52 -> 2.68)
        orig_cut = 2.50

        adj = self.planner.align_single_boundary(
            cut_index=1,
            original_cut=orig_cut,
            prev_boundary=0.0,
            next_boundary=5.0,
            pauses=[pause],
            word_spans=word_spans
        )

        self.assertNotEqual(adj.aligned_time, 2.60, "Must NOT place cut inside protected word span")
        self.assertEqual(adj.adjustment_type, "none")
        self.assertEqual(adj.aligned_time, orig_cut)

    def test_user_locked_scene_preservation(self):
        """User-locked scene boundary must remain 100% untouched regardless of pauses."""
        pause = PauseCandidate(
            start=2.50, end=2.70, center=2.60, min_energy_time=2.60,
            duration=0.20, min_db=-75.0, confidence=1.0
        )
        orig_cut = 2.58
        adj = self.planner.align_single_boundary(
            cut_index=1,
            original_cut=orig_cut,
            prev_boundary=0.0,
            next_boundary=5.0,
            pauses=[pause],
            is_user_locked=True
        )

        self.assertEqual(adj.aligned_time, orig_cut)
        self.assertEqual(adj.delta_ms, 0.0)
        self.assertEqual(adj.reason, "user_locked_boundary")
        self.assertEqual(adj.confidence, 1.0)

    def test_pacing_bias_bounds_and_determinism(self):
        """Pacing bias parameter behaves within [0.5, 2.0] and produces deterministic outputs."""
        p_slow = CadenceBoundaryPlanner(pacing_bias=0.5)
        p_fast = CadenceBoundaryPlanner(pacing_bias=2.0)
        p_clamp_low = CadenceBoundaryPlanner(pacing_bias=0.1)
        p_clamp_high = CadenceBoundaryPlanner(pacing_bias=10.0)

        self.assertEqual(p_slow.pacing_bias, 0.5)
        self.assertEqual(p_fast.pacing_bias, 2.0)
        self.assertEqual(p_clamp_low.pacing_bias, 0.5)
        self.assertEqual(p_clamp_high.pacing_bias, 2.0)

        # Determinism check
        pause = PauseCandidate(start=2.48, end=2.72, center=2.60, min_energy_time=2.69, duration=0.24, min_db=-74.0, confidence=0.9)
        res1 = p_slow.align_single_boundary(1, 2.58, 0.0, 5.0, [pause])
        res2 = p_slow.align_single_boundary(1, 2.58, 0.0, 5.0, [pause])
        self.assertEqual(res1.aligned_time, res2.aligned_time)
        self.assertEqual(res1.delta_ms, res2.delta_ms)
        self.assertEqual(res1.reason, res2.reason)

    def test_zero_master_audio_drift_and_timeline_continuity(self):
        """Batch timeline boundary alignment must maintain exact continuity and zero audio drift."""
        master_dur = 20.000
        initial_cuts = [3.000, 6.500, 10.000, 14.200, 17.500]
        pauses = [
            PauseCandidate(start=2.90, end=3.15, center=3.02, min_energy_time=3.05, duration=0.25, min_db=-65.0, confidence=0.9),
            PauseCandidate(start=6.40, end=6.65, center=6.52, min_energy_time=6.53, duration=0.25, min_db=-70.0, confidence=0.9),
            PauseCandidate(start=9.85, end=10.15, center=10.00, min_energy_time=9.98, duration=0.30, min_db=-68.0, confidence=0.9),
            PauseCandidate(start=14.10, end=14.35, center=14.22, min_energy_time=14.25, duration=0.25, min_db=-72.0, confidence=0.9),
            PauseCandidate(start=17.40, end=17.65, center=17.52, min_energy_time=17.50, duration=0.25, min_db=-75.0, confidence=0.9),
        ]
        dummy_profile = AudioRhythmProfile(duration=master_dur, sample_rate=16000, speech_pauses=pauses)

        aligned_cuts, adjs = self.planner.align_timeline_boundaries(
            scene_boundaries=initial_cuts,
            master_dur=master_dur,
            audio_profile=dummy_profile
        )

        self.assertEqual(len(aligned_cuts), len(initial_cuts))

        # Check strict monotonicity
        prev = 0.0
        dur_sum = 0.0
        for i, c in enumerate(aligned_cuts):
            self.assertGreater(c, prev, f"Cut {i} ({c}) must be greater than previous ({prev})")
            dur = c - prev
            dur_sum += dur
            prev = c
        # Last segment to master_dur
        dur_sum += (master_dur - prev)

        self.assertAlmostEqual(dur_sum, master_dur, places=3, msg="Total sum of scene durations must equal master duration")


class TestRealAudioCadenceIntegration(unittest.TestCase):
    """Integration tests on real project audio (projects/king/narration.wav)."""

    def setUp(self):
        self.audio_path = WORKSPACE_ROOT / "projects" / "king" / "narration.wav"
        self.transcript_path = WORKSPACE_ROOT / "projects" / "king" / "transcript.json"

    def test_real_narration_audio_profile(self):
        """Real narration audio analysis produces genuine pause candidates without crashes."""
        if not self.audio_path.exists():
            self.skipTest(f"Audio file {self.audio_path} not found")

        prof = AudioRhythmEngine.analyze_audio(self.audio_path, is_music=False)
        self.assertAlmostEqual(prof.duration, 214.666, places=1)
        self.assertFalse(prof.is_silent)
        self.assertFalse(prof.is_flat_noise)
        self.assertGreater(prof.dynamic_range_db, 30.0)
        self.assertGreater(len(prof.speech_pauses), 50)
        self.assertIsNone(prof.music_profile)  # narration only

    def test_real_semantic_beats_cadence_alignment(self):
        """Aligning mock semantic beats against real audio adjusts cuts to natural pauses."""
        if not self.audio_path.exists():
            self.skipTest("Real audio not found")

        # 4 beats covering first 12 seconds
        beats = [
            SemanticBeat(beat_id="b1", segment_index=0, start=0.0, end=2.58, dur=2.58, text="Berlin 1953, a city divided", visual_req=VisualRequirement()),
            SemanticBeat(beat_id="b2", segment_index=1, start=2.58, end=5.16, dur=2.58, text="by barbed wire, ideology and", visual_req=VisualRequirement()),
            SemanticBeat(beat_id="b3", segment_index=2, start=5.16, end=7.74, dur=2.58, text="fear. On one side,", visual_req=VisualRequirement()),
            SemanticBeat(beat_id="b4", segment_index=3, start=7.74, end=10.32, dur=2.58, text="American soldiers drove through streets,", visual_req=VisualRequirement())
        ]
        master_dur = 10.32

        aligned_beats, adjs, prof = align_semantic_beats_cadence(
            semantic_beats=beats,
            master_dur=master_dur,
            narration_audio_path=self.audio_path,
            tolerance_sec=0.180,
            pacing_bias=1.0
        )

        self.assertEqual(len(aligned_beats), 4)
        self.assertEqual(aligned_beats[0].start, 0.0)
        self.assertEqual(aligned_beats[-1].end, 10.32)

        # Cut 1: boundary around 2.58s should snap into the verified silence valley at ~2.595s
        self.assertAlmostEqual(aligned_beats[0].end, 2.595, delta=0.05)
        self.assertEqual(aligned_beats[0].end, aligned_beats[1].start, "Timeline must be mathematically continuous")

    def test_music_beat_inside_speech_pause_blending(self):
        """When a strong music beat falls inside a speech pause, the cut snaps to the music beat within the pause."""
        planner = CadenceBoundaryPlanner(tolerance_sec=0.180, pacing_bias=1.0)
        pause = PauseCandidate(start=2.45, end=2.75, center=2.60, min_energy_time=2.60, duration=0.30, min_db=-70.0, confidence=0.95)
        # Music beat at 2.65s (which is inside the pause [2.45, 2.75])
        beat = BeatCandidate(time=2.65, strength=0.90, is_downbeat=True, confidence=0.88)

        adj = planner.align_single_boundary(
            cut_index=1,
            original_cut=2.58,
            prev_boundary=0.0,
            next_boundary=5.0,
            pauses=[pause],
            beats=[beat]
        )

        self.assertEqual(adj.adjustment_type, "speech_pause_and_music_beat")
        self.assertEqual(adj.aligned_time, 2.65)
        self.assertAlmostEqual(adj.delta_ms, 70.0, delta=1.0)
        self.assertIn("snapped_to_music_beat_inside_speech_pause", adj.reason)

    def test_full_v3_synchronize_timeline_cadence_trace(self):
        """AIImageSyncEngineV3.synchronize_timeline must emit cadence_alignment metadata and metrics."""
        img_dir = WORKSPACE_ROOT / "scratch" / "eval_dataset" / "images"
        if not (self.audio_path.exists() and img_dir.exists()):
            self.skipTest("Required fixtures not present")

        image_files = [p.name for p in sorted(img_dir.glob("*.png"))[:6]]
        v3_engine = AIImageSyncEngineV3(config=SyncConfig(enable_cadence_alignment=True, cadence_tolerance_sec=0.180))

        tr, plan, report = v3_engine.synchronize_timeline(
            audio_path=self.audio_path,
            images_dir=img_dir,
            image_filenames=image_files,
            transcript_path=self.transcript_path,
            all_images_mode=True,
            project_dir=WORKSPACE_ROOT / "projects" / "king"
        )

        scenes = plan.get("scenes", [])
        self.assertGreater(len(scenes), 0)
        self.assertEqual(scenes[0]["start"], 0.0)
        self.assertEqual(scenes[-1]["end"], round(report.duration_sec, 3) if False else round(prof_dur := v3_engine.probe_audio_duration(self.audio_path), 3))

        # Check cadence metadata exists on scenes
        for i, sc in enumerate(scenes):
            self.assertIn("cadence_alignment", sc, f"Scene {i} missing cadence_alignment trace")
            if i > 0:
                self.assertEqual(sc["start"], scenes[i - 1]["end"], "Continuity must hold: scene[i].start == scene[i-1].end")

        # Check quality report metrics
        self.assertGreaterEqual(report.cadence_aligned_cuts, 1)
        self.assertGreaterEqual(report.cadence_speech_pauses_count, 1)
        self.assertLessEqual(report.cadence_adjustments_avg_ms, 180.0)


class TestPhase1MotionRegression(unittest.TestCase):
    """Preserve Phase 1 cinematography motion roles, easing functions, and L4 strings."""

    def test_shot_roles_and_easing_curves_validity(self):
        """All Phase 1 shot roles and easing curves must evaluate without regression."""
        for role in VALID_SHOT_ROLES:
            plan = MotionIntelligenceEngine.plan_scene_motion(
                scene_idx=0,
                dur=4.0,
                context="turning_point" if role == "dramatic_tension" else "normal"
            )
            self.assertIn(plan.shot_role, VALID_SHOT_ROLES)
            self.assertIn(plan.easing, VALID_EASING_CURVES)
            self.assertTrue(plan.renderer_motion_label.startswith("L4/"), "Must preserve L4/ prefix for renderer")

        # Test easing curve mathematics
        for curve in VALID_EASING_CURVES:
            v_start = apply_easing(0.0, curve)
            v_mid = apply_easing(0.5, curve)
            v_end = apply_easing(1.0, curve)
            self.assertAlmostEqual(v_start, 0.0, places=5)
            self.assertAlmostEqual(v_end, 1.0, places=5)
            self.assertTrue(0.0 <= v_mid <= 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
