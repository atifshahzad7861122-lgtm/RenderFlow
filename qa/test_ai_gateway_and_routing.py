"""
qa/test_ai_gateway_and_routing.py
Comprehensive test suite for the Multi-Provider AI Gateway, DPAPI Credential Vault, and Task Routing.
"""
import pytest
import os
import json
from pathlib import Path
from engine.ai_gateway import (
    AIGateway,
    TaskType,
    dpapi_encrypt,
    dpapi_decrypt,
    USAGE_LOG_PATH
)


def test_dpapi_vault_encryption_decryption():
    test_key = "sk-test-secret-api-key-12345"
    
    # Encrypt secret string via Windows DPAPI
    encrypted = dpapi_encrypt(test_key)
    assert encrypted is not None
    assert isinstance(encrypted, bytes)
    assert len(encrypted) > 0
    
    # Decrypt secret
    decrypted = dpapi_decrypt(encrypted)
    assert decrypted == test_key


def test_ai_gateway_provider_registry():
    gateway = AIGateway()
    providers = gateway.providers
    
    assert "local_deterministic" in providers
    assert "openai" in providers
    assert "gemini" in providers
    assert "claude" in providers
    assert "openrouter" in providers
    assert "deepseek" in providers
    assert "groq" in providers
    assert "kimi" in providers
    
    # Deterministic engine is always configured and ready
    assert providers["local_deterministic"].is_configured() is True


def test_ai_gateway_task_routing_defaults():
    gateway = AIGateway()
    
    # Verify default route for scene planning
    primary, fallback = gateway.get_route(TaskType.SEMANTIC_SCENE_PLANNING)
    assert primary in gateway.providers
    assert fallback in gateway.providers
    
    # Verify search query generation route
    q_primary, q_fallback = gateway.get_route(TaskType.SEARCH_QUERY_GENERATION)
    assert q_primary == "groq"
    assert q_fallback == "gemini"


def test_ai_gateway_deterministic_execution():
    gateway = AIGateway()
    
    # Force task to run through local deterministic rule engine
    det_provider = gateway.providers["local_deterministic"]
    prompt = "In 1969, Apollo 11 landed on the lunar surface. Neil Armstrong stepped onto the moon."
    
    # 1. Text mode
    text, counts = det_provider.complete(system_prompt="Analyze scene", user_prompt=prompt, json_mode=False)
    assert "Deterministic narrative analysis" in text
    assert "Apollo" in text or "Neil" in text or "Armstrong" in text
    assert counts["total_tokens"] > 0
    
    # 2. JSON structured mode
    json_text, counts_j = det_provider.complete(system_prompt="Generate scene plan", user_prompt=prompt, json_mode=True)
    parsed = json.loads(json_text)
    assert parsed["status"] == "deterministic_fallback"
    assert "visual_intent" in parsed
    assert "search_queries" in parsed
    assert len(parsed["search_queries"]) > 0


def test_ai_gateway_set_credential():
    gateway = AIGateway()
    test_key = "test-sk-vault-verification"
    gateway.set_provider_credential("gemini", test_key)
    assert gateway.providers["gemini"].api_key == test_key
