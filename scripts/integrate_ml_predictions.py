#!/usr/bin/env python3
"""
Integrate Electrolytomics ML predictions into the Knowledge Graph.

This script:
1. Loads the existing KG (v6)
2. Ingests ML-predicted properties for 76K candidate molecules
3. Saves the updated KG (v7)
"""

import sys
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import json
import gzip
from datetime import datetime

from src.kg_store.graph import KnowledgeGraph
from src.ingestion.ml_predictions import MLPredictionsIngestor


def load_kg(path: Path) -> KnowledgeGraph:
    """Load the existing KG."""
    print(f"Loading KG from {path}...")

    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            data = json.load(f)
    else:
        with open(path) as f:
            data = json.load(f)

    kg = KnowledgeGraph(version=data.get('version', '0.6.0'))

    from src.schema.entities import (
        Molecule, Solvent, Salt, ElectrolyteFormulation,
        PropertyMeasurement, MeasurementMethod, InterphaseSpecies,
        EvidenceSource,
    )
    from src.schema.provenance import ProvenanceRecord
    from src.schema.hypothesis import HypothesisEdge

    # Load molecules
    for k, v in data.get('molecules', {}).items():
        mol = Molecule(**v)
        kg._molecules[k] = mol
        kg._graph.add_node(k, type="Molecule", data=mol)
        kg._index_molecule_smiles(k, mol.smiles)

    for k, v in data.get('solvents', {}).items():
        if k in kg._molecules:
            kg._solvents[k] = kg._molecules[k]

    for k, v in data.get('salts', {}).items():
        if k in kg._molecules:
            kg._salts[k] = kg._molecules[k]

    for k, v in data.get('formulations', {}).items():
        kg._formulations[k] = ElectrolyteFormulation(**v)
        kg._graph.add_node(k, type="ElectrolyteFormulation")

    for k, v in data.get('measurements', {}).items():
        kg._measurements[k] = PropertyMeasurement(**v)
        kg._graph.add_node(k, type="PropertyMeasurement")

    for k, v in data.get('methods', {}).items():
        kg._methods[k] = MeasurementMethod(**v)

    for k, v in data.get('interphase_species', {}).items():
        kg._interphase_species[k] = InterphaseSpecies(**v)

    for k, v in data.get('sources', {}).items():
        kg._sources[k] = EvidenceSource(**v)

    for k, v in data.get('provenance', {}).items():
        kg._provenance[k] = ProvenanceRecord(**v)

    for k, v in data.get('hypotheses', {}).items():
        kg._hypotheses[k] = HypothesisEdge(**v)

    for s, r, o in data.get('relations', []):
        kg._graph.add_edge(s, o, relation=r)

    print(f"Loaded KG with {len(kg._molecules)} molecules, {len(kg._measurements)} measurements")
    return kg


def save_kg(kg: KnowledgeGraph, path: Path):
    """Save KG to JSON."""
    data = {
        "version": kg.version,
        "created_at": kg.created_at.isoformat(),
        "molecules": {k: v.model_dump() for k, v in kg._molecules.items()},
        "solvents": {k: v.model_dump() for k, v in kg._solvents.items()},
        "salts": {k: v.model_dump() for k, v in kg._salts.items()},
        "formulations": {k: v.model_dump() for k, v in kg._formulations.items()},
        "measurements": {k: v.model_dump() for k, v in kg._measurements.items()},
        "methods": {k: v.model_dump() for k, v in kg._methods.items()},
        "interphase_species": {k: v.model_dump() for k, v in kg._interphase_species.items()},
        "sources": {k: v.model_dump() for k, v in kg._sources.items()},
        "provenance": {k: v.model_dump() for k, v in kg._provenance.items()},
        "hypotheses": {k: v.model_dump() for k, v in kg._hypotheses.items()},
        "relations": kg.to_triples(),
    }

    print(f"Saving KG to {path}...")
    if path.suffix == '.gz':
        with gzip.open(path, 'wt', encoding='utf-8') as f:
            json.dump(data, f)
    else:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)


def main():
    # Paths
    KG_INPUT = PROJECT_ROOT / "data" / "output" / "knowledge_graph_v6.json"
    KG_INPUT_GZ = PROJECT_ROOT / "data" / "output" / "knowledge_graph_v6.json.gz"
    ELYTOMICS_DATA = PROJECT_ROOT / "data" / "external" / "electrolytomics"
    KG_OUTPUT = PROJECT_ROOT / "data" / "output" / "knowledge_graph_v7.json"

    # Check input files
    if KG_INPUT_GZ.exists():
        kg_path = KG_INPUT_GZ
    elif KG_INPUT.exists():
        kg_path = KG_INPUT
    else:
        print(f"Error: KG not found at {KG_INPUT} or {KG_INPUT_GZ}")
        sys.exit(1)

    if not ELYTOMICS_DATA.exists():
        print(f"Error: Electrolytomics data not found at {ELYTOMICS_DATA}")
        sys.exit(1)

    # Load existing KG
    kg = load_kg(kg_path)

    # Record baseline stats
    baseline_stats = kg.stats()
    print(f"\nBaseline KG stats:")
    print(f"  Molecules: {baseline_stats['num_molecules']}")
    print(f"  Measurements: {baseline_stats['num_measurements']}")
    print(f"  Relations: {baseline_stats['num_relations']}")

    # Run ingestion
    print(f"\nIngesting ML predictions...")
    ingestor = MLPredictionsIngestor(kg)
    stats = ingestor.ingest(ELYTOMICS_DATA)

    # Print ingestion results
    print(f"\n{'='*60}")
    print("INGESTION RESULTS")
    print(f"{'='*60}")
    print(f"  Records processed: {stats['records_processed']}")
    print(f"  Records skipped: {stats['records_skipped']}")
    print(f"  Molecules created: {stats['molecules_created']}")
    print(f"  Molecules matched: {stats['molecules_matched']}")
    print(f"  Conductivity predictions: {stats['conductivity_predictions']}")
    print(f"  Ionization energy predictions: {stats['ie_predictions']}")
    print(f"  Coulombic efficiency predictions: {stats['ce_predictions']}")

    # Update version
    kg.version = "0.7.0"

    # Final stats
    final_stats = kg.stats()
    print(f"\n{'='*60}")
    print("FINAL KG STATISTICS")
    print(f"{'='*60}")
    print(f"  Molecules: {final_stats['num_molecules']} (+{final_stats['num_molecules'] - baseline_stats['num_molecules']})")
    print(f"  Measurements: {final_stats['num_measurements']} (+{final_stats['num_measurements'] - baseline_stats['num_measurements']})")
    print(f"  Relations: {final_stats['num_relations']} (+{final_stats['num_relations'] - baseline_stats['num_relations']})")
    print(f"  Sources: {final_stats['num_sources']}")

    # Save updated KG
    save_kg(kg, KG_OUTPUT)
    print(f"\nSaved updated KG to {KG_OUTPUT}")


if __name__ == "__main__":
    main()
