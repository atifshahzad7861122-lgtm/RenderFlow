#!/usr/bin/env python3
"""
caption_engine.py — Master Caption Engine Coordinator for Rendering Studio.

Pipeline:
  AUDIO (Master Timeline)
          ↓
  STT ROUTER (Deepgram Nova-3 -> Local Whisper -> Existing Transcript)
          ↓
  WORD TIMESTAMPS + CONFIDENCE + UTTERANCES
          ↓
  CAPTION INTELLIGENCE (LLM: Clean / Viral Rewrite / Semantic Emphasis)
          ↓
  CAPTION TEXT ALIGNER (Anchored timestamp mapping preserving audio sync)
          ↓
  PAGINATION (Sentence + Clause + Silence aware)
          ↓
  STYLE REGISTRY (Creator-Inspired, TikTok, YouTube, Podcast, Cinematic, Karaoke)
          ↓
  ASS GENERATOR (libass-compatible v4.00+)
          ↓
  FFmpeg / libass RENDER & EXPORTS (Burn-in, SRT, ASS, VTT, JSON)
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from .caption_model import CaptionModel, CaptionSegment, Word
from .caption_pagination import paginate_captions
from .caption_styles import (
    get_style, CAPTION_STYLES, STYLE_CATEGORIES, PLATFORM_PRESETS,
    resolve_auto_style, customize_style, get_styles_by_category, search_styles
)
from .caption_ass import build_ass_script
from .caption_export import export_all_caption_formats, export_srt, export_ass, export_vtt, export_json
from .caption_qc import run_full_caption_qc
from .stt_provider import transcribe_with_fallback
from .llm_provider import execute_llm_intelligence_with_fallback
from .caption_aligner import CaptionTextAligner
from .caption_emphasis import CaptionEmphasisEngine

logger = logging.getLogger("rendering_studio.caption_engine")


class CaptionEngine:
    """Master Caption Engine orchestrating transcription, AI intelligence, alignment, pagination, styling, and ASS rendering."""

    def __init__(
        self,
        style_key: str = "classic",
        length_mode: str = "medium",
        language: str = "auto",
        style_overrides: Optional[Dict[str, Any]] = None,
        platform_preset: Optional[str] = None,
        stt_provider: str = "auto",
        deepgram_api_key: Optional[str] = None,
        deepgram_model: str = "nova-3",
        ai_mode: str = "raw",
        creative_rewrite: bool = False,
        llm_provider: str = "auto",
        llm_model: Optional[str] = None
    ):
        self.style_key = style_key
        self.length_mode = length_mode
        self.language = language
        self.style_overrides = style_overrides or {}
        self.platform_preset = platform_preset
        self.stt_provider = stt_provider
        self.deepgram_api_key = deepgram_api_key
        self.deepgram_model = deepgram_model
        self.ai_mode = ai_mode
        self.creative_rewrite = creative_rewrite
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.metadata: Dict[str, Any] = {
            "style": style_key,
            "stt_provider": stt_provider,
            "llm_provider": llm_provider,
            "llm_model": llm_model or "auto",
            "ai_mode": ai_mode
        }

    def prepare_captions(
        self,
        audio_path: Path,
        transcript_path: Optional[Path] = None,
        force_retranscribe: bool = False
    ) -> CaptionModel:
        """
        Execute full caption preparation:
          1. Speech Recognition (Deepgram Nova-3 / Whisper / Transcript fallback)
          2. Optional AI Caption Intelligence (Clean / Viral Rewrite)
          3. Caption Text Alignment to preserve source audio word timing
          4. Semantic Emphasis Annotation
          5. Sentence- and silence-aware pagination
        """
        # 1. Authoritative Speech Recognition
        raw_model, used_stt = transcribe_with_fallback(
            audio_path=audio_path,
            transcript_path=transcript_path,
            preferred_provider=self.stt_provider,
            language=self.language,
            deepgram_api_key=self.deepgram_api_key,
            deepgram_model=self.deepgram_model,
            force_retranscribe=force_retranscribe
        )
        self.metadata["stt_provider"] = used_stt

        # 2. Optional AI Caption Intelligence
        working_model = raw_model
        if self.ai_mode in ["clean", "viral"]:
            logger.info(f"[CAPTION AI] Running mode '{self.ai_mode}' via provider '{self.llm_provider}'...")
            segments_payload = [
                {"id": s.id, "text": s.text}
                for s in raw_model.segments
            ]
            ai_segments, used_llm, llm_meta = execute_llm_intelligence_with_fallback(
                mode=self.ai_mode,
                segments=segments_payload,
                preferred_provider=self.llm_provider,
                language=self.language,
                creative_rewrite=self.creative_rewrite,
                model=self.llm_model
            )
            self.metadata["llm_provider"] = used_llm
            self.metadata["llm_meta"] = llm_meta

            # 3. Dynamic Alignment: Map edited/shortened AI text to authoritative source word timestamps
            logger.info("[CAPTION ALIGN] Aligning rewritten text to source word timestamps...")
            working_model = CaptionTextAligner.align_model(
                source_model=raw_model,
                modified_segments_text=ai_segments
            )

        # 4. Paginate into sentence-aware & silence-aware caption pages
        paginated_model = paginate_captions(
            model=working_model,
            length_mode=self.length_mode
        )

        # 5. Semantic Emphasis Annotation
        for seg in paginated_model.segments:
            emp_tokens = CaptionEmphasisEngine.identify_emphasis_tokens(
                text=seg.text,
                language=self.language
            )
            # Store identified emphasis tokens on segment
            seg.words = seg.words

        # 6. Validate
        is_valid, errors = paginated_model.validate()
        if not is_valid:
            logger.warning(f"Caption validation warnings: {errors[:3]}")

        return paginated_model

    def generate_ass_for_render(
        self,
        model: CaptionModel,
        output_ass_path: Path,
        time_offset_s: float = 0.0,
        video_width: int = 1920,
        video_height: int = 1080,
        duration_s: Optional[float] = None
    ) -> Path:
        """Generate ASS script ready for FFmpeg libass filter."""
        output_ass_path = Path(output_ass_path)
        output_ass_path.parent.mkdir(parents=True, exist_ok=True)

        effective_style = self.style_key
        if effective_style == "auto":
            effective_style = resolve_auto_style()

        ass_text = build_ass_script(
            model=model,
            style_key=effective_style,
            style_overrides=self.style_overrides,
            video_width=video_width,
            video_height=video_height,
            time_offset_s=time_offset_s,
            duration_s=duration_s
        )

        with open(output_ass_path, "w", encoding="utf-8") as f:
            f.write(ass_text)

        return output_ass_path

    def export_all(
        self,
        model: CaptionModel,
        base_path: Path,
        video_width: int = 1920,
        video_height: int = 1080
    ) -> Dict[str, str]:
        """
        Export final.srt, final.ass, final.vtt, and captions.json alongside video.
        """
        effective_style = self.style_key
        if effective_style == "auto":
            effective_style = resolve_auto_style()

        exports = export_all_caption_formats(
            model=model,
            base_output_path=base_path,
            style_key=effective_style,
            style_overrides=self.style_overrides,
            metadata=self.metadata,
            video_width=video_width,
            video_height=video_height
        )

        return {k: str(v) for k, v in exports.items()}

    def verify_qc(self, video_path: Path, model: CaptionModel) -> Dict[str, Any]:
        """Run caption Quality Control and return diagnostic report."""
        return run_full_caption_qc(video_path, model, self.style_key, style_overrides=self.style_overrides)


def get_available_caption_styles() -> List[Dict[str, Any]]:
    """Return catalog of available styles for UI rendering."""
    catalog = []
    for k, s in CAPTION_STYLES.items():
        catalog.append({
            "id": k,
            "name": s["name"],
            "category": s.get("category", "documentary"),
            "description": s["description"],
            "font": s["font"],
            "font_size": s["font_size"],
            "primary_color": s["primary_color"],
            "highlight_color": s["highlight_color"],
            "word_highlight": s["word_highlight"],
            "animation": s["animation"],
            "badge": s.get("badge", ""),
            "preview_sample": {
                "inactive": "Every great empire begins with a",
                "active": "VISION",
                "trailing": "and determination."
            }
        })
    return catalog


def get_caption_style_categories() -> List[Dict[str, Any]]:
    """Return category list for UI style filtering."""
    return STYLE_CATEGORIES
