#!/usr/bin/env python3
"""
stt_provider.py — Speech-to-Text Provider Architecture for Rendering Studio.

Providers:
  - DeepgramSTTProvider: Deepgram Nova-3 HTTP API with word-level timestamps,
    confidence, punctuation, smart formatting, utterances, diarization.
  - LocalWhisperSTTProvider: Local Whisper (tiny/base/small) fallback.
  - ExistingTranscriptSTTProvider: Direct reuse of existing transcript.json.
  
Features:
  - STT_PROVIDER_REGISTRY with automatic priority fallback:
    Deepgram -> Local Whisper -> Existing Transcript.
  - Strict normalization into CaptionModel, CaptionSegment, and Word.
  - Audio remains master timeline; zero mandatory cloud dependency.
  - Connection testing and error diagnosis without exposing secret keys.
"""

import os
import re
import json
import time
import urllib.request
import urllib.error
import urllib.parse
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from .caption_model import CaptionModel, CaptionSegment, Word

logger = logging.getLogger("rendering_studio.stt")


class STTProvider(ABC):
    """Abstract base class for speech-to-text providers."""
    
    name: str = "base"
    
    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        language: str = "auto",
        **kwargs
    ) -> CaptionModel:
        """Transcribe audio into a normalized CaptionModel."""
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Verify API connectivity and model availability."""
        pass


class DeepgramSTTProvider(STTProvider):
    """
    Deepgram Speech-to-Text Provider (Nova-3 primary).
    Direct HTTP REST API integration without requiring heavy third-party SDKs.
    """
    
    name: str = "deepgram"
    API_URL = "https://api.deepgram.com/v1/listen"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "nova-3",
        smart_format: bool = True,
        punctuate: bool = True,
        utterances: bool = True,
        diarize: bool = False
    ):
        self.api_key = api_key or os.environ.get("DEEPGRAM_API_KEY", "").strip()
        self.model = model or os.environ.get("DEEPGRAM_MODEL", "nova-3")
        self.smart_format = smart_format
        self.punctuate = punctuate
        self.utterances = utterances
        self.diarize = diarize

    def test_connection(self) -> Dict[str, Any]:
        """Test Deepgram API key and network connectivity."""
        if not self.api_key:
            return {
                "provider": self.name,
                "status": "NOT_CONFIGURED",
                "message": "DEEPGRAM_API_KEY is not set. Using local/fallback STT."
            }
            
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                "https://api.deepgram.com/v1/projects",
                headers={
                    "Authorization": f"Token {self.api_key}",
                    "User-Agent": "RenderingStudio/2.1"
                }
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
                data = json.loads(resp.read().decode("utf-8"))
                projects = data.get("projects", [])
                return {
                    "provider": self.name,
                    "status": "CONNECTED",
                    "latency_ms": elapsed_ms,
                    "model": self.model,
                    "project_count": len(projects)
                }
        except urllib.error.HTTPError as e:
            return {
                "provider": self.name,
                "status": "ERROR",
                "http_code": e.code,
                "message": f"Deepgram auth/HTTP error: {e.reason}"
            }
        except Exception as e:
            return {
                "provider": self.name,
                "status": "UNREACHABLE",
                "message": str(e)
            }

    def transcribe(
        self,
        audio_path: Path,
        language: str = "auto",
        **kwargs
    ) -> CaptionModel:
        """
        Send raw audio to Deepgram Nova-3 and normalize words & utterances.
        """
        if not self.api_key:
            raise RuntimeError("Deepgram API key missing. Configure DEEPGRAM_API_KEY or use fallback.")

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Query parameters
        params = {
            "model": kwargs.get("model", self.model),
            "smart_format": "true" if self.smart_format else "false",
            "punctuate": "true" if self.punctuate else "false",
            "utterances": "true" if self.utterances else "false",
            "diarize": "true" if self.diarize else "false",
        }
        if language and language != "auto":
            params["language"] = language
        else:
            params["detect_language"] = "true"

        query_str = urllib.parse.urlencode(params)
        url = f"{self.API_URL}?{query_str}"

        # Detect audio mimetype
        suffix = audio_path.suffix.lower()
        content_type = "audio/wav"
        if suffix in [".mp3", ".mpeg"]:
            content_type = "audio/mp3"
        elif suffix in [".m4a", ".aac"]:
            content_type = "audio/m4a"
        elif suffix in [".ogg", ".opus"]:
            content_type = "audio/ogg"
        elif suffix == ".flac":
            content_type = "audio/flac"

        logger.info(f"[DEEPGRAM] Uploading {audio_path.name} ({content_type}) to {url}...")
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        req = urllib.request.Request(
            url,
            data=audio_bytes,
            headers={
                "Authorization": f"Token {self.api_key}",
                "Content-Type": content_type,
                "User-Agent": "RenderingStudio/2.1"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"[DEEPGRAM] Request failed: {e}")
            raise RuntimeError(f"Deepgram transcription error: {e}")

        return self.normalize_deepgram_response(resp_data, requested_language=language)

    @classmethod
    def normalize_deepgram_response(cls, data: Dict[str, Any], requested_language: str = "auto") -> CaptionModel:
        """
        Normalize Deepgram JSON output into Rendering Studio CaptionModel.
        Uses utterances for natural sentence/clause segments while preserving
        exact word-level timestamps, confidence scores, and punctuation.
        """
        results = data.get("results", {})
        channels = results.get("channels", [])
        if not channels:
            return CaptionModel(segments=[], language=requested_language)

        channel_0 = channels[0]
        detected_lang = channel_0.get("detected_language") or requested_language
        alternatives = channel_0.get("alternatives", [])
        if not alternatives:
            return CaptionModel(segments=[], language=detected_lang)

        alt_0 = alternatives[0]
        raw_words = alt_0.get("words", [])
        raw_utterances = results.get("utterances", [])

        # Build list of normalized Word objects
        normalized_words: List[Word] = []
        for rw in raw_words:
            w_text = rw.get("punctuated_word") or rw.get("word") or ""
            w_text = w_text.strip()
            if not w_text:
                continue
            normalized_words.append(Word(
                text=w_text,
                start=round(float(rw.get("start", 0.0)), 3),
                end=round(float(rw.get("end", 0.0)), 3),
                confidence=round(float(rw.get("confidence", 1.0)), 3)
            ))

        segments: List[CaptionSegment] = []

        # Strategy A: Use Deepgram Utterances if available (sentence/phrase boundaries)
        if raw_utterances:
            for u_idx, u in enumerate(raw_utterances):
                u_start = round(float(u.get("start", 0.0)), 3)
                u_end = round(float(u.get("end", 0.0)), 3)
                u_transcript = (u.get("transcript") or "").strip()
                
                # Match words falling within this utterance window
                u_words = [
                    w for w in normalized_words
                    if (w.start >= u_start - 0.05 and w.end <= u_end + 0.1)
                ]
                # Fallback text if transcript empty
                if not u_transcript and u_words:
                    u_transcript = " ".join(w.text for w in u_words)

                if u_transcript or u_words:
                    segments.append(CaptionSegment(
                        id=u_idx + 1,
                        start=u_start,
                        end=max(u_start + 0.05, u_end),
                        text=u_transcript,
                        words=u_words
                    ))
        
        # Strategy B: If no utterances, group words into segments by punctuation or duration
        if not segments and normalized_words:
            cur_words: List[Word] = []
            seg_id = 1
            for w in normalized_words:
                cur_words.append(w)
                # Split at punctuation or maximum 8 words
                has_punct = w.text.endswith((".", "!", "?", ";", "…"))
                if has_punct or len(cur_words) >= 8:
                    s_start = cur_words[0].start
                    s_end = cur_words[-1].end
                    s_text = " ".join(cw.text for cw in cur_words)
                    segments.append(CaptionSegment(
                        id=seg_id,
                        start=s_start,
                        end=s_end,
                        text=s_text,
                        words=list(cur_words)
                    ))
                    seg_id += 1
                    cur_words = []
            if cur_words:
                segments.append(CaptionSegment(
                    id=seg_id,
                    start=cur_words[0].start,
                    end=cur_words[-1].end,
                    text=" ".join(cw.text for cw in cur_words),
                    words=list(cur_words)
                ))

        model = CaptionModel(segments=segments, language=detected_lang)
        model.ensure_word_timings()
        return model


class LocalWhisperSTTProvider(STTProvider):
    """Local offline Whisper STT provider (zero API costs, 100% offline)."""
    
    name: str = "local_whisper"
    
    def __init__(self, model_name: str = "small"):
        self.model_name = model_name or os.environ.get("WHISPER_MODEL", "small")

    def test_connection(self) -> Dict[str, Any]:
        """Test local faster-whisper / Whisper availability, local cache, and device info."""
        try:
            import faster_whisper
            from .transcribe import resolve_local_whisper_model, get_whisper_device_and_compute_type
            
            device, compute_type = get_whisper_device_and_compute_type()
            try:
                local_path, is_local = resolve_local_whisper_model(self.model_name, allow_download=False)
                return {
                    "provider": self.name,
                    "status": "AVAILABLE",
                    "engine": "faster-whisper",
                    "version": getattr(faster_whisper, "__version__", "1.2.1"),
                    "default_model": self.model_name,
                    "model_path": local_path,
                    "device": device,
                    "compute_type": compute_type,
                    "offline": True,
                    "cached": True
                }
            except Exception as e:
                return {
                    "provider": self.name,
                    "status": "NOT_CACHED",
                    "engine": "faster-whisper",
                    "version": getattr(faster_whisper, "__version__", "1.2.1"),
                    "default_model": self.model_name,
                    "device": device,
                    "compute_type": compute_type,
                    "offline": True,
                    "cached": False,
                    "message": str(e)
                }
        except ImportError:
            try:
                import whisper
                return {
                    "provider": self.name,
                    "status": "AVAILABLE",
                    "engine": "openai-whisper",
                    "default_model": self.model_name,
                    "offline": True
                }
            except ImportError:
                return {
                    "provider": self.name,
                    "status": "NOT_INSTALLED",
                    "message": "Neither faster-whisper nor openai-whisper is installed"
                }

    def transcribe(
        self,
        audio_path: Path,
        language: str = "auto",
        **kwargs
    ) -> CaptionModel:
        """Transcribe audio locally via Whisper with word timestamps."""
        from .transcribe import transcribe_or_load_captions
        model_name = kwargs.get("model_name", self.model_name)
        device = kwargs.get("device")
        compute_type = kwargs.get("compute_type")
        return transcribe_or_load_captions(
            audio_path=audio_path,
            transcript_path=None,
            language=language,
            model_name=model_name,
            force_retranscribe=True,
            device=device,
            compute_type=compute_type
        )


class ExistingTranscriptSTTProvider(STTProvider):
    """Directly loads and verifies existing pre-generated transcript.json."""
    
    name: str = "existing_transcript"

    def test_connection(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "status": "AVAILABLE",
            "offline": True
        }

    def transcribe(
        self,
        audio_path: Path,
        language: str = "auto",
        **kwargs
    ) -> CaptionModel:
        transcript_path = kwargs.get("transcript_path")
        if not transcript_path or not Path(transcript_path).exists():
            raise FileNotFoundError(f"Transcript path not found: {transcript_path}")

        from .transcribe import transcribe_or_load_captions
        return transcribe_or_load_captions(
            audio_path=audio_path,
            transcript_path=Path(transcript_path),
            language=language,
            force_retranscribe=False
        )


# --- STT Registry & Fallback Dispatcher ---

STT_PROVIDER_REGISTRY: Dict[str, STTProvider] = {
    "deepgram": DeepgramSTTProvider(),
    "local_whisper": LocalWhisperSTTProvider(),
    "existing_transcript": ExistingTranscriptSTTProvider(),
}


def get_stt_provider(name: str = "deepgram") -> STTProvider:
    """Retrieve STT provider by name."""
    name_clean = (name or "deepgram").strip().lower()
    return STT_PROVIDER_REGISTRY.get(name_clean, STT_PROVIDER_REGISTRY["deepgram"])


def is_valid_speech_transcript(raw_segments: Any) -> bool:
    """
    Check if a list of segment dictionaries represents a genuine spoken speech transcript,
    rather than placeholder scene/beat markers (e.g. 'Scene 1', 'Scene 2', 'Narration', etc.)
    or empty silence cuts.
    """
    if not raw_segments or not isinstance(raw_segments, list):
        return False

    placeholder_pattern = re.compile(
        r'^(Scene\s*\d*|Narration\s*\d*|Segment\s*\d*|Beat\s*\d*|Track\s*\d*|Clip\s*\d*|\d+[\.\:]?)$',
        re.IGNORECASE
    )

    real_words = []
    total_valid_segs = 0

    for s in raw_segments:
        if not isinstance(s, dict):
            continue
        txt = str(s.get("text", "")).strip()
        if not txt:
            words_arr = s.get("words", [])
            if isinstance(words_arr, list) and words_arr:
                txt = " ".join(str(w.get("text" if isinstance(w, dict) else "word", "")).strip() for w in words_arr)

        if not txt:
            continue

        total_valid_segs += 1
        if placeholder_pattern.match(txt):
            continue

        tokens = [t.lower() for t in re.findall(r'\b[a-zA-Z\u00C0-\u024F\u0400-\u04FF\u0600-\u06FF\u4E00-\u9FFF]{2,}\b', txt)]
        tokens = [t for t in tokens if t not in {"scene", "narration", "segment", "beat", "track", "clip"}]
        real_words.extend(tokens)

    if total_valid_segs == 0:
        return False

    return len(real_words) >= 3


def transcribe_with_fallback(
    audio_path: Path,
    transcript_path: Optional[Path] = None,
    preferred_provider: str = "auto",
    language: str = "auto",
    deepgram_api_key: Optional[str] = None,
    deepgram_model: str = "nova-3",
    whisper_model: str = os.environ.get("WHISPER_MODEL", "tiny"),
    force_retranscribe: bool = False
) -> Tuple[CaptionModel, str]:
    """
    Authoritative STT transcription with automatic graceful fallback:
      1. If existing transcript.json has valid speech words and force_retranscribe is False -> reuse it.
      2. If preferred_provider is 'deepgram' (or 'auto' with DEEPGRAM_API_KEY present) -> Deepgram Nova-3.
      3. Fallback to Local Whisper if Deepgram fails or API key missing.
      4. Fallback to existing transcript if Whisper fails (only if it has valid words).
    
    Returns (CaptionModel, provider_used).
    """
    # Check if pre-existing transcript should be reused
    if transcript_path and Path(transcript_path).exists() and not force_retranscribe:
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            raw_segs = d.get("segments", []) if isinstance(d, dict) else d
            if is_valid_speech_transcript(raw_segs):
                logger.info(f"[STT] Reusing existing valid speech transcript from {transcript_path}")
                provider = ExistingTranscriptSTTProvider()
                model = provider.transcribe(audio_path, language=language, transcript_path=transcript_path)
                return model, "existing_transcript"
            else:
                logger.info(f"[STT] transcript.json at {transcript_path} contains placeholder scene/beat markers without real speech text. Running real STT.")
        except Exception as e:
            logger.warning(f"[STT] Existing transcript read failed: {e}")

    # Determine STT candidate order
    candidates: List[Tuple[str, STTProvider, Dict[str, Any]]] = []
    
    # 1. Deepgram candidate
    dg_key = deepgram_api_key or os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if preferred_provider == "deepgram" or (preferred_provider == "auto" and dg_key):
        candidates.append((
            "deepgram",
            DeepgramSTTProvider(api_key=dg_key, model=deepgram_model),
            {"model": deepgram_model}
        ))

    # 2. Local Whisper candidate
    candidates.append((
        "local_whisper",
        LocalWhisperSTTProvider(model_name=whisper_model),
        {"model_name": whisper_model}
    ))

    # 3. Existing transcript candidate (as last resort, only if valid speech words present)
    if transcript_path and Path(transcript_path).exists():
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            raw_segs = d.get("segments", []) if isinstance(d, dict) else d
            if is_valid_speech_transcript(raw_segs):
                candidates.append((
                    "existing_transcript",
                    ExistingTranscriptSTTProvider(),
                    {"transcript_path": transcript_path}
                ))
        except Exception:
            pass

    # Execute candidates with fallback
    last_err = None
    for prov_name, provider, prov_kwargs in candidates:
        try:
            logger.info(f"[STT] Attempting transcription via provider '{prov_name}'...")
            t0 = time.perf_counter()
            model = provider.transcribe(audio_path, language=language, **prov_kwargs)
            elapsed = time.perf_counter() - t0
            logger.info(f"[STT] Provider '{prov_name}' succeeded in {elapsed:.2f}s ({len(model.segments)} segments)")

            # Cache back to transcript_path if newly transcribed
            if transcript_path and prov_name != "existing_transcript":
                try:
                    tp = Path(transcript_path)
                    tp.parent.mkdir(parents=True, exist_ok=True)
                    with open(tp, "w", encoding="utf-8") as f:
                        f.write(model.to_json())
                    logger.info(f"[STT] Cached real speech transcript to {tp}")
                except Exception as ce:
                    logger.warning(f"[STT] Could not cache transcript to {transcript_path}: {ce}")

            return model, prov_name
        except Exception as e:
            logger.warning(f"[STT] Provider '{prov_name}' failed: {e}. Trying fallback...")
            last_err = e

    raise RuntimeError(f"All STT providers failed. Last error: {last_err}")
