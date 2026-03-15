"""Molecule enrichment using external knowledge graphs."""

from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

from .pubchem import PubChemClient, PubChemCompound
from .wikidata import WikidataClient, WikidataEntity
from ..kg_store.graph import KnowledgeGraph
from ..schema.entities import Molecule
from ..schema.provenance import ProvenanceRecord, Agent, AgentType


@dataclass
class EnrichedMolecule:
    """Molecule data enriched from external sources."""
    # Original data
    molecule_id: str
    name: str
    smiles: Optional[str] = None
    cas_number: Optional[str] = None

    # From PubChem
    pubchem_cid: Optional[int] = None
    pubchem_iupac_name: Optional[str] = None
    pubchem_synonyms: list[str] = field(default_factory=list)
    molecular_formula: Optional[str] = None
    molecular_weight: Optional[float] = None
    inchi: Optional[str] = None
    inchi_key: Optional[str] = None

    # From Wikidata
    wikidata_qid: Optional[str] = None
    wikidata_description: Optional[str] = None
    wikidata_uses: list[str] = field(default_factory=list)
    wikidata_classification: list[str] = field(default_factory=list)
    wikipedia_url: Optional[str] = None

    # Cross-references
    chebi_id: Optional[str] = None
    chembl_id: Optional[str] = None

    # Physical properties
    melting_point: Optional[str] = None
    boiling_point: Optional[str] = None
    density: Optional[str] = None

    # Enrichment metadata
    enriched_at: Optional[datetime] = None
    sources_used: list[str] = field(default_factory=list)


