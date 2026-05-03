"""RDKit-based Markush substructure matching.

Migrated from patent_finder/patent_finder/patent_agent/tools/substructure_match.py.
Removed langchain dependency; uses local rdkit_utils package.
"""

from __future__ import annotations
import copy
import re
from typing import Dict, List, Optional, Sequence, Union

from rdkit import Chem
from rdkit.Chem import rdRGroupDecomposition as rdRGD
from rdkit.Chem.rdchem import Mol, RWMol, Atom, ChiralType, BondType

from .rdkit_utils.translate import Translator, GroupDesc
from .rdkit_utils.misc import AtomIndex, RingIndex, is_valid_index


def _get_decom_params():
    param = rdRGD.RGroupDecompositionParameters()
    param.onlyMatchAtRGroups = True
    param.allowNonTerminalRGroups = True
    param.removeAllHydrogenRGroups = False
    param.removeAllHydrogenRGroupsAndLabels = False
    param.allowMultipleRGroupsOnUnlabelled = True
    return param


def _merge_nonterminal_Rsite(r_mol: Mol, r_atom: Atom) -> Optional[Mol]:
    r_mol = RWMol(r_mol)
    dummy_idx = end_idx = None
    for atom in r_mol.GetAtoms():
        if atom.HasProp('molAtomMapNumber') and atom.GetDegree() == 1:
            dummy_idx = atom.GetIdx()
            end_idx = atom.GetNeighbors()[0].GetIdx()
            break

    if dummy_idx is None:
        return

    r_mol.RemoveAtom(dummy_idx)
    begin_idx = r_mol.AddAtom(r_atom)
    r_mol.AddBond(begin_idx, end_idx, BondType.SINGLE)
    return r_mol.GetMol()


class MoleculeQuerier:
    def __init__(self, mol, grp_descriptions, **kwds) -> None:
        self._Rgroups = self._collect_Rgroups(mol, grp_descriptions)
        self._core = self._prepare_core(mol)
        self._Rsites = self._collect_Rsites(self._core)

    def _prepare_core(self, mol: Mol) -> Mol:
        Rsite_idx = 1
        for atom in mol.GetAtoms():
            if atom.GetChiralTag() != ChiralType.CHI_UNSPECIFIED:
                atom.SetChiralTag(ChiralType.CHI_UNSPECIFIED)
            if atom.GetSymbol() == '*':
                atom.SetProp('molAtomMapNumber', str(Rsite_idx))
                Rsite_idx += 1
        return mol

    def _collect_Rsites(self, mol: Mol) -> Dict[str, int]:
        Rsites = {}
        for atom in mol.GetAtoms():
            if atom.GetSymbol() == '*' and atom.GetDegree() >= 1:
                try:
                    i = atom.GetProp('molAtomMapNumber')
                except Exception:
                    continue
                Rsites[f'R{i}'] = atom.GetIdx()
        return Rsites

    def _collect_Rgroups(self, mol: Mol, grp_descriptions: List[GroupDesc]) -> Dict[int, str]:
        num_atoms = mol.GetNumAtoms()
        num_rings = mol.GetRingInfo().NumRings()
        Rgroups = {}
        for desc in grp_descriptions:
            if not isinstance(desc.id, AtomIndex):
                continue
            if not is_valid_index(desc.id, num_atoms, num_rings):
                continue
            if (
                desc.is_dummy
                or desc.symbol is None
                or mol.GetAtomWithIdx(int(desc.id)).GetSymbol() != '*'
            ):
                continue
            Rgroups[int(desc.id)] = str(desc)
        return Rgroups

    def _postprocess_Rgroups(self, decom: Dict[str, Mol]) -> Dict[str, str]:
        unk_idx = 1
        groups = {}
        for Rsite, atom_idx in self._Rsites.items():
            if atom_idx in self._Rgroups:
                key = self._Rgroups[atom_idx]
            else:
                key = f'UNK{unk_idx}'
                unk_idx += 1
            smi = self._get_Rsite_smi(atom_idx, Rsite, decom)
            if smi is not None:
                groups[key] = smi
        return groups

    def _get_Rsite_smi(self, atom_idx: int, Rsite: str, decom: Dict[str, Mol]) -> Optional[str]:
        r_atom = self._core.GetAtomWithIdx(atom_idx)
        if r_atom.GetDegree() == 1:
            return self._get_terminal_Rsite_smi(Rsite, decom)
        return self._get_nonterminal_Rsite_smi(Rsite, decom)

    def _get_terminal_Rsite_smi(self, Rsite: str, decom: Dict[str, Mol]) -> Optional[str]:
        r_mol = decom.get(Rsite)
        if r_mol is None:
            return
        dummy_idx = root_atom = None
        for atom in r_mol.GetAtoms():
            if atom.HasProp('molAtomMapNumber') and atom.GetDegree() == 1:
                dummy_idx = atom.GetIdx()
                root_atom = atom.GetNeighbors()[0]
                break
        if dummy_idx is None:
            return
        r_mol = RWMol(r_mol)
        r_mol.RemoveAtom(dummy_idx)
        begin_idx = r_mol.AddAtom(Atom(1))
        r_mol.AddBond(begin_idx, root_atom.GetIdx(), BondType.SINGLE)
        r_mol = r_mol.GetMol()
        r_mol = Chem.RemoveHs(r_mol)
        return Chem.MolToSmiles(r_mol, rootedAtAtom=root_atom.GetIdx())

    def _get_nonterminal_Rsite_smi(self, Rsite: str, decom: Dict[str, Mol]) -> Optional[str]:
        d_core = decom['Core']
        Rsite_idx = Rsite[1:]
        r_atom = None
        for atom in d_core.GetAtoms():
            if (
                atom.HasProp('molAtomMapNumber')
                and atom.GetProp('molAtomMapNumber') == Rsite_idx
                and atom.GetDegree() == 1
            ):
                r_atom = atom.GetNeighbors()[0]
                break
        if r_atom is None:
            return
        if decom.get(Rsite) is not None:
            r_mol = _merge_nonterminal_Rsite(
                r_mol=decom.get(Rsite), r_atom=Atom(r_atom.GetAtomicNum())
            )
        else:
            r_mol = RWMol()
            r_mol.AddAtom(Atom(r_atom.GetAtomicNum()))
            r_mol = r_mol.GetMol()
        if r_mol is None:
            return
        return Chem.MolToSmiles(r_mol, rootedAtAtom=(r_mol.GetNumAtoms() - 1))

    def query(self, q_mols: Union[str, Sequence[str]]) -> List[Optional[Dict[str, str]]]:
        if isinstance(q_mols, str):
            q_mols = [q_mols]
        q_mols = [Chem.MolFromSmiles(q) for q in q_mols]
        matched, unmatched = rdRGD.RGroupDecompose(
            [self._core], q_mols, asSmiles=False, options=_get_decom_params()
        )
        res = []
        j = 0
        for i in range(len(q_mols)):
            if i in unmatched:
                res.append(None)
            else:
                res.append(self._postprocess_Rgroups(decom=matched[j]))
                j += 1
        return res


