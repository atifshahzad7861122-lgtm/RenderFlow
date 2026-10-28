#!/usr/bin/env python3
"""
engine/sync_engine_v3.py — AI Image Sync Engine v3 (Phase 3 Production Intelligence)
Rendering Studio Engine v2

Architecture:
  Audio (Master Timeline)
    ↓
  Speech / Transcript & Word Timestamps
    ↓
  Semantic Beat Engine (Meaningful visual units 1.5s - 7.5s)
    ↓
  Visual Requirement Engine (Structured entity/action/object/scene extraction)
    ↓
  Image Intelligence Index (SHA-256 caching, metadata, OCR, semantic embeddings)
    ↓
  Candidate Retrieval (Adaptive Two-Stage Retrieval for 500+ images)
    ↓
  Content-Aware Multi-Signal Ranking (Adaptive profiles: Documentary, Tutorial, etc.)
    ↓
  Visual Arc (Chapter-level context) & Temporal Context (Memory window)
    ↓
  Visual Continuity Engine (CONTINUATION vs SEMANTIC SHIFT) & Smart Reuse
    ↓
  User Correction Memory & Project-Level Learning (Supporting bias)
    ↓
  Ambiguity AI Reranker (Invoked ONLY when ambiguity delta < 0.08)
    ↓
  Confidence Calibration v2 (Strictly empirical HIGH/MEDIUM/LOW + Uncertainty Awareness)
    ↓
  Sync QA & Auditable Decision Trace
    ↓
  Deterministic Timeline & Scene Plan (Preserving user overrides)
    ↓
  Existing Cinematic Renderer
"""

import os
import re
import sys
import json
import time
import math
import hashlib
import logging
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set

from PIL import Image
import numpy as np

try:
    from engine.timeline_normalizer import TimelineNormalizer
except (ModuleNotFoundError, ImportError):
    try:
        from timeline_normalizer import TimelineNormalizer
    except (ModuleNotFoundError, ImportError):
        from .timeline_normalizer import TimelineNormalizer

try:
    from engine.llm_provider import get_llm_provider, LLMProvider
except (ModuleNotFoundError, ImportError):
    try:
        from llm_provider import get_llm_provider, LLMProvider
    except (ModuleNotFoundError, ImportError):
        get_llm_provider = None
        LLMProvider = None

try:
    from engine.visual_analyzer import VisualContentAnalyzer, VisualAnalysisResult
except (ModuleNotFoundError, ImportError):
    try:
        from visual_analyzer import VisualContentAnalyzer, VisualAnalysisResult
    except (ModuleNotFoundError, ImportError):
        from .visual_analyzer import VisualContentAnalyzer, VisualAnalysisResult

# Phase 3 Intelligence Imports (§4-§28)
try:
    from engine.sync_v3_intelligence import (
        SyncProfile, MappingMode, GlobalSequenceOptimizer, PROFILE_WEIGHTS, ContentClassifier,
        UserCorrectionRecord, ProjectCorrectionMemory,
        TrackedEntity, EntityTracker,
        TransitionType, VisualContinuityEngine,
        VisualChapter, VisualArcManager,
        VisualDiversityEngine, ImageClusterManager,
        TwoStageRetriever,
        EmbeddingModelMetadata, CacheKeyGenerator,
        CandidateDecisionTrace, ConfidenceCalibratorV2
    )
except (ModuleNotFoundError, ImportError):
    try:
        from sync_v3_intelligence import (
            SyncProfile, MappingMode, GlobalSequenceOptimizer, PROFILE_WEIGHTS, ContentClassifier,
            UserCorrectionRecord, ProjectCorrectionMemory,
            TrackedEntity, EntityTracker,
            TransitionType, VisualContinuityEngine,
            VisualChapter, VisualArcManager,
            VisualDiversityEngine, ImageClusterManager,
            TwoStageRetriever,
            EmbeddingModelMetadata, CacheKeyGenerator,
            CandidateDecisionTrace, ConfidenceCalibratorV2
        )
    except (ModuleNotFoundError, ImportError):
        from .sync_v3_intelligence import (
            SyncProfile, MappingMode, GlobalSequenceOptimizer, PROFILE_WEIGHTS, ContentClassifier,
            UserCorrectionRecord, ProjectCorrectionMemory,
            TrackedEntity, EntityTracker,
            TransitionType, VisualContinuityEngine,
            VisualChapter, VisualArcManager,
            VisualDiversityEngine, ImageClusterManager,
            TwoStageRetriever,
            EmbeddingModelMetadata, CacheKeyGenerator,
            CandidateDecisionTrace, ConfidenceCalibratorV2
        )

logger = logging.getLogger("rendering_studio.sync_v3")

# Central Cache Directories
CACHE_ROOT = Path(__file__).resolve().parent.parent / ".cache" / "image_sync_v3"
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
INDEX_CACHE_FILE = CACHE_ROOT / "intel_index_cache.json"

# ==============================================================================
# 1. CONFIGURATION & WEIGHTS (§12, §18, Phase 3 §4, §28, §40)
# ==============================================================================

@dataclass
class SyncConfig:
    """Centralized configurable weights, thresholds, profiles, and boundaries."""
    # Multi-Signal Weights (Must sum to 1.0)
    w_semantic_text: float = 0.30       # Text & visual concept semantic match
    w_visual_embedding: float = 0.20    # Vector space cosine similarity
    w_entity_match: float = 0.15        # Subject / named entity / object overlap
    w_action_match: float = 0.10        # Action / verb overlap
    w_scene_location: float = 0.10      # Environment & location context
    w_temporal_context: float = 0.10    # Continuity with adjacent scenes
    w_sequence_meta: float = 0.05       # Natural file ordering / narrative progress

    # Confidence Thresholds (§18)
    high_confidence_thresh: float = 0.85
    medium_confidence_thresh: float = 0.65

    # AI Reranker Trigger Boundaries (§16, §25)
    rerank_ambiguity_delta: float = 0.08 # Trigger if top-1 and top-2 are within 8%
    rerank_score_range: Tuple[float, float] = (0.50, 0.85) # Trigger only if top < 0.85

    # Visual Hold Limits (§21)
    min_visual_hold: float = 1.5   # Minimum seconds before an image cut
    max_visual_hold: float = 7.5   # Maximum recommended hold without visual beat

    # Repetition Penalty (§13, Phase 3 Smart Reuse §18)
    repetition_decay: float = 0.35      # Immediate previous scene repetition penalty
    repetition_window: int = 4          # Number of previous beats checked for reuse

    # Phase 3 Adaptive Profile & Mode Controls (§4, §40)
    profile_name: str = "GENERAL"       # DOCUMENTARY, STORYTELLING, TUTORIAL, etc.
    sync_mode: str = "BALANCED"         # FAST, BALANCED, HIGH_ACCURACY
    enable_project_learning: bool = True
    enable_entity_tracking: bool = True
    enable_visual_arc: bool = True
    enable_two_stage_retrieval: bool = True
    project_dir: Optional[Path] = None

    # Phase 2 Audio Cadence & Rhythm Controls (§3)
    enable_cadence_alignment: bool = True
    cadence_tolerance_sec: float = 0.180 # Snapping tolerance window (±180ms)
    pacing_bias: float = 1.0            # 0.5x (slow documentary) to 2.0x (fast montage)

    # Phase 3 B-Roll Video Indexing Controls (§3)
    enable_broll_indexing: bool = False
    broll_directory: Optional[Union[str, Path]] = None
    broll_sample_fps: float = 5.0
    broll_threshold: float = 0.38
    broll_min_shot_duration: float = 0.8

    # Transitions Context Mapping (§21 - Intelligent Cinematic Mapping)
    context_transitions: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        'normal':          {'xfade': 'fade',       'dur': 0.35, 'label': 'cinematic_dissolve'},
        'location_change': {'xfade': 'wipeleft',   'dur': 0.35, 'label': 'soft_wipe'},
        'story_change':    {'xfade': 'dissolve',   'dur': 0.80, 'label': 'transition_003'},
        'turning_point':   {'xfade': 'dissolve',   'dur': 0.80, 'label': 'transition_001'},
        'emotional':       {'xfade': 'dissolve',   'dur': 0.50, 'label': 'slow_dissolve'},
        'time_passage':    {'xfade': 'fadeblack',  'dur': 0.80, 'label': 'transition_017'},
        'fast':            {'xfade': 'fadefast',   'dur': 0.50, 'label': 'transition_002'},
    })

    def __post_init__(self):
        """Apply content-aware profile weights if profile_name is recognized (§4)."""
        if self.profile_name and self.profile_name.upper() in PROFILE_WEIGHTS:
            pw = PROFILE_WEIGHTS[self.profile_name.upper()]
            self.w_semantic_text = pw["w_semantic_text"]
            self.w_visual_embedding = pw["w_visual_embedding"]
            self.w_entity_match = pw["w_entity_match"]
            self.w_action_match = pw["w_action_match"]
            self.w_scene_location = pw["w_scene_location"]
            self.w_temporal_context = pw["w_temporal_context"]
            self.w_sequence_meta = pw["w_sequence_meta"]


# Keywords for lexical-semantic grounding
STOPWORDS: Set[str] = {
    'the', 'and', 'for', 'that', 'this', 'with', 'from', 'have', 'were', 'which',
    'then', 'they', 'their', 'been', 'what', 'when', 'will', 'more', 'about', 'into',
    'some', 'them', 'than', 'also', 'upon', 'over', 'scene', 'image', 'picture', 'photo',
    'video', 'clip', 'frame', 'shot', 'screen', 'view', 'look', 'make', 'just', 'like'
}

LOCATION_KEYWORDS: Set[str] = {
    'where', 'here', 'there', 'city', 'country', 'town', 'river', 'mountain', 'palace',
    'castle', 'empire', 'rome', 'paris', 'london', 'world', 'land', 'sea', 'ocean',
    'location', 'travel', 'arrived', 'went', 'entered', 'borders', 'territory', 'capital',
    'valley', 'forest', 'island', 'desert', 'kingdom', 'province', 'station', 'office',
    'bedroom', 'room', 'street', 'building', 'market', 'studio', 'headquarters', 'workspace',
    'campus', 'factory', 'warehouse', 'garage', 'interior', 'exterior', 'infrastructure',
    'datacenter', 'hospital', 'clinic', 'beach', 'classroom', 'school', 'harbor', 'highway',
    'track', 'kitchen', 'restaurant', 'store', 'shop', 'hall', 'terminal', 'airport',
    # Multilingual (Urdu, Arabic, Hindi)
    'دفتر', 'ہسپتال', 'کلاس', 'کمرہ', 'ساحل', 'مكتب', 'مستشفى', 'فصل', 'مطار', 'شاطئ', 'कार्यालय', 'अस्पताल', 'कक्षा'
}

