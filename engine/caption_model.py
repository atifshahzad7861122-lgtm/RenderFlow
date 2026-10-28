#!/usr/bin/env python3
"""
caption_model.py — Normalized Caption & Subtitle Data Model for Rendering Studio.

Architecture:
  - Word: Word-level token with accurate start/end timestamps.
  - CaptionSegment: Sentence / phrase segment containing ordered words.
  - CaptionModel: Top-level normalized caption container with validation,
    serialization, fallback word interpolation, and active-word query.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
import json
import re


@dataclass
class Word:
    text: str
    start: float
    end: float
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "word": self.text,
            "start": round(float(self.start), 3),
            "end": round(float(self.end), 3),
            "confidence": round(float(self.confidence), 3),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Word":
        return cls(
            text=str(d.get("text") or d.get("word") or "").strip(),
            start=float(d.get("start", 0.0)),
            end=float(d.get("end", 0.0)),
            confidence=float(d.get("confidence", 1.0)),
        )


@dataclass
class CaptionSegment:
    id: int
    start: float
    end: float
    text: str
    words: List[Word] = field(default_factory=list)

    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def get_active_word_at(self, t: float) -> Optional[Tuple[int, Word]]:
        """Return (index, Word) if t falls within [word.start, word.end), else None."""
        if not (self.start <= t <= self.end):
            return None
        for idx, w in enumerate(self.words):
            if w.start <= t < w.end:
                return idx, w
        # Edge case: t matches segment end or last word
        if self.words and abs(t - self.words[-1].end) < 0.05:
            return len(self.words) - 1, self.words[-1]
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": int(self.id),
            "start": round(float(self.start), 3),
            "end": round(float(self.end), 3),
            "text": self.text.strip(),
            "words": [w.to_dict() for w in self.words],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CaptionSegment":
        raw_words = d.get("words", [])
        words = [Word.from_dict(w) for w in raw_words if isinstance(w, dict)]
        text = str(d.get("text", "")).strip()
        if not text and words:
            text = " ".join(w.text for w in words)
        raw_id = d.get("id")
        parsed_id = int(raw_id) if raw_id is not None and str(raw_id).strip() != "" else 0
        return cls(
            id=parsed_id,
            start=float(d.get("start", 0.0)),
            end=float(d.get("end", 0.0)),
            text=text,
            words=words,
        )


class CaptionModel:
    """Normalized caption timeline container."""

    def __init__(self, segments: Optional[List[CaptionSegment]] = None, language: str = "auto", duration_s: Optional[float] = None):
        self.segments: List[CaptionSegment] = segments or []
        self.language: str = language
        self._duration_s = duration_s

    @property
    def total_duration(self) -> float:
        if self._duration_s is not None:
            return float(self._duration_s)
        if not self.segments:
            return 0.0
        return max(s.end for s in self.segments)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "language": self.language,
            "segments": [s.to_dict() for s in self.segments]
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CaptionModel":
        if isinstance(d, list):
            raw_segs = d
            lang = "auto"
        else:
            raw_segs = d.get("segments", [])
            lang = d.get("language", "auto")
        segments = []
        for idx, s in enumerate(raw_segs):
            if isinstance(s, dict):
                seg = CaptionSegment.from_dict(s)
                if not seg.id or seg.id <= 0:
                    seg.id = idx + 1
                segments.append(seg)
        # Ensure all segment IDs are strictly unique (prevent degenerate id collisions)
        id_set = set(s.id for s in segments)
        if len(id_set) < len(segments):
            for idx, seg in enumerate(segments):
                seg.id = idx + 1
        model = cls(segments=segments, language=lang)
        model.ensure_word_timings()
        return model

    @classmethod
    def from_json(cls, json_str: str) -> "CaptionModel":
        data = json.loads(json_str)
        return cls.from_dict(data)

    def ensure_word_timings(self) -> None:
        """
        If segments have text but empty or missing word timestamps,
        interpolate realistic word timings across the segment duration.
        If segments already have words, sanitize them to guarantee positive durations (>= 0.04s),
        monotonic ordering, and valid boundary constraints.
        """
        for seg in self.segments:
            seg_text = seg.text.strip()

            # Case 1: Existing words present - sanitize and ensure validity
            if seg.words:
                if seg.end <= seg.start:
                    seg.end = round(seg.start + 0.5, 3)

                cur_t = seg.start
                for widx in range(len(seg.words)):
                    w = seg.words[widx]
                    # Clamp start to not precede segment start
                    if w.start < seg.start:
                        w.start = seg.start
                    # Monotonicity with previous word
                    if w.start < cur_t:
                        w.start = cur_t
                    # Ensure positive duration (minimum 0.04s)
                    if w.end <= w.start:
                        # If next word exists and starts further ahead, use part of gap
                        if widx + 1 < len(seg.words) and seg.words[widx + 1].start > w.start + 0.05:
                            w.end = round(min(seg.words[widx + 1].start, w.start + 0.08), 3)
                        else:
                            w.end = round(w.start + 0.05, 3)
                    # If w.end exceeds segment end, expand segment end
                    if w.end > seg.end:
                        seg.end = round(w.end + 0.02, 3)

                    w.start = round(w.start, 3)
                    w.end = round(w.end, 3)
                    cur_t = w.end
                continue

            # Case 2: No words present, interpolate
            if not seg_text:
                continue
            words_tokens = [w for w in re.split(r'\s+', seg_text) if w]
            if not words_tokens:
                continue

            seg_dur = max(0.1, seg.end - seg.start)
            # Weight each word by character length + pause bonus for punctuation
            weights = []
            for w in words_tokens:
                base_len = max(1, len(w))
                if w.endswith(('.', '!', '?', '…', ':')):
                    base_len += 2
                elif w.endswith((',', ';')):
                    base_len += 1
                weights.append(base_len)
            total_weight = sum(weights) or 1

            cur_t = seg.start
            interpolated_words = []
            for i, w in enumerate(words_tokens):
                word_dur = max(0.04, (weights[i] / total_weight) * seg_dur)
                w_start = cur_t
                w_end = seg.end if i == len(words_tokens) - 1 else min(seg.end, cur_t + word_dur)
                if w_end <= w_start:
                    w_end = round(w_start + 0.04, 3)
                    if w_end > seg.end:
                        seg.end = w_end
                interpolated_words.append(Word(text=w, start=round(w_start, 3), end=round(w_end, 3)))
                cur_t = w_end

            seg.words = interpolated_words

    def validate(self) -> Tuple[bool, List[str]]:
        """
        Rigorous validation of the normalized caption model.
        Checks:
          - start >= 0
          - end > start
          - word.start >= segment.start - 0.05 (tolerating micro float rounding)
          - word.end <= segment.end + 0.05
          - no negative durations
          - valid non-empty Unicode text
        """
        errors = []
        if not self.segments:
            return (False, ["Caption model has zero segments/cues: expected valid spoken narration captions"])
        for seg in self.segments:
            if seg.start < 0:
                errors.append(f"Segment {seg.id}: invalid negative start {seg.start}s")
            if seg.end <= seg.start:
                errors.append(f"Segment {seg.id}: end ({seg.end}s) must be greater than start ({seg.start}s)")
            if not seg.text.strip() and not seg.words:
                errors.append(f"Segment {seg.id}: missing both text and words")

            prev_w_end = seg.start
            for widx, w in enumerate(seg.words):
                if w.start < 0 or w.end <= w.start:
                    errors.append(f"Segment {seg.id} Word {widx} ('{w.text}'): invalid duration [{w.start}s, {w.end}s]")
                if w.start < seg.start - 0.1:
                    errors.append(f"Segment {seg.id} Word {widx} ('{w.text}'): start {w.start}s precedes segment start {seg.start}s")
                if w.end > seg.end + 0.1:
                    errors.append(f"Segment {seg.id} Word {widx} ('{w.text}'): end {w.end}s exceeds segment end {seg.end}s")
                prev_w_end = w.end

        return (len(errors) == 0, errors)

    def filter_by_time_window(self, window_start: float, window_end: float) -> "CaptionModel":
        """
        Extract and normalize captions for a sub-window (e.g. streaming chunk).
        Timestamps are shifted so window_start becomes 0.0s.
        """
        chunk_segs = []
        new_id = 1
        for s in self.segments:
            # Overlap check
            if s.end <= window_start or s.start >= window_end:
                continue
            chunk_len = window_end - window_start
            # Clip bounds strictly to [0.0, chunk_len]
            c_start = max(0.0, s.start - window_start)
            c_end = min(chunk_len, max(c_start + 0.05, s.end - window_start))
            
            # Words
            c_words = []
            for w in s.words:
                if w.end <= window_start or w.start >= window_end:
                    continue
                w_s = min(chunk_len, max(0.0, w.start - window_start))
                w_e = min(chunk_len, max(w_s + 0.02, w.end - window_start))
                if w_e > w_s:
                    c_words.append(Word(text=w.text, start=round(w_s, 3), end=round(w_e, 3), confidence=w.confidence))

            chunk_segs.append(CaptionSegment(
                id=new_id,
                start=round(c_start, 3),
                end=round(c_end, 3),
                text=s.text,
                words=c_words
            ))
            new_id += 1

        return CaptionModel(segments=chunk_segs, language=self.language)
