"""Relation type definitions for the electrolyte KG."""

from enum import Enum


class RelationType(str, Enum):
    """Types of relations in the KG."""

    # Formulation composition relations
    HAS_SOLVENT = "hasSolvent"
    HAS_SALT = "hasSalt"
    HAS_ADDITIVE = "hasAdditive"
    HAS_COMPONENT = "hasComponent"
    HAS_AMOUNT = "hasAmount"

    # Property measurement relations
    HAS_MEASUREMENT = "hasMeasurement"
    MEASURES_PROPERTY = "measuresProperty"
    MEASURED_BY = "measuredBy"
    MEASURED_AT = "measuredAt"
    DERIVED_FROM = "derivedFrom"

    # Interphase/SEI relations
    DECOMPOSES_TO = "decomposesTo"
    PARTICIPATES_IN_REACTION = "participatesInReaction"
    ASSOCIATED_WITH_SEI = "associatedWithSEI"
    FORMS_SPECIES = "formsSpecies"

    # Discovery/hypothesis relations
    HYPOTHESIZED_RELATION = "hypothesizedRelation"
    EVIDENCE_FOR = "evidenceFor"
    VALIDATED_BY = "validatedBy"
    CONTRADICTS = "contradicts"

    # Molecular relations
    IS_ISOMER_OF = "isIsomerOf"
    HAS_FUNCTIONAL_GROUP = "hasFunctionalGroup"
    SIMILAR_TO = "similarTo"
    SAME_AS = "sameAs"  # Identity relation for cross-dataset linking

    # Causal/effect relations (for hypotheses)
    INCREASES = "increases"
    DECREASES = "decreases"
    AFFECTS = "affects"
    CORRELATES_WITH = "correlatesWith"
    CO_OCCURS_WITH = "coOccursWith"


# Define valid domain-range pairs for relations
RELATION_CONSTRAINTS = {
    RelationType.HAS_SOLVENT: {
        "domain": "ElectrolyteFormulation",
        "range": "Solvent",
    },
    RelationType.HAS_SALT: {
        "domain": "ElectrolyteFormulation",
        "range": "Salt",
    },
    RelationType.HAS_ADDITIVE: {
        "domain": "ElectrolyteFormulation",
        "range": "Additive",
    },
    RelationType.HAS_MEASUREMENT: {
        "domain": "ElectrolyteFormulation",
        "range": "PropertyMeasurement",
    },
    RelationType.DECOMPOSES_TO: {
        "domain": "Molecule",
        "range": "InterphaseSpecies",
    },
    RelationType.INCREASES: {
        "domain": ["Additive", "Solvent", "Salt"],
        "range": "PropertyType",
    },
    RelationType.DECREASES: {
        "domain": ["Additive", "Solvent", "Salt"],
        "range": "PropertyType",
    },
    RelationType.CO_OCCURS_WITH: {
        "domain": "Molecule",
        "range": "Molecule",
    },
}
