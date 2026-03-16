#!/usr/bin/env python3
"""
Integrate ChemDataExtractor conductivity data into the Knowledge Graph.

This script:
1. Loads the existing KG (v4)
2. Ingests ChemDataExtractor conductivity measurements
3. Saves the updated KG (v5)
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
from src.ingestion.chemdataextractor import ChemDataExtractorIngestor


def load_kg_v4(path: Path) -> KnowledgeGraph:
    """Load the existing KG v4."""
    print(f"Loading KG from {path}...")

    # Try .json.gz first, then .json
    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            data = json.load(f)
    else:
        with open(path) as f:
            data = json.load(f)

    # Create KG and populate
    kg = KnowledgeGraph(version=data.get('version', '0.4.0'))

    # Import all entity types
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

    # Identify solvents and salts
    for k, v in data.get('solvents', {}).items():
        if k in kg._molecules:
            kg._solvents[k] = kg._molecules[k]

    for k, v in data.get('salts', {}).items():
        if k in kg._molecules:
            kg._salts[k] = kg._molecules[k]

    # Load other entities
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

    # Load relations
    for s, r, o in data.get('relations', []):
        kg._graph.add_edge(s, o, relation=r)

    print(f"Loaded KG with {len(kg._molecules)} molecules, {len(kg._measurements)} measurements")
    return kg


def save_kg(kg: KnowledgeGraph, path: Path):
    """Save KG to JSON (optionally gzipped)."""
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
    KG_INPUT = PROJECT_ROOT / "data" / "output" / "knowledge_graph_v4.json"
    KG_INPUT_GZ = PROJECT_ROOT / "data" / "output" / "knowledge_graph_v4.json.gz"
    CDE_DATA = PROJECT_ROOT / "data" / "external" / "battery-2022.csv"
    KG_OUTPUT = PROJECT_ROOT / "data" / "output" / "knowledge_graph_v5.json"

    # Check input files
    if KG_INPUT_GZ.exists():
        kg_path = KG_INPUT_GZ
    elif KG_INPUT.exists():
        kg_path = KG_INPUT
    else:
        print(f"Error: KG not found at {KG_INPUT} or {KG_INPUT_GZ}")
        sys.exit(1)

    if not CDE_DATA.exists():
        print(f"Error: ChemDataExtractor data not found at {CDE_DATA}")
        sys.exit(1)

    # Load existing KG
    kg = load_kg_v4(kg_path)

    # Record baseline stats
    baseline_stats = kg.stats()
    print(f"\nBaseline KG stats:")
    print(f"  Molecules: {baseline_stats['num_molecules']}")
    print(f"  Measurements: {baseline_stats['num_measurements']}")
    print(f"  Relations: {baseline_stats['num_relations']}")

    # Run ingestion
    print(f"\nIngesting ChemDataExtractor conductivity data...")
    ingestor = ChemDataExtractorIngestor(kg)
    stats = ingestor.ingest(CDE_DATA)

    # Print ingestion results
    print(f"\nIngestion Results:")
    print(f"  Records processed: {stats['records_processed']}")
    print(f"  Records skipped (non-electrolyte): {stats['records_skipped_non_electrolyte']}")
    print(f"  Records skipped (invalid): {stats['records_skipped_invalid']}")
    print(f"  Materials created: {stats['materials_created']}")
    print(f"  Materials matched: {stats['materials_matched']}")
    print(f"  Measurements created: {stats['measurements_created']}")
    print(f"  Unique DOIs: {stats['unique_dois']}")

    if stats['errors']:
        print(f"  Errors: {len(stats['errors'])}")
        for err in stats['errors'][:5]:
            print(f"    - {err}")

    # Update version
    kg.version = "0.5.0"

    # Final stats
    final_stats = kg.stats()
    print(f"\nFinal KG stats:")
    print(f"  Molecules: {final_stats['num_molecules']} (+{final_stats['num_molecules'] - baseline_stats['num_molecules']})")
    print(f"  Measurements: {final_stats['num_measurements']} (+{final_stats['num_measurements'] - baseline_stats['num_measurements']})")
    print(f"  Relations: {final_stats['num_relations']} (+{final_stats['num_relations'] - baseline_stats['num_relations']})")
    print(f"  Sources: {final_stats['num_sources']}")

    # Save updated KG
    save_kg(kg, KG_OUTPUT)
    print(f"\nSaved updated KG to {KG_OUTPUT}")


if __name__ == "__main__":
    main()
