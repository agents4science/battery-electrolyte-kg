"""Data loading utilities for the Streamlit app."""

import gzip
import json
from pathlib import Path
import pandas as pd
import streamlit as st

# Get the project root (parent of app/)
PROJECT_ROOT = Path(__file__).parent.parent.parent


@st.cache_data
def load_full_kg():
    """Load the full knowledge graph (supports gzipped files)."""
    # Try gzipped version first (for deployment)
    kg_path_gz = PROJECT_ROOT / "data" / "output" / "knowledge_graph_v3.json.gz"
    if kg_path_gz.exists():
        with gzip.open(kg_path_gz, 'rt', encoding='utf-8') as f:
            return json.load(f)

    # Fall back to uncompressed (for local dev)
    kg_path = PROJECT_ROOT / "data" / "output" / "knowledge_graph_v3.json"
    if kg_path.exists():
        with open(kg_path) as f:
            return json.load(f)

    return None


# SMILES data for common compounds
COMPOUND_SMILES = {
    # Lithium Salts
    "LiPF6": "[Li+].F[P-](F)(F)(F)(F)F",
    "LiBF4": "[Li+].F[B-](F)(F)F",
    "LiFSI": "[Li+].[N-](S(=O)(=O)F)S(=O)(=O)F",
    "LiTFSI": "[Li]N(S(=O)(=O)C(F)(F)F)S(=O)(=O)C(F)(F)F",
    "LiClO4": "[Li+].[O-]Cl(=O)(=O)=O",
    "LiBOB": "[Li+].O=C1O[B-]2(OC1=O)OC(=O)C(=O)O2",
    # Sodium Salts
    "NaPF6": "[Na+].F[P-](F)(F)(F)(F)F",
    "NaBF4": "[Na+].F[B-](F)(F)F",
    "NaFSI": "[Na+].[N-](S(=O)(=O)F)S(=O)(=O)F",
    "NaTFSI": "[Na+].C(F)(F)(F)S(=O)(=O)[N-]S(=O)(=O)C(F)(F)F",
    "NaClO4": "[Na+].[O-]Cl(=O)(=O)=O",
    "NaCF3SO3": "[Na+].[O-]S(=O)(=O)C(F)(F)F",
    # Solvents
    "EC": "C1COC(=O)O1",
    "PC": "CC1COC(=O)O1",
    "DMC": "COC(=O)OC",
    "EMC": "CCOC(=O)OC",
    "DEC": "CCOC(=O)OCC",
    "DME": "COCCOC",
    "DMSO": "CS(=O)C",
    "AN": "CC#N",
    "FEC": "C1C(OC(=O)O1)F",
    "DOL": "C1COCO1",
    "THF": "C1CCOC1",
    "Diglyme": "COCCOCCOC",
    "Tetraglyme": "COCCOCCOCCOCCOC",
}

COMPOUND_NAMES = {
    # Solvents
    "EC": "Ethylene carbonate",
    "PC": "Propylene carbonate",
    "DMC": "Dimethyl carbonate",
    "EMC": "Ethyl methyl carbonate",
    "DEC": "Diethyl carbonate",
    "DME": "Dimethoxyethane",
    "DMSO": "Dimethyl sulfoxide",
    "AN": "Acetonitrile",
    "FEC": "Fluoroethylene carbonate",
    "DOL": "Dioxolane",
    "THF": "Tetrahydrofuran",
    "Diglyme": "Diethylene glycol dimethyl ether",
    "Tetraglyme": "Tetraethylene glycol dimethyl ether",
    # Lithium Salts
    "LiPF6": "Lithium hexafluorophosphate",
    "LiBF4": "Lithium tetrafluoroborate",
    "LiFSI": "Lithium bis(fluorosulfonyl)imide",
    "LiTFSI": "Lithium bis(trifluoromethanesulfonyl)imide",
    "LiClO4": "Lithium perchlorate",
    "LiBOB": "Lithium bis(oxalato)borate",
    # Sodium Salts
    "NaPF6": "Sodium hexafluorophosphate",
    "NaBF4": "Sodium tetrafluoroborate",
    "NaFSI": "Sodium bis(fluorosulfonyl)imide",
    "NaTFSI": "Sodium bis(trifluoromethanesulfonyl)imide",
    "NaClO4": "Sodium perchlorate",
    "NaCF3SO3": "Sodium triflate",
}


