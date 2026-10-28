#!/usr/bin/env python3
"""
RenderFlow — Release Packaging & Authenticated Manifest Builder
Builds lightweight patch updates and/or full installer release packages,
computes SHA-256 checksums, and signs update_manifest.json with Ed25519.
"""

import os
import sys
import json
import zipfile
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from engine.crypto_ed25519 import ed25519_sign, ed25519_verify, ed25519_sk_to_pk
from engine.version import GITHUB_OWNER, GITHUB_REPO

RELEASE_DIR = ROOT_DIR / "release"
TOOLS_DIR = ROOT_DIR / "tools"
PRIVATE_KEY_PATH = TOOLS_DIR / "release_signing_key.priv"
PUBLIC_KEY_PATH = TOOLS_DIR / "release_public_key.pub"

# Extensions and directory prefixes to skip in patch archives
EXCLUDED_PATTERNS = [
    "__pycache__", ".pyc", ".pyo", ".git", ".idea", ".vscode",
    "projects", ".tmp_uploads", "logs", "dist", "build", "release",
    ".gemini", ".env", "release_signing_key.priv", "*.tmp"
]


def compute_sha256(filepath: Path) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def should_include_file(rel_path_str: str) -> bool:
    rel_p = Path(rel_path_str)
    parts = rel_p.parts
    # Check directory exclusions
    for part in parts:
        if part in ("__pycache__", ".git", "projects", ".tmp_uploads", "logs", "dist", "build", "release", ".gemini"):
            return False
    # Check filename / extension exclusions
    name = rel_p.name
    if name.endswith((".pyc", ".pyo", ".priv", ".tmp")) or name.startswith("."):
        return False
    if name in (".env", "release_signing_key.priv"):
        return False
    return True


