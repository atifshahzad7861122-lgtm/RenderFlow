#!/usr/bin/env python3
"""
Rendering Studio Engine v2 — Full Pipeline Runner.

Defaults to the ultra-fast FFmpeg-native composition pipeline:
  Source Images + Narration Audio + Exact Timeline + Cinematic Transitions + SFX
  -> 1080p 30fps H.264 / AAC Final Output in <= 8 minutes.

Supports --legacy-pipeline for 3-step separate base+overlay rendering.
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(cmd, cwd=None):
    print('+', ' '.join(str(c) for c in cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        sys.exit(f'FAILED rc={r.returncode}: {cmd[0]}')


def main():
    ap = argparse.ArgumentParser(description="Rendering Studio Engine v2 Pipeline")
    ap.add_argument('--images', required=True)
    ap.add_argument('--segments', required=True)
    ap.add_argument('--plan', required=True)
    ap.add_argument('--audio', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workdir', default=None)
    ap.add_argument('--pack-dir', default=str(HERE / '..' / 'transition_pack'))
    ap.add_argument('--overlay-dur', type=float, default=None,
                    help='Sab transitions ki fixed duration (default: context intelligence 0.15-0.60s)')
    ap.add_argument('--dur-scale', type=float, default=1.0,
                    help='Transitions duration scale multiplier')
    ap.add_argument('--preset', default='veryfast',
                    help='x264 encoding preset (ultrafast, superfast, veryfast)')
    ap.add_argument('--profile', default='balanced', choices=['quality', 'balanced', 'fast'],
                    help='Pipeline performance profile (balanced default)')
    ap.add_argument('--skip-verify', action='store_true')
    ap.add_argument('--chunk-size', type=int, default=35,
                    help='Scenes per chunk for long videos')
    ap.add_argument('--force-chunks', action='store_true',
                    help='Force streaming chunked architecture')
    ap.add_argument('--force-single-pass', action='store_true',
                    help='Force single-pass architecture')
    ap.add_argument('--no-transitions', dest='enable_transitions', action='store_false', default=True,
                    help='Disable transitions (hard cuts)')
    ap.add_argument('--legacy-pipeline', action='store_true',
                    help='Use legacy 3-step separate base render + overlay passes')
    ap.add_argument('--enable-captions', action='store_true',
                    help='Enable audio-synchronized captions')
    ap.add_argument('--caption-style', default='classic',
                    help='Caption style preset')
    ap.add_argument('--caption-length', default='medium', choices=['short', 'medium', 'long'],
                    help='Caption length preset')
    ap.add_argument('--caption-lang', default='auto',
                    help='Spoken language for captions')
    ap.add_argument('--caption-overrides', type=str, default=None,
                    help='JSON string with custom style overrides')
    ap.add_argument('--separate-subtitles', action='store_true', default=True,
                    help='Export sidecar .srt, .ass, and captions.json')
    ap.add_argument('--platform-preset', default=None,
                    help='Platform aspect ratio and safe area preset')
    ap.add_argument('--stt-provider', default='auto',
                    help='STT provider (auto, deepgram, local_whisper, existing_transcript)')
    ap.add_argument('--ai-mode', default='raw', choices=['raw', 'clean', 'viral'],
                    help='AI caption intelligence mode')
    ap.add_argument('--creative-rewrite', action='store_true',
                    help='Allow punchier social rewrite while preserving meaning')
    ap.add_argument('--llm-provider', default='auto',
                    help='LLM provider (auto, groq, gemini, openrouter, claude, openai, kimi, deepseek, local)')
    ap.add_argument('--llm-model', default=None,
                    help='Specific LLM model identifier')
    
    # Resolution and hardware profile arguments (Module 16)
    ap.add_argument('--resolution', default='1080p', choices=['1080p', '1440p', '4k'],
                    help='Target video resolution preset (1080p, 1440p, 4k)')
    ap.add_argument('--encoder', default='auto',
                    help='Video encoder (auto, libx264, h264_nvenc, h264_qsv, h264_amf, h264_mf)')
    ap.add_argument('--perf-mode', default='auto', choices=['auto', 'eco', 'balanced', 'performance', 'max_quality'],
                    help='Hardware performance mode')
    ap.add_argument('--quality-preset', default='standard', choices=['standard', 'high', 'maximum'],
                    help='Encoding quality profile')
    ap.add_argument('--visual-style', default='cinematic_warm',
                    help='Visual style grading preset')
    ap.add_argument('--transition-id', default=None,
                    help='Global transition id override')
    args = ap.parse_args()

    out = Path(args.out).resolve()
    work = Path(args.workdir).resolve() if args.workdir else out.parent / 'work'
    work.mkdir(parents=True, exist_ok=True)
    pack_dir = Path(args.pack_dir).resolve()

    if not args.legacy_pipeline:
        # --- Ultra-Fast Native FFmpeg Pipeline ---
        fast_script = HERE / 'fast_pipeline.py'
        cmd = [
            sys.executable, str(fast_script),
            '--images', str(Path(args.images).resolve()),
            '--segments', str(Path(args.segments).resolve()),
            '--plan', str(Path(args.plan).resolve()),
            '--audio', str(Path(args.audio).resolve()),
            '--out', str(out),
            '--workdir', str(work),
            '--pack-dir', str(pack_dir),
            '--preset', args.preset,
            '--profile', args.profile,
            '--dur-scale', str(args.dur_scale),
            '--chunk-size', str(args.chunk_size),
            '--resolution', args.resolution,
            '--encoder', args.encoder,
            '--perf-mode', args.perf_mode,
            '--quality-preset', args.quality_preset,
            '--visual-style', args.visual_style
        ]
        if args.transition_id:
            cmd += ['--transition-id', args.transition_id]
        if args.force_chunks:
            cmd += ['--force-chunks']
        if args.force_single_pass:
            cmd += ['--force-single-pass']
        if not args.enable_transitions:
            cmd += ['--no-transitions']
        if args.overlay_dur is not None:
            cmd += ['--overlay-dur', str(args.overlay_dur)]
        if args.skip_verify:
            cmd += ['--skip-verify']
        if args.enable_captions:
            cmd += ['--enable-captions']
            cmd += ['--caption-style', args.caption_style]
            cmd += ['--caption-length', args.caption_length]
            cmd += ['--caption-lang', args.caption_lang]
            if args.caption_overrides:
                cmd += ['--caption-overrides', args.caption_overrides]
            if args.separate_subtitles:
                cmd += ['--separate-subtitles']
            if args.platform_preset:
                cmd += ['--platform-preset', args.platform_preset]
            if args.stt_provider:
                cmd += ['--stt-provider', args.stt_provider]
            if args.ai_mode:
                cmd += ['--ai-mode', args.ai_mode]
            if args.creative_rewrite:
                cmd += ['--creative-rewrite']
            if args.llm_provider:
                cmd += ['--llm-provider', args.llm_provider]
            if args.llm_model:
                cmd += ['--llm-model', args.llm_model]

        run(cmd, cwd=str(HERE.parent))
        print('PIPELINE OK:', out, flush=True)
        return

    # --- Legacy Fallback Pipeline ---
    base = work / 'base.mp4'
    print('=== STEP 1/3: sync-timeline base render ===', flush=True)
    run([sys.executable, str(HERE / 'render_base.py'),
         '--images', args.images, '--segments', args.segments,
         '--plan', args.plan, '--audio', args.audio,
         '--out', str(base), '--workdir', str(work)])

    print('=== STEP 2/3: automatic transitions + SFX ===', flush=True)
    tcmd = [sys.executable, str(pack_dir / 'auto_transition.py'),
            '--scenes', str(work / 'scene_labels.json'),
            '--pack', str(pack_dir / 'pack.json'),
            '--base', str(base), '--out', str(out),
            '--dur-scale', str(args.dur_scale),
            '--preset', args.preset]
    if args.overlay_dur is not None:
        tcmd += ['--overlay-dur', str(args.overlay_dur)]
    run(tcmd, cwd=str(pack_dir))

    if not args.skip_verify:
        print('=== STEP 3/3: verification ===', flush=True)
        run([sys.executable, str(HERE / 'verify_output.py'),
             '--video', str(out),
             '--scenes', str(work / 'scene_labels.json'),
             '--sheet', str(work / 'contact_sheet.png')])
    print('LEGACY PIPELINE OK:', out, flush=True)


if __name__ == '__main__':
    main()
