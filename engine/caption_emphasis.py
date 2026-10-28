#!/usr/bin/env python3
"""
caption_emphasis.py — Semantic Keyword & Emphasis Extraction Engine.

Identifies high-impact visual words for professional social media / viral / documentary styles:
  - Numerical data & metrics ($10M, 10,000, 99%, #1)
  - Superlatives & contrast words (greatest, never, always, secret, massive, impossible)
  - Action verbs & emotional triggers (expand, destroy, conquer, built, discover, power)
  - Proper nouns & named entities
  - CTA & punchlines
"""

import re
from typing import List, Set, Dict, Any, Optional

from .caption_model import CaptionSegment, Word

# High-impact linguistic triggers for English, Roman Urdu, and multilingual cues
EMPHASIS_TRIGGERS: Set[str] = {
    # Power & impact words
    "empire", "power", "glory", "conquer", "destroy", "expand", "rapidly",
    "secret", "truth", "massive", "huge", "insane", "impossible", "revolutionary",
    "money", "wealth", "million", "billion", "dollars", "followers", "freedom",
    "danger", "fatal", "never", "always", "every", "first", "final", "ultimate",
    "vision", "great", "greatest", "historic", "shocking", "brutal", "unbelievable",
    "stop", "start", "now", "today", "forever", "legend", "war", "battle", "rise",
    # Roman Urdu / Hindi triggers
    "zaroori", "sabse", "bada", "kamyabi", "paisa", "asli", "karo", "mat",
    "zabardast", "shandar", "khatarnak", "naya", "pehla", "akhri", "duniya"
}


class CaptionEmphasisEngine:
    """Detects and scores keywords for dynamic caption styling."""

    @classmethod
    def identify_emphasis_tokens(
        cls,
        text: str,
        llm_suggested_words: Optional[List[str]] = None,
        language: str = "auto"
    ) -> List[str]:
        """
        Extract list of words/phrases in `text` that deserve visual emphasis.
        Merges LLM reasoning with deterministic semantic heuristics.
        """
        emphasis_set: Set[str] = set()

        # 1. Include LLM suggestions if provided
        if llm_suggested_words:
            for sw in llm_suggested_words:
                cleaned = sw.strip().strip(".,!?:;\"'").lower()
                if cleaned:
                    emphasis_set.add(cleaned)

        # 2. Extract numbers, percentages, currencies, ordinals
        tokens = re.findall(r'\b[\w\$\€\£\¥\%\,\.]+\b', text)
        for t in tokens:
            t_clean = t.strip(".,!?:;\"'")
            # Check for numbers / monetary
            if re.search(r'[\d\$\€\£\¥\%]', t_clean):
                emphasis_set.add(t_clean.lower())
            # Check for uppercase words (e.g. acronyms or intentional emphasis: NASA, FREE)
            elif t_clean.isupper() and len(t_clean) > 1:
                emphasis_set.add(t_clean.lower())
            # Check against semantic triggers dictionary
            elif t_clean.lower() in EMPHASIS_TRIGGERS:
                emphasis_set.add(t_clean.lower())

        # 3. If no emphasis detected, select longest noun/verb token as fallback
        if not emphasis_set and tokens:
            candidate_tokens = [
                t.strip(".,!?:;\"'").lower() for t in tokens
                if len(t.strip(".,!?:;\"'")) > 3
                and t.lower() not in {"this", "that", "with", "from", "have", "were", "been", "they"}
            ]
            if candidate_tokens:
                longest = max(candidate_tokens, key=len)
                emphasis_set.add(longest)

        return sorted(list(emphasis_set))

    @classmethod
    def annotate_segment_emphasis(
        cls,
        segment: CaptionSegment,
        llm_suggested_words: Optional[List[str]] = None,
        language: str = "auto"
    ) -> List[int]:
        """
        Return list of 0-based indices in segment.words that are emphasized.
        """
        emphasis_tokens = cls.identify_emphasis_tokens(
            text=segment.text,
            llm_suggested_words=llm_suggested_words,
            language=language
        )
        highlighted_indices: List[int] = []

        for idx, w in enumerate(segment.words):
            w_norm = re.sub(r'[^\w\s]', '', w.text).strip().lower()
            if w_norm in emphasis_tokens or any(emp in w_norm for emp in emphasis_tokens if len(emp) > 3):
                highlighted_indices.append(idx)

        return highlighted_indices
