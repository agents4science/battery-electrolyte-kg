"""Main Knowledge Graph class with entity storage and querying."""

from datetime import datetime
from typing import Optional, Any, TypeVar, Type
from pathlib import Path
import json
import networkx as nx
from pydantic import BaseModel

from ..schema.entities import (
    Molecule, Solvent, Salt, Additive,
    ElectrolyteFormulation, FormulationComponent,
    PropertyMeasurement, MeasurementMethod,
    InterphaseSpecies, EvidenceSource,
    ComponentType, PropertyType, PropertyTypeEntity,
)
from ..schema.provenance import ProvenanceRecord, Agent, ProvenanceActivity, KGVersion
from ..schema.hypothesis import HypothesisEdge, HypothesisStatus
from ..schema.relations import RelationType


T = TypeVar("T", bound=BaseModel)


def canonicalize_smiles(smiles: Optional[str]) -> Optional[str]:
    """
    Canonicalize a SMILES string for deduplication.

    Uses RDKit if available, otherwise returns the input unchanged.
    """
    if not smiles:
        return None

    # Try RDKit for proper canonicalization
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol:
            return Chem.MolToSmiles(mol, canonical=True)
    except ImportError:
        pass

    # Fallback: return as-is (not ideal but works for exact matches)
    return smiles.strip()


