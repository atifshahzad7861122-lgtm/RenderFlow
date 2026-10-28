#!/usr/bin/env python3
"""
Rendering Studio Engine v2 — ZIP & Image Asset Processor
Handles safe ZIP validation, secure extraction, recursive image discovery,
image decoding integrity validation, natural sorting, and scene asset registration.
"""

import os
import sys
import re
import shutil
import zipfile
import uuid
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Union
import PIL.Image

SUPPORTED_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}


def natural_sort_key(item: Union[str, Path]) -> list:
    """
    Deterministic natural sorting key.
    Splits string into numeric (int) and non-numeric (lowercase str) tokens.
    Guarantees 'img_1.png', 'img_2.png', ..., 'img_10.png' ordering.
    """
    p = Path(item)
    filename = p.name
    tokens = [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', filename)]
    path_tokens = [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(p))]
    return [tokens, path_tokens]


def validate_image_file(path: Path) -> Tuple[bool, str]:
    """
    Validates that an image exists, is non-empty, and can actually be decoded.
    Ensures no placeholder/corrupted graphics enter the rendering engine.
    """
    try:
        if not path.is_file():
            return False, "File does not exist"
        size = path.stat().st_size
        if size == 0:
            return False, "0 bytes (empty file)"

        with PIL.Image.open(path) as img:
            img.verify()

        # Load pixels to ensure no truncation or decoding errors
        with PIL.Image.open(path) as img:
            img.load()
            w, h = img.size
            if w < 8 or h < 8:
                return False, f"Degenerate dimensions ({w}x{h})"

        return True, "Valid"
    except Exception as e:
        return False, str(e)


