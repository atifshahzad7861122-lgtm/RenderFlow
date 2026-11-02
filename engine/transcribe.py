#!/usr/bin/env python3
"""
transcribe.py — Real Local Speech Transcription & Word-Level Timestamp Extraction.

Architecture:
  - If transcript.json already has valid text and word timestamps, REUSE THEM directly.
  - If transcript.json has text but no word timestamps, interpolate word timings proportionally.
  - If transcript.json is missing or has empty text:
      Audio -> FFmpeg audio extraction/normalization -> faster-whisper (tiny/base/small)
      -> Word-level timestamps -> CaptionModel
  - Zero mock captions. Zero fake data.
  - Zero mandatory cloud dependencies (works 100% offline).
"""

import os
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    from .caption_model import CaptionModel, CaptionSegment, Word
except ImportError:
    from caption_model import CaptionModel, CaptionSegment, Word

try:
    from .errors import MissingAudioError, MissingSTTModelError, STTFailureError
except ImportError:
    try:
        from engine.errors import MissingAudioError, MissingSTTModelError, STTFailureError
    except ImportError:
        from errors import MissingAudioError, MissingSTTModelError, STTFailureError

logger = logging.getLogger("rendering_studio.transcribe")


def patch_av_metadata_errors():
    """Ensure compatibility between faster-whisper and various PyAV versions."""
    try:
        import av
        _orig_open = av.open
        import functools
        @functools.wraps(_orig_open)
        def _safe_open(*args, **kwargs):
            try:
                return _orig_open(*args, **kwargs)
            except TypeError as te:
                if "metadata_errors" in str(te) and "metadata_errors" in kwargs:
                    kwargs_copy = dict(kwargs)
                    kwargs_copy.pop("metadata_errors", None)
                    return _orig_open(*args, **kwargs_copy)
                raise
        av.open = _safe_open
    except Exception:
        pass


patch_av_metadata_errors()


def prepare_audio_for_whisper(audio_path: Path, temp_dir: Optional[Path] = None) -> Path:
    """
    Extract and normalize narration audio to 16kHz mono 16-bit PCM WAV.
    Whisper models strictly expect 16kHz mono audio. Preprocessing eliminates
    channel mismatches, high bitrates, and strange container formats.
    """
    audio_path = Path(audio_path).resolve()
    if not audio_path.exists():
        raise MissingAudioError(f"Audio file not found: {audio_path}", details={"audio_path": str(audio_path)})

    # Create temporary 16kHz mono WAV file
    if temp_dir:
        temp_dir = Path(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        out_wav = temp_dir / f"whisper_prep_{audio_path.stem}.wav"
    else:
        td = Path(tempfile.gettempdir())
        out_wav = td / f"whisper_prep_{audio_path.stem}.wav"

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(audio_path),
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(out_wav)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return out_wav
    except Exception as e:
        logger.warning(f"Audio preprocessing via ffmpeg failed ({e}), using source audio directly.")
        return audio_path


DEFAULT_WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "tiny")


class STTModelNotFoundError(MissingSTTModelError):
    """Raised when a required local STT model is not found on disk in offline mode."""
    pass


def get_whisper_device_and_compute_type(
    device: Optional[str] = None,
    compute_type: Optional[str] = None
) -> tuple[str, str]:
    """
    Select execution device and compute type.
    Prioritizes CPU with int8 quantization on Intel i5 / target hardware.
    Detects and utilizes CUDA GPU if present and requested.
    """
    resolved_device = device or os.environ.get("WHISPER_DEVICE", "auto")
    if resolved_device == "auto":
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                resolved_device = "cuda"
            else:
                resolved_device = "cpu"
        except Exception:
            resolved_device = "cpu"

    resolved_compute = compute_type or os.environ.get("WHISPER_COMPUTE_TYPE", "auto")
    if resolved_compute == "auto":
        if resolved_device == "cuda":
            resolved_compute = "float16"
        else:
            resolved_compute = "int8"  # int8 CPU optimization for Intel i5

    return resolved_device, resolved_compute


