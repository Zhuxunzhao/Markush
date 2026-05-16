"""Helpers for request-scoped LLM configuration."""

from __future__ import annotations

import copy
from typing import Optional


def _model_candidates(model_or_profile: str) -> list[str]:
    raw = str(model_or_profile or "").strip()
    lowered = raw.lower().replace("_", "-")
    candidates = [raw, lowered]
    if lowered in {"glm5.1", "glm5-1", "glm-5.1"}:
        candidates.extend(["glm5.1", "glm-5.1"])
    if lowered in {
        "3.6plus",
        "3.6-plus",
        "qwen3.6plus",
        "qwen3.6-plus",
        "qwen-3.6plus",
        "qwen-3.6-plus",
    }:
        candidates.extend(
            ["qwen3.6-plus", "qwen-3.6plus", "qwen3.6plus", "qwen-3.6-plus"]
        )
    if lowered in {"qwen-max", "qwenmax"}:
        candidates.extend(["qwen-max", "qwen_max"])
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _canonical_model_name(model_or_profile: str) -> str:
    lowered = str(model_or_profile or "").strip().lower().replace("_", "-")
    if lowered in {"glm5.1", "glm5-1", "glm-5.1"}:
        return "glm-5.1"
    if lowered in {
        "3.6plus",
        "3.6-plus",
        "qwen3.6plus",
        "qwen3.6-plus",
        "qwen-3.6plus",
        "qwen-3.6-plus",
    }:
        return "qwen3.6-plus"
    if lowered in {"qwenmax", "qwen-max"}:
        return "qwen-max"
    return str(model_or_profile).strip()


def build_llm_config(
    config: dict,
    *,
    pipeline_key: Optional[str] = None,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_api_key_env: Optional[str] = None,
    llm_request_timeout: Optional[float] = None,
    llm_max_tokens: Optional[int] = None,
    llm_temperature: Optional[float] = None,
    llm_token_limit_param: Optional[str] = None,
    llm_omit_temperature: Optional[bool] = None,
    llm_reasoning_effort: Optional[str] = None,
    llm_verbosity: Optional[str] = None,
) -> dict:
    """Return a deep-copied config with temporary LLM overrides applied.

    ``llm_api_key`` is intended for request-scoped Web usage. Callers should not
    persist the returned config or expose it through job snapshots.
    """

    resolved = copy.deepcopy(config)
    pipe_cfg = resolved.get("pipelines", {}).get(pipeline_key or "", {})
    model_or_profile = llm_model or pipe_cfg.get("llm_model")
    llm_cfg = resolved.setdefault("llm", {})

    if model_or_profile:
        profiles = resolved.get("llm_profiles", {})
        profile = None
        for candidate in _model_candidates(model_or_profile):
            if candidate in profiles:
                profile = profiles[candidate]
                break
        if profile:
            llm_cfg.update(profile)
        else:
            llm_cfg["model"] = _canonical_model_name(model_or_profile)

    if llm_provider:
        llm_cfg["provider"] = llm_provider
    if llm_base_url:
        llm_cfg["base_url"] = llm_base_url
    if llm_api_key_env:
        llm_cfg["api_key_env"] = llm_api_key_env
    if llm_api_key:
        llm_cfg["api_key"] = llm_api_key
    if llm_request_timeout is not None:
        llm_cfg["request_timeout"] = llm_request_timeout
    if llm_max_tokens is not None:
        llm_cfg["max_tokens"] = llm_max_tokens
    if llm_temperature is not None:
        llm_cfg["temperature"] = llm_temperature
    if llm_token_limit_param:
        llm_cfg["token_limit_param"] = llm_token_limit_param
    if llm_omit_temperature is not None:
        llm_cfg["omit_temperature"] = llm_omit_temperature
    if llm_reasoning_effort:
        llm_cfg["reasoning_effort"] = llm_reasoning_effort
    if llm_verbosity:
        llm_cfg["verbosity"] = llm_verbosity

    return resolved
