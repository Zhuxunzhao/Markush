"""LLM API 统一封装 — 支持 OpenAI / Anthropic / Google

Features:
- Unified chat interface across providers
- Automatic JSON extraction from responses
- Retry with exponential backoff
- Temperature control
"""

from __future__ import annotations
import base64
import mimetypes
import os
import json
import time
import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger("markush.llm")

DEFAULT_OUTPUT_LANGUAGE_INSTRUCTION = """输出语言要求：
- 所有面向人类阅读的自然语言内容必须使用简体中文。
- JSON key、枚举值、专利号、SMILES/CXSMILES、化学式和代码式标识符必须严格保持 schema 或输入要求的原样。
- 对 JSON 输出，只翻译解释、报告、摘要、推理、风险、建议等自然语言字段值；不要翻译机器字段名。
- 当要求输出 JSON 时，只返回合法 JSON，不要输出 Markdown 代码块或额外说明。
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
        self.token_limit_param = str(
            llm_cfg.get("token_limit_param") or self._default_token_limit_param(self.model)
        ).strip()
        self.omit_temperature = bool(llm_cfg.get("omit_temperature", False))
        self.reasoning_effort = str(llm_cfg.get("reasoning_effort") or "").strip() or None
        self.verbosity = str(llm_cfg.get("verbosity") or "").strip() or None
        self.request_timeout = llm_cfg.get("request_timeout", 120)
        self.max_retries = int(llm_cfg.get("max_retries", 2))
        self.output_language_instruction = llm_cfg.get(
            "output_language_instruction",
            DEFAULT_OUTPUT_LANGUAGE_INSTRUCTION,
        ).strip()
        api_key_env = llm_cfg.get("api_key_env", "OPENAI_API_KEY")
        api_key = str(llm_cfg.get("api_key") or "").strip()
        if not api_key:
            api_key = os.environ.get(api_key_env, "")
        if not api_key:
            raise RuntimeError(
                f"API key not found in request config or env var: {api_key_env}"
            )
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
            kwargs: dict = {"api_key": api_key, "timeout": self.request_timeout}
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
        response_format: Optional[Any] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        max_retries: Optional[int] = None,
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
        max_retries = self.max_retries if max_retries is None else max_retries
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
                error_message = self._format_exception(e)
                wait = 2 ** attempt  # 1 s, 2 s, 4 s …
                error_message = self._format_exception(e)
                logger.warning(
                    f"LLM call failed (attempt {attempt + 1}/{max_retries}): {error_message}"
                )
                if attempt < max_retries - 1:
                    time.sleep(wait)

        raise RuntimeError(
            f"LLM call failed after {max_retries} retries: "
            f"{self._format_exception(last_error)}"
        )

    def chat_with_images(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: Optional[list[str]] = None,
        response_format: Optional[Any] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        max_retries: Optional[int] = None,
        raw_text: bool = False,
    ) -> dict[str, Any] | str:
        """Chat with optional local images using OpenAI-compatible content blocks.

        GLM/Qwen deployments in this project use the OpenAI-compatible API, so
        this method intentionally keeps multimodal support on that backend. If
        no images are supplied, it falls back to the regular text-only chat path.
        """
        images = [path for path in (image_paths or []) if path]
        if not images:
            return self.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_format=response_format,
                max_tokens=max_tokens,
                temperature=temperature,
                max_retries=max_retries,
                raw_text=raw_text,
            )
        if self.provider != "openai":
            raise ValueError(
                "chat_with_images currently supports the openai provider only"
            )

        temp = temperature if temperature is not None else self.temperature
        token_limit = max_tokens if max_tokens is not None else self.max_tokens
        max_retries = self.max_retries if max_retries is None else max_retries
        system_prompt = self._apply_output_language_instruction(system_prompt)
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                text = self._chat_openai_multimodal(
                    system_prompt,
                    user_prompt,
                    images,
                    response_format,
                    token_limit,
                    temp,
                )
                if raw_text:
                    return text
                return self._parse_json(text)
            except Exception as e:
                last_error = e
                wait = 2 ** attempt
                error_message = self._format_exception(e)
                logger.warning(
                    f"LLM multimodal call failed (attempt {attempt + 1}/{max_retries}): {error_message}"
                )
                if attempt < max_retries - 1:
                    time.sleep(wait)

        raise RuntimeError(
            f"LLM multimodal call failed after {max_retries} retries: "
            f"{self._format_exception(last_error)}"
        )

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
        response_format: Optional[Any],
        max_tokens: int,
        temperature: float,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        self._apply_openai_chat_tuning(kwargs, max_tokens=max_tokens, temperature=temperature)
        if response_format is not None:
            kwargs["response_format"] = response_format
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def _chat_openai_multimodal(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str],
        response_format: Optional[Any],
        max_tokens: int,
        temperature: float,
    ) -> str:
        content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        for image_path in image_paths:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._image_data_url(image_path)},
                }
            )

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
        }
        self._apply_openai_chat_tuning(kwargs, max_tokens=max_tokens, temperature=temperature)
        if response_format is not None:
            kwargs["response_format"] = response_format
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def _apply_openai_chat_tuning(
        self,
        kwargs: dict[str, Any],
        *,
        max_tokens: int,
        temperature: float,
    ) -> None:
        extra_body: dict[str, Any] = {}
        token_limit_param = self.token_limit_param
        if token_limit_param not in {"max_tokens", "max_completion_tokens"}:
            token_limit_param = self._default_token_limit_param(self.model)

        if token_limit_param == "max_completion_tokens":
            extra_body["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens

        if not self.omit_temperature:
            kwargs["temperature"] = temperature
        if self.reasoning_effort:
            extra_body["reasoning_effort"] = self.reasoning_effort
        if self.verbosity:
            extra_body["verbosity"] = self.verbosity
        if extra_body:
            kwargs["extra_body"] = extra_body

    @staticmethod
    def _default_token_limit_param(model: str) -> str:
        lowered = str(model or "").strip().lower().replace("_", "-")
        if lowered.startswith("gpt-5") or lowered.startswith(("o1", "o3", "o4")):
            return "max_completion_tokens"
        return "max_tokens"

    @staticmethod
    def _image_data_url(image_path: str) -> str:
        path = Path(image_path)
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{data}"

    @staticmethod
    def _format_exception(error: Optional[BaseException]) -> str:
        if error is None:
            return "unknown error"
        parts = [f"{error.__class__.__name__}: {error}"]
        cause = getattr(error, "__cause__", None)
        if cause is not None:
            parts.append(f"cause={cause.__class__.__name__}: {cause}")
        return " | ".join(parts)

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
