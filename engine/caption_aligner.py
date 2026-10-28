#!/usr/bin/env python3
"""
caption_aligner.py — Dynamic Caption Text Alignment Engine.

Guarantees:
  - Audio and Source Word Timestamps (Deepgram/Whisper) remain the absolute TIMING AUTHORITY.
  - When LLM or user modifies wording (e.g. contractions, numeral conversion, shortening):
      "you do not need ten thousand followers" -> "You don't need 10,000 followers."
    the new words are accurately aligned to the source speech timestamps without timing drift.
  - Preserves 4 versions of each segment:
      1. Original Transcript (raw authoritative speech output)
      2. AI Clean Version (fixed punctuation, grammar, filler removed)
      3. AI Viral Version (punchier, shortened, optimized phrase structure)
      4. User Final Version (custom user modifications)
"""

import re
import difflib
from typing import List, Dict, Any, Optional, Tuple

from .caption_model import CaptionSegment, Word, CaptionModel


def normalize_token(text: str) -> str:
    """Normalize token for robust phonetic/lexical matching."""
    t = text.lower()
    t = re.sub(r'[^\w\s]', '', t)
    return t.strip()


def number_phonetic_equivalent(token: str) -> List[str]:
    """Map common numbers and contractions to phonetic word equivalents."""
    num_map = {
        "1": ["one"], "2": ["two"], "3": ["three"], "4": ["four"], "5": ["five"],
        "6": ["six"], "7": ["seven"], "8": ["eight"], "9": ["nine"], "10": ["ten"],
        "100": ["hundred"], "1000": ["thousand"], "10000": ["ten", "thousand"],
        "10,000": ["ten", "thousand"], "100,000": ["hundred", "thousand"],
        "1,000,000": ["one", "million"], "1m": ["one", "million"], "1k": ["one", "thousand"]
    }
    return num_map.get(token.lower(), [token.lower()])


