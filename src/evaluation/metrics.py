"""Evaluation metrics for KG discovery."""

from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score


@dataclass
class LinkPredictionMetrics:
    """Metrics for link prediction evaluation."""
    mrr: float = 0.0  # Mean Reciprocal Rank
    hits_at_1: float = 0.0
    hits_at_3: float = 0.0
    hits_at_10: float = 0.0
    num_queries: int = 0

    @classmethod
    def compute(
        cls,
        rankings: list[int],
    ) -> "LinkPredictionMetrics":
        """
        Compute metrics from a list of rankings.

        Args:
            rankings: List of ranks for correct answers (1-indexed)
        """
        if not rankings:
            return cls()

        rankings = np.array(rankings)
        n = len(rankings)

        mrr = np.mean(1.0 / rankings)
        hits_1 = np.mean(rankings <= 1)
        hits_3 = np.mean(rankings <= 3)
        hits_10 = np.mean(rankings <= 10)

        return cls(
            mrr=float(mrr),
            hits_at_1=float(hits_1),
            hits_at_3=float(hits_3),
            hits_at_10=float(hits_10),
            num_queries=n,
        )

    def to_dict(self) -> dict:
        return {
            "mrr": self.mrr,
            "hits@1": self.hits_at_1,
            "hits@3": self.hits_at_3,
            "hits@10": self.hits_at_10,
            "num_queries": self.num_queries,
        }


@dataclass
class PropertyPredictionMetrics:
    """Metrics for property prediction (e.g., conductivity regression)."""
    rmse: float = 0.0
    mae: float = 0.0
    r2: float = 0.0
    num_samples: int = 0
    property_name: str = ""

    @classmethod
    def compute(
        cls,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        property_name: str = "",
    ) -> "PropertyPredictionMetrics":
        """Compute regression metrics."""
        if len(y_true) == 0:
            return cls(property_name=property_name)

        return cls(
            rmse=float(np.sqrt(mean_squared_error(y_true, y_pred))),
            mae=float(mean_absolute_error(y_true, y_pred)),
            r2=float(r2_score(y_true, y_pred)),
            num_samples=len(y_true),
            property_name=property_name,
        )

    def to_dict(self) -> dict:
        return {
            "rmse": self.rmse,
            "mae": self.mae,
            "r2": self.r2,
            "num_samples": self.num_samples,
            "property_name": self.property_name,
        }


@dataclass
class DiscoveryMetrics:
    """
    Metrics for evaluating the discovery process.

    Tracks the discovery funnel and validation outcomes.
    """
    # Funnel metrics
    num_proposed: int = 0
    num_novel: int = 0
    num_passed_time_slice: int = 0
    num_validated: int = 0
    num_rejected: int = 0

    # Quality metrics
    avg_confidence: float = 0.0
    validation_rate: float = 0.0  # validated / (validated + rejected)
    novelty_rate: float = 0.0  # novel / proposed

    # Impact metrics
    avg_model_lift: float = 0.0
    total_model_lift: float = 0.0

    # Provenance metrics
    provenance_completeness: float = 0.0

    def update_from_hypotheses(self, hypotheses: list) -> None:
        """Update metrics from a list of hypothesis edges."""
        if not hypotheses:
            return

        self.num_proposed = len(hypotheses)
        self.num_novel = sum(1 for h in hypotheses if h.is_novel)
        self.num_passed_time_slice = sum(1 for h in hypotheses if h.passed_time_slice)

        from ..schema.hypothesis import HypothesisStatus
        self.num_validated = sum(
            1 for h in hypotheses if h.status == HypothesisStatus.VALIDATED
        )
        self.num_rejected = sum(
            1 for h in hypotheses if h.status == HypothesisStatus.REJECTED
        )

        self.avg_confidence = np.mean([h.confidence for h in hypotheses])

        validated_or_rejected = self.num_validated + self.num_rejected
        if validated_or_rejected > 0:
            self.validation_rate = self.num_validated / validated_or_rejected

        if self.num_proposed > 0:
            self.novelty_rate = self.num_novel / self.num_proposed

        # Model lift from validated hypotheses
        lifts = [
            h.model_lift for h in hypotheses
            if h.model_lift is not None and h.status == HypothesisStatus.VALIDATED
        ]
        if lifts:
            self.avg_model_lift = np.mean(lifts)
            self.total_model_lift = sum(lifts)

    def to_dict(self) -> dict:
        return {
            "funnel": {
                "proposed": self.num_proposed,
                "novel": self.num_novel,
                "passed_time_slice": self.num_passed_time_slice,
                "validated": self.num_validated,
                "rejected": self.num_rejected,
            },
            "quality": {
                "avg_confidence": self.avg_confidence,
                "validation_rate": self.validation_rate,
                "novelty_rate": self.novelty_rate,
            },
            "impact": {
                "avg_model_lift": self.avg_model_lift,
                "total_model_lift": self.total_model_lift,
            },
            "provenance_completeness": self.provenance_completeness,
        }

    def print_summary(self) -> None:
        """Print a summary of discovery metrics."""
        print("\n=== Discovery Metrics ===")
        print(f"\nFunnel:")
        print(f"  Proposed:          {self.num_proposed}")
        print(f"  Novel:             {self.num_novel} ({self.novelty_rate:.1%})")
        print(f"  Passed time-slice: {self.num_passed_time_slice}")
        print(f"  Validated:         {self.num_validated}")
        print(f"  Rejected:          {self.num_rejected}")
        print(f"\nQuality:")
        print(f"  Avg confidence:    {self.avg_confidence:.3f}")
        print(f"  Validation rate:   {self.validation_rate:.1%}")
        print(f"\nImpact:")
        print(f"  Avg model lift:    {self.avg_model_lift:.4f}")
        print(f"  Total model lift:  {self.total_model_lift:.4f}")
        print(f"\nProvenance:          {self.provenance_completeness:.1%} complete")
