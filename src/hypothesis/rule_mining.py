"""Rule mining for hypothesis generation."""

from typing import Optional
from dataclasses import dataclass, field
from collections import defaultdict
import numpy as np

from ..kg_store.graph import KnowledgeGraph
from ..schema.entities import PropertyType, ComponentType
from ..schema.hypothesis import HypothesisEdge, HypothesisSource, HypothesisStatus
from ..schema.relations import RelationType


@dataclass
class Rule:
    """A mined rule from the KG."""
    head_relation: str  # The relation being predicted
    body: list[tuple[str, str, str]]  # List of (subject_var, relation, object_var)
    confidence: float
    support: int  # Number of supporting examples
    head_coverage: float  # Fraction of head relation instances covered
    description: str = ""
    target_entity_id: Optional[str] = None  # For co-occurrence: the predicted entity

    def __str__(self):
        body_str = " ∧ ".join([f"{s} {r} {o}" for s, r, o in self.body])
        return f"{body_str} → ?x {self.head_relation} ?y (conf={self.confidence:.3f}, sup={self.support})"


@dataclass
class PropertyPattern:
    """A pattern relating formulation composition to properties."""
    component_type: ComponentType
    component_id: str
    component_name: str
    property_type: PropertyType
    effect: str  # "increases", "decreases", "correlates"
    correlation: float
    num_samples: int
    mean_with: float
    mean_without: float
    description: str = ""


