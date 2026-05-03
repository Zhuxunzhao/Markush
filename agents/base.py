"""Agent 基类 — 统一 LLM 调用模式

所有 Agent 遵循相同模式:
1. 定义 system_prompt（角色 + 领域知识）
2. 构造 user_prompt（格式化输入数据）
3. 调用 LLM 获取结构化输出
4. 解析输出为对应的数据类型
"""

from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from tools.llm_client import LLMClient

logger = logging.getLogger("markush.agents")

# 共享的领域知识定义（复用 patent_finder 的 llm_utils 模式）
MARKUSH_STRING_DEFINITION = """
A Markush string represents a chemical structure with variable groups (R-groups).
Format: SMILES<sep>EXTENSION
- SMILES part: molecular structure with * as R-group placeholders
- EXTENSION part: XML-style annotations mapping atom indices to R-group labels
  e.g. <a>0:R[1]</a><a>12:R[2]</a><r>1:R[3]</r>
  - <a>idx:label</a> = atom substitution at atom index
  - <r>idx:label</r> = ring substitution at ring index
  - <c>idx:label</c> = circle substitution
  - <dum> = connection point (dummy atom)
  - GROUP_NAME can be abbreviation or full name (R, X, Y, Z, Ph, Me, OMe, CF3, etc.)
  - Subscripts are appended with brackets: R[1], R[2], R[3]
"""

RGROUP_MAPPING_DEFINITION = """
An R-group mapping is a dictionary where:
- Keys are R-group labels (e.g. "R1", "R[1]", "X", "Y")
- Values are SMILES strings representing the actual substituent
  e.g. {"R1": "CH3", "R2": "c1ccccc1", "X": "Cl"}

The R-group values are considered correct iff when we replace the R-groups
in the Markush structure with the corresponding values, we get the query molecule.
"""

CONFIDENCE_SCORE_DEFINITION = """
Scoring Criteria:
- High Confidence (80-99.9): Clear evidence, precise Markush match, unambiguous claim requirements met.
- Moderate Confidence (50-79): Some ambiguities in claim requirements or minor match uncertainties.
- Low Confidence (20-49): Contradictory evidence, partial overlap, broadly interpreted claims.
- Very Low Confidence (0-19): Little to no evidence, significant mismatches.
"""


class BaseAgent(ABC):
    """Agent 基类"""

    def __init__(self, llm: LLMClient, max_tokens: Optional[int] = None):
        self.llm = llm
        self.max_tokens = max_tokens
        self.last_llm_response: Any = None

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Agent 的角色定义和领域知识"""
        ...

    @abstractmethod
    def build_user_prompt(self, **kwargs) -> str:
        """根据输入数据构造 user prompt"""
        ...

    @abstractmethod
    def parse_response(self, response: dict) -> Any:
        """将 LLM 输出解析为结构化数据"""
        ...

    def run(self, **kwargs) -> Any:
        """执行 Agent: 构造 prompt → 调用 LLM → 解析输出"""
        logger.info(f"Running {self.name}...")
        user_prompt = self.build_user_prompt(**kwargs)
        self.last_llm_response = None
        response = self.llm.chat(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            max_tokens=self.max_tokens,
        )
        self.last_llm_response = response
        result = self.parse_response(response)
        logger.info(f"{self.name} completed.")
        return result

    @staticmethod
    def truncate(text: str, max_chars: int = 50000) -> str:
        """截断过长文本"""
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n... [truncated]"
