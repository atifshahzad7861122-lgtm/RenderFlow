"""
Rendering Studio Engine v2 — Self-Contained Application Launcher
================================================================
Entry point for packaged Windows distribution.
Configures bundled paths for FFmpeg, Whisper Small, transition pack,
and hardware detector without requiring any external system dependencies.
"""

import os
import sys
import webbrowser
import threading
import time
from pathlib import Path

def get_base_dir() -> Path:
    """Get the application root directory in frozen or script mode."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

def setup_environment(base_dir: Path):
    """Configure local environment to strictly prioritize bundled binaries."""
    # 1. Bundled bin/ (ffmpeg.exe, ffprobe.exe)
    bin_dir = base_dir / "bin"
    if bin_dir.exists():
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
        ffmpeg_exe = bin_dir / "ffmpeg.exe"
        ffprobe_exe = bin_dir / "ffprobe.exe"
        if ffmpeg_exe.exists():
            os.environ["FFMPEG_BINARY"] = str(ffmpeg_exe)
        if ffprobe_exe.exists():
            os.environ["FFPROBE_BINARY"] = str(ffprobe_exe)

    # 2. Bundled models/whisper & models/clip
    whisper_dir = base_dir / "models" / "whisper"
    if whisper_dir.exists():
        os.environ["WHISPER_MODELS_DIR"] = str(whisper_dir)

    clip_dir = base_dir / "models" / "clip"
    if clip_dir.exists():
        os.environ["RENDERFLOW_MODELS_DIR"] = str(base_dir / "models")
        bpe_file = clip_dir / "bpe_simple_vocab_16e6.txt.gz"
        if bpe_file.exists():
            os.environ["RENDERFLOW_BPE_PATH"] = str(bpe_file)

    # 3. Ensure offline-first operation
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSCRIPTION_OFFLINE"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUNBUFFERED"] = "1"

    # 4. Add base_dir to sys.path so modules (engine, web, etc.) are importable
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))

    # 5. Prioritize PathFinder in sys.meta_path so loose modules in base_dir take precedence
    import importlib.machinery
    path_finders = [finder for finder in sys.meta_path if finder is importlib.machinery.PathFinder]
    for pf in path_finders:
        sys.meta_path.remove(pf)
        sys.meta_path.insert(0, pf)

def main():
    base_dir = get_base_dir()
    setup_environment(base_dir)

    # Handle CLI subcommands
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd in ("--diagnostics", "-d", "diagnostics"):
            from engine.hardware_detector import get_hardware_info
            import json
            print("\n=== RENDERFLOW BY AI WITH ATIF — HARDWARE DIAGNOSTICS ===")
            info = get_hardware_info()
            print(json.dumps(info, indent=2))
            return 0
        elif cmd in ("--version", "-v", "version"):
            try:
                from engine.version import __version__
                print(f"RenderFlow by AI With Atif — Build {__version__} (Self-Contained Windows x64)")
            except Exception:
                print("RenderFlow by AI With Atif — Build 2.2.3 (Self-Contained Windows x64)")
            return 0
        elif cmd == "--pipeline" or "run_pipeline" in cmd or "fast_pipeline" in cmd:
            # Forward remaining args to fast_pipeline
            sys.argv.pop(1)
            from engine.fast_pipeline import main as pipeline_main
            return pipeline_main()
        elif cmd in ("--verify", "-vfy", "verify") or "verify_output" in cmd:
            sys.argv.pop(1)
            from engine.verify_output import main as verify_main
            return verify_main()

    # Default mode: Launch web UI server with robust single-instance lifecycle
    port = int(os.environ.get("PORT", "8000"))
    from engine.server_lifecycle import start_server_with_lifecycle
    from web.server import app

    return start_server_with_lifecycle(app, default_port=port, workspace_dir=base_dir)

if __name__ == "__main__":
    sys.exit(main() or 0)