def resolve_local_whisper_model(
    model_name: str = DEFAULT_WHISPER_MODEL,
    allow_download: bool = False
) -> tuple[str, bool]:
    """
    Resolve local Whisper model path without making Hugging Face network requests.
    Returns:
        (resolved_model_path_str, is_local_bool)
    Raises:
        STTModelNotFoundError: If offline and model is not locally cached.
    """
    # 1. Direct path check
    cand_path = Path(model_name)
    if cand_path.exists() and cand_path.is_dir():
        if (cand_path / "model.bin").exists() or (cand_path / "model.safetensors").exists():
            return str(cand_path.resolve()), True

    # 2. Check local workspace models (models/whisper/{model_name})
    root_models = Path(__file__).resolve().parent.parent / "models" / "whisper" / model_name
    if root_models.exists() and (root_models / "model.bin").exists():
        return str(root_models.resolve()), True

    # 3. Check local workspace cache (.cache/whisper/{model_name})
    workspace_cache = Path(__file__).resolve().parent.parent / ".cache" / "whisper" / model_name
    if workspace_cache.exists() and (workspace_cache / "model.bin").exists():
        return str(workspace_cache.resolve()), True

    # 3. Check HuggingFace local cache with local_files_only=True (ZERO network traffic)
    try:
        from faster_whisper.utils import download_model
        local_path = download_model(model_name, local_files_only=True)
        return local_path, True
    except Exception:
        pass

    # 4. If first-run provisioning is explicitly permitted:
    if allow_download:
        logger.info(f"Provisioning Whisper model '{model_name}' to local cache...")
        from faster_whisper.utils import download_model
        downloaded = download_model(model_name, local_files_only=False)
        return downloaded, False

    # 5. Offline and model missing -> Check if an alternate model is locally cached
    cached_alternatives = []
    for alt in ["small", "base", "tiny"]:
        if alt != model_name:
            try:
                from faster_whisper.utils import download_model
                p = download_model(alt, local_files_only=True)
                cached_alternatives.append(alt)
            except Exception:
                pass

    alt_msg = ""
    if cached_alternatives:
        alt_msg = f" Available locally cached models: {cached_alternatives}."

    raise STTModelNotFoundError(
        f"Whisper model '{model_name}' is not found in the local offline cache.{alt_msg}\n"
        f"To provision for offline operation, run:\n"
        f"    python engine/transcribe.py --provision-model {model_name}"
    )


def provision_whisper_model(model_name: str = "small") -> str:
    """Download and provision a Whisper model for 100% offline local use."""
    logger.info(f"Provisioning Whisper model '{model_name}' for local offline use...")
    from faster_whisper.utils import download_model
    path = download_model(model_name, local_files_only=False)
    logger.info(f"Whisper model '{model_name}' successfully provisioned at: {path}")
    return path


def list_local_whisper_models() -> List[Dict[str, Any]]:
    """List all locally available Whisper models without making network requests."""
    models = ["tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en", "large-v3"]
    results = []
    from faster_whisper.utils import download_model
    for m in models:
        try:
            p = download_model(m, local_files_only=True)
            results.append({"model": m, "status": "AVAILABLE", "path": p, "offline": True})
        except Exception:
            results.append({"model": m, "status": "NOT_CACHED", "path": None, "offline": False})
    return results