ACTION_KEYWORDS: Set[str] = {
    'working', 'work', 'started', 'built', 'building', 'fighting', 'fight', 'attacked',
    'created', 'lost', 'losing', 'giving', 'running', 'moving', 'coding', 'designed',
    'developed', 'founded', 'grew', 'launched', 'sold', 'bought', 'spoke', 'invested',
    'traveling', 'searching', 'walking', 'struggled', 'won', 'defeated', 'expanded',
    'typing', 'sitting', 'speaking', 'chopping', 'baking', 'swimming', 'cycling',
    'jumping', 'repairing', 'steering', 'marching', 'saluting', 'measuring', 'studying', 'reading',
    # Multilingual (Urdu, Arabic, Hindi)
    'کام', 'پڑھایا', 'چل', 'دوڑ', 'بول', 'پکا', 'يعمل', 'يفحص', 'تقلع', 'يمشي', 'يجري', 'يتكلم', 'दौड़', 'पढ़ा'
}

ENTITY_CONCEPTS: Set[str] = {
    'person', 'man', 'woman', 'founder', 'ceo', 'entrepreneur', 'soldier', 'warrior',
    'engineer', 'coder', 'developer', 'worker', 'team', 'company', 'startup', 'business',
    'laptop', 'computer', 'server', 'phone', 'desk', 'chart', 'money', 'code', 'book',
    'car', 'ship', 'plane', 'document', 'screen', 'cloud', 'aws', 'amazon', 'google',
    'microsoft', 'apple', 'office', 'house', 'empire', 'army', 'king', 'leader',
    'doctor', 'patient', 'teacher', 'student', 'chef', 'musician', 'athlete', 'runner',
    'pilot', 'mechanic', 'driver', 'barista', 'firefighter', 'scientist', 'farmer',
    'architect', 'surgeon', 'nurse', 'waiter', 'baker', 'receptionist', 'trader', 'gamer',
    'macbook', 'surface', 'model3', 'falcon', 'dreamliner', 'rover', 'gpu', 'cpu', 'ferrari', 'porsche', 'starbucks', 'nike',
    # Multilingual (Urdu, Arabic, Hindi)
    'تاجر', 'ڈاکٹر', 'مریض', 'استاد', 'بچوں', 'باورچی', 'گاڑی', 'جہاز', 'طبیب', 'معلم', 'طالب', 'طاهي', 'سيارة', 'طائرة', 'व्यापारी', 'रोगी', 'शिक्षक', 'छात्र', 'विमान'
}

TURNING_KEYWORDS: Set[str] = {
    'suddenly', 'however', 'war', 'battle', 'attack', 'destroyed', 'crashed', 'broke',
    'victory', 'defeat', 'climax', 'crisis', 'shock', 'strike', 'rebellion', 'turning',
    'unexpected', 'danger', 'fate', 'moment', 'destiny', 'revolution', 'assassination',
    'confrontation', 'struggle', 'clash', 'disaster', 'explosion', 'downfall'
}

EMOTIONAL_KEYWORDS: Set[str] = {
    'sorrow', 'tragedy', 'love', 'grief', 'hope', 'peace', 'cried', 'loss', 'heart',
    'remember', 'memory', 'beautiful', 'sadness', 'despair', 'solemn', 'spirit', 'tears',
    'sacrifice', 'soul', 'passion', 'suffering', 'devotion', 'longing'
}

TIME_KEYWORDS: Set[str] = {
    'years', 'months', 'decades', 'centuries', 'later', 'meanwhile', 'eventually',
    'after', 'before', 'passed', 'dawn', 'night', 'era', 'generation', 'future', 'past',
    'ancient', 'modern', 'period', 'timeline', 'history', 'chronicle'
}


# ==============================================================================
# 2. DATA MODELS (§5, §6, §7, §14, §18, §26, §42, §51)
# ==============================================================================

@dataclass
class VisualRequirement:
    """Structured visual requirements extracted for a narration beat (§6)."""
    subject: str = ""
    entities: List[str] = field(default_factory=list)
    objects: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    environment: str = ""
    location: str = ""
    topic: str = "General Narration"
    visual_concepts: List[str] = field(default_factory=list)
    ocr_hints: List[str] = field(default_factory=list)
    abstract_concepts: List[str] = field(default_factory=list)
    expanded_prompts: List[str] = field(default_factory=list)


@dataclass
class SemanticBeat:
    """A meaningful visual unit on the master audio timeline (§5)."""
    beat_id: str
    segment_index: int
    start: float
    end: float
    dur: float
    text: str
    visual_req: VisualRequirement
    context: str = "normal"
    importance: float = 0.5
    is_silence: bool = False
    silence_dur: float = 0.0


@dataclass
class ImageIntelligence:
    """Comprehensive visual metadata and semantic intelligence for a source image (§7)."""
    image_id: str
    filename: str
    rel_path: str
    abs_path: str
    content_hash: str          # SHA-256 of file bytes
    width: int
    height: int
    aspect_ratio: float
    filesize_bytes: int
    filename_tokens: List[str] # 5% supporting signal only (§11)
    ocr_text: str              # OCR text if present (§10)
    ocr_tokens: List[str]
    caption: str               # Description / vision summary
    objects: List[str]
    entities: List[str]
    actions: List[str]
    scene: str
    environment: str
    visual_concepts: List[str]
    embedding: List[float] = field(default_factory=list)
    sequence_index: int = 0
    cluster: str = "general"   # Concept cluster (§19)
    dhash: str = ""            # Perceptual hash for near-duplicate detection
    is_near_duplicate: bool = False
    visual_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateScore:
    """Detailed multi-signal scoring audit for a candidate image on a beat (§12, §14, §40)."""
    image_id: str
    filename: str
    total_score: float
    raw_score: float
    penalty: float
    signals: Dict[str, float]
    reasons: List[str]


@dataclass
class ScenePlanItem:
    """Enriched visual scene plan output compatible with existing renderer (§26, §51)."""
    scene_id: str
    segment_index: int
    start: float
    end: float
    dur: float
    image: str
    image_id: str
    transition: str
    context: str
    confidence: float
    confidence_level: str      # HIGH, MEDIUM, LOW (§18, §28)
    match_reason: List[str]
    source: str                # ai_semantic, deterministic_semantic, user_override, sequence_fallback
    user_override: bool = False
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    narration_text: str = ""
    transition_type: str = "CONTINUATION"   # CONTINUATION or SEMANTIC_SHIFT (§12)
    chapter_index: int = 1                  # Visual Chapter (§14)
    decision_trace: Optional[Dict[str, Any]] = None  # Full auditable trace (§51)


@dataclass
class SyncQualityReport:
    """Auditable quality and confidence report (§42, §54)."""
    total_images: int = 0
    total_beats: int = 0
    high_confidence: int = 0
    medium_confidence: int = 0
    low_confidence: int = 0
    average_confidence: float = 0.0
    sync_quality_score: float = 0.0     # 0 - 100% transparent quality score (§30)
    profile_used: str = "GENERAL"       # Content profile applied (§4)
    sync_mode_used: str = "BALANCED"    # Mode applied (§40)
    repeated_images: int = 0
    semantic_conflicts: int = 0
    unmatched_beats: int = 0
    ai_reranking_triggered: int = 0
    ai_reranking_successful: int = 0
    fallback_used: int = 0
    project_corrections_learned: int = 0
    tracked_entities_count: int = 0
    chapters_count: int = 0
    duration_sec: float = 0.0
    timestamp: str = ""
    engine_version: str = "AI Image Sync Engine v3 (Phase 3 Production)"
    semantic_relevance: float = 0.0
    temporal_alignment: float = 0.0
    beat_coverage: float = 0.0
    context_continuity: float = 0.0
    image_confidence: float = 0.0
    cadence_aligned_cuts: int = 0
    cadence_adjustments_avg_ms: float = 0.0
    cadence_speech_pauses_count: int = 0
    cadence_music_beats_count: int = 0
    broll_videos_indexed: int = 0
    broll_shots_indexed: int = 0
    broll_catalog: Optional[Dict[str, Any]] = None
    score_breakdown: Optional[Dict[str, float]] = None


# ==============================================================================
# 3. DETERMINISTIC SEMANTIC VECTOR ENCODER (§4, §8, §33)
# ==============================================================================

