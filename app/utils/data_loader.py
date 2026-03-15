"""Data loading utilities for the Streamlit app."""

import json
from pathlib import Path
import pandas as pd
import streamlit as st

# Get the project root (parent of app/)
PROJECT_ROOT = Path(__file__).parent.parent.parent


# SMILES data for common compounds
COMPOUND_SMILES = {
    # Salts
    "LiPF6": "[Li+].F[P-](F)(F)(F)(F)F",
    "LiBF4": "[Li+].F[B-](F)(F)F",
    "LiFSI": "[Li+].[N-](S(=O)(=O)F)S(=O)(=O)F",
    "LiTFSI": "[Li]N(S(=O)(=O)C(F)(F)F)S(=O)(=O)C(F)(F)F",
    "LiClO4": "[Li+].[O-]Cl(=O)(=O)=O",
    "LiBOB": "[Li+].O=C1O[B-]2(OC1=O)OC(=O)C(=O)O2",
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
}

COMPOUND_NAMES = {
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
    "LiPF6": "Lithium hexafluorophosphate",
    "LiBF4": "Lithium tetrafluoroborate",
    "LiFSI": "Lithium bis(fluorosulfonyl)imide",
    "LiTFSI": "Lithium bis(trifluoromethanesulfonyl)imide",
    "LiClO4": "Lithium perchlorate",
    "LiBOB": "Lithium bis(oxalato)borate",
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


def get_molecules_for_graph():
    """Get molecule data for graph visualization."""
    molecules = []

    # Add solvents
    for abbrev, smiles in COMPOUND_SMILES.items():
        if not abbrev.startswith("Li"):  # Not a salt
            molecules.append({
                "id": abbrev,
                "name": COMPOUND_NAMES.get(abbrev, abbrev),
                "smiles": smiles,
                "type": "solvent",
            })

    # Add salts
    for abbrev, smiles in COMPOUND_SMILES.items():
        if abbrev.startswith("Li"):
            molecules.append({
                "id": abbrev,
                "name": COMPOUND_NAMES.get(abbrev, abbrev),
                "smiles": smiles,
                "type": "salt",
            })

    return molecules


def get_relations_for_graph():
    """Get relations for graph visualization."""
    relations = []

    # Common solvent-salt combinations based on CALiSol data
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