class RuleMiner:
    """
    Mine association rules and patterns from the KG.

    Discovers rules like:
    - "If formulation contains X and Y, then conductivity is high"
    - "Additive X increases conductivity in EC-based formulations"
    """

    def __init__(self, kg: KnowledgeGraph):
        self.kg = kg
        self._rules: list[Rule] = []
        self._patterns: list[PropertyPattern] = []

    def mine_composition_property_patterns(
        self,
        property_type: PropertyType = PropertyType.IONIC_CONDUCTIVITY,
        min_samples: int = 5,
        min_correlation: float = 0.1,
    ) -> list[PropertyPattern]:
        """
        Mine patterns relating composition to properties.

        Finds which components correlate with high/low property values.
        """
        patterns = []

        # Get all formulations with measurements
        formulations_with_props = []
        for f in self.kg._formulations.values():
            for m_id in f.measurements:
                m = self.kg._measurements.get(m_id)
                if m and m.property_type == property_type:
                    formulations_with_props.append((f, m.value))

        if len(formulations_with_props) < min_samples:
            return patterns

        # For each component, check correlation with property
        component_formulations = defaultdict(list)
        all_values = []

        for f, prop_value in formulations_with_props:
            all_values.append(prop_value)
            for comp in f.components:
                component_formulations[comp.molecule_id].append(prop_value)

        overall_mean = np.mean(all_values)

        # Find components with significant effect
        for mol_id, values in component_formulations.items():
            if len(values) < min_samples:
                continue

            mol = self.kg.get_molecule(mol_id)
            if not mol:
                continue

            mean_with = np.mean(values)
            without_values = [
                v for f, v in formulations_with_props
                if mol_id not in [c.molecule_id for c in f.components]
            ]

            if len(without_values) < min_samples:
                continue

            mean_without = np.mean(without_values)

            # Calculate effect size
            effect_size = (mean_with - mean_without) / (np.std(all_values) + 1e-8)

            if abs(effect_size) < min_correlation:
                continue

            effect = "increases" if effect_size > 0 else "decreases"

            # Determine component type
            comp_type = ComponentType.SOLVENT
            if mol_id in self.kg._salts:
                comp_type = ComponentType.SALT
            elif mol_id in self.kg._additives:
                comp_type = ComponentType.ADDITIVE

            pattern = PropertyPattern(
                component_type=comp_type,
                component_id=mol_id,
                component_name=mol.name,
                property_type=property_type,
                effect=effect,
                correlation=effect_size,
                num_samples=len(values),
                mean_with=mean_with,
                mean_without=mean_without,
                description=f"{mol.name} {effect} {property_type.value} "
                           f"(effect size: {effect_size:.2f}, n={len(values)})",
            )
            patterns.append(pattern)

        # Sort by absolute correlation
        patterns.sort(key=lambda p: abs(p.correlation), reverse=True)
        self._patterns = patterns
        return patterns

    def mine_co_occurrence_rules(
        self,
        min_support: int = 3,
        min_confidence: float = 0.5,
    ) -> list[Rule]:
        """
        Mine co-occurrence rules for components.

        Finds patterns like "formulations with EC often also have EMC".
        """
        rules = []

        # Count component co-occurrences
        component_counts = defaultdict(int)
        pair_counts = defaultdict(int)

        for f in self.kg._formulations.values():
            comp_ids = [c.molecule_id for c in f.components]
            for comp_id in comp_ids:
                component_counts[comp_id] += 1

            for i, c1 in enumerate(comp_ids):
                for c2 in comp_ids[i+1:]:
                    pair_key = tuple(sorted([c1, c2]))
                    pair_counts[pair_key] += 1

        # Generate rules
        for (c1, c2), count in pair_counts.items():
            if count < min_support:
                continue

            # Rule: c1 -> c2
            conf1 = count / component_counts[c1]
            if conf1 >= min_confidence:
                mol1 = self.kg.get_molecule(c1)
                mol2 = self.kg.get_molecule(c2)
                rule = Rule(
                    head_relation="co-occurs-with",
                    body=[("?f", "hasComponent", c1)],
                    confidence=conf1,
                    support=count,
                    head_coverage=count / component_counts[c2],
                    description=f"If formulation has {mol1.name if mol1 else c1}, "
                               f"it likely has {mol2.name if mol2 else c2}",
                    target_entity_id=c2,  # The predicted molecule
                )
                rules.append(rule)

            # Rule: c2 -> c1
            conf2 = count / component_counts[c2]
            if conf2 >= min_confidence:
                mol1 = self.kg.get_molecule(c1)
                mol2 = self.kg.get_molecule(c2)
                rule = Rule(
                    head_relation="co-occurs-with",
                    body=[("?f", "hasComponent", c2)],
                    confidence=conf2,
                    support=count,
                    head_coverage=count / component_counts[c1],
                    description=f"If formulation has {mol2.name if mol2 else c2}, "
                               f"it likely has {mol1.name if mol1 else c1}",
                    target_entity_id=c1,  # The predicted molecule
                )
                rules.append(rule)

        rules.sort(key=lambda r: r.confidence, reverse=True)
        self._rules = rules
        return rules

    def mine_property_threshold_rules(
        self,
        property_type: PropertyType = PropertyType.IONIC_CONDUCTIVITY,
        high_percentile: float = 75,
        low_percentile: float = 25,
        min_support: int = 3,
        min_confidence: float = 0.6,
    ) -> list[Rule]:
        """
        Mine rules predicting high/low property values.

        Finds patterns like "EC > 30% and LiPF6 > 1M -> high conductivity".
        """
        rules = []

        # Collect property values
        formulation_props = []
        for f in self.kg._formulations.values():
            for m_id in f.measurements:
                m = self.kg._measurements.get(m_id)
                if m and m.property_type == property_type:
                    formulation_props.append((f, m.value))

        if len(formulation_props) < min_support * 2:
            return rules

        # Calculate thresholds
        values = [v for _, v in formulation_props]
        high_threshold = np.percentile(values, high_percentile)
        low_threshold = np.percentile(values, low_percentile)

        # Label formulations
        high_forms = [(f, v) for f, v in formulation_props if v >= high_threshold]
        low_forms = [(f, v) for f, v in formulation_props if v <= low_threshold]

        # Find component patterns in high-value formulations
        high_components = defaultdict(int)
        for f, _ in high_forms:
            for comp in f.components:
                high_components[comp.molecule_id] += 1

        low_components = defaultdict(int)
        for f, _ in low_forms:
            for comp in f.components:
                low_components[comp.molecule_id] += 1

        all_components = defaultdict(int)
        for f, _ in formulation_props:
            for comp in f.components:
                all_components[comp.molecule_id] += 1

        # Generate rules for high property
        for comp_id, high_count in high_components.items():
            if high_count < min_support:
                continue

            total_count = all_components[comp_id]
            confidence = high_count / total_count

            if confidence >= min_confidence:
                mol = self.kg.get_molecule(comp_id)
                rule = Rule(
                    head_relation=f"high_{property_type.value}",
                    body=[("?f", "hasComponent", comp_id)],
                    confidence=confidence,
                    support=high_count,
                    head_coverage=high_count / len(high_forms),
                    description=f"{mol.name if mol else comp_id} -> high {property_type.value}",
                )
                rules.append(rule)

        # Generate rules for low property
        for comp_id, low_count in low_components.items():
            if low_count < min_support:
                continue

            total_count = all_components[comp_id]
            confidence = low_count / total_count

            if confidence >= min_confidence:
                mol = self.kg.get_molecule(comp_id)
                rule = Rule(
                    head_relation=f"low_{property_type.value}",
                    body=[("?f", "hasComponent", comp_id)],
                    confidence=confidence,
                    support=low_count,
                    head_coverage=low_count / len(low_forms),
                    description=f"{mol.name if mol else comp_id} -> low {property_type.value}",
                )
                rules.append(rule)

        rules.sort(key=lambda r: r.confidence, reverse=True)
        return rules

    def mine_amount_property_correlations(
        self,
        property_type: PropertyType = PropertyType.IONIC_CONDUCTIVITY,
        min_correlation: float = 0.1,
        temperature_range: tuple[float, float] = (15, 25),
    ) -> list[PropertyPattern]:
        """
        Mine correlations between component AMOUNTS and property values.

        Unlike mine_composition_property_patterns which looks at presence/absence,
        this looks at how the amount of each component correlates with properties.
        """
        patterns = []

        # Collect composition-property data
        data = []
        for f in self.kg._formulations.values():
            for m_id in f.measurements:
                m = self.kg._measurements.get(m_id)
                if not m or m.property_type != property_type:
                    continue
                if m.temperature and not (temperature_range[0] <= m.temperature <= temperature_range[1]):
                    continue

                row = {"property_value": m.value}
                for c in f.components:
                    mol = self.kg._molecules.get(c.molecule_id)
                    if mol:
                        row[c.molecule_id] = c.amount
                        row[f"{c.molecule_id}_name"] = mol.name
                        row[f"{c.molecule_id}_type"] = c.component_type
                data.append(row)

        if len(data) < 10:
            return patterns

        # Calculate correlations for each component
        property_values = np.array([d["property_value"] for d in data])

        component_ids = set()
        for d in data:
            for k in d:
                if not k.endswith("_name") and not k.endswith("_type") and k != "property_value":
                    component_ids.add(k)

        for comp_id in component_ids:
            amounts = []
            for d in data:
                amounts.append(d.get(comp_id, 0))
            amounts = np.array(amounts)

            if np.std(amounts) < 1e-6:
                continue

            # Calculate Pearson correlation
            corr = np.corrcoef(amounts, property_values)[0, 1]

            if np.isnan(corr) or abs(corr) < min_correlation:
                continue

            # Get component info
            comp_name = data[0].get(f"{comp_id}_name", comp_id)
            comp_type = data[0].get(f"{comp_id}_type", ComponentType.SOLVENT)

            effect = "increases" if corr > 0 else "decreases"
            strength = "strongly" if abs(corr) > 0.3 else "moderately" if abs(corr) > 0.2 else "weakly"

            pattern = PropertyPattern(
                component_type=comp_type,
                component_id=comp_id,
                component_name=comp_name,
                property_type=property_type,
                effect=effect,
                correlation=corr,
                num_samples=len(data),
                mean_with=float(np.mean(amounts)),
                mean_without=0.0,  # Not applicable for amount-based
                description=f"{comp_name} {strength} {effect} {property_type.value} (r={corr:.3f}, n={len(data)})",
            )
            patterns.append(pattern)

        patterns.sort(key=lambda p: abs(p.correlation), reverse=True)
        self._patterns.extend(patterns)
        return patterns

    def patterns_to_hypotheses(
        self,
        patterns: Optional[list[PropertyPattern]] = None,
        min_correlation: float = 0.2,
    ) -> list[HypothesisEdge]:
        """Convert mined patterns to hypothesis edges."""
        if patterns is None:
            patterns = self._patterns

        hypotheses = []
        for pattern in patterns:
            if abs(pattern.correlation) < min_correlation:
                continue

            # Determine relation type
            if pattern.effect == "increases":
                rel = RelationType.INCREASES
            elif pattern.effect == "decreases":
                rel = RelationType.DECREASES
            else:
                rel = RelationType.CORRELATES_WITH

            hypothesis = HypothesisEdge(
                subject_id=pattern.component_id,
                subject_type=pattern.component_type.value,
                relation=rel,
                object_id=pattern.property_type.entity_id,  # Use deterministic entity ID
                object_type="PropertyType",
                status=HypothesisStatus.PROPOSED,
                source=HypothesisSource.RULE_MINING,
                confidence=min(abs(pattern.correlation), 1.0),
                explanation=pattern.description,
                is_novel=True,
            )
            hypotheses.append(hypothesis)

        return hypotheses

    def rules_to_hypotheses(
        self,
        rules: Optional[list[Rule]] = None,
        min_confidence: float = 0.5,
    ) -> list[HypothesisEdge]:
        """Convert mined rules to hypothesis edges."""
        if rules is None:
            rules = self._rules

        hypotheses = []
        for rule in rules:
            if rule.confidence < min_confidence:
                continue

            # Extract subject from rule body
            if not rule.body:
                continue

            _, _, subject_id = rule.body[0]

            # Determine object_id: use target_entity_id if available (for co-occurrence)
            if rule.target_entity_id:
                object_id = rule.target_entity_id
                object_type = "Molecule"
                relation = RelationType.CO_OCCURS_WITH
            else:
                # Fallback for other rule types
                object_id = rule.head_relation
                object_type = "PropertyClass"
                relation = RelationType.AFFECTS

            hypothesis = HypothesisEdge(
                subject_id=subject_id,
                subject_type="Molecule",
                relation=relation,
                object_id=object_id,
                object_type=object_type,
                status=HypothesisStatus.PROPOSED,
                source=HypothesisSource.RULE_MINING,
                confidence=rule.confidence,
                explanation=rule.description,
                is_novel=True,
            )
            hypotheses.append(hypothesis)

        return hypotheses