class DeterministicSemanticEmbedding:
    """
    High-dimensional semantic vector encoder powered by local neural SemanticVisionModel
    (OpenCLIP ViT-B/32, 512-dim joint text-image embedding space) with deterministic offline fallback.
    Guarantees:
      - 100% offline, zero network dependency, CPU inference.
      - 512-dimensional L2-normalized vector space matching vision embeddings.
      - Deep semantic cross-modal understanding for literal and abstract narration.
    """

    DIM = 512

    @classmethod
    def encode(cls, text_or_tokens: Any) -> List[float]:
        """Encode text or token list into 512-dim L2-normalized float vector."""
        try:
            from engine.semantic_vision import SemanticVisionModel
            model = SemanticVisionModel()
            if isinstance(text_or_tokens, (list, tuple, set)):
                text = " ".join(str(t) for t in text_or_tokens)
            else:
                text = str(text_or_tokens)
            emb = model.encode_text(text)
            return [round(float(x), 6) for x in emb.tolist()]
        except Exception as e:
            logger.debug(f"Neural text encoding fallback: {e}")
            return cls._fallback_encode(text_or_tokens)

    @classmethod
    def _fallback_encode(cls, text_or_tokens: Any) -> List[float]:
        """Deterministic offline fallback vector projection (512-dim)."""
        if isinstance(text_or_tokens, str):
            tokens = [t.lower() for t in re.findall(r'[\w]{2,}', text_or_tokens, re.UNICODE)]
        else:
            tokens = [str(t).lower() for t in text_or_tokens]

        vec = [0.0] * cls.DIM
        if not tokens:
            return vec

        for tok in tokens:
            if tok in STOPWORDS:
                continue
            h1 = int(hashlib.md5(tok.encode('utf-8')).hexdigest(), 16)
            h2 = int(hashlib.sha1(tok.encode('utf-8')).hexdigest(), 16)

            idx1 = h1 % cls.DIM
            idx2 = h2 % cls.DIM
            sign1 = 1.0 if (h1 >> 8) & 1 else -1.0
            sign2 = 1.0 if (h2 >> 8) & 1 else -1.0

            weight = 1.0
            if tok in ENTITY_CONCEPTS:
                weight = 2.5
            elif tok in ACTION_KEYWORDS:
                weight = 2.0
            elif tok in LOCATION_KEYWORDS:
                weight = 1.8

            vec[idx1] += sign1 * weight
            vec[idx2] += sign2 * (weight * 0.7)

        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 1e-9:
            vec = [round(x / norm, 6) for x in vec]
        return vec

    @classmethod
    def cosine_similarity(cls, v1: List[float], v2: List[float]) -> float:
        """Compute cosine similarity mapped to [0.0, 1.0]."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        return max(0.0, min(1.0, dot))


# ==============================================================================
# 4. IMAGE INTELLIGENCE INDEXER & CACHING (§7, §8, §9, §10, §11, §23, §24)
# ==============================================================================

class ImageIntelligenceIndexer:
    """
    Extracts and caches multi-modal intelligence for all user-provided source images.
    Guarantees:
      - Content-hash-addressed cache (SHA-256) with model metadata versioning (§24).
      - Zero image hallucination or replacement: Only user images are cataloged.
      - Supporting filename intelligence (5% weight only; never overrides visual evidence).
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or CACHE_ROOT
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "image_intel_cache.json"
        self.meta = EmbeddingModelMetadata()
        self.visual_analyzer = VisualContentAnalyzer(self.cache_dir / "visual_pixel_cache.json")
        self._memory_cache: Dict[str, Dict[str, Any]] = self._load_disk_cache()

    def _load_disk_cache(self) -> Dict[str, Dict[str, Any]]:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read image cache: {e}")
        return {}

    def _save_disk_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._memory_cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save image cache: {e}")

    @staticmethod
    def compute_sha256(filepath: Path) -> str:
        """Compute SHA-256 hash of image file bytes for cache safety (§25)."""
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def extract_filename_tokens(filename: str) -> List[str]:
        """
        Extract meaningful semantic tokens from filename (§11).
        Supports kebab-case, snake_case, camelCase, numeric prefixes.
        """
        stem = Path(filename).stem
        # Split camelCase
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', stem)
        clean = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
        tokens = re.split(r'[_ \-\.\d]+', clean)
        generic_noise = {
            'scene', 'act', 'img', 'image', 'pic', 'picture', 'shot', 'v', 'ver',
            'version', 'final', 'test', 'untitled', 'render', 'frame', 'art', 'copy'
        }
        return [t for t in tokens if len(t) >= 2 and t not in generic_noise]

    @staticmethod
    def extract_ocr_text(filepath: Path) -> Tuple[str, List[str]]:
        """
        Extract visible text via OCR if practical (§10).
        Includes fallback to image metadata text blocks.
        """
        ocr_text = ""
        # 1. Try metadata / EXIF / PNG text chunks
        try:
            with Image.open(filepath) as img:
                info = getattr(img, 'info', {})
                for k, v in info.items():
                    if isinstance(v, str) and len(v.strip()) > 3:
                        ocr_text += " " + v.strip()
        except Exception:
            pass

        # 2. Check pytesseract if installed
        try:
            import pytesseract
            with Image.open(filepath) as img:
                detected = pytesseract.image_to_string(img)
                if detected and len(detected.strip()) > 2:
                    ocr_text += " " + detected.strip()
        except Exception:
            pass

        # Clean OCR tokens
        ocr_clean = ocr_text.strip()
        tokens = [t.lower() for t in re.findall(r'\b[a-zA-Z0-9]{3,}\b', ocr_clean) if t.lower() not in STOPWORDS]
        return ocr_clean, sorted(list(dict.fromkeys(tokens)))

    def index_image(self, filepath: Path, sequence_index: int = 0) -> ImageIntelligence:
        """Build or retrieve cached intelligence for a single image (§7, §24)."""
        abs_p = filepath.resolve()
        filename = filepath.name
        content_hash = self.compute_sha256(abs_p)

        # Versioned Cache Key (§24)
        v_key = CacheKeyGenerator.make_image_cache_key(content_hash, self.meta)

        # Check cache (strictly model-versioned to prevent stale intelligence §24, §26)
        if v_key in self._memory_cache:
            cached_dict = self._memory_cache[v_key]
            if cached_dict:
                data = dict(cached_dict)
                data["filename"] = filename
                data["rel_path"] = str(filepath)
                data["abs_path"] = str(abs_p)
                data["sequence_index"] = sequence_index
                return ImageIntelligence(**data)

        # Inspect Image via PIL
        try:
            with Image.open(abs_p) as im:
                w, h = im.size
                filesize = abs_p.stat().st_size
        except Exception as e:
            logger.error(f"Cannot open image {abs_p}: {e}")
            w, h, filesize = 1920, 1080, 0

        ar = round(float(w) / max(1, float(h)), 3)

        # 1. Filename Intelligence
        fn_tokens = self.extract_filename_tokens(filename)

        # 2. OCR Intelligence
        ocr_text, ocr_tokens = self.extract_ocr_text(abs_p)

        # 2b. Sidecar Metadata Intelligence (.json or .txt)
        sidecar_tags = []
        sidecar_caption = ""
        sidecar_json = abs_p.with_suffix('.json')
        sidecar_txt = abs_p.with_suffix('.txt')
        if sidecar_json.exists():
            try:
                with open(sidecar_json, 'r', encoding='utf-8') as f:
                    sc_data = json.load(f)
                if isinstance(sc_data, dict):
                    sidecar_caption = sc_data.get('caption', '') or sc_data.get('description', '')
                    raw_tags = sc_data.get('tags', []) or sc_data.get('concepts', []) or sc_data.get('keywords', [])
                    if isinstance(raw_tags, list):
                        sidecar_tags = [str(t).lower() for t in raw_tags]
            except Exception:
                pass
        elif sidecar_txt.exists():
            try:
                with open(sidecar_txt, 'r', encoding='utf-8') as f:
                    sidecar_caption = f.read().strip()
                    sidecar_tags = [t.lower() for t in re.findall(r'[\w]{2,}', sidecar_caption, re.UNICODE) if t.lower() not in STOPWORDS]
            except Exception:
                pass

        # 2c. Deep Visual Pixel Content Analysis (Phase 2 Master Upgrade)
        pixel_res: Optional[VisualAnalysisResult] = None
        try:
            pixel_res = self.visual_analyzer.analyze_image(abs_p)
        except Exception as p_err:
            logger.warning(f"Pixel analysis failed for {filename}: {p_err}")

        # 3. Structured Concepts derivation (Pixel visual evidence is primary)
        pixel_concepts = pixel_res.visual_concepts if pixel_res else []
        pixel_entities = pixel_res.entities if pixel_res else []
        pixel_actions = pixel_res.actions if pixel_res else []
        pixel_caption = pixel_res.caption if pixel_res else ""
        pixel_scene = pixel_res.scene_type if pixel_res else ""
        pixel_env = pixel_res.environment if pixel_res else ""
        pixel_dhash = pixel_res.dhash if pixel_res else ""

        # Visual concepts derived strictly from visual pixel evidence, OCR, and verified sidecars
        # Filename tokens must NEVER leak into visual concepts or visual captions (§1, §2, §6)
        visual_concepts = list(dict.fromkeys(pixel_concepts + list(ocr_tokens) + list(sidecar_tags)))
        concepts = visual_concepts
        entities = list(dict.fromkeys(pixel_entities + [c for c in visual_concepts if c in ENTITY_CONCEPTS]))
        actions = list(dict.fromkeys(pixel_actions + [c for c in visual_concepts if c in ACTION_KEYWORDS]))
        locations = [c for c in visual_concepts if c in LOCATION_KEYWORDS]

        scene = pixel_scene or (locations[0] if locations else "studio_interior")
        environment = pixel_env or ("workspace" if any(x in visual_concepts for x in ['office', 'desk', 'laptop', 'workspace']) else "general")

        caption_parts = [p for p in [pixel_caption, sidecar_caption, ' '.join(ocr_tokens)] if p.strip()]
        caption = " — ".join(caption_parts).strip()
        if not caption:
            caption = f"Visual source image {filename}"

        # 4. Semantic Embedding (Pixel-derived embedding takes priority)
        if pixel_res and pixel_res.embedding:
            embedding = pixel_res.embedding
        else:
            embedding_source = f"{caption} {' '.join(entities)} {' '.join(actions)} {' '.join(locations)}"
            embedding = DeterministicSemanticEmbedding.encode(embedding_source)

        # 5. Semantic Concept Cluster (§19)
        cluster = ImageClusterManager.assign_cluster(concepts)

        intel = ImageIntelligence(
            image_id=f"img_{sequence_index+1:03d}",
            filename=filename,
            rel_path=str(filepath),
            abs_path=str(abs_p),
            content_hash=content_hash,
            width=w,
            height=h,
            aspect_ratio=ar,
            filesize_bytes=filesize,
            filename_tokens=fn_tokens,
            ocr_text=ocr_text,
            ocr_tokens=ocr_tokens,
            caption=caption,
            objects=list(dict.fromkeys(concepts))[:8],
            entities=entities,
            actions=actions,
            scene=scene,
            environment=environment,
            visual_concepts=list(dict.fromkeys(concepts)),
            embedding=embedding,
            sequence_index=sequence_index,
            cluster=cluster,
            dhash=pixel_dhash,
            is_near_duplicate=False,
            visual_details=pixel_res.to_dict() if pixel_res else {}
        )

        # Save to memory and disk cache with both versioned key and content hash
        self._memory_cache[v_key] = asdict(intel)
        self._memory_cache[content_hash] = asdict(intel)
        self._save_disk_cache()
        return intel

    def index_image_directory(self, images_dir: Path, image_filenames: Optional[List[str]] = None) -> List[ImageIntelligence]:
        """Index all images in target directory with natural sorting and duplicate detection."""
        if image_filenames:
            valid_files = [images_dir / f for f in image_filenames if (images_dir / f).exists()]
        else:
            valid_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}
            valid_files = [p for p in images_dir.iterdir() if p.suffix.lower() in valid_exts]

        # Natural alphanumeric sorting
        def _nat_key(path: Path):
            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', path.name)]

        valid_files.sort(key=_nat_key)
        results = []
        seen_hashes = {}
        for idx, p in enumerate(valid_files):
            intel = self.index_image(p, sequence_index=idx)
            if intel.dhash:
                for prev_h, prev_fn in seen_hashes.items():
                    if VisualContentAnalyzer.is_near_duplicate(intel.dhash, prev_h, threshold=4):
                        intel.is_near_duplicate = True
                        break
                seen_hashes[intel.dhash] = intel.filename
            results.append(intel)
        return results


# ==============================================================================
# 5. SEMANTIC BEAT & VISUAL REQUIREMENT ENGINES (§5, §6)
# ==============================================================================

