"""
qa/test_real_semantic_discrimination.py
Reproducible semantic intelligence and visual discrimination test using real, genuine photographs
downloaded via OpenMontage / NASA archives (not synthetic patterns).
"""
import pytest
import numpy as np
from pathlib import Path
from engine.semantic_vision import SemanticVisionModel
from engine.sync_engine_v3 import GlobalSequenceOptimizer

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "real_images"


def test_real_photographs_semantic_discrimination():
    """Verify that CLIP encodes genuine photographs and discriminates matching from non-matching text."""
    svm = SemanticVisionModel()
    
    astro_img = FIXTURES_DIR / "astronaut_moon.jpg"
    ocean_img = FIXTURES_DIR / "ocean_earth.jpg"
    plane_img = FIXTURES_DIR / "airplane_flight.jpg"
    
    assert astro_img.exists(), "Astronaut photo fixture missing"
    assert ocean_img.exists(), "Ocean photo fixture missing"
    assert plane_img.exists(), "Airplane photo fixture missing"
    
    # 1. Astronaut photo test
    emb_astro = svm.encode_image(astro_img)
    txt_astro = svm.encode_text("An Apollo astronaut in a spacesuit walking on the lunar surface of the moon")
    txt_kitchen = svm.encode_text("A modern kitchen with a chef baking bread and cooking food")
    
    sim_astro = float(np.dot(txt_astro, emb_astro))
    sim_kitchen = float(np.dot(txt_kitchen, emb_astro))
    diff_astro = sim_astro - sim_kitchen
    
    print(f"Astronaut: relevant={sim_astro:.4f}, irrelevant={sim_kitchen:.4f}, diff={diff_astro:+.4f}")
    assert diff_astro > 0.04, f"Astronaut discrimination margin too low ({diff_astro:.4f})"
    
    # 2. Ocean storm photo test
    emb_ocean = svm.encode_image(ocean_img)
    txt_ocean = svm.encode_text("Huge swirling storm clouds and cyclones over the deep blue ocean water")
    txt_train = svm.encode_text("A busy metropolitan train station with commuters rushing to work")
    
    sim_ocean = float(np.dot(txt_ocean, emb_ocean))
    sim_train = float(np.dot(txt_train, emb_ocean))
    diff_ocean = sim_ocean - sim_train
    
    print(f"Ocean: relevant={sim_ocean:.4f}, irrelevant={sim_train:.4f}, diff={diff_ocean:+.4f}")
    assert diff_ocean > 0.05, f"Ocean storm discrimination margin too low ({diff_ocean:.4f})"
    
    # 3. Airplane photo test
    emb_plane = svm.encode_image(plane_img)
    txt_plane = svm.encode_text("An experimental jet airplane and aircraft wing built for flight in a hangar")
    txt_jungle = svm.encode_text("A dense tropical rainforest with monkeys and exotic jungle flowers")
    
    sim_plane = float(np.dot(txt_plane, emb_plane))
    sim_jungle = float(np.dot(txt_jungle, emb_plane))
    diff_plane = sim_plane - sim_jungle
    
    print(f"Airplane: relevant={sim_plane:.4f}, irrelevant={sim_jungle:.4f}, diff={diff_plane:+.4f}")
    assert diff_plane > 0.04, f"Airplane discrimination margin too low ({diff_plane:.4f})"


def test_real_photographs_multibeat_assignment():
    """Verify that multi-signal ranking assigns each real photograph to its correct narrative beat."""
    svm = SemanticVisionModel()
    
    images = [
        ("astronaut_moon.jpg", FIXTURES_DIR / "astronaut_moon.jpg"),
        ("ocean_earth.jpg", FIXTURES_DIR / "ocean_earth.jpg"),
        ("airplane_flight.jpg", FIXTURES_DIR / "airplane_flight.jpg")
    ]
    
    image_embeddings = [svm.encode_image(path) for _, path in images]
    
    beats = [
        "An Apollo astronaut in a spacesuit walking on the lunar surface of the moon",
        "Huge swirling storm clouds and cyclones over the deep blue ocean water",
        "An experimental jet airplane and aircraft wing built for flight in a hangar"
    ]
    
    # Construct cost matrix (beats x images)
    cost_matrix = np.zeros((len(beats), len(images)), dtype=float)
    for b_idx, beat_text in enumerate(beats):
        txt_emb = svm.encode_text(beat_text)
        for i_idx, img_emb in enumerate(image_embeddings):
            sim = float(np.dot(txt_emb, img_emb))
            cost_matrix[b_idx, i_idx] = sim
            print(f"Beat {b_idx} vs Image {images[i_idx][0]}: {sim:.4f}")
    
    # Solve optimal global matching
    rows, cols = GlobalSequenceOptimizer.solve_linear_sum_assignment(-cost_matrix)
    
    # Expect 1-to-1 diagonal matching: Beat 0 -> Img 0, Beat 1 -> Img 1, Beat 2 -> Img 2
    for r, c in zip(rows, cols):
        print(f"Assigned Beat {r} -> {images[c][0]} (score: {cost_matrix[r, c]:.4f})")
        assert r == c, f"Beat {r} matched to wrong image {images[c][0]}"
