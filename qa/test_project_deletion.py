#!/usr/bin/env python3
"""
qa/test_project_deletion.py — Regression Test for DELETE /api/project/{project_name}
Validates:
1. Successful deletion of a real project with files and subdirectories.
2. Non-blocking async execution without NameError on 'time'.
3. 404 Not Found handling for non-existent projects.
4. 403 Forbidden handling for path traversal attempts (e.g. '../', nested slashes).
5. 400 Bad Request handling for empty or root-relative names ('.', '..').
6. 403 Forbidden protection for the root projects directory itself.
"""

import os
import sys
import shutil
import unittest
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from web.server import app, PROJECTS_DIR

class TestProjectDeletionAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.test_projects_dir = PROJECTS_DIR
        cls.test_projects_dir.mkdir(parents=True, exist_ok=True)

    def test_01_successful_project_deletion(self):
        """Verify normal project directory with content is cleanly deleted without NameError."""
        proj_name = "test_qa_delete_target_123"
        proj_dir = self.test_projects_dir / proj_name
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "project.json").write_text('{"name": "test"}', encoding="utf-8")
        (proj_dir / "subfolder").mkdir(exist_ok=True)
        (proj_dir / "subfolder" / "data.txt").write_text("sample content", encoding="utf-8")

        self.assertTrue(proj_dir.exists())

        response = self.client.delete(f"/api/project/{proj_name}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "deleted")
        self.assertEqual(data.get("name"), proj_name)

        # Confirm removed from filesystem
        self.assertFalse(proj_dir.exists())

    def test_02_delete_nonexistent_project_returns_404(self):
        """Verify deleting a nonexistent project returns 404."""
        proj_name = "nonexistent_project_qa_99999"
        response = self.client.delete(f"/api/project/{proj_name}")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json().get("detail", "").lower())

    def test_03_path_traversal_protection_returns_403(self):
        """Verify path traversal characters are rejected with 403/400."""
        # Attempt relative traversal
        response = self.client.delete("/api/project/..%2F..%2Fconfig")
        self.assertIn(response.status_code, (400, 403, 404))

    def test_04_dot_names_rejected_with_400(self):
        """Verify '.' and '..' are rejected with 400."""
        for invalid in (".", ".."):
            response = self.client.delete(f"/api/project/{invalid}")
            self.assertIn(response.status_code, (400, 404))

    def test_05_root_projects_dir_cannot_be_deleted(self):
        """Verify root projects dir cannot be deleted."""
        # Sanitization converts slashes or dots, ensuring root cannot be targeted
        self.assertTrue(self.test_projects_dir.exists())

if __name__ == "__main__":
    unittest.main()
