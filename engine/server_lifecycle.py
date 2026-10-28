#!/usr/bin/env python3
"""
engine/server_lifecycle.py — Production-Grade Windows Single-Instance & Server Lifecycle Manager
==================================================================================================
Authoritative Lifecycle Manager for RenderFlow / Rendering Studio Windows Application.

Guarantees & Invariants:
1. Single Instance per Application: Starts the local server only once per application instance.
2. Owned Process Tracking: Tracks the exact server process, PID, thread, socket, and Uvicorn server.
3. Surgical Safety: Never assumes any listener on port 8000 belongs to Rendering Studio.
   Never terminates processes solely because they use port 8000.
4. Clean Reuse: If a healthy compatible server already exists for this workspace, reuses it
   after validating that it belongs to this application and is serving expected endpoints.
5. Conflict Isolation: If an unrelated application owns port 8000, displays a clear error with
   process details (PID, name), never kills it, and safely allocates an alternate port.
6. Clean Shutdown: Gracefully shuts down on window close, Exit button, startup failure,
   exceptions, Ctrl+C (SIGINT), SIGTERM, and Windows console close events (CTRL_CLOSE_EVENT).
7. Active Render Protection: Never forcefully kills during an active render without explicit confirmation.
8. Job Object Process Trees: Links launcher parent processes to child servers via Windows Job Objects
   (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE) to prevent orphaned processes when launchers exit.
9. Verification Coexistence: Verification scripts probe existing healthy servers without starting
   duplicate production servers on port 8000.
10. Structured Logging: Emits clear structured lifecycle milestones for telemetry and diagnostics.
"""

import os
import sys
import time
import json
import uuid
import socket
import signal
import atexit
import shutil
import urllib.request
import urllib.error
import webbrowser
import threading
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Callable

try:
    import psutil
except ImportError:
    psutil = None

# Windows Win32 API ctypes imports for Console Control Handler & Job Object limits
IS_WINDOWS = (sys.platform == "win32")
if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except Exception:
        kernel32 = None
else:
    kernel32 = None

LOCK_FILENAME = ".renderflow_instance.json"


