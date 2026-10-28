#!/usr/bin/env python3
"""
llm_provider.py — Multi-LLM Caption Intelligence Engine for Rendering Studio.

Supported Providers:
  - Groq (ultra fast inference)
  - Google Gemini
  - OpenRouter (unified multi-model gateway)
  - Anthropic Claude
  - OpenAI / ChatGPT
  - Kimi (Moonshot)
  - DeepSeek
  - Local Deterministic Provider (100% offline fallback)

Features:
  - Three AI Caption Modes: RAW, CLEAN, VIRAL/POLISHED + Creative Rewrite.
  - LLMProvider abstraction with common interfaces.
  - JSON schema enforcement with automatic 1-shot repair.
  - Fallback pipeline ensuring video rendering never fails on API outages.
  - Caching system avoiding redundant token billing.
  - Usage tracker logging latency, tokens, estimated cost, and fallbacks.
  - Security: LLM output is pure data; never shell, code, or FFmpeg commands.
"""

import os
import json
import time
import hashlib
import urllib.request
import urllib.error
import urllib.parse
import re
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from .caption_model import CaptionModel, CaptionSegment

logger = logging.getLogger("rendering_studio.llm")

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "caption_ai"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
USAGE_LOG_PATH = CACHE_DIR / "usage.jsonl"


