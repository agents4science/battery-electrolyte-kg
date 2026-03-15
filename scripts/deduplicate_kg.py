#!/usr/bin/env python3
"""
Deduplicate molecules in the Knowledge Graph by canonical SMILES.

This script:
1. Loads the existing KG
2. Runs deduplication to merge molecules with the same SMILES
3. Saves the deduplicated KG
"""

import gzip
import json
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
KG_INPUT = PROJECT_ROOT / "data" / "output" / "knowledge_graph_v3.json.gz"
KG_OUTPUT = PROJECT_ROOT / "data" / "output" / "knowledge_graph_v4.json.gz"


def canonicalize_smiles(smiles: str) -> str:
    """Canonicalize SMILES. Uses RDKit if available."""
    if not smiles:
        return smiles
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol:
            return Chem.MolToSmiles(mol, canonical=True)
    except ImportError:
        pass
    return smiles.strip()


def is_smiles_like(name: str) -> bool:
    """Check if a name looks like a SMILES string."""
    return any(c in name for c in "()[]=#@+-/\\")


def pick_best_name(names: list[str]) -> str:
    """Pick the best name from a list (prefer longer, non-SMILES names)."""
    # Filter out empty names
    names = [n for n in names if n]
    if not names:
        return ""

    # Sort by: (not SMILES-like, length)
    return max(names, key=lambda n: (not is_smiles_like(n), len(n)))


def deduplicate_kg(kg: dict) -> dict:
    """Deduplicate molecules in the KG by canonical SMILES."""
    molecules = kg.get("molecules", {})
    relations = kg.get("relations", [])

    print(f"Original molecules: {len(molecules)}")
    print(f"Original relations: {len(relations)}")

    # Group molecules by canonical SMILES
    smiles_groups: dict[str, list[str]] = defaultdict(list)
    for mol_id, mol in molecules.items():
        smiles = mol.get("smiles")
        if smiles:
            canonical = canonicalize_smiles(smiles)
            smiles_groups[canonical].append(mol_id)
        else:
            # Keep molecules without SMILES as-is
            smiles_groups[f"__no_smiles_{mol_id}"].append(mol_id)

    # Find duplicate groups
    duplicate_groups = {s: ids for s, ids in smiles_groups.items() if len(ids) > 1}
    print(f"Duplicate groups: {len(duplicate_groups)}")
    print(f"Total duplicates to merge: {sum(len(ids) - 1 for ids in duplicate_groups.values())}")

    # Build ID mapping: old_id -> new_id
    id_mapping: dict[str, str] = {}
    new_molecules: dict[str, dict] = {}

    for canonical_smiles, mol_ids in smiles_groups.items():
        if len(mol_ids) == 1:
            # No duplicates, keep as-is
            new_molecules[mol_ids[0]] = molecules[mol_ids[0]]
        else:
            # Pick the best molecule to keep
            mols = [(mol_id, molecules[mol_id]) for mol_id in mol_ids]

            # Sort by name quality
            def name_score(item):
                mol_id, mol = item
                name = mol.get("name", "")
                return (not is_smiles_like(name), len(name))

            mols_sorted = sorted(mols, key=name_score, reverse=True)
            keep_id, keep_mol = mols_sorted[0]

            # Merge all molecules into the kept one
            all_names = [mol.get("name", "") for _, mol in mols]
            all_synonyms = set()
            for _, mol in mols:
                all_synonyms.update(mol.get("synonyms", []))

            # Merge synonyms and alternative names
            best_name = pick_best_name(all_names)
            synonyms = list(all_synonyms | set(all_names) - {best_name})

            keep_mol["name"] = best_name
            keep_mol["synonyms"] = synonyms

            # Merge other fields
            for _, mol in mols:
                if mol.get("inchi") and not keep_mol.get("inchi"):
                    keep_mol["inchi"] = mol["inchi"]
                if mol.get("inchi_key") and not keep_mol.get("inchi_key"):
                    keep_mol["inchi_key"] = mol["inchi_key"]
                if mol.get("pubchem_cid") and not keep_mol.get("pubchem_cid"):
                    keep_mol["pubchem_cid"] = mol["pubchem_cid"]
                if mol.get("cas_number") and not keep_mol.get("cas_number"):
                    keep_mol["cas_number"] = mol["cas_number"]
                if mol.get("molecular_weight") and not keep_mol.get("molecular_weight"):
                    keep_mol["molecular_weight"] = mol["molecular_weight"]

            new_molecules[keep_id] = keep_mol

            # Map removed IDs to kept ID
            for mol_id, _ in mols_sorted[1:]:
                id_mapping[mol_id] = keep_id

    print(f"Molecules after merge: {len(new_molecules)}")
    print(f"ID mappings created: {len(id_mapping)}")

    # Update relations
    new_relations = []
    removed_relations = 0

    for rel in relations:
        if len(rel) >= 3:
            src, rel_type, tgt = rel[0], rel[1], rel[2]

            # Map old IDs to new IDs
            new_src = id_mapping.get(src, src)
            new_tgt = id_mapping.get(tgt, tgt)

            # Skip self-loops created by deduplication
            if new_src == new_tgt and rel_type == "sameAs":
                removed_relations += 1
                continue

            new_relations.append([new_src, rel_type, new_tgt])

    # Remove duplicate relations
    unique_relations = list(set(tuple(r) for r in new_relations))
    new_relations = [list(r) for r in unique_relations]

    print(f"Relations after update: {len(new_relations)}")
    print(f"Self-loop sameAs relations removed: {removed_relations}")

    # Update formulations
    formulations = kg.get("formulations", {})
    for form_id, form in formulations.items():
        components = form.get("components", [])
        for comp in components:
            if comp.get("molecule_id") in id_mapping:
                comp["molecule_id"] = id_mapping[comp["molecule_id"]]

    # Build new KG
    new_kg = kg.copy()
    new_kg["molecules"] = new_molecules
    new_kg["relations"] = new_relations
    new_kg["version"] = "0.4.0"

    return new_kg


def main():
    print(f"Loading KG from {KG_INPUT}...")
    with gzip.open(KG_INPUT, 'rt', encoding='utf-8') as f:
        kg = json.load(f)

    print("\nDeduplicating molecules by SMILES...")
    new_kg = deduplicate_kg(kg)

    print(f"\nSaving deduplicated KG to {KG_OUTPUT}...")
    with gzip.open(KG_OUTPUT, 'wt', encoding='utf-8') as f:
        json.dump(new_kg, f)

    print("Done!")

    # Print summary
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    print(f"Molecules: {len(kg['molecules'])} -> {len(new_kg['molecules'])}")
    print(f"Relations: {len(kg['relations'])} -> {len(new_kg['relations'])}")


if __name__ == "__main__":
    main()
