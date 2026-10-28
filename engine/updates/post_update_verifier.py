"""
engine/updates/post_update_verifier.py — Post-Install Health & Version Verification
===================================================================================
Verifies backend readiness, endpoint availability, and truthful running version
following an application update. Eliminates false-positive success notifications.
"""

import time
import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, Tuple

from engine.updates.semver import SemVer

logger = logging.getLogger("renderflow.updates.post_verifier")


class PostUpdateVerifier:
    """Probes the newly spawned or restarted backend to verify health and version."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", max_wait_seconds: float = 45.0):
        self.base_url = base_url.rstrip("/")
        self.max_wait_seconds = max_wait_seconds

    def verify_running_application(
        self,
        target_version: str,
        poll_interval: float = 1.0
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Polls /api/system_status and /api/update/status until the backend reports the target version.
        Returns: (success: bool, error_message: Optional[str], status_details: Optional[Dict])
        """
        start_time = time.time()
        target_sem = SemVer(target_version)
        last_error = None
        server_alive = False

        logger.info("Beginning post-install verification for target version %s (max %ds)...", target_version, self.max_wait_seconds)

        while (time.time() - start_time) < self.max_wait_seconds:
            # 1. Probe backend readiness via /api/system_status
            try:
                sys_req = urllib.request.Request(
                    f"{self.base_url}/api/system_status",
                    headers={"User-Agent": "RenderFlow-PostUpdateVerifier"}
                )
                with urllib.request.urlopen(sys_req, timeout=2.0) as resp:
                    if resp.status == 200:
                        server_alive = True
            except Exception as e:
                last_error = f"Waiting for backend to start ({e})"
                time.sleep(poll_interval)
                continue

            # 2. If server responded, check /api/update/status for authoritative running version
            if server_alive:
                try:
                    stat_req = urllib.request.Request(
                        f"{self.base_url}/api/update/status",
                        headers={"User-Agent": "RenderFlow-PostUpdateVerifier"}
                    )
                    with urllib.request.urlopen(stat_req, timeout=2.0) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8"))
                            reported_version = data.get("current_version", "").strip()
                            if reported_version:
                                reported_sem = SemVer(reported_version)
                                if reported_sem >= target_sem:
                                    logger.info("Post-install verification SUCCESS: running version is v%s", reported_version)
                                    return True, None, data
                                else:
                                    logger.warning("Backend alive but reports older version v%s (target: v%s)", reported_version, target_version)
                                    last_error = f"Server is running older version v{reported_version}, but target version is v{target_version}."
                except Exception as e:
                    last_error = f"Error querying update status: {e}"

            time.sleep(poll_interval)

        if not server_alive:
            return False, f"Backend server failed to start on {self.base_url} within {self.max_wait_seconds} seconds.", None

        return False, last_error or f"Post-install verification timed out waiting for v{target_version}.", None
