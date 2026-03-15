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

    def add_molecule(self, molecule: Molecule) -> str:
        """Add a molecule to the KG."""
        self._molecules[molecule.id] = molecule
        self._graph.add_node(molecule.id, type="Molecule", data=molecule)
        return molecule.id

    def add_solvent(self, solvent: Solvent) -> str:
        """Add a solvent to the KG."""
        self._solvents[solvent.id] = solvent
        self._molecules[solvent.id] = solvent
        self._graph.add_node(solvent.id, type="Solvent", data=solvent)
        return solvent.id

    def add_salt(self, salt: Salt) -> str:
        """Add a salt to the KG."""
        self._salts[salt.id] = salt
        self._molecules[salt.id] = salt
        self._graph.add_node(salt.id, type="Salt", data=salt)
        return salt.id

    def add_additive(self, additive: Additive) -> str:
        """Add an additive to the KG."""
        self._additives[additive.id] = additive
        self._molecules[additive.id] = additive
        self._graph.add_node(additive.id, type="Additive", data=additive)
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
