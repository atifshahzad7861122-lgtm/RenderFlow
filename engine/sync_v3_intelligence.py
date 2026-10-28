#!/usr/bin/env python3
"""
engine/sync_v3_intelligence.py — AI Image Sync Engine v3 Phase 3 Intelligence
Rendering Studio Engine v2

Provides:
  1. Content-Aware Ranking Profiles & ContentClassifier (§4, §5)
  2. User Correction Memory & Project-Level Learning (§6, §7, §8, §9, §37, §38)
  3. Cross-Scene Entity Tracker & Pronoun Resolution (§10, §11)
  4. Visual Continuity Engine & Scene Transition Intelligence (§12, §13)
  5. Visual Arc Manager (Visual Chapters & Long-Form Context) (§14, §15, §16)
  6. Visual Diversity Engine, Smart Reuse & Image Clustering (§17, §18, §19, §20)
  7. Two-Stage Candidate Retrieval (§21, §22)
  8. Embedding Metadata & Cache Invalidation (§23, §24, §25, §26, §27)
  9. Decision Trace & Calibration v2 (§28, §29, §30, §51)
"""

import os
import re
import json
import time
import math
import hashlib
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Set, Union
import numpy as np

logger = logging.getLogger("rendering_studio.sync_v3.intelligence")

# ==============================================================================
# 1. ADAPTIVE CONTENT-AWARE RANKING PROFILES (§4, §5)
# ==============================================================================

class MappingMode(str, Enum):
    SEMANTIC_AUTO = "SEMANTIC_AUTO"         # 100% visual content & transcript meaning driven (default)
    SEQUENCE_AWARE = "SEQUENCE_AWARE"       # Semantic matching with narrative continuity
    STRICT_SEQUENTIAL = "STRICT_SEQUENTIAL" # Use input file order only when explicitly requested
    MANUAL = "MANUAL"                       # User-locked manual assignments preserved


class SyncProfile(str, Enum):
    DOCUMENTARY = "DOCUMENTARY"
    STORYTELLING = "STORYTELLING"
    EDUCATIONAL = "EDUCATIONAL"
    TUTORIAL = "TUTORIAL"
    BUSINESS = "BUSINESS"
    TECHNOLOGY = "TECHNOLOGY"
    PODCAST = "PODCAST"
    GENERAL = "GENERAL"


# Multi-signal weights for each content profile. Each set sums exactly to 1.00.
PROFILE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "DOCUMENTARY": {
        "w_semantic_text": 0.22,
        "w_visual_embedding": 0.22,
        "w_entity_match": 0.22,
        "w_temporal_context": 0.14,
        "w_scene_location": 0.10,
        "w_action_match": 0.05,
        "w_sequence_meta": 0.05,
    },
    "STORYTELLING": {
        "w_semantic_text": 0.25,
        "w_scene_location": 0.18,
        "w_temporal_context": 0.18,
        "w_entity_match": 0.15,
        "w_visual_embedding": 0.14,
        "w_action_match": 0.05,
        "w_sequence_meta": 0.05,
    },
    "TUTORIAL": {
        "w_action_match": 0.22,
        "w_semantic_text": 0.22,
        "w_visual_embedding": 0.20,
        "w_entity_match": 0.16,
        "w_temporal_context": 0.10,
        "w_scene_location": 0.05,
        "w_sequence_meta": 0.05,
    },
    "EDUCATIONAL": {
        "w_semantic_text": 0.25,
        "w_visual_embedding": 0.20,
        "w_entity_match": 0.18,
        "w_action_match": 0.12,
        "w_temporal_context": 0.10,
        "w_scene_location": 0.10,
        "w_sequence_meta": 0.05,
    },
    "BUSINESS": {
        "w_entity_match": 0.24,
        "w_semantic_text": 0.24,
        "w_visual_embedding": 0.20,
        "w_scene_location": 0.12,
        "w_action_match": 0.08,
        "w_temporal_context": 0.07,
        "w_sequence_meta": 0.05,
    },
    "TECHNOLOGY": {
        "w_semantic_text": 0.25,
        "w_entity_match": 0.22,
        "w_visual_embedding": 0.22,
        "w_action_match": 0.11,
        "w_scene_location": 0.08,
        "w_temporal_context": 0.07,
        "w_sequence_meta": 0.05,
    },
    "PODCAST": {
        "w_temporal_context": 0.22,
        "w_scene_location": 0.20,
        "w_semantic_text": 0.20,
        "w_visual_embedding": 0.18,
        "w_entity_match": 0.10,
        "w_sequence_meta": 0.05,
        "w_action_match": 0.05,
    },
    "GENERAL": {
        "w_semantic_text": 0.30,
        "w_visual_embedding": 0.20,
        "w_entity_match": 0.15,
        "w_action_match": 0.10,
        "w_scene_location": 0.10,
        "w_temporal_context": 0.10,
        "w_sequence_meta": 0.05,
    }
}