def create_patch_archive(target_version: str) -> Path:
    """Build lightweight zip containing updated engine, web, and config files."""
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    patch_zip_name = f"RenderFlow-Patch-v{target_version}.zip"
    patch_zip_path = RELEASE_DIR / patch_zip_name

    include_dirs = ["engine", "web", "config"]
    include_files = ["requirements.txt"]

    total_files = 0
    total_uncompressed_bytes = 0

    print(f"\n[1/4] Building lightweight patch zip: {patch_zip_name}")
    with zipfile.ZipFile(patch_zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for inc_dir in include_dirs:
            base_p = ROOT_DIR / inc_dir
            if not base_p.exists():
                continue
            for file_p in base_p.rglob("*"):
                if file_p.is_file():
                    rel = file_p.relative_to(ROOT_DIR).as_posix()
                    if should_include_file(rel):
                        zf.write(file_p, arcname=rel)
                        total_files += 1
                        total_uncompressed_bytes += file_p.stat().st_size

        for single_f in include_files:
            file_p = ROOT_DIR / single_f
            if file_p.is_file():
                zf.write(file_p, arcname=single_f)
                total_files += 1
                total_uncompressed_bytes += file_p.stat().st_size

    compressed_size = patch_zip_path.stat().st_size
    print(f"      Included {total_files} files.")
    print(f"      Uncompressed size: {total_uncompressed_bytes:,} bytes")
    print(f"      Compressed patch:  {compressed_size:,} bytes ({compressed_size / 1024 / 1024:.2f} MB)")
    return patch_zip_path


def load_signing_keys():
    if not PRIVATE_KEY_PATH.exists():
        raise FileNotFoundError(f"Private signing key not found at {PRIVATE_KEY_PATH}")
    priv_hex = PRIVATE_KEY_PATH.read_text(encoding="utf-8").strip()
    priv_bytes = bytes.fromhex(priv_hex)

    if PUBLIC_KEY_PATH.exists():
        pub_hex = PUBLIC_KEY_PATH.read_text(encoding="utf-8").strip()
        pub_bytes = bytes.fromhex(pub_hex)
    else:
        pub_bytes = ed25519_sk_to_pk(priv_bytes)
        pub_hex = pub_bytes.hex()
    return priv_bytes, pub_bytes, pub_hex


from typing import Optional

def build_and_sign_manifest(
    target_version: str,
    update_type: str,
    package_path: Path,
    release_notes: str,
    min_version: str = "2.0.0",
    manifest_name: str = "update_manifest.json",
    installer_path: Optional[Path] = None
) -> Path:
    print(f"\n[2/4] Computing package checksum and digital signature...")
    pkg_size = package_path.stat().st_size
    pkg_sha256 = compute_sha256(package_path)
    pkg_filename = package_path.name

    release_tag = f"v{target_version}"
    release_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/tag/{release_tag}"
    download_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/download/{release_tag}/{pkg_filename}"

    published_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest_data = {
        "manifest_version": "1.0",
        "latest_version": target_version,
        "minimum_supported_version": min_version,
        "release_notes": release_notes,
        "published_at": published_at,
        "release_page_url": release_url,
        "update_package_url": download_url,
        "package_size_bytes": pkg_size,
        "sha256": pkg_sha256,
        "update_type": update_type,
        "supported_platforms": ["windows-x64"]
    }

    if installer_path and installer_path.is_file():
        installer_size = installer_path.stat().st_size
        installer_sha256 = compute_sha256(installer_path)
        installer_filename = installer_path.name
        installer_download_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/download/{release_tag}/{installer_filename}"

        manifest_data["packages"] = {
            "patch": {
                "url": download_url,
                "package_size_bytes": pkg_size,
                "sha256": pkg_sha256,
                "applies_to": [">=2.0.0"]
            },
            "full": {
                "url": installer_download_url,
                "package_size_bytes": installer_size,
                "sha256": installer_sha256
            }
        }

    # Canonical serialization without signature
    canonical_json = json.dumps(manifest_data, sort_keys=True, separators=(',', ':'))
    canonical_bytes = canonical_json.encode("utf-8")

    priv_key, pub_key, pub_hex = load_signing_keys()
    sig_bytes = ed25519_sign(canonical_bytes, priv_key)
    sig_hex = sig_bytes.hex()

    manifest_data["signature"] = sig_hex
    manifest_data["public_key"] = pub_hex

    manifest_path = RELEASE_DIR / manifest_name
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    print(f"      Package SHA-256: {pkg_sha256}")
    if installer_path and installer_path.is_file():
        print(f"      Installer SHA-256: {installer_sha256}")
    print(f"      Ed25519 Sig:     {sig_hex[:32]}...")
    print(f"      Manifest saved:  {manifest_path}")

    # Self-verification check
    print(f"\n[3/4] Verifying generated manifest against embedded public key...")
    is_valid = ed25519_verify(canonical_bytes, sig_bytes, pub_key)
    if not is_valid:
        raise ValueError("CRITICAL: Generated manifest signature failed self-verification!")
    print(f"      Signature verification: PASSED (Ed25519 authentic)")
    return manifest_path


def generate_bundle_manifest(
    target_version: str,
    source_dir: Path,
    manifest_name: str = "bundle_manifest.json"
) -> Path:
    """Generate bundle inventory manifest indexing release files."""
    print(f"\nGenerating bundle manifest for {source_dir}...")
    tracked_dirs = {"bin", "transition_pack", "web", "models", "config", "engine"}
    files_map = {}
    total_bytes = 0

    for file_p in sorted(source_dir.rglob("*")):
        if not file_p.is_file():
            continue
        rel = file_p.relative_to(source_dir).as_posix()
        top_part = rel.split("/")[0]
        if top_part not in tracked_dirs:
            continue
        if should_include_file(rel):
            f_size = file_p.stat().st_size
            f_sha256 = compute_sha256(file_p)
            files_map[rel] = {
                "size": f_size,
                "sha256": f_sha256
            }
            total_bytes += f_size

    manifest = {
        "manifest_version": "1.0",
        "application": "RenderFlow",
        "version": target_version,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_files": len(files_map),
        "total_bytes": total_bytes,
        "files": files_map
    }

    out_path = RELEASE_DIR / manifest_name
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Bundle manifest saved: {out_path} ({len(files_map)} files, {total_bytes:,} bytes)")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="RenderFlow Release & Update Manifest Builder")
    parser.add_argument("--version", required=True, help="Semantic target version (e.g. 2.2.1)")
    parser.add_argument("--type", choices=["patch", "minor", "major"], default="patch", help="Update type")
    parser.add_argument("--notes", default="", help="Release notes text or path to notes file")
    parser.add_argument("--min-version", default="2.0.0", help="Minimum supported version")
    parser.add_argument("--installer", default=None, help="Path to full Windows installer")
    parser.add_argument("--manifest-name", default="update_manifest.json", help="Output filename for update manifest")
    parser.add_argument("--bundle-source", default=None, help="Source directory for generating bundle manifest")
    parser.add_argument("--bundle-name", default=None, help="Output filename for bundle manifest")

    args = parser.parse_args()

    notes = args.notes
    if notes and Path(notes).is_file():
        notes = Path(notes).read_text(encoding="utf-8")
    elif not notes:
        notes = f"RenderFlow v{args.version} Update\n• Production auto-update system\n• Performance optimizations and bug fixes."

    installer_path = Path(args.installer) if args.installer and Path(args.installer).is_file() else None
    if installer_path:
        print(f"Using full installer package: {installer_path}")

    # Generate patch archive
    patch_path = create_patch_archive(args.version)
    package_path = patch_path

    manifest_path = build_and_sign_manifest(
        target_version=args.version,
        update_type=args.type,
        package_path=package_path,
        release_notes=notes,
        min_version=args.min_version,
        manifest_name=args.manifest_name,
        installer_path=installer_path
    )

    if args.bundle_source and Path(args.bundle_source).is_dir():
        bundle_name = args.bundle_name or f"bundle_manifest_v{args.version}.json"
        generate_bundle_manifest(args.version, Path(args.bundle_source), bundle_name)

    print(f"\n[4/4] Release Build Complete!")
    print("=" * 60)
    print(f"Target Version:     v{args.version} ({args.type.upper()})")
    print(f"Patch Package:      {package_path.name} ({package_path.stat().st_size:,} bytes)")
    if installer_path:
        print(f"Full Installer:     {installer_path.name} ({installer_path.stat().st_size:,} bytes)")
    print(f"Update Manifest:    {manifest_path.name}")
    print("\nNext Steps to Publish Release:")
    print(f"  1. Commit and push any code changes.")
    print(f"  2. In GitHub, create release tag 'v{args.version}'.")
    print(f"  3. Upload the following files to the release assets:")
    print(f"       - release\\{package_path.name}")
    if installer_path:
        print(f"       - release\\{installer_path.name}")
    print(f"       - release\\update_manifest.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
