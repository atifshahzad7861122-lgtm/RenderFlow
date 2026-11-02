#!/usr/bin/env python3
"""
engine/semantic_scene_analyzer.py — Contextual Scene Parser & Visual Requirement Synthesizer.

Transforms raw voiceover transcripts into structured, context-rich scene representations:
- Extracts subjects, entities, actions, environments, and emotional/temporal tones.
- Handles abstract and metaphorical narrative expressions (e.g., betrayal, fear, covert operations).
- Generates multi-prompt visual query ensembles for neural vision-language models.
- Preserves exact audio timestamps, word-level alignments, and speech cadence.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any

logger = logging.getLogger("rendering_studio.scene_analyzer")

# Lexicons for grammatical and thematic analysis
STOPWORDS: Set[str] = {
    'the', 'and', 'for', 'that', 'this', 'with', 'from', 'have', 'were', 'which',
    'then', 'they', 'their', 'been', 'what', 'when', 'will', 'more', 'about', 'into',
    'some', 'them', 'than', 'also', 'upon', 'over', 'scene', 'image', 'picture', 'there',
    'here', 'just', 'only', 'could', 'would', 'should', 'each', 'every', 'other'
}

ABSTRACT_CONCEPT_MAP: Dict[str, Dict[str, Any]] = {
    "fear": {
        "visual_cues": ["dark shadows", "silhouette", "empty cold street", "paranoid glance", "dramatic lighting"],
        "mood": "ominous",
        "energy": "tense"
    },
    "suspicion": {
        "visual_cues": ["whispering in secrecy", "covert surveillance", "looking over shoulder", "obscured faces"],
        "mood": "tense",
        "energy": "subtle"
    },
    "espionage": {
        "visual_cues": ["subterranean tunnel", "listening device", "cables and wires", "covert agent", "classified documents"],
        "mood": "covert",
        "energy": "tactical"
    },
    "betrayal": {
        "visual_cues": ["broken trust", "two men walking away in fog", "shadowy doorway", "shattered glass", "confrontation"],
        "mood": "somber",
        "energy": "dramatic"
    },
    "freedom": {
        "visual_cues": ["wide open sky", "breaking barriers", "crowd rejoicing", "daylight horizon", "open gates"],
        "mood": "uplifting",
        "energy": "expansive"
    },
    "conflict": {
        "visual_cues": ["soldiers in combat", "smoke and fire", "military barricade", "intense confrontation"],
        "mood": "aggressive",
        "energy": "explosive"
    },
    "industry": {
        "visual_cues": ["heavy machinery", "smoking factory chimneys", "assembly line", "industrial workers", "sparks"],
        "mood": "industrial",
        "energy": "rhythmic"
    },
    "nightlife": {
        "visual_cues": ["jazz club", "neon lights", "musical instruments", "smoky room", "performers on stage"],
        "mood": "vibrant",
        "energy": "rhythmic"
    }
}

@dataclass
class EnrichedVisualRequirement:
    """Multi-tiered visual representation extracted from narrative script."""
    subject: str = ""
    entities: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    environment: str = ""
    location: str = ""
    topic: str = "General Narration"
    emotional_tone: str = "neutral"
    energy_level: str = "medium"  # subtle, medium, high, explosive
    abstract_themes: List[str] = field(default_factory=list)
    visual_concepts: List[str] = field(default_factory=list)
    prompt_ensemble: List[str] = field(default_factory=list)

    @property
    def locations(self) -> List[str]:
        return [self.location] if self.location else []

    @property
    def abstract_concepts(self) -> List[str]:
        return self.abstract_themes

    @property
    def expanded_prompts(self) -> List[str]:
        return self.prompt_ensemble

class SemanticSceneAnalyzer:
    """
    Extracts high-fidelity semantic visual requirements from voiceover text.
    Handles literal objects as well as abstract and metaphorical narrative beats.
    """

    @classmethod
    def analyze_script_segment(cls, text: str, segment_index: int = 0) -> EnrichedVisualRequirement:
        clean_text = text.strip()
        words = [w.lower() for w in re.findall(r'[\w]{2,}', clean_text, re.UNICODE)]
        content_words = [w for w in words if w not in STOPWORDS]

        # 1. Identify abstract/metaphorical themes
        detected_themes = []
        cues_to_add = []
        emotional_tone = "neutral"
        energy_level = "medium"

        text_lower = clean_text.lower()
        for theme_key, meta in ABSTRACT_CONCEPT_MAP.items():
            # Check root or synonyms
            if theme_key in text_lower or any(syn in text_lower for syn in meta["visual_cues"]):
                detected_themes.append(theme_key)
                cues_to_add.extend(meta["visual_cues"])
                emotional_tone = meta["mood"]
                energy_level = meta["energy"]

        # Check emotional keywords
        if any(w in text_lower for w in ["fear", "paranoia", "terror", "chill", "suspicion", "dread"]):
            detected_themes.append("fear")
            emotional_tone = "tense"
            energy_level = "tense"
        if any(w in text_lower for w in ["secret", "subterranean", "underground", "espionage", "wiretap", "spy", "tunnel"]):
            detected_themes.append("espionage")
            emotional_tone = "covert"
        if any(w in text_lower for w in ["soldiers", "patrol", "military", "jeep", "army", "troops", "war", "battle"]):
            detected_themes.append("military")
            energy_level = "high"
        if any(w in text_lower for w in ["factory", "machine", "machinery", "industrial", "chimney", "workers"]):
            detected_themes.append("industry")
            energy_level = "rhythmic"
        if any(w in text_lower for w in ["jazz", "club", "music", "saxophone", "trumpet", "nightlife", "shop windows"]):
            detected_themes.append("nightlife")
            emotional_tone = "vibrant"
        if any(w in text_lower for w in ["checkpoint", "border", "barbed wire", "guard tower", "berlin", "wall"]):
            detected_themes.append("border_checkpoint")
            emotional_tone = "somber"

        # 2. Extract Entities, Actions, and Environments
        entities = []
        actions = []
        locations = []

        # Noun/Subject extraction heuristics
        for w in content_words:
            if w in ["soldiers", "guards", "troops", "workers", "agents", "officers", "men", "people", "students", "founder"]:
                entities.append(w)
            elif w in ["factory", "machines", "jeep", "jeeps", "wiretap", "checkpoint", "wire", "instruments", "trucks"]:
                entities.append(w)
            elif w in ["patrolling", "drove", "watched", "rebuilding", "hummed", "gripped", "took", "whispered", "listening"]:
                actions.append(w)
            elif w in ["berlin", "streets", "city", "border", "tunnel", "underground", "clubs", "windows", "sector"]:
                locations.append(w)

        subject = entities[0] if entities else ("speaker" if "i" in words else "scene")
        location = locations[0] if locations else ("city" if "city" in text_lower else "environment")

        # 3. Formulate Multi-Prompt Visual Query Ensemble for Neural Matcher
        prompts = [clean_text]
        # Direct photographic representation
        prompts.append(f"a photo of {clean_text.rstrip('.!?')}")
        # Thematic synthesis
        if detected_themes:
            theme_str = ", ".join(detected_themes[:3])
            prompts.append(f"a photo representing {theme_str}")
        if cues_to_add:
            cues_str = ", ".join(cues_to_add[:3])
            prompts.append(f"a cinematic visual showing {cues_str}")

        # Topic classification
        if "military" in detected_themes or "conflict" in detected_themes:
            topic = "Military & Conflict"
        elif "industry" in detected_themes:
            topic = "Industry & Economy"
        elif "nightlife" in detected_themes:
            topic = "Culture & Nightlife"
        elif "espionage" in detected_themes or "fear" in detected_themes:
            topic = "Covert & Espionage"
        elif "border_checkpoint" in detected_themes:
            topic = "Border & Division"
        else:
            topic = "General Narration"

        all_concepts = sorted(list(dict.fromkeys(content_words + cues_to_add)))[:15]

        return EnrichedVisualRequirement(
            subject=subject,
            entities=entities,
            actions=actions,
            environment=location,
            location=location,
            topic=topic,
            emotional_tone=emotional_tone,
            energy_level=energy_level,
            abstract_themes=detected_themes,
            visual_concepts=all_concepts,
            prompt_ensemble=prompts
        )