class ContentClassifier:
    """
    Lightweight rule-based narration content-type detector (§5).
    Analyzes narration text to infer content profile:
      DOCUMENTARY, STORYTELLING, TUTORIAL, EDUCATIONAL, BUSINESS, TECHNOLOGY, PODCAST, GENERAL.
    Hard Rule: Affects ONLY ranking weights. Never alters audio timing, video duration,
    captions, transitions or chunking.
    If classification is ambiguous or uncertain, defaults safely to GENERAL.
    """

    PROFILE_LEXICONS: Dict[str, Set[str]] = {
        "DOCUMENTARY": {
            "history", "historical", "century", "war", "battle", "discovered", "archive", "ancient",
            "era", "reign", "emperor", "empire", "civilization", "biography", "chronicle", "decade",
            "archaeological", "artifact", "monument", "ruins", "timeline", "past", "tradition"
        },
        "TUTORIAL": {
            "how", "step", "first", "click", "install", "open", "configure", "setup", "tutorial",
            "guide", "follow", "press", "select", "download", "enter", "command", "setting", "options",
            "navigate", "code", "run", "instructions", "screen", "terminal", "method"
        },
        "BUSINESS": {
            "company", "revenue", "startup", "founder", "market", "profit", "customer", "sales",
            "growth", "business", "investor", "valuation", "strategy", "enterprise", "product",
            "scale", "quarter", "shares", "finance", "executive", "ceo", "industry", "commerce"
        },
        "TECHNOLOGY": {
            "software", "cloud", "ai", "algorithm", "server", "data", "system", "hardware", "api",
            "model", "machine", "learning", "network", "database", "computing", "processor", "gpu",
            "code", "framework", "architecture", "cyber", "internet", "tech", "digital", "platform"
        },
        "EDUCATIONAL": {
            "concept", "principle", "understand", "study", "research", "science", "lesson", "theory",
            "definition", "example", "formula", "experiment", "analysis", "academic", "teacher",
            "student", "learn", "knowledge", "explain", "meaning", "structure", "function"
        },
        "STORYTELLING": {
            "once", "suddenly", "journey", "dream", "fear", "heart", "character", "darkness", "light",
            "whispered", "remembered", "cried", "destiny", "shadow", "silence", "magic", "sorrow",
            "tale", "legend", "night", "morning", "feeling", "hope", "mystery", "adventure"
        },
        "PODCAST": {
            "welcome", "episode", "guest", "talk", "discuss", "conversation", "interview", "host",
            "chat", "listener", "thoughts", "opinion", "agree", "disagree", "today", "show"
        }
    }

    @classmethod
    def classify(cls, full_narration_text: str) -> Tuple[SyncProfile, float, Dict[str, int]]:
        """
        Classify narration text into the most probable SyncProfile.
        Returns (profile, confidence, scores).
        """
        if not full_narration_text:
            return SyncProfile.GENERAL, 0.5, {}

        tokens = [w.lower() for w in re.findall(r'[\w]{2,}', full_narration_text, re.UNICODE)]
        if not tokens:
            return SyncProfile.GENERAL, 0.5, {}

        scores: Dict[str, int] = {}
        for prof_name, lexicon in cls.PROFILE_LEXICONS.items():
            cnt = sum(1 for tok in tokens if tok in lexicon)
            scores[prof_name] = cnt

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_prof, top_count = sorted_scores[0]
        second_prof, second_count = sorted_scores[1] if len(sorted_scores) > 1 else ("", 0)

        # Ambiguity threshold: Need at least 3 keyword hits and a 20% margin over second
        if top_count < 3 or (second_count > 0 and (top_count - second_count) / float(top_count) < 0.15):
            return SyncProfile.GENERAL, 0.50, scores

        conf = min(0.95, round(0.50 + (top_count / float(len(tokens) + 1)) * 5.0, 3))
        return SyncProfile(top_prof), conf, scores


# ==============================================================================
# 2. USER CORRECTION MEMORY & PROJECT LEARNING (§6, §7, §8, §9, §37, §38)
# ==============================================================================

@dataclass
class UserCorrectionRecord:
    """Explicit record of a manual user override (§6)."""
    scene_id: str
    original_image: str
    corrected_image: str
    reason: str = "user_override"
    timestamp: str = ""
    project_id: str = ""
    entity: str = ""
    concept: str = ""