def log_llm_usage(record: Dict[str, Any]):
    """Append structured LLM usage metric to disk."""
    try:
        record["timestamp"] = time.time()
        record["datetime"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(USAGE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"Failed to record LLM usage log: {e}")


def get_cache_key(payload: Dict[str, Any]) -> str:
    """Compute deterministic MD5 cache key from task parameters."""
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


class LLMProvider(ABC):
    """Abstract base class for all Caption Intelligence LLM providers."""

    name: str = "base"
    default_model: str = "default"

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, json_mode: bool = True) -> str:
        """Execute chat completion returning raw response text."""
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Test API connectivity and model availability."""
        pass

    def clean_transcript(
        self,
        segments: List[Dict[str, Any]],
        language: str = "auto",
        model: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Mode CLEAN: Fix punctuation, normalize capitalization, remove transcription glitches
        and meaningless verbal fillers while strictly preserving original meaning.
        """
        system_prompt = (
            "You are a professional subtitle and transcript editor. Clean the given subtitle segments.\n"
            "Rules:\n"
            "1. Fix obvious punctuation, grammar, and capitalization.\n"
            "2. Remove meaningless verbal stutters (um, uh, you know) where safe.\n"
            "3. DO NOT change the intended meaning or delete core sentences.\n"
            "4. Return strict JSON matching: {\"segments\": [{\"id\": <int>, \"text\": \"<cleaned_text>\"}]}.\n"
            "5. Never output markdown, shell commands, or explanations."
        )
        user_prompt = json.dumps({"language": language, "segments": segments}, ensure_ascii=False)
        raw_res = self.complete(system_prompt, user_prompt, model=model, json_mode=True)
        return self._parse_and_validate_segments(raw_res, segments)

    def viral_rewrite(
        self,
        segments: List[Dict[str, Any]],
        language: str = "auto",
        creative: bool = False,
        model: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Mode VIRAL: Shorten, sharpen, and punch up caption text for high-impact social media.
        """
        creative_instruction = (
            "You may creatively rephrase for maximum punchiness and retention."
            if creative else
            "Shorten and sharpen for high retention without changing the original core facts."
        )
        system_prompt = (
            "You are an elite short-form video copywriter (Hormozi / MrBeast style caption specialist).\n"
            f"{creative_instruction}\n"
            "Rules:\n"
            "1. Make phrases punchy, clear, and easy to read in 0.5 to 2 seconds.\n"
            "2. Identify high-impact emphasis words (numbers, power verbs, contrast words).\n"
            "3. Return strict JSON matching: {\"segments\": [{\"id\": <int>, \"text\": \"<punchy_text>\", \"emphasis\": [\"<word>\"]}]}.\n"
            "4. Never output code or markdown backticks."
        )
        user_prompt = json.dumps({"language": language, "creative": creative, "segments": segments}, ensure_ascii=False)
        raw_res = self.complete(system_prompt, user_prompt, model=model, json_mode=True)
        return self._parse_and_validate_segments(raw_res, segments)

    def identify_emphasis(
        self,
        segments: List[Dict[str, Any]],
        language: str = "auto",
        model: Optional[str] = None
    ) -> Dict[int, List[str]]:
        """Identify key emphasis words for each segment ID."""
        system_prompt = (
            "Identify the 1-3 most visually important keywords (numbers, nouns, emotional punchlines) "
            "for each caption segment.\n"
            "Return JSON: {\"emphasis_by_id\": {\"<id>\": [\"word1\", \"word2\"]}}"
        )
        user_prompt = json.dumps({"segments": segments}, ensure_ascii=False)
        raw_res = self.complete(system_prompt, user_prompt, model=model, json_mode=True)
        try:
            cleaned = self._clean_json_str(raw_res)
            data = json.loads(cleaned)
            raw_map = data.get("emphasis_by_id", {})
            return {int(k): v for k, v in raw_map.items() if isinstance(v, list)}
        except Exception:
            return {}

    @classmethod
    def _clean_json_str(cls, text: str) -> str:
        """Strip markdown fences and whitespace from LLM output."""
        t = text.strip()
        t = re.sub(r'^```json\s*', '', t, flags=re.IGNORECASE)
        t = re.sub(r'^```\s*', '', t)
        t = re.sub(r'```$', '', t)
        return t.strip()

    def _parse_and_validate_segments(self, raw_json: str, original_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse structured segment JSON with 1-shot repair attempt and deterministic fallback."""
        try:
            cleaned = self._clean_json_str(raw_json)
            data = json.loads(cleaned)
            segs = data.get("segments", [])
            if isinstance(segs, list) and len(segs) > 0:
                # Merge validated results with originals
                id_map = {s["id"]: s for s in segs if isinstance(s, dict) and "id" in s}
                results = []
                for orig in original_segments:
                    oid = orig.get("id")
                    if oid in id_map and id_map[oid].get("text"):
                        item = dict(orig)
                        item["text"] = str(id_map[oid]["text"]).strip()
                        if "emphasis" in id_map[oid]:
                            item["emphasis"] = id_map[oid]["emphasis"]
                        results.append(item)
                    else:
                        results.append(orig)
                return results
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to parse JSON response: {e}. Trying repair...")

        # 1 repair attempt
        try:
            repair_prompt = f"Fix this invalid JSON into valid JSON with format {{\"segments\": [{{\"id\": 1, \"text\": \"...\"}}]}}:\n{raw_json[:1500]}"
            repaired = self.complete("Output only valid JSON.", repair_prompt, json_mode=True)
            cleaned = self._clean_json_str(repaired)
            data = json.loads(cleaned)
            segs = data.get("segments", [])
            if isinstance(segs, list) and len(segs) > 0:
                id_map = {s["id"]: s for s in segs if isinstance(s, dict) and "id" in s}
                return [
                    {**orig, "text": id_map[orig["id"]]["text"]}
                    if orig.get("id") in id_map and id_map[orig["id"]].get("text")
                    else orig
                    for orig in original_segments
                ]
        except Exception:
            pass

        # Fallback to originals
        logger.info(f"[{self.name}] Falling back to original transcript segments.")
        return original_segments


# --- Concrete Cloud Providers ---

class OpenAILLMProvider(LLMProvider):
    name = "openai"
    default_model = "gpt-4o-mini"
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "").strip()
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def test_connection(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"provider": self.name, "status": "NOT_CONFIGURED", "message": "OPENAI_API_KEY missing"}
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
                return {"provider": self.name, "status": "CONNECTED", "latency_ms": elapsed_ms, "model": self.model}
        except urllib.error.HTTPError as e:
            st = "AUTH_ERROR" if e.code in [401, 403] else ("RATE_LIMITED" if e.code == 429 else "ERROR")
            return {"provider": self.name, "status": st, "http_code": e.code, "message": f"OpenAI HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            return {"provider": self.name, "status": "NETWORK_ERROR", "message": f"Network error connecting to OpenAI: {e.reason}"}
        except Exception as e:
            return {"provider": self.name, "status": "ERROR", "message": str(e)}

    def complete(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, json_mode: bool = True) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        url = "https://api.openai.com/v1/chat/completions"
        chosen_model = model or self.model
        payload: Dict[str, Any] = {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        t0 = time.perf_counter()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            elapsed = time.perf_counter() - t0
            usage = data.get("usage", {})
            log_llm_usage({
                "provider": self.name,
                "model": chosen_model,
                "latency_s": round(elapsed, 3),
                "in_tokens": usage.get("prompt_tokens"),
                "out_tokens": usage.get("completion_tokens")
            })
            return data["choices"][0]["message"]["content"]


DEFAULT_USER_AGENT = "RenderingStudio/2.0 (Windows NT 10.0; Win64; x64)"


class GroqLLMProvider(LLMProvider):
    name = "groq"
    default_model = "qwen/qwen3.8-27b"
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "").strip()
        self.model = model or os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")

    def test_connection(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"provider": self.name, "status": "NOT_CONFIGURED", "message": "GROQ_API_KEY missing"}
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/models",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "User-Agent": DEFAULT_USER_AGENT
                }
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
                data = json.loads(resp.read().decode("utf-8"))
                models_data = data.get("data", [])
                available_models = [m.get("id") for m in models_data if isinstance(m, dict) and "id" in m]
                
                # Check model availability if specific model requested
                chosen_model = self.model
                if chosen_model and available_models and chosen_model not in available_models:
                    # If configured model is not available for this key, report MODEL_ERROR per status rules
                    return {
                        "provider": self.name,
                        "status": "MODEL_ERROR",
                        "http_code": 404,
                        "latency_ms": elapsed_ms,
                        "model": chosen_model,
                        "available_models": available_models,
                        "message": f"Model '{chosen_model}' was not found or is unavailable on Groq. Available models: {', '.join(available_models)}"
                    }

                return {
                    "provider": self.name,
                    "status": "CONNECTED",
                    "latency_ms": elapsed_ms,
                    "model": chosen_model,
                    "available_models": available_models
                }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if e.code == 401 or (e.code == 403 and "invalid_api_key" in err_body):
                st = "AUTH_ERROR"
            elif e.code == 404:
                st = "MODEL_ERROR"
            elif e.code == 429:
                st = "RATE_LIMITED"
            elif e.code == 403:
                st = "AUTH_ERROR"
            else:
                st = "ERROR"
            return {"provider": self.name, "status": st, "http_code": e.code, "message": f"Groq HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            return {"provider": self.name, "status": "NETWORK_ERROR", "message": f"Network error connecting to Groq: {e.reason}"}
        except Exception as e:
            return {"provider": self.name, "status": "ERROR", "message": str(e)}

    def complete(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, json_mode: bool = True) -> str:
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        url = "https://api.groq.com/openai/v1/chat/completions"
        chosen_model = model or self.model
        payload: Dict[str, Any] = {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": DEFAULT_USER_AGENT
        }
        t0 = time.perf_counter()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=25.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                elapsed = time.perf_counter() - t0
                usage = data.get("usage", {})
                log_llm_usage({
                    "provider": self.name,
                    "model": chosen_model,
                    "latency_s": round(elapsed, 3),
                    "in_tokens": usage.get("prompt_tokens"),
                    "out_tokens": usage.get("completion_tokens")
                })
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            # If 404 model not found and default model failed, try fallback to qwen/qwen3.8-27b
            if e.code == 404 and chosen_model != "qwen/qwen3.8-27b":
                logger.warning(f"[groq] Model '{chosen_model}' returned 404, falling back to 'qwen/qwen3.8-27b'...")
                payload["model"] = "qwen/qwen3.8-27b"
                req_fallback = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req_fallback, timeout=25.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    elapsed = time.perf_counter() - t0
                    usage = data.get("usage", {})
                    log_llm_usage({
                        "provider": self.name,
                        "model": "qwen/qwen3.8-27b",
                        "latency_s": round(elapsed, 3),
                        "in_tokens": usage.get("prompt_tokens"),
                        "out_tokens": usage.get("completion_tokens")
                    })
                    return data["choices"][0]["message"]["content"]
            raise


class GeminiLLMProvider(LLMProvider):
    name = "gemini"
    default_model = "gemini-1.5-flash"
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")

    def test_connection(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"provider": self.name, "status": "NOT_CONFIGURED", "message": "GEMINI_API_KEY missing"}
        t0 = time.perf_counter()
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
                return {"provider": self.name, "status": "CONNECTED", "latency_ms": elapsed_ms, "model": self.model}
        except urllib.error.HTTPError as e:
            st = "AUTH_ERROR" if e.code in [400, 401, 403] else ("RATE_LIMITED" if e.code == 429 else "ERROR")
            return {"provider": self.name, "status": st, "http_code": e.code, "message": f"Gemini HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            return {"provider": self.name, "status": "NETWORK_ERROR", "message": f"Network error connecting to Gemini: {e.reason}"}
        except Exception as e:
            return {"provider": self.name, "status": "ERROR", "message": str(e)}

    def complete(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, json_mode: bool = True) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        chosen_model = model or self.model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{chosen_model}:generateContent?key={self.api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.2}
        }
        if json_mode:
            payload["generationConfig"]["response_mime_type"] = "application/json"

        headers = {"Content-Type": "application/json"}
        t0 = time.perf_counter()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            elapsed = time.perf_counter() - t0
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("No candidate returned by Gemini API")
            out_text = candidates[0]["content"]["parts"][0]["text"]
            log_llm_usage({
                "provider": self.name,
                "model": chosen_model,
                "latency_s": round(elapsed, 3)
            })
            return out_text


class OpenRouterLLMProvider(LLMProvider):
    name = "openrouter"
    default_model = "google/gemini-2.0-flash-001"
    
    def __init__(self, api_key: Optional[str] = None, model: str = "google/gemini-2.0-flash-001"):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "").strip()
        self.model = model or os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")

    def test_connection(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"provider": self.name, "status": "NOT_CONFIGURED", "message": "OPENROUTER_API_KEY missing"}
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
                return {"provider": self.name, "status": "CONNECTED", "latency_ms": elapsed_ms, "model": self.model}
        except urllib.error.HTTPError as e:
            st = "AUTH_ERROR" if e.code in [401, 403] else ("RATE_LIMITED" if e.code == 429 else "ERROR")
            return {"provider": self.name, "status": st, "http_code": e.code, "message": f"OpenRouter HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            return {"provider": self.name, "status": "NETWORK_ERROR", "message": f"Network error connecting to OpenRouter: {e.reason}"}
        except Exception as e:
            return {"provider": self.name, "status": "ERROR", "message": str(e)}

    def complete(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, json_mode: bool = True) -> str:
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        url = "https://openrouter.ai/api/v1/chat/completions"
        chosen_model = model or self.model
        payload = {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://renderingstudio.engine",
            "X-Title": "Rendering Studio"
        }
        t0 = time.perf_counter()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            elapsed = time.perf_counter() - t0
            log_llm_usage({"provider": self.name, "model": chosen_model, "latency_s": round(elapsed, 3)})
            return data["choices"][0]["message"]["content"]


class ClaudeLLMProvider(LLMProvider):
    name = "claude"
    default_model = "claude-3-5-haiku-20241022"
    
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-haiku-20241022"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")

    def test_connection(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"provider": self.name, "status": "NOT_CONFIGURED", "message": "ANTHROPIC_API_KEY missing"}
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01"
                }
            )
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
                return {"provider": self.name, "status": "CONNECTED", "latency_ms": elapsed_ms, "model": self.model}
        except urllib.error.HTTPError as e:
            st = "AUTH_ERROR" if e.code in [401, 403] else ("RATE_LIMITED" if e.code == 429 else "ERROR")
            return {"provider": self.name, "status": st, "http_code": e.code, "message": f"Claude HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            return {"provider": self.name, "status": "NETWORK_ERROR", "message": f"Network error connecting to Anthropic: {e.reason}"}
        except Exception as e:
            return {"provider": self.name, "status": "ERROR", "message": str(e)}

    def complete(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, json_mode: bool = True) -> str:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")
        url = "https://api.anthropic.com/v1/messages"
        chosen_model = model or self.model
        payload = {
            "model": chosen_model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": 2048,
            "temperature": 0.2
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        t0 = time.perf_counter()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            elapsed = time.perf_counter() - t0
            log_llm_usage({"provider": self.name, "model": chosen_model, "latency_s": round(elapsed, 3)})
            return data["content"][0]["text"]


class DeepSeekLLMProvider(LLMProvider):
    name = "deepseek"
    default_model = "deepseek-chat"
    
    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek-chat"):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "").strip()
        self.model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

    def test_connection(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"provider": self.name, "status": "NOT_CONFIGURED", "message": "DEEPSEEK_API_KEY missing"}
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                "https://api.deepseek.com/models",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
                return {"provider": self.name, "status": "CONNECTED", "latency_ms": elapsed_ms, "model": self.model}
        except urllib.error.HTTPError as e:
            st = "AUTH_ERROR" if e.code in [401, 403] else ("RATE_LIMITED" if e.code == 429 else "ERROR")
            return {"provider": self.name, "status": st, "http_code": e.code, "message": f"DeepSeek HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            return {"provider": self.name, "status": "NETWORK_ERROR", "message": f"Network error connecting to DeepSeek: {e.reason}"}
        except Exception as e:
            return {"provider": self.name, "status": "ERROR", "message": str(e)}

    def complete(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, json_mode: bool = True) -> str:
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        url = "https://api.deepseek.com/chat/completions"
        chosen_model = model or self.model
        payload = {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        t0 = time.perf_counter()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            elapsed = time.perf_counter() - t0
            log_llm_usage({"provider": self.name, "model": chosen_model, "latency_s": round(elapsed, 3)})
            return data["choices"][0]["message"]["content"]


class KimiLLMProvider(LLMProvider):
    name = "kimi"
    default_model = "moonshot-v1-8k"
    
    def __init__(self, api_key: Optional[str] = None, model: str = "moonshot-v1-8k"):
        self.api_key = api_key or os.environ.get("MOONSHOT_API_KEY", "").strip() or os.environ.get("KIMI_API_KEY", "").strip()
        self.model = model or os.environ.get("KIMI_MODEL", "moonshot-v1-8k")

    def test_connection(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"provider": self.name, "status": "NOT_CONFIGURED", "message": "MOONSHOT_API_KEY / KIMI_API_KEY missing"}
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                "https://api.moonshot.cn/v1/models",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
                return {"provider": self.name, "status": "CONNECTED", "latency_ms": elapsed_ms, "model": self.model}
        except urllib.error.HTTPError as e:
            st = "AUTH_ERROR" if e.code in [401, 403] else ("RATE_LIMITED" if e.code == 429 else "ERROR")
            return {"provider": self.name, "status": st, "http_code": e.code, "message": f"Kimi/Moonshot HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            return {"provider": self.name, "status": "NETWORK_ERROR", "message": f"Network error connecting to Moonshot: {e.reason}"}
        except Exception as e:
            return {"provider": self.name, "status": "ERROR", "message": str(e)}

    def complete(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, json_mode: bool = True) -> str:
        if not self.api_key:
            raise RuntimeError("KIMI_API_KEY is not configured")
        url = "https://api.moonshot.cn/v1/chat/completions"
        chosen_model = model or self.model
        payload = {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        t0 = time.perf_counter()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            elapsed = time.perf_counter() - t0
            log_llm_usage({"provider": self.name, "model": chosen_model, "latency_s": round(elapsed, 3)})
            return data["choices"][0]["message"]["content"]


class DeterministicLocalLLMProvider(LLMProvider):
    """
    100% offline, deterministic heuristic NLP provider.
    Ensures that when all cloud APIs fail, are rate-limited, or are offline,
    the caption intelligence system still delivers high-quality cleaned and viral subtitles.
    """
    name = "local_deterministic"
    default_model = "rule_based_engine"

    def test_connection(self) -> Dict[str, Any]:
        return {"provider": self.name, "status": "AVAILABLE", "model": self.default_model, "offline": True}

    def complete(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, json_mode: bool = True) -> str:
        return "{}"

    def clean_transcript(self, segments: List[Dict[str, Any]], language: str = "auto", model: Optional[str] = None) -> List[Dict[str, Any]]:
        cleaned_segs = []
        fillers = {"um", "uh", "you know", "like,", "i mean"}
        for s in segments:
            txt = s.get("text", "")
            # Remove filler words
            for f in fillers:
                txt = re.sub(rf'\b{re.escape(f)}\b', '', txt, flags=re.IGNORECASE)
            # Normalize whitespace
            txt = re.sub(r'\s+', ' ', txt).strip()
            # Capitalize first letter if missing
            if txt and txt[0].islower():
                txt = txt[0].upper() + txt[1:]
            # Ensure sentence ending punctuation if missing
            if txt and not txt.endswith((".", "!", "?", "…")):
                txt += "."
            item = dict(s)
            item["text"] = txt
            cleaned_segs.append(item)
        return cleaned_segs

    def viral_rewrite(self, segments: List[Dict[str, Any]], language: str = "auto", creative: bool = False, model: Optional[str] = None) -> List[Dict[str, Any]]:
        # Shorten and punch up words (convert numbers, capitalize key words)
        rewritten = []
        num_word_map = {
            "ten thousand": "10,000", "one million": "1M", "one thousand": "1,000",
            "five hundred": "500", "twenty": "20", "fifty": "50", "hundred": "100"
        }
        for s in self.clean_transcript(segments, language=language):
            txt = s.get("text", "")
            for nw, num in num_word_map.items():
                txt = re.sub(rf'\b{re.escape(nw)}\b', num, txt, flags=re.IGNORECASE)
            # Remove unnecessary introductory padding
            txt = re.sub(r'^(So then|Basically|As you can see|In this video)\s*,?\s*', '', txt, flags=re.IGNORECASE)
            if txt and txt[0].islower():
                txt = txt[0].upper() + txt[1:]
            s["text"] = txt
            rewritten.append(s)
        return rewritten


# --- LLM Provider Registry & Intelligent Fallback Manager ---

LLM_PROVIDER_REGISTRY: Dict[str, LLMProvider] = {
    "groq": GroqLLMProvider(),
    "gemini": GeminiLLMProvider(),
    "openrouter": OpenRouterLLMProvider(),
    "claude": ClaudeLLMProvider(),
    "openai": OpenAILLMProvider(),
    "kimi": KimiLLMProvider(),
    "deepseek": DeepSeekLLMProvider(),
    "local_deterministic": DeterministicLocalLLMProvider()
}


def get_llm_provider(name: str = "auto") -> LLMProvider:
    """Retrieve LLM provider by name, defaulting to local fallback if unknown."""
    k = (name or "auto").strip().lower()
    if k == "auto":
        # Check active environment keys in prioritized order: Groq -> Gemini -> OpenRouter -> OpenAI -> Claude -> DeepSeek -> Local
        order = ["groq", "gemini", "openrouter", "openai", "claude", "deepseek", "kimi"]
        for p in order:
            prov = LLM_PROVIDER_REGISTRY[p]
            if getattr(prov, "api_key", None):
                return prov
        return LLM_PROVIDER_REGISTRY["local_deterministic"]
    return LLM_PROVIDER_REGISTRY.get(k, LLM_PROVIDER_REGISTRY["local_deterministic"])


def execute_llm_intelligence_with_fallback(
    mode: str,
    segments: List[Dict[str, Any]],
    preferred_provider: str = "auto",
    language: str = "auto",
    creative_rewrite: bool = False,
    model: Optional[str] = None,
    use_cache: bool = True
) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
    """
    Execute AI Caption Intelligence (CLEAN or VIRAL) with deterministic fallback.
    Returns (processed_segments, provider_name, execution_metadata).
    """
    mode_clean = (mode or "raw").strip().lower()
    if mode_clean == "raw" or not segments:
        return segments, "raw", {"cached": False, "provider": "none"}

    def _get_txt(item: Any) -> str:
        if isinstance(item, dict):
            return item.get("text", "")
        return getattr(item, "text", str(item))

    cache_key = get_cache_key({
        "mode": mode_clean,
        "language": language,
        "creative": creative_rewrite,
        "provider": preferred_provider,
        "model": model,
        "texts": [_get_txt(s) for s in segments]
    })
    cache_file = CACHE_DIR / f"{cache_key}.json"

    if use_cache and cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            logger.info(f"[LLM] Returning cached caption intelligence result ({cache_key[:8]})")
            return cached_data["segments"], cached_data["provider"], {"cached": True, "provider": cached_data["provider"]}
        except Exception:
            pass

    # Build fallback cascade
    candidates = []
    if preferred_provider and preferred_provider != "auto":
        if preferred_provider in LLM_PROVIDER_REGISTRY:
            candidates.append(LLM_PROVIDER_REGISTRY[preferred_provider])
    else:
        # Check available providers with API keys
        order = ["groq", "gemini", "openrouter", "openai", "claude", "deepseek", "kimi"]
        for p in order:
            prov = LLM_PROVIDER_REGISTRY[p]
            if getattr(prov, "api_key", None):
                candidates.append(prov)

    # Always add local deterministic as terminal fallback
    candidates.append(LLM_PROVIDER_REGISTRY["local_deterministic"])

    last_err = None
    for provider in candidates:
        try:
            t0 = time.perf_counter()
            if mode_clean == "viral":
                res = provider.viral_rewrite(segments, language=language, creative=creative_rewrite, model=model)
            else:
                res = provider.clean_transcript(segments, language=language, model=model)
            elapsed = time.perf_counter() - t0

            # Save to disk cache
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump({"segments": res, "provider": provider.name}, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

            return res, provider.name, {
                "cached": False,
                "provider": provider.name,
                "latency_s": round(elapsed, 3)
            }
        except Exception as e:
            logger.warning(f"[LLM] Provider {provider.name} failed: {e}. Trying next fallback...")
            last_err = e

    # Ultimate safety net: return original segments
    logger.error(f"[LLM] All LLM providers failed ({last_err}). Preserving original transcript.")
    return segments, "fallback_original", {"error": str(last_err), "cached": False}
