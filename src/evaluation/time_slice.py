"""Time-slice evaluation for retrospective validation."""

from datetime import datetime
from typing import Optional
from dataclasses import dataclass
import numpy as np

from ..kg_store.graph import KnowledgeGraph
from ..schema.hypothesis import HypothesisEdge, HypothesisStatus
from .metrics import DiscoveryMetrics


@dataclass
class TimeSliceResult:
    """Result of time-slice evaluation."""
    cutoff_date: datetime
    num_hypotheses: int
    num_appeared_after: int  # Appeared in post-cutoff data
    hit_rate: float
    avg_rank: float  # Average rank of correct predictions
    mrr: float  # Mean reciprocal rank


class TimeSliceEvaluator:
    """
    Retrospective time-slice validation.

    Builds KG from data up to cutoff date T, generates hypotheses,
    then checks if they appear in post-cutoff data.
    """

    def __init__(self, kg: KnowledgeGraph):
        self.kg = kg
        self._results: list[TimeSliceResult] = []

    def evaluate(
        self,
        hypotheses: list[HypothesisEdge],
        post_cutoff_triples: set[tuple[str, str, str]],
        cutoff_date: datetime,
    ) -> TimeSliceResult:
        """
        Evaluate hypotheses against post-cutoff data.

        Args:
            hypotheses: List of proposed hypothesis edges
            post_cutoff_triples: Set of triples that appeared after cutoff
            cutoff_date: The cutoff date used

        Returns:
            TimeSliceResult with evaluation metrics
        """
        if not hypotheses:
            return TimeSliceResult(
                cutoff_date=cutoff_date,
                num_hypotheses=0,
                num_appeared_after=0,
                hit_rate=0.0,
                avg_rank=float("inf"),
                mrr=0.0,
            )

        # Sort hypotheses by confidence (descending)
        sorted_hypotheses = sorted(hypotheses, key=lambda h: h.confidence, reverse=True)

        # Check which hypotheses appeared in post-cutoff data
        hits = []
        ranks = []

        for rank, h in enumerate(sorted_hypotheses, start=1):
            triple = (h.subject_id, h.relation.value, h.object_id)
            if triple in post_cutoff_triples:
                hits.append(h)
                ranks.append(rank)
                # Mark as validated
                h.status = HypothesisStatus.VALIDATED
                h.passed_time_slice = True
                h.validation_results.append({
                    "method": "time_slice",
                    "cutoff_date": cutoff_date.isoformat(),
                    "rank": rank,
                })

        num_appeared = len(hits)
        hit_rate = num_appeared / len(hypotheses) if hypotheses else 0.0
        avg_rank = np.mean(ranks) if ranks else float("inf")
        mrr = np.mean([1.0 / r for r in ranks]) if ranks else 0.0

        result = TimeSliceResult(
            cutoff_date=cutoff_date,
            num_hypotheses=len(hypotheses),
            num_appeared_after=num_appeared,
            hit_rate=hit_rate,
            avg_rank=avg_rank,
            mrr=mrr,
        )

        self._results.append(result)
        return result

    def create_time_split(
        self,
        cutoff_date: datetime,
    ) -> tuple[set[tuple], set[tuple]]:
        """
        Split KG triples by date.

        Returns (pre_cutoff_triples, post_cutoff_triples).

        Note: This requires provenance with timestamps. If not available,
        returns all triples as pre-cutoff.
        """
        pre_cutoff = set()
        post_cutoff = set()

        for triple in self.kg.to_triples():
            s, r, o = triple

            # Check provenance for timestamp
            # For now, simplified: all existing triples are pre-cutoff
            pre_cutoff.add(triple)

        return pre_cutoff, post_cutoff

    def run_time_slice_experiment(
        self,
        cutoff_date: datetime,
        hypothesis_generator,
        **generator_kwargs,
    ) -> TimeSliceResult:
        """
        Run a full time-slice experiment.

        1. Creates a snapshot of KG up to cutoff
        2. Generates hypotheses
        3. Evaluates against post-cutoff data
        """
        # Get pre/post split
        pre_cutoff, post_cutoff = self.create_time_split(cutoff_date)

        # Generate hypotheses using only pre-cutoff data
        # Note: In a full implementation, we would create a separate KG
        # with only pre-cutoff data
        batch = hypothesis_generator.generate_hypotheses(
            cutoff_date=cutoff_date,
            **generator_kwargs,
        )

        # Evaluate
        return self.evaluate(
            hypotheses=batch.hypotheses,
            post_cutoff_triples=post_cutoff,
            cutoff_date=cutoff_date,
        )

    def summary(self) -> dict:
        """Get summary of all time-slice evaluations."""
        if not self._results:
            return {"num_evaluations": 0}

        return {
            "num_evaluations": len(self._results),
            "avg_hit_rate": np.mean([r.hit_rate for r in self._results]),
            "avg_mrr": np.mean([r.mrr for r in self._results]),
            "total_validated": sum(r.num_appeared_after for r in self._results),
            "results": [
                {
                    "cutoff": r.cutoff_date.isoformat(),
                    "hypotheses": r.num_hypotheses,
                    "hits": r.num_appeared_after,
                    "hit_rate": r.hit_rate,
                    "mrr": r.mrr,
                }
                for r in self._results
            ],
        }
