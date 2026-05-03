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
Markush 字符串表示带有可变基团（R-groups）的化学结构。
格式：SMILES<sep>EXTENSION
- SMILES 部分：分子骨架，其中 * 表示 R 基团占位符
- EXTENSION 部分：XML 风格标注，用于把原子/环索引映射到 R 基团标签
  例如：<a>0:R[1]</a><a>12:R[2]</a><r>1:R[3]</r>
  - <a>idx:label</a> = 在原子 idx 位置发生取代
  - <r>idx:label</r> = 在环 idx 位置发生取代
  - <c>idx:label</c> = 圆形结构/可变连接处的取代
  - <dum> = 连接点（dummy atom）
  - GROUP_NAME 可以是缩写或全称，例如 R、X、Y、Z、Ph、Me、OMe、CF3 等
  - 下标用方括号表示：R[1]、R[2]、R[3]
"""

RGROUP_MAPPING_DEFINITION = """
R 基团映射是一个字典：
- 键是 R 基团标签，例如 "R1"、"R[1]"、"X"、"Y"
- 值是表示实际取代基的 SMILES 字符串
  例如：{"R1": "CH3", "R2": "c1ccccc1", "X": "Cl"}

只有当把 Markush 结构中的 R 基团替换为对应取代基后能够得到查询分子时，
该 R 基团映射才视为正确。
"""

CONFIDENCE_SCORE_DEFINITION = """
置信度判定标准：
- high（80-99.9）：证据清晰，Markush 精确匹配，权利要求要件明确满足。
- moderate（50-79）：权利要求存在一定歧义，或匹配结果有轻微不确定性。
- low（20-49）：证据相互矛盾、仅部分重叠，或需要较宽泛地解释权利要求。
- very_low（0-19）：几乎没有证据，或存在显著不匹配。
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
