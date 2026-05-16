"""统一数据类型定义"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MatchMethod(str, Enum):
    RDKIT = "rdkit"
    NN = "nn"
    LLM = "llm"
    FUSED = "fused"


class Confidence(str, Enum):
    HIGH = "high"          # 80-99.9
    MODERATE = "moderate"  # 50-79
    LOW = "low"            # 20-49
    VERY_LOW = "very_low"  # 0-19


# --------------- Tool 层输出 ---------------

@dataclass
class OCRCell:
    """ChemicalOCR 输出的单个文字区域"""
    text: str
    bbox: list[float]  # [x1, y1, x2, y2] normalized 0-1


@dataclass
class MarkushStructure:
    """MarkushGrapher 识别出的 Markush 结构"""
    cxsmiles: str                          # CXSMILES 表示
    substituent_table: dict[str, str]      # R-group → 描述
    caption: str = ""                      # 兼容 patent_finder 的 <sep><a> 格式
    source_image_path: str = ""
    score: float = 0.0
    is_markush: bool = True


@dataclass
class PatentImage:
    """专利中的单张图片及其解析结果"""
    path: str
    link: str = ""
    structure: Optional[MarkushStructure] = None


@dataclass
class PatentDocument:
    """完整的专利文档"""
    patent_id: str
    claims_text: str = ""
    description_text: str = ""
    abstract_text: str = ""
    full_text: str = ""
    images: list[PatentImage] = field(default_factory=list)
    markush_structures: list[MarkushStructure] = field(default_factory=list)


# --------------- Agent 层输出 ---------------

@dataclass
class MatchResult:
    """子结构匹配结果（单次匹配）"""
    is_match: Optional[bool]
    r_group_map: Optional[dict[str, str]]  # {"R1": "CH3", "R2": "OH", ...}
    method: MatchMethod
    reasoning: str = ""


@dataclass
class FusedMatchResult:
    """融合后的匹配结果（SubsMatcher Agent 输出）"""
    r_group_matching: dict[str, str]
    rdkit_result: Optional[MatchResult] = None
    nn_result: Optional[MatchResult] = None
    llm_result: Optional[MatchResult] = None
    reasoning: str = ""
    claim_aligned_r_group_matching: dict[str, str] = field(default_factory=dict)
    label_alignment: dict[str, dict] = field(default_factory=dict)


@dataclass
class RGroupAlignmentResult:
    """caption-local R 标签到 claim 法律变量标签的显式对齐结果"""
    aligned_r_group_matching: dict[str, str] = field(default_factory=dict)
    label_alignment: dict[str, dict] = field(default_factory=dict)
    unresolved_labels: list[str] = field(default_factory=list)
    reasoning: str = ""
    confidence: Confidence = Confidence.VERY_LOW


@dataclass
class RequirementsResult:
    """R 基团约束检查结果"""
    is_protected: bool
    reasoning: str
    confidence: Confidence = Confidence.VERY_LOW
    r_group_analysis: dict[str, dict] = field(default_factory=dict)
    # e.g. {"R1": {"value": "CH3", "covered": True, "reason": "..."}}


@dataclass
class InfringementResult:
    """专利侵权分析最终结果"""
    patent_id: str
    target_smiles: str
    is_protected: bool
    confidence: Confidence
    markush_structure: Optional[MarkushStructure] = None
    fused_match: Optional[FusedMatchResult] = None
    requirements: Optional[RequirementsResult] = None
    llm_outputs: dict = field(default_factory=dict)
    report: str = ""
    analysis_status: str = "completed"  # protected / not_protected / undetermined / failed
    is_conclusive: bool = True
    failure_reason: str = ""


# --------------- Pipeline 2: 可专利性分析 ---------------

@dataclass
class PriorArt:
    """一条现有技术"""
    patent_id: str
    relevance_score: float
    overlap_description: str
    markush_structures: list[MarkushStructure] = field(default_factory=list)


@dataclass
class PatentabilityResult:
    """专利申请成功率分析结果"""
    proposed_structure: MarkushStructure
    novelty_score: float               # 0-1, 越高越新颖
    prior_arts: list[PriorArt] = field(default_factory=list)
    risk_points: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    success_analysis: dict = field(default_factory=dict)
    llm_outputs: dict = field(default_factory=dict)
    report: str = ""