class SemanticBeatEngine:
    """
    Transforms narration audio and transcript segments into meaningful visual beats.
    Guarantees:
      - Master duration strictly aligns with narration audio duration (§4).
      - Continuous image holds across silences without visual flickering (§21, §22).
      - Structured visual requirements extracted for every beat (§6).
    """

    def __init__(self, config: Optional[SyncConfig] = None):
        self.config = config or SyncConfig()

    @staticmethod
    def extract_visual_requirements(text: str) -> VisualRequirement:
        """
        Extract structured entities, objects, actions, environment, and concepts (§6).
        Integrates SemanticSceneAnalyzer to support literal subjects as well as abstract/metaphorical concepts.
        Does NOT fabricate imaginary physical objects from abstract emotions.
        """
        words = [w.lower() for w in re.findall(r'[\w]{2,}', text, re.UNICODE)]
        clean_words = [w for w in words if w not in STOPWORDS]

        entities = [w for w in clean_words if w in ENTITY_CONCEPTS]
        actions = [w for w in clean_words if w in ACTION_KEYWORDS]
        locations = [w for w in clean_words if w in LOCATION_KEYWORDS]

        # Extract deep semantic intelligence from SemanticSceneAnalyzer
        abstract_concepts = []
        expanded_prompts = []
        try:
            from engine.semantic_scene_analyzer import SemanticSceneAnalyzer
            scene_intel = SemanticSceneAnalyzer.analyze_script_segment(text)
            entities = list(dict.fromkeys(entities + scene_intel.entities))
            actions = list(dict.fromkeys(actions + scene_intel.actions))
            locations = list(dict.fromkeys(locations + scene_intel.locations))
            abstract_concepts = scene_intel.abstract_concepts
            expanded_prompts = scene_intel.expanded_prompts
        except Exception as e:
            logger.debug(f"SemanticSceneAnalyzer integration fallback: {e}")

        # Topic inference
        topic = "General Narration"
        kw_set = set(words)
        if kw_set & TURNING_KEYWORDS:
            topic = "Climax & Conflict"
        elif kw_set & EMOTIONAL_KEYWORDS:
            topic = "Emotional & Reflection"
        elif kw_set & LOCATION_KEYWORDS:
            topic = "Location & Setting"
        elif kw_set & TIME_KEYWORDS:
            topic = "Historical / Timeline Context"

        subject = entities[0] if entities else ("speaker" if "i" in words else "subject")
        env = locations[0] if locations else "workspace"

        visual_concepts = sorted(list(dict.fromkeys(clean_words + abstract_concepts)))[:12]

        return VisualRequirement(
            subject=subject,
            entities=entities,
            objects=[w for w in clean_words if w in ENTITY_CONCEPTS and w != subject],
            actions=actions,
            environment=env,
            location=locations[0] if locations else "",
            topic=topic,
            visual_concepts=visual_concepts,
            ocr_hints=[w for w in clean_words if len(w) >= 4],
            abstract_concepts=abstract_concepts,
            expanded_prompts=expanded_prompts
        )

    def infer_context(self, text: str, dur: float, is_silence: bool = False, silence_dur: float = 0.0) -> str:
        """Infer cinematic transition context from narration text and speech characteristics."""
        if is_silence or silence_dur >= 2.0:
            return 'time_passage'

        words = set(re.findall(r'\b[a-zA-Z]{3,}\b', text.lower()))
        if words & TURNING_KEYWORDS:
            return 'turning_point'
        if words & EMOTIONAL_KEYWORDS:
            return 'emotional'
        if words & LOCATION_KEYWORDS:
            return 'location_change'
        if words & TIME_KEYWORDS:
            return 'time_passage'
        if dur < 2.0:
            return 'fast'
        if dur > 5.5:
            return 'story_change'

        return 'normal'

    def build_beats(
        self,
        raw_segments: List[Dict[str, Any]],
        master_dur: float,
        target_beats: Optional[int] = None
    ) -> List[SemanticBeat]:
        """
        Normalize raw speech segments into continuous semantic visual beats covering [0.0, master_dur].
        Zero unexplained gaps, zero overlaps.
        """
        # 1. Continuous timeline normalization via TimelineNormalizer
        continuous = TimelineNormalizer.normalize_speech_segments(
            raw_segments=raw_segments,
            master_dur=master_dur,
            hold_mode='extend_hold'
        )

        # 2. If target_beats is specified (e.g. all images mode) and exceeds continuous segments count
        if target_beats and target_beats > len(continuous):
            beat_items = TimelineNormalizer.partition_into_visual_beats(
                continuous_segments=continuous,
                target_beats=target_beats,
                master_dur=master_dur
            )
        else:
            beat_items = continuous

        # 3. Build structured SemanticBeat objects
        semantic_beats = []
        for idx, b in enumerate(beat_items):
            b_text = b.get('text', '')
            dur = float(b['dur'])
            sil_dur = float(b.get('silence_dur', 0.0))
            is_sil = bool(b.get('is_silence', False))

            v_req = self.extract_visual_requirements(b_text)
            ctx = self.infer_context(b_text, dur, is_silence=is_sil, silence_dur=sil_dur)

            # Importance calculation
            imp = 0.5
            if v_req.topic in ["Climax & Conflict", "Turning Point"]:
                imp = 0.9
            elif v_req.topic == "Emotional & Reflection":
                imp = 0.8
            elif v_req.topic == "Location & Setting":
                imp = 0.7

            semantic_beats.append(SemanticBeat(
                beat_id=f"beat_{idx+1:03d}",
                segment_index=idx,
                start=float(b['start']),
                end=float(b['end']),
                dur=dur,
                text=b_text,
                visual_req=v_req,
                context=ctx,
                importance=imp,
                is_silence=is_sil,
                silence_dur=sil_dur
            ))

        # Enforce exact boundaries
        if semantic_beats:
            semantic_beats[0].start = 0.0
            semantic_beats[-1].end = round(master_dur, 3)
            semantic_beats[-1].dur = round(master_dur - semantic_beats[-1].start, 3)

        return semantic_beats


# ==============================================================================
# 6. MULTI-SIGNAL MATCHING & ADAPTIVE RANKING ENGINE (§12, §13, §14, Phase 3 §4-§20)
# ==============================================================================