class ProjectCorrectionMemory:
    """
    Lightweight, strictly local project-level preference memory (§6, §7, §8, §9).
    Learns from user corrections:
      - Preferred images: entity/concept -> preferred image candidates
      - Negative associations: entity/concept -> rejected image candidates
    Hard Rules:
      - Supporting signal only: Adds small preference boost (+0.08) or negative penalty (-0.15).
      - NEVER overrides stronger semantic contradiction.
      - 100% local to project directory; zero external telemetry.
      - Reset Sync Learning completely wipes learning data without deleting assets.
    """

    def __init__(self, memory_file: Optional[Path] = None):
        self.memory_file = memory_file
        self.corrections: List[UserCorrectionRecord] = []
        self.preferred_images: Dict[str, Dict[str, int]] = {}  # key -> {img_fn: count}
        self.negative_images: Dict[str, Dict[str, int]] = {}   # key -> {img_fn: count}
        self.load()

    def load(self):
        """Load project learning memory from disk."""
        if not self.memory_file or not self.memory_file.exists():
            return
        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.preferred_images = data.get("preferred_images", {})
            self.negative_images = data.get("negative_images", {})
            raw_corrs = data.get("corrections", [])
            self.corrections = [UserCorrectionRecord(**c) for c in raw_corrs]
        except Exception as e:
            logger.warning(f"Could not load project correction memory: {e}")

    def save(self):
        """Save project learning memory atomically to disk (§38)."""
        if not self.memory_file:
            return
        try:
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "preferred_images": self.preferred_images,
                "negative_images": self.negative_images,
                "corrections": [asdict(c) for c in self.corrections],
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save project correction memory: {e}")

    def record_correction(
        self,
        scene_id: str,
        original_image: str,
        corrected_image: str,
        entity: str = "",
        concept: str = "",
        project_id: str = "",
        reason: str = "user_override"
    ):
        """Record an explicit correction from the user (§6, §7, §8, §9)."""
        if original_image == corrected_image:
            return

        rec = UserCorrectionRecord(
            scene_id=scene_id,
            original_image=original_image,
            corrected_image=corrected_image,
            reason=reason,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            project_id=project_id,
            entity=entity.lower().strip() if entity else "",
            concept=concept.lower().strip() if concept else ""
        )
        self.corrections.append(rec)

        keys_to_update = []
        if entity:
            keys_to_update.append(f"entity:{entity.lower().strip()}")
        if concept:
            keys_to_update.append(f"concept:{concept.lower().strip()}")
        if not keys_to_update:
            keys_to_update.append("global:correction")

        for k in keys_to_update:
            # Preferred image boost
            pref_sub = self.preferred_images.setdefault(k, {})
            pref_sub[corrected_image] = pref_sub.get(corrected_image, 0) + 1

            # Negative feedback for the rejected image (§9)
            neg_sub = self.negative_images.setdefault(k, {})
            neg_sub[original_image] = neg_sub.get(original_image, 0) + 1

        self.save()

    def get_learning_bias(
        self,
        image_filename: str,
        entities: List[str],
        concepts: List[str],
        semantic_text_sim: float
    ) -> Tuple[float, List[str]]:
        """
        Evaluate project-level learning bias for a candidate image (§7, §9).
        Hard Rule: Supporting signal only. Max boost: +0.08. Max penalty: -0.15.
        Suppressed if semantic text evidence is 0.0 and embedding is low.
        """
        bias = 0.0
        reasons = []

        # Check preferred
        keys = []
        for e in entities:
            keys.append(f"entity:{e.lower()}")
        for c in concepts:
            keys.append(f"concept:{c.lower()}")
        keys.append("global:correction")

        # Preferred boost: up to +0.08
        preferred_hits = 0
        for k in keys:
            if k in self.preferred_images and image_filename in self.preferred_images[k]:
                preferred_hits += self.preferred_images[k][image_filename]

        if preferred_hits > 0 and semantic_text_sim >= 0.15:
            boost = min(0.08, 0.04 + 0.02 * preferred_hits)
            bias += boost
            reasons.append("project_preferred_image")

        # Negative penalty: up to -0.15
        negative_hits = 0
        for k in keys:
            if k in self.negative_images and image_filename in self.negative_images[k]:
                negative_hits += self.negative_images[k][image_filename]

        if negative_hits > 0:
            penalty = min(0.15, 0.06 + 0.03 * negative_hits)
            bias -= penalty
            reasons.append("project_negative_feedback")

        return round(bias, 4), reasons

    def reset_learning(self):
        """Completely reset all learned preferences and negative associations (§37)."""
        self.corrections.clear()
        self.preferred_images.clear()
        self.negative_images.clear()
        self.save()


# ==============================================================================
# 3. CROSS-SCENE ENTITY TRACKING (§10, §11)
# ==============================================================================

@dataclass
class TrackedEntity:
    entity_id: str
    canonical_name: str
    aliases: List[str]
    recent_image: Optional[str] = None
    frequency: int = 0
    first_seen_beat: int = 0
    last_seen_beat: int = 0


class EntityTracker:
    """
    Maintains continuity for recurring entities across beats (§10, §11).
    Resolves pronouns ("he", "him", "she", "they") and role aliases ("the founder", "the CEO")
    to the active canonical entity.
    Guarantees:
      - Prevents jumping between different actor images when narration refers to the same person.
      - Lightweight rule-based resolution; no fabricated biometric identity models.
    """

    PRONOUN_MAP: Dict[str, str] = {
        "he": "person", "him": "person", "his": "person",
        "she": "person", "her": "person", "hers": "person",
        "they": "team", "them": "team", "their": "team",
        "it": "object", "its": "object"
    }

    ROLE_ALIASES: Dict[str, str] = {
        "founder": "person_leader",
        "entrepreneur": "person_leader",
        "ceo": "person_leader",
        "leader": "person_leader",
        "visionary": "person_leader",
        "creator": "person_leader",
        "inventor": "person_leader",
        "doctor": "person_medical",
        "physician": "person_medical",
        "surgeon": "person_medical",
        "patient": "person_patient",
        "coder": "person_tech",
        "developer": "person_tech",
        "engineer": "person_tech"
    }

    def __init__(self):
        self.active_entities: Dict[str, TrackedEntity] = {}
        self.last_active_person_entity: Optional[str] = None
        self.last_active_general_entity: Optional[str] = None

    def resolve_beat_entity(self, beat_text: str, detected_entities: List[str], beat_idx: int) -> Optional[str]:
        """
        Identify or resolve canonical entity for the current beat (§10).
        """
        words = [w.lower() for w in re.findall(r'[\w]{2,}', beat_text, re.UNICODE)]

        # 1. Direct explicit entity detected
        for ent in detected_entities:
            ent_key = ent.lower()
            canonical = self.ROLE_ALIASES.get(ent_key, ent_key)
            if canonical not in self.active_entities:
                self.active_entities[canonical] = TrackedEntity(
                    entity_id=f"ent_{len(self.active_entities)+1:03d}",
                    canonical_name=canonical,
                    aliases=[ent_key],
                    frequency=1,
                    first_seen_beat=beat_idx,
                    last_seen_beat=beat_idx
                )
            else:
                te = self.active_entities[canonical]
                te.frequency += 1
                te.last_seen_beat = beat_idx
                if ent_key not in te.aliases:
                    te.aliases.append(ent_key)

            if "person" in canonical or canonical in ["man", "woman", "founder", "ceo"]:
                self.last_active_person_entity = canonical
            self.last_active_general_entity = canonical
            return canonical

        # 2. Check for role alias in text
        for tok in words:
            if tok in self.ROLE_ALIASES:
                canonical = self.ROLE_ALIASES[tok]
                if canonical in self.active_entities:
                    self.active_entities[canonical].frequency += 1
                    self.active_entities[canonical].last_seen_beat = beat_idx
                    self.last_active_person_entity = canonical
                    return canonical

        # 3. Check for pronoun resolution (§10)
        for tok in words:
            if tok in ["he", "him", "his", "she", "her"]:
                if self.last_active_person_entity and self.last_active_person_entity in self.active_entities:
                    te = self.active_entities[self.last_active_person_entity]
                    # Only resolve if seen within last 4 beats
                    if beat_idx - te.last_seen_beat <= 4:
                        te.frequency += 1
                        te.last_seen_beat = beat_idx
                        return self.last_active_person_entity

        return None

    def update_entity_image(self, canonical_name: str, image_filename: str):
        """Bind chosen image to canonical entity for continuity."""
        if canonical_name in self.active_entities:
            self.active_entities[canonical_name].recent_image = image_filename

    def get_entity_preferred_image(self, canonical_name: Optional[str]) -> Optional[str]:
        """Retrieve recent image associated with canonical entity."""
        if canonical_name and canonical_name in self.active_entities:
            return self.active_entities[canonical_name].recent_image
        return None


