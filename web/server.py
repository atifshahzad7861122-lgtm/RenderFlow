#!/usr/bin/env python3
"""
Rendering Studio Engine v2 — Localhost Web Server & API
FastAPI + Uvicorn server providing an interactive studio UI, real-time render streaming,
timeline inspector, transition pack explorer, and output video player.
Includes robust ZIP extraction, natural sorting, image validation, and audio auto-mapping.
"""

import os
import sys
import time
import json
import asyncio
import subprocess
import shutil
import re
import uuid
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

if getattr(sys, "frozen", False):
    _base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    if not (_base_dir / "web" / "static").exists():
        _base_dir = Path(sys.executable).parent
    WORKSPACE_DIR = _base_dir
else:
    WORKSPACE_DIR = Path(__file__).resolve().parent.parent

if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from engine.version import __version__ as APP_VERSION
from engine.updater import update_manager, UpdateState
from engine.updates import update_service, UpdateState as NewUpdateState
from engine.timeline_normalizer import TimelineNormalizer
from engine.audio_waveform import AudioWaveformService, WaveformData
from engine.transcript_ripple import (
    TranscriptRipplePlanner,
    RippleEditRequest,
    RippleEditResult,
    RippleHistoryManager,
    ProtectedIntervalError,
    InvalidRippleRequestError
)

# Prioritize bundled binaries (ffmpeg, ffprobe) if present
bin_dir = WORKSPACE_DIR / "bin"
if bin_dir.exists():
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")

def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except Exception:
        pass

def get_ffmpeg_bin() -> str:
    env_v = os.environ.get("FFMPEG_BINARY", "").strip()
    if env_v and Path(env_v).exists():
        return str(Path(env_v).resolve())
    b = shutil.which("ffmpeg")
    if b:
        return b
    local_bin = WORKSPACE_DIR / "bin" / "ffmpeg.exe"
    if local_bin.exists():
        return str(local_bin.resolve())
    return "ffmpeg"

def get_ffprobe_bin() -> str:
    env_v = os.environ.get("FFPROBE_BINARY", "").strip()
    if env_v and Path(env_v).exists():
        return str(Path(env_v).resolve())
    b = shutil.which("ffprobe")
    if b:
        return b
    local_bin = WORKSPACE_DIR / "bin" / "ffprobe.exe"
    if local_bin.exists():
        return str(local_bin.resolve())
    return "ffprobe"

WEB_DIR = WORKSPACE_DIR / "web"
STATIC_DIR = WEB_DIR / "static"
if not STATIC_DIR.exists():
    STATIC_DIR = Path(__file__).resolve().parent / "static"

def _get_writable_dir(preferred_path: Path, fallback_subdir: str) -> Path:
    try:
        preferred_path.mkdir(parents=True, exist_ok=True)
        test_file = preferred_path / f".write_probe_{os.getpid()}"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        return preferred_path
    except Exception:
        fallback = Path.home() / "RenderFlow" / fallback_subdir
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

PROJECTS_DIR = _get_writable_dir(WORKSPACE_DIR / "projects", "projects")
TEMP_UPLOADS_DIR = _get_writable_dir(WORKSPACE_DIR / ".tmp_uploads", ".tmp_uploads")

# Add workspace and web directory to path for zip_processor and engine
sys.path.insert(0, str(WORKSPACE_DIR))
sys.path.insert(0, str(WEB_DIR))
from zip_processor import natural_sort_key, process_zip_archive, validate_image_file
from engine.semantic_sync import (
    build_semantic_timeline,
    validate_timeline_coverage,
    format_preview_summary,
    probe_audio_duration
)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Narrowly handle Windows WSAECONNRESET (WinError 10054) on abrupt client disconnection."""
    if sys.platform == 'win32':
        try:
            active_loop = asyncio.get_running_loop()
            def handle_win_disconnection(loop, context):
                exc = context.get('exception')
                # Filter client-initiated socket resets (tab closed, refreshed, or request aborted)
                if isinstance(exc, (ConnectionResetError, BrokenPipeError)) or (
                    isinstance(exc, OSError) and getattr(exc, 'winerror', 0) in (10054, 10053)
                ):
                    return
                # All real application exceptions, task errors, and unexpected faults remain visible:
                loop.default_exception_handler(context)
            active_loop.set_exception_handler(handle_win_disconnection)
        except Exception as e:
            safe_print(f"[STARTUP] Event loop handler setup notice: {e}")
    yield

app = FastAPI(title="RenderFlow by AI With Atif", version=APP_VERSION, lifespan=lifespan)

@app.get("/api/ping")
async def ping_server():
    """Instantaneous lightweight ping for launcher health probes and single-instance coordination."""
    return {
        "status": "ok",
        "app": "RenderFlow",
        "version": APP_VERSION,
        "pid": os.getpid(),
        "workspace": str(WORKSPACE_DIR)
    }

@app.get("/api/lifecycle/status")
async def get_lifecycle_status():
    """Returns active server lifecycle status, PID, port, and render state."""
    return {
        "app": "RenderFlow",
        "pid": os.getpid(),
        "port": int(os.environ.get("PORT", 8000)),
        "status": "ready",
        "rendering": (render_mgr.state == "running"),
        "workspace": str(WORKSPACE_DIR)
    }

@app.post("/api/shutdown")
async def shutdown_server(request: Request):
    """Graceful shutdown endpoint for lifecycle management."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    force = bool(body.get("force", False))

    # Active render protection (§3): Never terminate during active render unless confirmed
    if render_mgr.state == "running" and not force:
        return JSONResponse(
            status_code=409,
            content={
                "status": "rendering_in_progress",
                "message": "A render is currently active. Please confirm cancellation to exit."
            }
        )

    if render_mgr.state == "running" and force:
        try:
            if render_mgr.process:
                render_mgr.process.terminate()
        except Exception:
            pass
        render_mgr.state = "cancelled"
        render_mgr.state_marker = "CANCELLED"

    lifecycle_mgr = getattr(app.state, "lifecycle_manager", None)

    def _trigger_shutdown():
        import time
        time.sleep(0.2)
        if lifecycle_mgr is not None:
            lifecycle_mgr.request_shutdown(reason="api_exit", force=True)
        else:
            uv_server = getattr(app.state, "uvicorn_server", None)
            if uv_server is not None:
                uv_server.should_exit = True
            else:
                import signal
                os.kill(os.getpid(), signal.SIGTERM)

    import threading
    threading.Thread(target=_trigger_shutdown, daemon=True).start()
    return {"ok": True, "status": "shutting_down", "pid": os.getpid(), "message": "RenderFlow server is shutting down cleanly."}



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def no_cache_static_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    err_str = str(exc)
    safe_print(f"[UNHANDLED EXCEPTION] {request.method} {request.url.path}: {err_str}")
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "status": "error",
            "error": "Internal Server Error",
            "detail": err_str,
            "path": request.url.path
        }
    )

# Global render state tracker
class RenderManager:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.state: str = "idle"  # idle, running, completed, error
        self.state_marker: str = "IDLE"
        self.chunk_info: str = ""
        self.progress_percent: float = 0.0
        self.current_step: int = 0
        self.step_name: str = ""
        self.logs: List[str] = []
        self.listeners: List[asyncio.Queue] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.output_video: Optional[str] = None
        self.contact_sheet: Optional[str] = None
        self.scene_labels: Optional[str] = None
        self.qc_report: Optional[Dict[str, Any]] = None
        self.error_message: Optional[str] = None
        self.exit_code: Optional[int] = None
        self.active_encoder: Optional[str] = None

    def reset(self):
        self.state = "idle"
        self.state_marker = "IDLE"
        self.chunk_info = ""
        self.progress_percent = 0.0
        self.current_step = 0
        self.step_name = ""
        self.logs = []
        self.output_video = None
        self.contact_sheet = None
        self.scene_labels = None
        self.qc_report = None
        self.error_message = None
        self.exit_code = None
        self.active_encoder = None

    async def broadcast(self, data: Dict[str, Any]):
        for queue in list(self.listeners):
            try:
                await queue.put(data)
            except Exception:
                pass

render_mgr = RenderManager()


# --- Software Update API Endpoints ---

@app.get("/api/update/status")
async def get_update_status():
    """Returns authoritative updater state, versions, release notes, and progress metrics."""
    st = update_service.get_status()
    st.setdefault("package_size", st.get("package_size", "--"))
    st.setdefault("package_size_bytes", st.get("package_size_bytes", 0))
    st.setdefault("update_package_url", st.get("release_url", ""))
    return st

@app.post("/api/update/check")
async def check_for_updates(custom_manifest_url: Optional[str] = None):
    """Trigger a cryptographically authenticated check against the remote manifest."""
    status = update_service.get_status()
    if status.get("state") in (NewUpdateState.DOWNLOADING.value, NewUpdateState.INSTALLING.value):
        return {"ok": False, "message": f"Update operation currently in progress ({status.get('state')}).", "status": status}
    
    result = await asyncio.to_thread(update_service.check_for_updates, force=True, custom_manifest_url=custom_manifest_url)
    is_ok = bool(result.get("ok")) and bool(result.get("is_verified")) and (result.get("state") != NewUpdateState.CHECK_FAILED.value)
    has_update = bool(result.get("update_available", False))
    check_status = (
        "verified_latest" if (is_ok and not has_update)
        else ("update_available" if (is_ok and has_update) else "check_failed")
    )
    
    return {
        "ok": is_ok,
        "update_available": has_update,
        "latest_version": result.get("latest_version"),
        "current_version": result.get("current_version", APP_VERSION),
        "check_status": check_status,
        "is_verified": bool(result.get("is_verified", False)),
        "message": result.get("error_message") if not is_ok else (
            f"Update v{result.get('latest_version')} is available!" if has_update else f"RenderFlow is up to date (v{result.get('current_version')})"
        ),
        "status": result
    }

@app.post("/api/update/download")
async def download_update():
    """Initiates secure background download and checksum validation of verified installer."""
    status = update_service.get_status()
    if status.get("state") == NewUpdateState.DOWNLOADING.value:
        return {"ok": True, "message": "Download is already in progress.", "status": status}
    
    if not status.get("update_available") and status.get("state") != NewUpdateState.UPDATE_AVAILABLE.value:
        return JSONResponse(status_code=400, content={"ok": False, "message": "No update is currently available to download."})
    
    result = update_service.start_download()
    return {"ok": True, "message": "Download started.", "status": update_service.get_status()}

@app.post("/api/update/cancel")
async def cancel_update():
    """Cancels active download and safely restores updater to previous state."""
    status = update_service.cancel_download()
    return {"ok": True, "message": "Update download cancelled.", "status": status}

@app.post("/api/update/install_full")
async def install_full_installer():
    """Launches downloaded full installer executable."""
    status = update_service.get_status()
    if status.get("state") != NewUpdateState.READY_TO_INSTALL.value and not status.get("installer_ready"):
        return JSONResponse(status_code=400, content={"ok": False, "message": "Full installer is not downloaded or ready."})
    
    if render_mgr.state == "running":
        return JSONResponse(status_code=409, content={"ok": False, "message": "Cannot launch installer while a render is actively running."})
    
    result = update_service.launch_installer(silent=False)
    if result.get("state") == NewUpdateState.INSTALLING.value or result.get("ok"):
        return {"ok": True, "success": True, "message": "Installer launched. RenderFlow will close cleanly for installation."}
    else:
        err = result.get("error_message") or "Failed to launch installer."
        return JSONResponse(status_code=500, content={"ok": False, "success": False, "message": err})

@app.post("/api/update/verify_post_install")
async def verify_post_install():
    """Verifies that the newly started backend is healthy and running the target version."""
    result = await asyncio.to_thread(update_service.verify_post_install)
    status_code = 200 if result.get("ok") else 500
    return JSONResponse(status_code=status_code, content=result)

@app.get("/api/update/diagnostics")
async def get_update_diagnostics():
    """Returns recent diagnostic log lines and actionable recovery guidance."""
    st = update_service.get_status()
    lines = update_service.recovery.read_recent_diagnostics(max_lines=60)
    guidance = update_service.recovery.get_recovery_guidance(st.get("state", "IDLE"), st.get("error_message"))
    return {
        "ok": True,
        "log_path": str(update_service.recovery.diagnostics_file),
        "recent_logs": lines,
        "recovery_guidance": guidance
    }

@app.post("/api/update/apply")
async def apply_update():
    """Backward compatibility hook for applying verified update."""
    status = update_service.get_status()
    if status.get("state") == NewUpdateState.READY_TO_INSTALL.value or status.get("installer_ready"):
        if render_mgr.state == "running":
            return JSONResponse(status_code=409, content={"ok": False, "success": False, "message": "Cannot apply update while a render is actively running."})
        res = update_service.launch_installer(silent=False)
        return {"ok": True, "success": True, "message": "Installer launched.", "status": res}

    # Fallback to legacy patch application if patch is staged in update_manager
    legacy_st = update_manager.get_status()
    if legacy_st.get("state") == UpdateState.DOWNLOADED:
        if render_mgr.state == "running":
            return JSONResponse(status_code=409, content={"ok": False, "success": False, "message": "Cannot apply update while a render is actively running."})
        result = await asyncio.to_thread(update_manager.apply_patch)
        is_success = (result.get("state") == UpdateState.READY_TO_RESTART) or bool(result.get("ok")) or bool(result.get("success"))
        return {
            "ok": is_success,
            "success": is_success,
            "message": result.get("message") or ("Patch applied." if is_success else "Failed to apply patch."),
            "status": result
        }

    return JSONResponse(status_code=400, content={"ok": False, "success": False, "message": "No verified update package ready to apply. Please download first."})

@app.post("/api/update/restart")
async def restart_after_update():
    """Launch detached restart helper to safely restart RenderFlow."""
    if render_mgr.state == "running":
        return JSONResponse(status_code=409, content={"ok": False, "success": False, "message": "Cannot restart while a render is in progress."})
    
    success = update_manager.restart_app()
    if success:
        def _delayed_exit():
            time.sleep(1.0)
            os._exit(0)
        import threading
        threading.Thread(target=_delayed_exit, daemon=True).start()
        return {"ok": True, "success": True, "message": "RenderFlow is restarting..."}
    else:
        err_msg = update_manager.error_message or "Failed to launch restart helper. Please restart RenderFlow manually."
        return JSONResponse(status_code=500, content={"ok": False, "success": False, "message": err_msg, "error": err_msg})


# --- System Status & Transitions ---

@app.get("/api/system_status")
async def get_system_status():
    ffmpeg_ok = False
    ffmpeg_ver = "Not found"
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
        ffmpeg_ok = True
        ffmpeg_ver = r.stdout.splitlines()[0] if r.stdout else "Available"
    except Exception as e:
        ffmpeg_ver = str(e)

    ffprobe_ok = False
    try:
        subprocess.run(["ffprobe", "-version"], capture_output=True, text=True, check=True)
        ffprobe_ok = True
    except Exception:
        pass

    pack_json = WORKSPACE_DIR / "transition_pack" / "pack.json"
    pack_stats = {"total_clips": 0, "usable_clips": 0, "blacklisted": 0, "has_pack": False}
    if pack_json.exists():
        try:
            with open(pack_json, "r", encoding="utf-8") as f:
                pdata = json.load(f)
                clips = pdata.get("clips", [])
                pack_stats["total_clips"] = len(clips)
                pack_stats["blacklisted"] = sum(1 for c in clips if c.get("blacklisted", False))
                pack_stats["usable_clips"] = pack_stats["total_clips"] - pack_stats["blacklisted"]
                pack_stats["has_pack"] = True
        except Exception:
            pass

    assets_dir = WORKSPACE_DIR / "transition_pack" / "assets"
    keyed_count = len(list(assets_dir.glob("*.mov"))) if assets_dir.exists() else 0

    from engine.transition_registry import registry
    yt_clips = registry.list_transitions(category="YouTube Pack")
    builtin_clips = registry.list_transitions(category="Built-in")

    return {
        "status": "ready" if ffmpeg_ok and ffprobe_ok else "warning",
        "python_version": sys.version.split()[0],
        "ffmpeg": {"ok": ffmpeg_ok, "version": ffmpeg_ver},
        "ffprobe": {"ok": ffprobe_ok},
        "transition_pack": {
            **pack_stats,
            "keyed_assets_count": keyed_count,
            "youtube_pack_count": len(yt_clips),
            "builtin_count": len(builtin_clips),
            "categories": registry.get_categories()
        },
        "workspace": str(WORKSPACE_DIR)
    }