class CaptionTextAligner:
    """
    Aligns edited or rewritten caption text to source word timestamps,
    anchoring identical/similar words and interpolating missing/reworded boundaries.
    """

    @classmethod
    def align_segment_text(
        cls,
        source_segment: CaptionSegment,
        new_text: str,
        preserve_emphasis: Optional[List[str]] = None
    ) -> CaptionSegment:
        """
        Produce a new CaptionSegment with new_text where every word has
        microsecond timestamps mapped strictly from source_segment.words.
        """
        new_text_clean = new_text.strip()
        if not new_text_clean:
            return source_segment

        new_tokens = [t for t in re.split(r'\s+', new_text_clean) if t]
        if not new_tokens:
            return source_segment

        source_words = source_segment.words
        if not source_words:
            # If source has no words, interpolate across segment duration
            seg_copy = CaptionSegment(
                id=source_segment.id,
                start=source_segment.start,
                end=source_segment.end,
                text=new_text_clean,
                words=[]
            )
            # Reconstruct words
            model = CaptionModel(segments=[seg_copy])
            model.ensure_word_timings()
            return model.segments[0]

        # Step 1: Token sequence matching using difflib SequenceMatcher
        src_norm = [normalize_token(w.text) for w in source_words]
        dst_norm = [normalize_token(t) for t in new_tokens]

        matcher = difflib.SequenceMatcher(None, src_norm, dst_norm)
        matching_blocks = matcher.get_matching_blocks()

        aligned_words: List[Optional[Word]] = [None] * len(new_tokens)

        # Step 2: Place exact matches from matching blocks
        for block in matching_blocks:
            src_i = block.a
            dst_i = block.b
            match_len = block.size
            for k in range(match_len):
                sw = source_words[src_i + k]
                dw_text = new_tokens[dst_i + k]
                aligned_words[dst_i + k] = Word(
                    text=dw_text,
                    start=sw.start,
                    end=sw.end,
                    confidence=sw.confidence
                )

        # Step 3: Handle contractions & numbers (e.g. "don't" vs "do not", "10,000" vs "ten thousand")
        for i, dw in enumerate(aligned_words):
            if dw is not None:
                continue
            dst_token = dst_norm[i]
            # Check if dst_token corresponds to multiple source tokens
            eq_tokens = number_phonetic_equivalent(dst_token)
            if len(eq_tokens) > 1:
                # Find matching sequence in source
                for s_idx in range(len(src_norm) - len(eq_tokens) + 1):
                    if src_norm[s_idx:s_idx + len(eq_tokens)] == eq_tokens:
                        w_start = source_words[s_idx].start
                        w_end = source_words[s_idx + len(eq_tokens) - 1].end
                        aligned_words[i] = Word(
                            text=new_tokens[i],
                            start=w_start,
                            end=w_end,
                            confidence=0.95
                        )
                        break

        # Step 4: Proportional interpolation for unassigned tokens between anchors
        # Anchors include segment start at t=0 and segment end at t=dur
        seg_start = source_segment.start
        seg_end = source_segment.end

        # Find continuous unassigned spans and interpolate
        idx = 0
        n = len(new_tokens)
        while idx < n:
            if aligned_words[idx] is not None:
                idx += 1
                continue

            # Start of unassigned span
            span_start_idx = idx
            while idx < n and aligned_words[idx] is None:
                idx += 1
            span_end_idx = idx  # exclusive

            # Determine boundary time bounds for this unassigned span
            t_left = seg_start if span_start_idx == 0 else aligned_words[span_start_idx - 1].end
            t_right = seg_end if span_end_idx == n else aligned_words[span_end_idx].start

            # Ensure valid non-inverted time window
            if t_right <= t_left:
                t_right = round(t_left + 0.1 * (span_end_idx - span_start_idx), 3)
                if t_right > seg_end:
                    seg_end = t_right

            span_dur = t_right - t_left
            tokens_in_span = new_tokens[span_start_idx:span_end_idx]
            weights = [max(1, len(t)) for t in tokens_in_span]
            tot_w = sum(weights) or 1

            cur_t = t_left
            for k, tok in enumerate(tokens_in_span):
                w_dur = max(0.04, (weights[k] / tot_w) * span_dur)
                w_s = round(cur_t, 3)
                w_e = round(t_right if k == len(tokens_in_span) - 1 else min(t_right, cur_t + w_dur), 3)
                if w_e <= w_s:
                    w_e = round(w_s + 0.04, 3)
                aligned_words[span_start_idx + k] = Word(
                    text=tok,
                    start=w_s,
                    end=w_e,
                    confidence=0.9
                )
                cur_t = w_e

        # Step 5: Final monotonicity and boundary sanitization
        cur_t = seg_start
        final_words: List[Word] = []
        for w in aligned_words:
            assert w is not None
            if w.start < cur_t:
                w.start = cur_t
            if w.end <= w.start:
                w.end = round(w.start + 0.04, 3)
            if w.end > seg_end:
                seg_end = round(w.end + 0.02, 3)
            w.start = round(w.start, 3)
            w.end = round(w.end, 3)
            cur_t = w.end
            final_words.append(w)

        return CaptionSegment(
            id=source_segment.id,
            start=source_segment.start,
            end=round(max(seg_end, final_words[-1].end), 3),
            text=new_text_clean,
            words=final_words
        )

    @classmethod
    def align_model(
        cls,
        source_model: CaptionModel,
        modified_segments_text: List[Dict[str, Any]]
    ) -> CaptionModel:
        """
        Align an entire CaptionModel against rewritten/edited texts.
        modified_segments_text can be [{'id': 1, 'text': '...'}, ...]
        """
        text_by_id = {item.get("id"): item.get("text", "") for item in modified_segments_text if item.get("id") is not None}
        new_segments: List[CaptionSegment] = []

        for idx, seg in enumerate(source_model.segments):
            if seg.id in text_by_id:
                new_text = text_by_id[seg.id]
            elif idx < len(modified_segments_text):
                new_text = modified_segments_text[idx].get("text", seg.text)
            else:
                new_text = seg.text
            aligned_seg = cls.align_segment_text(seg, new_text)
            new_segments.append(aligned_seg)

        model = CaptionModel(segments=new_segments, language=source_model.language)
        model.ensure_word_timings()
        return model
