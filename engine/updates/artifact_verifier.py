"""
engine/updates/artifact_verifier.py — Cryptographic Authentication & Integrity Verification
==========================================================================================
RFC 8032 Ed25519 digital signature authentication and SHA-256 integrity validation.
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, Any, Optional, Tuple

from engine.crypto_ed25519 import verify_signature, RENDERFLOW_MASTER_PUBLIC_KEY

logger = logging.getLogger("renderflow.updates.verifier")

ALLOWED_DOMAINS = {
    "github.com",
    "objects.githubusercontent.com",
    "github-releases.githubusercontent.com",
    "api.github.com",
    "raw.githubusercontent.com",
}


def canonicalize_manifest(manifest_dict: Dict[str, Any]) -> bytes:
    """
    Returns deterministic, canonical UTF-8 JSON bytes excluding signatures and public keys.
    Keys are sorted lexicographically and whitespace separators are strictly (',', ':').
    """
    clean_dict = {
        k: v for k, v in manifest_dict.items()
        if k not in ("signature_ed25519", "signature", "public_key")
    }
    return json.dumps(clean_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")


class ArtifactVerifier:
    """Enforces cryptographic signatures, hash integrity, and domain allowlists."""

    def __init__(self, master_public_key: Optional[str] = None):
        self.master_public_key = (master_public_key or RENDERFLOW_MASTER_PUBLIC_KEY).lower().strip()

    def verify_url_domain(self, url: str) -> bool:
        """Ensures asset URLs originate from official, allowed GitHub domains."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().split(":")[0]
            if os.environ.get("RENDERFLOW_STAGING_MODE") == "1":
                if domain in ("127.0.0.1", "localhost") or parsed.scheme.lower() == "file":
                    return True
            if parsed.scheme.lower() != "https":
                logger.warning("Rejected non-HTTPS URL: %s", url)
                return False
            if domain in ALLOWED_DOMAINS or any(domain.endswith("." + d) for d in ALLOWED_DOMAINS):
                return True
            logger.warning("Domain %s not in allowed GitHub domains", domain)
            return False
        except Exception as e:
            logger.error("Error validating URL domain: %s", e)
            return False

    def verify_manifest_signature(self, manifest_dict: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Cryptographically authenticates the Ed25519 signature of a release manifest.
        Returns: (is_valid: bool, error_reason: Optional[str])
        """
        sig_hex = manifest_dict.get("signature_ed25519") or manifest_dict.get("signature")
        if not sig_hex:
            return False, "Manifest lacks an Ed25519 digital signature."

        pub_hex = (manifest_dict.get("public_key") or self.master_public_key).lower().strip()
        if pub_hex != self.master_public_key:
            return False, f"Manifest signed by untrusted public key: {pub_hex} (expected: {self.master_public_key})"

        try:
            canonical_bytes = canonicalize_manifest(manifest_dict)
            sig_bytes = bytes.fromhex(sig_hex)
            pub_bytes = bytes.fromhex(pub_hex)

            is_valid = verify_signature(canonical_bytes, sig_bytes, pub_bytes)
            if is_valid:
                logger.info("Ed25519 signature verified successfully for manifest.")
                return True, None
            else:
                logger.error("Ed25519 signature verification FAILED for manifest.")
                return False, "Digital signature failed cryptographic verification (manifest tampered or corrupted)."
        except Exception as e:
            logger.error("Signature verification exception: %s", e)
            return False, f"Signature verification error: {e}"

    @staticmethod
    def compute_sha256(filepath: Path) -> str:
        """Computes the SHA-256 digest of a local file."""
        sha = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest().lower()

    def verify_file_integrity(
        self,
        filepath: Path,
        expected_sha256: str,
        expected_size: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifies local file exists, matches expected size (if provided), and exact SHA-256 hash.
        """
        if not filepath.exists() or not filepath.is_file():
            return False, f"Artifact file does not exist at {filepath}"

        actual_size = filepath.stat().st_size
        if expected_size is not None and expected_size > 0:
            if actual_size != expected_size:
                return False, f"Size mismatch: got {actual_size} bytes, expected {expected_size} bytes."

        actual_hash = self.compute_sha256(filepath)
        if actual_hash != expected_sha256.lower().strip():
            logger.error("Checksum mismatch for %s: got %s, expected %s", filepath.name, actual_hash, expected_sha256)
            return False, f"SHA-256 checksum mismatch: got {actual_hash[:16]}..., expected {expected_sha256[:16]}..."

        logger.info("SHA-256 checksum verified for %s: %s", filepath.name, actual_hash)
        return True, None