@st.cache_data
def load_hypotheses():
    """Load cross-property hypotheses."""
    path = PROJECT_ROOT / "data" / "output" / "cross_property_hypotheses.json"
    with open(path) as f:
        return json.load(f)


@st.cache_data
def load_curated_properties():
    """Load curated electrochemical properties."""
    path = PROJECT_ROOT / "data" / "raw" / "solvent_electrochemical_properties.json"
    with open(path) as f:
        return json.load(f)


@st.cache_data
def load_calisol_data():
    """Load CALiSol-23 conductivity data."""
    path = PROJECT_ROOT / "data" / "raw" / "calisol23_dataset.csv"
    return pd.read_csv(path)


@st.cache_data
def get_solvent_conductivity_stats():
    """Compute average conductivity per solvent from CALiSol data."""
    df = load_calisol_data()

    # Solvent columns in the dataset
    solvent_cols = [
        "EC", "PC", "DMC", "EMC", "DEC", "DME", "DMSO", "AN", "FEC", "DOL", "THF"
    ]

    stats = {}
    for solvent in solvent_cols:
        if solvent in df.columns:
            # Find rows where this solvent is the primary (highest fraction)
            mask = df[solvent] > 0.5
            if mask.sum() > 0:
                conductivities = df.loc[mask, "k"]
                stats[solvent] = {
                    "mean": conductivities.mean(),
                    "std": conductivities.std(),
                    "min": conductivities.min(),
                    "max": conductivities.max(),
                    "count": int(mask.sum()),
                }

    return stats


@st.cache_data
def get_kg_statistics():
    """Get knowledge graph statistics."""
    return {
        "molecules": 23421,
        "formulations": 6134,
        "measurements": 57370,
        "relations": 116568,
        "interphase_species": 200,
        "hypotheses": 100,
    }


@st.cache_data
def get_data_sources():
    """Get data source information."""
    return [
        {
            "name": "HI Munster Conductivity",
            "measurements": 5035,
            "type": "Experimental",
            "properties": "Ionic conductivity",
        },
        {
            "name": "CALiSol-23",
            "measurements": 13023,
            "type": "Literature compilation",
            "properties": "Ionic conductivity",
        },
        {
            "name": "Materials Project Electrolyte Genome",
            "measurements": 39245,
            "type": "DFT computed",
            "properties": "IE, EA, redox potentials",
        },
        {
            "name": "Curated Electrochemical Properties",
            "measurements": 67,
            "type": "Literature curation",
            "properties": "HOMO, LUMO, dielectric",
        },
        {
            "name": "LIBE Interphase Species",
            "measurements": 200,
            "type": "DFT computed",
            "properties": "Thermodynamics, SEI",
        },
    ]


def _infer_molecule_type(name, smiles=""):
    """Infer molecule type from name and SMILES."""
    name_lower = name.lower()
    smiles_lower = smiles.lower() if smiles else ""

    # Check for salts (Li/Na compounds)
    salt_indicators = ["lithium", "sodium", "lipf6", "libf4", "litfsi", "lifsi",
                       "napf6", "nabf4", "natfsi", "nafsi", "liclo4", "naclo4"]
    if any(ind in name_lower for ind in salt_indicators):
        return "salt"
    if name.startswith(("Li", "Na")) and any(c.isupper() for c in name[2:4]):
        return "salt"
    if "[Li" in smiles or "[Na" in smiles:
        return "salt"

    # Check for common solvents
    solvent_indicators = ["carbonate", "ether", "sulfoxide", "sulfone",
                          "acetonitrile", "tetrahydrofuran", "dioxolane",
                          "glyme", "lactone", "furan"]
    if any(ind in name_lower for ind in solvent_indicators):
        return "solvent"

    # Default to molecule
    return "molecule"


