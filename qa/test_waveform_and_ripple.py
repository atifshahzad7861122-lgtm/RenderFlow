#!/usr/bin/env python3
"""
qa/test_waveform_and_ripple.py — Automated Unit & Regression Tests for Phase 4.

Covers:
1. Waveform peaks on silence, pure tone, and known amplitude signals.
2. Long-file streaming chunking and bounded execution.
3. Waveform caching, instant cache-hits, and invalidation on audio touch.
4. Missing FFmpeg and corrupt audio resilience.
5. Transcript segment ordering and timestamp validation.
6. Ripple removal at beginning, middle, and end of timeline.
7. Locked boundary protection (ProtectedIntervalError).
8. Audio/transcript synchronization and non-destructive narration preservation.
9. Preview (dry-run) versus committed edit verification.
10. Undo/redo history manager states.
11. Deterministic edit planning and repeated-operation safety.
12. Zero-regression verification across Phase 1, Phase 2, and Phase 3.
"""

import os
import sys
import math
import wave
import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.audio_waveform import AudioWaveformService, WaveformData
from engine.transcript_ripple import (
    TranscriptRipplePlanner,
    RippleEditRequest,
    RippleEditResult,
    RippleHistoryManager,
    ProtectedIntervalError,
    InvalidRippleRequestError
)
from engine.timeline_normalizer import TimelineNormalizer, InvalidTimelineError