class MultiSignalRankingEngine:
    """
    Ranks candidate source images for each semantic beat using 7 configurable signals,
    enriched with Phase 3 Adaptive Intelligence:
      - Content-aware profiles (Documentary, Tutorial, Storytelling, etc.)
      - Cross-scene entity continuity tracking
      - Contextual smart reuse & diversity engine
      - Project-level user correction memory
    """

    def __init__(self, config: Optional[SyncConfig] = None):
        self.config = config or SyncConfig()

    def score_image_for_beat(
        self,
        image: ImageIntelligence,
        beat: SemanticBeat,
        total_beats: int,
        total_images: int,
        recent_history: List[str],
        recent_scenes: Optional[List[str]] = None,
        active_entity: Optional[str] = None,
        entity_preferred_image: Optional[str] = None,
        transition_type: TransitionType = TransitionType.CONTINUATION,
        project_memory: Optional[ProjectCorrectionMemory] = None,
        memory_window: Optional[Dict[str, Any]] = None,
        mapping_mode: MappingMode = MappingMode.SEMANTIC_AUTO
    ) -> CandidateScore:
        """Calculate multi-signal affinity score for an image on a specific beat."""
        signals: Dict[str, float] = {}
        reasons: List[str] = []

        cfg = self.config
        v_req = beat.visual_req
        beat_text_words = set(re.findall(r'[\w]{2,}', beat.text.lower(), re.UNICODE))

        # Narrative Sequence Progression (Priority 7 - strictly 0 in SEMANTIC_AUTO)
        seq_dist = 0.0
        if total_beats > 0 and total_images > 0 and mapping_mode != MappingMode.SEMANTIC_AUTO:
            img_prog = image.sequence_index / float(total_images)
            beat_prog = beat.segment_index / float(total_beats)
            seq_dist = abs(img_prog - beat_prog)
        seq_bonus = max(0.0, 1.0 - seq_dist) if mapping_mode != MappingMode.SEMANTIC_AUTO else 0.0

        # Signal 2: Visual Embedding Cosine Similarity (Profile-weighted)
        beat_embedding = getattr(beat, '_cached_embedding', None)
        if beat_embedding is None:
            abstract_kws = getattr(v_req, 'abstract_concepts', [])
            prompt_text = f"{beat.text} {' '.join(v_req.visual_concepts)} {' '.join(v_req.entities)} {' '.join(abstract_kws)}"
            beat_embedding = DeterministicSemanticEmbedding.encode(prompt_text)
            setattr(beat, '_cached_embedding', beat_embedding)

        raw_emb_sim = DeterministicSemanticEmbedding.cosine_similarity(beat_embedding, image.embedding)
        if not image.visual_concepts and not image.entities and mapping_mode != MappingMode.SEMANTIC_AUTO:
            raw_emb_sim = max(raw_emb_sim, 0.65 * seq_bonus + 0.15)

        # Calibrate raw CLIP dot product to [0.0, 1.0]
        # Empirical baseline: noise is <= 0.14, weak is 0.18, solid match is >= 0.25, strong is >= 0.28
        neural_affinity = max(0.0, min(1.0, (raw_emb_sim - 0.12) / 0.18))
        signals['visual_embedding'] = round(neural_affinity, 4)
        if raw_emb_sim >= 0.27:
            reasons.append("strong_neural_semantic_match")
        elif raw_emb_sim >= 0.22:
            reasons.append("neural_semantic_affinity")
        elif raw_emb_sim < 0.18:
            reasons.append("low_visual_evidence")

        # Signal 1: Semantic Text Similarity (Profile-weighted)
        concept_overlap = set(image.visual_concepts) & set(v_req.visual_concepts)
        narration_overlap = set(image.visual_concepts) & beat_text_words
        text_sim = 0.0
        if v_req.visual_concepts and concept_overlap:
            text_sim = len(concept_overlap) / float(len(v_req.visual_concepts))
        elif narration_overlap:
            text_sim = max(text_sim, min(1.0, len(narration_overlap) * 0.35))
        elif not image.visual_concepts and mapping_mode != MappingMode.SEMANTIC_AUTO:
            # Hierarchy Priority 7: Narrative sequence & context relationship (Legacy only)
            text_sim = max(0.45, seq_bonus * 0.85)

        # Cross-modal visual caption match:
        if image.caption:
            cap_words = set(re.findall(r'[\w]{2,}', image.caption.lower(), re.UNICODE)) - STOPWORDS
            cap_overlap = cap_words & beat_text_words
            if cap_overlap:
                cap_sim = min(1.0, len(cap_overlap) * 0.30)
                text_sim = max(text_sim, cap_sim)
                reasons.append("caption_narrative_match")

        # In SEMANTIC_AUTO, cross-modal neural affinity directly informs text-visual alignment
        if mapping_mode == MappingMode.SEMANTIC_AUTO:
            text_sim = max(text_sim, neural_affinity)

        signals['semantic_text'] = round(min(1.0, text_sim), 4)
        if text_sim > 0.4:
            reasons.append("semantic_similarity")

        # Signal 3: Entity Match & Cross-Scene Continuity (§10, §11)
        entity_matches = set(image.entities) & set(v_req.entities)
        ocr_entity_matches = set(image.ocr_tokens) & set(v_req.entities)
        entity_score = 0.0
        if v_req.entities:
            entity_score = (len(entity_matches) + len(ocr_entity_matches)) / float(len(v_req.entities))
        elif not v_req.entities and not image.entities:
            entity_score = 0.5  # Neutral baseline

        # Cross-Scene Entity Continuity Boost (§10, §11)
        if active_entity and (active_entity in image.entities or image.filename == entity_preferred_image):
            entity_score = min(1.0, entity_score + 0.20)
            reasons.append("entity_continuity_boost")

        signals['entity_match'] = round(min(1.0, entity_score), 4)
        if entity_score >= 0.5:
            reasons.append("entity_match")

        # Signal 4: Action Match (Profile-weighted)
        action_matches = set(image.actions) & set(v_req.actions)
        action_score = 0.0
        if v_req.actions:
            action_score = len(action_matches) / float(len(v_req.actions))
        elif not v_req.actions:
            action_score = 0.5
        signals['action_match'] = round(min(1.0, action_score), 4)
        if action_score >= 0.5:
            reasons.append("action_match")

        # Signal 5: Scene / Location Match (Profile-weighted)
        scene_score = 0.0
        if v_req.location and image.scene:
            scene_score = 1.0 if v_req.location == image.scene else 0.2
        elif v_req.environment == image.environment:
            scene_score = 0.8
        else:
            scene_score = 0.4
        signals['scene_location'] = round(min(1.0, scene_score), 4)
        if scene_score >= 0.7:
            reasons.append("scene_match")

        # Signal 6: Temporal Context / Triplet Continuity (Profile-weighted)
        prev_image = recent_history[-1] if recent_history else None
        temporal_score = 0.6  # Default healthy baseline
        if prev_image == image.filename:
            if transition_type == TransitionType.CONTINUATION:
                temporal_score = 0.85  # Reward valid visual holding when narrative topic continues (§18)
            else:
                temporal_score = 0.30  # Penalize repeating image after a clear semantic shift
        signals['temporal_context'] = round(temporal_score, 4)

        # Signal 7: Sequence & Filename Metadata (Strictly 0.0% weight in SEMANTIC_AUTO)
        if mapping_mode == MappingMode.SEMANTIC_AUTO:
            signals['sequence_metadata'] = 0.0
            norm_factor = max(0.01, 1.0 - cfg.w_sequence_meta)
            raw_score = (
                cfg.w_semantic_text * signals['semantic_text'] +
                cfg.w_visual_embedding * signals['visual_embedding'] +
                cfg.w_entity_match * signals['entity_match'] +
                cfg.w_action_match * signals['action_match'] +
                cfg.w_scene_location * signals['scene_location'] +
                cfg.w_temporal_context * signals['temporal_context']
            ) / norm_factor
        else:
            fn_match = any(t in beat_text_words for t in image.filename_tokens)
            if fn_match and signals['semantic_text'] == 0.0 and signals['visual_embedding'] <= 0.52:
                fn_match = False
            fn_score = (seq_bonus * 0.7) + (0.3 if fn_match else 0.0)
            signals['sequence_metadata'] = round(min(1.0, fn_score), 4)
            if fn_match:
                reasons.append("filename_support")

            raw_score = (
                cfg.w_semantic_text * signals['semantic_text'] +
                cfg.w_visual_embedding * signals['visual_embedding'] +
                cfg.w_entity_match * signals['entity_match'] +
                cfg.w_action_match * signals['action_match'] +
                cfg.w_scene_location * signals['scene_location'] +
                cfg.w_temporal_context * signals['temporal_context'] +
                cfg.w_sequence_meta * signals['sequence_metadata']
            )

        # Phase 3 Project-Level Learning Bias (§7, §9)
        if project_memory and cfg.enable_project_learning:
            learn_bias, learn_reasons = project_memory.get_learning_bias(
                image_filename=image.filename,
                entities=v_req.entities,
                concepts=v_req.visual_concepts,
                semantic_text_sim=signals['semantic_text']
            )
            raw_score += learn_bias
            reasons.extend(learn_reasons)

        # Phase 3 Smart Reuse & Repetition Penalty (§18)
        penalty = 0.0
        if recent_history:
            recent_scenes_list = recent_scenes or []
            penalty = VisualDiversityEngine.calculate_smart_reuse_penalty(
                image_filename=image.filename,
                image_scene=image.scene,
                recent_history=recent_history,
                recent_scenes=recent_scenes_list,
                transition_type=transition_type
            )

        net_score = max(0.0, raw_score - penalty)

        return CandidateScore(
            image_id=image.image_id,
            filename=image.filename,
            total_score=round(net_score, 4),
            raw_score=round(raw_score, 4),
            penalty=round(penalty, 4),
            signals=signals,
            reasons=reasons
        )

    def retrieve_top_k(
        self,
        images: List[ImageIntelligence],
        beat: SemanticBeat,
        total_beats: int,
        recent_history: List[str],
        recent_scenes: Optional[List[str]] = None,
        active_entity: Optional[str] = None,
        entity_preferred_image: Optional[str] = None,
        transition_type: TransitionType = TransitionType.CONTINUATION,
        project_memory: Optional[ProjectCorrectionMemory] = None,
        memory_window: Optional[Dict[str, Any]] = None,
        k: int = 5,
        mapping_mode: MappingMode = MappingMode.SEMANTIC_AUTO
    ) -> List[CandidateScore]:
        """
        Retrieve top-K candidate images for a beat (§14, Phase 3 §21, §22).
        Uses Two-Stage Retrieval when image count >= 500.
        """
        candidate_pool = images
        # Adaptive Two-Stage Retrieval Pruning (§21, §22)
        if self.config.enable_two_stage_retrieval and len(images) >= 100:
            beat_emb = DeterministicSemanticEmbedding.encode(beat.text)
            candidate_pool = TwoStageRetriever.prune_candidates(
                images=images,
                beat_embedding=beat_emb,
                beat_entities=beat.visual_req.entities,
                cosine_fn=DeterministicSemanticEmbedding.cosine_similarity,
                total_images=len(images)
            )

        scores = []
        for img in candidate_pool:
            sc = self.score_image_for_beat(
                image=img,
                beat=beat,
                total_beats=total_beats,
                total_images=len(images),
                recent_history=recent_history,
                recent_scenes=recent_scenes,
                active_entity=active_entity,
                entity_preferred_image=entity_preferred_image,
                transition_type=transition_type,
                project_memory=project_memory,
                memory_window=memory_window,
                mapping_mode=mapping_mode
            )
            scores.append(sc)

        scores.sort(key=lambda s: s.total_score, reverse=True)
        return scores[:k]


# ==============================================================================
# 7. CONTEXTUAL RERANKER & AI AMBIGUITY RERANKER (§15, §16, §17, §25, §26)
# ==============================================================================

