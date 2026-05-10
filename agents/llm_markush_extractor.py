"""LLM-based Markush extraction agent.

This agent replaces the image -> MarkushGrapher step in the LLM-only
infringement workflow. It can use the first patent image plus claim text, but
it deliberately returns a conservative textual fallback when an exact
MarkushGrapher-style caption cannot be recovered.
"""

from __future__ import annotations

from typing import Any, Optional

from agents.base import BaseAgent, MARKUSH_STRING_DEFINITION
from schemas.types import MarkushStructure, PatentDocument


class LLMMarkushExtractorAgent(BaseAgent):
    @property
    def system_prompt(self) -> str:
        return f"""你是一名化学专利 Markush 结构识别专家。
你的任务是复现 MarkushGrapher 的作用：从专利图片和权利要求文本中提取主 Markush 结构。

{MARKUSH_STRING_DEFINITION}

要求：
- 优先识别保护范围最宽的主 Markush 通式，通常来自第一张结构图或独立权利要求。
- 如果可以可靠写成 MarkushGrapher/RDKit caption，输出到 markush_caption。
- 如果无法可靠写出带原子索引的 caption，不要编造索引；请在 markush_caption 中输出紧凑的文本化 Markush 描述，包含通式、连接点、变量标签和变量定义。
- substituent_table 应尽量把 R/X/Y/Z 等变量映射到中文或英文约束描述。
- score 是 0 到 1 的可靠性分数；图片和权利要求一致时更高。
- 对无法确认的结构保持保守，is_markush=false 且 markush_caption 为空字符串。

只返回合法 JSON：
- "is_markush": boolean
- "markush_caption": string
- "cxsmiles": string
- "substituent_table": object
- "structure_summary": string
- "score": number
"""

    def build_user_prompt(self, **kwargs) -> str:
        patent: PatentDocument = kwargs["patent"]
        target_smiles = kwargs.get("target_smiles", "")
        image_path = kwargs.get("image_path")

        image_note = (
            f"已随请求附上本地第一张专利图片: {image_path}"
            if image_path
            else "未提供可用图片，请只基于文本提取主 Markush 结构。"
        )
        description = patent.description_text or patent.full_text
        abstract_limit = 2000 if image_path else 8000
        description_limit = 4000 if image_path else 20000

        return f"""## 专利号
{patent.patent_id}

## 查询分子 SMILES（仅用于判断哪个通式最相关，不要直接据此改写 Markush）
`{target_smiles}`

## 图片
{image_note}

## 权利要求文本
```
{self.truncate(patent.claims_text)}
```

## 摘要
```
{self.truncate(patent.abstract_text, max_chars=abstract_limit)}
```

## 说明书片段
```
{self.truncate(description, max_chars=description_limit)}
```

请提取主 Markush 结构，并按指定 JSON schema 返回。"""

    def run(
        self,
        *,
        patent: PatentDocument,
        target_smiles: str,
        image_path: Optional[str] = None,
    ) -> MarkushStructure:
        user_prompt = self.build_user_prompt(
            patent=patent,
            target_smiles=target_smiles,
            image_path=image_path,
        )
        image_paths = [image_path] if image_path else []
        self.last_llm_response = self.llm.chat_with_images(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            image_paths=image_paths,
            response_format={"type": "json_object"},
            max_tokens=self.max_tokens,
        )
        result = self.parse_response(self.last_llm_response)
        result.source_image_path = image_path or ""
        return result

    def parse_response(self, response: dict[str, Any]) -> MarkushStructure:
        table = response.get("substituent_table", {})
        if not isinstance(table, dict):
            table = {}

        caption = str(
            response.get("markush_caption")
            or response.get("caption")
            or response.get("structure_summary")
            or ""
        ).strip()
        cxsmiles = str(response.get("cxsmiles") or "").strip()
        score = _coerce_score(response.get("score", 0.0))
        is_markush = bool(response.get("is_markush", bool(caption or cxsmiles)))

        return MarkushStructure(
            cxsmiles=cxsmiles,
            substituent_table={str(key): str(value) for key, value in table.items()},
            caption=caption,
            score=score,
            is_markush=is_markush,
        )


def _coerce_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if score > 1.0 and score <= 100.0:
        score = score / 100.0
    return max(0.0, min(1.0, score))
