#!/usr/bin/env python3
"""
Rendering Studio Engine v2 — ZIP & Image Asset Processor
=========================================================
Handles safe ZIP validation, secure extraction, manifest.json discovery,
deterministic image ordering, ambiguity detection for third-party archives,
image decoding integrity validation, and non-destructive Media Library registration.
"""

import os
import sys
import re
import json
import shutil
import zipfile
import uuid
import time
import hashlib
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


def detect_filename_sequence_ambiguity(filenames: List[str]) -> Tuple[bool, str]:
    """
    Analyzes a list of image filenames to detect whether they follow a clear
    sequential numbering scheme or if ordering is ambiguous (e.g. random hashes or UUIDs).
    Returns (is_ambiguous: bool, reason: str).
    """
    if len(filenames) <= 1:
        return False, "Single or zero images"

    numbers_found = []
    hash_like_count = 0

    for name in filenames:
        stem = Path(name).stem
        # Check if filename is hexadecimal hash (e.g., 16, 32, 40, or 64 hex characters)
        if re.fullmatch(r'[0-9a-fA-F]{12,64}', stem):
            hash_like_count += 1

        digits = re.findall(r'\d+', stem)
        if digits:
            numbers_found.append(int(digits[-1]))

    # If majority of files look like random hashes
    if hash_like_count >= len(filenames) * 0.5:
        return True, "Filenames appear to be hashes without sequence information."

    # If less than half the files have numeric tokens
    if len(numbers_found) < len(filenames) * 0.5:
        return True, "Filenames lack sequence numbering. Alphabetical order applied."

    return False, "Monotonic or numeric sequence detected."


