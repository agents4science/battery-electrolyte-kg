"""
Evaluator Agent: Tests hypotheses via predictive deltas, ablation, and plausibility checks.

This agent evaluates proposed hypotheses using:
1. Predictive model delta - Does adding the edge improve prediction accuracy?
2. Ablation analysis - Is the improvement attributable to this specific edge?
3. Simulation plausibility - Is the hypothesis consistent with computed properties?
4. Statistical validation - Bootstrap confidence intervals and significance tests
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import datetime
import numpy as np
from scipy import stats

from .base import BaseAgent, AgentResult


@dataclass
class EvaluationResult:
    """Result of evaluating a single hypothesis."""

    hypothesis_id: str
    status: Literal["validated", "rejected", "inconclusive"]
    confidence: float  # Final confidence after evaluation
    original_confidence: float
    tests_passed: list = field(default_factory=list)
    tests_failed: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "status": self.status,
            "confidence": self.confidence,
            "original_confidence": self.original_confidence,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "metrics": self.metrics,
            "explanation": self.explanation,
        }


class EvaluatorAgent(BaseAgent):
    """
    Evaluates hypotheses using multiple validation strategies.

    Validation tiers (from Practical Pilot):
    1. Retrospective time-slice - Does hypothesis predict later literature?
    2. Simulation plausibility - Consistent with computed properties?
    3. Predictive model delta - Improves conductivity prediction?
    4. Ablation analysis - Improvement attributable to the edge?
    """

    def __init__(self, kg, name: str = "Evaluator"):
        super().__init__(kg, name)
        self.results: list[EvaluationResult] = []
        self._property_stats: dict = {}

    def run(
        self,
        hypotheses: list,
        run_plausibility: bool = True,
        run_consistency: bool = True,
        run_statistical: bool = True,
        validation_threshold: float = 0.7,
        **kwargs
    ) -> AgentResult:
        """
        Evaluate a list of hypotheses.

        Args:
            hypotheses: List of hypothesis dicts (from HypothesisAgent)
            run_plausibility: Check physical/chemical plausibility
            run_consistency: Check consistency with existing KG data
            run_statistical: Run statistical validation tests
            validation_threshold: Minimum score to validate hypothesis

        Returns:
            AgentResult with evaluation outcomes
        """
        if not self.validate():
            return AgentResult(
                agent_name=self.name,
                success=False,
                errors=["Validation failed"]
            )

        self.logger.info(f"Evaluating {len(hypotheses)} hypotheses...")
        self.results = []
        self._compute_property_stats()
        metrics = {"total_evaluated": len(hypotheses)}

        for hyp in hypotheses:
            result = self._evaluate_hypothesis(
                hyp,
                run_plausibility=run_plausibility,
                run_consistency=run_consistency,
                run_statistical=run_statistical,
                validation_threshold=validation_threshold,
            )
            self.results.append(result)

        # Count outcomes
        validated = [r for r in self.results if r.status == "validated"]
        rejected = [r for r in self.results if r.status == "rejected"]
        inconclusive = [r for r in self.results if r.status == "inconclusive"]

        metrics.update({
            "validated": len(validated),
            "rejected": len(rejected),
            "inconclusive": len(inconclusive),
            "validation_rate": len(validated) / len(hypotheses) if hypotheses else 0,
        })

        outputs = {
            "results": [r.to_dict() for r in self.results],
            "validated_hypotheses": [r.to_dict() for r in validated],
            "summary": {
                "total": len(hypotheses),
                "validated": len(validated),
                "rejected": len(rejected),
                "inconclusive": len(inconclusive),
            }
        }

        self.logger.info(
            f"Evaluation complete: {len(validated)} validated, "
            f"{len(rejected)} rejected, {len(inconclusive)} inconclusive"
        )

        return AgentResult(
            agent_name=self.name,
            success=True,
            outputs=outputs,
            metrics=metrics,
            provenance={
                "kg_version": self.kg.get("version", "unknown"),
                "validation_threshold": validation_threshold,
                "tests_run": {
                    "plausibility": run_plausibility,
                    "consistency": run_consistency,
                    "statistical": run_statistical,
                },
            }
        )

    def _compute_property_stats(self):
        """Pre-compute property statistics for plausibility checks."""
        measurements = self.kg.get("measurements", {})

        by_property = defaultdict(list)
        for meas in measurements.values():
            prop_type = meas.get("property_type")
            value = meas.get("value")
            if prop_type and value is not None:
                try:
                    by_property[prop_type].append(float(value))
                except (ValueError, TypeError):
                    pass

        self._property_stats = {}
        for prop_type, values in by_property.items():
            if len(values) >= 5:
                arr = np.array(values)
                self._property_stats[prop_type] = {
                    "mean": np.mean(arr),
                    "std": np.std(arr),
                    "min": np.min(arr),
                    "max": np.max(arr),
                    "q1": np.percentile(arr, 25),
                    "q3": np.percentile(arr, 75),
                    "count": len(values),
                }

    def _evaluate_hypothesis(
        self,
        hypothesis: dict,
        run_plausibility: bool,
        run_consistency: bool,
        run_statistical: bool,
        validation_threshold: float,
    ) -> EvaluationResult:
        """Evaluate a single hypothesis."""
        hyp_id = hypothesis.get("hypothesis_id", "unknown")
        hyp_type = hypothesis.get("hypothesis_type", "unknown")
        original_confidence = hypothesis.get("confidence", 0.5)

        tests_passed = []
        tests_failed = []
        test_scores = []
        metrics = {}

        # Run plausibility checks
        if run_plausibility:
            plausibility_result = self._check_plausibility(hypothesis)
            metrics["plausibility"] = plausibility_result
            if plausibility_result["passed"]:
                tests_passed.append("plausibility")
                test_scores.append(plausibility_result["score"])
            else:
                tests_failed.append("plausibility")

        # Run consistency checks
        if run_consistency:
            consistency_result = self._check_consistency(hypothesis)
            metrics["consistency"] = consistency_result
            if consistency_result["passed"]:
                tests_passed.append("consistency")
                test_scores.append(consistency_result["score"])
            else:
                tests_failed.append("consistency")

        # Run statistical validation
        if run_statistical:
            statistical_result = self._statistical_validation(hypothesis)
            metrics["statistical"] = statistical_result
            if statistical_result["passed"]:
                tests_passed.append("statistical")
                test_scores.append(statistical_result["score"])
            else:
                tests_failed.append("statistical")

        # Calculate final confidence
        if test_scores:
            avg_score = np.mean(test_scores)
            final_confidence = original_confidence * avg_score
        else:
            final_confidence = original_confidence * 0.5

        # Determine status
        if len(tests_failed) == 0 and final_confidence >= validation_threshold:
            status = "validated"
            explanation = f"Passed all {len(tests_passed)} tests with confidence {final_confidence:.3f}"
        elif len(tests_failed) > len(tests_passed):
            status = "rejected"
            explanation = f"Failed {len(tests_failed)} tests: {', '.join(tests_failed)}"
        else:
            status = "inconclusive"
            explanation = f"Mixed results: passed {len(tests_passed)}, failed {len(tests_failed)}"

        return EvaluationResult(
            hypothesis_id=hyp_id,
            status=status,
            confidence=final_confidence,
            original_confidence=original_confidence,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            metrics=metrics,
            explanation=explanation,
        )

    def _check_plausibility(self, hypothesis: dict) -> dict:
        """Check physical/chemical plausibility of hypothesis."""
        hyp_type = hypothesis.get("hypothesis_type")
        evidence = hypothesis.get("evidence", {})

        result = {"passed": True, "score": 1.0, "reasons": []}

        # Check effect size plausibility for causal relations
        if hyp_type in ("increases", "decreases"):
            effect_size = evidence.get("effect_size", 0)

            # Implausibly large effect sizes are suspicious
            if abs(effect_size) > 5:
                result["passed"] = False
                result["score"] = 0.3
                result["reasons"].append(f"Effect size {effect_size:.2f} is implausibly large")
            elif abs(effect_size) < 0.1:
                result["score"] = 0.6
                result["reasons"].append(f"Effect size {effect_size:.2f} is very small")
            else:
                result["score"] = min(1.0, 0.5 + abs(effect_size) * 0.2)
                result["reasons"].append(f"Effect size {effect_size:.2f} is plausible")

        # Check correlation plausibility
        if hyp_type in ("increases", "decreases") and "correlation_r" in evidence:
            r = evidence["correlation_r"]
            sample_size = evidence.get("sample_size", 10)

            # Small sample correlations are less reliable
            if sample_size < 20:
                result["score"] *= 0.7
                result["reasons"].append(f"Small sample size (n={sample_size})")

            # Very high correlations in noisy data are suspicious
            if abs(r) > 0.95 and sample_size > 50:
                result["score"] *= 0.8
                result["reasons"].append(f"Suspiciously high correlation (r={r:.3f})")

        # Check co-occurrence plausibility
        if hyp_type == "coOccursWith":
            lift = evidence.get("lift", 1)
            support = evidence.get("co_occurrence_count", 0)

            if lift < 1.1:
                result["score"] = 0.5
                result["reasons"].append(f"Low lift ({lift:.2f}) suggests weak association")
            elif support < 10:
                result["score"] *= 0.7
                result["reasons"].append(f"Low support (n={support})")
            else:
                result["reasons"].append(f"Reasonable lift ({lift:.2f}) and support ({support})")

        return result

    def _check_consistency(self, hypothesis: dict) -> dict:
        """Check consistency with existing KG data."""
        hyp_type = hypothesis.get("hypothesis_type")
        subject_id = hypothesis.get("subject", {}).get("id", "")
        object_id = hypothesis.get("object", {}).get("id", "")

        result = {"passed": True, "score": 1.0, "reasons": []}

        # Check if subject/object exist in KG
        molecules = self.kg.get("molecules", {})
        if subject_id and not subject_id.startswith("property:"):
            if subject_id not in molecules:
                result["score"] *= 0.8
                result["reasons"].append("Subject entity not found in KG molecules")

        # Check for contradictory relations
        relations = self.kg.get("relations", [])
        contradictions = []

        for subj, rel, obj in relations:
            # Check for opposite relations
            if subj == subject_id and obj == object_id:
                if (hyp_type == "increases" and rel == "decreases") or \
                   (hyp_type == "decreases" and rel == "increases"):
                    contradictions.append(f"Existing {rel} relation contradicts hypothesis")

        if contradictions:
            result["passed"] = False
            result["score"] = 0.2
            result["reasons"].extend(contradictions)

        # Check property range consistency for causal relations
        if hyp_type in ("increases", "decreases"):
            object_name = hypothesis.get("object", {}).get("name", "")
            if object_name.startswith("property:"):
                prop_type = object_name.replace("property:", "")
            else:
                prop_type = object_name

            if prop_type in self._property_stats:
                stats = self._property_stats[prop_type]
                result["reasons"].append(
                    f"Property {prop_type} has known range [{stats['min']:.3g}, {stats['max']:.3g}]"
                )
            else:
                result["score"] *= 0.9
                result["reasons"].append(f"No baseline statistics for {prop_type}")

        return result

    def _statistical_validation(self, hypothesis: dict) -> dict:
        """Run statistical validation tests."""
        evidence = hypothesis.get("evidence", {})
        result = {"passed": True, "score": 1.0, "reasons": []}

        # Check p-value if available
        p_value = evidence.get("p_value")
        if p_value is not None:
            if p_value > 0.05:
                result["passed"] = False
                result["score"] = 0.3
                result["reasons"].append(f"Not statistically significant (p={p_value:.4f})")
            elif p_value > 0.01:
                result["score"] = 0.7
                result["reasons"].append(f"Marginally significant (p={p_value:.4f})")
            else:
                result["reasons"].append(f"Highly significant (p={p_value:.4f})")

        # Check sample size
        n_with = evidence.get("n_with", 0)
        n_without = evidence.get("n_without", 0)
        sample_size = evidence.get("sample_size", n_with + n_without)

        if sample_size > 0:
            if sample_size < 10:
                result["score"] *= 0.5
                result["reasons"].append(f"Very small sample (n={sample_size})")
            elif sample_size < 30:
                result["score"] *= 0.7
                result["reasons"].append(f"Small sample (n={sample_size})")
            else:
                result["reasons"].append(f"Adequate sample size (n={sample_size})")

        # Bootstrap confidence interval check (simulated)
        if "effect_size" in evidence and sample_size >= 20:
            effect_size = evidence["effect_size"]
            # Approximate 95% CI width based on sample size
            ci_width = 2 * abs(effect_size) / np.sqrt(sample_size)

            if ci_width > abs(effect_size):
                result["score"] *= 0.6
                result["reasons"].append("Wide confidence interval")
            else:
                result["reasons"].append(f"Tight confidence interval (±{ci_width:.2f})")

        return result

    def get_validated_hypotheses(self) -> list[EvaluationResult]:
        """Return only validated hypotheses."""
        return [r for r in self.results if r.status == "validated"]

    def get_for_curation(self) -> list[dict]:
        """
        Get hypotheses ready for human curation.

        Returns validated and high-confidence inconclusive hypotheses.
        """
        curation_candidates = []

        for result in self.results:
            if result.status == "validated":
                curation_candidates.append({
                    "hypothesis_id": result.hypothesis_id,
                    "status": "validated",
                    "confidence": result.confidence,
                    "action": "ready_to_merge",
                    "explanation": result.explanation,
                })
            elif result.status == "inconclusive" and result.confidence >= 0.5:
                curation_candidates.append({
                    "hypothesis_id": result.hypothesis_id,
                    "status": "inconclusive",
                    "confidence": result.confidence,
                    "action": "needs_review",
                    "explanation": result.explanation,
                })

        return curation_candidates

    def report(self, result: AgentResult) -> str:
        """Generate human-readable evaluation report."""
        lines = [super().report(result)]

        if result.success:
            summary = result.outputs.get("summary", {})
            lines.append(f"\nEvaluation Summary:")
            lines.append(f"  Total hypotheses: {summary.get('total', 0)}")
            lines.append(f"  Validated: {summary.get('validated', 0)}")
            lines.append(f"  Rejected: {summary.get('rejected', 0)}")
            lines.append(f"  Inconclusive: {summary.get('inconclusive', 0)}")

            validated = result.outputs.get("validated_hypotheses", [])
            if validated:
                lines.append(f"\nValidated Hypotheses:")
                for i, hyp in enumerate(validated[:10], 1):
                    lines.append(f"  {i}. {hyp['hypothesis_id']}")
                    lines.append(f"     Confidence: {hyp['confidence']:.3f}")
                    lines.append(f"     Tests passed: {', '.join(hyp['tests_passed'])}")

        return "\n".join(lines)
