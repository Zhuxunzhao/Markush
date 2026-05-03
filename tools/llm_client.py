"""LLM API 统一封装 — 支持 OpenAI / Anthropic / Google

Features:
- Unified chat interface across providers
- Automatic JSON extraction from responses
- Retry with exponential backoff
- Temperature control
"""

from __future__ import annotations
import os
import json
import time
import logging
from typing import Any, Optional

import yaml

logger = logging.getLogger("markush.llm")

DEFAULT_OUTPUT_LANGUAGE_INSTRUCTION = """Output language requirements:
- All human-readable natural-language values in your response must be Simplified Chinese.
- Keep JSON object keys, enum values, patent IDs, SMILES/CXSMILES, chemical formulas, and code-like identifiers exactly as requested by the schema or input.
- For JSON outputs, only translate the string/list/dict values that are explanations, reports, summaries, reasoning, risks, suggestions, or other prose.
- When JSON is requested, return valid JSON only.
"""


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class LLMClient:
    """统一的 LLM 调用接口，屏蔽不同 provider 的差异"""

    def __init__(self, config: Optional[dict] = None):
        if config is None:
            config = load_config()
        llm_cfg = config["llm"]
        self.provider = llm_cfg["provider"]
        self.model = llm_cfg["model"]
        self.max_tokens = llm_cfg.get("max_tokens", 96000)
        self.temperature = llm_cfg.get("temperature", 0.1)
        self.output_language_instruction = llm_cfg.get(
            "output_language_instruction",
            DEFAULT_OUTPUT_LANGUAGE_INSTRUCTION,
        ).strip()
        api_key = os.environ.get(llm_cfg["api_key_env"], "")
        if not api_key:
            logger.warning(f"API key not found in env var: {llm_cfg['api_key_env']}")
        # base_url: explicit config value, then OPENAI_API_BASE env var (DashScope compat)
        self.base_url = (
            llm_cfg.get("base_url")
            or os.environ.get("OPENAI_API_BASE")
            or os.environ.get("OPENAI_BASE_URL")
        )
        self._client = self._init_client(api_key)

    def _init_client(self, api_key: str):
        if self.provider == "openai":
            from openai import OpenAI
            kwargs: dict = {"api_key": api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            return OpenAI(**kwargs)
        elif self.provider == "anthropic":
            from anthropic import Anthropic
            return Anthropic(api_key=api_key)
        elif self.provider == "google":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            return genai
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[type] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        max_retries: int = 3,
        raw_text: bool = False,
    ) -> dict[str, Any] | str:
        """统一聊天接口

        Args:
            system_prompt: System role prompt
            user_prompt: User message
            response_format: OpenAI structured output format class
            max_tokens: Max response tokens
            temperature: Override default temperature (falls back to config value)
            max_retries: Number of retries on failure (exponential backoff: 1s, 2s, 4s…)
            raw_text: If True, return raw text instead of parsed JSON

        Returns:
            Parsed dict (or raw string if raw_text=True)
        """
        temp = temperature if temperature is not None else self.temperature
        token_limit = max_tokens if max_tokens is not None else self.max_tokens
        system_prompt = self._apply_output_language_instruction(system_prompt)
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                if self.provider == "openai":
                    text = self._chat_openai(system_prompt, user_prompt, response_format, token_limit, temp)
                elif self.provider == "anthropic":
                    text = self._chat_anthropic(system_prompt, user_prompt, token_limit, temp)
                elif self.provider == "google":
                    text = self._chat_google(system_prompt, user_prompt, token_limit, temp)
                else:
                    raise ValueError(f"Unsupported LLM provider: {self.provider}")

                if raw_text:
                    return text
                return self._parse_json(text)

            except Exception as e:
                last_error = e
                wait = 2 ** attempt  # 1 s, 2 s, 4 s …
                logger.warning(
                    f"LLM call failed (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt < max_retries - 1:
                    time.sleep(wait)

        raise RuntimeError(f"LLM call failed after {max_retries} retries: {last_error}")

    def _apply_output_language_instruction(self, system_prompt: str) -> str:
        if not self.output_language_instruction:
            return system_prompt
        if self.output_language_instruction in system_prompt:
            return system_prompt
        return f"{system_prompt.rstrip()}\n\n{self.output_language_instruction}"

    # ------------------------------------------------------------------
    # Provider-specific backends (return raw text string)
    # ------------------------------------------------------------------

    def _chat_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[type],
        max_tokens: int,
        temperature: float,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def _chat_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        response = self._client.messages.create(
            model=self.model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.content[0].text

    def _chat_google(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        model = self._client.GenerativeModel(
            self.model,
            system_instruction=system_prompt,
            generation_config={
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        response = model.generate_content(user_prompt)
        return response.text

    # ------------------------------------------------------------------
    # JSON extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(text: str) -> dict:
        """尝试从 LLM 输出中提取 JSON，支持多种格式

        策略（按优先级）：
        1. 直接 json.loads
        2. 提取 ```json … ``` 代码块
        3. 提取 ``` … ``` 代码块（跳过可选的语言标签行）
        4. 提取最外层 { … }
        5. Fallback — 返回 {"raw_text": …}
        """
        text = text.strip()

        # strict=False allows raw control chars (unescaped newlines, tabs) inside
        # JSON string values — some LLMs (notably Qwen/DashScope) emit literal
        # newlines inside long "reasoning" fields, which fails strict json.loads.

        # 1. 直接解析
        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError:
            pass

        # 2. 提取 ```json ... ``` 块
        if "```json" in text:
            try:
                start = text.index("```json") + 7
                end = text.index("```", start)
                return json.loads(text[start:end].strip(), strict=False)
            except (ValueError, json.JSONDecodeError):
                pass

        # 3. 提取 ``` ... ``` 块（跳过可选的语言标签行）
        if "```" in text:
            try:
                start = text.index("```") + 3
                newline = text.index("\n", start)
                start = newline + 1
                end = text.index("```", start)
                return json.loads(text[start:end].strip(), strict=False)
            except (ValueError, json.JSONDecodeError):
                pass

        # 4. 提取最外层 { ... }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end], strict=False)
            except json.JSONDecodeError:
                pass

        # 5. Fallback
        logger.warning("Failed to parse JSON from LLM response, returning raw text")
        return {"raw_text": text}
