"""Utilities for tracing provenance of KG assertions."""

from typing import Optional
from .graph import KnowledgeGraph


def explain_entity(kg: KnowledgeGraph, entity_id: str) -> dict:
    """
    Explain the provenance of an entity in the KG.

    Returns a dict with:
    - entity_type: Type of entity
    - entity_data: The entity itself
    - provenance: Provenance record(s) for this entity
    - source: EvidenceSource with DOI/URL
    """
    result = {
        "entity_id": entity_id,
        "entity_type": None,
        "entity_data": None,
        "provenance": [],
        "sources": [],
    }

    # Find the entity
    if entity_id in kg._molecules:
        result["entity_type"] = "Molecule"
        result["entity_data"] = kg._molecules[entity_id]
    elif entity_id in kg._solvents:
        result["entity_type"] = "Solvent"
        result["entity_data"] = kg._solvents[entity_id]
    elif entity_id in kg._salts:
        result["entity_type"] = "Salt"
        result["entity_data"] = kg._salts[entity_id]
    elif entity_id in kg._formulations:
        result["entity_type"] = "ElectrolyteFormulation"
        result["entity_data"] = kg._formulations[entity_id]
    elif entity_id in kg._measurements:
        result["entity_type"] = "PropertyMeasurement"
        result["entity_data"] = kg._measurements[entity_id]
    elif entity_id in kg._interphase_species:
        result["entity_type"] = "InterphaseSpecies"
        result["entity_data"] = kg._interphase_species[entity_id]

    # Find provenance records for this entity
    for prov_id, prov in kg._provenance.items():
        if prov.entity_id == entity_id:
            result["provenance"].append({
                "source_doi": prov.source_doi,
                "source_row_id": prov.source_row_id,
                "extraction_method": prov.extraction_method,
                "confidence": prov.confidence,
                "validated": prov.validated,
                "created_at": str(prov.created_at),
            })

            # Get EvidenceSource details
            for source_id in prov.source_ids:
                if source_id in kg._sources:
                    src = kg._sources[source_id]
                    result["sources"].append({
                        "name": src.name,
                        "doi": src.doi,
                        "url": src.url,
                        "source_type": src.source_type,
                    })

    return result


def explain_relation(
    kg: KnowledgeGraph,
    subject_id: str,
    relation: str,
    object_id: str,
) -> dict:
    """
    Explain why a relation exists between two entities.

    Returns provenance for both entities and inference method if applicable.
    """
    result = {
        "relation": relation,
        "subject": explain_entity(kg, subject_id),
        "object": explain_entity(kg, object_id),
        "inference_basis": None,
    }

    # Check if this is a SAME_AS relation (based on SMILES matching)
    if relation == "sameAs":
        subj_data = result["subject"]["entity_data"]
        obj_data = result["object"]["entity_data"]

        if hasattr(subj_data, "smiles") and hasattr(obj_data, "smiles"):
            if subj_data.smiles == obj_data.smiles:
                result["inference_basis"] = {
                    "method": "SMILES_matching",
                    "explanation": f"Both entities have identical SMILES: {subj_data.smiles}",
                }

    # Check if this is a decomposesTo relation
    elif relation == "decomposesTo":
        result["inference_basis"] = {
            "method": "literature_knowledge",
            "explanation": "Decomposition pathway from electrolyte chemistry literature",
        }

    # Check if from hypothesis generation
    elif relation in ["increases", "decreases", "coOccursWith"]:
        # Check hypotheses
        for hyp in kg._hypotheses.values():
            if (hyp.subject_id == subject_id and
                hyp.relation.value == relation and
                hyp.object_id == object_id):
                result["inference_basis"] = {
                    "method": hyp.source.value,
                    "confidence": hyp.confidence,
                    "supporting_evidence": hyp.supporting_evidence,
                    "explanation": hyp.explanation,
                }
                break

    return result


def trace_measurement(kg: KnowledgeGraph, measurement_id: str) -> dict:
    """
    Trace a measurement back to its original source.

    Returns the full chain: measurement -> formulation -> source dataset.
    """
    result = {
        "measurement": None,
        "formulation": None,
        "source_dataset": None,
        "original_row": None,
    }

    if measurement_id not in kg._measurements:
        return result

    meas = kg._measurements[measurement_id]
    result["measurement"] = {
        "property_type": meas.property_type.value if hasattr(meas.property_type, 'value') else str(meas.property_type),
        "value": meas.value,
        "unit": meas.unit,
        "temperature": meas.temperature,
    }

    # Find formulation that has this measurement
    for form_id, form in kg._formulations.items():
        if measurement_id in form.measurements:
            result["formulation"] = {
                "id": form_id,
                "name": form.name,
            }

            # Find provenance for formulation
            for prov in kg._provenance.values():
                if prov.entity_id == form_id:
                    result["source_dataset"] = prov.source_doi
                    result["original_row"] = prov.source_row_id
                    break
            break

    return result
