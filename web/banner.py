"""
RenderFlow — Professional Cinematic Rendering Workstation
Brand: AI With Atif
Product: RenderFlow
"""

import sys
import shutil
import time
from pathlib import Path

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ANSI Color Codes (Standard Windows 10/11 & Terminal safe)
CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"
WHITE = "\033[37m"
GREEN = "\033[92m"
BLUE = "\033[94m"
PURPLE = "\033[95m"
DIM = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"


ATIF_LINES = [
    " █████╗ ████████╗██╗███████╗",
    "██╔══██╗╚══██╔══╝██║██╔════╝",
    "███████║   ██║   ██║█████╗  ",
    "██╔══██║   ██║   ██║██╔══╝  ",
    "██║  ██║   ██║   ██║██║     ",
    "╚═╝  ╚═╝   ╚═╝   ╚═╝╚═╝     "
]


def print_splash():
    """Prints the large ASCII wordmark and full creator branding hierarchy."""
    width = 68
    sep_line = "═" * (width - 2)

    print(f"{CYAN}╔{sep_line}╗{RESET}")
    print(f"{CYAN}║{RESET}{' ' * (width - 2)}{CYAN}║{RESET}")

    def print_word_block(lines):
        for line in lines:
            pad_left = (width - 2 - len(line)) // 2
            pad_right = width - 2 - len(line) - pad_left
            print(f"{CYAN}║{RESET}{' ' * pad_left}{CYAN}{BOLD}{line}{RESET}{' ' * pad_right}{CYAN}║{RESET}")

    # Print primary ATIF block wordmark
    print_word_block(ATIF_LINES)

    print(f"{CYAN}║{RESET}{' ' * (width - 2)}{CYAN}║{RESET}")
    print(f"{CYAN}║{RESET}{CYAN}{BOLD}{'AI WITH ATIF'.center(width - 2)}{RESET}{CYAN}║{RESET}")
    print(f"{CYAN}║{RESET}{' ' * (width - 2)}{CYAN}║{RESET}")
    print(f"{CYAN}║{RESET}{BRIGHT_WHITE}{BOLD}{'RENDERFLOW · CINEMATIC WORKSTATION'.center(width - 2)}{RESET}{CYAN}║{RESET}")
    print(f"{CYAN}║{RESET}{' ' * (width - 2)}{CYAN}║{RESET}")
    print(f"{CYAN}║{RESET}{CYAN}{'Built by AI With Atif'.center(width - 2)}{RESET}{CYAN}║{RESET}")
    print(f"{CYAN}║{RESET}{' ' * (width - 2)}{CYAN}║{RESET}")
    print(f"{CYAN}║{RESET}{WHITE}{'AI Automation • Cinematic Video • Creative Technology'.center(width - 2)}{RESET}{CYAN}║{RESET}")
    print(f"{CYAN}║{RESET}{' ' * (width - 2)}{CYAN}║{RESET}")
    print(f"{CYAN}║{RESET}{DIM}{'Professional 4K Cinematic Video Rendering Studio'.center(width - 2)}{RESET}{CYAN}║{RESET}")
    print(f"{CYAN}║{RESET}{DIM}{'with Hardware-Adaptive Acceleration'.center(width - 2)}{RESET}{CYAN}║{RESET}")
    print(f"{CYAN}║{RESET}{' ' * (width - 2)}{CYAN}║{RESET}")
    print(f"{CYAN}╚{sep_line}╝{RESET}\n")

    print(f"{WHITE}Welcome to {CYAN}{BOLD}RenderFlow{RESET}{WHITE} by {CYAN}AI With Atif{WHITE} —")
    print(f"Professional cinematic video rendering workstation with")
    print(f"hardware-adaptive intelligence and 4K output.{RESET}\n")
    sys.stdout.flush()


def run_checks_and_startup(workspace_dir: Path, port: int = 8000) -> bool:
    """Runs pre-flight checks and displays startup status sequence."""
    divider = "--------------------------------------------------------------"
    print(divider)
    print("                    LOCAL STUDIO LAUNCHER")
    print(divider)
    print()

    # 1. Check Python environment
    py_ok = sys.version_info >= (3, 8)
    if py_ok:
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        print(f"  {GREEN}[OK]{RESET} Checking Python environment... ({py_ver})")
    else:
        print(f"  \033[91m[FAIL]\033[0m Checking Python environment... (Requires Python 3.8+)")
        sys.stdout.flush()
        return False

    # 2. Check Rendering Studio codebase
    server_py = workspace_dir / "web" / "server.py"
    engine_dir = workspace_dir / "engine"
    studio_ok = server_py.exists() and engine_dir.exists()
    if studio_ok:
        print(f"  {GREEN}[OK]{RESET} Checking Rendering Studio...")
    else:
        print(f"  \033[91m[FAIL]\033[0m Checking Rendering Studio core files...")
        sys.stdout.flush()
        return False

    # 3. Check FFmpeg / ffprobe runtime
    ffmpeg_ok = bool(shutil.which("ffmpeg") or shutil.which("ffprobe"))
    if ffmpeg_ok:
        print(f"  {GREEN}[OK]{RESET} Checking required runtime... (FFmpeg detected)")
    else:
        print(f"  \033[93m[WARN]\033[0m Checking required runtime... (FFmpeg not in PATH)")

    # 4. Check core Python dependencies
    try:
        import numpy, cv2, PIL, psutil, fastapi, uvicorn
        print(f"  {GREEN}[OK]{RESET} Checking core dependencies... (All core packages ready)")
    except ImportError as e:
        print(f"  \033[93m[WARN]\033[0m Checking core dependencies... (Missing package: {e.name})")

    # 5. Starting Web Studio
    print(f"  {GREEN}[OK]{RESET} Starting Web Studio...")

    print()
    print(divider)
    print()
    print(f"  {BRIGHT_WHITE}{BOLD}RENDERFLOW WORKSTATION IS STARTING...{RESET}")
    print()
    print(f"  Local URL:")
    print(f"  {CYAN}http://127.0.0.1:{port}{RESET}")
    print()
    sys.stdout.flush()
    return True


def print_success_state(port: int = 8000):
    """Displays the required success state banner once the server is ready."""
    bar = "=============================================================="
    print(f"\n{CYAN}{bar}{RESET}\n")
    print(f"{CYAN}{BOLD}{'AI WITH ATIF'.center(62)}{RESET}\n")
    print(f"{BRIGHT_WHITE}{BOLD}{'RENDERFLOW · CINEMATIC WORKSTATION'.center(62)}{RESET}\n")
    print(f"{CYAN}{'Built by AI With Atif'.center(62)}{RESET}\n")
    print(f"{WHITE}{'AI Automation • Cinematic Video • Creative Technology'.center(62)}{RESET}\n")
    print(f"{CYAN}{bar}{RESET}\n")
    print(f"{GREEN}{BOLD}{'RENDERFLOW WORKSTATION IS RUNNING'.center(62)}{RESET}\n")
    print(f"  Local:")
    print(f"  {CYAN}http://127.0.0.1:{port}{RESET}\n")
    print(f"  {DIM}Press CTRL+C to stop the server.{RESET}\n")
    print(f"{CYAN}{bar}{RESET}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    ws = Path(__file__).resolve().parent.parent
    print_splash()
    run_checks_and_startup(ws)
    time.sleep(0.5)
    print_success_state()
