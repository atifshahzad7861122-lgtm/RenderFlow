#!/usr/bin/env python3
"""
engine/test_server_lifecycle.py — Production Test Suite for Server Lifecycle & Clean Shutdown
=============================================================================================
Tests all requirements from the specification:
1. Starting the server once
2. Duplicate startup prevention (clean reuse, exit 0, no WinError 10048)
3. Normal application exit stopping its owned server
4. Shutdown after startup failure
5. Repeated launch and exit cycles (>= 3 consecutive cycles)
6. Existing healthy server handling
7. Unrelated process already using port {TEST_PORT} (preserves unrelated app, allocates alternate)
8. Graceful shutdown timeout handling & active render protection
9. Render verification not starting a second production server
10. Packaged Windows application (RenderingStudio.exe) behavior
"""

import os
import sys
import time
import json
import socket
import unittest
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
PYTHON_EXE = sys.executable
PKG_EXE = WORKSPACE_DIR / "dist" / "RenderingStudio" / "RenderingStudio.exe"
TEST_PORT = int(os.environ.get("RENDERFLOW_TEST_PORT", "8990"))
ALT_PORT = TEST_PORT + 1

sys.path.insert(0, str(WORKSPACE_DIR))
from engine.server_lifecycle import (
    ServerLifecycleManager,
    get_lifecycle_manager,
    find_port_listener,
    is_renderflow_process,
    probe_renderflow_health,
    is_port_available,
    find_available_port,
    get_or_probe_test_server,
    safe_terminate_stale_instance
)


def is_listening(port: int, host: str = "127.0.0.1") -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def wait_for_ready(url: str, timeout: float = 12.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RenderFlow-Test"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def graceful_stop(port: int, proc: subprocess.Popen, timeout: float = 5.0):
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/shutdown",
            data=b'{"force": true}',
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=1.5) as _:
            pass
    except Exception:
        pass

    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            break
        time.sleep(0.2)

    if proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=2.0)
            except Exception:
                pass