def ensure_vad_model_available() -> Optional[Path]:
    """
    Ensure the Silero VAD model (silero_vad_v6.onnx) is present in faster_whisper's
    expected assets directory. If missing in the frozen executable or dev environment,
    locates it from bundled fallback paths and copies it into place.
    """
    try:
        from faster_whisper.utils import get_assets_path
        assets_dir = Path(get_assets_path())
        target_model = assets_dir / "silero_vad_v6.onnx"
        if target_model.exists() and target_model.stat().st_size > 0:
            return target_model

        # Search candidate locations
        app_root = Path(__file__).resolve().parent.parent
        exe_dir = Path(sys.executable).parent
        candidates = [
            app_root / "models" / "vad" / "silero_vad_v6.onnx",
            app_root / "dist" / "RenderingStudio" / "models" / "vad" / "silero_vad_v6.onnx",
            app_root / "dist" / "RenderingStudio_v2.6.0_candidate_v3" / "models" / "vad" / "silero_vad_v6.onnx",
            app_root / "dist" / "RenderingStudio_v2.6.0_candidate_v2" / "models" / "vad" / "silero_vad_v6.onnx",
            app_root / "_internal" / "faster_whisper" / "assets" / "silero_vad_v6.onnx",
            exe_dir / "_internal" / "faster_whisper" / "assets" / "silero_vad_v6.onnx",
            exe_dir / "models" / "vad" / "silero_vad_v6.onnx",
        ]
        if hasattr(sys, "_MEIPASS"):
            candidates.insert(0, Path(sys._MEIPASS) / "faster_whisper" / "assets" / "silero_vad_v6.onnx")
            candidates.insert(1, Path(sys._MEIPASS) / "models" / "vad" / "silero_vad_v6.onnx")

        for cand in candidates:
            if cand.exists() and cand.stat().st_size > 0:
                assets_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cand, target_model)
                logger.info(f"[FASTER-WHISPER] Successfully staged Silero VAD model to {target_model} from {cand}")
                return target_model

        logger.warning(
            f"[FASTER-WHISPER] Silero VAD model 'silero_vad_v6.onnx' not found in assets path ({assets_dir}) "
            f"or candidate search paths. Direct transcription fallback will be used if VAD fails."
        )
        return None
    except Exception as e:
        logger.warning(f"[FASTER-WHISPER] Note during VAD model resolution: {e}")
        return None


