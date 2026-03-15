#!/usr/bin/env python3
"""Test external KG integration with our electrolyte molecules."""

import sys
sys.path.insert(0, '.')

from src.kg_store.graph import KnowledgeGraph
from src.integration import PubChemClient, WikidataClient, MoleculeEnricher


def test_pubchem():
    """Test PubChem integration."""
    print("\n" + "=" * 60)
    print("Testing PubChem Integration")
    print("=" * 60)

    client = PubChemClient()

    # Test search by name for our electrolyte components
    test_compounds = ["ethylene carbonate", "propylene carbonate", "ethyl methyl carbonate", "lithium hexafluorophosphate"]

    for name in test_compounds:
        print(f"\nSearching for: {name}")
        results = client.search_by_name(name)
        if results:
            compound = results[0]
            print(f"  Found: CID {compound.cid}")
            print(f"  IUPAC: {compound.iupac_name}")
            print(f"  Formula: {compound.molecular_formula}")
            print(f"  MW: {compound.molecular_weight} g/mol")
            print(f"  SMILES: {compound.smiles}")
            print(f"  InChI Key: {compound.inchi_key}")
            if compound.synonyms:
                print(f"  Synonyms: {', '.join(compound.synonyms[:3])}")
        else:
            print("  Not found")


def test_wikidata():
    """Test Wikidata integration."""
    print("\n" + "=" * 60)
    print("Testing Wikidata Integration")
    print("=" * 60)

    client = WikidataClient()

    # Test CAS lookups for common electrolyte components
    cas_numbers = {
        "96-49-1": "Ethylene carbonate (EC)",
        "108-32-7": "Propylene carbonate (PC)",
        "623-53-0": "Ethyl methyl carbonate (EMC)",
        "21324-40-3": "Lithium hexafluorophosphate (LiPF6)",
    }

    for cas, name in cas_numbers.items():
        print(f"\nLooking up CAS {cas} ({name})")
        entity = client.get_by_cas(cas)
        if entity:
            print(f"  Wikidata QID: {entity.qid}")
            print(f"  Label: {entity.label}")
            print(f"  Description: {entity.description}")
            if entity.uses:
                print(f"  Uses: {', '.join(entity.uses[:3])}")
            if entity.wikipedia_url:
                print(f"  Wikipedia: {entity.wikipedia_url}")
        else:
            print("  Not found in Wikidata")


def test_enrichment():
    """Test full molecule enrichment pipeline."""
    print("\n" + "=" * 60)
    print("Testing Molecule Enrichment Pipeline")
    print("=" * 60)

    # Load our knowledge graph
    try:
        kg = KnowledgeGraph.load('data/output/knowledge_graph.json')
        print(f"\nLoaded KG with {len(kg._molecules)} molecules")
    except FileNotFoundError:
        print("\nKG not found. Creating test molecules...")
        kg = KnowledgeGraph()

        # Add test molecules manually
        from src.schema.entities import Molecule

        test_mols = [
            Molecule(name="Ethylene Carbonate", smiles="C1COC(=O)O1", cas_number="96-49-1"),
            Molecule(name="Propylene Carbonate", smiles="CC1COC(=O)O1", cas_number="108-32-7"),
            Molecule(name="Ethyl Methyl Carbonate", smiles="CCOC(=O)OC", cas_number="623-53-0"),
            Molecule(name="LiPF6", cas_number="21324-40-3"),
        ]

        for mol in test_mols:
            kg.add_molecule(mol)

        print(f"Created {len(test_mols)} test molecules")

    # Enrich molecules
    enricher = MoleculeEnricher(kg)
    results = enricher.enrich_all_molecules(verbose=True)

    # Print detailed report for first molecule
    if results:
        print("\n" + "-" * 60)
        print("Detailed report for first enriched molecule:")
        enricher.print_enrichment_report(results[0])


if __name__ == "__main__":
    print("=" * 60)
    print("External Knowledge Graph Integration Test")
    print("=" * 60)

    test_pubchem()
    test_wikidata()
    test_enrichment()

    print("\n" + "=" * 60)
    print("Integration tests complete!")
    print("=" * 60)