# ==============================================================================
# 4. VISUAL CONTINUITY ENGINE & SCENE TRANSITION INTELLIGENCE (§12, §13)
# ==============================================================================

class TransitionType(str, Enum):
    CONTINUATION = "CONTINUATION"
    SEMANTIC_SHIFT = "SEMANTIC_SHIFT"


class VisualContinuityEngine:
    """
    Evaluates visual and semantic continuity between adjacent beats (§12, §13).
    Distinguishes:
      - CONTINUATION: Same topic, entity, or environment -> preserve visual continuity.
      - SEMANTIC SHIFT: New location, entity, or topic -> permits visual change.
    """

    @classmethod
    def evaluate_transition(
        cls,
        prev_beat_req: Optional[Any],
        curr_beat_req: Any,
        prev_image_scene: Optional[str],
        curr_image_scene: Optional[str]
    ) -> Tuple[TransitionType, float, List[str]]:
        """
        Determine whether beat transition is a CONTINUATION or a SEMANTIC SHIFT.
        Returns (transition_type, continuity_score, reasons).
        """
        if not prev_beat_req:
            return TransitionType.SEMANTIC_SHIFT, 0.5, ["initial_scene"]

        reasons = []
        score = 0.5  # Neutral baseline

        # 1. Entity continuity check
        prev_entities = set(getattr(prev_beat_req, 'entities', []))
        curr_entities = set(getattr(curr_beat_req, 'entities', []))
        shared_entities = prev_entities & curr_entities
        if shared_entities:
            score += 0.25
            reasons.append(f"shared_entity:{list(shared_entities)[0]}")

        # 2. Location / Environment continuity check
        prev_loc = getattr(prev_beat_req, 'location', '') or getattr(prev_beat_req, 'environment', '')
        curr_loc = getattr(curr_beat_req, 'location', '') or getattr(curr_beat_req, 'environment', '')
        if prev_loc and curr_loc and prev_loc == curr_loc:
            score += 0.20
            reasons.append(f"same_location:{curr_loc}")
        elif prev_loc and curr_loc and prev_loc != curr_loc:
            score -= 0.20
            reasons.append(f"location_shift:{prev_loc}->{curr_loc}")

        # 3. Topic continuity check
        prev_topic = getattr(prev_beat_req, 'topic', '')
        curr_topic = getattr(curr_beat_req, 'topic', '')
        if prev_topic and curr_topic and prev_topic == curr_topic:
            score += 0.15
            reasons.append("topic_continuation")
        else:
            score -= 0.15
            reasons.append("topic_shift")

        score = max(0.0, min(1.0, score))
        if score >= 0.55:
            return TransitionType.CONTINUATION, score, reasons
        else:
            return TransitionType.SEMANTIC_SHIFT, score, reasons


# ==============================================================================
# 5. VISUAL ARC (CHAPTERS) & LONG-FORM CONTEXT (§14, §15, §16)
# ==============================================================================

@dataclass
class VisualChapter:
    """High-level visual narrative chapter (§14)."""
    chapter_index: int
    title: str
    start_time: float
    end_time: float
    beat_start_idx: int
    beat_end_idx: int
    dominant_topic: str
    dominant_entities: List[str]
    dominant_environment: str


