"""
Hypothesis Agent: Proposes KG augmentations via rule mining and statistical analysis.

This agent generates candidate edges (hypotheses) using:
1. Association rule mining - frequent patterns in formulations
2. Cross-property correlation - structure-property relationships
3. Property prediction - ML-based prediction for missing values
4. Link prediction - suggest missing relations based on graph structure
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import datetime
import hashlib
import numpy as np
from scipy import stats

from .base import BaseAgent, AgentResult


@dataclass
class ProposedHypothesis:
    """A proposed KG augmentation (hypothesis edge)."""

    hypothesis_id: str
    hypothesis_type: Literal["increases", "decreases", "coOccursWith", "decomposesTo", "sameAs", "predictedProperty"]
    subject_id: str
    subject_name: str
    object_id: str
    object_name: str
    confidence: float  # 0-1
    evidence: dict = field(default_factory=dict)
    explanation: str = ""
    falsifiable: bool = True
    novelty_score: float = 0.0  # Higher = more novel
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "hypothesis_type": self.hypothesis_type,
            "subject": {"id": self.subject_id, "name": self.subject_name},
            "object": {"id": self.object_id, "name": self.object_name},
            "confidence": self.confidence,
            "evidence": self.evidence,
            "explanation": self.explanation,
            "falsifiable": self.falsifiable,
            "novelty_score": self.novelty_score,
            "created_at": self.created_at.isoformat(),
        }

    def to_triple(self) -> tuple:
        """Return as (subject, relation, object) triple."""
        return (self.subject_id, self.hypothesis_type, self.object_id)


class HypothesisAgent(BaseAgent):
    """
    Proposes KG augmentations (hypotheses) using multiple strategies.

    Strategies:
    1. Association rule mining: Discover co-occurrence patterns
    2. Correlation analysis: Find property-property relationships
    3. Property prediction: Suggest missing property values
    4. Causal inference: Propose increases/decreases relations
    """

    def __init__(self, kg, name: str = "Hypothesis"):
        super().__init__(kg, name)
        self.hypotheses: list[ProposedHypothesis] = []
        self._existing_relations: set = set()

    def run(
        self,
        run_association_mining: bool = True,
        run_correlation_analysis: bool = True,
        run_causal_inference: bool = True,
        min_confidence: float = 0.6,
        min_support: int = 5,
        top_k: int = 50,
        explorer_candidates: Optional[list] = None,
        **kwargs
    ) -> AgentResult:
        """
        Generate hypothesis candidates.

        Args:
            run_association_mining: Mine co-occurrence patterns
            run_correlation_analysis: Analyze property correlations
            run_causal_inference: Infer causal relationships
            min_confidence: Minimum confidence threshold
            min_support: Minimum support count for patterns
            top_k: Maximum hypotheses to return
            explorer_candidates: Candidates from Explorer agent

        Returns:
            AgentResult with proposed hypotheses
        """
        if not self.validate():
            return AgentResult(
                agent_name=self.name,
                success=False,
                errors=["Validation failed"]
            )

        self.logger.info("Starting hypothesis generation...")
        self.hypotheses = []
        self._build_existing_relations()
        metrics = {}

        # Run hypothesis generation strategies
        if run_association_mining:
            assoc_hyps = self._mine_association_rules(min_support, min_confidence)
            self.hypotheses.extend(assoc_hyps)
            metrics["association_hypotheses"] = len(assoc_hyps)

        if run_correlation_analysis:
            corr_hyps = self._analyze_correlations(min_confidence)
            self.hypotheses.extend(corr_hyps)
            metrics["correlation_hypotheses"] = len(corr_hyps)

        if run_causal_inference:
            causal_hyps = self._infer_causal_relations(min_confidence, min_support)
            self.hypotheses.extend(causal_hyps)
            metrics["causal_hypotheses"] = len(causal_hyps)

        # Calculate novelty scores
        self._calculate_novelty_scores()

        # Filter duplicates and existing relations
        self.hypotheses = self._filter_hypotheses()

        # Sort by confidence * novelty
        self.hypotheses.sort(
            key=lambda h: h.confidence * (1 + h.novelty_score),
            reverse=True
        )

        # Limit to top_k
        self.hypotheses = self.hypotheses[:top_k]

        # Prepare outputs
        outputs = {
            "total_hypotheses": len(self.hypotheses),
            "by_type": Counter(h.hypothesis_type for h in self.hypotheses),
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "avg_confidence": np.mean([h.confidence for h in self.hypotheses]) if self.hypotheses else 0,
            "avg_novelty": np.mean([h.novelty_score for h in self.hypotheses]) if self.hypotheses else 0,
        }

        self.logger.info(f"Generated {len(self.hypotheses)} hypotheses")

        return AgentResult(
            agent_name=self.name,
            success=True,
            outputs=outputs,
            metrics=metrics,
            provenance={
                "kg_version": self.kg.get("version", "unknown"),
                "strategies_run": {
                    "association_mining": run_association_mining,
                    "correlation_analysis": run_correlation_analysis,
                    "causal_inference": run_causal_inference,
                },
                "thresholds": {
                    "min_confidence": min_confidence,
                    "min_support": min_support,
                },
            }
        )

    def _build_existing_relations(self):
        """Build set of existing relations for novelty checking."""
        self._existing_relations = set()
        for subj, rel, obj in self.kg.get("relations", []):
            self._existing_relations.add((subj, rel, obj))

    def _generate_hypothesis_id(self, subj: str, rel: str, obj: str) -> str:
        """Generate deterministic hypothesis ID."""
        content = f"{subj}:{rel}:{obj}"
        return f"hyp-{hashlib.md5(content.encode()).hexdigest()[:12]}"

    def _mine_association_rules(
        self,
        min_support: int,
        min_confidence: float
    ) -> list[ProposedHypothesis]:
        """Mine co-occurrence patterns from formulations."""
        hypotheses = []
        formulations = self.kg.get("formulations", {})
        relations = self.kg.get("relations", [])
        molecules = self.kg.get("molecules", {})

        # Build formulation -> components map
        form_components = defaultdict(set)
        for subj, rel, obj in relations:
            if rel in ("hasSolvent", "hasSalt", "hasAdditive"):
                form_components[subj].add(obj)

        if not form_components:
            return hypotheses

        # Count component co-occurrences
        pair_counts = Counter()
        component_counts = Counter()

        for form_id, components in form_components.items():
            for comp in components:
                component_counts[comp] += 1
            for i, comp1 in enumerate(sorted(components)):
                for comp2 in sorted(components)[i+1:]:
                    pair_counts[(comp1, comp2)] += 1

        # Generate coOccursWith hypotheses
        total_formulations = len(form_components)
        for (comp1, comp2), count in pair_counts.most_common(100):
            if count < min_support:
                continue

            # Calculate confidence as lift
            p_comp1 = component_counts[comp1] / total_formulations
            p_comp2 = component_counts[comp2] / total_formulations
            p_both = count / total_formulations

            if p_comp1 * p_comp2 > 0:
                lift = p_both / (p_comp1 * p_comp2)
                confidence = min(1.0, lift / 2)  # Normalize lift to confidence

                if confidence >= min_confidence:
                    name1 = molecules.get(comp1, {}).get("name", comp1[:12])
                    name2 = molecules.get(comp2, {}).get("name", comp2[:12])

                    hypotheses.append(ProposedHypothesis(
                        hypothesis_id=self._generate_hypothesis_id(comp1, "coOccursWith", comp2),
                        hypothesis_type="coOccursWith",
                        subject_id=comp1,
                        subject_name=name1,
                        object_id=comp2,
                        object_name=name2,
                        confidence=confidence,
                        evidence={
                            "co_occurrence_count": count,
                            "lift": lift,
                            "support_pct": p_both * 100,
                            "comp1_freq": component_counts[comp1],
                            "comp2_freq": component_counts[comp2],
                        },
                        explanation=f"{name1} and {name2} co-occur in {count} formulations (lift={lift:.2f})",
                        falsifiable=True,
                    ))

        return hypotheses

    def _analyze_correlations(self, min_confidence: float) -> list[ProposedHypothesis]:
        """Analyze property-property correlations."""
        hypotheses = []
        measurements = self.kg.get("measurements", {})
        relations = self.kg.get("relations", [])
        molecules = self.kg.get("molecules", {})

        # Build entity -> property values map
        entity_properties = defaultdict(dict)
        for subj, rel, obj in relations:
            if rel == "hasMeasurement" and obj in measurements:
                meas = measurements[obj]
                prop_type = meas.get("property_type")
                value = meas.get("value")
                if prop_type and value is not None:
                    try:
                        # Store average if multiple measurements
                        if prop_type not in entity_properties[subj]:
                            entity_properties[subj][prop_type] = []
                        entity_properties[subj][prop_type].append(float(value))
                    except (ValueError, TypeError):
                        pass

        # Average multiple measurements
        for entity_id in entity_properties:
            for prop_type in entity_properties[entity_id]:
                vals = entity_properties[entity_id][prop_type]
                entity_properties[entity_id][prop_type] = np.mean(vals)

        # Find entities with multiple properties
        property_types = set()
        for props in entity_properties.values():
            property_types.update(props.keys())

        property_types = list(property_types)

        # Calculate correlations between property types
        for i, prop1 in enumerate(property_types):
            for prop2 in property_types[i+1:]:
                # Get entities with both properties
                paired_values = []
                for entity_id, props in entity_properties.items():
                    if prop1 in props and prop2 in props:
                        paired_values.append((props[prop1], props[prop2]))

                if len(paired_values) < 10:
                    continue

                x = np.array([v[0] for v in paired_values])
                y = np.array([v[1] for v in paired_values])

                # Calculate Pearson correlation
                r, p_value = stats.pearsonr(x, y)

                if abs(r) >= min_confidence and p_value < 0.05:
                    direction = "increases" if r > 0 else "decreases"
                    confidence = abs(r)

                    hypotheses.append(ProposedHypothesis(
                        hypothesis_id=self._generate_hypothesis_id(prop1, f"correlated_with", prop2),
                        hypothesis_type=direction,
                        subject_id=f"property:{prop1}",
                        subject_name=prop1,
                        object_id=f"property:{prop2}",
                        object_name=prop2,
                        confidence=confidence,
                        evidence={
                            "correlation_r": r,
                            "p_value": p_value,
                            "sample_size": len(paired_values),
                            "direction": "positive" if r > 0 else "negative",
                        },
                        explanation=f"{prop1} {'positively' if r > 0 else 'negatively'} correlates with {prop2} (r={r:.3f}, n={len(paired_values)})",
                        falsifiable=True,
                    ))

        return hypotheses

    def _infer_causal_relations(
        self,
        min_confidence: float,
        min_support: int
    ) -> list[ProposedHypothesis]:
        """Infer component -> property causal relations."""
        hypotheses = []
        formulations = self.kg.get("formulations", {})
        measurements = self.kg.get("measurements", {})
        relations = self.kg.get("relations", [])
        molecules = self.kg.get("molecules", {})

        # Build formulation -> components and measurements maps
        form_components = defaultdict(set)
        form_measurements = defaultdict(list)

        for subj, rel, obj in relations:
            if rel in ("hasSolvent", "hasSalt", "hasAdditive"):
                form_components[subj].add(obj)
            elif rel == "hasMeasurement" and obj in measurements:
                meas = measurements[obj]
                prop_type = meas.get("property_type")
                value = meas.get("value")
                if prop_type and value is not None:
                    try:
                        form_measurements[subj].append({
                            "property": prop_type,
                            "value": float(value),
                        })
                    except (ValueError, TypeError):
                        pass

        # For each component, compare formulations with vs without
        component_effects = defaultdict(lambda: defaultdict(list))

        for form_id, components in form_components.items():
            for meas in form_measurements.get(form_id, []):
                for comp in components:
                    component_effects[comp][meas["property"]].append(meas["value"])

        # Calculate effect of each component on each property
        for comp_id, prop_effects in component_effects.items():
            comp_name = molecules.get(comp_id, {}).get("name", comp_id[:12])

            for prop_type, values in prop_effects.items():
                if len(values) < min_support:
                    continue

                # Get values for formulations WITHOUT this component
                without_values = []
                for form_id, components in form_components.items():
                    if comp_id not in components:
                        for meas in form_measurements.get(form_id, []):
                            if meas["property"] == prop_type:
                                without_values.append(meas["value"])

                if len(without_values) < min_support:
                    continue

                # Compare distributions
                with_mean = np.mean(values)
                without_mean = np.mean(without_values)

                # T-test for significance
                if len(values) >= 3 and len(without_values) >= 3:
                    t_stat, p_value = stats.ttest_ind(values, without_values)

                    if p_value < 0.05:
                        effect_size = (with_mean - without_mean) / np.std(without_values) if np.std(without_values) > 0 else 0
                        direction = "increases" if effect_size > 0 else "decreases"
                        confidence = min(1.0, abs(effect_size) / 2)  # Normalize effect size

                        if confidence >= min_confidence:
                            hypotheses.append(ProposedHypothesis(
                                hypothesis_id=self._generate_hypothesis_id(comp_id, direction, prop_type),
                                hypothesis_type=direction,
                                subject_id=comp_id,
                                subject_name=comp_name,
                                object_id=f"property:{prop_type}",
                                object_name=prop_type,
                                confidence=confidence,
                                evidence={
                                    "with_mean": with_mean,
                                    "without_mean": without_mean,
                                    "effect_size": effect_size,
                                    "t_statistic": t_stat,
                                    "p_value": p_value,
                                    "n_with": len(values),
                                    "n_without": len(without_values),
                                },
                                explanation=f"{comp_name} {direction} {prop_type} (effect size={effect_size:.2f}, p={p_value:.3f})",
                                falsifiable=True,
                            ))

        return hypotheses

    def _calculate_novelty_scores(self):
        """Calculate novelty scores for hypotheses."""
        existing_hypotheses = set()
        for hyp in self.kg.get("hypotheses", {}).values():
            subj = hyp.get("subject_id", "")
            rel = hyp.get("relation_type", "")
            obj = hyp.get("object_id", "")
            existing_hypotheses.add((subj, rel, obj))

        for hyp in self.hypotheses:
            triple = hyp.to_triple()

            # Check if relation already exists
            if triple in self._existing_relations:
                hyp.novelty_score = 0.0
            elif triple in existing_hypotheses:
                hyp.novelty_score = 0.2  # Already proposed but not validated
            else:
                # Novel hypothesis - score based on evidence strength
                hyp.novelty_score = 0.8 + (0.2 * hyp.confidence)

    def _filter_hypotheses(self) -> list[ProposedHypothesis]:
        """Filter out duplicate and existing hypotheses."""
        seen = set()
        filtered = []

        for hyp in self.hypotheses:
            triple = hyp.to_triple()

            # Skip if already in KG
            if triple in self._existing_relations:
                continue

            # Skip duplicates
            if triple in seen:
                continue

            seen.add(triple)
            filtered.append(hyp)

        return filtered

    def get_top_hypotheses(
        self,
        n: int = 10,
        hypothesis_type: Optional[str] = None
    ) -> list[ProposedHypothesis]:
        """Get top N hypotheses, optionally filtered by type."""
        hypotheses = self.hypotheses

        if hypothesis_type:
            hypotheses = [h for h in hypotheses if h.hypothesis_type == hypothesis_type]

        return hypotheses[:n]

    def report(self, result: AgentResult) -> str:
        """Generate human-readable hypothesis report."""
        lines = [super().report(result)]

        if result.success:
            outputs = result.outputs
            lines.append(f"\nTotal hypotheses: {outputs.get('total_hypotheses', 0)}")
            lines.append(f"Average confidence: {outputs.get('avg_confidence', 0):.3f}")
            lines.append(f"Average novelty: {outputs.get('avg_novelty', 0):.3f}")

            lines.append("\nHypotheses by type:")
            for hyp_type, count in outputs.get("by_type", {}).items():
                lines.append(f"  {hyp_type}: {count}")

            lines.append("\nTop hypotheses:")
            for i, hyp in enumerate(outputs.get("hypotheses", [])[:10], 1):
                lines.append(f"  {i}. [{hyp['hypothesis_type']}] {hyp['subject']['name']} -> {hyp['object']['name']}")
                lines.append(f"     Confidence: {hyp['confidence']:.3f}, Novelty: {hyp['novelty_score']:.3f}")
                lines.append(f"     {hyp['explanation']}")

        return "\n".join(lines)