class MoleculeEnricher:
    """
    Enriches molecules in the KG with data from external sources.

    Sources:
    - PubChem: chemical identifiers, synonyms, properties
    - Wikidata: classifications, uses, Wikipedia links
    """

    def __init__(self, kg: KnowledgeGraph):
        self.kg = kg
        self.pubchem = PubChemClient()
        self.wikidata = WikidataClient()
        self._agent = self._create_agent()

    def _create_agent(self) -> Agent:
        """Create provenance agent for enrichment."""
        agent = Agent(
            name="MoleculeEnricher",
            agent_type=AgentType.SOFTWARE,
            version="1.0.0",
            description="Enriches molecules from PubChem and Wikidata",
        )
        self.kg.add_agent(agent)
        return agent

    def enrich_molecule(self, molecule: Molecule) -> EnrichedMolecule:
        """
        Enrich a single molecule with external data.

        Tries multiple strategies:
        1. Search by PubChem CID if available
        2. Search by CAS number
        3. Search by SMILES
        4. Search by name
        """
        enriched = EnrichedMolecule(
            molecule_id=molecule.id,
            name=molecule.name,
            smiles=molecule.smiles,
            cas_number=molecule.cas_number,
            pubchem_cid=molecule.pubchem_cid,
        )

        # Try PubChem
        pubchem_data = self._get_pubchem_data(molecule)
        if pubchem_data:
            self._merge_pubchem(enriched, pubchem_data)
            enriched.sources_used.append("PubChem")

        # Try Wikidata
        wikidata_data = self._get_wikidata_data(molecule, enriched)
        if wikidata_data:
            self._merge_wikidata(enriched, wikidata_data)
            enriched.sources_used.append("Wikidata")

        enriched.enriched_at = datetime.utcnow()
        return enriched

    def _get_pubchem_data(self, molecule: Molecule) -> Optional[PubChemCompound]:
        """Get PubChem data for a molecule."""
        # Try by CID first
        if molecule.pubchem_cid:
            data = self.pubchem.get_compound_by_cid(molecule.pubchem_cid)
            if data:
                return data

        # Try by SMILES
        if molecule.smiles:
            data = self.pubchem.search_by_smiles(molecule.smiles)
            if data:
                return data

        # Try by name
        if molecule.name:
            results = self.pubchem.search_by_name(molecule.name)
            if results:
                return results[0]

        return None

    def _get_wikidata_data(
        self,
        molecule: Molecule,
        enriched: EnrichedMolecule,
    ) -> Optional[WikidataEntity]:
        """Get Wikidata data for a molecule."""
        # Try by CAS number
        if molecule.cas_number:
            data = self.wikidata.get_by_cas(molecule.cas_number)
            if data:
                return data

        # Try by PubChem CID (from enriched data)
        if enriched.pubchem_cid:
            data = self.wikidata.get_by_pubchem_cid(enriched.pubchem_cid)
            if data:
                return data

        # Try by SMILES
        if molecule.smiles:
            data = self.wikidata.get_by_smiles(molecule.smiles)
            if data:
                return data

        return None

    def _merge_pubchem(self, enriched: EnrichedMolecule, data: PubChemCompound) -> None:
        """Merge PubChem data into enriched molecule."""
        enriched.pubchem_cid = data.cid
        enriched.pubchem_iupac_name = data.iupac_name
        enriched.pubchem_synonyms = data.synonyms
        enriched.molecular_formula = data.molecular_formula
        enriched.molecular_weight = data.molecular_weight
        enriched.inchi = data.inchi
        enriched.inchi_key = data.inchi_key

        if data.chebi_id:
            enriched.chebi_id = data.chebi_id
        if data.chembl_id:
            enriched.chembl_id = data.chembl_id

    def _merge_wikidata(self, enriched: EnrichedMolecule, data: WikidataEntity) -> None:
        """Merge Wikidata data into enriched molecule."""
        enriched.wikidata_qid = data.qid
        enriched.wikidata_description = data.description
        enriched.wikidata_uses = data.uses
        enriched.wikidata_classification = data.instance_of + data.subclass_of
        enriched.wikipedia_url = data.wikipedia_url

        # Fill in missing identifiers
        if not enriched.chebi_id and data.chebi_id:
            enriched.chebi_id = data.chebi_id
        if not enriched.chembl_id and data.chembl_id:
            enriched.chembl_id = data.chembl_id
        if not enriched.cas_number and data.cas_number:
            enriched.cas_number = data.cas_number

        # Physical properties
        enriched.melting_point = data.melting_point
        enriched.boiling_point = data.boiling_point
        enriched.density = data.density

    def enrich_all_molecules(self, verbose: bool = True) -> list[EnrichedMolecule]:
        """Enrich all molecules in the KG."""
        results = []
        molecules = list(self.kg._molecules.values())

        if verbose:
            print(f"Enriching {len(molecules)} molecules...")

        for i, mol in enumerate(molecules):
            if verbose:
                print(f"  [{i+1}/{len(molecules)}] {mol.name}...", end=" ")

            enriched = self.enrich_molecule(mol)
            results.append(enriched)

            if verbose:
                sources = ", ".join(enriched.sources_used) or "none"
                print(f"({sources})")

            # Update molecule in KG with new data
            self._update_kg_molecule(mol, enriched)

        if verbose:
            print(f"\nEnriched {len(results)} molecules")
            with_pubchem = sum(1 for r in results if "PubChem" in r.sources_used)
            with_wikidata = sum(1 for r in results if "Wikidata" in r.sources_used)
            print(f"  PubChem: {with_pubchem}")
            print(f"  Wikidata: {with_wikidata}")

        return results

    def _update_kg_molecule(self, mol: Molecule, enriched: EnrichedMolecule) -> None:
        """Update KG molecule with enriched data."""
        # Update identifiers
        if enriched.pubchem_cid and not mol.pubchem_cid:
            mol.pubchem_cid = enriched.pubchem_cid
        if enriched.inchi and not mol.inchi:
            mol.inchi = enriched.inchi
        if enriched.inchi_key and not mol.inchi_key:
            mol.inchi_key = enriched.inchi_key
        if enriched.cas_number and not mol.cas_number:
            mol.cas_number = enriched.cas_number
        if enriched.molecular_weight and not mol.molecular_weight:
            mol.molecular_weight = enriched.molecular_weight

        # Add synonyms
        for syn in enriched.pubchem_synonyms[:5]:
            if syn not in mol.synonyms:
                mol.synonyms.append(syn)

        # Create provenance record
        prov = ProvenanceRecord(
            entity_id=mol.id,
            entity_type="Molecule",
            source_ids=enriched.sources_used,
            agent_id=self._agent.id,
            extraction_method="external_kg_enrichment",
            confidence=1.0,
        )
        self.kg.add_provenance(prov)

    def print_enrichment_report(self, enriched: EnrichedMolecule) -> None:
        """Print a detailed report for an enriched molecule."""
        print(f"\n{'=' * 60}")
        print(f"ENRICHED: {enriched.name}")
        print(f"{'=' * 60}")

        print(f"\nIdentifiers:")
        print(f"  PubChem CID: {enriched.pubchem_cid}")
        print(f"  CAS: {enriched.cas_number}")
        print(f"  ChEBI: {enriched.chebi_id}")
        print(f"  ChEMBL: {enriched.chembl_id}")
        print(f"  Wikidata: {enriched.wikidata_qid}")

        print(f"\nStructure:")
        print(f"  SMILES: {enriched.smiles}")
        print(f"  InChI Key: {enriched.inchi_key}")
        print(f"  Formula: {enriched.molecular_formula}")
        print(f"  MW: {enriched.molecular_weight} g/mol")

        if enriched.wikidata_description:
            print(f"\nDescription: {enriched.wikidata_description}")

        if enriched.wikidata_uses:
            print(f"\nUses: {', '.join(enriched.wikidata_uses[:5])}")

        if enriched.wikidata_classification:
            print(f"\nClassification: {', '.join(enriched.wikidata_classification[:5])}")

        if enriched.wikipedia_url:
            print(f"\nWikipedia: {enriched.wikipedia_url}")

        print(f"\nPhysical Properties:")
        print(f"  Melting point: {enriched.melting_point}")
        print(f"  Boiling point: {enriched.boiling_point}")
        print(f"  Density: {enriched.density}")

        print(f"\nSources: {', '.join(enriched.sources_used)}")