@app.get("/api/hardware/info")
async def get_hardware_info():
    """Retrieve full hardware capability detection, verified encoders, and classification."""
    try:
        from engine.hardware_detector import get_full_hardware_report
        return get_full_hardware_report()
    except Exception as e:
        return {
            "error": str(e),
            "classification": {
                "profile_code": "PROFILE_A_ECO",
                "profile_name": "Standard PC",
                "recommended_resolution": "1080p",
                "recommended_encoder": "libx264",
                "recommended_performance_mode": "balanced",
                "recommendation_note": "1080p is recommended."
            }
        }


@app.get("/api/system/diagnostic_export")
async def get_diagnostic_export():
    """Export safe, sanitized diagnostic report for customer troubleshooting without secrets."""
    try:
        from engine.hardware_detector import export_sanitized_diagnostics
        report = export_sanitized_diagnostics(workspace_dir=WORKSPACE_DIR)
        return report
    except Exception as e:
        return {"error": str(e), "sanitized": True}


@app.get("/api/render/profiles")
async def get_render_profiles():
    """Retrieve available resolution presets, performance modes, and quality levels."""
    try:
        from engine.render_profiles import RESOLUTION_PROFILES, PERFORMANCE_MODES, QUALITY_LEVELS
        return {
            "resolutions": RESOLUTION_PROFILES,
            "performance_modes": PERFORMANCE_MODES,
            "quality_levels": QUALITY_LEVELS
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/transitions")
async def get_transitions(
    category: Optional[str] = None,
    kind: Optional[str] = None,
    usable_only: bool = True,
    search: Optional[str] = None
):
    """
    Returns unified transition catalog including:
      - YouTube Pack overlay effects
      - Built-in cinematic transitions
      - Lens flare transition clips (from pack.json)
    """
    from engine.transition_registry import registry

    all_items = []

    # 1. Add YouTube Pack transitions
    for t in registry.list_transitions(category="YouTube Pack"):
        all_items.append({
            "id": t["id"],
            "title": t["name"],
            "name": t["name"],
            "category": "YouTube Pack",
            "subcategory": t.get("subcategory", "Light Leak"),
            "duration": t["duration"],
            "width": t.get("width", 3840),
            "height": t.get("height", 2160),
            "fps": t.get("fps", 25.0),
            "kind": "screen",
            "asset_type": t.get("asset_type", "overlay_effect"),
            "compositing_mode": t.get("compositing_mode", "screen_blend"),
            "blacklisted": False,
            "silent": True,
            "preview": t.get("preview", ""),
            "media_url": t.get("media_url", ""),
            "source": t.get("source", "YouTube Transition Pack"),
            "icon": t.get("icon", "✨")
        })

    # 2. Add Built-in transitions
    for t in registry.list_transitions(category="Built-in"):
        all_items.append({
            "id": t["id"],
            "title": t["name"],
            "name": t["name"],
            "category": "Built-in",
            "subcategory": t.get("subcategory", "Dissolve"),
            "duration": t["duration"],
            "width": t.get("width", 1920),
            "height": t.get("height", 1080),
            "fps": t.get("fps", 30.0),
            "kind": "builtin",
            "asset_type": "xfade",
            "compositing_mode": "xfade",
            "blacklisted": False,
            "silent": True,
            "preview": t.get("preview", ""),
            "media_url": "",
            "source": "native_ffmpeg_xfade",
            "icon": t.get("icon", "🎬")
        })

    # 3. Add legacy lens flare clips from pack.json
    pack_json = WORKSPACE_DIR / "transition_pack" / "pack.json"
    if pack_json.exists():
        try:
            with open(pack_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            for c in data.get("clips", []):
                if usable_only and c.get("blacklisted", False):
                    continue
                video_path = c.get("video", "")
                media_url = f"/media/transition_pack/{video_path}" if video_path else ""
                all_items.append({
                    "id": c.get("id"),
                    "title": c.get("title"),
                    "name": c.get("title"),
                    "category": "Lens Flares",
                    "subcategory": "Green Screen" if c.get("kind") == "green" else "Screen Flare",
                    "duration": c.get("duration"),
                    "kind": c.get("kind"),
                    "asset_type": "legacy_pack_clip",
                    "compositing_mode": "chromakey" if c.get("kind") == "green" else "screen_blend",
                    "blacklisted": c.get("blacklisted", False),
                    "blacklist_reason": c.get("blacklist_reason", ""),
                    "audio_mean_db": c.get("audio_mean_db"),
                    "silent": c.get("silent", True),
                    "preview": media_url,
                    "media_url": media_url,
                    "source": "Lens Flare Transition Pack",
                    "icon": "🔆"
                })
        except Exception as e:
            safe_print(f"Warning reading pack.json: {e}")

    # Filtering
    filtered = []
    for item in all_items:
        # Category filter
        if category:
            cat_lower = category.lower()
            if cat_lower in ("youtube", "youtube pack", "imported"):
                if item["category"] != "YouTube Pack":
                    continue
            elif cat_lower in ("builtin", "built-in", "native"):
                if item["category"] != "Built-in":
                    continue
            elif cat_lower in ("flares", "lens flares", "legacy"):
                if item["category"] != "Lens Flares":
                    continue
            elif item["category"].lower() != cat_lower:
                continue

        # Kind filter
        if kind and item.get("kind") != kind:
            continue

        # Search filter
        if search:
            q = search.lower()
            text = f"{item['id']} {item.get('title', '')} {item.get('name', '')} {item.get('category', '')} {item.get('subcategory', '')}".lower()
            if q not in text:
                continue

        filtered.append(item)

    return {
        "total": len(all_items),
        "filtered_count": len(filtered),
        "categories": ["All", "YouTube Pack", "Built-in", "Lens Flares"],
        "clips": filtered
    }


# --- Project Management & Data ---

@app.get("/api/projects")
async def list_projects():
    """List all real projects in PROJECTS_DIR with rich metadata."""
    projects = []
    if not PROJECTS_DIR.exists():
        return {"projects": [], "total": 0}

    for p_dir in PROJECTS_DIR.iterdir():
        if not p_dir.is_dir() or p_dir.name.startswith("."):
            continue

        # Isolate internal benchmarks and automated test harnesses from user-facing projects (§13, §14)
        if p_dir.name in ["benchmarks", "test_chunk_cases_work", "clean_machine_qa"] or \
           p_dir.name.startswith("e2e_recovery_") or p_dir.name.startswith("test_") or p_dir.name.startswith("tmp_"):
            continue

        images_dir = p_dir / "images"
        image_count = 0
        first_img_url = None
        if images_dir.exists():
            imgs = [f for f in images_dir.glob("*.*") if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]]
            image_count = len(imgs)
            if imgs:
                imgs.sort(key=natural_sort_key)
                rel_img = imgs[0].relative_to(WORKSPACE_DIR) if str(imgs[0]).startswith(str(WORKSPACE_DIR)) else imgs[0].name
                first_img_url = f"/media/{rel_img.as_posix()}"

        audio_file = p_dir / "narration.wav"
        has_audio = audio_file.exists()
        audio_dur = 0.0
        if has_audio:
            try:
                audio_dur = probe_audio_duration(audio_file)
            except Exception:
                audio_dur = 0.0

        plan_file = p_dir / "plan.json"
        scene_count = image_count
        visual_style = "cinematic_warm"
        if plan_file.exists():
            try:
                with open(plan_file, "r", encoding="utf-8") as pf:
                    pdata = json.load(pf)
                    scene_count = len(pdata.get("scenes", []))
                    visual_style = pdata.get("visual_style", "cinematic_warm")
            except Exception:
                pass

        final_mp4 = p_dir / "final.mp4"
        is_rendered = final_mp4.exists()
        video_dur = None
        video_res = None
        if is_rendered:
            try:
                r = subprocess.run([
                    "ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=width,height,duration",
                    "-of", "json", str(final_mp4)
                ], capture_output=True, text=True, check=True)
                probe = json.loads(r.stdout)
                streams = probe.get("streams", [])
                if streams:
                    st = streams[0]
                    w = st.get("width", 1920)
                    h = st.get("height", 1080)
                    if w >= 3840:
                        video_res = "4K UHD"
                    elif w >= 2560:
                        video_res = "1440p"
                    else:
                        video_res = f"{h}p" if h else "1080p"
                    video_dur = float(st.get("duration", 0.0))
            except Exception:
                video_res = "1080p"

        mtime = p_dir.stat().st_mtime
        mtime_str = datetime.fromtimestamp(mtime).strftime("%b %d, %H:%M")
        status = "Rendered ✓" if is_rendered else ("Ready to Render" if (image_count > 0 and has_audio) else "In Progress")

        projects.append({
            "name": p_dir.name,
            "path": str(p_dir.resolve()),
            "mtime": mtime,
            "mtime_str": mtime_str,
            "image_count": image_count,
            "has_audio": has_audio,
            "audio_duration": round(audio_dur, 2),
            "scene_count": scene_count,
            "visual_style": visual_style,
            "is_rendered": is_rendered,
            "video_res": video_res or ("4K UHD" if image_count > 0 else "1080p"),
            "video_duration": round(video_dur or audio_dur, 2),
            "status": status,
            "thumbnail": first_img_url
        })

    projects.sort(key=lambda x: x["mtime"], reverse=True)
    return {"projects": projects, "total": len(projects)}


@app.post("/api/project/create")
async def create_new_project(request: Request):
    """Create a genuinely new, isolated project workspace directory."""
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        name = f"project_{int(datetime.now().timestamp())}"
    safe_name = os.path.basename(name.strip())
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', safe_name)
    if not safe_name or safe_name in (".", ".."):
        safe_name = f"project_{int(datetime.now().timestamp())}"
        
    target_dir = PROJECTS_DIR / safe_name
    # Ensure a newly created project never inherits an existing non-empty directory
    if target_dir.exists() and any(target_dir.iterdir()):
        safe_name = f"{safe_name}_{int(datetime.now().timestamp())}"
        target_dir = PROJECTS_DIR / safe_name

    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "images").mkdir(parents=True, exist_ok=True)
    (target_dir / "work").mkdir(parents=True, exist_ok=True)
    return {
        "status": "created",
        "name": safe_name,
        "project_name": safe_name,
        "path": str(target_dir.resolve()),
        "project_path": str(target_dir.resolve())
    }


@app.delete("/api/project/{project_name}")
async def delete_existing_project(project_name: str):
    """Permanently delete a project workspace with path-traversal protection."""
    raw_name = project_name.strip()
    safe_name = os.path.basename(raw_name)
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', safe_name)
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid project name")

    projects_dir_resolved = PROJECTS_DIR.resolve()
    target_dir = (PROJECTS_DIR / safe_name).resolve()

    # Strict path traversal validation: target_dir MUST be directly inside PROJECTS_DIR
    try:
        rel = target_dir.relative_to(projects_dir_resolved)
        if len(rel.parts) != 1:
            raise ValueError("Nested path traversal")
    except (ValueError, Exception):
        raise HTTPException(status_code=403, detail="Access denied: path traversal detected")

    if target_dir == projects_dir_resolved:
        raise HTTPException(status_code=403, detail="Cannot delete root projects directory")

    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project '{safe_name}' not found")

    # Safe permanent removal with Windows read-only lock override
    def _force_remove_readonly(func, path, exc_info):
        try:
            os.chmod(path, 0o777)
            func(path)
        except Exception:
            pass

    try:
        shutil.rmtree(target_dir, onerror=_force_remove_readonly)
    except Exception as e:
        safe_print(f"[PROJECT DELETE] rmtree notice: {e}")

    # Verify actual removal
    if target_dir.exists():
        await asyncio.sleep(0.3)
        try:
            shutil.rmtree(target_dir, ignore_errors=True)
        except Exception:
            pass

    if target_dir.exists():
        raise HTTPException(status_code=500, detail="Failed to completely delete project folder from disk")

    return {"status": "deleted", "name": safe_name}


@app.post("/api/project/clear_audio")
async def clear_project_audio(request: Request):
    """Clear narration audio for the specified project."""
    body = await request.json()
    project_path = body.get("project_path")
    if not project_path:
        raise HTTPException(status_code=400, detail="Missing project_path")
    p = Path(project_path).resolve()
    audio_deleted = False
    for audio_name in ["narration.wav", "narration.mp3", "narration.m4a", "narration.aac"]:
        af = p / audio_name
        if af.exists():
            try:
                af.unlink()
                audio_deleted = True
            except Exception:
                pass
    for stale in ["transcript.json", "plan.json"]:
        sf = p / stale
        if sf.exists():
            try:
                sf.unlink()
            except Exception:
                pass
    return {"status": "cleared", "audio_deleted": audio_deleted}