def transcribe_or_load_captions(
    audio_path: Path,
    transcript_path: Optional[Path] = None,
    language: str = "auto",
    model_name: str = DEFAULT_WHISPER_MODEL,
    force_retranscribe: bool = False,
    device: Optional[str] = None,
    compute_type: Optional[str] = None,
    allow_download: bool = False
) -> CaptionModel:
    """
    Get normalized CaptionModel with real word timestamps following the hierarchy:
      1. Re-use existing transcript.json if it contains populated text and words.
      2. If transcript.json has text but missing words, interpolate word timestamps.
      3. If transcript.json has empty text or does not exist, transcribe via local faster-whisper.
    """
    audio_path = Path(audio_path).resolve()

    # 1. Inspect existing transcript
    if transcript_path and Path(transcript_path).exists() and not force_retranscribe:
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            raw_segs = data.get("segments", []) if isinstance(data, dict) else data
            from .stt_provider import is_valid_speech_transcript
            if is_valid_speech_transcript(raw_segs):
                has_words = any(bool(s.get("words")) for s in raw_segs if isinstance(s, dict))
                logger.info(f"Reusing existing valid speech transcript from {transcript_path} (has_words={has_words})")
                model = CaptionModel.from_dict(data)
                model.ensure_word_timings()
                return model
            else:
                logger.info(f"Existing transcript at {transcript_path} contains placeholder scene/beat markers without real speech text. Proceeding to real speech transcription.")
        except Exception as e:
            logger.warning(f"Failed to read existing transcript {transcript_path}: {e}")

    # 2. Local Speech-to-Text Transcription
    logger.info(f"Running authoritative local faster-whisper transcription ({model_name}) on {audio_path}...")
    
    # Preprocess audio to 16kHz mono WAV for optimal faster-whisper performance
    prep_audio = prepare_audio_for_whisper(audio_path)

    # Attempt faster-whisper first (authoritative local path)
    fw_error = None
    try:
        from faster_whisper import WhisperModel
        
        # Resolve model path locally without Hugging Face network call
        resolved_model_path, is_local = resolve_local_whisper_model(model_name, allow_download=allow_download)
        device, compute_type = get_whisper_device_and_compute_type(device, compute_type)
        logger.info(f"[FASTER-WHISPER] Loading model from '{resolved_model_path}' (device={device}, compute_type={compute_type}, offline={is_local})...")
        model = WhisperModel(resolved_model_path, device=device, compute_type=compute_type)

        # Verify / stage Silero VAD model in faster_whisper assets path
        vad_model_path = ensure_vad_model_available()

        transcribe_kwargs = {
            "word_timestamps": True,
            "vad_filter": True,
            "vad_parameters": dict(min_silence_duration_ms=300),
            "beam_size": 5
        }
        if language and language != "auto":
            transcribe_kwargs["language"] = language

        logger.info(f"[FASTER-WHISPER] Transcribing {prep_audio.name} with word-level timestamps...")
        try:
            segments_gen, info = model.transcribe(str(prep_audio), **transcribe_kwargs)
            segments_list = list(segments_gen)
            if not segments_list and transcribe_kwargs.get("vad_filter"):
                logger.info("[FASTER-WHISPER] VAD filter returned 0 segments; retrying with vad_filter=False...")
                retry_kwargs = dict(transcribe_kwargs)
                retry_kwargs["vad_filter"] = False
                retry_kwargs.pop("vad_parameters", None)
                segments_gen, info = model.transcribe(str(prep_audio), **retry_kwargs)
                segments_list = list(segments_gen)
        except Exception as vad_err:
            if "silero_vad" in str(vad_err).lower() or "onnx" in str(vad_err).lower():
                logger.warning(f"[FASTER-WHISPER] VAD filter failed ({vad_err}), falling back to direct transcribe without vad_filter...")
                transcribe_kwargs["vad_filter"] = False
                transcribe_kwargs.pop("vad_parameters", None)
                segments_gen, info = model.transcribe(str(prep_audio), **transcribe_kwargs)
                segments_list = list(segments_gen)
            else:
                raise

        detected_lang = info.language or (language if language != "auto" else "en")

        segments: List[CaptionSegment] = []
        for idx, seg in enumerate(segments_list):
            words: List[Word] = []
            if seg.words:
                for w in seg.words:
                    w_text = (w.word or "").strip()
                    if not w_text:
                        continue
                    words.append(Word(
                        text=w_text,
                        start=round(float(w.start), 3),
                        end=round(float(w.end), 3),
                        confidence=round(float(w.probability), 3)
                    ))

            seg_text = (seg.text or "").strip()
            if not seg_text and words:
                seg_text = " ".join(w.text for w in words)
            if not seg_text:
                continue

            segments.append(CaptionSegment(
                id=idx + 1,
                start=round(float(seg.start), 3),
                end=round(float(seg.end), 3),
                text=seg_text,
                words=words
            ))

        if segments:
            model_res = CaptionModel(segments=segments, language=detected_lang)
            model_res.ensure_word_timings()

            # Cache back to transcript_path if provided
            if transcript_path:
                try:
                    tp = Path(transcript_path)
                    tp.parent.mkdir(parents=True, exist_ok=True)
                    with open(tp, "w", encoding="utf-8") as f:
                        f.write(model_res.to_json())
                    logger.info(f"Saved normalized transcript with word timestamps to {tp}")
                except Exception as e:
                    logger.warning(f"Could not cache transcript to {transcript_path}: {e}")

            # Clean up temp audio if created
            if prep_audio != audio_path and prep_audio.exists():
                try:
                    prep_audio.unlink()
                except Exception:
                    pass

            return model_res
        else:
            logger.warning("[FASTER-WHISPER] No speech segments detected by VAD.")

    except Exception as e:
        logger.warning(f"faster-whisper transcription error: {e}. Trying openai-whisper fallback...")
        fw_error = e

    # Secondary fallback to openai-whisper if faster-whisper fails
    try:
        import whisper
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            logger.info(f"[WHISPER] Loading fallback model '{model_name}'...")
            wh_model = whisper.load_model(model_name)
            whisper_kwargs = {
                "word_timestamps": True,
                "verbose": False
            }
            if language and language != "auto":
                whisper_kwargs["language"] = language

            result = wh_model.transcribe(str(prep_audio), **whisper_kwargs)

        detected_lang = result.get("language", language or "en")
        segments = []
        for idx, seg in enumerate(result.get("segments", [])):
            raw_words = seg.get("words", [])
            words = []
            for w in raw_words:
                w_text = w.get("word", "").strip()
                if not w_text:
                    continue
                words.append(Word(
                    text=w_text,
                    start=round(float(w.get("start", 0.0)), 3),
                    end=round(float(w.get("end", 0.0)), 3),
                    confidence=round(float(w.get("probability", 1.0)), 3)
                ))

            seg_text = seg.get("text", "").strip()
            if not seg_text and words:
                seg_text = " ".join(w.text for w in words)
            if not seg_text:
                continue

            segments.append(CaptionSegment(
                id=idx + 1,
                start=round(float(seg.get("start", 0.0)), 3),
                end=round(float(seg.get("end", 0.0)), 3),
                text=seg_text,
                words=words
            ))

        if segments:
            model_res = CaptionModel(segments=segments, language=detected_lang)
            model_res.ensure_word_timings()

            if transcript_path:
                try:
                    tp = Path(transcript_path)
                    tp.parent.mkdir(parents=True, exist_ok=True)
                    with open(tp, "w", encoding="utf-8") as f:
                        f.write(model_res.to_json())
                except Exception:
                    pass

            if prep_audio != audio_path and prep_audio.exists():
                try:
                    prep_audio.unlink()
                except Exception:
                    pass

            return model_res

    except Exception as e:
        logger.error(f"Whisper fallback failed: {e}")

    # Clean up temp audio if exists
    if prep_audio != audio_path and prep_audio.exists():
        try:
            prep_audio.unlink()
        except Exception:
            pass

    raise STTFailureError(
        f"Real local transcription failed. faster-whisper error: {fw_error}. "
        "No speech detected or local model could not process audio. Ensure audio is non-silent.",
        details={"audio_path": str(audio_path), "error": str(fw_error)}
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rendering Studio Local Whisper STT Engine")
    parser.add_argument("--audio", help="Input audio file path to transcribe")
    parser.add_argument("--out", help="Output transcript.json path")
    parser.add_argument("--model", default="small", help="Whisper model name (default: small)")
    parser.add_argument("--language", default="auto", help="Spoken language or 'auto'")
    parser.add_argument("--provision-model", help="Download and provision model for offline use (e.g. small, base, tiny)")
    parser.add_argument("--list-models", action="store_true", help="List local cached models")
    parser.add_argument("--device", help="Device (cpu, cuda, or auto)")
    parser.add_argument("--compute-type", help="Compute type (int8, float16, or auto)")

    args = parser.parse_args()

    if args.list_models:
        print("\n--- Local Whisper Models Status ---")
        for m in list_local_whisper_models():
            status = m['status']
            path = m['path'] or 'None'
            print(f"  [{status}] {m['model']:<12} -> {path}")
        print()
    elif args.provision_model:
        print(f"Provisioning Whisper model '{args.provision_model}' for local offline use...")
        path = provision_whisper_model(args.provision_model)
        print(f"SUCCESS: Model provisioned at {path}")
    elif args.audio:
        print(f"Transcribing '{args.audio}' with local model '{args.model}'...")
        captions = transcribe_or_load_captions(
            audio_path=Path(args.audio),
            transcript_path=Path(args.out) if args.out else None,
            language=args.language,
            model_name=args.model,
            force_retranscribe=True,
            device=args.device,
            compute_type=args.compute_type
        )
        print(f"SUCCESS: Transcribed {len(captions.segments)} segments.")
        if args.out:
            print(f"Saved transcript to {args.out}")
        else:
            print(captions.to_json())
    else:
        parser.print_help()
