#!/usr/bin/env python3
"""
credentials_manager.py — Secure Server-Side Credential & AI Provider Store.

Security Guarantees:
  1. Secrets are NEVER returned over API or rendered into client-side templates.
  2. Keys are masked (e.g. sk-••••••••••••9F2A) whenever returned for display.
  3. Credentials are saved directly to local .env and updated in os.environ without shell exposure.
  4. Real-time connectivity and status tracking (CONNECTED, NOT_CONFIGURED, AUTH_ERROR, etc.).
"""

import os
import re
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("rendering_studio.credentials")

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"

# Status Constants
STATUS_NOT_CONFIGURED = "NOT CONFIGURED"
STATUS_CONFIGURED = "CONFIGURED"
STATUS_CONNECTED = "CONNECTED"
STATUS_AUTH_ERROR = "AUTH ERROR"
STATUS_RATE_LIMITED = "RATE LIMITED"
STATUS_NETWORK_ERROR = "NETWORK ERROR"
STATUS_MODEL_ERROR = "MODEL ERROR"
STATUS_ERROR = "ERROR"
STATUS_LOCAL = "LOCAL"

# Provider Specifications
PROVIDER_SPECS: Dict[str, Dict[str, Any]] = {
    "deepgram": {
        "id": "deepgram",
        "name": "Deepgram",
        "category": "stt",
        "purpose": "Speech-to-Text / Word Timestamps",
        "env_key": "DEEPGRAM_API_KEY",
        "model_env_key": "DEEPGRAM_MODEL",
        "default_model": "nova-3",
        "models": [
            {"id": "nova-3", "name": "Nova-3 (Latest 2026 Recommended)", "tag": "Fastest & Highest Accuracy"},
            {"id": "nova-2", "name": "Nova-2", "tag": "Legacy Stable"},
            {"id": "enhanced", "name": "Enhanced", "tag": "General Audio"},
            {"id": "base", "name": "Base", "tag": "Economical"}
        ],
        "doc_url": "https://developers.deepgram.com"
    },
    "groq": {
        "id": "groq",
        "name": "Groq",
        "category": "llm",
        "purpose": "Ultra-Low Latency Inference",
        "env_key": "GROQ_API_KEY",
        "model_env_key": "GROQ_MODEL",
        "default_model": "qwen/qwen3.8-27b",
        "models": [
            {"id": "qwen/qwen3.8-27b", "name": "Qwen 3.8 27B", "tag": "Active & High Accuracy"},
            {"id": "openai/gpt-oss-120b", "name": "GPT-OSS 120B", "tag": "High Capability"},
            {"id": "openai/gpt-oss-20b", "name": "GPT-OSS 20B", "tag": "Fast & Lightweight"},
            {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B Versatile", "tag": "Llama 3.3 Tier"},
            {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B Instant", "tag": "Sub-200ms Latency"}
        ],
        "doc_url": "https://console.groq.com"
    },
    "gemini": {
        "id": "gemini",
        "name": "Google Gemini",
        "category": "llm",
        "purpose": "Multilingual & Multimodal Reasoning",
        "env_key": "GEMINI_API_KEY",
        "model_env_key": "GEMINI_MODEL",
        "default_model": "gemini-2.0-flash",
        "models": [
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "tag": "Next-Gen Flash"},
            {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "tag": "High Throughput"},
            {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "tag": "Deep Reasoning"}
        ],
        "doc_url": "https://aistudio.google.com"
    },
    "openrouter": {
        "id": "openrouter",
        "name": "OpenRouter",
        "category": "llm",
        "purpose": "Universal AI Gateway",
        "env_key": "OPENROUTER_API_KEY",
        "model_env_key": "OPENROUTER_MODEL",
        "default_model": "google/gemini-2.0-flash-001",
        "models": [
            {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash (OpenRouter)", "tag": "Economical"},
            {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet", "tag": "Elite Nuance"},
            {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B Instruct", "tag": "Open Weights"},
            {"id": "mistralai/mistral-large-2407", "name": "Mistral Large", "tag": "Multilingual"}
        ],
        "doc_url": "https://openrouter.ai"
    },
    "claude": {
        "id": "claude",
        "name": "Anthropic Claude",
        "category": "llm",
        "purpose": "Elite Style & Human-like Editing",
        "env_key": "ANTHROPIC_API_KEY",
        "model_env_key": "ANTHROPIC_MODEL",
        "default_model": "claude-3-5-haiku-20241022",
        "models": [
            {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "tag": "High Speed / Cost-Effective"},
            {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "tag": "Peak Quality"},
            {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "tag": "Complex Reasoning"}
        ],
        "doc_url": "https://console.anthropic.com"
    },
    "openai": {
        "id": "openai",
        "name": "OpenAI",
        "category": "llm",
        "purpose": "Strict JSON Conformance & Precision",
        "env_key": "OPENAI_API_KEY",
        "model_env_key": "OPENAI_MODEL",
        "default_model": "gpt-4o-mini",
        "models": [
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "tag": "Fast & High Quality"},
            {"id": "gpt-4o", "name": "GPT-4o", "tag": "Flagship Multimodal"},
            {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "tag": "Production Tested"},
            {"id": "o1-mini", "name": "o1-mini", "tag": "Reasoning Specialist"}
        ],
        "doc_url": "https://platform.openai.com"
    },
    "kimi": {
        "id": "kimi",
        "name": "Kimi (Moonshot)",
        "category": "llm",
        "purpose": "Long Context & Asian Linguistic Nuance",
        "env_key": "MOONSHOT_API_KEY",
        "alt_env_keys": ["KIMI_API_KEY"],
        "model_env_key": "KIMI_MODEL",
        "default_model": "moonshot-v1-8k",
        "models": [
            {"id": "moonshot-v1-8k", "name": "Moonshot v1 8k", "tag": "Standard"},
            {"id": "moonshot-v1-32k", "name": "Moonshot v1 32k", "tag": "Medium Context"},
            {"id": "moonshot-v1-128k", "name": "Moonshot v1 128k", "tag": "Long Context"}
        ],
        "doc_url": "https://platform.moonshot.cn"
    },
    "deepseek": {
        "id": "deepseek",
        "name": "DeepSeek",
        "category": "llm",
        "purpose": "Economical Open Intelligence",
        "env_key": "DEEPSEEK_API_KEY",
        "model_env_key": "DEEPSEEK_MODEL",
        "default_model": "deepseek-chat",
        "models": [
            {"id": "deepseek-chat", "name": "DeepSeek Chat (V3)", "tag": "General Reasoning"},
            {"id": "deepseek-coder", "name": "DeepSeek Coder", "tag": "Structured Syntax"}
        ],
        "doc_url": "https://platform.deepseek.com"
    },
    "local_deterministic": {
        "id": "local_deterministic",
        "name": "Local Deterministic",
        "category": "local",
        "purpose": "100% Offline Rule-Based NLP",
        "env_key": None,
        "model_env_key": None,
        "default_model": "rule_based_engine",
        "models": [
            {"id": "rule_based_engine", "name": "Rule-Based Heuristic NLP", "tag": "Zero Latency / Offline"}
        ],
        "doc_url": ""
    }
}

# In-memory status cache for connection metadata
PROVIDER_STATUS_CACHE: Dict[str, Dict[str, Any]] = {}


def load_dotenv():
    """Load key-value pairs from .env into os.environ if file exists."""
    if not ENV_PATH.exists():
        return
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                clean = line.strip()
                if not clean or clean.startswith("#") or "=" not in clean:
                    continue
                k, v = clean.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and v and k not in os.environ:
                    os.environ[k] = v
    except Exception as e:
        logger.warning(f"Failed to read .env: {e}")


def mask_key(raw_key: Optional[str]) -> str:
    """Mask key securely (e.g. sk-••••••••••••9F2A). Never returns full key."""
    if not raw_key:
        return ""
    clean = raw_key.strip()
    if len(clean) <= 6:
        return "•" * len(clean)
    prefix = clean[:3]
    suffix = clean[-4:]
    return f"{prefix}••••••••••••{suffix}"


def get_stored_key(provider_id: str) -> str:
    """Retrieve raw key from environment without exposing it to callers."""
    spec = PROVIDER_SPECS.get(provider_id)
    if not spec or not spec.get("env_key"):
        return ""
    
    # Check primary env key
    key = os.environ.get(spec["env_key"], "").strip()
    if key:
        return key
        
    # Check alternate keys if defined
    for alt in spec.get("alt_env_keys", []):
        k = os.environ.get(alt, "").strip()
        if k:
            return k
    return ""


def get_stored_model(provider_id: str) -> str:
    """Retrieve stored model from environment or default."""
    spec = PROVIDER_SPECS.get(provider_id)
    if not spec:
        return ""
    m_env = spec.get("model_env_key")
    if m_env and os.environ.get(m_env):
        return os.environ[m_env].strip()
    return spec.get("default_model", "")


def save_credential(provider_id: str, api_key: str, model: Optional[str] = None) -> Dict[str, Any]:
    """
    Save API key and selected model securely to .env and os.environ.
    Validates key formatting, ensures no shell injection, and updates registry instances.
    """
    spec = PROVIDER_SPECS.get(provider_id)
    if not spec or not spec.get("env_key"):
        return {"status": "error", "message": f"Invalid or non-configurable provider '{provider_id}'"}

    clean_key = (api_key or "").strip()
    if not clean_key:
        return {"status": "error", "message": "API key cannot be empty."}

    # Validate against illegal characters in env values
    if any(c in clean_key for c in ["\r", "\n", "\0"]):
        return {"status": "error", "message": "Invalid characters in API key."}

    env_key = spec["env_key"]
    model_key = spec.get("model_env_key")
    chosen_model = (model or spec.get("default_model", "")).strip()

    # Update in-memory os.environ
    os.environ[env_key] = clean_key
    if model_key and chosen_model:
        os.environ[model_key] = chosen_model

    # Persist cleanly to .env
    existing_lines = []
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    keys_to_update = {env_key: clean_key}
    if model_key and chosen_model:
        keys_to_update[model_key] = chosen_model

    new_lines = []
    found_keys = set()
    for line in existing_lines:
        match = re.match(r"^([A-Za-z0-9_]+)\s*=", line.strip())
        if match:
            k = match.group(1)
            if k in keys_to_update:
                new_lines.append(f"{k}={keys_to_update[k]}\n")
                found_keys.add(k)
                continue
        new_lines.append(line)

    for k, v in keys_to_update.items():
        if k not in found_keys:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{k}={v}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    # Sync into living provider registry instances
    sync_provider_instance(provider_id, clean_key, chosen_model)

    # Invalidate status cache
    PROVIDER_STATUS_CACHE[provider_id] = {
        "status": STATUS_CONFIGURED,
        "last_tested": "Not tested yet",
        "latency_ms": None,
        "model": chosen_model
    }

    return {
        "status": "success",
        "success": True,
        "provider": provider_id,
        "name": spec["name"],
        "masked_key": mask_key(clean_key),
        "model": chosen_model,
        "message": f"Successfully saved credentials for {spec['name']}."
    }


def delete_credential(provider_id: str) -> Dict[str, Any]:
    """Delete credential from .env, os.environ, and reset in-memory provider."""
    spec = PROVIDER_SPECS.get(provider_id)
    if not spec or not spec.get("env_key"):
        return {"status": "error", "success": False, "message": f"Invalid provider '{provider_id}'"}

    env_key = spec["env_key"]
    if env_key in os.environ:
        del os.environ[env_key]

    for alt in spec.get("alt_env_keys", []):
        if alt in os.environ:
            del os.environ[alt]

    # Remove from .env file
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = [l for l in lines if not re.match(rf"^{env_key}\s*=", l.strip())]
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    sync_provider_instance(provider_id, "", spec.get("default_model", ""))
    PROVIDER_STATUS_CACHE[provider_id] = {
        "status": STATUS_NOT_CONFIGURED,
        "last_tested": "Cleared",
        "latency_ms": None,
        "model": spec.get("default_model", "")
    }

    return {
        "status": "success",
        "success": True,
        "provider": provider_id,
        "message": f"Credentials cleared for {spec['name']}."
    }


def sync_provider_instance(provider_id: str, api_key: str, model: str):
    """Update running singleton in STT_PROVIDER_REGISTRY or LLM_PROVIDER_REGISTRY."""
    spec = PROVIDER_SPECS.get(provider_id)
    if not spec:
        return

    if spec["category"] == "stt":
        from engine.stt_provider import STT_PROVIDER_REGISTRY
        inst = STT_PROVIDER_REGISTRY.get(provider_id)
        if inst:
            inst.api_key = api_key
            inst.model = model
    else:
        from engine.llm_provider import LLM_PROVIDER_REGISTRY
        inst = LLM_PROVIDER_REGISTRY.get(provider_id)
        if inst:
            inst.api_key = api_key
            inst.model = model


def test_provider_connection(provider_id: str, api_key: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute a real, live HTTP connectivity test against the provider endpoint.
    Measures latency, validates HTTP response, parses model availability,
    and returns a sanitized report without leaking tokens.
    """
    spec = PROVIDER_SPECS.get(provider_id)
    if not spec:
        return {"status": "error", "message": f"Unknown provider '{provider_id}'"}

    if provider_id == "local_deterministic":
        return {
            "provider": provider_id,
            "name": spec["name"],
            "status": STATUS_LOCAL,
            "latency_ms": 0.1,
            "model": "rule_based_engine",
            "message": "Local deterministic engine is ready and 100% offline."
        }

    key = (api_key or get_stored_key(provider_id)).strip()
    if not key:
        status_res = {
            "provider": provider_id,
            "name": spec["name"],
            "status": STATUS_NOT_CONFIGURED,
            "latency_ms": None,
            "model": model or get_stored_model(provider_id),
            "message": f"API key required for {spec['name']}."
        }
        PROVIDER_STATUS_CACHE[provider_id] = status_res
        return status_res

    chosen_model = model or get_stored_model(provider_id)

    # Dispatch to provider's native test_connection
    if spec["category"] == "stt":
        from engine.stt_provider import STT_PROVIDER_REGISTRY
        inst = STT_PROVIDER_REGISTRY.get(provider_id)
        if not inst:
            return {"status": "error", "message": f"STT provider '{provider_id}' not loaded"}
        
        orig_key = getattr(inst, "api_key", "")
        orig_model = getattr(inst, "model", "")
        try:
            inst.api_key = key
            inst.model = chosen_model
            res = inst.test_connection()
        finally:
            if api_key:
                inst.api_key = orig_key
                inst.model = orig_model
    else:
        from engine.llm_provider import LLM_PROVIDER_REGISTRY
        inst = LLM_PROVIDER_REGISTRY.get(provider_id)
        if not inst:
            return {"status": "error", "message": f"LLM provider '{provider_id}' not loaded"}

        orig_key = getattr(inst, "api_key", "")
        orig_model = getattr(inst, "model", "")
        try:
            inst.api_key = key
            inst.model = chosen_model
            res = inst.test_connection()
        finally:
            if api_key:
                inst.api_key = orig_key
                inst.model = orig_model

    # Standardize result and cache
    raw_status = res.get("status", "ERROR").upper()
    if raw_status in ["CONNECTED", "AVAILABLE"]:
        final_status = STATUS_CONNECTED
        msg = f"Connected successfully to {spec['name']} ({res.get('latency_ms', 0)} ms)."
    elif raw_status == "AUTH_ERROR" or res.get("http_code") in [401, 403]:
        final_status = STATUS_AUTH_ERROR
        msg = f"{spec['name']} rejected the API key (HTTP {res.get('http_code', 401)}). Please verify your credential."
    elif raw_status == "RATE_LIMITED" or res.get("http_code") == 429:
        final_status = STATUS_RATE_LIMITED
        msg = f"{spec['name']} rate-limit or quota exceeded. Please check your provider account tier."
    elif raw_status in ["UNREACHABLE", "NETWORK_ERROR"]:
        final_status = STATUS_NETWORK_ERROR
        msg = f"Unable to reach {spec['name']} API endpoint. Please check your internet connection."
    elif raw_status == "MODEL_ERROR" or res.get("http_code") == 404:
        final_status = STATUS_MODEL_ERROR
        msg = f"Model '{chosen_model}' was not found or is unavailable on {spec['name']}."
    else:
        final_status = STATUS_ERROR
        msg = res.get("message") or f"Connection failed to {spec['name']}."

    cached_entry = {
        "provider": provider_id,
        "name": spec["name"],
        "status": final_status,
        "latency_ms": res.get("latency_ms"),
        "model": chosen_model,
        "last_tested": time.strftime("%d %b %Y, %H:%M:%S"),
        "message": msg
    }
    PROVIDER_STATUS_CACHE[provider_id] = cached_entry
    return cached_entry


def get_provider_info(provider_id: str) -> Dict[str, Any]:
    """Retrieve public card metadata for a single provider without exposing secrets."""
    spec = PROVIDER_SPECS.get(provider_id)
    if not spec:
        return {}

    raw_key = get_stored_key(provider_id)
    cached = PROVIDER_STATUS_CACHE.get(provider_id, {})

    if provider_id == "local_deterministic":
        status = STATUS_LOCAL
    elif not raw_key:
        status = STATUS_NOT_CONFIGURED
    else:
        status = cached.get("status", STATUS_CONFIGURED)

    icon_map = {
        "deepgram": "🎙️",
        "groq": "⚡",
        "gemini": "💎",
        "openrouter": "🌐",
        "claude": "🧠",
        "openai": "🤖",
        "kimi": "🌙",
        "deepseek": "🐋",
        "local_deterministic": "💻"
    }

    chosen_model = cached.get("model") or get_stored_model(provider_id) or spec.get("default_model", "")

    return {
        "id": spec["id"],
        "name": spec["name"],
        "category": spec["category"],
        "type": spec["category"],
        "purpose": spec["purpose"],
        "description": spec["purpose"],
        "icon": icon_map.get(provider_id, "🤖"),
        "env_var": spec.get("env_key", ""),
        "configured": bool(raw_key) or provider_id == "local_deterministic",
        "status": status,
        "masked_key": mask_key(raw_key),
        "model": chosen_model,
        "current_model": chosen_model,
        "default_model": spec.get("default_model", ""),
        "models": spec.get("models", []),
        "latency_ms": cached.get("latency_ms"),
        "last_tested": cached.get("last_tested", "Never"),
        "doc_url": spec.get("doc_url", ""),
        "last_error": cached.get("message", "") if status in [STATUS_AUTH_ERROR, STATUS_RATE_LIMITED, STATUS_NETWORK_ERROR, STATUS_MODEL_ERROR, STATUS_ERROR] else "",
        "message": cached.get("message", "")
    }


def get_all_providers_info() -> List[Dict[str, Any]]:
    """Retrieve cards for all registered providers in logical order."""
    order = ["deepgram", "groq", "gemini", "openrouter", "claude", "openai", "kimi", "deepseek", "local_deterministic"]
    return [get_provider_info(pid) for pid in order if pid in PROVIDER_SPECS]


def get_fallback_chain_status(primary_provider: Optional[str] = None) -> List[Dict[str, Any]]:
    """Expose the real active fallback chain with live configuration status."""
    primary = primary_provider or "auto"
    chain = []

    if primary != "auto" and primary in PROVIDER_SPECS:
        chain.append({
            "step": "Primary",
            "provider": primary,
            "name": PROVIDER_SPECS[primary]["name"],
            "configured": bool(get_stored_key(primary)) or primary == "local_deterministic",
            "status": PROVIDER_STATUS_CACHE.get(primary, {}).get("status", STATUS_CONFIGURED if get_stored_key(primary) else STATUS_NOT_CONFIGURED)
        })

    # Default fallback sequence
    default_order = ["groq", "gemini", "openrouter", "claude", "openai", "kimi", "deepseek"]
    step_num = 1
    for pid in default_order:
        if pid == primary:
            continue
        key_exists = bool(get_stored_key(pid))
        if key_exists or primary == "auto":
            chain.append({
                "step": f"Fallback {step_num}",
                "provider": pid,
                "name": PROVIDER_SPECS[pid]["name"],
                "configured": key_exists,
                "status": PROVIDER_STATUS_CACHE.get(pid, {}).get("status", STATUS_CONFIGURED if key_exists else STATUS_NOT_CONFIGURED)
            })
            step_num += 1

    # Final guarantee step
    chain.append({
        "step": "Final Fallback",
        "provider": "local_deterministic",
        "name": "Local Deterministic Engine",
        "configured": True,
        "status": STATUS_LOCAL
    })

    return chain


# Load environment on module import
load_dotenv()
