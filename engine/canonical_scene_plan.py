"""
canonical_scene_plan.py — Authoritative Semantic Scene Plan & Storyboard Model
================================================================================
RenderFlow v2.5.1 Single Source of Truth for timeline scene decisions, semantic intent,
timing confidence, candidate asset scoring, and transition definitions.

Fully compatible with existing RenderFlow plan.json schemas while adding robust
semantic attributes, word-level audio alignment references, and deterministic validation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("rendering_studio.canonical_scene_plan")


@dataclass
class WordAlignmentRef:
    """Word-level alignment timestamp reference."""
    word: str
    start: float
    end: float
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "start": round(float(self.start), 3),
            "end": round(float(self.end), 3),
            "confidence": round(float(self.confidence), 3),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WordAlignmentRef:
        return cls(
            word=str(data.get("word", "")),
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
            confidence=float(data.get("confidence", 1.0)),
        )


@dataclass
class CandidateAssetScore:
    """Scoring and rationale for a candidate asset considered for a scene."""
    asset_id: str
    filename: str
    source: str = "local"  # "local", "openmontage", "pexels", "wikimedia", "nasa", etc.
    total_score: float = 0.0
    raw_semantic_score: float = 0.0
    penalty: float = 0.0
    reasons: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
    thumbnail_url: str = ""
    source_url: str = ""
    license: str = ""
    creator: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "filename": self.filename,
            "source": self.source,
            "total_score": round(float(self.total_score), 4),
            "raw_semantic_score": round(float(self.raw_semantic_score), 4),
            "penalty": round(float(self.penalty), 4),
            "reasons": list(self.reasons),
            "rejection_reasons": list(self.rejection_reasons),
            "thumbnail_url": self.thumbnail_url,
            "source_url": self.source_url,
            "license": self.license,
            "creator": self.creator,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CandidateAssetScore:
        return cls(
            asset_id=str(data.get("asset_id", data.get("image_id", ""))),
            filename=str(data.get("filename", data.get("image", ""))),
            source=str(data.get("source", "local")),
            total_score=float(data.get("total_score", data.get("score", 0.0))),
            raw_semantic_score=float(data.get("raw_semantic_score", data.get("raw_score", 0.0))),
            penalty=float(data.get("penalty", 0.0)),
            reasons=list(data.get("reasons", [])),
            rejection_reasons=list(data.get("rejection_reasons", [])),
            thumbnail_url=str(data.get("thumbnail_url", "")),
            source_url=str(data.get("source_url", "")),
            license=str(data.get("license", "")),
            creator=str(data.get("creator", "")),
        )


@dataclass
class CanonicalScene:
    """
    Authoritative single scene representation in the RenderFlow timeline.
    Guarantees strict narrative continuity, timebase consistency, and
    backward compatibility with legacy plan.json structure.
    """
    scene_id: str
    sequence_index: int
    start: float
    end: float
    dur: float
    transcript_text: str = ""
    word_timestamps: List[WordAlignmentRef] = field(default_factory=list)
    transcript_start: float = 0.0
    transcript_end: float = 0.0

    # Semantic & Visual Intent
    semantic_summary: str = ""
    visual_intent: str = ""
    main_subjects: List[str] = field(default_factory=list)
    required_objects: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    setting: str = "general"
    mood: str = "neutral"
    suggested_shot_type: str = "medium_shot"
    search_queries: List[str] = field(default_factory=list)

    # Asset Assignment & Matching
    candidate_asset_ids: List[str] = field(default_factory=list)
    candidate_scores: List[CandidateAssetScore] = field(default_factory=list)
    selected_asset_id: str = ""
    selected_image: str = ""  # filename or relative path
    asset_source: str = "local"  # "local", "openmontage", "stock", "generated"
    asset_source_url: str = ""
    asset_license: str = ""
    asset_attribution: str = ""
    selection_rationale: str = ""

    # Confidence & Validation
    timing_confidence: float = 1.0
    semantic_confidence: float = 0.75
    confidence_level: str = "HIGH"  # "HIGH", "MEDIUM", "LOW", "NO_MATCH", "UNRESOLVED"
    validation_state: str = "VALID"  # "VALID", "INVALID", "NEEDS_REVIEW"
    user_override: bool = False
    locked: bool = False
    manual_review_needed: bool = False
    no_match_warning: bool = False

    # Transitions & Effects (paritized between preview and export)
    transition: str = "cinematic_dissolve"
    transition_dur: float = 0.40
    transition_sfx: bool = False
    context: str = "normal"
    motion: str = "L4/push"
    motion_mode: str = "push"
    shot_role: str = "narrative_inspection"
    easing: str = "smoothstep"
    zoom_scale: float = 1.03
    pan_speed: float = 0.0
    motion_rationale: str = "automatic_cinematic"

    def __post_init__(self):
        # Enforce consistency: dur = end - start
        if self.dur <= 0.0 and self.end > self.start:
            self.dur = round(self.end - self.start, 3)

    @property
    def is_resolved(self) -> bool:
        """True if the scene has a valid visual asset and is not unmatchable."""
        return bool(self.selected_image) and self.confidence_level != "NO_MATCH"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary, preserving full compatibility with legacy plan.json."""
        return {
            # Legacy fields expected by frontend, fast_pipeline, and existing tests
            "scene_id": self.scene_id,
            "segment_index": self.sequence_index,
            "start": round(float(self.start), 3),
            "end": round(float(self.end), 3),
            "dur": round(float(self.dur), 3),
            "image": self.selected_image,
            "image_id": self.selected_asset_id or f"img_{self.sequence_index+1:03d}",
            "transition": self.transition,
            "transition_dur": round(float(self.transition_dur), 3),
            "transition_sfx": self.transition_sfx,
            "context": self.context,
            "motion": self.motion,
            "motion_mode": self.motion_mode,
            "shot_role": self.shot_role,
            "easing": self.easing,
            "zoom_scale": round(float(self.zoom_scale), 3),
            "pan_speed": round(float(self.pan_speed), 3),
            "motion_rationale": self.motion_rationale,
            "user_override": self.user_override,
            "locked": self.locked,
            "manual_review_needed": self.manual_review_needed or (self.confidence_level in ("NO_MATCH", "LOW", "UNRESOLVED")),
            "no_match_warning": self.no_match_warning or (self.confidence_level == "NO_MATCH"),
            "confidence": round(float(self.semantic_confidence), 3),
            "confidence_level": self.confidence_level,
            "timing_confidence": round(float(self.timing_confidence), 3),

            # Enriched v2.5.1 canonical fields
            "transcript_text": self.transcript_text,
            "word_timestamps": [w.to_dict() for w in self.word_timestamps],
            "transcript_start": round(float(self.transcript_start), 3),
            "transcript_end": round(float(self.transcript_end), 3),
            "semantic_summary": self.semantic_summary,
            "visual_intent": self.visual_intent,
            "main_subjects": list(self.main_subjects),
            "required_objects": list(self.required_objects),
            "actions": list(self.actions),
            "setting": self.setting,
            "mood": self.mood,
            "suggested_shot_type": self.suggested_shot_type,
            "search_queries": list(self.search_queries),
            "candidate_asset_ids": list(self.candidate_asset_ids),
            "candidate_scores": [c.to_dict() for c in self.candidate_scores],
            "selected_asset_id": self.selected_asset_id,
            "asset_source": self.asset_source,
            "asset_source_url": self.asset_source_url,
            "asset_license": self.asset_license,
            "asset_attribution": self.asset_attribution,
            "selection_rationale": self.selection_rationale,
            "validation_state": self.validation_state,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], default_index: int = 0) -> CanonicalScene:
        """Parse from legacy or enriched scene dictionary."""
        seq_idx = int(data.get("segment_index", data.get("sequence_index", default_index)))
        start_t = float(data.get("start", 0.0))
        end_t = float(data.get("end", start_t + 3.0))
        dur_t = float(data.get("dur", max(0.01, end_t - start_t)))

        words = []
        for w in data.get("word_timestamps", []):
            if isinstance(w, dict):
                words.append(WordAlignmentRef.from_dict(w))

        cands = []
        for c in data.get("candidate_scores", []):
            if isinstance(c, dict):
                cands.append(CandidateAssetScore.from_dict(c))

        selected_img = str(data.get("image", data.get("selected_image", "")))
        selected_id = str(data.get("selected_asset_id", data.get("image_id", "")))

        return cls(
            scene_id=str(data.get("scene_id", f"scene_{seq_idx+1:04d}")),
            sequence_index=seq_idx,
            start=start_t,
            end=end_t,
            dur=dur_t,
            transcript_text=str(data.get("transcript_text", data.get("text", ""))),
            word_timestamps=words,
            transcript_start=float(data.get("transcript_start", start_t)),
            transcript_end=float(data.get("transcript_end", end_t)),
            semantic_summary=str(data.get("semantic_summary", "")),
            visual_intent=str(data.get("visual_intent", "")),
            main_subjects=list(data.get("main_subjects", [])),
            required_objects=list(data.get("required_objects", [])),
            actions=list(data.get("actions", [])),
            setting=str(data.get("setting", "general")),
            mood=str(data.get("mood", "neutral")),
            suggested_shot_type=str(data.get("suggested_shot_type", "medium_shot")),
            search_queries=list(data.get("search_queries", [])),
            candidate_asset_ids=list(data.get("candidate_asset_ids", [])),
            candidate_scores=cands,
            selected_asset_id=selected_id,
            selected_image=selected_img,
            asset_source=str(data.get("asset_source", "local")),
            asset_source_url=str(data.get("asset_source_url", "")),
            asset_license=str(data.get("asset_license", "")),
            asset_attribution=str(data.get("asset_attribution", "")),
            selection_rationale=str(data.get("selection_rationale", data.get("match_reason", ""))),
            timing_confidence=float(data.get("timing_confidence", 1.0)),
            semantic_confidence=float(data.get("confidence", data.get("semantic_confidence", 0.75))),
            confidence_level=str(data.get("confidence_level", "HIGH")),
            validation_state=str(data.get("validation_state", "VALID")),
            user_override=bool(data.get("user_override", False)),
            locked=bool(data.get("locked", False)),
            manual_review_needed=bool(data.get("manual_review_needed", False)),
            no_match_warning=bool(data.get("no_match_warning", False)),
            transition=str(data.get("transition", "cinematic_dissolve")),
            transition_dur=float(data.get("transition_dur", 0.40)),
            transition_sfx=bool(data.get("transition_sfx", False)),
            context=str(data.get("context", "normal")),
            motion=str(data.get("motion", "L4/push")),
            motion_mode=str(data.get("motion_mode", "push")),
            shot_role=str(data.get("shot_role", "narrative_inspection")),
            easing=str(data.get("easing", "smoothstep")),
            zoom_scale=float(data.get("zoom_scale", 1.03)),
            pan_speed=float(data.get("pan_speed", 0.0)),
            motion_rationale=str(data.get("motion_rationale", "automatic_cinematic")),
        )


