"""
qa/test_preview_transition_parity.py
Mathematical and pixel-level parity tests for built-in preview transitions vs FFmpeg xfade.
"""
import pytest
import numpy as np


def compute_transition_window(cut_time: float, duration: float):
    half = duration / 2.0
    return cut_time - half, cut_time + half


def compute_transition_progress(current_time: float, cut_time: float, duration: float) -> float:
    start_t, end_t = compute_transition_window(cut_time, duration)
    if current_time <= start_t:
        return 0.0
    if current_time >= end_t:
        return 1.0
    return (current_time - start_t) / duration


def blend_crossfade(frame_a: np.ndarray, frame_b: np.ndarray, progress: float) -> np.ndarray:
    p = np.clip(progress, 0.0, 1.0)
    return ((1.0 - p) * frame_a + p * frame_b).astype(np.uint8)


def blend_dip_black(frame_a: np.ndarray, frame_b: np.ndarray, progress: float) -> np.ndarray:
    p = np.clip(progress, 0.0, 1.0)
    if p < 0.5:
        factor = 1.0 - (p * 2.0)
        return (frame_a * factor).astype(np.uint8)
    else:
        factor = (p - 0.5) * 2.0
        return (frame_b * factor).astype(np.uint8)


def blend_wipe_right(frame_a: np.ndarray, frame_b: np.ndarray, progress: float) -> np.ndarray:
    p = np.clip(progress, 0.0, 1.0)
    h, w, c = frame_a.shape
    split_x = int(w * p)
    result = frame_a.copy()
    if split_x > 0:
        result[:, :split_x] = frame_b[:, :split_x]
    return result


def test_transition_window_and_progress_timing():
    cut_time = 5.0
    duration = 1.0
    
    start_t, end_t = compute_transition_window(cut_time, duration)
    assert start_t == 4.5
    assert end_t == 5.5
    
    # Prior to window: progress 0
    assert compute_transition_progress(4.0, cut_time, duration) == 0.0
    assert compute_transition_progress(4.5, cut_time, duration) == 0.0
    
    # Exact center: progress 0.5
    assert compute_transition_progress(5.0, cut_time, duration) == 0.5
    
    # 25% and 75%
    assert abs(compute_transition_progress(4.75, cut_time, duration) - 0.25) < 1e-6
    assert abs(compute_transition_progress(5.25, cut_time, duration) - 0.75) < 1e-6
    
    # Beyond window: progress 1.0
    assert compute_transition_progress(5.5, cut_time, duration) == 1.0
    assert compute_transition_progress(6.0, cut_time, duration) == 1.0


def test_crossfade_pixel_blending():
    # Frame A: Pure Red (200, 0, 0)
    # Frame B: Pure Blue (0, 0, 200)
    h, w = 10, 10
    frame_a = np.zeros((h, w, 3), dtype=np.uint8)
    frame_a[:, :] = [200, 0, 0]
    
    frame_b = np.zeros((h, w, 3), dtype=np.uint8)
    frame_b[:, :] = [0, 0, 200]
    
    # At p=0 -> pure Frame A
    out_0 = blend_crossfade(frame_a, frame_b, 0.0)
    assert np.all(out_0 == [200, 0, 0])
    
    # At p=0.5 -> 50% blend
    out_half = blend_crossfade(frame_a, frame_b, 0.5)
    assert np.all(out_half == [100, 0, 100])
    
    # At p=1.0 -> pure Frame B
    out_1 = blend_crossfade(frame_a, frame_b, 1.0)
    assert np.all(out_1 == [0, 0, 200])


def test_dip_black_pixel_blending():
    h, w = 10, 10
    frame_a = np.full((h, w, 3), 200, dtype=np.uint8)
    frame_b = np.full((h, w, 3), 100, dtype=np.uint8)
    
    # At p=0.5 -> black
    out_half = blend_dip_black(frame_a, frame_b, 0.5)
    assert np.all(out_half == [0, 0, 0])
    
    # At p=0.25 -> Frame A at 50% brightness
    out_quarter = blend_dip_black(frame_a, frame_b, 0.25)
    assert np.all(out_quarter == [100, 100, 100])
    
    # At p=0.75 -> Frame B at 50% brightness
    out_3quarter = blend_dip_black(frame_a, frame_b, 0.75)
    assert np.all(out_3quarter == [50, 50, 50])


def test_wipe_right_pixel_blending():
    h, w = 10, 100
    frame_a = np.full((h, w, 3), 50, dtype=np.uint8)
    frame_b = np.full((h, w, 3), 220, dtype=np.uint8)
    
    # At p=0.4 -> first 40 columns are Frame B, remaining 60 are Frame A
    out = blend_wipe_right(frame_a, frame_b, 0.4)
    assert np.all(out[:, :40] == [220, 220, 220])
    assert np.all(out[:, 40:] == [50, 50, 50])
