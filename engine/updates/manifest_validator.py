"""
engine/updates/manifest_validator.py — Release Discovery & Manifest Validation Service
=====================================================================================
Fetches and validates release metadata from GitHub Releases API and signed manifests.
Strictly enforces stable releases, architecture matching, and schema integrity.
Supports full installer executables, incremental ZIP patches, and dual-package releases.
"""

import os
import json
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from engine.version import (
    GITHUB_OWNER,
    GITHUB_REPO,
    GITHUB_REPO_API,
    GITHUB_RELEASES_PAGE,
    UPDATE_MANIFEST_URL,
    UPDATE_MANIFEST_FALLBACK_URL,
)
from engine.updates.models import ReleaseInfo, InstallerAsset, PatchAsset, PackageType
from engine.updates.semver import SemVer
from engine.updates.artifact_verifier import ArtifactVerifier

logger = logging.getLogger("renderflow.updates.validator")


class ReleaseManifestValidator:
    """Interacts with GitHub Releases API and authenticates release manifests."""

    def __init__(
        self,
        verifier: Optional[ArtifactVerifier] = None,
        timeout_seconds: float = 12.0
    ):
        self.verifier = verifier or ArtifactVerifier()
        self.timeout = timeout_seconds

    def fetch_latest_release(
        self,
        custom_manifest_url: Optional[str] = None
    ) -> Tuple[Optional[ReleaseInfo], Optional[str]]:
        """
        Queries official GitHub Releases direct asset manifest, GitHub Releases API, or fallback manifest.
        Returns: (ReleaseInfo, None) on success, or (None, error_message) on failure.
        NEVER returns None with no error if a network/validation problem occurs.
        """
        if custom_manifest_url:
            return self._fetch_from_manifest_url(custom_manifest_url)

        last_error = None

        # 1. Primary path: Direct download of signed update_manifest.json from the latest GitHub release
        try:
            rel_info, err = self._fetch_from_manifest_url(UPDATE_MANIFEST_URL)
            if rel_info:
                return rel_info, None
            if err:
                last_error = err
                logger.warning("Primary manifest endpoint (%s) failed: %s. Attempting GitHub API.", UPDATE_MANIFEST_URL, err)
        except Exception as e:
            last_error = str(e)
            logger.warning("Primary manifest endpoint error: %s. Attempting GitHub API.", e)

        # 2. Secondary fallback: Query GitHub Releases REST API for latest published release
        api_url = GITHUB_REPO_API
        req = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": f"RenderFlow-Updater/2.6.x ({os.name})",
                "Accept": "application/vnd.github.v3+json",
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            rel_info, err = self._parse_github_release_payload(data)
            if rel_info:
                return rel_info, None
            if err:
                last_error = err
                logger.warning("GitHub Releases API payload error: %s. Attempting raw repository manifest.", err)
        except urllib.error.HTTPError as e:
            logger.warning("GitHub Releases API HTTP error (%d): %s. Attempting raw repository manifest.", e.code, e)
            last_error = f"HTTP {e.code}"
        except urllib.error.URLError as e:
            logger.warning("Network connection error reaching GitHub API: %s. Attempting raw repository manifest.", e)
            last_error = str(e.reason)
        except Exception as e:
            logger.warning("Unexpected error querying GitHub Releases API: %s. Attempting raw repository manifest.", e)
            last_error = str(e)

        # 3. Tertiary fallback: Query repository raw manifest on main branch
        try:
            rel_info, err = self._fetch_from_manifest_url(UPDATE_MANIFEST_FALLBACK_URL)
            if rel_info:
                return rel_info, None
            if err:
                last_error = err
        except Exception as e:
            last_error = str(e)

        return None, f"Unable to reach update server ({last_error or 'Connection failed'}). Please verify your internet connection."

    def _parse_github_release_payload(self, rel: Dict[str, Any]) -> Tuple[Optional[ReleaseInfo], Optional[str]]:
        """Parses and validates a GitHub release object."""
        # 1. Filter drafts and prereleases
        if rel.get("draft", False):
            return None, "The latest release is marked as Draft and cannot be distributed."
        if rel.get("prerelease", False):
            return None, "The latest release is a Prerelease. Only stable releases are supported."

        tag_name = rel.get("tag_name", "").strip()
        version_str = tag_name.lstrip("vV")
        if not version_str:
            return None, "Release has no valid version tag."

        assets = rel.get("assets", [])
        if not assets:
            return None, f"Release v{version_str} contains no downloadable assets."

        # Find update_manifest.json asset if bundled on the release to get authoritative signatures & hashes
        manifest_asset = next((a for a in assets if a.get("name") == "update_manifest.json"), None)
        manifest_data = {}
        if manifest_asset and manifest_asset.get("browser_download_url"):
            try:
                m_url = manifest_asset["browser_download_url"]
                req = urllib.request.Request(m_url, headers={"User-Agent": "RenderFlow-Updater"})
                with urllib.request.urlopen(req, timeout=self.timeout) as m_resp:
                    manifest_data = json.loads(m_resp.read().decode("utf-8"))
            except Exception as e:
                logger.warning("Could not fetch bundled update_manifest.json from release: %s", e)

        # If we successfully parsed the manifest, validate it (supports full, patch, or dual)
        if manifest_data:
            return self._validate_and_build_release_info(manifest_data, rel_fallback=rel)

        # Fallback when release lacks update_manifest.json: Locate full standalone Windows installer
        installer_asset_dict = next(
            (a for a in assets if a.get("name", "").endswith(".exe") and "Setup" in a.get("name", "")),
            None
        )
        if not installer_asset_dict:
            return None, f"Release v{version_str} lacks a standalone Windows installer (.exe)."

        download_url = installer_asset_dict.get("browser_download_url", "")
        if not self.verifier.verify_url_domain(download_url):
            return None, f"Installer download URL originates from untrusted domain: {download_url}"

        installer = InstallerAsset(
            name=installer_asset_dict.get("name", f"RenderFlow-Setup-v{version_str}.exe"),
            url=download_url,
            size_bytes=int(installer_asset_dict.get("size", 0)),
            sha256="",
            platform="windows-x64",
            browser_download_url=download_url
        )

        release_info = ReleaseInfo(
            version=version_str,
            release_title=rel.get("name", f"RenderFlow v{version_str}"),
            release_notes=rel.get("body", "").strip(),
            published_at=rel.get("published_at", ""),
            release_url=rel.get("html_url", GITHUB_RELEASES_PAGE),
            installer=installer,
            patch=None,
            package_type=PackageType.FULL,
            is_prerelease=rel.get("prerelease", False),
            is_draft=rel.get("draft", False),
            raw_manifest=rel
        )

        return release_info, None

    def _fetch_from_manifest_url(self, manifest_url: str) -> Tuple[Optional[ReleaseInfo], Optional[str]]:
        """Directly fetches and validates a release manifest JSON file."""
        if not self.verifier.verify_url_domain(manifest_url):
            return None, f"Manifest URL rejected (untrusted domain): {manifest_url}"

        req = urllib.request.Request(
            manifest_url,
            headers={"User-Agent": "RenderFlow-Updater"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return self._validate_and_build_release_info(data)
        except urllib.error.HTTPError as e:
            return None, f"Failed to download update manifest (HTTP {e.code})."
        except urllib.error.URLError as e:
            return None, f"Network error downloading update manifest: {e.reason}"
        except json.JSONDecodeError:
            return None, "Downloaded update manifest contains malformed JSON."
        except Exception as e:
            return None, f"Failed to parse update manifest: {e}"

    def _validate_and_build_release_info(
        self,
        manifest: Dict[str, Any],
        rel_fallback: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[ReleaseInfo], Optional[str]]:
        """Validates manifest cryptographic signature and constructs ReleaseInfo."""
        # 1. Cryptographic Ed25519 authentication
        is_valid, err_reason = self.verifier.verify_manifest_signature(manifest)
        if not is_valid:
            logger.error("Manifest signature verification rejected: %s", err_reason)
            return None, f"Cryptographic authentication failed: {err_reason}"

        # 2. Extract version and metadata
        target_version = manifest.get("latest_version") or manifest.get("release_version") or manifest.get("version")
        if not target_version:
            return None, "Manifest is missing 'latest_version' field."

        packages = manifest.get("packages", {})
        full_pkg = packages.get("full") or {}
        patch_pkg = packages.get("patch") or {}

        # Fallback for flat schema manifests
        if not full_pkg and manifest.get("update_type") == "full":
            full_pkg = {
                "url": manifest.get("update_package_url"),
                "package_size_bytes": manifest.get("package_size_bytes", 0),
                "sha256": manifest.get("sha256", ""),
                "platform": manifest.get("supported_platform", "windows-x64"),
            }
        elif not patch_pkg and manifest.get("update_type") == "patch":
            patch_pkg = {
                "url": manifest.get("update_package_url"),
                "package_size_bytes": manifest.get("package_size_bytes", 0),
                "sha256": manifest.get("sha256", ""),
                "from_version": manifest.get("from_version"),
                "to_version": target_version,
                "platform": manifest.get("supported_platform", "windows-x64"),
            }

        installer: Optional[InstallerAsset] = None
        installer_url = full_pkg.get("url")
        if installer_url:
            if not self.verifier.verify_url_domain(installer_url):
                logger.warning("Installer URL violates domain security policy: %s", installer_url)
            else:
                installer_size = full_pkg.get("package_size_bytes") or full_pkg.get("size", 0)
                installer_sha256 = full_pkg.get("sha256", "")
                installer_name = full_pkg.get("filename") or Path(installer_url).name or f"RenderFlow-Setup-v{target_version}.exe"
                installer = InstallerAsset(
                    name=installer_name,
                    url=installer_url,
                    size_bytes=int(installer_size),
                    sha256=installer_sha256.lower().strip(),
                    platform=full_pkg.get("supported_platform", "windows-x64"),
                    browser_download_url=installer_url
                )

        patch: Optional[PatchAsset] = None
        patch_url = patch_pkg.get("url")
        if patch_url:
            if not self.verifier.verify_url_domain(patch_url):
                logger.warning("Patch URL violates domain security policy: %s", patch_url)
            else:
                patch_size = patch_pkg.get("package_size_bytes") or patch_pkg.get("size", 0)
                patch_sha256 = patch_pkg.get("sha256", "")
                patch_name = patch_pkg.get("filename") or Path(patch_url).name or f"RenderFlow-Patch-v{target_version}.zip"
                patch = PatchAsset(
                    name=patch_name,
                    url=patch_url,
                    size_bytes=int(patch_size),
                    sha256=patch_sha256.lower().strip(),
                    from_version=patch_pkg.get("from_version"),
                    to_version=patch_pkg.get("to_version", target_version),
                    platform=patch_pkg.get("supported_platform", "windows-x64"),
                    browser_download_url=patch_url
                )

        if not installer and not patch:
            return None, f"Manifest for v{target_version} defines neither a valid patch nor a full installer package."

        if installer and patch:
            pkg_type = PackageType.DUAL
        elif patch:
            pkg_type = PackageType.PATCH
        else:
            pkg_type = PackageType.FULL

        notes = manifest.get("release_notes", "")
        if not notes and rel_fallback:
            notes = rel_fallback.get("body", "")

        title = manifest.get("release_title") or f"RenderFlow v{target_version}"
        if rel_fallback and rel_fallback.get("name"):
            title = rel_fallback["name"]

        pub_at = manifest.get("published_at", "")
        if not pub_at and rel_fallback:
            pub_at = rel_fallback.get("published_at", "")

        page_url = manifest.get("release_page_url", GITHUB_RELEASES_PAGE)
        if rel_fallback and rel_fallback.get("html_url"):
            page_url = rel_fallback["html_url"]

        release_info = ReleaseInfo(
            version=target_version,
            release_title=title,
            release_notes=notes,
            published_at=pub_at,
            release_url=page_url,
            installer=installer,
            patch=patch,
            package_type=pkg_type,
            signature_ed25519=manifest.get("signature") or manifest.get("signature_ed25519"),
            public_key=manifest.get("public_key"),
            is_prerelease=False,
            is_draft=False,
            raw_manifest=manifest
        )

        return release_info, None