def Molecule_query(caption: str, q_mols: Union[str, List[str]]) -> Optional[List]:
    """Match query molecules against a Markush caption.

    Returns list of R-group dicts (or None per non-matching molecule),
    or None if the caption is invalid or no match found for ring substitutions.
    """
    if not isinstance(q_mols, list):
        q_mols = [q_mols]

    parsed = Translator.parse_caption(caption, return_mol=True)
    if parsed is None:
        raise ValueError(f'Incorrect caption: {caption}')
    mol, groups = parsed
    grp_descriptions = Translator.parse_groups(groups)

    atom_list = []
    ring_list = []
    for grp in grp_descriptions:
        if isinstance(grp.id, RingIndex):
            ring_list.append(grp)
        elif isinstance(grp.id, AtomIndex):
            atom_list.append(grp)

    if len(ring_list) == 0:
        mol_querier = MoleculeQuerier(mol, atom_list)
        return mol_querier.query(q_mols)

    ri = mol.GetRingInfo()
    atominfo = ri.AtomRings()
    for ring in ring_list:
        orig_atom_list = copy.deepcopy(atom_list)
        orig_mol = copy.deepcopy(mol)
        ring_id = ring.id
        atom_idx = atominfo[ring_id]
        for idx in atom_idx:
            rw_mol = Chem.RWMol(orig_mol)
            add_idx = rw_mol.AddAtom(Chem.Atom(0))
            rw_mol.AddBond(idx, add_idx, Chem.BondType.SINGLE)
            smi = Chem.MolToSmiles(rw_mol.GetMol(), rootedAtAtom=0, canonical=False)
            try:
                mol = Chem.RWMol(Chem.MolFromSmiles(smi))
            except Exception:
                continue
            desc = GroupDesc(id=AtomIndex(idx + 1))
            desc.symbol = ring.symbol
            desc.script = ring.script
            desc.prime = ring.prime
            desc.multiple = ring.multiple
            for atom in orig_atom_list:
                if atom.id > idx:
                    atom.id = AtomIndex(atom.id + 1)
            orig_atom_list.append(desc)

            mol_querier = MoleculeQuerier(mol, orig_atom_list)
            res = mol_querier.query(q_mols)
            for result in res:
                if result is not None:
                    return res
    return None


def substructure_match(claim: str, target_smiles: str) -> dict:
    """Match a target SMILES against a Markush claim caption.

    Returns:
        {"is_match": bool|None, "substructure_map": dict|str}
    """
    try:
        # This specific SMILES causes a segfault in RDKit RGroupDecompose
        assert target_smiles != 'CC(C)Oc1ccc(CNc2nc(N)nc(-c3ccco3)c2C#N)cc1Br'
        match_result = Molecule_query(claim, target_smiles)
        assert match_result is not None
        return {
            "is_match": any(match_result),
            "substructure_map": match_result[0],
        }
    except Exception as e:
        return {
            "is_match": None,
            "substructure_map": f'Structure matching failed: {repr(e)}',
        }
