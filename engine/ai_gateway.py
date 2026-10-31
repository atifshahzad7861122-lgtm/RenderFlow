"""
ai_gateway.py — Centralized Multi-Provider AI Model Gateway & Routing Engine
=============================================================================
RenderFlow v2.5.1 Enterprise Multimodal AI Subsystem.

Supported Providers:
  - OpenAI (GPT-4o, GPT-4o-mini, o1-mini)
  - Google Gemini (Gemini 2.0 Flash, Gemini 1.5 Flash, Gemini 1.5 Pro)
  - Anthropic Claude (Claude 3.5 Sonnet, Claude 3.5 Haiku, Claude 3 Opus)
  - OpenRouter (Unified multi-model gateway: Llama, Mistral, Gemini, Claude)
  - DeepSeek (DeepSeek Chat V3, DeepSeek Coder)
  - Groq (Qwen 3.8, Llama 3.3 70B Versatile, Llama 3.1 8B)
  - Kimi / Moonshot (Moonshot v1 8k/32k/128k)
  - Local Deterministic Provider (100% offline, zero-latency, rule-based NLP)

Per-Task Routing:
  1. TRANSCRIPT_NORMALIZATION
  2. SCENE_SEGMENTATION
  3. SEMANTIC_SCENE_PLANNING
  4. SEARCH_QUERY_GENERATION
  5. IMAGE_VIDEO_SEMANTIC_ANALYSIS (Vision / Multimodal)
  6. CAPTION_REFINEMENT
  7. SCENE_CONTINUITY_EVALUATION
  8. AMBIGUOUS_ASSET_REVIEW
  9. SCENE_PLAN_VALIDATION_ASSISTANCE
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import enum
import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("rendering_studio.ai_gateway")

ROOT_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT_DIR / ".cache" / "ai_gateway"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
USAGE_LOG_PATH = CACHE_DIR / "usage.jsonl"
VAULT_PATH = CACHE_DIR / ".dpapi_vault.bin"
CONFIG_PATH = ROOT_DIR / "config" / "ai_routing.json"


# ---------------------------------------------------------------------------
# Windows DPAPI Hardware / OS-level Cryptographic Vault
# ---------------------------------------------------------------------------

class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def dpapi_encrypt(data_str: str) -> Optional[bytes]:
    """Encrypt a secret string using Windows DPAPI (CryptProtectData)."""
    if sys.platform != "win32":
        return None
    try:
        raw_bytes = data_str.encode("utf-8")
        blob_in = DATA_BLOB(len(raw_bytes), ctypes.cast(ctypes.create_string_buffer(raw_bytes), ctypes.POINTER(ctypes.c_byte)))
        blob_out = DATA_BLOB()
        res = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), "RenderFlowVault", None, None, None, 0, ctypes.byref(blob_out)
        )
        if not res:
            return None
        encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return encrypted
    except Exception as e:
        logger.debug(f"DPAPI encryption fallback: {e}")
        return None


def dpapi_decrypt(enc_bytes: bytes) -> Optional[str]:
    """Decrypt DPAPI-protected secret."""
    if sys.platform != "win32":
        return None
    try:
        blob_in = DATA_BLOB(len(enc_bytes), ctypes.cast(ctypes.create_string_buffer(enc_bytes), ctypes.POINTER(ctypes.c_byte)))
        blob_out = DATA_BLOB()
        res = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        )
        if not res:
            return None
        decrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return decrypted.decode("utf-8")
    except Exception as e:
        logger.debug(f"DPAPI decryption fallback: {e}")
        return None


class TaskType(str, enum.Enum):
    TRANSCRIPT_NORMALIZATION = "transcript_normalization"
    SCENE_SEGMENTATION = "scene_segmentation"
    SEMANTIC_SCENE_PLANNING = "semantic_scene_planning"
    SEARCH_QUERY_GENERATION = "search_query_generation"
    IMAGE_VIDEO_SEMANTIC_ANALYSIS = "image_video_semantic_analysis"
    CAPTION_REFINEMENT = "caption_refinement"
    SCENE_CONTINUITY_EVALUATION = "scene_continuity_evaluation"
    AMBIGUOUS_ASSET_REVIEW = "ambiguous_asset_review"
    SCENE_PLAN_VALIDATION_ASSISTANCE = "scene_plan_validation_assistance"


@dataclass
class ProviderCapabilities:
    supports_text: bool = True
    supports_vision: bool = False
    supports_structured_output: bool = True
    supports_system_prompt: bool = True
    context_window: int = 32000
    estimated_input_cost_per_m: float = 0.50
    estimated_output_cost_per_m: float = 1.50


@dataclass
class ModelUsageMetric:
    task: str
    provider: str
    model: str
    duration_sec: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    success: bool = True
    error_message: Optional[str] = None
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "provider": self.provider,
            "model": self.model,
            "duration_sec": round(self.duration_sec, 3),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": round(self.estimated_cost, 6),
            "success": self.success,
            "error_message": self.error_message,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "timestamp": round(self.timestamp, 3),
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp)),
        }


# ---------------------------------------------------------------------------
# Base Provider Adapter
# ---------------------------------------------------------------------------

class BaseAIProvider:
    """Normalized provider adapter interface."""
    id: str = "base"
    name: str = "Base Provider"
    capabilities: ProviderCapabilities = ProviderCapabilities()

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or ""
        self.base_url = base_url or ""

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        json_mode: bool = False,
        images: Optional[List[Union[str, Path, bytes]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_sec: float = 25.0,
    ) -> Tuple[str, Dict[str, int]]:
        """
        Execute completion returning (response_text, token_counts).
        Subclasses must implement.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Concrete Providers