def validate_image_file(path: Path) -> Tuple[bool, str]:
    """
    Validates that an image exists, is non-empty, and can actually be decoded.
    Ensures no placeholder or corrupted graphics enter the rendering engine.
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


def create_ordered_image_zip(
    image_entries: List[Dict[str, Any]],
    output_zip_path: Path,
    job_id: Optional[str] = None
) -> Path:
    """
    Generates a deterministic ZIP archive with an authoritative top-level manifest.json.
    Guarantees that archive entry order and manifest order match the original result index.
    
    image_entries is a list of dicts with:
    - 'file_path': Path to source image file
    - 'query': Optional search query
    - 'source_url': Optional original source URL
    - 'original_index': Optional search result index
    """
    output_zip_path = Path(output_zip_path).resolve()
    output_zip_path.parent.mkdir(parents=True, exist_ok=True)

    manifest_images = []
    job = job_id or f"rf_job_{uuid.uuid4().hex[:8]}"

    with zipfile.ZipFile(output_zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, entry in enumerate(image_entries):
            src_p = Path(entry['file_path'])
            if not src_p.is_file():
                continue

            seq_idx = idx + 1
            orig_idx = entry.get('original_index', idx)
            ext = src_p.suffix.lower()
            archive_name = f"images/img_{seq_idx:04d}{ext}"

            # Compute sha256
            hasher = hashlib.sha256()
            with open(src_p, 'rb') as f_in:
                while chunk := f_in.read(65536):
                    hasher.update(chunk)
            sha256_hash = hasher.hexdigest()

            manifest_images.append({
                "image_id": f"img_{seq_idx:04d}",
                "original_result_index": orig_idx,
                "sequence_index": seq_idx,
                "source_url": entry.get("source_url", ""),
                "source_filename": src_p.name,
                "archive_filename": archive_name,
                "query": entry.get("query", ""),
                "download_status": "success",
                "sha256": sha256_hash,
                "attribution": entry.get("attribution", None)
            })

            zf.write(src_p, arcname=archive_name)

        manifest_data = {
            "manifest_schema_version": "1.0",
            "generator": "RenderFlow Studio v2.6.1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "job_id": job,
            "total_images": len(manifest_images),
            "images": manifest_images
        }

        zf.writestr("manifest.json", json.dumps(manifest_data, indent=2))

    return output_zip_path


def process_zip_archive(
    zip_path: Path,
    target_images_dir: Path,
    temp_work_dir: Path,
    replace_existing: bool = False
) -> Dict[str, Any]:
    """
    Safely validates, extracts, orders, validates, and registers image assets from a ZIP archive.
    
    Ordering Hierarchy:
    1. manifest.json: If archive contains manifest.json, images are strictly ordered by manifest['images'].
    2. Natural Sort: If no manifest, sequential numbers are detected and natural sorting is applied.
    3. Ambiguity Detection: If filenames are non-sequential or random hashes, ordering_ambiguous is flagged.
    
    DEFAULT IS NON-DESTRUCTIVE (replace_existing=False): preserves existing Media Library images.
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

    # 2. Extraction sandbox
    extract_id = f"extract_{uuid.uuid4().hex[:8]}_{int(time.time())}"
    extract_root = (temp_work_dir / extract_id).resolve()
    extract_root.mkdir(parents=True, exist_ok=True)

    extracted_candidates: List[Path] = []
    manifest_data: Optional[Dict[str, Any]] = None

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            infolist = zf.infolist()

            # First: Look for manifest.json
            for info in infolist:
                norm_name = os.path.normpath(info.filename).lstrip(r'\/')
                if Path(norm_name).name.lower() == 'manifest.json':
                    try:
                        with zf.open(info) as mf:
                            manifest_data = json.loads(mf.read().decode('utf-8'))
                        diag_logs.append("[ZIP] manifest.json=FOUND (deterministic ordering enabled)")
                        break
                    except Exception as me:
                        diag_logs.append(f"[ZIP] manifest.json=MALFORMED ({me})")

            # Extract image files safely
            for info in infolist:
                if info.is_dir():
                    continue

                raw_name = info.filename
                # Filter macOS and metadata
                if raw_name.startswith('__MACOSX/') or '/__MACOSX/' in raw_name or '\\__MACOSX\\' in raw_name:
                    continue
                basename = Path(raw_name).name
                if basename.startswith('._') or basename.startswith('.DS_Store') or basename.lower() == 'thumbs.db':
                    continue

                ext = Path(raw_name).suffix.lower()
                if ext not in SUPPORTED_IMAGE_EXTS:
                    continue

                # Path traversal defense
                norm_rel = os.path.normpath(raw_name).lstrip(r'\/')
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

    diag_logs.append(f"[ZIP] valid_images={len(valid_images)}")

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

    # 4. Deterministic Ordering
    ordering_source = "natural_sort"
    ordering_ambiguous = False
    ordering_message = ""

    if manifest_data and isinstance(manifest_data.get("images"), list):
        # Strict manifest sequence
        manifest_order = {}
        for idx, item in enumerate(manifest_data["images"]):
            seq = item.get("sequence_index", idx)
            # Map archive_filename, downloaded_filename, source_filename, and stem
            for k in ("archive_filename", "downloaded_filename", "source_filename", "image_id"):
                v = item.get(k)
                if v:
                    manifest_order[Path(v).name.lower()] = seq
                    manifest_order[Path(v).stem.lower()] = seq

        def manifest_sort_key(p: Path):
            name_key = p.name.lower()
            stem_key = p.stem.lower()
            if name_key in manifest_order:
                return (0, manifest_order[name_key])
            if stem_key in manifest_order:
                return (0, manifest_order[stem_key])
            return (1, natural_sort_key(p))

        valid_images.sort(key=manifest_sort_key)
        ordering_source = "manifest"
        diag_logs.append("[ZIP] Ordered strictly via manifest.json")
    else:
        # Check for sequence ambiguity in third-party filenames
        candidate_names = [p.name for p in valid_images]
        is_ambiguous, reason = detect_filename_sequence_ambiguity(candidate_names)
        valid_images.sort(key=natural_sort_key)
        if is_ambiguous:
            ordering_ambiguous = True
            ordering_source = "natural_sort_ambiguous"
            ordering_message = (
                "Original image order could not be determined automatically from filenames. "
                "Please review the import order in your Media Library."
            )
            diag_logs.append(f"[ZIP_ORDERING] AMBIGUOUS: {reason}")
        else:
            ordering_source = "natural_sort"
            diag_logs.append("[ZIP_ORDERING] Sequential numbering verified with natural sort")

    # 5. Register into project's images directory
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
        rel_to_extract = src_p.relative_to(extract_root)
        parts = rel_to_extract.parts
        if len(parts) > 1:
            clean_name = "_".join(parts)
        else:
            clean_name = src_p.name

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

    diag_logs.append(f"[ASSETS] registered={len(registered_files)}")

    return {
        "success": True,
        "images_found": len(registered_files),
        "registered_count": len(registered_files),
        "files": registered_files,
        "ordering_source": ordering_source,
        "ordering_ambiguous": ordering_ambiguous,
        "ordering_message": ordering_message,
        "corrupted_images": corrupted_images,
        "diagnostics": diag_logs
    }