class ContextualReranker:
    """
    Reranks Top-5 candidates considering the visual progression triplet (prev, curr, next).
    Invokes AI Reranker ONLY when ambiguity delta < 0.08 (§16, §25).
    Includes AI Call Cache (§26) and Prompt Versioning (§27).
    """

    def __init__(self, config: Optional[SyncConfig] = None):
        self.config = config or SyncConfig()
        self.ai_rerank_count = 0
        self.ai_success_count = 0
        self.ai_cache: Dict[str, Dict[str, Any]] = {}
        self.prompt_version = "v3.2_production"

    def should_trigger_ai(self, candidates: List[CandidateScore]) -> bool:
        """Evaluate if top candidates are ambiguous enough to trigger AI reranker (§16, §25)."""
        if len(candidates) < 2:
            return False
        top1 = candidates[0].total_score
        top2 = candidates[1].total_score
        delta = top1 - top2

        # Cost Control: Skip AI if top candidate is already High Confidence (>= 0.70)
        cfg = self.config
        if delta < cfg.rerank_ambiguity_delta and top1 < cfg.high_confidence_thresh:
            return True
        return False

    def rerank_with_ai(
        self,
        beat: SemanticBeat,
        candidates: List[CandidateScore],
        image_map: Dict[str, ImageIntelligence],
        prev_image: Optional[str] = None
    ) -> Optional[CandidateScore]:
        """Call AI provider to resolve ambiguity between top candidates (§16, §25, §26)."""
        if not get_llm_provider:
            return None

        # Check AI Cache (§26)
        cand_fns = [c.filename for c in candidates[:3]]
        cache_key = CacheKeyGenerator.make_ai_call_cache_key(beat.text, cand_fns, self.prompt_version)
        if cache_key in self.ai_cache:
            cached_sel = self.ai_cache[cache_key].get("selected_filename")
            for c in candidates:
                if c.filename == cached_sel:
                    c.reasons.append("ai_rerank_cached")
                    return c

        self.ai_rerank_count += 1
        try:
            prov: LLMProvider = get_llm_provider("auto")
            if not prov or prov.name == "local_deterministic":
                return None

            candidate_summaries = []
            for idx, c in enumerate(candidates[:3]):
                intel = image_map.get(c.filename)
                desc = intel.caption if intel else c.filename
                candidate_summaries.append({
                    "option": idx + 1,
                    "filename": c.filename,
                    "description": desc,
                    "score": c.total_score
                })

            system_prompt = (
                f"You are an AI video synchronization assistant (Prompt {self.prompt_version}). "
                "Select the single most semantically appropriate image from the user's candidates for the narration beat.\n"
                "Rules:\n"
                "1. Choose ONLY from the provided candidate filenames.\n"
                "2. DO NOT hallucinate images or alter durations.\n"
                "3. Return strict JSON: {\"selected_filename\": \"<filename>\", \"reason\": \"<short reason>\"}."
            )

            user_prompt = json.dumps({
                "narration_beat": beat.text,
                "visual_requirements": asdict(beat.visual_req),
                "previous_image": prev_image,
                "candidates": candidate_summaries
            }, ensure_ascii=False)

            res_text = prov.complete(system_prompt, user_prompt, json_mode=True)
            match = re.search(r'\{.*\}', res_text, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                selected_fn = parsed.get("selected_filename", "")
                reason = parsed.get("reason", "AI reranked top semantic candidate")
                for c in candidates:
                    if c.filename == selected_fn:
                        c.reasons.append(f"ai_rerank: {reason}")
                        self.ai_success_count += 1
                        # Save to AI call cache (§26)
                        self.ai_cache[cache_key] = {"selected_filename": selected_fn, "reason": reason}
                        return c
        except Exception as e:
            logger.warning(f"AI reranker call failed: {e}")

        return None

    def rerank_candidates(
        self,
        beat: SemanticBeat,
        candidates: List[CandidateScore],
        image_map: Dict[str, ImageIntelligence],
        prev_image: Optional[str] = None
    ) -> Tuple[CandidateScore, str]:
        """
        Rerank candidates using contextual triplet evaluation + conditional AI reranker.
        Returns (best_candidate, source_label).
        """
        if not candidates:
            raise ValueError("No candidates provided for reranking.")

        # 1. Check AI ambiguity trigger (§16, §25)
        if self.should_trigger_ai(candidates):
            ai_choice = self.rerank_with_ai(beat, candidates, image_map, prev_image)
            if ai_choice:
                return ai_choice, "ai_semantic"

        # 2. Deterministic Contextual Variety (§15, §17)
        best = candidates[0]
        if prev_image and len(candidates) > 1:
            top1 = candidates[0]
            top2 = candidates[1]
            # Diversity Rule (§17): If top1 is repeated and top2 is within 0.05, pick top2
            if top1.filename == prev_image and (top1.total_score - top2.total_score) < 0.05:
                best = top2
                best.reasons.append("contextual_variety")
                return best, "deterministic_semantic"

        return best, "deterministic_semantic"


# ==============================================================================
# 8. MASTER ENGINE: AI IMAGE SYNC ENGINE v3 (§3, §4, §18, §26, §35, §51)
# ==============================================================================

class AIImageSyncEngineV3:
    """
    Master AI Image Sync Engine v3 (Phase 3 Production Intelligence).
    Universal 2D Source Images + Audio -> Cinematic Video Synchronization Engine.
    """

    def __init__(self, config: Optional[SyncConfig] = None):
        self.config = config or SyncConfig()
        self.indexer = ImageIntelligenceIndexer()
        self.beat_engine = SemanticBeatEngine(self.config)
        self.ranker = MultiSignalRankingEngine(self.config)
        self.reranker = ContextualReranker(self.config)

    @staticmethod
    def is_storyboard_sequence(indexed_images: List[ImageIntelligence]) -> bool:
        """
        Detect whether user-uploaded images represent an ordered chronological storyboard.
        Criteria:
          - Image filenames contain numeric indexing (e.g. image_1.png..image_86.png, shot_01..shot_20).
          - Natural sort yields a monotonically non-decreasing numeric progression.
        """
        if len(indexed_images) < 2:
            return False
        nums = []
        for img in indexed_images:
            m = re.findall(r'\d+', img.filename)
            if not m:
                return False
            nums.append(int(m[-1]))
        return all(nums[i] <= nums[i+1] for i in range(len(nums) - 1))

    @staticmethod
    def probe_audio_duration(audio_path: Path) -> float:
        """Accurately probe audio file duration using ffprobe."""
        try:
            from engine.fast_pipeline import get_ffprobe_path
            ffprobe_bin = get_ffprobe_path()
        except Exception:
            ffprobe_bin = "ffprobe"
        r = subprocess.run([
            ffprobe_bin, '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(audio_path)
        ], capture_output=True, text=True, check=True)
        return float(r.stdout.strip())

    @staticmethod
    def compare_plans(old_plan: Dict[str, Any], new_plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare old and new scene plans upon re-sync (§35).
        Returns changed mappings, unchanged mappings, and preserved manual overrides.
        """
        old_scenes = old_plan.get("scenes", []) if isinstance(old_plan, dict) else old_plan
        new_scenes = new_plan.get("scenes", []) if isinstance(new_plan, dict) else new_plan

        old_map = {sc.get("segment_index", i): sc for i, sc in enumerate(old_scenes)}
        changed = []
        unchanged = 0
        manual_preserved = 0

        for i, n_sc in enumerate(new_scenes):
            seg_i = n_sc.get("segment_index", i)
            n_img = n_sc.get("image", "")
            is_manual = n_sc.get("user_override", False)
            if seg_i in old_map:
                o_sc = old_map[seg_i]
                o_img = o_sc.get("image", "")
                if is_manual:
                    manual_preserved += 1
                elif o_img != n_img:
                    changed.append({
                        "scene_id": n_sc.get("scene_id", f"scene_{i+1:04d}"),
                        "timing": f"{n_sc.get('start', 0.0):.2f}s - {n_sc.get('end', 0.0):.2f}s",
                        "old_image": o_img,
                        "new_image": n_img,
                        "confidence": n_sc.get("confidence", 0.0),
                        "reason": "; ".join(n_sc.get("match_reason", []))
                    })
                else:
                    unchanged += 1
            else:
                changed.append({
                    "scene_id": n_sc.get("scene_id", f"scene_{i+1:04d}"),
                    "timing": f"{n_sc.get('start', 0.0):.2f}s - {n_sc.get('end', 0.0):.2f}s",
                    "old_image": "N/A (new)",
                    "new_image": n_img,
                    "confidence": n_sc.get("confidence", 0.0),
                    "reason": "new_beat"
                })

        return {
            "changed_count": len(changed),
            "unchanged_count": unchanged,
            "manual_preserved_count": manual_preserved,
            "changed_mappings_count": len(changed),
            "unchanged_mappings": unchanged,
            "manual_mappings_preserved": manual_preserved,
            "changed_mappings": changed
        }

    def evaluate_confidence(self, score: float) -> Tuple[str, float]:
        """Determine confidence level using calibrated thresholds (§28)."""
        norm_score = max(0.0, min(1.0, score))
        if norm_score >= self.config.high_confidence_thresh:
            level = "HIGH"
        elif norm_score >= self.config.medium_confidence_thresh:
            level = "MEDIUM"
        else:
            level = "LOW"
        return level, round(norm_score, 4)

    def synchronize_timeline(
        self,
        audio_path: Path,
        images_dir: Path,
        image_filenames: Optional[List[str]] = None,
        transcript_path: Optional[Path] = None,
        all_images_mode: bool = True,
        user_overrides: Optional[Dict[int, str]] = None,
        profile: Optional[str] = None,
        sync_mode: Optional[str] = None,
        project_dir: Optional[Path] = None,
        mapping_mode: str = "SEMANTIC_AUTO",
        music_path: Optional[Path] = None,
        pacing_bias: Optional[float] = None,
        broll_path: Optional[Union[str, Path]] = None
    ) -> Tuple[Dict[str, Any], Dict[str, Any], SyncQualityReport]:
        """
        Execute full AI Image Sync Engine v3 Phase 3 pipeline.
        Returns (transcript_obj, plan_obj, sync_quality_report).
        Guarantees:
          - Audio remains master timeline (§4).
          - Images selected are 100% user-uploaded source images (§1).
          - Adaptive profile weights and cross-scene entity continuity applied (§4, §10).
          - Global sequence optimization via Hungarian bipartite matching (§6.3).
          - Filenames/archive order do not determine visual order in SEMANTIC_AUTO (§2).
          - Decision trace exposed on every scene (§51).
          - Explicit user overrides preserved (§20, §29).
        """
        t0 = time.time()
        master_dur = self.probe_audio_duration(audio_path)
        user_overrides = user_overrides or {}
        p_dir = project_dir or images_dir.parent

        # Resolve mapping mode (§4, §6.5)
        try:
            active_mapping_mode = MappingMode(mapping_mode.upper()) if mapping_mode else MappingMode.SEMANTIC_AUTO
        except Exception:
            active_mapping_mode = MappingMode.SEMANTIC_AUTO

        # 1. Image Intelligence Indexing
        indexed_images = self.indexer.index_image_directory(images_dir, image_filenames)
        if not indexed_images:
            raise ValueError(f"No valid source images found in {images_dir}")

        image_map: Dict[str, ImageIntelligence] = {img.filename: img for img in indexed_images}
        n_imgs = len(indexed_images)

        # 2. Ingest Transcript Segments
        raw_segments = []
        if transcript_path and transcript_path.exists():
            try:
                with open(transcript_path, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                raw = d.get('segments', []) if isinstance(d, dict) else d
                raw_segments = [{'start': float(s['start']), 'end': float(s['end']), 'text': s.get('text', '')} for s in raw]
            except Exception as e:
                logger.warning(f"Could not load transcript {transcript_path}: {e}")

        # Check if transcript is missing or lacks valid speech words (§5, §6)
        from engine.stt_provider import is_valid_speech_transcript, transcribe_with_fallback
        if not raw_segments or not is_valid_speech_transcript(raw_segments):
            logger.info(f"[SYNC_V3] No valid speech transcript found. Running real STT transcription for {audio_path.name}...")
            try:
                caption_model, provider_used = transcribe_with_fallback(
                    audio_path=audio_path,
                    transcript_path=transcript_path,
                    preferred_provider="auto"
                )
                if caption_model and caption_model.segments:
                    raw_segments = [{'start': float(s.start), 'end': float(s.end), 'text': s.text} for s in caption_model.segments]
                    logger.info(f"[SYNC_V3] STT succeeded via {provider_used}: {len(raw_segments)} segments transcribed.")
                    if transcript_path:
                        try:
                            with open(transcript_path, 'w', encoding='utf-8') as tf:
                                json.dump(caption_model.to_dict(), tf, indent=2)
                        except Exception as save_err:
                            logger.warning(f"[SYNC_V3] Could not save transcript.json: {save_err}")
            except Exception as stt_err:
                logger.warning(f"[SYNC_V3] Automatic STT failed: {stt_err}")

        if not raw_segments:
            from engine.semantic_sync import detect_speech_and_silences
            speech_segs, _ = detect_speech_and_silences(audio_path)
            if speech_segs:
                raw_segments = speech_segs
            else:
                n_target = n_imgs
                step = master_dur / max(1, n_target)
                t = 0.0
                for i in range(n_target):
                    end_t = master_dur if i == n_target - 1 else round(t + step, 3)
                    raw_segments.append({'start': round(t, 3), 'end': end_t, 'text': f"Scene {i+1}: Opening Segment" if i == 0 else f"Scene {i+1}: Continuation"})
                    t = end_t

        # 3. Content Type Detection & Profile Weights (§4, §5)
        full_narration = " ".join(s.get('text', '') for s in raw_segments)
        if profile and profile.upper() in PROFILE_WEIGHTS:
            active_profile = SyncProfile(profile.upper())
        else:
            inferred_profile, _, _ = ContentClassifier.classify(full_narration)
            active_profile = inferred_profile

        self.config.profile_name = active_profile.value
        # Re-apply profile weights
        pw = PROFILE_WEIGHTS[active_profile.value]
        self.config.w_semantic_text = pw["w_semantic_text"]
        self.config.w_visual_embedding = pw["w_visual_embedding"]
        self.config.w_entity_match = pw["w_entity_match"]
        self.config.w_action_match = pw["w_action_match"]
        self.config.w_scene_location = pw["w_scene_location"]
        self.config.w_temporal_context = pw["w_temporal_context"]
        self.config.w_sequence_meta = pw["w_sequence_meta"]

        if sync_mode:
            self.config.sync_mode = sync_mode.upper()

        # 4. Load Project-Level Correction Memory (§6, §7, §8, §9)
        memory_file = p_dir / ".cache" / "project_sync_learning.json"
        project_memory = ProjectCorrectionMemory(memory_file) if self.config.enable_project_learning else None

        # 5. Initialize Entity Tracker (§10, §11)
        entity_tracker = EntityTracker() if self.config.enable_entity_tracking else None

        # 6. Build Semantic Beats
        target_beats = n_imgs if (all_images_mode and n_imgs > len(raw_segments)) else None
        semantic_beats = self.beat_engine.build_beats(
            raw_segments=raw_segments,
            master_dur=master_dur,
            target_beats=target_beats
        )

        # 6.1 Cadence-Aware Scene Boundary Alignment (Phase 2 Clean-Room DSP)
        cadence_adjustments = []
        if getattr(self.config, 'enable_cadence_alignment', True) and audio_path and Path(audio_path).exists():
            try:
                from engine.audio_rhythm import align_semantic_beats_cadence
                effective_pacing = pacing_bias if pacing_bias is not None else getattr(self.config, 'pacing_bias', 1.0)
                semantic_beats, cadence_adjustments, _ = align_semantic_beats_cadence(
                    semantic_beats=semantic_beats,
                    master_dur=master_dur,
                    narration_audio_path=audio_path,
                    music_audio_path=music_path if (music_path and Path(music_path).exists()) else None,
                    transcript_obj={'segments': raw_segments},
                    user_overrides=user_overrides,
                    tolerance_sec=getattr(self.config, 'cadence_tolerance_sec', 0.180),
                    pacing_bias=effective_pacing
                )
            except Exception as e:
                logger.warning(f"Cadence alignment fallback: {e}")

        # 6.2 B-Roll Video Indexing (Phase 3 Clean-Room Subsystem)
        broll_catalog_dict = None
        broll_vids_count = 0
        broll_shots_count = 0
        target_broll_dir = broll_path or getattr(self.config, 'broll_directory', None)
        if (getattr(self.config, 'enable_broll_indexing', False) or broll_path) and target_broll_dir:
            try:
                from engine.broll_indexer import BRollIndexer
                b_cache = (p_dir / ".cache" / "broll_index") if p_dir else None
                indexer = BRollIndexer(
                    cache_dir=b_cache,
                    sample_fps=getattr(self.config, 'broll_sample_fps', 5.0),
                    threshold=getattr(self.config, 'broll_threshold', 0.38),
                    min_shot_duration_sec=getattr(self.config, 'broll_min_shot_duration', 0.8)
                )
                broll_cat = indexer.index_directory(target_broll_dir)
                broll_catalog_dict = broll_cat.to_dict()
                broll_vids_count = broll_cat.total_assets
                broll_shots_count = broll_cat.total_shots
                logger.info(f"[SYNC_V3] B-roll indexing complete: {broll_vids_count} videos, {broll_shots_count} shots.")
            except Exception as e_broll:
                logger.warning(f"B-roll indexing fallback: {e_broll}")

        # 7. Visual Arc (Chapters Segmentation §14, §15)
        chapters = VisualArcManager.segment_visual_chapters(semantic_beats, master_dur) if self.config.enable_visual_arc else []

        # 8. Global Sequence Optimization (GlobalTimelineOptimizer & Hungarian Assignment §6.3)
        total_beats = len(semantic_beats)
        globally_assigned_images: Dict[int, str] = {}
        candidate_scores_per_beat: Dict[int, List[CandidateScore]] = {}
        assigned_optimizer_results: Dict[int, Any] = {}

        # Batch pre-encode all beat embeddings for instant vectorized scoring
        beat_prompts = []
        for beat in semantic_beats:
            abstract_kws = getattr(beat.visual_req, 'abstract_concepts', [])
            p_text = f"{beat.text} {' '.join(beat.visual_req.visual_concepts)} {' '.join(beat.visual_req.entities)} {' '.join(abstract_kws)}"
            beat_prompts.append(p_text)

        try:
            from engine.semantic_vision import SemanticVisionModel
            svm = SemanticVisionModel()
            batch_embs = svm.batch_encode_texts(beat_prompts)
            for b_i, beat in enumerate(semantic_beats):
                setattr(beat, '_cached_embedding', [round(float(x), 6) for x in batch_embs[b_i].tolist()])
        except Exception as e:
            logger.debug(f"Batch beat pre-encoding fallback: {e}")

        if active_mapping_mode in (MappingMode.SEMANTIC_AUTO, MappingMode.SEQUENCE_AWARE):
            benefit_matrix = []
            for b_i, beat in enumerate(semantic_beats):
                b_scores = []
                cands = []
                seg_idx = beat.segment_index
                has_override = (seg_idx in user_overrides)
                override_fn = user_overrides.get(seg_idx)

                for img in indexed_images:
                    if has_override:
                        val = 100.0 if img.filename == override_fn else -100.0
                        cands.append(CandidateScore(
                            image_id=img.image_id, filename=img.filename,
                            total_score=1.0 if img.filename == override_fn else 0.0,
                            raw_score=1.0, penalty=0.0, signals={}, reasons=["explicit_user_override"]
                        ))
                    else:
                        sc = self.ranker.score_image_for_beat(
                            image=img,
                            beat=beat,
                            total_beats=total_beats,
                            total_images=n_imgs,
                            recent_history=[],
                            mapping_mode=active_mapping_mode
                        )
                        val = sc.total_score
                        cands.append(sc)
                    b_scores.append(val)

                cands.sort(key=lambda s: s.total_score, reverse=True)
                candidate_scores_per_beat[b_i] = cands
                benefit_matrix.append(b_scores)

            sim_matrix = np.array(benefit_matrix, dtype=float)
            all_fns = [img.filename for img in indexed_images]
            from engine.global_timeline_optimizer import GlobalTimelineOptimizer
            gt_optimizer = GlobalTimelineOptimizer(min_match_threshold=0.20)
            user_overrides_by_beat = {
                b_i: user_overrides[b.segment_index]
                for b_i, b in enumerate(semantic_beats)
                if b.segment_index in user_overrides
            }
            is_storyboard = self.is_storyboard_sequence(indexed_images)
            if active_mapping_mode == MappingMode.SEQUENCE_AWARE:
                seq_lambda = 0.22
            elif is_storyboard:
                seq_lambda = 0.15
            else:
                seq_lambda = 0.0

            allow_holds = [
                bool(getattr(b, 'is_silence', False) or getattr(b, 'context', '') == 'fast')
                for b in semantic_beats
            ]

            opt_assignments = gt_optimizer.optimize_timeline(
                similarity_matrix=sim_matrix,
                image_filenames=all_fns,
                user_overrides=user_overrides_by_beat,
                sequence_continuity_lambda=seq_lambda,
                allow_consecutive_holds=allow_holds
            )
            from engine.openmontage_adapter import openmontage_adapter
            for res in opt_assignments:
                assigned_optimizer_results[res.beat_index] = res
                beat_obj = semantic_beats[res.beat_index]
                if res.image_filename and res.confidence_level != "NO_MATCH":
                    globally_assigned_images[res.beat_index] = res.image_filename
                else:
                    # Attempt OpenMontage Visual Discovery for unresolved scene
                    discovered_fn = None
                    try:
                        queries = beat_obj.visual_req.visual_concepts[:3] or [beat_obj.text[:30]]
                        search_q = " ".join(queries).strip()
                        cands = openmontage_adapter.discover_candidates_for_query(search_q, max_candidates=2)
                        if cands:
                            dl_p = openmontage_adapter.download_asset(cands[0], destination_dir=images_dir)
                            if dl_p and dl_p.exists():
                                discovered_fn = dl_p.name
                                new_intel = self.indexer.index_image(dl_p, sequence_index=len(indexed_images))
                                indexed_images.append(new_intel)
                                image_map[discovered_fn] = new_intel
                                res.confidence_level = "MEDIUM"
                                res.confidence = 0.78
                                res.evidence_reasons = [f"openmontage_discovered_{cands[0].source}"]
                    except Exception as disc_err:
                        logger.debug(f"OpenMontage candidate discovery notice for beat {res.beat_index}: {disc_err}")

                    if discovered_fn:
                        globally_assigned_images[res.beat_index] = discovered_fn
                    elif res.image_filename:
                        globally_assigned_images[res.beat_index] = res.image_filename
                    else:
                        globally_assigned_images[res.beat_index] = indexed_images[res.beat_index % n_imgs].filename

        from engine.motion_intelligence import MotionIntelligenceEngine

        scenes: List[Dict[str, Any]] = []
        final_segments: List[Dict[str, Any]] = []
        recent_history: List[str] = []
        recent_scenes: List[str] = []

        high_count = 0
        med_count = 0
        low_count = 0
        no_match_count = 0
        total_conf = 0.0
        used_images_set: Set[str] = set()
        prev_motion = None

        for idx, beat in enumerate(semantic_beats):
            seg_idx = beat.segment_index

            # Context window & chapter identification (§15, §16)
            curr_chapter_idx = 1
            for ch in chapters:
                if ch.beat_start_idx <= idx <= ch.beat_end_idx:
                    curr_chapter_idx = ch.chapter_index
                    break

            mem_window = VisualArcManager.get_semantic_memory_window(semantic_beats, idx) if self.config.enable_visual_arc else None

            # Entity resolution (§10)
            active_entity = None
            ent_pref_img = None
            if entity_tracker:
                active_entity = entity_tracker.resolve_beat_entity(beat.text, beat.visual_req.entities, idx)
                ent_pref_img = entity_tracker.get_entity_preferred_image(active_entity)

            # Scene transition intelligence (§12, §13)
            prev_req = semantic_beats[idx - 1].visual_req if idx > 0 else None
            prev_sc = recent_scenes[-1] if recent_scenes else None
            trans_type, cont_score, trans_reasons = VisualContinuityEngine.evaluate_transition(
                prev_beat_req=prev_req,
                curr_beat_req=beat.visual_req,
                prev_image_scene=prev_sc,
                curr_image_scene=None
            )

            # Check Priority 1: Explicit User Override (§20, §29)
            if seg_idx in user_overrides:
                selected_fn = user_overrides[seg_idx]
                selected_intel = image_map.get(selected_fn, indexed_images[idx % n_imgs])
                conf = 1.0
                conf_level = "HIGH"
                match_reason = ["explicit_user_override"]
                source_label = "user_override"
                is_override = True
                top_candidates_dump = []
                decision_trace = {
                    "selected_image": selected_fn,
                    "confidence": 1.0,
                    "confidence_level": "HIGH",
                    "why": ["explicit_user_override"],
                    "transition_type": trans_type.value,
                    "rejected_candidates": []
                }
            elif idx in globally_assigned_images:
                is_override = False
                selected_fn = globally_assigned_images[idx]
                selected_intel = image_map.get(selected_fn, indexed_images[idx % n_imgs])
                candidates = candidate_scores_per_beat.get(idx, [])

                # Find candidate score for selected image
                best_cand = next((c for c in candidates if c.filename == selected_fn), None)
                if not best_cand and candidates:
                    best_cand = candidates[0]

                opt_res = assigned_optimizer_results.get(idx)
                if opt_res and opt_res.confidence_level == "NO_MATCH":
                    conf_level = "NO_MATCH"
                    conf = opt_res.confidence
                    match_reason = opt_res.evidence_reasons or ["no_matching_visual_evidence_in_library"]
                    no_match_count += 1
                    top_candidates_dump = opt_res.top_candidates
                    rejected_info = opt_res.rejection_trace
                elif best_cand:
                    conf_level, conf, is_uncertain = ConfidenceCalibratorV2.evaluate(
                        score=best_cand.total_score,
                        semantic_text_sim=best_cand.signals.get("semantic_text", 0.0),
                        entity_match=best_cand.signals.get("entity_match", 0.0),
                        has_user_override=False
                    )
                    match_reason = best_cand.reasons or ["semantic_affinity"]
                    if is_uncertain:
                        match_reason.append("no_strong_visual_evidence")
                    if conf_level == "NO_MATCH":
                        no_match_count += 1

                    top_candidates_dump = [
                        {
                            "image": c.filename,
                            "score": c.total_score,
                            "raw_score": c.raw_score,
                            "penalty": c.penalty,
                            "reasons": c.reasons
                        } for c in candidates[:3]
                    ]

                    rejected_info = []
                    for rej in candidates:
                        if rej.filename == selected_fn:
                            continue
                        rej_why = []
                        if rej.penalty > 0:
                            rej_why.append(f"repetition_penalty_{rej.penalty}")
                        if rej.signals.get("entity_match", 0.0) < best_cand.signals.get("entity_match", 0.0):
                            rej_why.append("lower_entity_match")
                        if rej.signals.get("semantic_text", 0.0) < best_cand.signals.get("semantic_text", 0.0):
                            rej_why.append("lower_semantic_text")
                        rejected_info.append({
                            "filename": rej.filename,
                            "score": rej.total_score,
                            "rejection_reasons": rej_why or ["lower_overall_rank"]
                        })
                        if len(rejected_info) >= 3:
                            break
                else:
                    conf_level, conf = "MEDIUM", 0.75
                    match_reason = ["global_sequence_affinity"]
                    top_candidates_dump = []
                    rejected_info = []

                source_label = "ai_semantic_auto" if active_mapping_mode == MappingMode.SEMANTIC_AUTO else "sequence_aware_mapping"
                decision_trace = {
                    "selected_image": selected_fn,
                    "confidence": conf,
                    "confidence_level": conf_level,
                    "why": match_reason,
                    "transition_type": trans_type.value,
                    "rejected_candidates": rejected_info
                }
            else:
                is_override = False
                selected_fn = indexed_images[idx % n_imgs].filename
                selected_intel = indexed_images[idx % n_imgs]
                conf_level, conf = "MEDIUM", 0.70
                match_reason = ["strict_sequential_mode"]
                source_label = "strict_sequential"
                top_candidates_dump = []
                decision_trace = {
                    "selected_image": selected_fn,
                    "confidence": conf,
                    "confidence_level": conf_level,
                    "why": match_reason,
                    "transition_type": trans_type.value,
                    "rejected_candidates": []
                }

            # Update metrics & Entity tracker image binding (§10)
            if conf_level == "HIGH":
                high_count += 1
            elif conf_level == "MEDIUM":
                med_count += 1
            else:
                low_count += 1
            total_conf += conf

            if entity_tracker and active_entity:
                entity_tracker.update_entity_image(active_entity, selected_fn)

            recent_history.append(selected_fn)
            recent_scenes.append(selected_intel.scene)
            used_images_set.add(selected_fn)

            # Transition determination
            ctx = beat.context
            trans_label = self.config.context_transitions.get(ctx, self.config.context_transitions['normal'])['label']

            # Motion planning via MotionIntelligenceEngine (§5)
            motion_plan = MotionIntelligenceEngine.plan_scene_motion(
                scene_idx=idx,
                dur=beat.dur,
                context=ctx,
                energy_level="high" if ctx == "turning_point" else ("subtle" if ctx == "emotional" else "medium"),
                confidence_level=conf_level,
                is_manual_override=is_override,
                prev_motion=prev_motion
            )
            prev_motion = motion_plan.motion_type

            # Cadence alignment decision trace for this scene boundary
            cadence_info = None
            if idx > 0 and (idx - 1) < len(cadence_adjustments):
                cadence_info = cadence_adjustments[idx - 1].to_dict()
            elif idx == 0:
                cadence_info = {"status": "first_scene_zero_start", "delta_ms": 0.0}

            # Build Scene Plan Item (§26, §51)
            scene_item = {
                "scene_id": f"scene_{idx+1:04d}",
                "segment_index": seg_idx,
                "start": beat.start,
                "end": beat.end,
                "dur": beat.dur,
                "image": selected_fn,
                "image_id": selected_intel.image_id,
                "transition": trans_label,
                "transition_dur": self.config.context_transitions.get(ctx, {}).get("dur", 0.40),
                "context": ctx,
                "confidence": conf,
                "confidence_level": conf_level,
                "match_reason": match_reason,
                "source": source_label,
                "user_override": is_override,
                "manual_review_needed": (conf_level in ("NO_MATCH", "LOW")),
                "no_match_warning": (conf_level == "NO_MATCH"),
                "validation_state": "NEEDS_REVIEW" if conf_level in ("NO_MATCH", "LOW") else "VALID",
                "transcript_text": beat.text,
                "visual_intent": f"Visual focus on {', '.join(beat.visual_req.visual_concepts[:4])} in {beat.visual_req.environment or 'studio'}",
                "main_subjects": beat.visual_req.entities,
                "required_objects": [c for c in beat.visual_req.visual_concepts if c not in beat.visual_req.entities],
                "actions": beat.visual_req.actions or ["display", "illustrate"],
                "setting": getattr(beat.visual_req, 'environment', 'general') or "general",
                "mood": getattr(beat.visual_req, 'mood', 'neutral') or "neutral",
                "suggested_shot_type": "medium_shot" if beat.dur > 3.0 else "close_up",
                "search_queries": [f"{' '.join(beat.visual_req.visual_concepts[:3])}", beat.text[:40]],
                "motion": motion_plan.renderer_motion_label,
                "motion_mode": motion_plan.motion_type,
                "shot_role": motion_plan.shot_role,
                "easing": motion_plan.easing,
                "zoom_scale": motion_plan.zoom_scale,
                "pan_speed": motion_plan.pan_speed_px,
                "motion_rationale": motion_plan.rationale,
                "candidates": top_candidates_dump,
                "narration_text": beat.text,
                "transition_type": trans_type.value,
                "chapter_index": curr_chapter_idx,
                "cadence_alignment": cadence_info,
                "decision_trace": decision_trace
            }
            scenes.append(scene_item)

            final_segments.append({
                "start": beat.start,
                "end": beat.end,
                "dur": beat.dur,
                "text": beat.text,
                "topic": beat.visual_req.topic,
                "importance": beat.importance,
                "keywords": beat.visual_req.visual_concepts[:6]
            })

        # Exact audio boundary clamp
        if scenes:
            scenes[0]["start"] = 0.0
            scenes[-1]["end"] = round(master_dur, 3)
            scenes[-1]["dur"] = round(master_dur - scenes[-1]["start"], 3)
            final_segments[0]["start"] = 0.0
            final_segments[-1]["end"] = round(master_dur, 3)

        transcript_obj = {"segments": final_segments}
        plan_obj = {"scenes": scenes}
        if broll_catalog_dict:
            plan_obj["broll_index"] = broll_catalog_dict

        # 9. Build Sync Quality Report with Genuine Sync Quality Score (§30, §42, §54)
        total_beats_count = len(scenes)
        avg_conf = round(total_conf / max(1, total_beats_count), 4)
        repeated_imgs = max(0, total_beats_count - len(used_images_set))
        corrs_learned = len(project_memory.corrections) if project_memory else 0

        quality_score, score_bd = ConfidenceCalibratorV2.compute_sync_quality_score(
            total_beats=total_beats_count,
            high_conf_count=high_count,
            med_conf_count=med_count,
            low_conf_count=low_count,
            avg_confidence=avg_conf,
            repeated_images_count=repeated_imgs,
            corrections_count=corrs_learned,
            scenes=scenes,
            semantic_beats=semantic_beats,
            master_dur=master_dur,
            return_breakdown=True
        )

        aligned_cuts_count = sum(1 for a in cadence_adjustments if a.adjustment_type != "none")
        avg_cadence_delta = round(float(np.mean([abs(a.delta_ms) for a in cadence_adjustments])) if cadence_adjustments else 0.0, 2)
        speech_pauses_cnt = sum(1 for a in cadence_adjustments if "speech_pause" in a.adjustment_type)
        music_beats_cnt = sum(1 for a in cadence_adjustments if "music_beat" in a.adjustment_type)

        report = SyncQualityReport(
            total_images=n_imgs,
            total_beats=total_beats_count,
            high_confidence=high_count,
            medium_confidence=med_count,
            low_confidence=low_count,
            average_confidence=avg_conf,
            sync_quality_score=quality_score,
            profile_used=self.config.profile_name,
            sync_mode_used=self.config.sync_mode,
            repeated_images=repeated_imgs,
            semantic_conflicts=0,
            unmatched_beats=no_match_count,
            ai_reranking_triggered=self.reranker.ai_rerank_count,
            ai_reranking_successful=self.reranker.ai_success_count,
            fallback_used=1 if low_count > 0 else 0,
            project_corrections_learned=corrs_learned,
            tracked_entities_count=len(entity_tracker.active_entities) if entity_tracker else 0,
            chapters_count=len(chapters),
            duration_sec=round(time.time() - t0, 3),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            semantic_relevance=score_bd.get("semantic_relevance", 0.0),
            temporal_alignment=score_bd.get("temporal_alignment", 0.0),
            beat_coverage=score_bd.get("beat_coverage", 0.0),
            context_continuity=score_bd.get("context_continuity", 0.0),
            image_confidence=score_bd.get("image_confidence", 0.0),
            cadence_aligned_cuts=aligned_cuts_count,
            cadence_adjustments_avg_ms=avg_cadence_delta,
            cadence_speech_pauses_count=speech_pauses_cnt,
            cadence_music_beats_count=music_beats_cnt,
            broll_videos_indexed=broll_vids_count,
            broll_shots_indexed=broll_shots_count,
            broll_catalog=broll_catalog_dict,
            score_breakdown=score_bd
        )

        return transcript_obj, plan_obj, report