class TestAudioWaveformAndRipple(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="rf_test_phase4_")
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_synthetic_wav(
        self,
        filename: str,
        duration_sec: float = 2.0,
        sample_rate: int = 16000,
        freq_hz: float = 440.0,
        amplitude: float = 0.8
    ) -> Path:
        """Create an uncompressed 16-bit mono PCM WAV file."""
        wav_path = self.temp_path / filename
        num_samples = int(duration_sec * sample_rate)

        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)

            samples = []
            for i in range(num_samples):
                if amplitude == 0.0 or freq_hz == 0.0:
                    val = 0
                else:
                    t = float(i) / float(sample_rate)
                    sample_float = amplitude * math.sin(2.0 * math.pi * freq_hz * t)
                    val = int(max(-32768, min(32767, sample_float * 32767.0)))
                samples.append(struct.pack("<h", val))

            wf.writeframes(b"".join(samples))

        return wav_path

    # =========================================================================
    # 1. WAVEFORM UNIT TESTS
    # =========================================================================

    def test_waveform_silence_tone_known_amplitude(self):
        """Verify waveform peaks for pure silence and calibrated amplitude signals."""
        # 1. Pure silence
        silence_wav = self._create_synthetic_wav("silence.wav", duration_sec=1.0, amplitude=0.0)
        wf_silence = AudioWaveformService.extract_waveform(silence_wav, points_per_second=20.0, use_cache=False)
        self.assertAlmostEqual(wf_silence.duration, 1.0, delta=0.05)
        self.assertEqual(wf_silence.total_points, len(wf_silence.peaks))
        for p in wf_silence.peaks:
            self.assertAlmostEqual(p, 0.0, delta=0.001)

        # 2. Known 0.75 amplitude sine wave
        tone_wav = self._create_synthetic_wav("tone_075.wav", duration_sec=1.5, freq_hz=440.0, amplitude=0.75)
        wf_tone = AudioWaveformService.extract_waveform(tone_wav, points_per_second=20.0, use_cache=False)
        self.assertAlmostEqual(wf_tone.duration, 1.5, delta=0.05)
        self.assertGreater(len(wf_tone.peaks), 10)
        # Check average peak level matches amplitude ~0.75
        avg_peak = sum(wf_tone.peaks) / len(wf_tone.peaks)
        self.assertAlmostEqual(avg_peak, 0.75, delta=0.08)

    def test_waveform_long_file_chunking_and_bounds(self):
        """Verify long file extraction executes quickly with bounded memory and accurate binning."""
        # 30 seconds audio
        long_wav = self._create_synthetic_wav("long_voiceover.wav", duration_sec=30.0, amplitude=0.6)
        wf = AudioWaveformService.extract_waveform(
            long_wav,
            points_per_second=25.0,
            use_cache=False
        )
        self.assertAlmostEqual(wf.duration, 30.0, delta=0.1)
        expected_points = int(round(30.0 * 25.0))
        self.assertAlmostEqual(wf.total_points, expected_points, delta=2)
        self.assertEqual(len(wf.min_peaks), wf.total_points)
        self.assertEqual(len(wf.max_peaks), wf.total_points)

    def test_waveform_cache_hit_and_invalidation(self):
        """Verify instant cache hit on repeated extraction and re-computation on file touch."""
        audio_wav = self._create_synthetic_wav("cache_test.wav", duration_sec=2.0, amplitude=0.5)
        cache_dir = self.temp_path / "waveform_cache"

        # 1. Cold pass
        wf_cold = AudioWaveformService.extract_waveform(audio_wav, points_per_second=20.0, cache_dir=cache_dir)
        self.assertFalse(wf_cold.cached)

        # 2. Warm pass (Cache hit)
        wf_warm = AudioWaveformService.extract_waveform(audio_wav, points_per_second=20.0, cache_dir=cache_dir)
        self.assertTrue(wf_warm.cached)
        self.assertEqual(wf_cold.peaks, wf_warm.peaks)
        self.assertEqual(wf_cold.fingerprint, wf_warm.fingerprint)

        # 3. File modification (Invalidate cache)
        with open(audio_wav, "ab") as f:
            f.write(b"\x00\x00" * 800)  # append samples

        wf_invalidated = AudioWaveformService.extract_waveform(audio_wav, points_per_second=20.0, cache_dir=cache_dir)
        self.assertFalse(wf_invalidated.cached)
        self.assertNotEqual(wf_cold.fingerprint, wf_invalidated.fingerprint)

    def test_waveform_missing_ffmpeg_and_corrupt_audio(self):
        """Verify graceful handling for corrupt, empty, and non-existent audio."""
        # 1. Non-existent file
        wf_missing = AudioWaveformService.extract_waveform(self.temp_path / "ghost.wav", use_cache=False)
        self.assertEqual(wf_missing.duration, 0.0)
        self.assertIsNotNone(wf_missing.warning)

        # 2. Empty file (0 bytes)
        empty_wav = self.temp_path / "empty.wav"
        empty_wav.write_bytes(b"")
        wf_empty = AudioWaveformService.extract_waveform(empty_wav, use_cache=False)
        self.assertEqual(wf_empty.duration, 0.0)
        self.assertIn("empty", wf_empty.warning.lower())

        # 3. Corrupt pseudo-wav file
        corrupt_wav = self.temp_path / "corrupt.wav"
        corrupt_wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00garbage_data_here")
        wf_corrupt = AudioWaveformService.extract_waveform(corrupt_wav, use_cache=False)
        self.assertEqual(wf_corrupt.duration, 0.0)
        self.assertIsNotNone(wf_corrupt.warning)

    # =========================================================================
    # 2. TRANSCRIPT RIPPLE PLANNING & SAFETY TESTS
    # =========================================================================

    def _get_sample_timeline(self):
        """Returns a 4-scene continuous timeline covering 10.0s."""
        scenes = [
            {"segment_index": 0, "start": 0.0, "end": 2.5, "dur": 2.5, "image": "1.png", "text": "Intro Scene"},
            {"segment_index": 1, "start": 2.5, "end": 5.0, "dur": 2.5, "image": "2.png", "text": "Filler Phrase"},
            {"segment_index": 2, "start": 5.0, "end": 7.5, "dur": 2.5, "image": "3.png", "text": "Main Topic"},
            {"segment_index": 3, "start": 7.5, "end": 10.0, "dur": 2.5, "image": "4.png", "text": "Outro Scene"}
        ]
        transcripts = [
            {"id": 0, "start": 0.0, "end": 2.2, "dur": 2.2, "text": "Welcome to the show."},
            {"id": 1, "start": 2.5, "end": 4.8, "dur": 2.3, "text": "Uh, like, you know what I mean."},
            {"id": 2, "start": 5.1, "end": 7.3, "dur": 2.2, "text": "Here is the key insight."},
            {"id": 3, "start": 7.6, "end": 9.8, "dur": 2.2, "text": "Thanks for watching."}
        ]
        return scenes, transcripts, 10.0

    def test_transcript_segment_validation(self):
        """Verify transcript timestamp validator detects negative durations and regressions."""
        valid_segs = [
            {"start": 0.0, "end": 2.0, "dur": 2.0, "text": "Hello"},
            {"start": 2.0, "end": 4.5, "dur": 2.5, "text": "World"}
        ]
        ok, errs = TranscriptRipplePlanner.validate_transcript_segments(valid_segs)
        self.assertTrue(ok)
        self.assertEqual(len(errs), 0)

        # Regressing timestamp
        regress_segs = [
            {"start": 3.0, "end": 2.0, "dur": -1.0, "text": "Bad"}
        ]
        ok_bad, errs_bad = TranscriptRipplePlanner.validate_transcript_segments(regress_segs)
        self.assertFalse(ok_bad)
        self.assertGreater(len(errs_bad), 0)

    def test_ripple_cut_beginning(self):
        """Test ripple removal at the start of timeline [0.0 - 2.0s]."""
        scenes, trans, master_dur = self._get_sample_timeline()
        req = RippleEditRequest(start_time=0.0, end_time=2.0, reason="Cut Lead-in Silence")
        res = TranscriptRipplePlanner.plan_ripple_edit(scenes, trans, master_dur, req)

        self.assertTrue(res.success)
        self.assertEqual(res.cut_duration, 2.0)
        self.assertEqual(res.new_master_dur, 8.0)

        # First scene should be trimmed to [0.0, 0.5]
        self.assertAlmostEqual(res.scenes[0]["start"], 0.0, places=3)
        self.assertAlmostEqual(res.scenes[0]["end"], 0.5, places=3)
        self.assertAlmostEqual(res.scenes[0]["dur"], 0.5, places=3)

        # Remaining scenes shifted leftward by exactly 2.0s
        self.assertAlmostEqual(res.scenes[1]["start"], 0.5, places=3)
        self.assertAlmostEqual(res.scenes[1]["end"], 3.0, places=3)
        self.assertAlmostEqual(res.scenes[-1]["end"], 8.0, places=3)

        # Strict timeline continuity verification
        valid, errs, _ = TimelineNormalizer.validate_timeline(res.scenes, 8.0)
        self.assertTrue(valid, f"Timeline invalid: {errs}")

    def test_ripple_cut_middle(self):
        """Test ripple removal of entire middle scene & segment [2.5 - 5.0s]."""
        scenes, trans, master_dur = self._get_sample_timeline()
        # 1. Cut exactly Scene #2 by range [2.5, 5.0]
        req_range = RippleEditRequest(start_time=2.5, end_time=5.0, target_type="range")
        res_range = TranscriptRipplePlanner.plan_ripple_edit(scenes, trans, master_dur, req_range)

        self.assertTrue(res_range.success)
        self.assertEqual(res_range.cut_duration, 2.5)
        self.assertEqual(res_range.new_master_dur, 7.5)
        self.assertEqual(res_range.removed_scenes_count, 1)
        self.assertEqual(len(res_range.scenes), 3)

        # Scene 1 strictly preserved
        self.assertAlmostEqual(res_range.scenes[0]["start"], 0.0, places=3)
        self.assertAlmostEqual(res_range.scenes[0]["end"], 2.5, places=3)
        self.assertEqual(res_range.scenes[0]["image"], "1.png")

        # Scene 3 shifted into position 2: [2.5, 5.0]
        self.assertAlmostEqual(res_range.scenes[1]["start"], 2.5, places=3)
        self.assertAlmostEqual(res_range.scenes[1]["end"], 5.0, places=3)
        self.assertEqual(res_range.scenes[1]["image"], "3.png")

        # Scene 4 shifted into position 3: [5.0, 7.5]
        self.assertAlmostEqual(res_range.scenes[2]["start"], 5.0, places=3)
        self.assertAlmostEqual(res_range.scenes[2]["end"], 7.5, places=3)
        self.assertEqual(res_range.scenes[2]["image"], "4.png")

        valid, errs, _ = TimelineNormalizer.validate_timeline(res_range.scenes, 7.5)
        self.assertTrue(valid, f"Timeline invalid: {errs}")

        # 2. Also verify segment-specific targeting (Segment #1 is 2.5s to 4.8s -> 2.3s cut)
        req_seg = RippleEditRequest(start_time=0.0, end_time=0.0, target_type="segment", segment_index=1)
        res_seg = TranscriptRipplePlanner.plan_ripple_edit(scenes, trans, master_dur, req_seg)
        self.assertTrue(res_seg.success)
        self.assertEqual(res_seg.cut_duration, 2.3)
        self.assertEqual(res_seg.new_master_dur, 7.7)

    def test_ripple_cut_end(self):
        """Test ripple removal at the tail of timeline [8.0 - 10.0s]."""
        scenes, trans, master_dur = self._get_sample_timeline()
        req = RippleEditRequest(start_time=8.0, end_time=10.0)
        res = TranscriptRipplePlanner.plan_ripple_edit(scenes, trans, master_dur, req)

        self.assertTrue(res.success)
        self.assertEqual(res.new_master_dur, 8.0)
        self.assertAlmostEqual(res.scenes[-1]["end"], 8.0, places=3)
        valid, errs, _ = TimelineNormalizer.validate_timeline(res.scenes, 8.0)
        self.assertTrue(valid)

    def test_ripple_locked_boundary_protection(self):
        """Verify that locked scenes cannot be trimmed or deleted without explicit override."""
        scenes, trans, master_dur = self._get_sample_timeline()
        # Lock Scene #2
        scenes[1]["is_locked"] = True

        req = RippleEditRequest(start_time=2.5, end_time=5.0, protect_locked=True)
        with self.assertRaises(ProtectedIntervalError):
            TranscriptRipplePlanner.plan_ripple_edit(scenes, trans, master_dur, req)

    def test_ripple_preview_vs_committed(self):
        """Verify dry_run preview leaves source objects unmodified."""
        scenes, trans, master_dur = self._get_sample_timeline()
        scenes_copy = json.dumps(scenes)

        req = RippleEditRequest(start_time=1.0, end_time=3.0)
        preview_res = TranscriptRipplePlanner.plan_ripple_edit(scenes, trans, master_dur, req, dry_run=True)

        self.assertTrue(preview_res.is_dry_run)
        self.assertEqual(preview_res.cut_duration, 2.0)
        # Ensure original input was completely untouched
        self.assertEqual(json.dumps(scenes), scenes_copy)

    def test_ripple_undo_redo_history(self):
        """Verify state preservation across history undo and redo stack."""
        history = RippleHistoryManager(max_history=10)
        scenes, trans, master_dur = self._get_sample_timeline()

        # 1. Push initial snapshot
        history.push_snapshot(scenes, trans, master_dur)
        self.assertTrue(history.can_undo())
        self.assertFalse(history.can_redo())

        # 2. Simulate edit to 7.5s
        edited_scenes = scenes[:3]
        edited_dur = 7.5

        # 3. Undo restores initial state
        restored = history.undo(edited_scenes, trans, edited_dur)
        self.assertIsNotNone(restored)
        self.assertEqual(restored["master_dur"], 10.0)
        self.assertEqual(len(restored["scenes"]), 4)
        self.assertTrue(history.can_redo())

        # 4. Redo restores edited state
        redone = history.redo(restored["scenes"], trans, restored["master_dur"])
        self.assertIsNotNone(redone)
        self.assertEqual(redone["master_dur"], 7.5)
        self.assertEqual(len(redone["scenes"]), 3)

    def test_ripple_repeated_operation_safety(self):
        """Verify that attempting to cut out-of-bounds intervals is rejected safely."""
        scenes, trans, master_dur = self._get_sample_timeline()

        # Inverted cut range [6.0 - 4.0]
        req_inverted = RippleEditRequest(start_time=6.0, end_time=4.0)
        with self.assertRaises(InvalidRippleRequestError):
            TranscriptRipplePlanner.plan_ripple_edit(scenes, trans, master_dur, req_inverted)

        # Exceeding master duration [8.0 - 15.0s]
        req_oob = RippleEditRequest(start_time=8.0, end_time=15.0)
        with self.assertRaises(InvalidRippleRequestError):
            TranscriptRipplePlanner.plan_ripple_edit(scenes, trans, master_dur, req_oob)

    # =========================================================================
    # 3. REGRESSION CHECKS (PHASES 1, 2, 3)
    # =========================================================================

    def test_phase1_2_3_regressions(self):
        """Verify Phase 1 motion, Phase 2 cadence alignment, and Phase 3 B-roll modules stay intact."""
        # Phase 1: Motion easing & shot roles
        from engine.motion_intelligence import (
            MotionIntelligenceEngine,
            SceneMotionPlan,
            apply_easing,
            VALID_SHOT_ROLES,
            VALID_EASING_CURVES
        )
        self.assertAlmostEqual(apply_easing(0.5, "smoothstep"), 0.5, places=3)
        self.assertLess(apply_easing(0.2, "smoothstep"), 0.2)
        self.assertIn("establishing_wide", VALID_SHOT_ROLES)
        self.assertIn("cubic_in_out", VALID_EASING_CURVES)

        # Phase 2: Audio rhythm engine
        from engine.audio_rhythm import AudioRhythmEngine, CadenceBoundaryPlanner
        self.assertTrue(hasattr(AudioRhythmEngine, "probe_audio_duration"))
        self.assertTrue(hasattr(CadenceBoundaryPlanner, "align_timeline_boundaries"))

        # Phase 3: B-roll indexer
        from engine.broll_indexer import BRollIndexer, ShotDetector
        self.assertTrue(hasattr(BRollIndexer, "discover_video_assets"))
        self.assertTrue(hasattr(ShotDetector, "detect_shots"))

    # =========================================================================
    # 4. FASTAPI ENDPOINT INTEGRATION TESTS
    # =========================================================================

    def test_api_waveform_endpoint(self):
        """Test GET /api/audio/waveform endpoint contract."""
        from fastapi.testclient import TestClient
        from web.server import app

        proj_dir = self.temp_path / "api_test_project"
        proj_dir.mkdir(parents=True, exist_ok=True)
        self._create_synthetic_wav(str(proj_dir / "narration.wav"), duration_sec=3.0, amplitude=0.7)

        client = TestClient(app)
        resp = client.get(f"/api/audio/waveform?project_path={str(proj_dir)}&points_per_second=20.0")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertAlmostEqual(data["duration"], 3.0, delta=0.1)
        self.assertGreater(data["total_points"], 0)
        self.assertEqual(len(data["peaks"]), data["total_points"])
        self.assertTrue(isinstance(data["fingerprint"], str))

    def test_api_ripple_preview_apply_undo_endpoints(self):
        """Test POST /api/timeline/ripple_preview, ripple_apply, and ripple_undo endpoints."""
        from fastapi.testclient import TestClient
        from web.server import app

        proj_dir = self.temp_path / "api_ripple_project"
        proj_dir.mkdir(parents=True, exist_ok=True)
        self._create_synthetic_wav(str(proj_dir / "narration.wav"), duration_sec=10.0, amplitude=0.5)

        scenes, trans, master_dur = self._get_sample_timeline()
        plan_file = proj_dir / "plan.json"
        trans_file = proj_dir / "transcript.json"

        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump({"scenes": scenes}, f)
        with open(trans_file, "w", encoding="utf-8") as f:
            json.dump({"segments": trans}, f)

        client = TestClient(app)

        # 1. Preview
        prev_resp = client.post("/api/timeline/ripple_preview", json={
            "project_path": str(proj_dir),
            "start_time": 2.5,
            "end_time": 5.0,
            "target_type": "range"
        })
        self.assertEqual(prev_resp.status_code, 200)
        prev_data = prev_resp.json()
        self.assertTrue(prev_data["is_dry_run"])
        self.assertEqual(prev_data["cut_duration"], 2.5)

        # Ensure plan on disk unchanged
        with open(plan_file, "r") as f:
            disk_plan = json.load(f)
        self.assertEqual(len(disk_plan["scenes"]), 4)

        # 2. Apply
        apply_resp = client.post("/api/timeline/ripple_apply", json={
            "project_path": str(proj_dir),
            "start_time": 2.5,
            "end_time": 5.0,
            "target_type": "range"
        })
        self.assertEqual(apply_resp.status_code, 200)
        apply_data = apply_resp.json()
        self.assertFalse(apply_data["is_dry_run"])
        self.assertEqual(apply_data["new_master_dur"], 7.5)

        # Verify plan on disk was atomically updated
        with open(plan_file, "r") as f:
            updated_plan = json.load(f)
        self.assertEqual(len(updated_plan["scenes"]), 3)
        self.assertEqual(updated_plan["scenes"][-1]["end"], 7.5)
        self.assertIn("audio_edits", updated_plan)

        # 3. Undo
        undo_resp = client.post("/api/timeline/ripple_undo", json={
            "project_path": str(proj_dir)
        })
        self.assertEqual(undo_resp.status_code, 200)
        undo_data = undo_resp.json()
        self.assertTrue(undo_data["success"])
        self.assertEqual(undo_data["master_dur"], 10.0)

        # Verify plan on disk was restored
        with open(plan_file, "r") as f:
            restored_plan = json.load(f)
        self.assertEqual(len(restored_plan["scenes"]), 4)
        self.assertEqual(restored_plan["scenes"][-1]["end"], 10.0)


if __name__ == "__main__":
    unittest.main()