@st.cache_data
def get_all_molecules_from_kg():
    """Get all molecules from the KG with their types."""
    kg = load_full_kg()
    if not kg:
        return []

    molecules = []

    # Add molecules with inferred types
    for mol_id, mol in kg.get("molecules", {}).items():
        name = mol.get("name", mol_id[:12])
        smiles = mol.get("smiles", "")
        mol_type = _infer_molecule_type(name, smiles)
        molecules.append({
            "id": mol_id,
            "name": name,
            "smiles": smiles,
            "type": mol_type,
            "source": "molecules",
        })

    # Add solvents (if KG has separate solvents dict)
    for sol_id, sol in kg.get("solvents", {}).items():
        molecules.append({
            "id": sol_id,
            "name": sol.get("name", sol_id[:12]),
            "smiles": sol.get("smiles", ""),
            "type": "solvent",
            "source": "solvents",
        })

    # Add salts (if KG has separate salts dict)
    for salt_id, salt in kg.get("salts", {}).items():
        molecules.append({
            "id": salt_id,
            "name": salt.get("name", salt_id[:12]),
            "smiles": salt.get("smiles", ""),
            "type": "salt",
            "source": "salts",
        })

    # Add interphase species
    for sp_id, sp in kg.get("interphase_species", {}).items():
        molecules.append({
            "id": sp_id,
            "name": sp.get("name", sp_id[:12]),
            "smiles": sp.get("smiles", ""),
            "type": "interphase",
            "source": "interphase_species",
        })

    return molecules


@st.cache_data
def get_all_relations_from_kg():
    """Get all relations from the KG."""
    kg = load_full_kg()
    if not kg:
        return []

    relations = []
    for rel in kg.get("relations", []):
        if len(rel) >= 3:
            relations.append({
                "source": rel[0],
                "type": rel[1],
                "target": rel[2],
            })

    return relations


def get_molecules_for_graph(search_query="", entity_types=None, max_nodes=50):
    """
    Get molecule data for graph visualization.

    Args:
        search_query: Filter by name/SMILES
        entity_types: List of types to include
        max_nodes: Maximum nodes to return (for performance)
    """
    all_molecules = get_all_molecules_from_kg()

    # Always add common compounds (including sodium salts) to ensure they're searchable
    existing_smiles = {m.get("smiles") for m in all_molecules}
    for abbrev, smiles in COMPOUND_SMILES.items():
        if smiles not in existing_smiles:
            mol_type = "salt" if abbrev.startswith(("Li", "Na")) else "solvent"
            all_molecules.append({
                "id": abbrev,
                "name": COMPOUND_NAMES.get(abbrev, abbrev),
                "smiles": smiles,
                "type": mol_type,
            })

    if not all_molecules:
        return []

    # Filter by type
    if entity_types:
        all_molecules = [m for m in all_molecules if m["type"] in entity_types]

    # Filter by search query
    if search_query:
        query_lower = search_query.lower()
        all_molecules = [
            m for m in all_molecules
            if (query_lower in m["name"].lower()
                or query_lower in m.get("smiles", "").lower()
                or query_lower in m.get("type", "").lower())
        ]

    # Sort by name and limit
    all_molecules.sort(key=lambda x: x["name"])

    return all_molecules[:max_nodes]


def get_relations_for_graph(molecule_ids=None):
    """
    Get relations for graph visualization.

    Args:
        molecule_ids: Set of molecule IDs to filter relations (only show relations between these)
    """
    all_relations = get_all_relations_from_kg()

    if not all_relations:
        # Fallback to hardcoded
        relations = []
        common_pairs = [
            ("EC", "LiPF6"),
            ("PC", "LiPF6"),
            ("DMC", "LiPF6"),
            ("EMC", "LiPF6"),
            ("DEC", "LiPF6"),
            ("EC", "LiBF4"),
            ("PC", "LiBF4"),
            ("EC", "LiTFSI"),
            ("DME", "LiTFSI"),
            ("AN", "LiPF6"),
            ("DMSO", "LiTFSI"),
            ("FEC", "LiPF6"),
        ]

        for solvent, salt in common_pairs:
            relations.append({
                "source": solvent,
                "target": salt,
                "type": "usedWith",
            })

        # Solvent co-occurrence patterns
        cooccur = [
            ("EC", "DMC"),
            ("EC", "EMC"),
            ("EC", "DEC"),
            ("EC", "PC"),
            ("PC", "EMC"),
            ("DMC", "EMC"),
        ]

        for s1, s2 in cooccur:
            relations.append({
                "source": s1,
                "target": s2,
                "type": "coOccursWith",
            })

        return relations

    # Filter to only relations between specified molecules
    if molecule_ids:
        molecule_ids = set(molecule_ids)
        filtered = [
            r for r in all_relations
            if r["source"] in molecule_ids and r["target"] in molecule_ids
        ]
        return filtered

    return all_relations