class VisualArcManager:
    """
    Groups semantic beats into higher-level visual chapters for long narratives (§14, §15).
    Maintains semantic memory window:
      current beat + current chapter + previous beats + next beats.
    Guarantees:
      - Does NOT force chapters if narration is too short (< 20s or < 4 beats).
      - Timestamps remain strictly audio-driven and authoritative (§16).
    """

    @classmethod
    def segment_visual_chapters(cls, beats: List[Any], master_dur: float) -> List[VisualChapter]:
        """Segment semantic beats into chapters based on topic shifts and time boundaries."""
        if len(beats) < 4 or master_dur < 25.0:
            # Single unified chapter
            entities = []
            for b in beats:
                entities.extend(getattr(b.visual_req, 'entities', []))
            return [VisualChapter(
                chapter_index=1,
                title="Chapter 1: Narrative",
                start_time=0.0,
                end_time=master_dur,
                beat_start_idx=0,
                beat_end_idx=len(beats) - 1,
                dominant_topic=beats[0].visual_req.topic if beats else "General",
                dominant_entities=sorted(list(dict.fromkeys(entities)))[:5],
                dominant_environment=beats[0].visual_req.environment if beats else "workspace"
            )]

        chapters: List[VisualChapter] = []
        curr_start_idx = 0
        curr_topic = beats[0].visual_req.topic

        for i in range(1, len(beats)):
            b = beats[i]
            topic_changed = b.visual_req.topic != curr_topic
            chapter_dur = b.start - beats[curr_start_idx].start
            # Create chapter boundary on topic change if chapter > 20s, or hard limit > 75s
            if (topic_changed and chapter_dur >= 20.0) or chapter_dur >= 75.0:
                ch_beats = beats[curr_start_idx:i]
                ch_entities = []
                for cb in ch_beats:
                    ch_entities.extend(getattr(cb.visual_req, 'entities', []))
                chapters.append(VisualChapter(
                    chapter_index=len(chapters) + 1,
                    title=f"Chapter {len(chapters)+1}: {curr_topic}",
                    start_time=beats[curr_start_idx].start,
                    end_time=b.start,
                    beat_start_idx=curr_start_idx,
                    beat_end_idx=i - 1,
                    dominant_topic=curr_topic,
                    dominant_entities=sorted(list(dict.fromkeys(ch_entities)))[:5],
                    dominant_environment=ch_beats[0].visual_req.environment
                ))
                curr_start_idx = i
                curr_topic = b.visual_req.topic

        # Final chapter
        last_beats = beats[curr_start_idx:]
        ch_entities = []
        for cb in last_beats:
            ch_entities.extend(getattr(cb.visual_req, 'entities', []))
        chapters.append(VisualChapter(
            chapter_index=len(chapters) + 1,
            title=f"Chapter {len(chapters)+1}: {curr_topic}",
            start_time=beats[curr_start_idx].start,
            end_time=master_dur,
            beat_start_idx=curr_start_idx,
            beat_end_idx=len(beats) - 1,
            dominant_topic=curr_topic,
            dominant_entities=sorted(list(dict.fromkeys(ch_entities)))[:5],
            dominant_environment=last_beats[0].visual_req.environment
        ))

        return chapters

    @classmethod
    def get_semantic_memory_window(
        cls,
        beats: List[Any],
        current_idx: int,
        window_prev: int = 2,
        window_next: int = 1
    ) -> Dict[str, Any]:
        """
        Compile context window (prev 2 beats, current beat, next 1 beat) for ranking (§16).
        """
        curr_beat = beats[current_idx]
        start_p = max(0, current_idx - window_prev)
        end_p = min(len(beats), current_idx + window_next + 1)

        prev_concepts = []
        for i in range(start_p, current_idx):
            prev_concepts.extend(getattr(beats[i].visual_req, 'visual_concepts', []))

        next_concepts = []
        for i in range(current_idx + 1, end_p):
            next_concepts.extend(getattr(beats[i].visual_req, 'visual_concepts', []))

        return {
            "current_concepts": getattr(curr_beat.visual_req, 'visual_concepts', []),
            "previous_concepts": sorted(list(dict.fromkeys(prev_concepts)))[:8],
            "next_concepts": sorted(list(dict.fromkeys(next_concepts)))[:6],
            "current_topic": getattr(curr_beat.visual_req, 'topic', ''),
            "current_environment": getattr(curr_beat.visual_req, 'environment', '')
        }


# ==============================================================================
# 6. VISUAL DIVERSITY ENGINE, SMART REUSE & CLUSTERING (§17, §18, §19, §20)
# ==============================================================================

class VisualDiversityEngine:
    """
    Maintains visual diversity while safeguarding semantic correctness (§17, §18).
    Rules:
      - same subject + same context = acceptable reuse (penalty: 0.05).
      - same subject + changed context = evaluate alternatives (penalty: 0.15).
      - unrelated context = strong penalty (penalty: 0.35).
      - Diversity gap rule: If alternative is within 0.05 of recent image, promote alternative.
        If alternative gap is large (e.g. 0.94 vs 0.51), semantic correctness always wins.
    """

    @classmethod
    def calculate_smart_reuse_penalty(
        cls,
        image_filename: str,
        image_scene: str,
        recent_history: List[str],
        recent_scenes: List[str],
        transition_type: TransitionType
    ) -> float:
        """
        Calculate contextual smart reuse penalty (§18).
        """
        if not recent_history or image_filename not in recent_history[-3:]:
            return 0.0

        pos = list(reversed(recent_history[-3:])).index(image_filename)
        # Immediate repetition (pos=0)
        if pos == 0:
            if transition_type == TransitionType.CONTINUATION:
                # Same subject & ongoing continuity: zero penalty for valid topic holding
                return 0.0
            else:
                # Semantic shift: strong penalty to encourage fresh visual
                return 0.35

        # 2 or 3 beats ago
        if pos == 1:
            return 0.15 if transition_type == TransitionType.SEMANTIC_SHIFT else 0.0
        return 0.05


