"""LLM selector for the main Markush image in a patent document."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agents.base import BaseAgent
from schemas.types import PatentDocument, PatentImage


@dataclass
class MarkushImageSelection:
    """Result of judging one patent image as the main Markush structure."""

    image_index: int = -1
    image_path: str = ""
    is_markush: bool = False
    is_main_markush: bool = False
    score: float = 0.0
    image_role: str = ""
    reasoning: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)


class MarkushImageSelectorAgent(BaseAgent):
    """Scan patent images top-down and select the first main Markush image."""

    @property
    def system_prompt(self) -> str:
        return """你是一名化学专利附图筛选专家。
你的任务是按专利附图从上到下的顺序，判断当前图片是否是“满足主权利要求的主 Markush 通式结构”。

判断标准：
- 主 Markush 图通常是独立权利要求中的 Formula I / Formula (I) / general formula / compound of formula 等通式。
- 图中应包含可变取代基或可变连接点，例如 R1/R2/Ra/X/Y/Z、环变量、linker 变量等。
- 要结合权利要求文本判断它是否对应保护范围最宽、最核心的通式，而不是单个实施例、具体化合物、反应式、流程图、谱图、表格、晶型图或生物实验图。
- 若图片只是具体实施例结构，或者虽然有化学结构但不是主 Markush 通式，应返回 is_main_markush=false。
- 若证据不足，请保守返回 false，并解释原因。

只返回合法 JSON：
- "is_markush": boolean，当前图片是否为 Markush/通式类结构图
- "is_main_markush": boolean，当前图片是否为满足主权利要求的主 Markush 通式
- "score": number，0 到 1
- "image_role": string，例如 "main_markush_formula"、"specific_example"、"reaction_scheme"、"non_chemical_figure"、"uncertain"
- "reasoning": 中文简要说明
"""

    def build_user_prompt(self, **kwargs) -> str:
        patent: PatentDocument = kwargs["patent"]
        image_index = kwargs["image_index"]
        total_images = kwargs["total_images"]
        target_smiles = kwargs.get("target_smiles") or ""
        purpose = kwargs.get("purpose") or "infringement"

        target_note = (
            f"## 查询/拟评估分子 SMILES\n`{target_smiles}`\n\n"
            if target_smiles
            else ""
        )

        return f"""## 任务场景
{purpose}

## 专利号
{patent.patent_id}

## 当前图片顺序
第 {image_index} 张 / 共 {total_images} 张。
请只判断随附的这一张图片；外层流程会按从上到下顺序逐张调用你。

{target_note}## 权利要求文本
```
{self.truncate(patent.claims_text)}
```

## 摘要
```
{self.truncate(patent.abstract_text, max_chars=8000)}
```

请判断当前图片是否是满足主权利要求的主 Markush 通式结构。"""

    def evaluate_image(
        self,
        *,
        patent: PatentDocument,
        image: PatentImage,
        image_index: int,
        total_images: int,
        target_smiles: str = "",
        purpose: str = "infringement",
    ) -> MarkushImageSelection:
        user_prompt = self.build_user_prompt(
            patent=patent,
            image_index=image_index,
            total_images=total_images,
            target_smiles=target_smiles,
            purpose=purpose,
        )
        self.last_llm_response = self.llm.chat_with_images(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            image_paths=[image.path],
            response_format={"type": "json_object"},
            max_tokens=self.max_tokens,
        )
        selection = self.parse_response(self.last_llm_response)
        selection.image_index = image_index
        selection.image_path = image.path
        return selection

    def select_main_markush_image(
        self,
        *,
        patent: PatentDocument,
        target_smiles: str = "",
        purpose: str = "infringement",
        max_images: int = 60,
        min_score: float = 0.55,
        allow_candidate_fallback: bool = True,
    ) -> tuple[Optional[MarkushImageSelection], list[MarkushImageSelection]]:
        """Evaluate images in document order and return the first qualifying one."""

        usable_images = [image for image in patent.images if image.path]
        if not usable_images:
            return None, []

        max_images = max(1, int(max_images))
        min_score = max(0.0, min(1.0, float(min_score)))
        total = len(usable_images)
        evaluations: list[MarkushImageSelection] = []
        best_candidate: Optional[MarkushImageSelection] = None

        for idx, image in enumerate(usable_images[:max_images], start=1):
            selection = self.evaluate_image(
                patent=patent,
                image=image,
                image_index=idx,
                total_images=total,
                target_smiles=target_smiles,
                purpose=purpose,
            )
            evaluations.append(selection)

            if selection.is_markush and (
                best_candidate is None or selection.score > best_candidate.score
            ):
                best_candidate = selection

            if selection.is_main_markush and selection.score >= min_score:
                return selection, evaluations

        if (
            allow_candidate_fallback
            and best_candidate is not None
            and best_candidate.score >= min_score
        ):
            return best_candidate, evaluations
        return None, evaluations

    def parse_response(self, response: dict[str, Any]) -> MarkushImageSelection:
        return MarkushImageSelection(
            is_markush=_coerce_bool(response.get("is_markush")),
            is_main_markush=_coerce_bool(response.get("is_main_markush")),
            score=_coerce_score(response.get("score", 0.0)),
            image_role=str(response.get("image_role") or "uncertain"),
            reasoning=str(response.get("reasoning") or ""),
            raw_response=response,
        )


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}
    return bool(value)


def _coerce_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if score > 1.0 and score <= 100.0:
        score = score / 100.0
    return max(0.0, min(1.0, score))
