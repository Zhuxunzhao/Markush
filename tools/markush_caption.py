"""Helpers for making MarkushGrapher captions usable by downstream tools."""

from __future__ import annotations

import re
from typing import Optional

from rdkit import Chem, RDLogger

from tools.rdkit_utils.translate import Translator


_INLINE_RGROUP_RE = re.compile(r"<r>(.*?)</r>")
_LABEL_RE = re.compile(r"[^A-Za-z0-9\[\]'\"]+")


def is_rdkit_caption(caption: str) -> bool:
    """Return True if the caption is already in Translator/RDKit format."""
    if not caption:
        return False
    return Translator.parse_caption(caption, return_mol=True) is not None


def normalize_markush_caption(caption: str) -> Optional[str]:
    """Normalize known MarkushGrapher outputs into RDKit matcher format.

    The matcher expects ``SMILES<sep><a>idx:R1</a>``. Some MarkushGrapher runs
    produce inline labels such as ``<r>R1</r>NC...`` instead. This helper
    converts those inline R labels to dummy atoms plus atom annotations when the
    resulting SMILES is parseable.
    """
    caption = (caption or "").strip()
    if not caption:
        return None
    if is_rdkit_caption(caption):
        return caption
    return inline_markush_to_rdkit_caption(caption)


def inline_markush_to_rdkit_caption(caption: str) -> Optional[str]:
    """Convert ``<r>R</r>`` inline notation to ``<sep><a>idx:R</a>`` notation."""
    labels = [_clean_label(match.group(1), idx) for idx, match in enumerate(_INLINE_RGROUP_RE.finditer(caption), start=1)]
    if not labels:
        return None

    smiles = _INLINE_RGROUP_RE.sub("*", caption).split("|", 1)[0].strip()
    if not smiles:
        return None

    RDLogger.DisableLog("rdApp.*")
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    dummy_indices = [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetSymbol() == "*"]
    if len(dummy_indices) != len(labels):
        return None

    extension = "".join(
        f"<a>{atom_idx}:{label}</a>" for atom_idx, label in zip(dummy_indices, labels)
    )
    normalized = f"{smiles}<sep>{extension}"
    if not is_rdkit_caption(normalized):
        return None
    return normalized


def _clean_label(raw: str, fallback_idx: int) -> str:
    label = _LABEL_RE.sub("", (raw or "").strip())
    if not label or label == "*":
        return f"R{fallback_idx}"
    return label