class KnowledgeGraph:
    """
    Main Knowledge Graph for electrolyte discovery.

    Stores entities, relations, provenance, and hypotheses.
    Uses NetworkX for graph operations and supports export to RDF.
    """

    def __init__(self, version: str = "0.1.0"):
        self.version = version
        self.created_at = datetime.utcnow()

        # Graph structure for relations (initialize first)
        self._graph = nx.MultiDiGraph()

        # Entity stores (by type)
        self._molecules: dict[str, Molecule] = {}
        self._solvents: dict[str, Solvent] = {}
        self._salts: dict[str, Salt] = {}
        self._additives: dict[str, Additive] = {}
        self._formulations: dict[str, ElectrolyteFormulation] = {}
        self._measurements: dict[str, PropertyMeasurement] = {}
        self._methods: dict[str, MeasurementMethod] = {}
        self._interphase_species: dict[str, InterphaseSpecies] = {}
        self._sources: dict[str, EvidenceSource] = {}

        # SMILES deduplication index: canonical_smiles -> molecule_id
        self._smiles_to_molecule_id: dict[str, str] = {}

        # Property types (auto-initialized after graph)
        self._property_types: dict[str, PropertyTypeEntity] = {}
        self._init_property_types()

        # Provenance
        self._provenance: dict[str, ProvenanceRecord] = {}
        self._agents: dict[str, Agent] = {}
        self._activities: dict[str, ProvenanceActivity] = {}

        # Hypotheses
        self._hypotheses: dict[str, HypothesisEdge] = {}

        # Version history
        self._versions: list[KGVersion] = []

    # --- Initialization ---

    def _init_property_types(self) -> None:
        """Initialize property type entities for grounding."""
        for prop_type in PropertyType:
            entity = PropertyTypeEntity.from_enum(prop_type)
            self._property_types[entity.id] = entity
            self._graph.add_node(entity.id, type="PropertyType", data=entity)

    def get_property_type_id(self, prop_type: PropertyType) -> str:
        """Get the entity ID for a property type."""
        return prop_type.entity_id

    # --- Entity Management ---

    def _find_existing_molecule_by_smiles(self, smiles: Optional[str]) -> Optional[str]:
        """Find an existing molecule ID by canonical SMILES."""
        if not smiles:
            return None
        canonical = canonicalize_smiles(smiles)
        if canonical:
            return self._smiles_to_molecule_id.get(canonical)
        return None

    def _index_molecule_smiles(self, molecule_id: str, smiles: Optional[str]) -> None:
        """Add molecule to SMILES index."""
        if smiles:
            canonical = canonicalize_smiles(smiles)
            if canonical:
                self._smiles_to_molecule_id[canonical] = molecule_id

    def _merge_molecule_data(self, existing: Molecule, new: Molecule) -> Molecule:
        """
        Merge data from a new molecule into an existing one.

        Prefers the better name (longer, non-SMILES), merges synonyms.
        """
        # Prefer longer, non-SMILES name
        existing_name = existing.name or ""
        new_name = new.name or ""

        # Check if name looks like SMILES (contains special chars)
        def is_smiles_like(name: str) -> bool:
            return any(c in name for c in "()[]=#@+-/\\")

        if is_smiles_like(existing_name) and not is_smiles_like(new_name) and new_name:
            existing.name = new_name
        elif len(new_name) > len(existing_name) and not is_smiles_like(new_name):
            existing.name = new_name

        # Merge synonyms
        existing_synonyms = set(existing.synonyms or [])
        new_synonyms = set(new.synonyms or [])
        # Add old name as synonym if replaced
        if existing_name and existing_name != existing.name:
            existing_synonyms.add(existing_name)
        if new_name and new_name != existing.name:
            new_synonyms.add(new_name)
        existing.synonyms = list(existing_synonyms | new_synonyms)

        # Merge other fields (prefer non-None values)
        if new.inchi and not existing.inchi:
            existing.inchi = new.inchi
        if new.inchi_key and not existing.inchi_key:
            existing.inchi_key = new.inchi_key
        if new.pubchem_cid and not existing.pubchem_cid:
            existing.pubchem_cid = new.pubchem_cid
        if new.cas_number and not existing.cas_number:
            existing.cas_number = new.cas_number
        if new.molecular_weight and not existing.molecular_weight:
            existing.molecular_weight = new.molecular_weight

        return existing

    def add_molecule(self, molecule: Molecule, deduplicate: bool = True) -> str:
        """
        Add a molecule to the KG.

        If deduplicate=True and a molecule with the same SMILES exists,
        merges the data and returns the existing molecule's ID.
        """
        if deduplicate and molecule.smiles:
            existing_id = self._find_existing_molecule_by_smiles(molecule.smiles)
            if existing_id and existing_id in self._molecules:
                # Merge into existing
                self._molecules[existing_id] = self._merge_molecule_data(
                    self._molecules[existing_id], molecule
                )
                return existing_id

        # Add as new molecule
        self._molecules[molecule.id] = molecule
        self._graph.add_node(molecule.id, type="Molecule", data=molecule)
        self._index_molecule_smiles(molecule.id, molecule.smiles)
        return molecule.id

    def add_solvent(self, solvent: Solvent, deduplicate: bool = True) -> str:
        """Add a solvent to the KG, deduplicating by SMILES."""
        if deduplicate and solvent.smiles:
            existing_id = self._find_existing_molecule_by_smiles(solvent.smiles)
            if existing_id and existing_id in self._molecules:
                self._molecules[existing_id] = self._merge_molecule_data(
                    self._molecules[existing_id], solvent
                )
                # Also mark as solvent if not already
                if existing_id not in self._solvents:
                    self._solvents[existing_id] = self._molecules[existing_id]
                return existing_id

        self._solvents[solvent.id] = solvent
        self._molecules[solvent.id] = solvent
        self._graph.add_node(solvent.id, type="Solvent", data=solvent)
        self._index_molecule_smiles(solvent.id, solvent.smiles)
        return solvent.id

    def add_salt(self, salt: Salt, deduplicate: bool = True) -> str:
        """Add a salt to the KG, deduplicating by SMILES."""
        if deduplicate and salt.smiles:
            existing_id = self._find_existing_molecule_by_smiles(salt.smiles)
            if existing_id and existing_id in self._molecules:
                self._molecules[existing_id] = self._merge_molecule_data(
                    self._molecules[existing_id], salt
                )
                if existing_id not in self._salts:
                    self._salts[existing_id] = self._molecules[existing_id]
                return existing_id

        self._salts[salt.id] = salt
        self._molecules[salt.id] = salt
        self._graph.add_node(salt.id, type="Salt", data=salt)
        self._index_molecule_smiles(salt.id, salt.smiles)
        return salt.id

    def add_additive(self, additive: Additive, deduplicate: bool = True) -> str:
        """Add an additive to the KG, deduplicating by SMILES."""
        if deduplicate and additive.smiles:
            existing_id = self._find_existing_molecule_by_smiles(additive.smiles)
            if existing_id and existing_id in self._molecules:
                self._molecules[existing_id] = self._merge_molecule_data(
                    self._molecules[existing_id], additive
                )
                if existing_id not in self._additives:
                    self._additives[existing_id] = self._molecules[existing_id]
                return existing_id

        self._additives[additive.id] = additive
        self._molecules[additive.id] = additive
        self._graph.add_node(additive.id, type="Additive", data=additive)
        self._index_molecule_smiles(additive.id, additive.smiles)
        return additive.id

    def add_formulation(self, formulation: ElectrolyteFormulation) -> str:
        """Add a formulation to the KG."""
        self._formulations[formulation.id] = formulation
        self._graph.add_node(formulation.id, type="ElectrolyteFormulation", data=formulation)

        # Add edges for components
        for comp in formulation.components:
            if comp.molecule_id in self._molecules:
                rel = self._component_type_to_relation(comp.component_type)
                self.add_relation(formulation.id, rel, comp.molecule_id)

        return formulation.id

    def add_measurement(self, measurement: PropertyMeasurement) -> str:
        """Add a property measurement to the KG."""
        self._measurements[measurement.id] = measurement
        self._graph.add_node(measurement.id, type="PropertyMeasurement", data=measurement)
        return measurement.id

    def add_interphase_species(self, species: InterphaseSpecies) -> str:
        """Add an interphase species to the KG."""
        self._interphase_species[species.id] = species
        self._graph.add_node(species.id, type="InterphaseSpecies", data=species)
        return species.id

    def add_source(self, source: EvidenceSource) -> str:
        """Add an evidence source to the KG."""
        self._sources[source.id] = source
        self._graph.add_node(source.id, type="EvidenceSource", data=source)
        return source.id

    def add_method(self, method: MeasurementMethod) -> str:
        """Add a measurement method to the KG."""
        self._methods[method.id] = method
        self._graph.add_node(method.id, type="MeasurementMethod", data=method)
        return method.id

    # --- Relation Management ---

    def add_relation(
        self,
        subject_id: str,
        relation: RelationType,
        object_id: str,
        provenance: Optional[ProvenanceRecord] = None,
    ) -> None:
        """Add a relation (edge) between two entities."""
        self._graph.add_edge(
            subject_id,
            object_id,
            relation=relation.value,
            provenance_id=provenance.id if provenance else None,
        )
        if provenance:
            self._provenance[provenance.id] = provenance

    def get_relations(
        self,
        subject_id: Optional[str] = None,
        relation: Optional[RelationType] = None,
        object_id: Optional[str] = None,
    ) -> list[tuple[str, str, str]]:
        """Query relations by subject, relation type, and/or object."""
        results = []
        for u, v, data in self._graph.edges(data=True):
            if subject_id and u != subject_id:
                continue
            if object_id and v != object_id:
                continue
            if relation and data.get("relation") != relation.value:
                continue
            results.append((u, data.get("relation"), v))
        return results

    # --- Hypothesis Management ---

    def add_hypothesis(self, hypothesis: HypothesisEdge) -> str:
        """Add a hypothesis edge to the KG."""
        self._hypotheses[hypothesis.id] = hypothesis
        return hypothesis.id

    def get_hypotheses(
        self,
        status: Optional[HypothesisStatus] = None,
        is_novel: Optional[bool] = None,
    ) -> list[HypothesisEdge]:
        """Get hypotheses filtered by status and/or novelty."""
        results = []
        for h in self._hypotheses.values():
            if status and h.status != status:
                continue
            if is_novel is not None and h.is_novel != is_novel:
                continue
            results.append(h)
        return results

    def merge_validated_hypothesis(self, hypothesis_id: str) -> bool:
        """Merge a validated hypothesis into the KG as a real edge."""
        hypothesis = self._hypotheses.get(hypothesis_id)
        if not hypothesis or hypothesis.status != HypothesisStatus.VALIDATED:
            return False

        # Create provenance for the merged edge
        prov = ProvenanceRecord(
            entity_id=hypothesis_id,
            entity_type="merged_hypothesis",
            source_ids=hypothesis.supporting_evidence,
            extraction_method=f"hypothesis_validation:{hypothesis.source.value}",
            confidence=hypothesis.confidence,
            validated=True,
            validation_method=hypothesis.validated_by,
            validation_date=hypothesis.validated_at,
        )

        # Add the relation
        self.add_relation(
            hypothesis.subject_id,
            hypothesis.relation,
            hypothesis.object_id,
            provenance=prov,
        )
        return True

    # --- Provenance Management ---

    def add_provenance(self, provenance: ProvenanceRecord) -> str:
        """Add a provenance record."""
        self._provenance[provenance.id] = provenance
        return provenance.id

    def add_agent(self, agent: Agent) -> str:
        """Add an agent."""
        self._agents[agent.id] = agent
        return agent.id

    def get_provenance_completeness(self) -> float:
        """Calculate provenance completeness (fraction of entities with provenance)."""
        total_entities = (
            len(self._formulations) +
            len(self._measurements) +
            len(self._hypotheses)
        )
        if total_entities == 0:
            return 1.0

        entities_with_prov = sum(
            1 for p in self._provenance.values() if p.is_complete()
        )
        return entities_with_prov / total_entities

    # --- Deduplication ---

    def deduplicate_molecules(self) -> dict:
        """
        Post-process the KG to merge duplicate molecules with the same SMILES.

        This method:
        1. Groups molecules by canonical SMILES
        2. For each group, keeps the molecule with the best name
        3. Merges all data (synonyms, properties) into the kept molecule
        4. Updates all relations to point to the kept molecule
        5. Removes duplicate molecules

        Returns statistics about the deduplication.
        """
        from collections import defaultdict

        stats = {
            "molecules_before": len(self._molecules),
            "duplicates_found": 0,
            "molecules_merged": 0,
            "relations_updated": 0,
        }

        # Group molecules by canonical SMILES
        smiles_groups: dict[str, list[str]] = defaultdict(list)
        for mol_id, mol in self._molecules.items():
            if mol.smiles:
                canonical = canonicalize_smiles(mol.smiles)
                if canonical:
                    smiles_groups[canonical].append(mol_id)

        # Find groups with duplicates
        duplicate_groups = {s: ids for s, ids in smiles_groups.items() if len(ids) > 1}
        stats["duplicates_found"] = sum(len(ids) - 1 for ids in duplicate_groups.values())

        # Process each group
        id_mapping: dict[str, str] = {}  # old_id -> new_id

        for canonical_smiles, mol_ids in duplicate_groups.items():
            # Pick the best molecule to keep (prefer longer, non-SMILES name)
            def name_score(mol_id: str) -> tuple:
                mol = self._molecules[mol_id]
                name = mol.name or ""
                is_smiles = any(c in name for c in "()[]=#@+-/\\")
                return (not is_smiles, len(name))

            mol_ids_sorted = sorted(mol_ids, key=name_score, reverse=True)
            keep_id = mol_ids_sorted[0]
            remove_ids = mol_ids_sorted[1:]

            # Merge all molecules into the kept one
            keep_mol = self._molecules[keep_id]
            for remove_id in remove_ids:
                remove_mol = self._molecules[remove_id]
                self._merge_molecule_data(keep_mol, remove_mol)
                id_mapping[remove_id] = keep_id
                stats["molecules_merged"] += 1

        # Update relations to use new IDs
        if id_mapping:
            new_edges = []
            edges_to_remove = []

            for u, v, key, data in self._graph.edges(keys=True, data=True):
                new_u = id_mapping.get(u, u)
                new_v = id_mapping.get(v, v)
                if new_u != u or new_v != v:
                    edges_to_remove.append((u, v, key))
                    new_edges.append((new_u, new_v, data))
                    stats["relations_updated"] += 1

            for u, v, key in edges_to_remove:
                self._graph.remove_edge(u, v, key)

            for new_u, new_v, data in new_edges:
                self._graph.add_edge(new_u, new_v, **data)

            # Update formulation component references
            for form in self._formulations.values():
                for comp in form.components:
                    if comp.molecule_id in id_mapping:
                        comp.molecule_id = id_mapping[comp.molecule_id]

            # Remove duplicate molecules from stores
            for old_id in id_mapping:
                if old_id in self._molecules:
                    del self._molecules[old_id]
                if old_id in self._solvents:
                    del self._solvents[old_id]
                if old_id in self._salts:
                    del self._salts[old_id]
                if old_id in self._additives:
                    del self._additives[old_id]
                if self._graph.has_node(old_id):
                    self._graph.remove_node(old_id)

        # Rebuild SMILES index
        self._smiles_to_molecule_id.clear()
        for mol_id, mol in self._molecules.items():
            self._index_molecule_smiles(mol_id, mol.smiles)

        stats["molecules_after"] = len(self._molecules)
        return stats

    # --- Querying ---

    def get_entity(self, entity_id: str) -> Optional[BaseModel]:
        """Get any entity by ID."""
        for store in [
            self._molecules, self._formulations, self._measurements,
            self._interphase_species, self._sources, self._methods,
        ]:
            if entity_id in store:
                return store[entity_id]
        return None

    def get_formulation(self, formulation_id: str) -> Optional[ElectrolyteFormulation]:
        """Get a formulation by ID."""
        return self._formulations.get(formulation_id)

    def get_molecule(self, molecule_id: str) -> Optional[Molecule]:
        """Get a molecule by ID."""
        return self._molecules.get(molecule_id)

    def find_formulations_by_component(
        self,
        molecule_id: str,
    ) -> list[ElectrolyteFormulation]:
        """Find all formulations containing a specific molecule."""
        results = []
        for f in self._formulations.values():
            for comp in f.components:
                if comp.molecule_id == molecule_id:
                    results.append(f)
                    break
        return results

    def find_formulations_by_property(
        self,
        property_type: PropertyType,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        temperature: Optional[float] = None,
    ) -> list[tuple[ElectrolyteFormulation, PropertyMeasurement]]:
        """Find formulations with property values in a range."""
        results = []
        for f in self._formulations.values():
            for m_id in f.measurements:
                m = self._measurements.get(m_id)
                if not m or m.property_type != property_type:
                    continue
                if min_value is not None and m.value < min_value:
                    continue
                if max_value is not None and m.value > max_value:
                    continue
                if temperature is not None and m.temperature != temperature:
                    continue
                results.append((f, m))
        return results

    # --- Statistics ---

    def stats(self) -> dict[str, Any]:
        """Return KG statistics."""
        return {
            "version": self.version,
            "num_molecules": len(self._molecules),
            "num_solvents": len(self._solvents),
            "num_salts": len(self._salts),
            "num_additives": len(self._additives),
            "num_formulations": len(self._formulations),
            "num_measurements": len(self._measurements),
            "num_interphase_species": len(self._interphase_species),
            "num_sources": len(self._sources),
            "num_methods": len(self._methods),
            "num_property_types": len(self._property_types),
            "num_relations": self._graph.number_of_edges(),
            "num_hypotheses": len(self._hypotheses),
            "num_hypotheses_validated": sum(
                1 for h in self._hypotheses.values()
                if h.status == HypothesisStatus.VALIDATED
            ),
            "provenance_completeness": self.get_provenance_completeness(),
        }

    # --- Export/Import ---

    def to_triples(self) -> list[tuple[str, str, str]]:
        """Export all relations as (subject, relation, object) triples."""
        return [
            (u, data.get("relation"), v)
            for u, v, data in self._graph.edges(data=True)
        ]

    def save(self, path: Path | str) -> None:
        """Save KG to disk as JSON."""
        path = Path(path)
        data = {
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "molecules": {k: v.model_dump() for k, v in self._molecules.items()},
            "formulations": {k: v.model_dump() for k, v in self._formulations.items()},
            "measurements": {k: v.model_dump() for k, v in self._measurements.items()},
            "interphase_species": {k: v.model_dump() for k, v in self._interphase_species.items()},
            "sources": {k: v.model_dump() for k, v in self._sources.items()},
            "methods": {k: v.model_dump() for k, v in self._methods.items()},
            "property_types": {k: v.model_dump() for k, v in self._property_types.items()},
            "provenance": {k: v.model_dump() for k, v in self._provenance.items()},
            "hypotheses": {k: v.model_dump() for k, v in self._hypotheses.items()},
            "relations": self.to_triples(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    @classmethod
    def load(cls, path: Path) -> "KnowledgeGraph":
        """Load KG from disk."""
        with open(path) as f:
            data = json.load(f)

        kg = cls(version=data.get("version", "0.1.0"))

        # Load entities
        for k, v in data.get("molecules", {}).items():
            kg._molecules[k] = Molecule(**v)

        for k, v in data.get("formulations", {}).items():
            kg._formulations[k] = ElectrolyteFormulation(**v)

        for k, v in data.get("measurements", {}).items():
            kg._measurements[k] = PropertyMeasurement(**v)

        for k, v in data.get("interphase_species", {}).items():
            kg._interphase_species[k] = InterphaseSpecies(**v)

        for k, v in data.get("sources", {}).items():
            kg._sources[k] = EvidenceSource(**v)

        for k, v in data.get("methods", {}).items():
            kg._methods[k] = MeasurementMethod(**v)

        for k, v in data.get("provenance", {}).items():
            kg._provenance[k] = ProvenanceRecord(**v)

        for k, v in data.get("hypotheses", {}).items():
            kg._hypotheses[k] = HypothesisEdge(**v)

        # Rebuild graph
        for entity_id in kg._molecules:
            kg._graph.add_node(entity_id, type="Molecule")
        for entity_id in kg._formulations:
            kg._graph.add_node(entity_id, type="ElectrolyteFormulation")
        for entity_id in kg._measurements:
            kg._graph.add_node(entity_id, type="PropertyMeasurement")
        for entity_id in kg._methods:
            kg._graph.add_node(entity_id, type="MeasurementMethod")
        for entity_id in kg._sources:
            kg._graph.add_node(entity_id, type="EvidenceSource")

        for s, r, o in data.get("relations", []):
            kg._graph.add_edge(s, o, relation=r)

        return kg

    # --- Helpers ---

    def _component_type_to_relation(self, comp_type: ComponentType) -> RelationType:
        """Map component type to relation type."""
        mapping = {
            ComponentType.SOLVENT: RelationType.HAS_SOLVENT,
            ComponentType.SALT: RelationType.HAS_SALT,
            ComponentType.ADDITIVE: RelationType.HAS_ADDITIVE,
        }
        return mapping.get(comp_type, RelationType.HAS_COMPONENT)