def process_zip_archive(
    zip_path: Path,
    target_images_dir: Path,
    temp_work_dir: Path,
    replace_existing: bool = True
) -> Dict[str, Any]:
    """
    Safely validates, extracts, recursively discovers, validates, naturally sorts,
    and registers image assets from a ZIP archive.
    DEFAULT IS REPLACE MODE (replace_existing=True): cleans existing media before registering new images.
    """
    diag_logs: List[str] = []
    file_size_mb = round(zip_path.stat().st_size / (1024 * 1024), 2)
    diag_logs.append(f"[UPLOAD] filename={zip_path.name}")
    diag_logs.append(f"[UPLOAD] extension={zip_path.suffix.lower()}")
    diag_logs.append(f"[UPLOAD] size={file_size_mb}MB")

    # 1. Structure validation
    if not zipfile.is_zipfile(zip_path):
        diag_logs.append("[ZIP] validation=FAIL (not a valid zipfile)")
        return {
            "success": False,
            "error": "The uploaded file is not a valid ZIP archive.",
            "diagnostics": diag_logs,
            "images_found": 0,
            "registered_count": 0
        }

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            bad_file = zf.testzip()
            if bad_file is not None:
                diag_logs.append(f"[ZIP] validation=FAIL (corrupted CRC in {bad_file})")
                return {
                    "success": False,
                    "error": f"Corrupted file inside ZIP archive: {bad_file}",
                    "diagnostics": diag_logs,
                    "images_found": 0,
                    "registered_count": 0
                }
    except Exception as e:
        diag_logs.append(f"[ZIP] validation=FAIL ({e})")
        return {
            "success": False,
            "error": f"Failed reading ZIP archive: {e}",
            "diagnostics": diag_logs,
            "images_found": 0,
            "registered_count": 0
        }

    diag_logs.append("[ZIP] validation=PASS")

    # 2. Dedicated temporary extraction sandbox
    extract_id = f"extract_{uuid.uuid4().hex[:8]}_{int(time.time())}"
    extract_root = (temp_work_dir / extract_id).resolve()
    extract_root.mkdir(parents=True, exist_ok=True)

    extracted_candidates: List[Path] = []
    total_raw_entries = 0
    ignored_meta_entries = 0

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            infolist = zf.infolist()
            total_raw_entries = len(infolist)

            for info in infolist:
                if info.is_dir():
                    continue

                raw_name = info.filename
                # Filter macOS and hidden metadata
                if raw_name.startswith('__MACOSX/') or '/__MACOSX/' in raw_name or '\\__MACOSX\\' in raw_name:
                    ignored_meta_entries += 1
                    continue
                basename = Path(raw_name).name
                if basename.startswith('._') or basename.startswith('.DS_Store') or basename.lower() == 'thumbs.db':
                    ignored_meta_entries += 1
                    continue

                # Filter image extension
                ext = Path(raw_name).suffix.lower()
                if ext not in SUPPORTED_IMAGE_EXTS:
                    continue

                # Path Traversal Protection
                norm_rel = os.path.normpath(raw_name).lstrip(r'\/')
                # Disallow drive letters or parent directory jumps
                if ':' in norm_rel or norm_rel.startswith('..') or ('..' + os.sep) in norm_rel:
                    diag_logs.append(f"[SECURITY] Blocked path traversal attempt in zip entry: {raw_name}")
                    continue

                dest_file = (extract_root / norm_rel).resolve()
                try:
                    if hasattr(dest_file, 'is_relative_to'):
                        if not dest_file.is_relative_to(extract_root):
                            diag_logs.append(f"[SECURITY] Blocked path traversal attempt: {raw_name}")
                            continue
                    else:
                        if os.path.commonpath([str(extract_root), str(dest_file)]) != str(extract_root):
                            diag_logs.append(f"[SECURITY] Blocked path traversal attempt: {raw_name}")
                            continue
                except ValueError:
                    diag_logs.append(f"[SECURITY] Invalid target path in zip: {raw_name}")
                    continue

                dest_file.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(dest_file, 'wb') as dst:
                    shutil.copyfileobj(src, dst)

                extracted_candidates.append(dest_file)

    except Exception as e:
        shutil.rmtree(extract_root, ignore_errors=True)
        diag_logs.append(f"[ZIP] extraction=FAIL ({e})")
        return {
            "success": False,
            "error": f"Failed extracting ZIP archive: {e}",
            "diagnostics": diag_logs,
            "images_found": 0,
            "registered_count": 0
        }

    diag_logs.append(f"[ZIP] extraction=PASS (candidates={len(extracted_candidates)})")

    if not extracted_candidates:
        shutil.rmtree(extract_root, ignore_errors=True)
        diag_logs.append("[ZIP] images_found=0")
        return {
            "success": False,
            "error": "No valid PNG/JPG/JPEG/WEBP images were found in the ZIP archive.",
            "diagnostics": diag_logs,
            "images_found": 0,
            "registered_count": 0
        }

    # 3. Image Decoding Integrity Validation
    valid_images: List[Path] = []
    corrupted_images: List[Dict[str, str]] = []

    for img_path in extracted_candidates:
        ok, reason = validate_image_file(img_path)
        if ok:
            valid_images.append(img_path)
        else:
            corrupted_images.append({"file": img_path.name, "reason": reason})
            diag_logs.append(f"[IMAGE_VALIDATION] FAIL: {img_path.name} -> {reason}")

    diag_logs.append(f"[ZIP] images_found={len(valid_images)}")

    if not valid_images:
        shutil.rmtree(extract_root, ignore_errors=True)
        return {
            "success": False,
            "error": "All discovered image files in ZIP failed validation or were corrupt.",
            "corrupted_images": corrupted_images,
            "diagnostics": diag_logs,
            "images_found": 0,
            "registered_count": 0
        }

    # 4. Natural Sorting
    valid_images.sort(key=natural_sort_key)

    # 5. Register into project's images directory (Default: REPLACE MODE)
    target_images_dir.mkdir(parents=True, exist_ok=True)
    if replace_existing:
        removed_count = 0
        for old_img in list(target_images_dir.glob("*.*")):
            if old_img.is_file() and old_img.suffix.lower() in SUPPORTED_IMAGE_EXTS:
                try:
                    old_img.unlink()
                    removed_count += 1
                except Exception:
                    pass
        if removed_count > 0:
            diag_logs.append(f"[ASSETS] Replaced previous media: removed {removed_count} stale image(s)")

    registered_files: List[str] = []

    for idx, src_p in enumerate(valid_images):
        # Flatten nested paths gracefully (e.g., scene_01/img_01.png -> scene_01_img_01.png)
        rel_to_extract = src_p.relative_to(extract_root)
        parts = rel_to_extract.parts
        if len(parts) > 1:
            clean_name = "_".join(parts)
        else:
            clean_name = src_p.name

        # Ensure no collision in target_images_dir
        dest_target = target_images_dir / clean_name
        if dest_target.exists():
            stem = dest_target.stem
            ext = dest_target.suffix
            collision_num = 1
            while dest_target.exists():
                dest_target = target_images_dir / f"{stem}_{collision_num:03d}{ext}"
                collision_num += 1

        shutil.copy2(src_p, dest_target)
        registered_files.append(dest_target.name)

    # Clean up extraction workspace
    shutil.rmtree(extract_root, ignore_errors=True)

    # Final natural sort of registered files
    registered_files.sort(key=natural_sort_key)
    diag_logs.append(f"[ASSETS] registered={len(registered_files)}")

    return {
        "success": True,
        "images_found": len(registered_files),
        "registered_count": len(registered_files),
        "files": registered_files,
        "corrupted_images": corrupted_images,
        "diagnostics": diag_logs
    }