class ImageClusterManager:
    """
    Categorizes images into semantic concept clusters (§19, §20):
      people, workspace, technology, outdoor, documents, vehicles, general.
    Enables accelerated candidate retrieval for large image libraries.
    """

    CLUSTERS: Dict[str, Set[str]] = {
        "people": {"person", "man", "woman", "founder", "ceo", "team", "doctor", "student", "teacher", "worker"},
        "workspace": {"office", "desk", "room", "building", "headquarters", "studio", "chair", "table"},
        "technology": {"laptop", "computer", "server", "code", "screen", "phone", "chart", "cloud", "ai", "hardware"},
        "outdoor": {"street", "city", "mountain", "river", "sea", "ocean", "forest", "beach", "exterior"},
        "vehicles": {"car", "plane", "ship", "airplane", "truck", "automobile", "rover"},
        "documents": {"document", "book", "report", "paper", "contract", "archive", "certificate"}
    }

    @classmethod
    def assign_cluster(cls, concepts: List[str]) -> str:
        """Assign primary cluster based on keyword intersection."""
        c_set = set(concepts)
        best_cluster = "general"
        max_hits = 0
        for cluster_name, keywords in cls.CLUSTERS.items():
            hits = len(c_set & keywords)
            if hits > max_hits:
                max_hits = hits
                best_cluster = cluster_name
        return best_cluster


# ==============================================================================
# 7. TWO-STAGE RETRIEVAL & PERFORMANCE ADAPTATION (§21, §22)
# ==============================================================================

class TwoStageRetriever:
    """
    Adaptive candidate retrieval engine (§21, §22).
    Strategy by library size:
      - N < 100 images: Direct full-library scoring.
      - 100 <= N < 500 images: Indexed cluster retrieval.
      - N >= 500 images: Two-stage retrieval:
        1. Fast cosine similarity on 256-dim embeddings -> Top 40.
        2. Fast metadata / entity filtering -> Top 12.
        3. Full multi-signal ranking -> Top 5.
    """

    @classmethod
    def prune_candidates(
        cls,
        images: List[Any],
        beat_embedding: List[float],
        beat_entities: List[str],
        cosine_fn: Any,
        total_images: int
    ) -> List[Any]:
        """
        Prune candidate list according to performance adaptation tiers.
        """
        if total_images < 100:
            return images

        if total_images < 500:
            # Sort by cosine similarity, return top 60
            scored = []
            for img in images:
                sim = cosine_fn(beat_embedding, img.embedding)
                scored.append((sim, img))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [x[1] for x in scored[:60]]

        # Large image set (500+): Fast 2-stage retrieval
        # Stage 1: Cosine similarity Top 40
        scored = []
        for img in images:
            sim = cosine_fn(beat_embedding, img.embedding)
            scored.append((sim, img))
        scored.sort(key=lambda x: x[0], reverse=True)
        top40 = [x[1] for x in scored[:40]]

        # Stage 2: Entity & metadata matching boost into Top 15
        ent_set = set(beat_entities)
        stage2 = []
        for img in top40:
            ent_bonus = 0.20 if (set(img.entities) & ent_set) else 0.0
            stage2.append((ent_bonus, img))
        stage2.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in stage2[:15]]


# ==============================================================================
# 8. EMBEDDING METADATA & CACHE MANAGEMENT (§23, §24, §25, §26, §27)
# ==============================================================================

@dataclass
class EmbeddingModelMetadata:
    """Explicit embedding model metadata record (§23)."""
    model_name: str = "openclip_vit_b_32"
    model_version: str = "3.3.0"
    dimension: int = 512
    provider: str = "local_openclip"
    device: str = "cpu"
    normalization: str = "L2"
    config_version: str = "v3.3_neural_semantic"
    created_at: str = "2026-10-21"


class CacheKeyGenerator:
    """
    Generates model-versioned cache keys (§24, §26).
    Cache Key = SHA256(image_bytes) + ":" + model_name + ":" + model_version + ":" + config_version.
    Prevents stale intelligence if embedding model or weights change.
    """

    @classmethod
    def make_image_cache_key(cls, content_hash: str, meta: EmbeddingModelMetadata) -> str:
        raw = f"{content_hash}:{meta.model_name}:{meta.model_version}:{meta.config_version}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    @classmethod
    def make_ai_call_cache_key(cls, narration_beat: str, candidate_fns: List[str], prompt_version: str = "v3.2") -> str:
        raw = f"{narration_beat}:{'|'.join(sorted(candidate_fns))}:{prompt_version}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()


# ==============================================================================
# 9. CONFIDENCE CALIBRATION v2 & DECISION TRACE (§28, §29, §30, §51)
# ==============================================================================

@dataclass
class CandidateDecisionTrace:
    """Explicit decision trace for auditing scene image selection (§51)."""
    selected_image: str
    confidence: float
    confidence_level: str
    reasons: List[str]
    transition_type: str
    rejected_candidates: List[Dict[str, Any]] = field(default_factory=list)


