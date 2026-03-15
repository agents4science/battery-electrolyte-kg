"""Main hypothesis generation module combining multiple approaches."""

from datetime import datetime
from typing import Optional
from pathlib import Path

from ..kg_store.graph import KnowledgeGraph
from ..schema.hypothesis import (
    HypothesisEdge, HypothesisBatch, HypothesisStatus, HypothesisSource
)
from ..schema.entities import PropertyType
from ..schema.relations import RelationType
from .link_prediction import LinkPredictor
from .rule_mining import RuleMiner


class HypothesisGenerator:
    """
    Main hypothesis generation system.

    Combines multiple methods:
    1. KG embedding link prediction
    2. Rule mining and pattern discovery
    3. Novelty and time-slice filtering
    """

    def __init__(self, kg: KnowledgeGraph):
        self.kg = kg
        self.link_predictor: Optional[LinkPredictor] = None
        self.rule_miner: Optional[RuleMiner] = None
        self._batches: list[HypothesisBatch] = []

    def train_link_predictor(
        self,
        model_name: str = "TransE",
        embedding_dim: int = 128,
        epochs: int = 100,
        **kwargs,
    ) -> dict:
        """Train the link prediction model."""
        self.link_predictor = LinkPredictor(
            self.kg,
            model_name=model_name,
            embedding_dim=embedding_dim,
        )
        return self.link_predictor.train(epochs=epochs, **kwargs)

    def run_rule_mining(
        self,
        property_type: PropertyType = PropertyType.IONIC_CONDUCTIVITY,
        min_support: int = 3,
        min_confidence: float = 0.5,
    ) -> dict:
        """Run rule mining on the KG."""
        self.rule_miner = RuleMiner(self.kg)

        # Mine different types of patterns
        patterns = self.rule_miner.mine_composition_property_patterns(
            property_type=property_type,
            min_samples=min_support,
        )

        # Mine amount-based correlations (continuous variable analysis)
        amount_patterns = self.rule_miner.mine_amount_property_correlations(
            property_type=property_type,
            min_correlation=0.1,
        )

        co_occurrence_rules = self.rule_miner.mine_co_occurrence_rules(
            min_support=min_support,
            min_confidence=min_confidence,
        )

        threshold_rules = self.rule_miner.mine_property_threshold_rules(
            property_type=property_type,
            min_support=min_support,
            min_confidence=min_confidence,
        )

        return {
            "num_patterns": len(patterns),
            "num_amount_patterns": len(amount_patterns),
            "num_co_occurrence_rules": len(co_occurrence_rules),
            "num_threshold_rules": len(threshold_rules),
        }

    def generate_hypotheses(
        self,
        use_link_prediction: bool = True,
        use_rule_mining: bool = True,
        max_candidates: int = 100,
        min_confidence: float = 0.3,
        relations: Optional[list[RelationType]] = None,
        cutoff_date: Optional[datetime] = None,
    ) -> HypothesisBatch:
        """
        Generate a batch of hypothesis edges.

        Args:
            use_link_prediction: Whether to use link prediction
            use_rule_mining: Whether to use rule mining
            max_candidates: Maximum number of candidates to return
            min_confidence: Minimum confidence threshold
            relations: List of relations to consider for link prediction
            cutoff_date: Time-slice cutoff for novelty filtering

        Returns:
            HypothesisBatch containing proposed hypotheses
        """
        all_hypotheses = []

        # Generate from link prediction
        if use_link_prediction and self.link_predictor:
            lp_candidates = self.link_predictor.generate_candidates(
                relations=relations,
                top_k_per_entity=10,
            )
            all_hypotheses.extend(lp_candidates)

        # Generate from rule mining
        if use_rule_mining and self.rule_miner:
            pattern_hypotheses = self.rule_miner.patterns_to_hypotheses(
                min_correlation=0.1,  # Lower threshold to include property-effect hypotheses
            )
            rule_hypotheses = self.rule_miner.rules_to_hypotheses(
                min_confidence=min_confidence,
            )
            all_hypotheses.extend(pattern_hypotheses)
            all_hypotheses.extend(rule_hypotheses)

        # Filter by confidence
        all_hypotheses = [h for h in all_hypotheses if h.confidence >= min_confidence]

        # Apply novelty filter
        all_hypotheses = self._filter_novel(all_hypotheses)

        # Apply time-slice filter if cutoff provided
        if cutoff_date:
            all_hypotheses = self._filter_time_slice(all_hypotheses, cutoff_date)

        # Separate property-effect hypotheses (always include these)
        property_effect = [h for h in all_hypotheses if h.relation in [
            RelationType.INCREASES, RelationType.DECREASES
        ]]
        other_hypotheses = [h for h in all_hypotheses if h not in property_effect]

        # Sort each group by confidence
        property_effect.sort(key=lambda h: h.confidence, reverse=True)
        other_hypotheses.sort(key=lambda h: h.confidence, reverse=True)

        # Always include property-effect hypotheses, fill rest with others
        remaining_slots = max(0, max_candidates - len(property_effect))
        all_hypotheses = property_effect + other_hypotheses[:remaining_slots]

        # Create batch
        batch = HypothesisBatch(
            source=HypothesisSource.KG_EMBEDDING if use_link_prediction else HypothesisSource.RULE_MINING,
            model_name=self.link_predictor.model_name if self.link_predictor else "RuleMiner",
            kg_version=self.kg.version,
        )

        for h in all_hypotheses:
            batch.add_hypothesis(h)
            self.kg.add_hypothesis(h)

        batch.update_stats()
        self._batches.append(batch)

        return batch

    def _filter_novel(self, hypotheses: list[HypothesisEdge]) -> list[HypothesisEdge]:
        """Filter out hypotheses that already exist in the KG."""
        existing_triples = set(self.kg.to_triples())
        novel = []

        for h in hypotheses:
            triple = (h.subject_id, h.relation.value, h.object_id)
            if triple not in existing_triples:
                h.is_novel = True
                novel.append(h)
            else:
                h.is_novel = False

        return novel

    def _filter_time_slice(
        self,
        hypotheses: list[HypothesisEdge],
        cutoff_date: datetime,
    ) -> list[HypothesisEdge]:
        """
        Filter hypotheses for time-slice validation.

        Marks hypotheses that pass the time-slice filter
        (not present in data before cutoff).
        """
        # For a full implementation, we would check evidence sources
        # and filter based on publication dates
        # For now, just mark the cutoff date
        for h in hypotheses:
            h.cutoff_date = cutoff_date
            h.passed_time_slice = True  # Simplified; full impl would check sources

        return hypotheses

    def get_top_hypotheses(
        self,
        n: int = 10,
        status: Optional[HypothesisStatus] = None,
        source: Optional[HypothesisSource] = None,
    ) -> list[HypothesisEdge]:
        """Get top-n hypotheses by confidence."""
        hypotheses = list(self.kg._hypotheses.values())

        if status:
            hypotheses = [h for h in hypotheses if h.status == status]

        if source:
            hypotheses = [h for h in hypotheses if h.source == source]

        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        return hypotheses[:n]

    def validate_hypothesis(
        self,
        hypothesis_id: str,
        status: HypothesisStatus,
        evidence: list[str],
        method: str,
        model_lift: Optional[float] = None,
    ) -> bool:
        """
        Validate a hypothesis and update its status.

        Returns True if hypothesis was found and updated.
        """
        hypothesis = self.kg._hypotheses.get(hypothesis_id)
        if not hypothesis:
            return False

        hypothesis.validate(status, evidence, method, model_lift)

        # If validated, optionally merge into KG
        if status == HypothesisStatus.VALIDATED:
            self.kg.merge_validated_hypothesis(hypothesis_id)

        return True

    def summary(self) -> dict:
        """Get summary statistics of hypothesis generation."""
        hypotheses = list(self.kg._hypotheses.values())

        return {
            "total_hypotheses": len(hypotheses),
            "by_status": {
                status.value: sum(1 for h in hypotheses if h.status == status)
                for status in HypothesisStatus
            },
            "by_source": {
                source.value: sum(1 for h in hypotheses if h.source == source)
                for source in HypothesisSource
            },
            "num_novel": sum(1 for h in hypotheses if h.is_novel),
            "num_batches": len(self._batches),
            "avg_confidence": (
                sum(h.confidence for h in hypotheses) / len(hypotheses)
                if hypotheses else 0
            ),
        }

    def save_hypotheses(self, path: Path) -> None:
        """Save all hypotheses to a JSON file."""
        import json

        data = {
            "kg_version": self.kg.version,
            "generated_at": datetime.utcnow().isoformat(),
            "summary": self.summary(),
            "hypotheses": [
                h.model_dump() for h in self.kg._hypotheses.values()
            ],
        }

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