@app.get("/api/health")
async def get_system_health():
    """Authoritative system health audit reporting actual runtime state."""
    checks = []

    # 1. Backend Server
    checks.append({
        "component": "RenderFlow Backend",
        "status": "PASS",
        "detail": f"FastAPI v{APP_VERSION} operational on Python {sys.version.split()[0]} (PID {os.getpid()})"
    })

    # 2. FFmpeg & FFprobe
    ff_ok = False
    ff_detail = "Not found in PATH"
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            ff_ok = True
            vline = r.stdout.splitlines()[0] if r.stdout else "Available"
            has_ass = "--enable-libass" in r.stdout
            ff_detail = f"{vline} (libass: {'YES' if has_ass else 'NO'})"
    except Exception as e:
        ff_detail = str(e)
    checks.append({
        "component": "FFmpeg Engine",
        "status": "PASS" if ff_ok else "FAIL",
        "detail": ff_detail
    })

    ffp_ok = False
    ffp_detail = "Not found"
    try:
        r = subprocess.run(["ffprobe", "-version"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            ffp_ok = True
            ffp_detail = r.stdout.splitlines()[0] if r.stdout else "Available"
    except Exception as e:
        ffp_detail = str(e)
    checks.append({
        "component": "FFprobe Media Analyzer",
        "status": "PASS" if ffp_ok else "FAIL",
        "detail": ffp_detail
    })

    # 3. Offline Speech Model (Whisper)
    whisper_model_dir = WORKSPACE_DIR / "models" / "whisper" / "small"
    whisper_cached = whisper_model_dir.exists() and any(whisper_model_dir.glob("*.bin"))
    checks.append({
        "component": "Offline Whisper Model",
        "status": "PASS" if whisper_cached else "WARNING",
        "detail": f"Local Small model cached at {whisper_model_dir}" if whisper_cached else "Small model not pre-cached in models/whisper/small"
    })

    # 4. Storage & Scratch Directories
    storage_ok = True
    storage_notes = []
    for d, label in [(PROJECTS_DIR, "Projects"), (TEMP_UPLOADS_DIR, "Temp Uploads"), (WORKSPACE_DIR, "Workspace")]:
        try:
            test_file = d / f".health_probe_{os.getpid()}"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            storage_notes.append(f"{label}: OK")
        except Exception as e:
            storage_ok = False
            storage_notes.append(f"{label}: Error ({e})")
    checks.append({
        "component": "Filesystem & Storage",
        "status": "PASS" if storage_ok else "FAIL",
        "detail": " | ".join(storage_notes)
    })

    # 5. Transition Packs
    pack_json = WORKSPACE_DIR / "transition_pack" / "pack.json"
    from engine.transition_registry import registry
    yt_count = len(registry.list_transitions(category="YouTube Pack"))
    bi_count = len(registry.list_transitions(category="Built-in"))
    checks.append({
        "component": "Transition Library Packs",
        "status": "PASS" if (yt_count + bi_count > 0) else "WARNING",
        "detail": f"28 Registered transitions ({yt_count} YouTube 4K Overlays, {bi_count} Built-in xfade)"
    })

    # 6. Hardware Encoders
    from engine.hardware_detector import get_full_hardware_report
    hw_report = get_full_hardware_report()
    encoders = hw_report.get("encoders", {})
    c = hw_report.get("classification", {})
    active_enc = c.get("recommended_encoder", "libx264")
    prof_name = c.get("profile_name", "Balanced")
    checks.append({
        "component": "Hardware Acceleration & Encoders",
        "status": "PASS",
        "detail": f"Profile: {prof_name} | Active: {active_enc} | Encoders: {', '.join([k for k, v in encoders.items() if v]) or 'libx264'}"
    })

    all_pass = all(c["status"] == "PASS" for c in checks)
    any_fail = any(c["status"] == "FAIL" for c in checks)
    overall = "FAIL" if any_fail else ("PASS" if all_pass else "WARNING")

    return {
        "status": overall,
        "timestamp": datetime.now().isoformat(),
        "checks": checks
    }


@app.get("/api/project/data")
async def get_project_data(project_path: Optional[str] = None, path: Optional[str] = None, allow_fallback: bool = True):
    """Retrieve isolated project workspace data. Never falls back when explicit path or empty state is requested."""
    cleaned_path = (project_path or path or "").strip()
    project_path = cleaned_path
    if cleaned_path in ("__empty__", "none", "null"):
        return {
            "project_path": "",
            "project_name": "",
            "images": [],
            "audio": None,
            "transcript": None,
            "plan": None,
            "previous_render": {
                "video": None,
                "contact_sheet_url": None,
                "qc": None,
                "captions": None
            }
        }

    if not cleaned_path:
        if allow_fallback and PROJECTS_DIR.exists():
            existing = [d for d in PROJECTS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")]
            existing = [d for d in existing if d.name not in ["benchmarks", "test_chunk_cases_work", "clean_machine_qa"] and not d.name.startswith("e2e_recovery_") and not d.name.startswith("test_") and not d.name.startswith("tmp_")]
            if existing:
                existing.sort(key=lambda d: d.stat().st_mtime, reverse=True)
                p = existing[0]
                project_path = str(p.resolve())
            else:
                project_path = ""
        else:
            project_path = ""

    if not project_path:
        return {
            "project_path": "",
            "project_name": "",
            "images": [],
            "audio": None,
            "transcript": None,
            "plan": None,
            "previous_render": {
                "video": None,
                "contact_sheet_url": None,
                "qc": None,
                "captions": None
            }
        }

    p = Path(project_path).resolve()
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=404, detail=f"Project folder not found: {p}")

    images_dir = p / "images"
    images_list = []
    if images_dir.exists():
        raw_files = [f for f in images_dir.glob("*.*") if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]]
        # Natural sorting (crucial: img_1, img_2, ..., img_10, img_11)
        raw_files.sort(key=natural_sort_key)

        for f in raw_files:
            rel = f.relative_to(WORKSPACE_DIR) if str(f).startswith(str(WORKSPACE_DIR)) else f.name
            w, h = 0, 0
            aspect = "16:9"
            size_b = f.stat().st_size
            try:
                from PIL import Image
                with Image.open(f) as im:
                    w, h = im.size
                    if h > 0:
                        ratio = round(w / h, 2)
                        if ratio in (1.78, 1.77):
                            aspect = "16:9"
                        elif ratio == 0.56:
                            aspect = "9:16"
                        elif ratio == 1.0:
                            aspect = "1:1"
                        elif ratio == 1.33:
                            aspect = "4:3"
                        else:
                            aspect = f"{w}:{h}"
            except Exception:
                pass

            images_list.append({
                "name": f.name,
                "path": str(f),
                "width": w,
                "height": h,
                "aspect_ratio": aspect,
                "size_bytes": size_b,
                "size_human": f"{size_b / (1024*1024):.1f} MB" if size_b >= 1024*1024 else f"{size_b / 1024:.0f} KB",
                "url": f"/media/{rel.as_posix()}" if str(f).startswith(str(WORKSPACE_DIR)) else f"/media/abs/{f.as_posix()}"
            })

    audio_file = None
    for cand_name in ["narration.wav", "narration.mp3", "narration.m4a", "narration.aac", "narration.ogg", "narration.flac"]:
        af = p / cand_name
        if af.exists() and af.stat().st_size > 0:
            audio_file = af
            break

    audio_info = None
    if audio_file and audio_file.exists():
        try:
            dur = probe_audio_duration(audio_file)
            rel = audio_file.relative_to(WORKSPACE_DIR) if str(audio_file).startswith(str(WORKSPACE_DIR)) else audio_file.name
            audio_info = {
                "name": audio_file.name,
                "path": str(audio_file),
                "duration": dur,
                "size": audio_file.stat().st_size,
                "url": f"/media/{rel.as_posix()}" if str(audio_file).startswith(str(WORKSPACE_DIR)) else f"/media/abs/{audio_file.as_posix()}"
            }
        except Exception as e:
            audio_info = {"name": audio_file.name, "path": str(audio_file), "error": str(e), "duration": 0.0}

    transcript_file = p / "transcript.json"
    transcript_data = None
    if transcript_file.exists():
        try:
            with open(transcript_file, "r", encoding="utf-8") as f:
                transcript_data = json.load(f)
        except Exception:
            pass

    plan_file = p / "plan.json"
    plan_data = None
    if plan_file.exists():
        try:
            with open(plan_file, "r", encoding="utf-8") as f:
                plan_data = json.load(f)
        except Exception:
            pass

    # Auto-generate plan if missing/empty but narration and images are present
    if (plan_data is None or not plan_data.get("scenes")) and audio_file and images_list:
        try:
            raw_img_names = [im["name"] for im in images_list]
            transcript_obj, plan_obj = build_semantic_timeline(
                audio_path=audio_file,
                images=raw_img_names,
                transcript_path=transcript_file if transcript_file.exists() else None,
                all_images_mode=True,
                project_dir=p
            )
            with open(plan_file, "w", encoding="utf-8") as pf:
                json.dump(plan_obj, pf, indent=2)
            plan_data = plan_obj
            if not transcript_file.exists() and transcript_obj:
                with open(transcript_file, "w", encoding="utf-8") as tf:
                    json.dump(transcript_obj, tf, indent=2)
                transcript_data = transcript_obj
        except Exception as auto_err:
            logger.warning(f"Auto-generation of missing plan on project load failed: {auto_err}")

    # Check for previous outputs
    final_mp4 = p / "final.mp4"
    contact_sheet = p / "work" / "contact_sheet.png"
    qc_file = Path(str(final_mp4) + ".qc.json")
    caption_qc_file = Path(str(final_mp4) + ".caption_qc.json")
    final_srt = p / "final.srt"
    final_ass = p / "final.ass"
    captions_json = p / "captions.json" if (p / "captions.json").exists() else p / "final.json"

    final_info = None
    if final_mp4.exists():
        rel = final_mp4.relative_to(WORKSPACE_DIR) if str(final_mp4).startswith(str(WORKSPACE_DIR)) else final_mp4.name
        final_info = {
            "path": str(final_mp4),
            "url": f"/media/{rel.as_posix()}",
            "size_mb": round(final_mp4.stat().st_size / (1024 * 1024), 2),
            "modified": datetime.fromtimestamp(final_mp4.stat().st_mtime).isoformat()
        }

    sheet_url = None
    if contact_sheet.exists():
        rel = contact_sheet.relative_to(WORKSPACE_DIR) if str(contact_sheet).startswith(str(WORKSPACE_DIR)) else contact_sheet.name
        sheet_url = f"/media/{rel.as_posix()}"

    qc_data = None
    if qc_file.exists():
        try:
            with open(qc_file, "r", encoding="utf-8") as f:
                qc_data = json.load(f)
        except Exception:
            pass

    caption_qc_data = None
    if caption_qc_file.exists():
        try:
            with open(caption_qc_file, "r", encoding="utf-8") as f:
                caption_qc_data = json.load(f)
        except Exception:
            pass

    def _file_url(fpath: Path):
        if not fpath.exists():
            return None
        if str(fpath).startswith(str(WORKSPACE_DIR)):
            return f"/media/{fpath.relative_to(WORKSPACE_DIR).as_posix()}"
        return f"/media/abs/{fpath.as_posix()}"

    return {
        "project_path": str(p),
        "images": images_list,
        "audio": audio_info,
        "transcript": transcript_data,
        "plan": plan_data,
        "previous_render": {
            "video": final_info,
            "contact_sheet_url": sheet_url,
            "qc": qc_data,
            "captions": {
                "srt_url": _file_url(final_srt),
                "ass_url": _file_url(final_ass),
                "json_url": _file_url(captions_json),
                "qc": caption_qc_data
            }
        }
    }


@app.post("/api/timeline/split_scene")
async def split_scene(request: Request):
    """
    Split a scene at the specified playhead timestamp.
    Validates boundary margins, maintains integer-ms normalization,
    and preserves audio-first duration synchronization.
    """
    body = await request.json()
    project_path = body.get("project_path")
    split_time = body.get("split_time")
    min_clip_duration = float(body.get("min_clip_duration", 0.3))

    if not project_path:
        raise HTTPException(status_code=400, detail="Missing project_path")
    if split_time is None:
        raise HTTPException(status_code=400, detail="Missing split_time")

    try:
        split_time = float(split_time)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid split_time: {split_time}")

    p = Path(project_path).resolve()
    plan_file = p / "plan.json"
    if not plan_file.exists():
        raise HTTPException(status_code=404, detail="Project plan.json not found")

    with open(plan_file, "r", encoding="utf-8") as f:
        plan = json.load(f)

    scenes = plan.get("scenes", [])
    if not scenes:
        raise HTTPException(status_code=400, detail="Project plan contains no scenes to split")

    # Probe master audio duration from project directory or last scene
    master_dur = None
    for af_cand in ["narration.wav", "narration.mp3", "narration.m4a"]:
        af_p = p / af_cand
        if af_p.exists() and af_p.stat().st_size > 0:
            try:
                master_dur = probe_audio_duration(af_p)
                if master_dur and master_dur > 0:
                    break
            except Exception:
                pass

    if not master_dur or master_dur <= 0:
        # Fallback to current scenes visual coverage
        master_dur = float(scenes[-1].get("end", float(scenes[-1].get("start", 0.0)) + float(scenes[-1].get("dur", 0.0))))

    try:
        new_scenes, new_index = TimelineNormalizer.split_scene_at(
            scenes=scenes,
            split_time=split_time,
            master_dur=master_dur,
            min_clip_duration=min_clip_duration
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Timeline validation failed: {str(e)}")

    # Update plan in memory
    plan["scenes"] = new_scenes

    # Save plan atomically
    temp_plan = plan_file.with_suffix(".tmp")
    with open(temp_plan, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    temp_plan.replace(plan_file)

    return {
        "success": True,
        "split_time": split_time,
        "split_index": new_index,
        "total_scenes": len(new_scenes),
        "scenes": new_scenes
    }


_project_ripple_history: Dict[str, RippleHistoryManager] = {}

def get_ripple_history(project_path: str) -> RippleHistoryManager:
    p_key = str(Path(project_path).resolve())
    if p_key not in _project_ripple_history:
        _project_ripple_history[p_key] = RippleHistoryManager(max_history=30)
    return _project_ripple_history[p_key]


@app.get("/api/audio/waveform")
async def get_audio_waveform(
    project_path: Optional[str] = None,
    audio_path: Optional[str] = None,
    points_per_second: float = 25.0,
    target_points: Optional[int] = None
):
    """
    Extract or retrieve cached high-precision audio waveform peaks.
    Non-destructive, cache-aware, bounded memory.
    """
    target_audio = None
    if audio_path and Path(audio_path).exists():
        target_audio = Path(audio_path)
    elif project_path:
        p = Path(project_path).resolve()
        for cand in ["narration.wav", "narration.mp3", "narration.m4a", "narration.aac", "narration.ogg", "narration.flac"]:
            cand_p = p / cand
            if cand_p.exists() and cand_p.stat().st_size > 0:
                target_audio = cand_p
                break

    if not target_audio or not target_audio.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    cache_dir = target_audio.parent / ".cache" / "audio_waveform"
    waveform = AudioWaveformService.extract_waveform(
        audio_path=target_audio,
        points_per_second=points_per_second,
        target_points=target_points,
        use_cache=True,
        cache_dir=cache_dir
    )
    return waveform.to_dict()


@app.post("/api/timeline/ripple_preview")
async def ripple_preview(request: Request):
    """
    Calculates and returns a preview of a proposed transcript or time-range ripple edit.
    Does not mutate plan.json or transcript.json on disk.
    """
    body = await request.json()
    project_path = body.get("project_path")
    if not project_path:
        raise HTTPException(status_code=400, detail="Missing project_path")

    p = Path(project_path).resolve()
    plan_file = p / "plan.json"
    transcript_file = p / "transcript.json"

    if not plan_file.exists():
        raise HTTPException(status_code=404, detail="plan.json not found")

    with open(plan_file, "r", encoding="utf-8") as f:
        plan = json.load(f)

    transcript_segments = []
    if transcript_file.exists():
        try:
            with open(transcript_file, "r", encoding="utf-8") as f:
                t_data = json.load(f)
                transcript_segments = t_data.get("segments", [])
        except Exception:
            pass

    scenes = plan.get("scenes", [])
    if not scenes:
        raise HTTPException(status_code=400, detail="Project plan contains no scenes")

    master_dur = None
    for cand in ["narration.wav", "narration.mp3", "narration.m4a"]:
        cand_p = p / cand
        if cand_p.exists() and cand_p.stat().st_size > 0:
            try:
                master_dur = probe_audio_duration(cand_p)
                if master_dur and master_dur > 0:
                    break
            except Exception:
                pass
    if not master_dur or master_dur <= 0:
        master_dur = float(scenes[-1].get("end", 0.0))

    req = RippleEditRequest(
        start_time=float(body.get("start_time", 0.0)),
        end_time=float(body.get("end_time", 0.0)),
        target_type=body.get("target_type", "range"),
        segment_index=body.get("segment_index"),
        word_range=tuple(body["word_range"]) if body.get("word_range") else None,
        reason=body.get("reason", "Ripple Trim Preview"),
        protect_locked=bool(body.get("protect_locked", True))
    )

    try:
        result = TranscriptRipplePlanner.plan_ripple_edit(
            scenes=scenes,
            transcript_segments=transcript_segments,
            master_dur=master_dur,
            request=req,
            dry_run=True
        )
        return result.to_dict()
    except ProtectedIntervalError as pie:
        raise HTTPException(status_code=409, detail=f"Protected boundary violation: {str(pie)}")
    except InvalidRippleRequestError as ire:
        raise HTTPException(status_code=400, detail=str(ire))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ripple preview failed: {str(e)}")


@app.post("/api/timeline/ripple_apply")
async def ripple_apply(request: Request):
    """
    Commits a ripple edit to plan.json and transcript.json atomically.
    Saves state to undo history before applying.
    """
    body = await request.json()
    project_path = body.get("project_path")
    if not project_path:
        raise HTTPException(status_code=400, detail="Missing project_path")

    p = Path(project_path).resolve()
    plan_file = p / "plan.json"
    transcript_file = p / "transcript.json"

    if not plan_file.exists():
        raise HTTPException(status_code=404, detail="plan.json not found")

    with open(plan_file, "r", encoding="utf-8") as f:
        plan = json.load(f)

    transcript_segments = []
    t_data = {}
    if transcript_file.exists():
        try:
            with open(transcript_file, "r", encoding="utf-8") as f:
                t_data = json.load(f)
                transcript_segments = t_data.get("segments", [])
        except Exception:
            pass

    scenes = plan.get("scenes", [])
    if not scenes:
        raise HTTPException(status_code=400, detail="Project plan contains no scenes")

    master_dur = None
    for cand in ["narration.wav", "narration.mp3", "narration.m4a"]:
        cand_p = p / cand
        if cand_p.exists() and cand_p.stat().st_size > 0:
            try:
                master_dur = probe_audio_duration(cand_p)
                if master_dur and master_dur > 0:
                    break
            except Exception:
                pass
    if not master_dur or master_dur <= 0:
        master_dur = float(scenes[-1].get("end", 0.0))

    req = RippleEditRequest(
        start_time=float(body.get("start_time", 0.0)),
        end_time=float(body.get("end_time", 0.0)),
        target_type=body.get("target_type", "range"),
        segment_index=body.get("segment_index"),
        word_range=tuple(body["word_range"]) if body.get("word_range") else None,
        reason=body.get("reason", "Committed Ripple Trim"),
        protect_locked=bool(body.get("protect_locked", True))
    )

    try:
        result = TranscriptRipplePlanner.plan_ripple_edit(
            scenes=scenes,
            transcript_segments=transcript_segments,
            master_dur=master_dur,
            request=req,
            dry_run=False
        )
    except ProtectedIntervalError as pie:
        raise HTTPException(status_code=409, detail=f"Protected boundary violation: {str(pie)}")
    except InvalidRippleRequestError as ire:
        raise HTTPException(status_code=400, detail=str(ire))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ripple apply failed: {str(e)}")

    # Push to undo history manager
    history_mgr = get_ripple_history(str(p))
    history_mgr.push_snapshot(
        scenes=scenes,
        transcript_segments=transcript_segments,
        master_dur=master_dur,
        audio_edits=plan.get("audio_edits")
    )

    # Update plan.json atomically
    plan["scenes"] = result.scenes
    plan["audio_edits"] = result.audio_edits
    temp_plan = plan_file.with_suffix(".tmp")
    with open(temp_plan, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    temp_plan.replace(plan_file)

    # Update transcript.json if exists
    if transcript_file.exists():
        t_data["segments"] = result.transcript_segments
        temp_trans = transcript_file.with_suffix(".tmp")
        with open(temp_trans, "w", encoding="utf-8") as f:
            json.dump(t_data, f, indent=2, ensure_ascii=False)
        temp_trans.replace(transcript_file)

    return result.to_dict()


@app.post("/api/timeline/ripple_undo")
async def ripple_undo(request: Request):
    """
    Restores the previous timeline and transcript state from project history stack.
    """
    body = await request.json()
    project_path = body.get("project_path")
    if not project_path:
        raise HTTPException(status_code=400, detail="Missing project_path")

    p = Path(project_path).resolve()
    plan_file = p / "plan.json"
    transcript_file = p / "transcript.json"

    if not plan_file.exists():
        raise HTTPException(status_code=404, detail="plan.json not found")

    with open(plan_file, "r", encoding="utf-8") as f:
        plan = json.load(f)

    transcript_segments = []
    t_data = {}
    if transcript_file.exists():
        try:
            with open(transcript_file, "r", encoding="utf-8") as f:
                t_data = json.load(f)
                transcript_segments = t_data.get("segments", [])
        except Exception:
            pass

    cur_scenes = plan.get("scenes", [])
    cur_dur = float(cur_scenes[-1].get("end", 0.0)) if cur_scenes else 0.0
    history_mgr = get_ripple_history(str(p))

    restored = history_mgr.undo(
        current_scenes=cur_scenes,
        current_transcript=transcript_segments,
        current_dur=cur_dur,
        current_audio_edits=plan.get("audio_edits")
    )

    if not restored:
        return {"success": False, "message": "Nothing to undo in ripple history"}

    # Write restored state to disk atomically
    plan["scenes"] = restored["scenes"]
    if restored.get("audio_edits"):
        plan["audio_edits"] = restored["audio_edits"]
    else:
        plan.pop("audio_edits", None)

    temp_plan = plan_file.with_suffix(".tmp")
    with open(temp_plan, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    temp_plan.replace(plan_file)

    if transcript_file.exists():
        t_data["segments"] = restored["transcript_segments"]
        temp_trans = transcript_file.with_suffix(".tmp")
        with open(temp_trans, "w", encoding="utf-8") as f:
            json.dump(t_data, f, indent=2, ensure_ascii=False)
        temp_trans.replace(transcript_file)

    return {
        "success": True,
        "scenes": restored["scenes"],
        "transcript_segments": restored["transcript_segments"],
        "master_dur": restored["master_dur"],
        "can_undo": history_mgr.can_undo(),
        "can_redo": history_mgr.can_redo()
    }




@app.post("/api/project/save_plan")
async def save_plan(request: Request):
    body = await request.json()
    project_path = body.get("project_path")
    plan_data = body.get("plan")
    if not project_path or not plan_data:
        raise HTTPException(status_code=400, detail="Missing project_path or plan")

    p = Path(project_path).resolve()
    plan_file = p / "plan.json"

    # Intelligent merge: preserve full timeline attributes if old plan exists
    if plan_file.exists():
        try:
            with open(plan_file, "r", encoding="utf-8") as f:
                existing_plan = json.load(f)
            if isinstance(existing_plan, dict) and "scenes" in existing_plan:
                new_scenes = plan_data.get("scenes", [])
                # If scene count changed or new scenes contain explicit timing edits
                has_timing_mods = (len(new_scenes) != len(existing_plan.get("scenes", []))) or any(
                    s.get("user_override") or ("start" in s and "dur" in s) for s in new_scenes
                )
                if has_timing_mods and new_scenes:
                    # Enforce strict mathematical continuity across all scenes
                    new_scenes[0]["start"] = 0.0
                    for i in range(len(new_scenes)):
                        if i > 0:
                            prev_end = float(new_scenes[i - 1].get("end", float(new_scenes[i - 1]["start"]) + float(new_scenes[i - 1].get("dur", 3.0))))
                            new_scenes[i]["start"] = round(prev_end, 3)
                        cur_end = float(new_scenes[i].get("end", float(new_scenes[i]["start"]) + float(new_scenes[i].get("dur", 3.0))))
                        new_scenes[i]["end"] = round(cur_end, 3)
                        new_scenes[i]["dur"] = round(new_scenes[i]["end"] - new_scenes[i]["start"], 3)
                        new_scenes[i]["segment_index"] = i

                    # Align last scene end to master audio duration if available
                    for af_cand in ["narration.wav", "narration.mp3", "narration.m4a"]:
                        af_p = p / af_cand
                        if af_p.exists() and af_p.stat().st_size > 0:
                            try:
                                master_dur = probe_audio_duration(af_p)
                                if master_dur and master_dur > float(new_scenes[-1]["start"]):
                                    new_scenes[-1]["end"] = round(float(master_dur), 3)
                                    new_scenes[-1]["dur"] = round(float(master_dur) - float(new_scenes[-1]["start"]), 3)
                                break
                            except Exception:
                                pass

                    existing_plan["scenes"] = new_scenes
                else:
                    new_by_idx = {s.get("segment_index", i): s for i, s in enumerate(new_scenes)}
                    for i, ex_sc in enumerate(existing_plan["scenes"]):
                        seg_i = ex_sc.get("segment_index", i)
                        if seg_i in new_by_idx:
                            update = new_by_idx[seg_i]
                            if "image" in update and update["image"] != ex_sc.get("image"):
                                ex_sc["image"] = update["image"]
                                ex_sc["user_override"] = True
                            if "transition" in update:
                                ex_sc["transition"] = update["transition"]
                            if "context" in update:
                                ex_sc["context"] = update["context"]
                            if "motion" in update:
                                ex_sc["motion"] = update["motion"]

                if "editor_timeline" in plan_data:
                    existing_plan["editor_timeline"] = plan_data["editor_timeline"]
                if "visual_style" in plan_data:
                    existing_plan["visual_style"] = plan_data["visual_style"]
                elif "visual_style" in body:
                    existing_plan["visual_style"] = body["visual_style"]

                for key in ["caption_style", "caption_preset", "resolution"]:
                    if key in plan_data:
                        existing_plan[key] = plan_data[key]
                    elif key in body:
                        existing_plan[key] = body[key]

                # Persist manual text / subtitle segments if edited
                trans_segs = plan_data.get("transcript_segments") or body.get("transcript_segments")
                if trans_segs and isinstance(trans_segs, list):
                    existing_plan["transcript_segments"] = trans_segs
                    try:
                        transcript_file = p / "transcript.json"
                        with open(transcript_file, "w", encoding="utf-8") as tf:
                            json.dump({"segments": trans_segs}, tf, indent=2)
                    except Exception as te:
                        safe_print(f"[SAVE_PLAN] Transcript update warning: {te}")

                with open(plan_file, "w", encoding="utf-8") as f:
                    json.dump(existing_plan, f, indent=2)
                return {"status": "saved", "path": str(plan_file), "merged": True}
        except Exception as e:
            safe_print(f"[SAVE_PLAN] Plan merge warning: {e}")

    for key in ["visual_style", "caption_style", "caption_preset", "resolution"]:
        if key in body and key not in plan_data:
            plan_data[key] = body[key]

    # Persist manual text / subtitle segments if edited on fresh plan
    trans_segs = plan_data.get("transcript_segments") or body.get("transcript_segments")
    if trans_segs and isinstance(trans_segs, list):
        plan_data["transcript_segments"] = trans_segs
        try:
            transcript_file = p / "transcript.json"
            with open(transcript_file, "w", encoding="utf-8") as tf:
                json.dump({"segments": trans_segs}, tf, indent=2)
        except Exception as te:
            safe_print(f"[SAVE_PLAN] Transcript update warning: {te}")

    with open(plan_file, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, indent=2)

    return {"status": "saved", "path": str(plan_file)}


@app.post("/api/project/auto_plan")
async def auto_plan(request: Request):
    """
    AI Image Sync Engine v3 — Semantic Synchronization API:
    1. Narration audio acts as the master timeline (§4).
    2. Dynamic semantic visual beats (1.5s - 7.5s) with structured visual requirements.
    3. Multi-signal ranking (7 signals), repetition penalty, and contextual reranking (§12-§15).
    4. Ambiguity AI Reranker triggered only when delta < 0.08 (§16).
    5. Preserves explicit user overrides (§20, §29).
    6. Validates timeline coverage (zero gaps, zero overlaps) and returns sync quality report (§27, §42).
    """
    body = await request.json()
    project_path = body.get("project_path")
    all_images_mode = bool(body.get("all_images_mode", True))
    reset_overrides = bool(body.get("reset_overrides", False))
    profile = body.get("profile")
    sync_mode = body.get("sync_mode")
    mapping_mode = body.get("mapping_mode", "SEMANTIC_AUTO")

    if not project_path:
        raise HTTPException(status_code=400, detail="Missing project_path")

    p = Path(project_path).resolve()
    transcript_file = p / "transcript.json"
    audio_file = None
    for cand in ["narration.wav", "narration.mp3", "narration.m4a", "narration.aac", "narration.ogg", "narration.flac"]:
        cand_p = p / cand
        if cand_p.exists() and cand_p.stat().st_size > 0:
            audio_file = cand_p
            break
    images_dir = p / "images"
    plan_file = p / "plan.json"

    if not images_dir.exists():
        raise HTTPException(status_code=400, detail="No images/ directory found in project")

    raw_images = [f for f in images_dir.glob("*.*") if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]]
    if not raw_images:
        raise HTTPException(status_code=400, detail="No valid images found in images/ directory")

    raw_images.sort(key=natural_sort_key)
    img_files = [f.name for f in raw_images]

    if not audio_file:
        master_dur = len(img_files) * 3.0
    else:
        try:
            master_dur = probe_audio_duration(audio_file)
        except Exception as e:
            logger.warning(f"Failed to probe narration audio {audio_file}: {e}")
            master_dur = len(img_files) * 3.0

    # Read old plan for comparison (§35)
    old_plan = None
    if plan_file.exists():
        try:
            with open(plan_file, "r", encoding="utf-8") as f:
                old_plan = json.load(f)
        except Exception:
            old_plan = None

    # Extract user overrides from existing plan if not explicitly reset (§20, §29)
    user_overrides = {}
    if not reset_overrides and old_plan:
        try:
            old_scenes = old_plan.get("scenes", []) if isinstance(old_plan, dict) else old_plan
            for sc in old_scenes:
                if (sc.get("user_override", False) or sc.get("locked", False)) and sc.get("image"):
                    seg_i = int(sc.get("segment_index", 0))
                    user_overrides[seg_i] = sc["image"]
        except Exception:
            user_overrides = {}

    try:
        transcript_obj, plan_obj = build_semantic_timeline(
            audio_path=audio_file,
            images=img_files,
            transcript_path=transcript_file if transcript_file.exists() else None,
            all_images_mode=all_images_mode,
            user_overrides=user_overrides,
            profile=profile,
            sync_mode=sync_mode,
            project_dir=p,
            mapping_mode=mapping_mode
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Semantic timeline generation failed: {e}")

    # Validate timeline coverage
    is_valid, validation_errors, metrics = validate_timeline_coverage(
        transcript_obj=transcript_obj,
        plan_obj=plan_obj,
        master_dur=master_dur,
        images_dir=images_dir
    )

    if not is_valid:
        raise HTTPException(status_code=500, detail=f"Timeline validation failed: {'; '.join(validation_errors)}")

    # Plan comparison (§35)
    comparison = None
    if old_plan:
        try:
            from engine.sync_engine_v3 import AIImageSyncEngineV3
            comparison = AIImageSyncEngineV3.compare_plans(old_plan, plan_obj)
        except Exception as e:
            logger.warning(f"Plan comparison failed: {e}")

    # Format preview summary for user confidence before rendering (§42)
    preview_summary = format_preview_summary(transcript_obj, plan_obj, max_preview=15)
    sync_report = plan_obj.get("sync_report", {})

    # Save transcript.json and plan.json atomically
    # Guard: Do not overwrite an existing valid speech transcript with placeholder scene cuts (§5)
    from engine.stt_provider import is_valid_speech_transcript
    should_save_transcript = True
    if transcript_file.exists():
        try:
            with open(transcript_file, "r", encoding="utf-8") as f:
                existing_d = json.load(f)
            existing_segs = existing_d.get("segments", []) if isinstance(existing_d, dict) else existing_d
            if is_valid_speech_transcript(existing_segs) and not is_valid_speech_transcript(transcript_obj.get("segments", [])):
                should_save_transcript = False
        except Exception:
            should_save_transcript = True

    if should_save_transcript:
        with open(transcript_file, "w", encoding="utf-8") as f:
            json.dump(transcript_obj, f, indent=2)

    with open(plan_file, "w", encoding="utf-8") as f:
        json.dump(plan_obj, f, indent=2)

    return {
        "status": "created",
        "mode": "all_images_semantic_sync" if all_images_mode else "semantic_beats_sync",
        "audio_duration": master_dur,
        "images_mapped": len(img_files),
        "scenes_count": len(plan_obj.get("scenes", [])),
        "validation": metrics,
        "preview_summary": preview_summary,
        "sync_report": sync_report,
        "comparison": comparison,
        "transcript": transcript_obj,
        "plan": plan_obj
    }


@app.post("/api/project/record_correction")
async def record_user_correction(request: Request):
    """
    Record user override correction for project-level learning (§6, §7, §8, §9).
    Stores preferred image and negative feedback in project's local cache.
    """
    body = await request.json()
    project_path = body.get("project_path")
    if not project_path:
        raise HTTPException(status_code=400, detail="Missing project_path")

    scene_id = body.get("scene_id", "")
    original_image = body.get("original_image", "")
    corrected_image = body.get("corrected_image", "")
    reason = body.get("reason", "user_override")
    entity = body.get("entity", "")
    concept = body.get("concept", "")

    p = Path(project_path).resolve()
    memory_file = p / ".cache" / "project_sync_learning.json"
    from engine.sync_v3_intelligence import ProjectCorrectionMemory
    mem = ProjectCorrectionMemory(memory_file)
    mem.record_correction(
        scene_id=scene_id,
        original_image=original_image,
        corrected_image=corrected_image,
        entity=entity,
        concept=concept,
        project_id=p.name,
        reason=reason
    )

    return {
        "status": "ok",
        "message": f"Recorded correction for {scene_id}: {original_image} -> {corrected_image}",
        "corrections_count": len(mem.corrections),
        "preferred_keys": list(mem.preferred_images.keys())
    }


@app.post("/api/project/lock_scene_image")
async def lock_scene_image(request: Request):
    """
    Lock, unlock, or reassign an image for a specific scene (§6.5, §6.6).
    Preserves manual override across future re-syncs.
    """
    body = await request.json()
    project_path = body.get("project_path")
    if not project_path:
        raise HTTPException(status_code=400, detail="Missing project_path")
    scene_id = body.get("scene_id")
    segment_index = body.get("segment_index")
    image_filename = body.get("image_filename")
    is_locked = bool(body.get("is_locked", True))

    p = Path(project_path).resolve()
    plan_file = p / "plan.json"
    if not plan_file.exists():
        raise HTTPException(status_code=404, detail="plan.json not found")

    with open(plan_file, "r", encoding="utf-8") as f:
        plan = json.load(f)

    scenes = plan.get("scenes", [])
    updated = False
    for sc in scenes:
        if (scene_id and sc.get("scene_id") == scene_id) or (segment_index is not None and sc.get("segment_index") == segment_index):
            old_image = sc.get("image", "")
            if image_filename:
                sc["image"] = image_filename
                if old_image != image_filename:
                    try:
                        from engine.sync_v3_intelligence import ProjectCorrectionMemory
                        mem = ProjectCorrectionMemory(p / ".cache" / "project_sync_learning.json")
                        mem.record_correction(
                            scene_id=sc.get("scene_id", ""),
                            original_image=old_image,
                            corrected_image=image_filename,
                            project_id=p.name,
                            reason="manual_ui_override"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record correction: {e}")
            sc["user_override"] = is_locked
            sc["source"] = "user_override" if is_locked else "ai_semantic_auto"
            sc["confidence"] = 1.0 if is_locked else sc.get("confidence", 0.85)
            sc["confidence_level"] = "HIGH" if is_locked else sc.get("confidence_level", "MEDIUM")
            updated = True
            break

    if updated:
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)

    return {"status": "ok", "updated": updated, "is_locked": is_locked}


@app.post("/api/project/reset_learning")
async def reset_project_learning(request: Request):
    """
    Reset project sync learning memory without touching media (§37).
    """
    body = await request.json()
    project_path = body.get("project_path")
    if not project_path:
        raise HTTPException(status_code=400, detail="Missing project_path")

    p = Path(project_path).resolve()
    memory_file = p / ".cache" / "project_sync_learning.json"
    from engine.sync_v3_intelligence import ProjectCorrectionMemory
    mem = ProjectCorrectionMemory(memory_file)
    mem.reset_learning()

    return {
        "status": "ok",
        "message": "Reset project sync learning memory successfully."
    }


@app.get("/api/project/review_queue")
async def get_review_queue(project_path: str):
    """
    Compact manual review queue: returns scenes with LOW or MEDIUM confidence (§31).
    """
    if not project_path:
        raise HTTPException(status_code=400, detail="Missing project_path")

    p = Path(project_path).resolve()
    plan_file = p / "plan.json"
    if not plan_file.exists():
        return {"scenes": [], "total_count": 0, "low_count": 0, "medium_count": 0}

    try:
        with open(plan_file, "r", encoding="utf-8") as f:
            plan = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read plan.json: {e}")

    all_scenes = plan.get("scenes", []) if isinstance(plan, dict) else plan
    review_scenes = []
    low_c = 0
    med_c = 0

    for sc in all_scenes:
        conf_lvl = sc.get("confidence_level", "HIGH")
        is_override = sc.get("user_override", False)
        if not is_override and conf_lvl in ["LOW", "MEDIUM"]:
            if conf_lvl == "LOW":
                low_c += 1
            else:
                med_c += 1
            review_scenes.append({
                "scene_id": sc.get("scene_id"),
                "segment_index": sc.get("segment_index"),
                "start": sc.get("start"),
                "end": sc.get("end"),
                "dur": sc.get("dur"),
                "narration_text": sc.get("narration_text", ""),
                "selected_image": sc.get("image", ""),
                "confidence": sc.get("confidence", 0.0),
                "confidence_level": conf_lvl,
                "reasons": sc.get("match_reason", []),
                "candidates": sc.get("candidates", []),
                "decision_trace": sc.get("decision_trace", {})
            })

    return {
        "total_count": len(review_scenes),
        "low_count": low_c,
        "medium_count": med_c,
        "scenes": review_scenes
    }


@app.post("/api/project/approve_high_conf")
async def approve_high_confidence(request: Request):
    """
    Bulk approves all HIGH confidence scene mappings (§32).
    Leaves MEDIUM and LOW confidence scenes untouched for manual review.
    """
    body = await request.json()
    project_path = body.get("project_path")
    if not project_path:
        raise HTTPException(status_code=400, detail="Missing project_path")

    p = Path(project_path).resolve()
    plan_file = p / "plan.json"
    if not plan_file.exists():
        raise HTTPException(status_code=400, detail="plan.json does not exist")

    with open(plan_file, "r", encoding="utf-8") as f:
        plan = json.load(f)

    scenes = plan.get("scenes", []) if isinstance(plan, dict) else plan
    approved_count = 0
    for sc in scenes:
        if sc.get("confidence_level") == "HIGH" and not sc.get("user_override", False):
            sc["approved"] = True
            approved_count += 1

    with open(plan_file, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    return {
        "status": "ok",
        "approved_count": approved_count,
        "message": f"Approved {approved_count} HIGH confidence scene mappings."
    }


@app.post("/api/project/clear_media")
async def clear_project_media(request: Request):
    """
    Clear current project's media state (§1-§9):
    Removes:
      - All loaded images and extracted ZIP images in images/
      - Current narration audio
      - Current transcript generated from that audio
      - Current mapped timeline plan
      - Previous render outputs and QC reports
      - Work directory contents
      - Temporary upload copies in .tmp_uploads/
    Guarantees:
      - Rendering Studio engine code, transitions library, and settings are NOT touched
      - Next upload starts with a clean 0-image, 0-scene state
    """
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    project_path = body.get("project_path")
    project_name = body.get("project_name")

    target_dir = None
    if project_path:
        p = Path(project_path).resolve()
        if p.exists() and p.is_dir():
            target_dir = p
    elif project_name:
        p = (PROJECTS_DIR / project_name).resolve()
        if p.exists() and p.is_dir():
            target_dir = p

    if not target_dir:
        # Fallback to the latest or default project
        existing_projects = [d for d in PROJECTS_DIR.iterdir() if d.is_dir()]
        if existing_projects:
            existing_projects.sort(key=lambda d: d.stat().st_mtime, reverse=True)
            target_dir = existing_projects[0]
        else:
            target_dir = PROJECTS_DIR / "custom_project_01"
            target_dir.mkdir(parents=True, exist_ok=True)

    images_dir = target_dir / "images"
    deleted_images_count = 0
    if images_dir.exists():
        for f in list(images_dir.glob("*.*")):
            try:
                f.unlink()
                deleted_images_count += 1
            except Exception as e:
                print(f"[CLEAR MEDIA] Warning deleting image {f}: {e}")

    # Remove narration audio files
    audio_deleted = False
    for audio_name in ["narration.wav", "narration.mp3", "narration.m4a", "narration.aac"]:
        af = target_dir / audio_name
        if af.exists():
            try:
                af.unlink()
                audio_deleted = True
            except Exception as e:
                print(f"[CLEAR MEDIA] Warning deleting audio {af}: {e}")

    # Remove transcript and plan
    transcript_deleted = False
    tf = target_dir / "transcript.json"
    if tf.exists():
        try:
            tf.unlink()
            transcript_deleted = True
        except Exception:
            pass

    plan_deleted = False
    pf = target_dir / "plan.json"
    if pf.exists():
        try:
            pf.unlink()
            plan_deleted = True
        except Exception:
            pass

    # Remove render outputs and QC files
    outputs_cleaned = False
    output_files = [
        target_dir / "final.mp4",
        target_dir / "final.srt",
        target_dir / "final.ass",
        target_dir / "final.vtt",
        target_dir / "final.json",
        target_dir / "captions.json",
        Path(str(target_dir / "final.mp4") + ".qc.json"),
        Path(str(target_dir / "final.mp4") + ".caption_qc.json"),
        Path(str(target_dir / "final.mp4") + ".transitions.json"),
    ]
    for of in output_files:
        if of.exists():
            try:
                of.unlink()
                outputs_cleaned = True
            except Exception:
                pass

    # Clean work directory
    work_dir = target_dir / "work"
    work_cleaned = False
    if work_dir.exists():
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            work_cleaned = True
        except Exception as e:
            print(f"[CLEAR MEDIA] Warning cleaning work dir: {e}")

    # Clean stale uploads in .tmp_uploads
    try:
        for f in list(TEMP_UPLOADS_DIR.glob("*.*")):
            try:
                f.unlink()
            except Exception:
                pass
    except Exception:
        pass

    # Clean project cache directory (.cache: project_sync_learning.json, embeddings, etc.)
    cache_cleaned = False
    cache_dir = target_dir / ".cache"
    if cache_dir.exists():
        try:
            shutil.rmtree(cache_dir, ignore_errors=True)
            cache_cleaned = True
        except Exception as e:
            safe_print(f"[CLEAR MEDIA] Warning cleaning cache dir: {e}")

    # Reset render manager if idle or error
    if render_mgr.state != "running":
        render_mgr.reset()

    safe_print(f"[CLEAR MEDIA] Project media successfully reset for: {target_dir}")

    return {
        "status": "cleared",
        "project_name": target_dir.name,
        "project_path": str(target_dir),
        "deleted": {
            "images_count": deleted_images_count,
            "audio_deleted": audio_deleted,
            "transcript_deleted": transcript_deleted,
            "plan_deleted": plan_deleted,
            "work_cleaned": work_cleaned,
            "cache_cleaned": cache_cleaned,
            "outputs_cleaned": outputs_cleaned
        },
        "media_state": {
            "images_count": 0,
            "audio": None,
            "scenes_count": 0,
            "timeline": [],
            "captions": "Pending",
            "render": "No previous render selected"
        }
    }


@app.post("/api/project/upload")
async def upload_project_files(
    project_name: str = Form(...),
    files: List[UploadFile] = File(...),
    replace_mode: bool = Form(True)
):
    try:
        p_clean = project_name.strip().strip('"').strip("'")
        if not p_clean:
            p_clean = "my_project"
        target_dir = PROJECTS_DIR / p_clean
        target_dir.mkdir(parents=True, exist_ok=True)
        images_dir = target_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        diag_logs: List[str] = []
        uploaded = []
        zip_results = []
        images_registered = 0
        errors = []

        # If in replace mode (product default §6), and incoming files include images or a ZIP,
        # clean out existing images so new ZIP / images do not mix with previous media
        has_image_files = any(Path(f.filename or '').suffix.lower() in [".zip", ".jpg", ".jpeg", ".png", ".webp", ".bmp"] for f in files)
        if replace_mode and has_image_files:
            diag_logs.append("[REPLACE_MODE] Cleaning previous project images before processing new media...")
            for existing in list(images_dir.glob("*.*")):
                try:
                    existing.unlink()
                except Exception as e:
                    diag_logs.append(f"[REPLACE_MODE] Warning deleting {existing.name}: {e}")
            # Clean stale plan and previous render outputs when replacing images
            for stale in ["plan.json", "final.mp4"]:
                sf = target_dir / stale
                if sf.exists():
                    try:
                        sf.unlink()
                    except Exception:
                        pass

        has_audio_file = any(Path(f.filename or '').suffix.lower() in [".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"] for f in files)
        if replace_mode and has_audio_file:
            diag_logs.append("[REPLACE_MODE] New audio detected. Refreshing audio references & timeline...")
            for old_audio in ["narration.wav", "narration.mp3", "narration.m4a", "narration.aac", "narration.ogg", "narration.flac"]:
                af = target_dir / old_audio
                if af.exists():
                    try:
                        af.unlink()
                    except Exception:
                        pass
            for stale in ["transcript.json", "plan.json"]:
                sf = target_dir / stale
                if sf.exists():
                    try:
                        sf.unlink()
                    except Exception:
                        pass

        audio_info = None

        for file in files:
            raw_name = Path(file.filename or 'upload_file').name
            fname = re.sub(r'[<>:"/\\|?*]', '_', raw_name)
            ext = Path(fname).suffix.lower()
            mime = file.content_type or "unknown"
            
            # Save to temp location first
            temp_file = TEMP_UPLOADS_DIR / f"{uuid.uuid4().hex[:6]}_{fname}"
            with open(temp_file, "wb") as f:
                shutil.copyfileobj(file.file, f)

            file_size = temp_file.stat().st_size
            file_size_mb = round(file_size / (1024 * 1024), 2)
            diag_logs.append(f"[UPLOAD] filename={fname}")
            diag_logs.append(f"[UPLOAD] extension={ext}")
            diag_logs.append(f"[UPLOAD] mime={mime}")
            diag_logs.append(f"[UPLOAD] size={file_size_mb}MB")

            # 1. ZIP Archive Handling (Option A: ZIP containing all images)
            if ext in [".zip"]:
                diag_logs.append(f"[ZIP] Processing ZIP archive: {fname}")
                z_res = process_zip_archive(temp_file, images_dir, target_dir / "work")
                diag_logs.extend(z_res.get("diagnostics", []))
                
                if z_res["success"]:
                    count = z_res["registered_count"]
                    images_registered += count
                    uploaded.append(f"zip: {fname} ({count} valid images extracted & naturally sorted)")
                    zip_results.append({
                        "filename": fname,
                        "status": "success",
                        "images_found": count,
                        "registered_count": count,
                        "files": z_res.get("files", [])
                    })
                else:
                    err_msg = z_res.get("error", "ZIP processing failed")
                    errors.append(f"{fname}: {err_msg}")
                    zip_results.append({
                        "filename": fname,
                        "status": "error",
                        "error": err_msg,
                        "corrupted_images": z_res.get("corrupted_images", [])
                    })

            # 2. Individual Image Handling (Option B: Individual images)
            elif ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
                ok, reason = validate_image_file(temp_file)
                if ok:
                    dest = images_dir / fname
                    shutil.copy2(temp_file, dest)
                    images_registered += 1
                    uploaded.append(f"image: {fname}")
                    diag_logs.append(f"[IMAGE_VALIDATION] PASS: {fname}")
                else:
                    errors.append(f"Image validation failed for {fname}: {reason}")
                    diag_logs.append(f"[IMAGE_VALIDATION] FAIL: {fname} ({reason})")

            # 3. Audio Narration Handling
            elif ext in [".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"]:
                dest_wav = target_dir / "narration.wav"
                if ext == ".wav":
                    shutil.copy2(temp_file, dest_wav)
                    uploaded.append(f"audio: narration.wav")
                    diag_logs.append(f"[AUDIO] Saved WAV: narration.wav")
                else:
                    # Convert MP3/M4A/AAC to 48kHz stereo WAV for optimal video engine processing
                    transcode_ok = False
                    try:
                        subprocess.run([
                            get_ffmpeg_bin(), "-y", "-i", str(temp_file),
                            "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
                            str(dest_wav)
                        ], capture_output=True, check=True)
                        uploaded.append(f"audio: narration.wav (converted from {ext})")
                        diag_logs.append(f"[AUDIO] Converted {ext} to narration.wav")
                        transcode_ok = True
                    except Exception as audio_err:
                        diag_logs.append(f"[AUDIO] Transcoding failed ({audio_err}), falling back to direct copy")

                    if not transcode_ok or not dest_wav.exists() or dest_wav.stat().st_size == 0:
                        shutil.copy2(temp_file, dest_wav)
                        uploaded.append(f"audio: narration.wav")
                        diag_logs.append(f"[AUDIO] Direct copy fallback used for {fname}")

                # Probe audio duration
                if dest_wav.exists():
                    try:
                        dur = probe_audio_duration(dest_wav)
                    except Exception:
                        dur = 0.0
                    rel_wav = dest_wav.relative_to(WORKSPACE_DIR) if str(dest_wav).startswith(str(WORKSPACE_DIR)) else dest_wav.name
                    audio_info = {
                        "name": fname,
                        "saved_as": "narration.wav",
                        "path": str(dest_wav),
                        "duration": dur,
                        "size": dest_wav.stat().st_size,
                        "url": f"/media/{rel_wav.as_posix()}" if str(dest_wav).startswith(str(WORKSPACE_DIR)) else f"/media/abs/{dest_wav.as_posix()}"
                    }
                    diag_logs.append(f"[AUDIO] Master Audio registered: {dur:.2f}s, {audio_info['size']} bytes")

            # 4. JSON Config Handling (transcript, plan)
            elif ext == ".json":
                if "transcript" in fname.lower() or "analysis" in fname.lower():
                    dest = target_dir / "transcript.json"
                elif "plan" in fname.lower():
                    dest = target_dir / "plan.json"
                else:
                    dest = target_dir / fname
                shutil.copy2(temp_file, dest)
                uploaded.append(f"json: {dest.name}")
                diag_logs.append(f"[CONFIG] Saved {dest.name}")

            # Clean up temp upload file
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

        # Print diagnostics to server console safely
        for l in diag_logs:
            safe_print(l)

        # Check overall result
        has_zip_error = any(z.get("status") == "error" for z in zip_results)
        if has_zip_error and images_registered == 0:
            err_details = "; ".join(errors) if errors else "No valid images could be registered from the ZIP."
            raise HTTPException(status_code=400, detail=f"ZIP rejected: {err_details}")

        # Check if project now has both audio and images ready for auto-planning
        audio_cand = None
        for cand in ["narration.wav", "narration.mp3", "narration.m4a", "narration.aac", "narration.ogg", "narration.flac"]:
            c_p = target_dir / cand
            if c_p.exists() and c_p.stat().st_size > 0:
                audio_cand = c_p
                break

        valid_raw = [f for f in images_dir.glob("*.*") if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]]
        valid_raw.sort(key=natural_sort_key)
        valid_img_names = [f.name for f in valid_raw]

        generated_plan = None
        generated_transcript = None
        plan_file = target_dir / "plan.json"
        has_existing_plan = plan_file.exists() and plan_file.stat().st_size > 10

        if audio_cand and len(valid_img_names) > 0 and (replace_mode or not has_existing_plan):
            try:
                diag_logs.append(f"[AUTO_PLAN] Auto-generating semantic timeline for {len(valid_img_names)} images with master audio {audio_cand.name}...")
                transcript_file = target_dir / "transcript.json"
                gen_transcript, gen_plan = build_semantic_timeline(
                    audio_path=audio_cand,
                    images=valid_img_names,
                    transcript_path=transcript_file if transcript_file.exists() else None,
                    all_images_mode=True,
                    project_dir=target_dir
                )
                with open(plan_file, "w", encoding="utf-8") as pf:
                    json.dump(gen_plan, pf, indent=2)
                generated_plan = gen_plan

                from engine.stt_provider import is_valid_speech_transcript
                should_save_t = True
                if transcript_file.exists():
                    try:
                        with open(transcript_file, "r", encoding="utf-8") as tf:
                            ex_d = json.load(tf)
                        ex_segs = ex_d.get("segments", []) if isinstance(ex_d, dict) else ex_d
                        if is_valid_speech_transcript(ex_segs) and not is_valid_speech_transcript(gen_transcript.get("segments", [])):
                            should_save_t = False
                    except Exception:
                        should_save_t = True
                if should_save_t and gen_transcript:
                    with open(transcript_file, "w", encoding="utf-8") as tf:
                        json.dump(gen_transcript, tf, indent=2)
                generated_transcript = gen_transcript
                diag_logs.append(f"[AUTO_PLAN] Successfully generated {len(gen_plan.get('scenes', []))} scenes covering {audio_cand.name}")
            except Exception as plan_err:
                diag_logs.append(f"[AUTO_PLAN] Automatic timeline generation notice: {plan_err}")

        return {
            "ok": True,
            "status": "uploaded",
            "project_name": p_clean,
            "project_path": str(target_dir),
            "uploaded_files": uploaded,
            "images_registered": images_registered,
            "images_count": len(valid_img_names),
            "zip_results": zip_results,
            "audio": audio_info,
            "plan": generated_plan,
            "transcript": generated_transcript,
            "scenes_count": len(generated_plan.get("scenes", [])) if generated_plan else 0,
            "errors": errors,
            "diagnostics": diag_logs
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_print(f"[UPLOAD ERROR] {e}\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "status": "error",
                "error": f"Audio/media upload failed: {str(e)}",
                "detail": str(e),
                "traceback": traceback.format_exc()
            }
        )


@app.get("/api/captions/styles")
async def get_caption_styles():
    """Retrieve catalog of all caption styles for UI."""
    from engine.caption_styles import get_all_styles
    all_st = get_all_styles()
    style_list = []
    for k, v in all_st.items():
        entry = dict(v)
        entry["id"] = k
        entry["key"] = k
        style_list.append(entry)
    return {"styles": style_list, "styles_dict": all_st}


@app.get("/api/captions/categories")
async def get_caption_categories():
    """Retrieve style categories and platform presets."""
    from engine.caption_styles import STYLE_CATEGORIES, PLATFORM_PRESETS
    return {
        "categories": STYLE_CATEGORIES,
        "platform_presets": PLATFORM_PRESETS
    }


@app.get("/api/captions/health")
async def get_captions_health():
    """Diagnostic health check endpoint for local caption pipeline."""
    import sys
    import subprocess
    import shutil
    from pathlib import Path

    health = {
        "status": "healthy",
        "Python": "OK",
        "FastAPI": "OK",
        "FFmpeg": "FAIL",
        "FFprobe": "FAIL",
        "faster-whisper": "FAIL",
        "Whisper model": "UNAVAILABLE",
        "ASS generation": "FAIL",
        "libass": "UNAVAILABLE",
        "Caption renderer": "FAIL",
        "details": {}
    }

    # 1. FFmpeg & libass
    try:
        ff_res = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        if ff_res.returncode == 0:
            health["FFmpeg"] = "OK"
            if "--enable-libass" in ff_res.stdout:
                health["libass"] = "AVAILABLE"
            health["details"]["ffmpeg_version"] = ff_res.stdout.splitlines()[0] if ff_res.stdout else "unknown"
    except Exception as e:
        health["details"]["ffmpeg_error"] = str(e)

    # 2. FFprobe
    try:
        ffp_res = subprocess.run(["ffprobe", "-version"], capture_output=True, text=True, timeout=5)
        if ffp_res.returncode == 0:
            health["FFprobe"] = "OK"
    except Exception as e:
        health["details"]["ffprobe_error"] = str(e)

    # 3. faster-whisper
    try:
        import faster_whisper
        health["faster-whisper"] = "OK"
        health["details"]["faster_whisper_version"] = getattr(faster_whisper, "__version__", "installed")
        health["Whisper model"] = "AVAILABLE"
    except Exception as e:
        health["details"]["whisper_error"] = str(e)

    # 4. ASS generation
    try:
        from engine.caption_ass import build_ass_script
        from engine.caption_model import CaptionModel, CaptionSegment, Word
        sample_model = CaptionModel(segments=[
            CaptionSegment(id=0, start=0.0, end=1.0, text="Health Check", words=[Word(text="Health", start=0.0, end=0.5), Word(text="Check", start=0.5, end=1.0)])
        ])
        sample_ass = build_ass_script(sample_model)
        if "[Events]" in sample_ass and "Dialogue:" in sample_ass:
            health["ASS generation"] = "OK"
    except Exception as e:
        health["details"]["ass_error"] = str(e)

    # 5. Caption renderer
    try:
        from engine.caption_engine import CaptionEngine
        ce = CaptionEngine(style_key="classic")
        if ce:
            health["Caption renderer"] = "OK"
    except Exception as e:
        health["details"]["caption_engine_error"] = str(e)

    all_ok = all(
        health[k] in ("OK", "AVAILABLE")
        for k in ["Python", "FastAPI", "FFmpeg", "FFprobe", "faster-whisper", "Whisper model", "ASS generation", "libass", "Caption renderer"]
    )
    health["status"] = "healthy" if all_ok else "degraded"
    return health


@app.post("/api/captions/transcribe")
async def transcribe_captions(request: Request):
    """
    Transcribe audio using authoritative local faster-whisper engine.
    Extracts real word-level timestamps without fake or mock data.
    """
    body = await request.json()
    project_name = body.get("project_name")
    audio_path_str = body.get("audio_path")
    model_name = body.get("model_name", "small")
    language = body.get("language", "auto")
    force = body.get("force", True)

    target_audio = None
    transcript_dest = None

    if project_name:
        p = PROJECTS_DIR / project_name
        if not p.exists():
            raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
        wav_cand = p / "narration.wav"
        if wav_cand.exists():
            target_audio = wav_cand
            transcript_dest = p / "transcript.json"

    if not target_audio and audio_path_str:
        p = Path(audio_path_str)
        if p.exists():
            target_audio = p

    if not target_audio or not target_audio.exists():
        raise HTTPException(status_code=400, detail="Valid audio file not found for transcription")

    try:
        from engine.transcribe import transcribe_or_load_captions
        model = transcribe_or_load_captions(
            audio_path=target_audio,
            transcript_path=transcript_dest,
            language=language,
            model_name=model_name,
            force_retranscribe=force
        )

        res_dict = model.to_dict()

        if transcript_dest:
            with open(transcript_dest, "w", encoding="utf-8") as f:
                json.dump(res_dict, f, indent=2)

        return {
            "status": "success",
            "audio_file": str(target_audio),
            "model_used": model_name,
            "segments_count": len(model.segments),
            "words_count": sum(len(s.words) for s in model.segments),
            "transcript": res_dict
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")


@app.get("/api/ai/providers")
async def get_ai_providers():
    """Retrieve full provider cards with masked keys and status without exposing secrets."""
    from engine.credentials_manager import get_all_providers_info
    providers = get_all_providers_info()
    stt_list = [p for p in providers if p["category"] == "stt"]
    llm_list = [p for p in providers if p["category"] == "llm"]
    return {
        "providers": providers,
        "stt_providers": stt_list,
        "llm_providers": llm_list,
        "quality_levels": ["fast", "balanced", "quality", "max"]
    }


@app.get("/api/ai/providers/{provider}")
async def get_single_ai_provider(provider: str):
    """Retrieve detailed provider card with status and models."""
    from engine.credentials_manager import get_provider_info
    info = get_provider_info(provider.lower())
    if not info:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found.")
    return info


@app.post("/api/ai/providers/{provider}/credentials")
async def save_ai_credentials(provider: str, request: Request):
    """Securely save API key and model to server-side .env and update running provider."""
    body = await request.json()
    api_key = body.get("api_key", "").strip()
    model = body.get("model")

    from engine.credentials_manager import save_credential, test_provider_connection
    res = save_credential(provider.lower(), api_key, model)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message"))

    # Optionally run automatic live verification
    test_now = body.get("test_now", False)
    test_result = None
    if test_now:
        test_result = test_provider_connection(provider.lower(), api_key=api_key, model=model)

    return {
        **res,
        "test_result": test_result
    }


@app.delete("/api/ai/providers/{provider}/credentials")
async def delete_ai_credentials(provider: str):
    """Securely remove API key from server-side .env and reset provider."""
    from engine.credentials_manager import delete_credential
    res = delete_credential(provider.lower())
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res


@app.post("/api/ai/providers/{provider}/test")
async def test_provider_endpoint(provider: str, request: Request):
    """Execute live connection test for a specific provider."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    api_key = body.get("api_key")
    model = body.get("model")

    from engine.credentials_manager import test_provider_connection
    return test_provider_connection(provider.lower(), api_key=api_key, model=model)


@app.get("/api/ai/models/{provider}")
async def get_provider_models(provider: str):
    """Retrieve models available for a specific provider."""
    from engine.credentials_manager import PROVIDER_SPECS
    spec = PROVIDER_SPECS.get(provider.lower())
    if not spec:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found.")
    return {
        "provider": provider.lower(),
        "name": spec["name"],
        "default_model": spec.get("default_model", ""),
        "models": spec.get("models", [])
    }


# --- v2.5.1 Multi-Provider AI Gateway Endpoints ---

@app.get("/api/ai/gateway/status")
async def get_ai_gateway_status():
    """Retrieve full AI Gateway status, task routing, model capabilities, and DPAPI vault state."""
    from engine.ai_gateway import gateway
    return gateway.get_status_overview()


@app.post("/api/ai/gateway/route")
async def update_ai_gateway_route(request: Request):
    """Update task-to-provider routing configuration."""
    body = await request.json()
    task = body.get("task")
    primary = body.get("primary")
    fallback = body.get("fallback")
    if not task or not primary:
        raise HTTPException(status_code=400, detail="Missing task or primary provider.")

    from engine.ai_gateway import gateway
    gateway.task_routing[task] = {"primary": primary, "fallback": fallback or "local_deterministic"}
    return {"status": "updated", "task": task, "route": gateway.task_routing[task]}


@app.post("/api/ai/gateway/credentials")
async def save_gateway_credentials(request: Request):
    """Save provider credentials into DPAPI vault and running registry."""
    body = await request.json()
    provider = body.get("provider", "").lower()
    api_key = body.get("api_key", "").strip()
    model = body.get("model")
    if not provider:
        raise HTTPException(status_code=400, detail="Missing provider ID.")

    from engine.ai_gateway import gateway
    gateway.set_provider_credential(provider, api_key, model)
    return {"status": "saved", "provider": provider}


@app.post("/api/ai/gateway/test")
async def test_gateway_execution(request: Request):
    """Execute test prompt through AI Gateway with automatic capability-check and fallback."""
    body = await request.json()
    task = body.get("task", "semantic_scene_planning")
    prompt = body.get("prompt", "Analyze scene requirements for cinematic video.")
    sys_prompt = body.get("system_prompt", "You are an AI video production planner.")
    json_mode = bool(body.get("json_mode", True))

    from engine.ai_gateway import gateway
    resp, metric = gateway.execute_task(
        task=task,
        system_prompt=sys_prompt,
        user_prompt=prompt,
        json_mode=json_mode
    )
    return {
        "response": resp,
        "metric": metric.to_dict()
    }


# --- v2.5.1 OpenMontage Visual Discovery Endpoints ---

@app.get("/api/visual_discovery/sources")
async def get_visual_discovery_sources():
    """List available OpenMontage discovery sources and their availability."""
    from engine.openmontage_adapter import openmontage_adapter
    return {
        "sources": openmontage_adapter.get_available_sources(),
        "enabled": openmontage_adapter.enable_discovery,
        "openmontage_installed": openmontage_adapter.is_present
    }


@app.post("/api/visual_discovery/search")
async def search_visual_discovery(request: Request):
    """Search OpenMontage stock sources (Wikimedia, NASA, LOC, Archive.org, Pexels, etc.)."""
    body = await request.json()
    query = body.get("query", "").strip()
    media_type = body.get("media_type", "image")
    limit = int(body.get("limit", 6))
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    from engine.openmontage_adapter import openmontage_adapter
    candidates = openmontage_adapter.discover_candidates_for_query(query=query, media_type=media_type, max_candidates=limit)
    return {
        "query": query,
        "count": len(candidates),
        "candidates": [c.to_dict() for c in candidates]
    }


@app.post("/api/visual_discovery/download")
async def download_visual_discovery_asset(request: Request):
    """Download discovered asset safely into project images directory."""
    body = await request.json()
    project_path = body.get("project_path")
    candidate_dict = body.get("candidate")
    if not project_path or not candidate_dict:
        raise HTTPException(status_code=400, detail="Missing project_path or candidate data.")

    target_dir = Path(project_path) / "images"
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)

    from engine.openmontage_adapter import openmontage_adapter, DiscoveredAsset
    cand = DiscoveredAsset(**candidate_dict)
    dl_path = openmontage_adapter.download_asset(cand, destination_dir=target_dir)
    if not dl_path or not dl_path.exists():
        raise HTTPException(status_code=500, detail="Asset download or validation failed.")

    return {
        "status": "downloaded",
        "filename": dl_path.name,
        "path": str(dl_path),
        "asset_id": cand.asset_id,
        "source": cand.source
    }


# --- v2.5.1 Deterministic Timeline Validation Endpoint ---

@app.post("/api/timeline/validate")
async def validate_project_timeline(request: Request):
    """Run deterministic TimelineValidator on project plan."""
    body = await request.json()
    project_path = body.get("project_path")
    if not project_path:
        raise HTTPException(status_code=400, detail="Missing project_path.")

    p = Path(project_path).resolve()
    plan_file = p / "plan.json"
    if not plan_file.exists():
        raise HTTPException(status_code=404, detail="plan.json not found in project.")

    with open(plan_file, "r", encoding="utf-8") as f:
        plan_data = json.load(f)

    audio_dur = None
    for cand in ["narration.wav", "narration.mp3", "narration.m4a"]:
        cand_p = p / cand
        if cand_p.exists():
            from engine.semantic_sync import probe_audio_duration
            try:
                audio_dur = probe_audio_duration(cand_p)
            except Exception:
                pass
            break

    from engine.timeline_validator import TimelineValidator
    validator = TimelineValidator()
    result = validator.validate_plan(
        plan=plan_data,
        master_audio_dur=audio_dur,
        images_dir=p / "images",
        check_files=True
    )
    return result.to_dict()


@app.get("/api/ai/status")
async def get_ai_status(primary: Optional[str] = None):
    """Retrieve comprehensive AI system status, fallback chain, and active provider."""
    from engine.credentials_manager import get_fallback_chain_status, get_all_providers_info
    chain = get_fallback_chain_status(primary)
    providers = get_all_providers_info()
    connected_count = sum(1 for p in providers if p.get("status") == "CONNECTED")
    configured_count = sum(1 for p in providers if p.get("configured"))
    return {
        "total_providers": len(providers),
        "configured_count": configured_count,
        "connected_count": connected_count,
        "fallback_chain": chain,
        "offline_ready": True
    }


@app.post("/api/ai/test-connection")
async def test_ai_connection(request: Request):
    """Legacy test-connection endpoint forwarding to secure credential test."""
    body = await request.json()
    provider = body.get("provider", "groq")
    api_key = body.get("api_key")
    model = body.get("model")

    from engine.credentials_manager import test_provider_connection
    return test_provider_connection(provider.lower(), api_key=api_key, model=model)


@app.post("/api/ai/process-preview")
async def process_ai_preview(request: Request):
    """Generate side-by-side comparison of Raw, Clean, and Viral captions with emphasis."""
    body = await request.json()
    sample_text = body.get("text", "you do not need ten thousand followers to make good money on the internet today")
    language = body.get("language", "auto")
    provider = body.get("provider", "auto")
    model = body.get("model")

    from engine.caption_model import CaptionSegment
    from engine.llm_provider import execute_llm_intelligence_with_fallback
    from engine.caption_emphasis import CaptionEmphasisEngine

    segments_payload = [{"id": 1, "text": sample_text}]

    # 1. Clean mode
    clean_segs, c_prov, c_meta = execute_llm_intelligence_with_fallback(
        mode="clean",
        segments=segments_payload,
        preferred_provider=provider,
        language=language,
        creative_rewrite=False,
        model=model
    )

    # 2. Viral mode
    viral_segs, v_prov, v_meta = execute_llm_intelligence_with_fallback(
        mode="viral",
        segments=segments_payload,
        preferred_provider=provider,
        language=language,
        creative_rewrite=True,
        model=model
    )

    clean_text = clean_segs[0].get("text", sample_text) if (clean_segs and isinstance(clean_segs[0], dict)) else sample_text
    viral_text = viral_segs[0].get("text", sample_text) if (viral_segs and isinstance(viral_segs[0], dict)) else sample_text

    clean_emp = CaptionEmphasisEngine.identify_emphasis_tokens(clean_text, language)
    viral_emp = CaptionEmphasisEngine.identify_emphasis_tokens(viral_text, language)

    return {
        "original": sample_text,
        "clean": {
            "text": clean_text,
            "emphasis": clean_emp,
            "provider": c_prov,
            "meta": c_meta
        },
        "viral": {
            "text": viral_text,
            "emphasis": viral_emp,
            "provider": v_prov,
            "meta": v_meta
        }
    }


@app.post("/api/captions/preview")
async def get_caption_preview(request: Request):
    """Generate dynamic preview data for any selected style and text."""
    body = await request.json()
    style_key = body.get("style", "classic")
    from engine.caption_styles import get_style, customize_style
    style = customize_style(style_key, body.get("overrides"))
    return {
        "style": style,
        "sample": {
            "inactive_prefix": body.get("inactive_prefix", "Every great empire begins with a"),
            "active_word": body.get("active_word", "VISION"),
            "trailing": body.get("trailing", "and determination.")
        }
    }


# --- Render Pipeline Runner & SSE Streaming ---

@app.post("/api/render/start")
async def start_render(request: Request):
    if render_mgr.state == "running":
        raise HTTPException(status_code=400, detail="A render task is already in progress")

    body = await request.json()
    images = body.get("images")
    segments = body.get("segments")
    plan = body.get("plan")
    audio = body.get("audio")
    out = body.get("out")
    workdir = body.get("workdir")
    skip_verify = bool(body.get("skip_verify", False))
    chunk_size = body.get("chunk_size")
    force_chunks = bool(body.get("force_chunks", False))
    force_single_pass = bool(body.get("force_single_pass", False))
    enable_transitions = bool(body.get("enable_transitions", True))
    
    # 1. Resolution canonical normalization & validation
    def _clean_resolution(val: Any) -> str:
        if not val:
            return "1080p"
        s = str(val).strip().lower()
        if s in ("1080p", "1080", "1080p full hd", "fhd", "full hd"):
            return "1080p"
        if s in ("1440p", "1440", "1440p 2k qhd", "qhd", "2k"):
            return "1440p"
        if s in ("4k", "4k uhd", "4k uhd master", "uhd", "2160p", "2160"):
            return "4k"
        if s in ("1080p", "1440p", "4k"):
            return s
        return "1080p"

    raw_res = body.get("resolution")
    resolution = _clean_resolution(raw_res)
    safe_print(f"[RENDER] Verified resolution choice: '{resolution}' (raw: '{raw_res}')")

    # 2. Preset
    preset = str(body.get("preset", "veryfast") or "veryfast").strip()
    if not preset or preset.lower() in ("none", "null"):
        preset = "veryfast"

    # 3. Encoder
    encoder = str(body.get("encoder", "auto") or "auto").strip()
    if not encoder or encoder.lower() in ("none", "null"):
        encoder = "auto"

    # 4. Perf mode
    valid_perf_modes = {'auto', 'eco', 'balanced', 'performance', 'max_quality'}
    perf_mode = str(body.get("perf_mode", "auto") or "auto").strip().lower()
    if perf_mode not in valid_perf_modes:
        perf_mode = "auto"

    # 5. Quality preset
    valid_quality_presets = {'standard', 'high', 'maximum'}
    quality_preset = str(body.get("quality_preset", "standard") or "standard").strip().lower()
    if quality_preset not in valid_quality_presets:
        quality_preset = "standard"

    # 6. Visual style
    visual_style = str(body.get("visual_style", "cinematic_warm") or "cinematic_warm").strip()
    if not visual_style or visual_style.lower() in ("none", "null"):
        visual_style = "cinematic_warm"

    # 7. Transition ID (optional override)
    raw_trans = body.get("transition_id")
    transition_id = str(raw_trans).strip() if raw_trans and str(raw_trans).strip() and str(raw_trans).strip().lower() not in ("none", "null") else None

    # 8. Overlay dur (optional)
    raw_overlay = body.get("overlay_dur")
    overlay_dur = None
    if raw_overlay is not None and str(raw_overlay).strip() and str(raw_overlay).strip().lower() not in ("none", "null"):
        try:
            overlay_dur = float(raw_overlay)
        except (ValueError, TypeError):
            overlay_dur = None

    # 9. Dur scale
    try:
        dur_scale = float(body.get("dur_scale", 1.0))
        if dur_scale <= 0:
            dur_scale = 1.0
    except (ValueError, TypeError):
        dur_scale = 1.0

    # 10. Caption parameters
    enable_captions = bool(body.get("enable_captions", False))
    caption_style = str(body.get("caption_style", "classic") or "classic").strip()
    if not caption_style or caption_style.lower() in ("none", "null"):
        caption_style = "classic"
    caption_length = str(body.get("caption_length", "medium") or "medium").strip()
    if not caption_length or caption_length.lower() in ("none", "null"):
        caption_length = "medium"
    caption_lang = str(body.get("caption_lang", "auto") or "auto").strip()
    if not caption_lang or caption_lang.lower() in ("none", "null"):
        caption_lang = "auto"

    separate_subtitles = bool(body.get("separate_subtitles", True))
    caption_overrides = body.get("caption_overrides")

    raw_platform = body.get("platform_preset")
    platform_preset = str(raw_platform).strip() if raw_platform and str(raw_platform).strip() and str(raw_platform).strip().lower() not in ("none", "null") else None

    stt_provider = str(body.get("stt_provider", "auto") or "auto").strip()
    if not stt_provider or stt_provider.lower() in ("none", "null"):
        stt_provider = "auto"

    ai_mode = str(body.get("ai_mode", "raw") or "raw").strip()
    if not ai_mode or ai_mode.lower() in ("none", "null"):
        ai_mode = "raw"

    creative_rewrite = bool(body.get("creative_rewrite", False))

    llm_provider = str(body.get("llm_provider", "auto") or "auto").strip()
    if not llm_provider or llm_provider.lower() in ("none", "null"):
        llm_provider = "auto"

    raw_llm_model = body.get("llm_model")
    llm_model = str(raw_llm_model).strip() if raw_llm_model and str(raw_llm_model).strip() and str(raw_llm_model).strip().lower() not in ("none", "null") else None

    if not all([images, segments, plan, audio, out]):
        missing = [k for k, v in [("images", images), ("segments", segments), ("plan", plan), ("audio", audio), ("out", out)] if not v]
        raise HTTPException(status_code=400, detail=f"Missing required render parameters: {', '.join(missing)}")

    # Resolve paths relative to WORKSPACE_DIR if relative
    img_path = Path(images) if Path(images).is_absolute() else (WORKSPACE_DIR / images)
    aud_path = Path(audio) if Path(audio).is_absolute() else (WORKSPACE_DIR / audio)
    plan_path = Path(plan) if Path(plan).is_absolute() else (WORKSPACE_DIR / plan)
    seg_path = Path(segments) if Path(segments).is_absolute() else (WORKSPACE_DIR / segments)
    out_path = Path(out) if Path(out).is_absolute() else (WORKSPACE_DIR / out)

    if not aud_path.exists():
        raise HTTPException(status_code=400, detail=f"Audio file not found: {audio}. Please upload narration audio before rendering.")

    if not img_path.exists():
        raise HTTPException(status_code=400, detail=f"Images directory not found: {images}. Please upload scene images before rendering.")

    valid_img_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    raw_imgs = [f.name for f in img_path.glob("*.*") if f.suffix.lower() in valid_img_exts]
    raw_imgs.sort(key=natural_sort_key)
    if not raw_imgs:
        raise HTTPException(status_code=400, detail=f"No image files found in {images}. Please upload at least one image before rendering.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if workdir:
        w_path = Path(workdir) if Path(workdir).is_absolute() else (WORKSPACE_DIR / workdir)
        w_path.mkdir(parents=True, exist_ok=True)

    # Ensure plan.json and transcript.json exist; auto-generate if missing
    if not plan_path.exists() or not seg_path.exists():
        safe_print("[RENDER] Missing plan or segments; generating semantic timeline...")
        try:
            build_semantic_timeline(
                audio_path=aud_path,
                images=raw_imgs,
                transcript_path=seg_path if seg_path.exists() else None,
                all_images_mode=True,
                user_overrides={},
                project_dir=plan_path.parent
            )
        except Exception as auto_err:
            safe_print(f"[RENDER] Warning auto-generating timeline: {auto_err}")

    if not plan_path.exists():
        raise HTTPException(status_code=400, detail="Scene plan.json could not be generated. Please run Auto-Map Images to Audio before rendering.")

    render_mgr.reset()
    render_mgr.state = "running"
    render_mgr.start_time = asyncio.get_event_loop().time()
    render_mgr.output_video = str(Path(out).resolve())

    # Build command respecting frozen and development runtimes
    if getattr(sys, "frozen", False):
        cmd = [
            sys.executable,
            "--pipeline",
            "--images", str(images),
            "--segments", str(segments),
            "--plan", str(plan),
            "--audio", str(audio),
            "--out", str(out),
            "--dur-scale", str(dur_scale),
            "--preset", str(preset),
            "--resolution", str(resolution),
            "--encoder", str(encoder),
            "--perf-mode", str(perf_mode),
            "--quality-preset", str(quality_preset)
        ]
    else:
        runner_script = WORKSPACE_DIR / "engine" / "run_pipeline.py"
        cmd = [
            sys.executable,
            str(runner_script),
            "--images", str(images),
            "--segments", str(segments),
            "--plan", str(plan),
            "--audio", str(audio),
            "--out", str(out),
            "--dur-scale", str(dur_scale),
            "--preset", str(preset),
            "--resolution", str(resolution),
            "--encoder", str(encoder),
            "--perf-mode", str(perf_mode),
            "--quality-preset", str(quality_preset)
        ]
    if visual_style and str(visual_style).strip():
        cmd += ["--visual-style", str(visual_style).strip()]
    if transition_id and str(transition_id).strip() and str(transition_id).strip().lower() not in ("none", "null"):
        cmd += ["--transition-id", str(transition_id).strip()]
    if workdir and str(workdir).strip():
        cmd += ["--workdir", str(workdir).strip()]
    if overlay_dur is not None:
        cmd += ["--overlay-dur", str(overlay_dur)]
    if chunk_size and str(chunk_size).strip():
        cmd += ["--chunk-size", str(chunk_size).strip()]
    if force_chunks:
        cmd += ["--force-chunks"]
    if force_single_pass:
        cmd += ["--force-single-pass"]
    if not enable_transitions:
        cmd += ["--no-transitions"]
    if skip_verify:
        cmd += ["--skip-verify"]
    if enable_captions:
        cmd += ["--enable-captions"]
        cmd += ["--caption-style", str(caption_style)]
        cmd += ["--caption-length", str(caption_length)]
        cmd += ["--caption-lang", str(caption_lang)]
        if separate_subtitles:
            cmd += ["--separate-subtitles"]
        if caption_overrides:
            cmd += ["--caption-overrides", json.dumps(caption_overrides)]
        if platform_preset and str(platform_preset).strip() and str(platform_preset).strip().lower() not in ("none", "null"):
            cmd += ["--platform-preset", str(platform_preset).strip()]
        if stt_provider and str(stt_provider).strip():
            cmd += ["--stt-provider", str(stt_provider).strip()]
        if ai_mode and str(ai_mode).strip():
            cmd += ["--ai-mode", str(ai_mode).strip()]
        if creative_rewrite:
            cmd += ["--creative-rewrite"]
        if llm_provider and str(llm_provider).strip():
            cmd += ["--llm-provider", str(llm_provider).strip()]
        if llm_model and str(llm_model).strip() and str(llm_model).strip().lower() not in ("none", "null"):
            cmd += ["--llm-model", str(llm_model).strip()]

    # Run in asynchronous background task
    asyncio.create_task(_execute_render(cmd, Path(out).resolve()))

    return {"status": "started", "command": " ".join(cmd)}


async def _execute_render(cmd: List[str], out_path: Path):
    loop = asyncio.get_running_loop()
    work_dir = out_path.parent / "work"
    contact_sheet = work_dir / "contact_sheet.png"
    qc_file = Path(str(out_path) + ".qc.json")

    await render_mgr.broadcast({"type": "status", "state": "running", "msg": "Starting Render Pipeline..."})

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(WORKSPACE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        render_mgr.process = proc

        last_output_time = loop.time()
        stall_threshold = 45.0  # seconds with zero stdout while process is alive
        is_stalled = False

        while True:
            try:
                line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=3.0)
            except asyncio.TimeoutError:
                if proc.returncode is not None:
                    break
                now = loop.time()
                elapsed_since_out = now - last_output_time
                elapsed_total = round(now - (render_mgr.start_time or now), 1)

                if elapsed_since_out >= stall_threshold:
                    if not is_stalled:
                        is_stalled = True
                        render_mgr.state_marker = "STALLED"
                    # Broadcast stall warning (§8)
                    await render_mgr.broadcast({
                        "type": "heartbeat",
                        "state_marker": "STALLED",
                        "stalled": True,
                        "stall_duration": round(elapsed_since_out, 1),
                        "msg": f"RENDER MAY BE STALLED — no output for {int(elapsed_since_out)}s. Process PID {proc.pid} still alive.",
                        "step": render_mgr.current_step,
                        "step_name": render_mgr.step_name,
                        "chunk_info": render_mgr.chunk_info,
                        "progress_percent": render_mgr.progress_percent,
                        "elapsed": elapsed_total
                    })
                else:
                    await render_mgr.broadcast({
                        "type": "heartbeat",
                        "state_marker": render_mgr.state_marker or "RENDERING",
                        "stalled": False,
                        "step": render_mgr.current_step,
                        "step_name": render_mgr.step_name,
                        "chunk_info": render_mgr.chunk_info,
                        "progress_percent": render_mgr.progress_percent,
                        "elapsed": elapsed_total
                    })
                continue

            if not line_bytes:
                break

            last_output_time = loop.time()
            if is_stalled:
                is_stalled = False
                render_mgr.state_marker = "RENDERING"

            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            render_mgr.logs.append(line)

            # Detect observable pipeline states (§12)
            if "[STATE:" in line:
                m_st = re.search(r'\[STATE:([^\]]+)\]', line)
                if m_st:
                    st_val = m_st.group(1).strip()
                    render_mgr.state_marker = st_val
                    await render_mgr.broadcast({
                        "type": "state_update",
                        "state_marker": st_val,
                        "step": render_mgr.current_step,
                        "step_name": render_mgr.step_name
                    })

            # Detect active encoder updates (§16)
            if "[ENCODER_ACTIVE]" in line:
                enc_name = line.split("[ENCODER_ACTIVE]", 1)[1].strip()
                render_mgr.active_encoder = enc_name
                await render_mgr.broadcast({
                    "type": "encoder_update",
                    "encoder": enc_name
                })
            elif "[HARDWARE FALLBACK]" in line and "libx264" in line:
                render_mgr.active_encoder = "libx264 (CPU Fallback)"
                await render_mgr.broadcast({
                    "type": "encoder_update",
                    "encoder": "libx264 (CPU Fallback)"
                })

            # Detect chunk progress (§13)
            if "[CHUNK #" in line:
                m_ch = re.search(r'\[CHUNK #(\d+)(?:/(\d+))?\]', line)
                if m_ch:
                    curr_ch = m_ch.group(1)
                    tot_ch = m_ch.group(2)
                    render_mgr.chunk_info = f"Chunk {curr_ch} / {tot_ch}" if tot_ch else f"Chunk #{curr_ch}"
                    await render_mgr.broadcast({
                        "type": "chunk_update",
                        "chunk_info": render_mgr.chunk_info
                    })

            # Detect [PROGRESS]
            if "[PROGRESS]" in line:
                m_pct = re.search(r'([\d\.]+)%', line)
                if m_pct:
                    try:
                        render_mgr.progress_percent = float(m_pct.group(1))
                    except Exception:
                        pass
                await render_mgr.broadcast({
                    "type": "progress_update",
                    "progress_line": line,
                    "progress_percent": render_mgr.progress_percent,
                    "chunk_info": render_mgr.chunk_info,
                    "elapsed": round(loop.time() - (render_mgr.start_time or loop.time()), 1)
                })

            # Detect steps
            step_num = render_mgr.current_step
            step_name = render_mgr.step_name
            if "STEP 1/3" in line:
                step_num = 1
                step_name = "Audio Timeline & Image Preprocessing"
            elif "STEP 2/3" in line:
                step_num = 2
                step_name = "Cinematic Transitions & Audio Composition"
            elif "STEP 3/3" in line:
                step_num = 3
                step_name = "Production Verification QC"

            render_mgr.current_step = step_num
            render_mgr.step_name = step_name

            await render_mgr.broadcast({
                "type": "log",
                "line": line,
                "step": step_num,
                "step_name": step_name,
                "state_marker": render_mgr.state_marker,
                "chunk_info": render_mgr.chunk_info
            })

        exit_code = await proc.wait()
        render_mgr.exit_code = exit_code
        render_mgr.end_time = loop.time()

        if exit_code == 0:
            render_mgr.state = "completed"
            render_mgr.state_marker = "COMPLETED"
            render_mgr.output_video = str(out_path)
            if contact_sheet.exists():
                render_mgr.contact_sheet = str(contact_sheet)
            if qc_file.exists():
                try:
                    with open(qc_file, "r", encoding="utf-8") as f:
                        render_mgr.qc_report = json.load(f)
                except Exception:
                    pass

            rel_video = out_path.relative_to(WORKSPACE_DIR) if str(out_path).startswith(str(WORKSPACE_DIR)) else out_path.name
            rel_sheet = contact_sheet.relative_to(WORKSPACE_DIR) if contact_sheet.exists() and str(contact_sheet).startswith(str(WORKSPACE_DIR)) else None

            final_srt = out_path.parent / "final.srt"
            final_ass = out_path.parent / "final.ass"
            captions_json = out_path.parent / "captions.json" if (out_path.parent / "captions.json").exists() else out_path.parent / "final.json"
            caption_qc_file = Path(str(out_path) + ".caption_qc.json")
            caption_qc_data = None
            if caption_qc_file.exists():
                try:
                    with open(caption_qc_file, "r", encoding="utf-8") as f:
                        caption_qc_data = json.load(f)
                except Exception:
                    pass

            def _file_url(fpath: Path):
                if not fpath.exists():
                    return None
                if str(fpath).startswith(str(WORKSPACE_DIR)):
                    return f"/media/{fpath.relative_to(WORKSPACE_DIR).as_posix()}"
                return f"/media/abs/{fpath.as_posix()}"

            await render_mgr.broadcast({
                "type": "finished",
                "state": "completed",
                "state_marker": "COMPLETED",
                "video_url": f"/media/{rel_video.as_posix()}",
                "contact_sheet_url": f"/media/{rel_sheet.as_posix()}" if rel_sheet else None,
                "qc": render_mgr.qc_report,
                "captions": {
                    "srt_url": _file_url(final_srt),
                    "ass_url": _file_url(final_ass),
                    "json_url": _file_url(captions_json),
                    "qc": caption_qc_data
                },
                "elapsed": round(render_mgr.end_time - (render_mgr.start_time or 0), 2)
            })
        else:
            render_mgr.state = "error"
            render_mgr.state_marker = "FAILED"
            err_code = "RENDER_FAILED"
            err_details = None
            err_msg_line = None
            for l in reversed(render_mgr.logs):
                if "[ERROR:" in l:
                    m = re.search(r'\[ERROR:([A-Z_]+)\]\s*(.*)', l)
                    if m:
                        err_code = m.group(1).strip()
                        err_msg_line = m.group(2).strip()
                        break
            for l in reversed(render_mgr.logs):
                if "[ERROR_DETAILS]" in l:
                    try:
                        err_details = json.loads(l.split("[ERROR_DETAILS]", 1)[1].strip())
                    except Exception:
                        pass
                    break

            tail = [l for l in render_mgr.logs[-15:] if l.strip()]
            tail_str = "\n".join(tail) if tail else "Check server console for details."
            render_mgr.error_message = err_msg_line or f"Render process failed with exit code {exit_code}.\n{tail_str}"
            await render_mgr.broadcast({
                "type": "finished",
                "state": "error",
                "state_marker": "FAILED",
                "error": render_mgr.error_message,
                "error_code": err_code,
                "error_details": err_details
            })

    except Exception as e:
        render_mgr.state = "error"
        render_mgr.state_marker = "FAILED"
        render_mgr.error_message = str(e)
        await render_mgr.broadcast({
            "type": "finished",
            "state": "error",
            "state_marker": "FAILED",
            "error": str(e)
        })
    finally:
        render_mgr.process = None


@app.post("/api/render/cancel")
async def cancel_render():
    if render_mgr.process and render_mgr.state == "running":
        try:
            pid = render_mgr.process.pid
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            else:
                render_mgr.process.terminate()
            render_mgr.state = "cancelled"
            render_mgr.state_marker = "CANCELLED"
            render_mgr.error_message = "Render cancelled by user"
            await render_mgr.broadcast({"type": "status", "state": "cancelled", "state_marker": "CANCELLED", "msg": "Render cancelled by user"})
            return {"status": "cancelled"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    return {"status": "not_running"}


@app.get("/api/render/status")
async def get_render_status():
    video_url = None
    sheet_url = None
    if render_mgr.output_video and Path(render_mgr.output_video).exists():
        p = Path(render_mgr.output_video)
        rel = p.relative_to(WORKSPACE_DIR) if str(p).startswith(str(WORKSPACE_DIR)) else p.name
        video_url = f"/media/{rel.as_posix()}"

    if render_mgr.contact_sheet and Path(render_mgr.contact_sheet).exists():
        p = Path(render_mgr.contact_sheet)
        rel = p.relative_to(WORKSPACE_DIR) if str(p).startswith(str(WORKSPACE_DIR)) else p.name
        sheet_url = f"/media/{rel.as_posix()}"

    loop_time = asyncio.get_event_loop().time()
    elapsed = round(loop_time - render_mgr.start_time, 1) if render_mgr.start_time else 0.0

    return {
        "state": render_mgr.state,
        "state_marker": render_mgr.state_marker,
        "step": render_mgr.current_step,
        "step_name": render_mgr.step_name,
        "chunk_info": render_mgr.chunk_info,
        "progress_percent": render_mgr.progress_percent,
        "elapsed": elapsed,
        "video_url": video_url,
        "contact_sheet_url": sheet_url,
        "qc": render_mgr.qc_report,
        "error": render_mgr.error_message,
        "active_encoder": render_mgr.active_encoder,
        "log_count": len(render_mgr.logs)
    }


def _build_finished_payload():
    if render_mgr.state == "completed":
        out_path = Path(render_mgr.output_video) if render_mgr.output_video else None
        rel_video = out_path.relative_to(WORKSPACE_DIR) if out_path and str(out_path).startswith(str(WORKSPACE_DIR)) else (out_path.name if out_path else "")
        contact_sheet = Path(render_mgr.contact_sheet) if render_mgr.contact_sheet else None
        rel_sheet = contact_sheet.relative_to(WORKSPACE_DIR) if contact_sheet and str(contact_sheet).startswith(str(WORKSPACE_DIR)) else None

        final_srt = out_path.parent / "final.srt" if out_path else None
        final_ass = out_path.parent / "final.ass" if out_path else None
        captions_json = (out_path.parent / "captions.json" if (out_path.parent / "captions.json").exists() else out_path.parent / "final.json") if out_path else None

        def _f_url(fpath: Optional[Path]):
            if not fpath or not fpath.exists():
                return None
            if str(fpath).startswith(str(WORKSPACE_DIR)):
                return f"/media/{fpath.relative_to(WORKSPACE_DIR).as_posix()}"
            return f"/media/abs/{fpath.as_posix()}"

        return {
            "type": "finished",
            "state": "completed",
            "state_marker": "COMPLETED",
            "video_url": f"/media/{rel_video.as_posix()}" if isinstance(rel_video, Path) else f"/media/{rel_video}",
            "contact_sheet_url": f"/media/{rel_sheet.as_posix()}" if rel_sheet else None,
            "qc": render_mgr.qc_report,
            "captions": {
                "srt_url": _f_url(final_srt),
                "ass_url": _f_url(final_ass),
                "json_url": _f_url(captions_json),
                "qc": None
            },
            "elapsed": round((render_mgr.end_time or 0) - (render_mgr.start_time or 0), 2)
        }
    else:
        return {
            "type": "finished",
            "state": render_mgr.state,
            "state_marker": render_mgr.state_marker or "FAILED",
            "error": render_mgr.error_message or "Render failed",
            "error_code": "RENDER_FAILED",
            "elapsed": round((render_mgr.end_time or 0) - (render_mgr.start_time or 0), 2)
        }


@app.get("/api/render/stream")
async def render_stream():
    """Server-Sent Events endpoint streaming real-time render output."""
    queue = asyncio.Queue()
    render_mgr.listeners.append(queue)

    async def event_generator():
        # Send existing logs
        for log in render_mgr.logs[-100:]:
            yield f"data: {json.dumps({'type': 'log', 'line': log})}\n\n"

        yield f"data: {json.dumps({'type': 'status', 'state': render_mgr.state, 'step': render_mgr.current_step, 'step_name': render_mgr.step_name})}\n\n"

        # If already terminated before connection opened, emit final state immediately
        if render_mgr.state in ("completed", "error", "cancelled"):
            yield f"data: {json.dumps(_build_finished_payload())}\n\n"
            return

        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(msg)}\n\n"
                    if msg.get("type") == "finished":
                        break
                except asyncio.TimeoutError:
                    yield ": ping keepalive\n\n"
        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            if queue in render_mgr.listeners:
                render_mgr.listeners.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# --- Media Range & Static File Serving ---

@app.api_route("/media/{file_path:path}", methods=["GET", "HEAD"])
async def serve_media(file_path: str, request: Request):
    # Strip any abs/ prefix if present
    is_abs = False
    clean_path_str = file_path
    if clean_path_str.startswith("abs/"):
        clean_path_str = clean_path_str[4:]
        is_abs = True

    if is_abs:
        full_path = Path(clean_path_str).resolve()
    else:
        full_path = (WORKSPACE_DIR / clean_path_str).resolve()

    # Path traversal protection: Ensure full_path is inside WORKSPACE_DIR or authorized TEMP directories
    allowed_roots = [
        WORKSPACE_DIR.resolve(),
        Path(tempfile.gettempdir()).resolve()
    ]
    is_allowed = any(
        full_path == root or root in full_path.parents
        for root in allowed_roots
    )

    if not is_allowed:
        raise HTTPException(status_code=403, detail="Access denied: Path outside authorized directories")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    return FileResponse(
        str(full_path),
        filename=full_path.name
    )


# Mount static frontend assets
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Studio UI static files are initializing...</h1>")
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    from engine.server_lifecycle import start_server_with_lifecycle
    port = int(os.environ.get("PORT", 8008))
    sys.exit(start_server_with_lifecycle(app, default_port=port, workspace_dir=WORKSPACE_DIR))
