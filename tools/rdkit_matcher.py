"""RDKit 子结构匹配 — 复用 patent_finder 的核心逻辑

将 Markush caption 和目标分子 SMILES 进行 R-group 分解，
判断目标分子是否匹配 Markush 骨架并提取 R 基团映射。
"""

from __future__ import annotations
from typing import Optional

from schemas.types import MatchResult, MatchMethod
from tools.markush_caption import normalize_markush_caption
from tools.substructure_match import substructure_match


class RDKitMatcherTool:
    """基于 RDKit 的确定性子结构匹配"""

    def match(self, markush_caption: str, target_smiles: str) -> MatchResult:
        """执行子结构匹配

        Args:
            markush_caption: Markush 结构的 caption 格式
                e.g. "*C1CCON1C(=O)C1CCN(*)CC1<sep><a>0:R[3]</a><a>12:R[1]</a>"
            target_smiles: 目标分子 SMILES

        Returns:
            MatchResult
        """
        try:
            normalized_caption = normalize_markush_caption(markush_caption)
            if normalized_caption is None:
                return MatchResult(
                    is_match=None,
                    r_group_map=None,
                    method=MatchMethod.RDKIT,
                    reasoning=f"RDKit matching skipped: unsupported Markush caption format: {markush_caption}",
                )

            result = substructure_match(normalized_caption, target_smiles)
            r_group_map = result.get("substructure_map")

            if isinstance(r_group_map, dict):
                return MatchResult(
                    is_match=True,
                    r_group_map=r_group_map,
                    method=MatchMethod.RDKIT,
                    reasoning="RDKit R-group decomposition succeeded",
                )
            else:
                return MatchResult(
                    is_match=False,
                    r_group_map=None,
                    method=MatchMethod.RDKIT,
                    reasoning=str(r_group_map),
                )
        except Exception as e:
            return MatchResult(
                is_match=None,
                r_group_map=None,
                method=MatchMethod.RDKIT,
                reasoning=f"RDKit matching failed: {e}",
            )
