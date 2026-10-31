"""
qa/test_openmontage_discovery_adapter.py
Unit and integration tests for OpenMontageAdapter, source availability, candidate ranking, and download safety.
"""
import pytest
import os
from pathlib import Path
from PIL import Image
from engine.openmontage_adapter import OpenMontageAdapter, DiscoveredAsset


def test_openmontage_sources_registration():
    adapter = OpenMontageAdapter()
    sources = adapter.get_available_sources()
    source_map = {s["id"]: s for s in sources}
    
    # Verify that open, keyless sources are registered
    assert "wikimedia" in source_map
    assert "nasa" in source_map
    assert "loc" in source_map
    assert "archive_org" in source_map
    
    # Keyless sources must be available immediately without credentials
    assert source_map["wikimedia"]["is_available"] is True
    assert source_map["nasa"]["is_available"] is True
    assert source_map["loc"]["is_available"] is True
    assert source_map["archive_org"]["is_available"] is True


def test_openmontage_candidate_validation(tmp_path):
    adapter = OpenMontageAdapter()
    
    # Create a synthetic valid test image (>1024 bytes)
    test_img_path = tmp_path / "test_discovery.png"
    import numpy as np
    arr = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    img.save(test_img_path, format="PNG")
    
    asset = DiscoveredAsset(
        asset_id="wiki_12345",
        source="wikimedia",
        source_id="12345",
        kind="image",
        title="Apollo 11 Liftoff",
        download_url="https://fake.url/image.jpg",
        source_url="https://fake.url/details",
        thumbnail_url="https://fake.url/thumb.jpg",
        creator="NASA",
        license="Public Domain",
        tags="apollo moon rocket",
        width=320,
        height=240,
        local_path=str(test_img_path)
    )
    
    assert asset.title == "Apollo 11 Liftoff"
    assert asset.width == 320
    assert asset.height == 240
    
    # Verify media validation
    is_valid = adapter._validate_media_file(test_img_path, "image")
    assert is_valid is True
    
    # Corrupted / invalid file test
    corrupt_path = tmp_path / "corrupt.png"
    with open(corrupt_path, "wb") as f:
        f.write(b"NOT_AN_IMAGE_HEADER_DATA")
    
    is_valid_corrupt = adapter._validate_media_file(corrupt_path, "image")
    assert is_valid_corrupt is False


def test_openmontage_search_graceful_handling():
    adapter = OpenMontageAdapter()
    
    # Search with empty query should return empty list gracefully
    results = adapter.discover_candidates_for_query(query="", media_type="image", max_candidates=5)
    assert isinstance(results, list)
    assert len(results) == 0