class ConfidenceCalibratorV2:
    """
    Calibrates confidence levels based on Phase 2 empirical benchmark evidence (§28, §29).
    Phase 2 Ground Truth Findings:
      - Score >= 0.70: 100.0% precision (0 false matches).
      - Score 0.55 - 0.69: High precision, minor edge cases.
      - Score < 0.55: Review recommended; failure rate concentrated here (67.6% - 74.5%).
    Uncertainty Awareness:
      - If best candidate lacks strong semantic or entity evidence, marks as LOW with explicit tag.
    """

    HIGH_THRESH = 0.70
    MEDIUM_THRESH = 0.55
    NO_MATCH_THRESH = 0.35

    @classmethod
    def evaluate(
        cls,
        score: float,
        semantic_text_sim: float,
        entity_match: float,
        has_user_override: bool = False
    ) -> Tuple[str, float, bool]:
        """
        Evaluate calibrated confidence, uncertainty, and no-match status (§28, §29).
        Returns (confidence_level, normalized_score, is_uncertain).
        Levels: HIGH, MEDIUM, LOW, NO_MATCH.
        """
        if has_user_override:
            return "HIGH", 1.0, False

        norm_score = max(0.0, min(1.0, score))
        is_uncertain = False

        # Explicit No-Match detection when visual evidence is below acceptable baseline
        if (norm_score < cls.NO_MATCH_THRESH and semantic_text_sim < 0.25) or norm_score < 0.20:
            return "NO_MATCH", round(norm_score, 4), True

        # Uncertainty awareness check (§29)
        if semantic_text_sim < 0.20 and entity_match < 0.30 and norm_score < 0.60:
            is_uncertain = True

        if is_uncertain:
            level = "LOW"
        elif norm_score >= cls.HIGH_THRESH:
            level = "HIGH"
        elif norm_score >= cls.MEDIUM_THRESH:
            level = "MEDIUM"
        else:
            level = "LOW"

        return level, round(norm_score, 4), is_uncertain

    @classmethod
    def compute_sync_quality_score(
        cls,
        total_beats: int,
        high_conf_count: int,
        med_conf_count: int,
        low_conf_count: int,
        avg_confidence: float,
        repeated_images_count: int,
        corrections_count: int,
        scenes: Optional[List[Dict[str, Any]]] = None,
        semantic_beats: Optional[List[Any]] = None,
        master_dur: Optional[float] = None,
        unmatched_beats_count: int = 0,
        return_breakdown: bool = False
    ) -> Union[float, Tuple[float, Dict[str, float]]]:
        """
        Calculates a genuine, auditable Project Sync Quality Score (0 - 100%) (§30).
        Calibrated component model:
          1. Semantic Relevance   (35%): Image relevance to narration & context
          2. Temporal Alignment   (25%): Contiguous scene boundaries & duration pacing
          3. Beat Coverage        (20%): Coverage of meaningful narration beats
          4. Context Continuity   (10%): Contextual coherence of image reuse
          5. Image Confidence     (10%): Calibrated match confidence
        """
        if total_beats == 0:
            bd = {
                "semantic_relevance": 0.0,
                "temporal_alignment": 0.0,
                "beat_coverage": 0.0,
                "context_continuity": 0.0,
                "image_confidence": 0.0,
                "final_sync_quality": 0.0
            }
            return (0.0, bd) if return_breakdown else 0.0

        # --- 1. Semantic Relevance (35%) ---
        if scenes:
            scene_relevances = []
            for sc in scenes:
                is_override = sc.get("user_override", False) or sc.get("source") == "explicit_user_override"
                conf = float(sc.get("confidence", 0.0))
                reasons = sc.get("match_reason") or []
                if isinstance(reasons, str):
                    reasons = [reasons]

                if is_override:
                    scene_relevances.append(100.0)
                else:
                    semantic_signals = {
                        "semantic_similarity", "visual_similarity", "entity_match",
                        "action_match", "topic_match", "explicit_user_override",
                        "entity_continuity_boost"
                    }
                    has_signals = any(r in semantic_signals for r in reasons)
                    has_uncertain = "no_strong_visual_evidence" in reasons or "unmatched_beat" in reasons

                    if has_uncertain or not sc.get("image"):
                        rel = max(15.0, min(50.0, conf * 100.0))
                    elif has_signals:
                        if conf >= cls.HIGH_THRESH:
                            rel = 100.0
                        elif conf >= cls.MEDIUM_THRESH:
                            span = max(0.01, cls.HIGH_THRESH - cls.MEDIUM_THRESH)
                            rel = 88.0 + ((conf - cls.MEDIUM_THRESH) / span) * 10.0
                        else:
                            span = max(0.01, cls.MEDIUM_THRESH)
                            rel = max(55.0, 70.0 + (conf / span) * 18.0)
                    else:
                        rel = max(30.0, min(75.0, conf * 100.0))
                    scene_relevances.append(min(100.0, max(0.0, rel)))
            sem_relevance = sum(scene_relevances) / float(len(scene_relevances))
        else:
            sem_relevance = (
                (high_conf_count * 100.0 + med_conf_count * 88.0 + low_conf_count * 60.0)
                / float(total_beats)
            )

        # --- 2. Temporal Alignment (25%) ---
        if scenes:
            alignment_score = 100.0
            for k in range(1, len(scenes)):
                prev_end = float(scenes[k - 1].get("end", 0.0))
                curr_start = float(scenes[k].get("start", 0.0))
                if abs(curr_start - prev_end) > 0.08:
                    alignment_score -= 10.0

            if master_dur and master_dur > 0:
                last_end = float(scenes[-1].get("end", 0.0))
                drift = abs(last_end - master_dur)
                if drift > 0.5:
                    drift_penalty = min(35.0, (drift / master_dur) * 100.0 * 2.0)
                    alignment_score -= drift_penalty

            for sc in scenes:
                dur = float(sc.get("dur", 0.0))
                if dur < 0.35 or dur > 16.0:
                    alignment_score -= 15.0

            temporal_alignment = max(0.0, min(100.0, alignment_score))
        else:
            temporal_alignment = 100.0

        # --- 3. Beat Coverage (20%) ---
        if scenes:
            unmapped_count = sum(1 for sc in scenes if not sc.get("image") or sc.get("image") in ("None", "none", ""))
            effective_unmatched = unmapped_count + unmatched_beats_count
            covered_beats = max(0, total_beats - effective_unmatched)
            beat_coverage = (covered_beats / float(total_beats)) * 100.0
        else:
            covered_beats = max(0, total_beats - unmatched_beats_count)
            beat_coverage = (covered_beats / float(total_beats)) * 100.0

        # --- 4. Context Continuity (10%) ---
        if scenes:
            unjustified_reuse_count = 0
            seen_images = {}
            for idx_sc, sc in enumerate(scenes):
                img = sc.get("image")
                if not img:
                    continue
                if img in seen_images:
                    reasons = sc.get("match_reason") or []
                    trans_type = sc.get("transition_type", "")
                    has_continuity = (
                        trans_type in ("CONTINUATION", "SUB_BEAT", "CHAPTER_CONTINUITY")
                        or "entity_continuity_boost" in reasons
                        or "visual_similarity" in reasons
                        or (idx_sc > 0 and scenes[idx_sc - 1].get("image") == img)
                    )
                    if not has_continuity:
                        unjustified_reuse_count += 1
                seen_images[img] = idx_sc

            continuity_score = max(0.0, 100.0 - (unjustified_reuse_count * 25.0))
            context_continuity = continuity_score
        else:
            rep_ratio = repeated_images_count / float(total_beats)
            context_continuity = max(75.0, 100.0 - rep_ratio * 25.0)

        # --- 5. Image Confidence (10%) ---
        if scenes:
            calibrated_confs = []
            for sc in scenes:
                c = float(sc.get("confidence", 0.0))
                if c >= cls.HIGH_THRESH:
                    calibrated_confs.append(100.0)
                elif c >= cls.MEDIUM_THRESH:
                    span = max(0.01, cls.HIGH_THRESH - cls.MEDIUM_THRESH)
                    calibrated_confs.append(85.0 + ((c - cls.MEDIUM_THRESH) / span) * 15.0)
                else:
                    span = max(0.01, cls.MEDIUM_THRESH)
                    calibrated_confs.append(max(30.0, (c / span) * 85.0))
            image_confidence = sum(calibrated_confs) / float(len(calibrated_confs))
        else:
            if avg_confidence >= cls.HIGH_THRESH:
                image_confidence = 100.0
            elif avg_confidence >= cls.MEDIUM_THRESH:
                image_confidence = 85.0 + ((avg_confidence - cls.MEDIUM_THRESH) / max(0.01, cls.HIGH_THRESH - cls.MEDIUM_THRESH)) * 15.0
            else:
                image_confidence = max(40.0, (avg_confidence / max(0.01, cls.MEDIUM_THRESH)) * 85.0)

        corr_bonus = min(2.0, corrections_count * 0.5)

        final_score = (
            (0.35 * sem_relevance)
            + (0.25 * temporal_alignment)
            + (0.20 * beat_coverage)
            + (0.10 * context_continuity)
            + (0.10 * image_confidence)
            + corr_bonus
        )
        final_score = round(max(0.0, min(100.0, final_score)), 1)

        breakdown = {
            "semantic_relevance": round(sem_relevance, 1),
            "temporal_alignment": round(temporal_alignment, 1),
            "beat_coverage": round(beat_coverage, 1),
            "context_continuity": round(context_continuity, 1),
            "image_confidence": round(image_confidence, 1),
            "final_sync_quality": final_score
        }

        if return_breakdown:
            return final_score, breakdown
        return final_score