@dataclass
class CanonicalStoryboardPlan:
    """
    Authoritative container for an entire RenderFlow video project timeline plan.
    """
    project_id: str
    total_duration: float
    scenes: List[CanonicalScene] = field(default_factory=list)
    resolution: str = "1080p"
    aspect_ratio: str = "16:9"
    fps: int = 30
    caption_preset: str = "hormozi"
    audio_path: Optional[str] = None
    transcript_path: Optional[str] = None
    sync_report: Dict[str, Any] = field(default_factory=dict)
    unresolved_scenes_count: int = 0
    version: str = "2.5.1"

    def to_dict(self) -> Dict[str, Any]:
        """Convert complete storyboard plan to dictionary format for plan.json."""
        unresolved = sum(1 for s in self.scenes if not s.is_resolved)
        return {
            "version": self.version,
            "project_id": self.project_id,
            "total_duration": round(float(self.total_duration), 3),
            "resolution": self.resolution,
            "aspect_ratio": self.aspect_ratio,
            "fps": self.fps,
            "caption_preset": self.caption_preset,
            "audio_path": self.audio_path,
            "transcript_path": self.transcript_path,
            "unresolved_scenes_count": unresolved,
            "scenes": [s.to_dict() for s in self.scenes],
            "sync_report": self.sync_report,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], project_id: str = "default_project") -> CanonicalStoryboardPlan:
        """Parse from dictionary (handles both legacy and canonical structure)."""
        raw_scenes = data.get("scenes", []) if isinstance(data, dict) else data
        scenes = []
        for i, s_data in enumerate(raw_scenes):
            if isinstance(s_data, dict):
                scenes.append(CanonicalScene.from_dict(s_data, default_index=i))

        tot_dur = float(data.get("total_duration", scenes[-1].end if scenes else 0.0))
        return cls(
            project_id=str(data.get("project_id", project_id)),
            total_duration=tot_dur,
            scenes=scenes,
            resolution=str(data.get("resolution", "1080p")),
            aspect_ratio=str(data.get("aspect_ratio", "16:9")),
            fps=int(data.get("fps", 30)),
            caption_preset=str(data.get("caption_preset", "hormozi")),
            audio_path=data.get("audio_path"),
            transcript_path=data.get("transcript_path"),
            sync_report=data.get("sync_report", {}),
            unresolved_scenes_count=int(data.get("unresolved_scenes_count", 0)),
            version=str(data.get("version", "2.5.1")),
        )

    def save_json(self, path: Union[str, Path]):
        """Atomic write to plan.json."""
        p = Path(path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        tmp.replace(p)

    @classmethod
    def load_json(cls, path: Union[str, Path], project_id: Optional[str] = None) -> CanonicalStoryboardPlan:
        """Load plan from plan.json."""
        p = Path(path).resolve()
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data, project_id=project_id or p.parent.name)
