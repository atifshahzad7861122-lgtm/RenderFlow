"""
RenderFlow — Application Version & Metadata
===========================================
Single source of truth for RenderFlow workstation release versions.
"""

__version__ = "2.6.1"
APP_NAME = "RenderFlow"
APP_PUBLISHER = "AI With Atif"
BUILD_TARGET = "windows-x64"
GITHUB_OWNER = "atifshahzad7861122-lgtm"
GITHUB_REPO = "RenderFlow"
UPDATE_MANIFEST_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest/download/update_manifest.json"
UPDATE_MANIFEST_FALLBACK_URL = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main/release/update_manifest.json"
GITHUB_REPO_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"