# ---------------------------------------------------------------------------

class OpenAICompatibleProvider(BaseAIProvider):
    """Generic OpenAI-compatible HTTP client."""
    id: str = "openai_compatible"
    default_endpoint: str = "https://api.openai.com/v1/chat/completions"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        json_mode: bool = False,
        images: Optional[List[Union[str, Path, bytes]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_sec: float = 25.0,
    ) -> Tuple[str, Dict[str, int]]:
        endpoint = self.base_url or self.default_endpoint
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "RenderFlow-Gateway/2.5.1",
        }

        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Process user content (multimodal or text)
        if images and self.capabilities.supports_vision:
            content_list: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]
            for img in images:
                b64_data = ""
                mime = "image/jpeg"
                if isinstance(img, (str, Path)):
                    p = Path(img)
                    if p.exists():
                        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
                        with open(p, "rb") as f:
                            b64_data = base64.b64encode(f.read()).decode("utf-8")
                elif isinstance(img, bytes):
                    b64_data = base64.b64encode(img).decode("utf-8")

                if b64_data:
                    content_list.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64_data}"}
                    })
            messages.append({"role": "user", "content": content_list})
        else:
            messages.append({"role": "user", "content": user_prompt})

        payload: Dict[str, Any] = {
            "model": model or getattr(self, "default_model", "gpt-4o-mini"),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        content = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage", {})
        counts = {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }
        return content, counts


class OpenAIProvider(OpenAICompatibleProvider):
    id = "openai"
    name = "OpenAI"
    default_model = "gpt-4o-mini"
    default_endpoint = "https://api.openai.com/v1/chat/completions"
    capabilities = ProviderCapabilities(
        supports_text=True,
        supports_vision=True,
        supports_structured_output=True,
        context_window=128000,
        estimated_input_cost_per_m=0.15,
        estimated_output_cost_per_m=0.60
    )


class GroqProvider(OpenAICompatibleProvider):
    id = "groq"
    name = "Groq"
    default_model = "qwen/qwen3.8-27b"
    default_endpoint = "https://api.groq.com/openai/v1/chat/completions"
    capabilities = ProviderCapabilities(
        supports_text=True,
        supports_vision=False,
        supports_structured_output=True,
        context_window=32768,
        estimated_input_cost_per_m=0.08,
        estimated_output_cost_per_m=0.15
    )


class OpenRouterProvider(OpenAICompatibleProvider):
    id = "openrouter"
    name = "OpenRouter"
    default_model = "google/gemini-2.0-flash-001"
    default_endpoint = "https://openrouter.ai/api/v1/chat/completions"
    capabilities = ProviderCapabilities(
        supports_text=True,
        supports_vision=True,
        supports_structured_output=True,
        context_window=1000000,
        estimated_input_cost_per_m=0.10,
        estimated_output_cost_per_m=0.40
    )


class DeepSeekProvider(OpenAICompatibleProvider):
    id = "deepseek"
    name = "DeepSeek"
    default_model = "deepseek-chat"
    default_endpoint = "https://api.deepseek.com/chat/completions"
    capabilities = ProviderCapabilities(
        supports_text=True,
        supports_vision=False,
        supports_structured_output=True,
        context_window=64000,
        estimated_input_cost_per_m=0.14,
        estimated_output_cost_per_m=0.28
    )


class KimiProvider(OpenAICompatibleProvider):
    id = "kimi"
    name = "Kimi (Moonshot)"
    default_model = "moonshot-v1-8k"
    default_endpoint = "https://api.moonshot.cn/v1/chat/completions"
    capabilities = ProviderCapabilities(
        supports_text=True,
        supports_vision=False,
        supports_structured_output=True,
        context_window=8192,
        estimated_input_cost_per_m=0.20,
        estimated_output_cost_per_m=0.40
    )


class GeminiProvider(BaseAIProvider):
    """Google Gemini REST API adapter."""
    id = "gemini"
    name = "Google Gemini"
    default_model = "gemini-2.0-flash"
    capabilities = ProviderCapabilities(
        supports_text=True,
        supports_vision=True,
        supports_structured_output=True,
        context_window=1000000,
        estimated_input_cost_per_m=0.10,
        estimated_output_cost_per_m=0.40
    )

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        json_mode: bool = False,
        images: Optional[List[Union[str, Path, bytes]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_sec: float = 25.0,
    ) -> Tuple[str, Dict[str, int]]:
        chosen_model = model or self.default_model
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{chosen_model}:generateContent?key={self.api_key}"

        parts: List[Dict[str, Any]] = []
        if images:
            for img in images:
                b64_data = ""
                mime = "image/jpeg"
                if isinstance(img, (str, Path)):
                    p = Path(img)
                    if p.exists():
                        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
                        with open(p, "rb") as f:
                            b64_data = base64.b64encode(f.read()).decode("utf-8")
                elif isinstance(img, bytes):
                    b64_data = base64.b64encode(img).decode("utf-8")

                if b64_data:
                    parts.append({"inlineData": {"mimeType": mime, "data": b64_data}})

        parts.append({"text": user_prompt})

        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "RenderFlow-Gateway/2.5.1"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        cands = data.get("candidates", [])
        if not cands:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        content_parts = cands[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in content_parts)
        usage = data.get("usageMetadata", {})
        counts = {
            "prompt_tokens": usage.get("promptTokenCount", 0),
            "completion_tokens": usage.get("candidatesTokenCount", 0),
            "total_tokens": usage.get("totalTokenCount", 0),
        }
        return text, counts


class ClaudeProvider(BaseAIProvider):
    """Anthropic Claude REST API adapter."""
    id = "claude"
    name = "Anthropic Claude"
    default_model = "claude-3-5-sonnet-20241022"
    capabilities = ProviderCapabilities(
        supports_text=True,
        supports_vision=True,
        supports_structured_output=True,
        context_window=200000,
        estimated_input_cost_per_m=3.00,
        estimated_output_cost_per_m=15.00
    )

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        json_mode: bool = False,
        images: Optional[List[Union[str, Path, bytes]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout_sec: float = 25.0,
    ) -> Tuple[str, Dict[str, int]]:
        endpoint = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "RenderFlow-Gateway/2.5.1",
        }

        user_content: List[Dict[str, Any]] = []
        if images:
            for img in images:
                b64_data = ""
                mime = "image/jpeg"
                if isinstance(img, (str, Path)):
                    p = Path(img)
                    if p.exists():
                        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
                        with open(p, "rb") as f:
                            b64_data = base64.b64encode(f.read()).decode("utf-8")
                elif isinstance(img, bytes):
                    b64_data = base64.b64encode(img).decode("utf-8")

                if b64_data:
                    user_content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": mime, "data": b64_data}
                    })

        prompt_text = user_prompt
        if json_mode:
            prompt_text += "\nRespond with valid RFC-8259 JSON only."
        user_content.append({"type": "text", "text": prompt_text})

        payload = {
            "model": model or self.default_model,
            "messages": [{"role": "user", "content": user_content}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        content_blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        usage = data.get("usage", {})
        counts = {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        }
        return text, counts


class LocalDeterministicProvider(BaseAIProvider):
    """100% offline, rule-based semantic NLP fallback provider."""
    id = "local_deterministic"
    name = "Local Deterministic Rule Engine"
    capabilities = ProviderCapabilities(
        supports_text=True,
        supports_vision=False,
        supports_structured_output=True,
        context_window=1000000,
        estimated_input_cost_per_m=0.0,
        estimated_output_cost_per_m=0.0
    )

    def is_configured(self) -> bool:
        return True

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        json_mode: bool = False,
        images: Optional[List[Union[str, Path, bytes]]] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        timeout_sec: float = 1.0,
    ) -> Tuple[str, Dict[str, int]]:
        """Synthesize deterministic rule-based output based on task context."""
        # Clean extracted words from user prompt
        words = [w.strip() for w in re.findall(r"\b[A-Za-z0-9_-]{3,}\b", user_prompt) if len(w) > 2]
        unique_words = list(dict.fromkeys(words))[:10]

        if json_mode:
            # Generate deterministic structured fallback
            result = {
                "status": "deterministic_fallback",
                "summary": " ".join(unique_words[:5]) if unique_words else "Scene overview",
                "visual_intent": f"Visual presentation focusing on {', '.join(unique_words[:4])}" if unique_words else "Visual narrative inspection",
                "subjects": unique_words[:3],
                "actions": ["present", "inspect", "highlight"],
                "setting": "studio",
                "mood": "neutral",
                "search_queries": [" ".join(unique_words[i:i+2]) for i in range(0, min(6, len(unique_words)), 2)] or ["cinematic backdrop"],
                "confidence": 0.70,
            }
            return json.dumps(result), {"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100}

        return f"Deterministic narrative analysis: {' '.join(unique_words)}", {"prompt_tokens": 20, "completion_tokens": 20, "total_tokens": 40}


# ---------------------------------------------------------------------------
# Centralized AI Gateway
# ---------------------------------------------------------------------------

class AIGateway:
    """
    Centralized Multi-Provider AI Gateway & Router.
    Enforces task-based routing, primary-to-fallback escalation,
    Windows DPAPI secret protection, and JSON output repair.
    """
    _instance: Optional[AIGateway] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(AIGateway, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.providers: Dict[str, BaseAIProvider] = {}
        self.task_routing: Dict[str, Dict[str, str]] = {}
        self._init_providers()
        self._load_routing_config()
        self._initialized = True

    def _init_providers(self):
        """Instantiate all supported providers with active keys."""
        provider_classes = [
            OpenAIProvider,
            GeminiProvider,
            ClaudeProvider,
            OpenRouterProvider,
            DeepSeekProvider,
            GroqProvider,
            KimiProvider,
            LocalDeterministicProvider,
        ]

        from .credentials_manager import get_stored_key, get_stored_model

        for p_cls in provider_classes:
            p_id = p_cls.id
            key = get_stored_key(p_id)
            # Check DPAPI vault if env key was empty
            if not key:
                key = self._get_vault_key(p_id) or ""
            inst = p_cls(api_key=key)
            self.providers[p_id] = inst

    def _get_vault_key(self, provider_id: str) -> Optional[str]:
        if not VAULT_PATH.exists():
            return None
        try:
            with open(VAULT_PATH, "rb") as f:
                enc = f.read()
            dec = dpapi_decrypt(enc)
            if dec:
                data = json.loads(dec)
                return data.get(provider_id)
        except Exception:
            pass
        return None

    def _save_vault_key(self, provider_id: str, key: str):
        existing: Dict[str, str] = {}
        if VAULT_PATH.exists():
            try:
                with open(VAULT_PATH, "rb") as f:
                    dec = dpapi_decrypt(f.read())
                if dec:
                    existing = json.loads(dec)
            except Exception:
                existing = {}

        existing[provider_id] = key
        enc = dpapi_encrypt(json.dumps(existing))
        if enc:
            with open(VAULT_PATH, "wb") as f:
                f.write(enc)

    def set_provider_credential(self, provider_id: str, api_key: str, model: Optional[str] = None):
        """Update provider credentials in memory, vault, and living provider instance."""
        clean_key = (api_key or "").strip()
        if provider_id in self.providers:
            self.providers[provider_id].api_key = clean_key
        # Save to DPAPI vault
        self._save_vault_key(provider_id, clean_key)
        # Also sync to credentials manager / .env
        from .credentials_manager import save_credential
        save_credential(provider_id, clean_key, model)

    def _load_routing_config(self):
        """Load default task-routing configuration."""
        default_routing = {
            TaskType.TRANSCRIPT_NORMALIZATION.value: {"primary": "groq", "fallback": "local_deterministic"},
            TaskType.SCENE_SEGMENTATION.value: {"primary": "gemini", "fallback": "local_deterministic"},
            TaskType.SEMANTIC_SCENE_PLANNING.value: {"primary": "gemini", "fallback": "openai"},
            TaskType.SEARCH_QUERY_GENERATION.value: {"primary": "groq", "fallback": "gemini"},
            TaskType.IMAGE_VIDEO_SEMANTIC_ANALYSIS.value: {"primary": "gemini", "fallback": "openai"},
            TaskType.CAPTION_REFINEMENT.value: {"primary": "groq", "fallback": "gemini"},
            TaskType.SCENE_CONTINUITY_EVALUATION.value: {"primary": "gemini", "fallback": "local_deterministic"},
            TaskType.AMBIGUOUS_ASSET_REVIEW.value: {"primary": "gemini", "fallback": "openai"},
            TaskType.SCENE_PLAN_VALIDATION_ASSISTANCE.value: {"primary": "gemini", "fallback": "local_deterministic"},
        }
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    default_routing.update(loaded)
            except Exception as e:
                logger.warning(f"Could not load custom routing config: {e}")

        self.task_routing = default_routing

    def get_route(self, task: Union[str, TaskType]) -> Tuple[str, str]:
        """Return (primary_provider_id, fallback_provider_id) for task."""
        t_str = task.value if isinstance(task, TaskType) else str(task)
        route = self.task_routing.get(t_str, {"primary": "gemini", "fallback": "local_deterministic"})
        return route.get("primary", "gemini"), route.get("fallback", "local_deterministic")

    def execute_task(
        self,
        task: Union[str, TaskType],
        system_prompt: str,
        user_prompt: str,
        model_override: Optional[str] = None,
        json_mode: bool = False,
        images: Optional[List[Union[str, Path, bytes]]] = None,
        temperature: float = 0.3,
        max_retries: int = 2,
        timeout_sec: float = 25.0,
    ) -> Tuple[str, ModelUsageMetric]:
        """
        Execute request with automatic capability-checking, fallback escalation,
        and usage observability.
        """
        t_str = task.value if isinstance(task, TaskType) else str(task)
        primary_id, fallback_id = self.get_route(task)

        needs_vision = bool(images)
        chain = [primary_id, fallback_id, "local_deterministic"]
        # Deduplicate while preserving order
        candidate_ids = list(dict.fromkeys(chain))

        last_error = None
        for attempt_idx, p_id in enumerate(candidate_ids):
            prov = self.providers.get(p_id)
            if not prov:
                continue

            if not prov.is_configured() and p_id != "local_deterministic":
                continue

            # Check capabilities
            if needs_vision and not prov.capabilities.supports_vision:
                logger.info(f"Skipping provider {p_id} for {t_str}: does not support multimodal vision.")
                continue

            t0 = time.time()
            # Bounded retry loop for current provider
            for retry_i in range(max_retries + 1):
                try:
                    resp_text, token_counts = prov.complete(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        model=model_override,
                        json_mode=json_mode,
                        images=images,
                        temperature=temperature,
                        timeout_sec=timeout_sec,
                    )

                    # Validate JSON if json_mode is required
                    if json_mode:
                        resp_text = self._repair_json_output(resp_text)

                    dur = time.time() - t0
                    # Estimate cost
                    pt = token_counts.get("prompt_tokens", 0)
                    ct = token_counts.get("completion_tokens", 0)
                    cost = (pt / 1_000_000.0) * prov.capabilities.estimated_input_cost_per_m + \
                           (ct / 1_000_000.0) * prov.capabilities.estimated_output_cost_per_m

                    metric = ModelUsageMetric(
                        task=t_str,
                        provider=p_id,
                        model=model_override or getattr(prov, "default_model", "default"),
                        duration_sec=dur,
                        prompt_tokens=pt,
                        completion_tokens=ct,
                        total_tokens=token_counts.get("total_tokens", pt + ct),
                        estimated_cost=cost,
                        success=True,
                        fallback_used=(attempt_idx > 0),
                        fallback_reason=str(last_error) if attempt_idx > 0 else None,
                    )
                    self._record_usage(metric)
                    return resp_text, metric

                except Exception as exc:
                    last_error = exc
                    logger.warning(f"Provider {p_id} failed on task {t_str} (attempt {retry_i+1}/{max_retries+1}): {exc}")
                    if retry_i < max_retries:
                        time.sleep(0.5 * (2 ** retry_i))  # Exponential backoff

        # All attempts failed; fall back directly to deterministic provider
        logger.error(f"All configured providers failed for task {t_str}. Using local deterministic engine.")
        local_prov = self.providers["local_deterministic"]
        t0 = time.time()
        resp_text, token_counts = local_prov.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=json_mode,
        )
        metric = ModelUsageMetric(
            task=t_str,
            provider="local_deterministic",
            model="rule_based_engine",
            duration_sec=time.time() - t0,
            success=True,
            fallback_used=True,
            fallback_reason=f"All remote providers failed: {last_error}",
        )
        self._record_usage(metric)
        return resp_text, metric

    @staticmethod
    def _repair_json_output(raw_text: str) -> str:
        """Strip markdown fences, trailing commas, and parse JSON safely."""
        clean = raw_text.strip()
        # Remove ```json ... ``` markdown wraps
        if clean.startswith("```"):
            clean = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", clean)
            clean = re.sub(r"\s*```$", "", clean).strip()

        # Try direct parse
        try:
            json.loads(clean)
            return clean
        except Exception:
            pass

        # Try extracting outermost { ... } or [ ... ]
        m = re.search(r"(\{.*\}|\[.*\])", clean, re.DOTALL)
        if m:
            candidate = m.group(1).strip()
            # Remove trailing commas before } or ]
            candidate = re.sub(r",\s*([\}\]])", r"\1", candidate)
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                pass

        # If still invalid, wrap in a safe JSON error dictionary
        safe_fallback = {
            "status": "repaired_fallback",
            "raw_output": clean,
            "visual_intent": "Narrative illustration of speech topic",
            "search_queries": ["cinematic visual"],
        }
        return json.dumps(safe_fallback)

    def _record_usage(self, metric: ModelUsageMetric):
        """Append metric to usage.jsonl."""
        try:
            with open(USAGE_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(metric.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug(f"Failed to record usage metric: {e}")

    def get_status_overview(self) -> Dict[str, Any]:
        """Return provider statuses and configured tasks for UI & diagnostics."""
        prov_list = []
        for p_id, p in self.providers.items():
            prov_list.append({
                "id": p_id,
                "name": p.name,
                "configured": p.is_configured(),
                "supports_vision": p.capabilities.supports_vision,
                "supports_structured_output": p.capabilities.supports_structured_output,
                "default_model": getattr(p, "default_model", "default"),
                "context_window": p.capabilities.context_window,
            })
        return {
            "providers": prov_list,
            "routing": self.task_routing,
            "tasks": [t.value for t in TaskType],
            "vault_active": (sys.platform == "win32"),
        }


# Global singleton access
gateway = AIGateway()
