#!/usr/bin/env python3
"""
caption_pagination.py — Sentence-Aware & Silence-Aware Caption Pagination.

Implements pagination principles inspired by remotion-captions-kit and @remotion/captions:
  - Sentence boundaries always take highest priority (. ! ? … quotes/brackets).
  - Silence gaps (>= 350ms) create clean natural page breaks.
  - Abbreviation protection (Dr., Mr., vs., U.S., $1.5M, etc.).
  - Configurable lengths: Short (2-4 words), Medium (4-7 words), Long (7-12 words).
  - Character bounds (e.g. 42 chars for medium, 24 for short, 75 for long).
  - Clause-aware backup: backs up to the nearest comma/clause break when forced by limits.
  - Flash-page merging (< 300ms) to prevent flickering.
"""

import re
from typing import List, Optional
from .caption_model import CaptionModel, CaptionSegment, Word

PAGINATION_PRESETS = {
    "short": {
        "min_words": 1,
        "target_words": 3,
        "max_words": 4,
        "max_chars": 26,
        "max_duration": 1.6,
        "silence_gap": 0.30,
        "min_duration": 0.25,
    },
    "medium": {
        "min_words": 3,
        "target_words": 6,
        "max_words": 8,
        "max_chars": 44,
        "max_duration": 2.8,
        "silence_gap": 0.35,
        "min_duration": 0.30,
    },
    "long": {
        "min_words": 6,
        "target_words": 10,
        "max_words": 14,
        "max_chars": 80,
        "max_duration": 4.5,
        "silence_gap": 0.40,
        "min_duration": 0.35,
    },
}

# Common abbreviations that should NOT trigger a sentence break
ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "vs.", "etc.",
    "e.g.", "i.e.", "u.s.", "u.k.", "u.n.", "st.", "ave.", "gen.", "rep.", "sen."
}


def is_abbreviation(word_text: str) -> bool:
    clean = word_text.strip().lower()
    if clean in ABBREVIATIONS:
        return True
    # Check numeric decimals e.g. $1.5, 3.14
    if re.match(r'^[\$€£]?\d+\.\d+%?$', clean):
        return True
    return False


def is_sentence_ender(word_text: str) -> bool:
    clean = word_text.strip()
    if is_abbreviation(clean):
        return False
    # Ends with . ! ? … followed optionally by quote/paren/bracket
    return bool(re.search(r'[\.\!\?…][\'"”’\)\]}]*$', clean))


def is_clause_boundary(word_text: str) -> bool:
    clean = word_text.strip()
    return bool(re.search(r'[,;:—–][\'"”’\)\]}]*$', clean))


def paginate_captions(
    model: CaptionModel,
    length_mode: str = "medium",
    custom_params: Optional[dict] = None
) -> CaptionModel:
    """
    Paginate a raw or segment-based CaptionModel into human-readable,
    syntactically pleasing caption pages.
    """
    preset = PAGINATION_PRESETS.get(length_mode.lower(), PAGINATION_PRESETS["medium"]).copy()
    if custom_params:
        preset.update(custom_params)

    max_words = preset["max_words"]
    max_chars = preset["max_chars"]
    max_duration = preset["max_duration"]
    silence_gap = preset["silence_gap"]
    min_duration = preset["min_duration"]

    # Flatten all words from input segments
    all_words: List[Word] = []
    if any(not seg.words and seg.text.strip() for seg in model.segments):
        model.ensure_word_timings()
    for seg in model.segments:
        if seg.words:
            all_words.extend(seg.words)

    if not all_words:
        return model

    # Ensure words are strictly sorted chronologically (handles overlapping manual text overlays)
    all_words.sort(key=lambda w: (w.start, w.end))

    pages: List[List[Word]] = []
    current_page: List[Word] = []

    def get_page_chars(words: List[Word]) -> int:
        return sum(len(w.text) for w in words) + max(0, len(words) - 1)

    def get_page_duration(words: List[Word]) -> float:
        if not words:
            return 0.0
        return max(0.0, words[-1].end - words[0].start)

    i = 0
    while i < len(all_words):
        w = all_words[i]
        
        # Check silence gap before w
        if current_page:
            gap = w.start - current_page[-1].end
            if gap >= silence_gap:
                # Natural breath silence break
                pages.append(current_page)
                current_page = [w]
                i += 1
                continue

        # Add word tentatively
        candidate = current_page + [w]
        c_words = len(candidate)
        c_chars = get_page_chars(candidate)
        c_dur = get_page_duration(candidate)

        # Immediate sentence end check
        if is_sentence_ender(w.text):
            candidate_page = candidate
            pages.append(candidate_page)
            current_page = []
            i += 1
            continue

        # Check if limits exceeded
        if c_words > max_words or c_chars > max_chars or c_dur > max_duration:
            if not current_page:
                # Single word exceeds limit, must output it alone
                pages.append([w])
                current_page = []
                i += 1
                continue

            # Limit exceeded: Try clause boundary backup
            # Look backwards in current_page for a comma or semicolon
            backup_idx = -1
            for k in range(len(current_page) - 1, 0, -1):
                if is_clause_boundary(current_page[k].text):
                    backup_idx = k
                    break

            if backup_idx > 0 and (backup_idx + 1) >= preset["min_words"]:
                # Back up to the clause boundary!
                page_words = current_page[:backup_idx + 1]
                remaining_words = current_page[backup_idx + 1:]
                pages.append(page_words)
                current_page = remaining_words + [w]
            else:
                # Regular break at previous word
                pages.append(current_page)
                current_page = [w]
            i += 1
            continue

        # Otherwise continue page
        current_page.append(w)
        i += 1

    if current_page:
        pages.append(current_page)

    # Flash-page merging: merge tiny pages (< min_duration) with an adjacent page if limits permit
    merged_pages: List[List[Word]] = []
    for p in pages:
        if not p:
            continue
        p_dur = p[-1].end - p[0].start
        if p_dur < min_duration and merged_pages:
            # Check if previous page can absorb p without exceeding max_chars * 1.3
            prev = merged_pages[-1]
            combined = prev + p
            combined_chars = get_page_chars(combined)
            combined_dur = combined[-1].end - combined[0].start
            # Only merge if not across a heavy sentence boundary
            if not is_sentence_ender(prev[-1].text) and combined_chars <= int(max_chars * 1.3) and combined_dur <= (max_duration * 1.25):
                merged_pages[-1] = combined
                continue
        merged_pages.append(p)

    # Construct final paginated CaptionSegments
    new_segments: List[CaptionSegment] = []
    for idx, p in enumerate(merged_pages):
        if not p:
            continue
        p_sorted = sorted(p, key=lambda w: (w.start, w.end))
        start_t = round(float(p_sorted[0].start), 3)
        end_t = round(float(max(w.end for w in p_sorted)), 3)
        if end_t <= start_t:
            end_t = round(start_t + 0.1, 3)
        text = " ".join(w.text for w in p_sorted).strip()
        sanitized_words = [
            Word(
                text=w.text,
                start=round(float(max(start_t, w.start)), 3),
                end=round(float(min(end_t, max(w.start + 0.04, w.end))), 3),
                confidence=w.confidence
            )
            for w in p_sorted
        ]
        new_segments.append(CaptionSegment(
            id=idx + 1,
            start=start_t,
            end=end_t,
            text=text,
            words=sanitized_words
        ))

    return CaptionModel(segments=new_segments, language=model.language)