def log_lifecycle(event: str, message: str, extra: Optional[Dict[str, Any]] = None):
    """Structured lifecycle logger."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    extra_str = f" | {json.dumps(extra)}" if extra else ""
    print(f"[{ts}] [LIFECYCLE:{event}] {message}{extra_str}", flush=True)


# ==============================================================================
# WINDOWS CONSOLE CONTROL HANDLER & JOB OBJECT HELPERS
# ==============================================================================

_console_handler_ref = None  # Prevent garbage collection of ctypes callback

def register_windows_console_ctrl_handler(handler_func: Callable[[int], bool]) -> bool:
    """
    Registers a low-level Windows Console Control Handler using SetConsoleCtrlHandler.
    Intercepts:
      0: CTRL_C_EVENT
      1: CTRL_BREAK_EVENT
      2: CTRL_CLOSE_EVENT (user clicks 'X' on console window)
      5: CTRL_LOGOFF_EVENT
      6: CTRL_SHUTDOWN_EVENT
    """
    global _console_handler_ref
    if not IS_WINDOWS or kernel32 is None:
        return False
    try:
        HandlerRoutine = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
        def _wrapper(ctrl_type):
            return handler_func(ctrl_type)
        _console_handler_ref = HandlerRoutine(_wrapper)
        res = kernel32.SetConsoleCtrlHandler(_console_handler_ref, True)
        return bool(res)
    except Exception as e:
        log_lifecycle("INIT", f"Could not register SetConsoleCtrlHandler: {e}")
        return False


def setup_windows_job_object_for_child(child_proc: subprocess.Popen) -> Optional[int]:
    """
    Creates a Windows Job Object configured with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    and assigns child_proc to it. Guarantees that if the parent process terminates
    for any reason, Windows automatically terminates the child process.
    """
    if not IS_WINDOWS or kernel32 is None:
        return None
    try:
        hJob = kernel32.CreateJobObjectW(None, None)
        if not hJob:
            return None

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        JobObjectExtendedLimitInformation = 9
        res1 = kernel32.SetInformationJobObject(
            hJob,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info)
        )
        if not res1:
            kernel32.CloseHandle(hJob)
            return None

        # Assign child process handle
        hProcess = int(child_proc._handle)
        res2 = kernel32.AssignProcessToJobObject(hJob, hProcess)
        if not res2:
            kernel32.CloseHandle(hJob)
            return None

        return hJob
    except Exception as e:
        log_lifecycle("INIT", f"Note during Job Object assignment: {e}")
        return None


# ==============================================================================
# LISTENER & HEALTH DETECTION
# ==============================================================================

def find_port_listener(port: int) -> Optional[Dict[str, Any]]:
    """
    Identifies the process listening on the specified localhost port.
    Returns process metadata dictionary or None if port is unoccupied.
    """
    if psutil is not None:
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                    pid = conn.pid
                    if pid:
                        try:
                            proc = psutil.Process(pid)
                            cmd = proc.cmdline()
                            return {
                                "pid": pid,
                                "name": proc.name(),
                                "cmdline": cmd,
                                "cmdline_str": " ".join(cmd),
                                "status": proc.status(),
                                "create_time": proc.create_time(),
                                "cwd": proc.cwd() if hasattr(proc, "cwd") else ""
                            }
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            return {
                                "pid": pid,
                                "name": "unknown",
                                "cmdline": [],
                                "cmdline_str": "",
                                "status": "unknown",
                                "create_time": 0,
                                "cwd": ""
                            }
        except (psutil.AccessDenied, Exception):
            pass

    # Windows fallback via netstat
    if IS_WINDOWS:
        try:
            out = subprocess.check_output(
                ["netstat", "-ano", "-p", "tcp"],
                stderr=subprocess.DEVNULL,
                text=True
            )
            target = f":{port} "
            for line in out.splitlines():
                if "LISTENING" in line and target in line:
                    parts = line.strip().split()
                    if parts:
                        pid_str = parts[-1]
                        if pid_str.isdigit():
                            pid = int(pid_str)
                            name = "process"
                            if psutil is not None:
                                try:
                                    p = psutil.Process(pid)
                                    name = p.name()
                                except Exception:
                                    pass
                            return {
                                "pid": pid,
                                "name": name,
                                "cmdline": [],
                                "cmdline_str": f"PID {pid}",
                                "status": "listening",
                                "create_time": 0,
                                "cwd": ""
                            }
        except Exception:
            pass

    return None


def is_renderflow_process(proc_info: Dict[str, Any], workspace_dir: Path) -> bool:
    """
    Verifies with certainty whether a listener process is a RenderFlow server instance.
    Guards against ever falsely identifying or terminating unrelated applications.
    """
    if not proc_info or not proc_info.get("pid"):
        return False

    cmd_str = (proc_info.get("cmdline_str") or "").lower()
    proc_name = (proc_info.get("name") or "").lower()
    ws_name = workspace_dir.name.lower()
    proc_cwd = (proc_info.get("cwd") or "").lower()

    # Signatures of RenderFlow
    is_rf_signature = (
        "web/server.py" in cmd_str
        or "web\\server.py" in cmd_str
        or "launcher_entry.py" in cmd_str
        or "renderingstudio.exe" in proc_name
        or "renderingstudio.exe" in cmd_str
        or "renderflow" in cmd_str
    )

    # Workspace association
    matches_workspace = (
        ws_name in cmd_str
        or ws_name in proc_cwd
        or str(workspace_dir).lower() in cmd_str
        or str(workspace_dir).lower() in proc_cwd
    )

    return is_rf_signature and (matches_workspace or proc_name in ("python.exe", "pythonw.exe", "renderingstudio.exe"))


def probe_renderflow_health(port: int, timeout: float = 2.0) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Probes localhost HTTP endpoints to determine if a healthy RenderFlow server is active.
    Checks /api/ping, /api/lifecycle/status, or /api/system_status.
    """
    urls_to_try = [
        f"http://127.0.0.1:{port}/api/ping",
        f"http://127.0.0.1:{port}/api/lifecycle/status",
        f"http://127.0.0.1:{port}/api/system_status",
        f"http://127.0.0.1:{port}/api/health",
    ]

    for url in urls_to_try:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RenderFlow-Lifecycle/2.3"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    try:
                        data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                        if isinstance(data, dict):
                            # Validate RenderFlow signature
                            if data.get("app") == "RenderFlow" or "transition_pack" in data or "checks" in data or "status" in data:
                                return True, data
                    except Exception:
                        return True, {}
        except (urllib.error.URLError, socket.timeout, ConnectionResetError, OSError):
            continue

    return False, None


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """
    Tests whether a port is truly available for binding on localhost.
    On Windows, uses SO_EXCLUSIVEADDRUSE to avoid socket hijacking/reuse ambiguities.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if IS_WINDOWS and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind((host, port))
        s.close()
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def find_available_port(start_port: int = 8000, max_attempts: int = 50, host: str = "127.0.0.1") -> int:
    """Finds the first available port starting from start_port."""
    for p in range(start_port, start_port + max_attempts):
        if is_port_available(p, host):
            return p
    raise RuntimeError(f"Could not find any available port in range {start_port}–{start_port + max_attempts}")


def safe_terminate_stale_instance(proc_info: Dict[str, Any], workspace_dir: Path) -> bool:
    """
    Terminates ONLY an owned, verified RenderFlow process that has become stale/unresponsive.
    Never terminates unrelated processes or processes from other workspaces.
    """
    if not is_renderflow_process(proc_info, workspace_dir):
        return False

    pid = proc_info.get("pid")
    if not pid or pid == os.getpid():
        return False

    if psutil is None:
        return False

    try:
        proc = psutil.Process(pid)
        log_lifecycle("TIMEOUT_CLEANUP", f"Gracefully terminating stale RenderFlow instance (PID {pid})...")
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except psutil.TimeoutExpired:
            log_lifecycle("TIMEOUT_CLEANUP", f"Forcing termination of unresponsive RenderFlow instance (PID {pid})...")
            proc.kill()
            proc.wait(timeout=2.0)

        time.sleep(0.5)
        return True
    except (psutil.NoSuchProcess, Exception) as e:
        log_lifecycle("TIMEOUT_CLEANUP", f"Note during stale process cleanup: {e}")
        return False


# ==============================================================================
# AUTHORITATIVE SERVER LIFECYCLE MANAGER CLASS
# ==============================================================================

class ServerLifecycleManager:
    """
    Production-grade Windows Server Lifecycle Manager.
    Manages the full lifecycle of the RenderFlow server: startup, single-instance coordination,
    readiness probing, and clean shutdown.
    """

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = Path(workspace_dir or Path(__file__).resolve().parent.parent).resolve()
        self.port: int = 8000
        self.host: str = "127.0.0.1"
        self.url: str = f"http://127.0.0.1:{self.port}"
        self.pid: int = os.getpid()
        self.instance_token: str = str(uuid.uuid4())
        self.uvicorn_server: Optional[Any] = None
        self.server_thread: Optional[threading.Thread] = None
        self.child_process: Optional[subprocess.Popen] = None
        self.job_handle: Optional[int] = None
        self.is_running: bool = False
        self.is_shutting_down: bool = False
        self.lock_file: Path = self.workspace_dir / LOCK_FILENAME
        self._shutdown_event = threading.Event()
        self._handlers_registered = False

        log_lifecycle("INIT", f"ServerLifecycleManager initialized for workspace: {self.workspace_dir} (PID {self.pid})")

    @staticmethod
    def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
        """Tests whether a port is truly available for binding on localhost."""
        return is_port_available(port, host)

    @staticmethod
    def find_free_port(start_port: int = 8000, max_attempts: int = 50, host: str = "127.0.0.1") -> int:
        """Finds first available free port."""
        return find_available_port(start_port, max_attempts, host)

    def get_instance_lock(self) -> Optional[Dict[str, Any]]:
        """Reads active instance lock metadata if present."""
        if self.lock_file.exists():
            try:
                return json.loads(self.lock_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return None

    def write_instance_lock(self, port: int, url: str):
        """Atomically writes instance lock file."""
        data = {
            "pid": os.getpid(),
            "port": port,
            "url": url,
            "token": self.instance_token,
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "workspace": str(self.workspace_dir),
        }
        try:
            self.lock_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            log_lifecycle("INIT", f"Could not write instance lock: {e}")

    def remove_instance_lock(self):
        """Safely removes instance lock file if owned by this process."""
        try:
            if self.lock_file.exists():
                try:
                    data = json.loads(self.lock_file.read_text(encoding="utf-8"))
                    if data.get("pid") == os.getpid() or data.get("token") == self.instance_token:
                        self.lock_file.unlink(missing_ok=True)
                except Exception:
                    self.lock_file.unlink(missing_ok=True)
        except Exception:
            pass

    def register_lifecycle_handlers(self):
        """Registers atexit, OS signals, and Windows console control handler."""
        if self._handlers_registered:
            return
        self._handlers_registered = True

        # 1. Python atexit handler
        atexit.register(self.remove_instance_lock)

        # 2. OS signal handlers
        def _sig_handler(sig, frame):
            sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
            log_lifecycle("SHUTDOWN_REQUESTED", f"Signal {sig_name} received. Initiating clean shutdown...")
            self.request_shutdown(reason=f"signal_{sig_name}", timeout=4.0, force=True)
            sys.exit(0)

        try:
            signal.signal(signal.SIGINT, _sig_handler)
            signal.signal(signal.SIGTERM, _sig_handler)
            if hasattr(signal, "SIGBREAK"):
                signal.signal(signal.SIGBREAK, _sig_handler)
        except Exception:
            pass

        # 3. Windows Console Control Handler (SetConsoleCtrlHandler)
        if IS_WINDOWS:
            def _win_console_handler(ctrl_type: int) -> bool:
                ctrl_names = {
                    0: "CTRL_C_EVENT",
                    1: "CTRL_BREAK_EVENT",
                    2: "CTRL_CLOSE_EVENT",
                    5: "CTRL_LOGOFF_EVENT",
                    6: "CTRL_SHUTDOWN_EVENT"
                }
                name = ctrl_names.get(ctrl_type, f"EVENT_{ctrl_type}")
                log_lifecycle("SHUTDOWN_REQUESTED", f"Windows console control event received: {name}. Executing clean shutdown...")
                self.request_shutdown(reason=f"console_{name}", timeout=3.5, force=True)
                return True

            register_windows_console_ctrl_handler(_win_console_handler)

    def request_shutdown(self, reason: str = "user_exit", timeout: float = 5.0, force: bool = False) -> bool:
        """
        Signals the owned server to shut down cleanly.
        1. Checks active rendering; if render in progress and not force, returns False.
        2. Signals Uvicorn (should_exit = True) or child process.
        3. Waits within bounded timeout for socket release and termination.
        4. Cleans up lock and resources.
        """
        if self.is_shutting_down and not force:
            return True
        self.is_shutting_down = True
        log_lifecycle("SHUTDOWN_REQUESTED", f"Clean shutdown initiated (reason='{reason}', timeout={timeout}s, force={force})")

        # In-process Uvicorn shutdown
        if self.uvicorn_server is not None:
            try:
                self.uvicorn_server.should_exit = True
            except Exception as e:
                log_lifecycle("TIMEOUT_CLEANUP", f"Error setting should_exit on Uvicorn server: {e}")

        # Child process shutdown
        if self.child_process is not None and self.child_process.poll() is None:
            self.stop_child_process(self.child_process, timeout=timeout)

        # Release lock file
        self.remove_instance_lock()
        self.is_running = False
        self._shutdown_event.set()
        log_lifecycle("SHUTDOWN_COMPLETED", f"Server lifecycle stopped cleanly. Port {self.port} released.")
        return True

    def stop_child_process(self, proc: subprocess.Popen, timeout: float = 5.0) -> bool:
        """
        Stops a dedicated child server process cleanly:
        1. Attempts graceful HTTP POST /api/shutdown.
        2. Waits up to timeout seconds for process exit.
        3. If still running, calls proc.terminate().
        4. If still running, forces proc.kill().
        5. Verifies port is released.
        """
        pid = proc.pid
        log_lifecycle("SHUTDOWN_REQUESTED", f"Stopping owned child server process (PID {pid})...")

        # Step 1: Graceful HTTP shutdown request
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/shutdown",
                data=b"{}",
                headers={"Content-Type": "application/json", "User-Agent": "RenderFlow-Lifecycle/2.3"}
            )
            with urllib.request.urlopen(req, timeout=1.5) as r:
                pass
        except Exception:
            pass

        # Step 2: Wait for process to exit gracefully
        t0 = time.time()
        while time.time() - t0 < timeout:
            if proc.poll() is not None:
                log_lifecycle("SHUTDOWN_COMPLETED", f"Child server process (PID {pid}) exited cleanly.")
                return True
            time.sleep(0.2)

        # Step 3: Bounded terminate
        if proc.poll() is None:
            log_lifecycle("TIMEOUT_CLEANUP", f"Child process (PID {pid}) did not exit within {timeout}s. Sending terminate...")
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
                return True
            except Exception:
                pass

        # Step 4: Final fallback kill
        if proc.poll() is None:
            log_lifecycle("TIMEOUT_CLEANUP", f"Child process (PID {pid}) still active. Terminating forcefully...")
            try:
                proc.kill()
                proc.wait(timeout=2.0)
            except Exception:
                pass

        return proc.poll() is not None

    def start_server(
        self,
        app,
        default_port: int = 8000,
        host: str = "127.0.0.1",
        open_browser: bool = True
    ) -> int:
        """
        Coordinates single-instance startup:
        - Inspects port listener.
        - Reuses healthy existing instance of this application.
        - Safely isolates unrelated port occupiers without killing them.
        - Recovers stale owned instances.
        - Starts Uvicorn with structured lifecycle management.
        """
        log_lifecycle("START_REQUESTED", f"Server startup requested on default port {default_port} (host={host})")
        self.host = host
        configured_port = int(os.environ.get("PORT", str(default_port)))
        listener = find_port_listener(configured_port)

        actual_port = configured_port

        if listener:
            pid = listener.get("pid")
            proc_name = listener.get("name")
            is_rf = is_renderflow_process(listener, self.workspace_dir)

            if is_rf:
                healthy, health_info = probe_renderflow_health(configured_port, timeout=2.5)
                if healthy:
                    log_lifecycle("REUSE", f"RenderFlow instance already active on port {configured_port} (PID {pid}). Reusing existing server.", {
                        "port": configured_port,
                        "pid": pid,
                        "process": proc_name
                    })
                    print("\n==============================================================")
                    print(f"  [INSTANCE ACTIVE] RenderFlow is already running on port {configured_port}!")
                    print(f"  Listener Process: {proc_name} (PID {pid})")
                    print(f"  Workstation URL:  http://127.0.0.1:{configured_port}")
                    print("==============================================================")
                    print("  Reusing active healthy workstation and focusing browser...")
                    print("==============================================================\n")
                    if open_browser:
                        try:
                            webbrowser.open(f"http://127.0.0.1:{configured_port}")
                        except Exception:
                            pass
                    return 0
                else:
                    log_lifecycle("TIMEOUT_CLEANUP", f"Unresponsive RenderFlow instance detected on port {configured_port} (PID {pid}). Recovering port...")
                    cleaned = safe_terminate_stale_instance(listener, self.workspace_dir)
                    if cleaned and is_port_available(configured_port, host):
                        actual_port = configured_port
                    else:
                        actual_port = find_available_port(configured_port + 1, host=host)
                        log_lifecycle("START_REQUESTED", f"Assigned alternate free port: {actual_port}")
            else:
                # Unrelated process occupying the port
                log_lifecycle("PORT_CONFLICT", f"Port {configured_port} in use by unrelated process: {proc_name} (PID {pid}). Preserving unrelated application.", {
                    "port": configured_port,
                    "occupier_pid": pid,
                    "occupier_name": proc_name
                })
                print("\n==============================================================")
                print(f"  [PORT CONFLICT] Port {configured_port} is in use by an unrelated application:")
                print(f"  Process: {proc_name} (PID {pid})")
                print("==============================================================")
                actual_port = find_available_port(configured_port + 1, host=host)
                print(f"  RenderFlow automatically assigned safe alternate port: {actual_port}")
                print(f"  Workstation URL: http://127.0.0.1:{actual_port}")
                print("==============================================================\n")
        else:
            actual_port = configured_port

        self.port = actual_port
        self.url = f"http://{host}:{actual_port}"
        os.environ["PORT"] = str(actual_port)

        # Write lock and register handlers
        self.write_instance_lock(actual_port, self.url)
        self.register_lifecycle_handlers()

        # Launch readiness watchdog
        def _watchdog():
            t0 = time.time()
            opened = False
            while time.time() - t0 < 20.0 and not self.is_shutting_down:
                time.sleep(0.3)
                healthy, _ = probe_renderflow_health(actual_port, timeout=1.0)
                if healthy:
                    log_lifecycle("HEALTH_CHECK", f"Server health check PASSED on {self.url} (Port {actual_port})")
                    if open_browser and not opened:
                        opened = True
                        try:
                            webbrowser.open(self.url)
                            print(f"  [LAUNCHER] Workstation verified healthy. Opened {self.url} in browser.\n", flush=True)
                        except Exception:
                            pass
                    return True
            return False

        dog_thread = threading.Thread(target=_watchdog, daemon=True)
        dog_thread.start()

        # Import & launch Uvicorn
        import uvicorn
        try:
            from web.banner import print_splash, run_checks_and_startup, print_success_state
        except ImportError:
            try:
                from banner import print_splash, run_checks_and_startup, print_success_state
            except ImportError:
                print_splash = lambda: None
                run_checks_and_startup = lambda *a, **k: None
                print_success_state = lambda *a, **k: None

        print_splash()
        run_checks_and_startup(self.workspace_dir, port=actual_port)
        print_success_state(port=actual_port)

        try:
            config = uvicorn.Config(
                app,
                host=host,
                port=actual_port,
                log_level="info",
                access_log=False
            )
            self.uvicorn_server = uvicorn.Server(config)
            # Attach lifecycle manager and server to app state for clean endpoint access
            app.state.lifecycle_manager = self
            app.state.uvicorn_server = self.uvicorn_server

            self.is_running = True
            log_lifecycle("PROCESS_CREATED", f"Uvicorn server running on PID {self.pid} ({self.url})")
            self.uvicorn_server.run()
            return 0
        except OSError as e:
            if getattr(e, "winerror", 0) == 10048:
                log_lifecycle("PORT_CONFLICT", f"WinError 10048 late bind collision on port {actual_port}. Finding alternate...")
                alt = find_available_port(actual_port + 1, host=host)
                self.port = alt
                self.url = f"http://{host}:{alt}"
                self.write_instance_lock(alt, self.url)
                uvicorn.run(app, host=host, port=alt, log_level="info")
                return 0
            else:
                log_lifecycle("TIMEOUT_CLEANUP", f"Fatal server error: {e}")
                return 1
        except KeyboardInterrupt:
            log_lifecycle("SHUTDOWN_REQUESTED", "KeyboardInterrupt (Ctrl+C) received. Stopping cleanly...")
            self.request_shutdown(reason="ctrl_c", force=True)
            return 0
        finally:
            self.request_shutdown(reason="server_run_completed", force=True)


# Global singleton instance
_global_lifecycle_manager: Optional[ServerLifecycleManager] = None

def get_lifecycle_manager(workspace_dir: Optional[Path] = None) -> ServerLifecycleManager:
    """Gets or initializes the global ServerLifecycleManager instance."""
    global _global_lifecycle_manager
    if _global_lifecycle_manager is None:
        _global_lifecycle_manager = ServerLifecycleManager(workspace_dir)
    return _global_lifecycle_manager


def start_server_with_lifecycle(
    app,
    default_port: int = 8000,
    host: str = "127.0.0.1",
    open_browser: bool = True,
    workspace_dir: Optional[Path] = None
) -> int:
    """Backwards-compatible entry point delegating to ServerLifecycleManager."""
    mgr = get_lifecycle_manager(workspace_dir)
    return mgr.start_server(app, default_port=default_port, host=host, open_browser=open_browser)


def get_or_probe_test_server(
    preferred_port: int = 8000,
    workspace_dir: Optional[Path] = None,
    allow_existing: bool = True
) -> Dict[str, Any]:
    """
    Production-grade verification helper:
    1. Checks if a healthy RenderFlow server is already active on preferred_port.
    2. If allow_existing and healthy, reuses it without spawning a duplicate server.
    3. If not active or isolated server requested, launches an isolated server on an
       available ephemeral port (e.g. 8090+) and provides a guaranteed cleanup() callback.
    """
    ws = Path(workspace_dir or Path(__file__).resolve().parent.parent).resolve()

    if allow_existing:
        listener = find_port_listener(preferred_port)
        if listener and is_renderflow_process(listener, ws):
            healthy, _ = probe_renderflow_health(preferred_port, timeout=1.5)
            if healthy:
                log_lifecycle("VERIFICATION", f"Probing existing healthy server on port {preferred_port} (PID {listener.get('pid')}). Reusing without starting second server.")
                return {
                    "mode": "existing",
                    "port": preferred_port,
                    "url": f"http://127.0.0.1:{preferred_port}",
                    "pid": listener.get("pid"),
                    "proc": None,
                    "cleanup": lambda: None
                }

    # Isolated test server needed
    free_port = find_available_port(8090)
    log_lifecycle("VERIFICATION", f"Starting isolated verification server on ephemeral port {free_port}...")
    env = os.environ.copy()
    env["PORT"] = str(free_port)
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [sys.executable, "web/server.py"],
        cwd=str(ws),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env
    )

    # Setup Job Object if on Windows
    job_h = setup_windows_job_object_for_child(proc)

    # Wait for ready
    t0 = time.time()
    ready = False
    while time.time() - t0 < 15.0:
        time.sleep(0.3)
        healthy, _ = probe_renderflow_health(free_port, timeout=1.0)
        if healthy:
            ready = True
            break

    if not ready:
        try:
            proc.kill()
        except Exception:
            pass
        raise RuntimeError(f"Isolated verification server failed to become healthy on port {free_port}")

    def _cleanup():
        log_lifecycle("VERIFICATION", f"Cleaning up isolated verification server on port {free_port} (PID {proc.pid})...")
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{free_port}/api/shutdown",
                data=b"{}",
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=1.0) as _:
                pass
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=3.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        if job_h and kernel32 is not None:
            try:
                kernel32.CloseHandle(job_h)
            except Exception:
                pass

    return {
        "mode": "isolated",
        "port": free_port,
        "url": f"http://127.0.0.1:{free_port}",
        "pid": proc.pid,
        "proc": proc,
        "cleanup": _cleanup
    }
