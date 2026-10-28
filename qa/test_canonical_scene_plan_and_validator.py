"""
qa/test_canonical_scene_plan_and_validator.py
Unit and regression tests for CanonicalScene, CanonicalStoryboardPlan, and TimelineValidator.
"""
import pytest
from pathlib import Path
from engine.canonical_scene_plan import (
    WordAlignmentRef,
    CandidateAssetScore,
    CanonicalScene,
    CanonicalStoryboardPlan
)
from engine.timeline_validator import TimelineValidator, TimelineValidationResult


def test_canonical_scene_plan_roundtrip():
    plan = CanonicalStoryboardPlan(
        project_id="test_proj_001",
        audio_path="projects/king/audio.mp3",
        total_duration=12.5
    )
    
    scene1 = CanonicalScene(
        scene_id="scene_0001",
        sequence_index=0,
        start=0.0,
        end=6.0,
        dur=6.0,
        transcript_text="The ancient Roman Colosseum stood majestically under the golden sun.",
        visual_intent="A grand historical view of the Roman Colosseum with warm sunlight.",
        main_subjects=["Colosseum", "Rome", "monument"],
        required_objects=["ancient stones", "sunlight"],
        actions=["standing majestically"],
        setting="Rome, Italy",
        mood="epic and historical",
        suggested_shot_type="wide angle",
        search_queries=["Roman Colosseum exterior", "ancient Rome monument"],
        selected_image="image_1.png",
        selected_asset_id="asset_colosseum_01",
        selection_rationale="High semantic alignment with Colosseum prompt",
        semantic_confidence=0.92,
        timing_confidence=0.98,
        validation_state="VALID",
        transition="crossfade",
        transition_dur=1.0,
        word_timestamps=[
            WordAlignmentRef(word="The", start=0.0, end=0.3, confidence=0.99),
            WordAlignmentRef(word="ancient", start=0.3, end=0.8, confidence=0.97),
            WordAlignmentRef(word="Roman", start=0.8, end=1.4, confidence=0.95),
            WordAlignmentRef(word="Colosseum", start=1.4, end=2.2, confidence=0.98)
        ],
        candidate_scores=[
            CandidateAssetScore(asset_id="asset_colosseum_01", filename="image_1.png", total_score=0.92, source="local"),
            CandidateAssetScore(asset_id="asset_wrong_02", filename="image_2.png", total_score=0.31, source="local")
        ]
    )
    
    scene2 = CanonicalScene(
        scene_id="scene_0002",
        sequence_index=1,
        start=6.0,
        end=12.5,
        dur=6.5,
        transcript_text="Thousands of spectators gathered for the gladiatorial games.",
        visual_intent="Crowds of Roman citizens gathered inside the arena stands.",
        main_subjects=["spectators", "gladiators", "arena"],
        search_queries=["Roman arena crowd", "gladiators in arena"],
        selected_image="image_2.png",
        selected_asset_id="asset_arena_02",
        selection_rationale="Semantic match for Roman arena crowd",
        semantic_confidence=0.87,
        validation_state="VALID",
        transition="dip_black",
        transition_dur=0.5
    )
    
    plan.scenes.append(scene1)
    plan.scenes.append(scene2)
    
    assert len(plan.scenes) == 2
    assert plan.total_duration == 12.5
    
    # Test dictionary serialization and deserialization
    plan_dict = plan.to_dict()
    restored_plan = CanonicalStoryboardPlan.from_dict(plan_dict)
    
    assert restored_plan.project_id == "test_proj_001"
    assert len(restored_plan.scenes) == 2
    assert restored_plan.scenes[0].scene_id == "scene_0001"
    assert restored_plan.scenes[0].semantic_confidence == 0.92
    assert len(restored_plan.scenes[0].word_timestamps) == 4
    assert len(restored_plan.scenes[0].candidate_scores) == 2
    assert restored_plan.scenes[0].word_timestamps[3].word == "Colosseum"
    assert restored_plan.scenes[1].transition == "dip_black"


def test_timeline_validator_valid_sequence():
    validator = TimelineValidator(audio_drift_tolerance_sec=0.08)
    
    scenes = [
        {
            "scene_id": "scene_0001",
            "start": 0.0,
            "end": 5.0,
            "dur": 5.0,
            "image": "image_1.png",
            "transition": "cinematic_dissolve",
            "transition_dur": 0.4
        },
        {
            "scene_id": "scene_0002",
            "start": 5.0,
            "end": 10.0,
            "dur": 5.0,
            "image": "image_2.png",
            "transition": "none",
            "transition_dur": 0.0
        }
    ]
    
    plan_data = {"scenes": scenes}
    result = validator.validate_plan(plan_data, master_audio_dur=10.0, check_files=False)
    assert result.is_valid is True
    assert len(result.issues) == 0


def test_timeline_validator_detects_temporal_errors():
    validator = TimelineValidator()
    
    # 1. Negative start time
    plan1 = {"scenes": [{"scene_id": "sc1", "start": -1.0, "end": 4.0, "dur": 5.0, "image": "image_1.png"}]}
    res1 = validator.validate_plan(plan1, master_audio_dur=4.0, check_files=False)
    assert res1.is_valid is False
    assert any("negative" in i.message.lower() for i in res1.issues)
    
    # 2. End time before start time
    plan2 = {"scenes": [{"scene_id": "sc1", "start": 5.0, "end": 2.0, "dur": -3.0, "image": "image_1.png"}]}
    res2 = validator.validate_plan(plan2, master_audio_dur=5.0, check_files=False)
    assert res2.is_valid is False
    assert any("end" in i.message.lower() and "start" in i.message.lower() for i in res2.issues)
    
    # 3. Gap between scenes
    plan3 = {"scenes": [
        {"scene_id": "sc1", "start": 0.0, "end": 4.0, "dur": 4.0, "image": "image_1.png"},
        {"scene_id": "sc2", "start": 4.8, "end": 8.0, "dur": 3.2, "image": "image_2.png"}
    ]}
    res3 = validator.validate_plan(plan3, master_audio_dur=8.0, check_files=False)
    assert res3.is_valid is False
    assert any("gap" in i.message.lower() for i in res3.issues)


def test_timeline_validator_audio_drift():
    validator = TimelineValidator(audio_drift_tolerance_sec=0.08)
    
    # Timeline ends at 10.0s, audio is 10.5s -> drift is 0.5s > 0.08s
    plan = {"scenes": [{"scene_id": "sc1", "start": 0.0, "end": 10.0, "dur": 10.0, "image": "image_1.png"}]}
    res = validator.validate_plan(plan, master_audio_dur=10.5, check_files=False)
    assert res.is_valid is False
    assert any("drift" in i.message.lower() for i in res.issues)