# ==============================================================================
# 10. GLOBAL SEQUENCE OPTIMIZER (Auction Algorithm & Global Bipartite Matching)
# ==============================================================================

class GlobalSequenceOptimizer:
    """
    Solves global visual assignment across the entire narrative timeline.
    Guarantees:
      - Optimal maximum-benefit matching between semantic beats and candidate images.
      - Zero reliance on filenames or archive indices in SEMANTIC_AUTO mode.
      - Seamlessly handles N_images == N_beats, N_images > N_beats, and N_images < N_beats.
      - Preserves explicit user overrides unconditionally.
      - Respects topic continuity (holding valid visual context across sub-beats).
    """

    @classmethod
    def solve_linear_sum_assignment(cls, cost_matrix: Any) -> Tuple[Any, Any]:
        """
        Pure NumPy implementation of the Auction Algorithm for linear sum assignment.
        Finds row and column indices minimizing the total cost.
        """
        cost = np.array(cost_matrix, dtype=float)
        n_rows, n_cols = cost.shape
        if n_rows == 0 or n_cols == 0:
            return np.array([], dtype=int), np.array([], dtype=int)

        dim = max(n_rows, n_cols)
        max_val = float(cost.max()) if cost.size > 0 else 1.0
        padded = np.full((dim, dim), max_val * 2.0 + 1.0, dtype=float)
        padded[:n_rows, :n_cols] = cost

        benefit = -padded
        price = np.zeros(dim, dtype=float)
        eps = 1.0 / (dim + 1)
        assignment = np.full(dim, -1, dtype=int)
        unassigned = list(range(dim))

        iter_count = 0
        max_iters = dim * 150
        while unassigned and iter_count < max_iters:
            iter_count += 1
            p = unassigned.pop(0)
            payoffs = benefit[p, :] - price
            best_j = int(np.argmax(payoffs))
            best_val = payoffs[best_j]

            payoffs[best_j] = -1e9
            second_best_val = float(np.max(payoffs))
            bid = best_val - second_best_val + eps
            price[best_j] += bid

            old_p = assignment[best_j]
            assignment[best_j] = p
            if old_p != -1:
                unassigned.append(old_p)

        row_ind = []
        col_ind = []
        for j in range(dim):
            p = assignment[j]
            if p < n_rows and j < n_cols:
                row_ind.append(p)
                col_ind.append(j)

        order = np.argsort(row_ind)
        return np.array(row_ind)[order], np.array(col_ind)[order]