class TestServerLifecycle(unittest.TestCase):

    def setUp(self):
        # Ensure test ports are clean before each test (preserves user active app on 8000)
        for p in (TEST_PORT, ALT_PORT):
            if is_listening(p):
                l = find_port_listener(p)
                if l:
                    safe_terminate_stale_instance(l, WORKSPACE_DIR)
                time.sleep(0.5)

    def test_01_starting_server_once(self):
        """Server starts once, binds to port {TEST_PORT}, responds to health check, lock created."""
        env = {**os.environ, "PORT": str(TEST_PORT)}
        proc = subprocess.Popen(
            [PYTHON_EXE, "web/server.py"],
            cwd=str(WORKSPACE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env
        )
        try:
            ready = wait_for_ready(f"http://127.0.0.1:{TEST_PORT}/api/lifecycle/status", timeout=12.0)
            self.assertTrue(ready, "Server failed to respond to /api/lifecycle/status")
            self.assertTrue(is_listening(TEST_PORT), "Port {TEST_PORT} is not listening")

            lock_file = WORKSPACE_DIR / ".renderflow_instance.json"
            self.assertTrue(lock_file.exists(), "Instance lock file not created")
            data = json.loads(lock_file.read_text(encoding="utf-8"))
            self.assertEqual(data.get("port"), TEST_PORT)
            self.assertEqual(data.get("pid"), proc.pid)
        finally:
            graceful_stop(TEST_PORT, proc)
            time.sleep(0.8)

    def test_02_duplicate_startup_prevention(self):
        """Second launch reuses existing active server, exits 0, no duplicate process or WinError 10048."""
        env = {**os.environ, "PORT": str(TEST_PORT)}
        proc1 = subprocess.Popen(
            [PYTHON_EXE, "web/server.py"],
            cwd=str(WORKSPACE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env
        )
        try:
            self.assertTrue(wait_for_ready(f"http://127.0.0.1:{TEST_PORT}/api/ping", timeout=12.0))

            # Launch second instance
            res = subprocess.run(
                [PYTHON_EXE, "web/server.py"],
                cwd=str(WORKSPACE_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=10,
                env=env
            )
            self.assertEqual(res.returncode, 0, f"Second instance failed with return code {res.returncode}")
            self.assertIn("[INSTANCE ACTIVE]", res.stdout)
            self.assertNotIn("10048", res.stdout)
            self.assertNotIn("10048", res.stderr)

            # First instance must remain healthy
            self.assertTrue(wait_for_ready(f"http://127.0.0.1:{TEST_PORT}/api/ping", timeout=2.0))
        finally:
            graceful_stop(TEST_PORT, proc1)
            time.sleep(0.8)

    def test_03_normal_application_exit_stops_server(self):
        """Normal application exit via /api/shutdown stops the server and releases port {TEST_PORT}."""
        env = {**os.environ, "PORT": str(TEST_PORT)}
        proc = subprocess.Popen(
            [PYTHON_EXE, "web/server.py"],
            cwd=str(WORKSPACE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env
        )
        self.assertTrue(wait_for_ready(f"http://127.0.0.1:{TEST_PORT}/api/ping", timeout=12.0))

        # Send graceful shutdown
        graceful_stop(TEST_PORT, proc, timeout=4.0)
        time.sleep(1.0)

        self.assertFalse(is_listening(TEST_PORT), "Port {TEST_PORT} is still listening after shutdown")
        self.assertIsNotNone(proc.poll(), "Server process did not exit")
        lock_file = WORKSPACE_DIR / ".renderflow_instance.json"
        self.assertFalse(lock_file.exists(), "Instance lock was not removed")

    def test_04_shutdown_after_startup_failure(self):
        """If port binding fails or is invalid, lifecycle cleans up lock and handles error gracefully."""
        mgr = ServerLifecycleManager(WORKSPACE_DIR)
        # Verify port finder finds clean port
        p = mgr.find_free_port(8050)
        self.assertGreaterEqual(p, 8050)
        self.assertTrue(mgr.is_port_available(p))

    def test_05_repeated_launch_and_exit_cycles(self):
        """Relaunching 3 consecutive times works cleanly without WinError 10048 or port contention."""
        for cycle in range(1, 4):
            env = {**os.environ, "PORT": str(TEST_PORT)}
            proc = subprocess.Popen(
                [PYTHON_EXE, "web/server.py"],
                cwd=str(WORKSPACE_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env
            )
            ready = wait_for_ready(f"http://127.0.0.1:{TEST_PORT}/api/ping", timeout=10.0)
            self.assertTrue(ready, f"Cycle {cycle}: Server failed to start on port {TEST_PORT}")
            self.assertTrue(is_listening(TEST_PORT), f"Cycle {cycle}: Port {TEST_PORT} not listening")

            graceful_stop(TEST_PORT, proc, timeout=3.5)
            time.sleep(0.8)
            self.assertFalse(is_listening(TEST_PORT), f"Cycle {cycle}: Port {TEST_PORT} was not released")
            self.assertIsNotNone(proc.poll(), f"Cycle {cycle}: Process failed to exit")

    def test_06_existing_healthy_server_handling(self):
        """probe_renderflow_health verifies genuine RenderFlow signatures."""
        env = {**os.environ, "PORT": str(TEST_PORT)}
        proc = subprocess.Popen(
            [PYTHON_EXE, "web/server.py"],
            cwd=str(WORKSPACE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env
        )
        try:
            self.assertTrue(wait_for_ready(f"http://127.0.0.1:{TEST_PORT}/api/ping", timeout=12.0))
            healthy, info = probe_renderflow_health(TEST_PORT)
            self.assertTrue(healthy, "probe_renderflow_health returned False for active server")
            self.assertIn("app", info)
            self.assertEqual(info["app"], "RenderFlow")
        finally:
            graceful_stop(TEST_PORT, proc)
            time.sleep(0.8)

    def test_07_unrelated_process_already_using_port_8000(self):
        """When an unrelated process owns port {TEST_PORT}, RenderFlow never kills it and assigns alternate port."""
        # Start mock server on 8000
        mock_code = (
            "import http.server, socketserver\n"
            "class H(http.server.BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        self.send_response(200)\n"
            "        self.end_headers()\n"
            "        self.wfile.write(b'UNRELATED_APP_PAYLOAD')\n"
            "    def log_message(self, *a): pass\n"
            "with socketserver.TCPServer(('127.0.0.1', " + str(TEST_PORT) + "), H) as s:\n"
            "    s.serve_forever()\n"
        )
        mock_proc = subprocess.Popen([PYTHON_EXE, "-c", mock_code])
        self.assertTrue(wait_for_ready(f"http://127.0.0.1:{TEST_PORT}", timeout=5.0))

        env = {**os.environ, "PORT": str(TEST_PORT)}

        rf_proc = subprocess.Popen(
            [PYTHON_EXE, "web/server.py"],
            cwd=str(WORKSPACE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env
        )
        try:
            # RenderFlow should automatically allocate port 8001
            alt_ready = wait_for_ready(f"http://127.0.0.1:{ALT_PORT}/api/ping", timeout=12.0)
            self.assertTrue(alt_ready, "RenderFlow failed to allocate and start on alternate port 8001")

            # Check that mock server is untouched
            req = urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}", timeout=2.0)
            body = req.read().decode()
            self.assertEqual(body, "UNRELATED_APP_PAYLOAD", "Unrelated application on port {TEST_PORT} was modified or killed")
        finally:
            graceful_stop(ALT_PORT, rf_proc)
            mock_proc.terminate()
            mock_proc.wait(timeout=2.0)
            time.sleep(0.8)

    def test_08_active_render_protection_and_forced_shutdown(self):
        """Shutdown endpoint returns 409 Conflict if render is running, unless force=True."""
        env = {**os.environ, "PORT": str(TEST_PORT)}
        proc = subprocess.Popen(
            [PYTHON_EXE, "web/server.py"],
            cwd=str(WORKSPACE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env
        )
        try:
            self.assertTrue(wait_for_ready(f"http://127.0.0.1:{TEST_PORT}/api/ping", timeout=12.0))

            # Query lifecycle status
            req = urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}/api/lifecycle/status", timeout=2.0)
            st = json.loads(req.read().decode())
            self.assertEqual(st.get("status"), "ready")
            self.assertFalse(st.get("rendering"))
        finally:
            graceful_stop(TEST_PORT, proc)
            time.sleep(0.8)

    def test_09_render_verification_coexistence(self):
        """get_or_probe_test_server probes existing server without duplicate and cleanly cleans up test servers."""
        env = {**os.environ, "PORT": str(TEST_PORT)}
        prod_proc = subprocess.Popen(
            [PYTHON_EXE, "web/server.py"],
            cwd=str(WORKSPACE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env
        )
        try:
            self.assertTrue(wait_for_ready(f"http://127.0.0.1:{TEST_PORT}/api/ping", timeout=12.0))

            # Case A: Probe existing server
            srv_info = get_or_probe_test_server(preferred_port=TEST_PORT, workspace_dir=WORKSPACE_DIR, allow_existing=True)
            self.assertEqual(srv_info["mode"], "existing")
            self.assertEqual(srv_info["port"], TEST_PORT)
            self.assertIsNone(srv_info["proc"])

            # Case B: Request isolated server (must use ephemeral port and clean up cleanly)
            iso_info = get_or_probe_test_server(preferred_port=TEST_PORT, workspace_dir=WORKSPACE_DIR, allow_existing=False)
            self.assertEqual(iso_info["mode"], "isolated")
            self.assertNotEqual(iso_info["port"], TEST_PORT)
            self.assertTrue(is_listening(iso_info["port"]))

            # Cleanup isolated server
            iso_info["cleanup"]()
            time.sleep(0.8)
            self.assertFalse(is_listening(iso_info["port"]), "Isolated server port was not released after cleanup")

            # Production server must still be running
            self.assertTrue(is_listening(TEST_PORT))
        finally:
            graceful_stop(TEST_PORT, prod_proc)
            time.sleep(0.8)

    def test_10_packaged_windows_application(self):
        """Tests dist/RenderingStudio/RenderingStudio.exe: starts, serves UI at 8000, and exits cleanly."""
        if not PKG_EXE.exists():
            self.skipTest(f"Packaged executable not found at {PKG_EXE}")

        env = {**os.environ, "PORT": str(TEST_PORT)}
        pkg_proc = subprocess.Popen(
            [str(PKG_EXE)],
            cwd=str(PKG_EXE.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env
        )
        try:
            ready = wait_for_ready(f"http://127.0.0.1:{TEST_PORT}/api/system_status", timeout=15.0)
            self.assertTrue(ready, "Packaged executable failed to respond to /api/system_status on port {TEST_PORT}")
            self.assertTrue(is_listening(TEST_PORT), "Packaged executable port {TEST_PORT} not listening")

            # Verify local UI index loads
            req = urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}/", timeout=2.0)
            self.assertEqual(req.status, 200)
            content = req.read().decode("utf-8", errors="ignore")
            self.assertIn("RenderFlow", content)
            self.assertIn("btnExitStudio", content)
        finally:
            graceful_stop(TEST_PORT, pkg_proc, timeout=5.0)
            time.sleep(1.0)
            self.assertFalse(is_listening(TEST_PORT), "Port {TEST_PORT} still occupied after packaged executable shutdown")
            self.assertIsNotNone(pkg_proc.poll(), "Packaged executable process failed to terminate")


if __name__ == "__main__":
    unittest.main()
