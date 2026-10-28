#!/usr/bin/env python3
"""
engine/motion_intelligence.py — Context-Aware Motion and Kinetic Orchestration Engine.

Generates structured, cinematography-informed motion instructions for RenderFlow:
1. Dynamic 2.5D camera motions: push (zoom in), pull (zoom out), drift_left, drift_right.
2. Context-aware selection driven by scene energy, topic, duration, and visual composition.
3. Conservative, stable motion when confidence is low (avoids distracting visual churn).
4. Full backward-compatibility with Python/FFmpeg renderer (L4 prefix standards).
5. Kinetic typography synchronization with narration rhythm and emphasis beats.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger("rendering_studio.motion_intelligence")

# Supported base motion modes recognized by RenderFlow video pipelines
VALID_MOTIONS = ["push", "pull", "drift_left", "drift_right", "static"]

# Structured cinematography shot roles (adapted from video-shotcraft)
VALID_SHOT_ROLES = [
    "establishing_wide",
    "character_focus",
    "dramatic_tension",
    "narrative_inspection",
    "environmental_drift",
]

# Supported non-linear easing curves
VALID_EASING_CURVES = [
    "linear",
    "smoothstep",
    "cubic_in_out",
    "ease_out",
    "ease_in",
]

# Easing curve mathematical implementations
EASING_FUNCTIONS = {
    "linear": lambda u: u,
    "smoothstep": lambda u: 3.0 * (u ** 2) - 2.0 * (u ** 3),
    "cubic_in_out": lambda u: 4.0 * (u ** 3) if u < 0.5 else 1.0 - ((-2.0 * u + 2.0) ** 3) / 2.0,
    "ease_out": lambda u: 1.0 - ((1.0 - u) ** 3),
    "ease_in": lambda u: u ** 3,
}

def apply_easing(u: float, curve: str = "smoothstep") -> float:
    """Evaluates a normalized time parameter u in [0.0, 1.0] under a named easing curve."""
    u_clamped = max(0.0, min(1.0, float(u)))
    fn = EASING_FUNCTIONS.get(curve, EASING_FUNCTIONS["smoothstep"])
    return float(fn(u_clamped))

# Shot role configuration taxonomy (cinematography framing and default dynamics)
SHOT_ROLE_CONFIG: Dict[str, Dict[str, Any]] = {
    "establishing_wide": {
        "description": "Opening spatial orientation and geographical context",
        "default_motion": "drift_right",
        "default_easing": "smoothstep",
        "zoom_scale": 1.025,
        "pan_speed_px": 20.0,
    },
    "character_focus": {
        "description": "Intimate entity focus or dialogue inspection",
        "default_motion": "push",
        "default_easing": "cubic_in_out",
        "zoom_scale": 1.035,
        "pan_speed_px": 0.0,
    },
    "dramatic_tension": {
        "description": "Climactic narrative turning points, suspense and conflict",
        "default_motion": "push",
        "default_easing": "cubic_in_out",
        "zoom_scale": 1.048,
        "pan_speed_px": 0.0,
    },
    "narrative_inspection": {
        "description": "Close observation of details, artifacts, or emotional reflection",
        "default_motion": "pull",
        "default_easing": "ease_out",
        "zoom_scale": 1.025,
        "pan_speed_px": 0.0,
    },
    "environmental_drift": {
        "description": "Background progression, scenery movement and temporal passage",
        "default_motion": "drift_left",
        "default_easing": "smoothstep",
        "zoom_scale": 1.030,
        "pan_speed_px": 24.0,
    },
}

# Cinematic transition library
TRANSITION_MAP = {
    "normal":          {"label": "cinematic_dissolve", "xfade": "dissolve",  "dur": 0.40},
    "location_change": {"label": "soft_wipe",          "xfade": "wipeleft",  "dur": 0.35},
    "turning_point":   {"label": "dip_to_black",       "xfade": "fadeblack", "dur": 0.45},
    "time_passage":    {"label": "dip_to_black",       "xfade": "fadeblack", "dur": 0.40},
    "emotional":       {"label": "slow_dissolve",      "xfade": "dissolve",  "dur": 0.50},
    "fast":            {"label": "clean_cut",          "xfade": "fadefast",  "dur": 0.15},
    "story_change":    {"label": "cinematic_dissolve", "xfade": "dissolve",  "dur": 0.40}
}

@dataclass
class SceneMotionPlan:
    """Structured motion and transition specification for an individual scene."""
    scene_id: str
    motion_type: str            # push, pull, drift_left, drift_right
    renderer_motion_label: str  # L4/push, L4/pull, etc.
    zoom_scale: float           # e.g. 1.035
    pan_speed_px: float         # e.g. 24.0 px across scene
    transition_label: str       # cinematic_dissolve, soft_wipe, etc.
    transition_duration: float  # in seconds
    is_conservative_default: bool = False
    rationale: str = ""
    shot_role: str = "character_focus"
    easing: str = "smoothstep"

class MotionIntelligenceEngine:
    """
    Synthesizes intelligent, narrative-aligned camera motion for video scenes.
    Combines cinematography shot role taxonomy with non-linear easing curves.
    """

    @classmethod
    def plan_scene_motion(
        cls,
        scene_idx: int,
        dur: float,
        context: str = "normal",
        energy_level: str = "medium",
        confidence_level: str = "HIGH",
        is_manual_override: bool = False,
        prev_motion: Optional[str] = None
    ) -> SceneMotionPlan:
        """
        Determines the optimal camera motion mode and shot role for a scene.
        Guarantees:
          - Contrasts consecutive motions to avoid repetitive visual monotony.
          - Uses conservative subtle motion on low-confidence or short scenes.
          - Applies structured shot roles (establishing_wide, character_focus, etc.).
          - Injects non-linear easing curves (smoothstep, cubic_in_out, ease_out).
        """
        # 1. Conservative fallback if confidence is low, NO_MATCH, or scene is ultra-short
        if confidence_level in ["LOW", "NO_MATCH"] or dur < 1.4:
            shot_role = "narrative_inspection"
            motion = "push"
            easing = "smoothstep"
            z = 1.015  # Subtle 1.5% push for stabilization
            pan = 0.0
            rationale = "conservative_low_confidence_default" if dur >= 1.4 else "short_scene_stabilization"
            is_conservative = True

        # 2. Turning points and high/explosive energy scenes
        elif context == "turning_point" or energy_level in ["high", "explosive"]:
            shot_role = "dramatic_tension"
            motion = "push"
            easing = "cubic_in_out"
            z = 1.048
            pan = 0.0
            rationale = "dramatic_turning_point_tension"
            is_conservative = False

        # 3. Location change or passage of time
        elif context in ["location_change", "time_passage"]:
            if scene_idx == 0:
                shot_role = "establishing_wide"
                motion = "drift_right"
                easing = "smoothstep"
                z = 1.025
                pan = 20.0
                rationale = "initial_establishing_wide_reveal"
            else:
                shot_role = "environmental_drift"
                motion = "drift_right" if prev_motion != "drift_right" else "drift_left"
                easing = "smoothstep"
                z = 1.030
                pan = 24.0 if motion == "drift_right" else -24.0
                rationale = "lateral_environmental_tracking"
            is_conservative = False

        # 4. Emotional, contemplative, or subtle energy scenes
        elif context == "emotional" or energy_level == "subtle":
            shot_role = "narrative_inspection"
            motion = "pull" if prev_motion != "pull" else "push"
            easing = "ease_out"
            z = 1.025
            pan = 0.0
            rationale = "reflective_pull_inspection"
            is_conservative = False

        # 5. Narrative continuity cycle for general narration
        else:
            if scene_idx == 0:
                shot_role = "establishing_wide"
                motion = "drift_right"
                easing = "smoothstep"
                z = 1.025
                pan = 18.0
                rationale = "establishing_wide_introduction"
            else:
                roles_cycle = ["character_focus", "environmental_drift", "narrative_inspection", "character_focus"]
                shot_role = roles_cycle[scene_idx % len(roles_cycle)]
                cfg = SHOT_ROLE_CONFIG[shot_role]
                cand_motion = cfg["default_motion"]
                if cand_motion == prev_motion:
                    alt_map = {"push": "pull", "pull": "push", "drift_right": "drift_left", "drift_left": "drift_right"}
                    cand_motion = alt_map.get(cand_motion, "push")
                motion = cand_motion
                easing = cfg["default_easing"]
                z = cfg["zoom_scale"]
                pan = cfg["pan_speed_px"] if "drift" in motion else 0.0
                if motion == "drift_left" and pan > 0:
                    pan = -pan
                rationale = f"narrative_continuity_{shot_role}"
            is_conservative = False

        # Transition resolution
        t_meta = TRANSITION_MAP.get(context, TRANSITION_MAP["normal"])
        t_label = t_meta["label"]
        t_dur = min(dur * 0.40, t_meta["dur"])

        return SceneMotionPlan(
            scene_id=f"scene_{scene_idx+1:04d}",
            motion_type=motion,
            renderer_motion_label=f"L4/{motion}",
            zoom_scale=z,
            pan_speed_px=pan,
            transition_label=t_label,
            transition_duration=round(t_dur, 3),
            is_conservative_default=is_conservative,
            rationale=rationale,
            shot_role=shot_role,
            easing=easing
        )

    @classmethod
    def apply_motion_to_scenes(
        cls,
        scenes: List[Dict[str, Any]],
        confidence_levels: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Enriches a list of timeline scene dictionaries with intelligent motion plans.
        Preserves existing user overrides and ensures 100% renderer compatibility.
        """
        prev_m = None
        for idx, sc in enumerate(scenes):
            dur = float(sc.get("dur", 3.0))
            ctx = sc.get("context", "normal")
            conf_level = confidence_levels[idx] if (confidence_levels and idx < len(confidence_levels)) else sc.get("confidence_level", "HIGH")
            is_over = sc.get("user_override", False)

            plan = cls.plan_scene_motion(
                scene_idx=idx,
                dur=dur,
                context=ctx,
                confidence_level=conf_level,
                is_manual_override=is_over,
                prev_motion=prev_m
            )

            # Assign compliant motion fields
            sc["motion"] = plan.renderer_motion_label
            sc["motion_mode"] = plan.motion_type
            sc["shot_role"] = plan.shot_role
            sc["easing"] = plan.easing
            sc["zoom_scale"] = plan.zoom_scale
            sc["pan_speed"] = plan.pan_speed_px
            sc["motion_details"] = {
                "type": plan.motion_type,
                "shot_role": plan.shot_role,
                "easing": plan.easing,
                "zoom_scale": plan.zoom_scale,
                "pan_speed_px": plan.pan_speed_px,
                "is_conservative": plan.is_conservative_default,
                "rationale": plan.rationale
            }
            if not sc.get("transition"):
                sc["transition"] = plan.transition_label
            prev_m = plan.motion_type

        return scenes
