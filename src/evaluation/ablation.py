"""Ablation studies for hypothesis validation."""

from dataclasses import dataclass, field
from typing import Optional, Callable
import numpy as np
from sklearn.model_selection import KFold
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge

from ..kg_store.graph import KnowledgeGraph
from ..schema.hypothesis import HypothesisEdge, HypothesisStatus
from ..schema.entities import PropertyType
from .metrics import PropertyPredictionMetrics


@dataclass
class AblationResult:
    """Result of an ablation study."""
    hypothesis_id: str
    baseline_rmse: float
    with_edge_rmse: float
    delta_rmse: float  # Negative means improvement
    relative_improvement: float  # Percentage improvement
    is_significant: bool
    p_value: Optional[float] = None
    num_folds: int = 5


class AblationStudy:
    """
    Ablation studies to verify hypothesis impact on predictive tasks.

    Tests whether adding a hypothesized edge improves model performance.
    """

    def __init__(self, kg: KnowledgeGraph):
        self.kg = kg
        self._results: dict[str, AblationResult] = {}

    def prepare_conductivity_data(
        self,
    ) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """
        Prepare data for conductivity prediction task.

        Returns (X, y, formulation_ids) where:
        - X: feature matrix (formulation composition)
        - y: target vector (conductivity values)
        - formulation_ids: list of formulation IDs
        """
        X_list = []
        y_list = []
        form_ids = []

        # Get all solvents and salt for feature indices
        all_molecules = {}
        for mol_id, mol in self.kg._solvents.items():
            all_molecules[mol_id] = len(all_molecules)
        for mol_id, mol in self.kg._salts.items():
            all_molecules[mol_id] = len(all_molecules)
        for mol_id, mol in self.kg._additives.items():
            all_molecules[mol_id] = len(all_molecules)

        num_features = len(all_molecules)

        for f in self.kg._formulations.values():
            # Get conductivity measurement
            conductivity = None
            for m_id in f.measurements:
                m = self.kg._measurements.get(m_id)
                if m and m.property_type == PropertyType.IONIC_CONDUCTIVITY:
                    conductivity = m.value
                    break

            if conductivity is None:
                continue

            # Build feature vector
            features = np.zeros(num_features)
            for comp in f.components:
                if comp.molecule_id in all_molecules:
                    idx = all_molecules[comp.molecule_id]
                    features[idx] = comp.amount

            X_list.append(features)
            y_list.append(conductivity)
            form_ids.append(f.id)

        return np.array(X_list), np.array(y_list), form_ids

    def run_ablation(
        self,
        hypothesis: HypothesisEdge,
        X: np.ndarray,
        y: np.ndarray,
        n_folds: int = 5,
        model_class: type = RandomForestRegressor,
        model_kwargs: Optional[dict] = None,
    ) -> AblationResult:
        """
        Run ablation study for a single hypothesis.

        Compares model performance with and without the edge.
        """
        if model_kwargs is None:
            model_kwargs = {"n_estimators": 100, "random_state": 42}

        if len(X) < n_folds * 2:
            # Not enough data for cross-validation
            return AblationResult(
                hypothesis_id=hypothesis.id,
                baseline_rmse=float("nan"),
                with_edge_rmse=float("nan"),
                delta_rmse=0.0,
                relative_improvement=0.0,
                is_significant=False,
                num_folds=0,
            )

        kf = KFold(n_splits=n_folds, shuffle=True, random_state=42)

        baseline_errors = []
        with_edge_errors = []

        for train_idx, test_idx in kf.split(X):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            # Baseline model
            model_baseline = model_class(**model_kwargs)
            model_baseline.fit(X_train, y_train)
            pred_baseline = model_baseline.predict(X_test)
            baseline_errors.append(np.sqrt(np.mean((y_test - pred_baseline) ** 2)))

            # Model with edge (add feature based on hypothesis)
            X_train_aug = self._augment_features(X_train, hypothesis)
            X_test_aug = self._augment_features(X_test, hypothesis)

            model_aug = model_class(**model_kwargs)
            model_aug.fit(X_train_aug, y_train)
            pred_aug = model_aug.predict(X_test_aug)
            with_edge_errors.append(np.sqrt(np.mean((y_test - pred_aug) ** 2)))

        baseline_rmse = np.mean(baseline_errors)
        with_edge_rmse = np.mean(with_edge_errors)
        delta = with_edge_rmse - baseline_rmse
        relative_improvement = -delta / baseline_rmse if baseline_rmse > 0 else 0.0

        # Simple significance test (paired t-test)
        from scipy import stats
        t_stat, p_value = stats.ttest_rel(baseline_errors, with_edge_errors)
        is_significant = p_value < 0.05 and delta < 0

        result = AblationResult(
            hypothesis_id=hypothesis.id,
            baseline_rmse=baseline_rmse,
            with_edge_rmse=with_edge_rmse,
            delta_rmse=delta,
            relative_improvement=relative_improvement,
            is_significant=is_significant,
            p_value=p_value,
            num_folds=n_folds,
        )

        self._results[hypothesis.id] = result

        # Update hypothesis with result
        hypothesis.model_lift = -delta if delta < 0 else 0.0
        hypothesis.ablation_verified = is_significant
        hypothesis.validation_results.append({
            "method": "ablation",
            "baseline_rmse": baseline_rmse,
            "with_edge_rmse": with_edge_rmse,
            "delta": delta,
            "p_value": p_value,
            "significant": is_significant,
        })

        if is_significant:
            hypothesis.status = HypothesisStatus.VALIDATED
        elif delta > 0.05 * baseline_rmse:  # Made things worse
            hypothesis.status = HypothesisStatus.REJECTED

        return result

    def _augment_features(
        self,
        X: np.ndarray,
        hypothesis: HypothesisEdge,
    ) -> np.ndarray:
        """
        Augment feature matrix based on hypothesis.

        For now, adds an indicator feature based on the hypothesis relation.
        """
        # Simple augmentation: add interaction term
        # This is a simplified version; full impl would depend on hypothesis type
        new_feature = np.zeros((X.shape[0], 1))

        # For property-effect hypotheses, use component presence as feature
        if hypothesis.subject_id in self.kg._molecules:
            mol_idx = None
            for i, (mol_id, _) in enumerate(self.kg._molecules.items()):
                if mol_id == hypothesis.subject_id:
                    mol_idx = i
                    break

            if mol_idx is not None and mol_idx < X.shape[1]:
                # Interaction with presence of this component
                new_feature[:, 0] = X[:, mol_idx] > 0

        return np.hstack([X, new_feature])

    def run_all_ablations(
        self,
        hypotheses: list[HypothesisEdge],
        X: Optional[np.ndarray] = None,
        y: Optional[np.ndarray] = None,
        top_k: int = 10,
        **kwargs,
    ) -> list[AblationResult]:
        """
        Run ablation studies for multiple hypotheses.

        Args:
            hypotheses: List of hypotheses to evaluate
            X, y: Data matrices (if None, will prepare from KG)
            top_k: Only evaluate top-k by confidence
            **kwargs: Passed to run_ablation
        """
        if X is None or y is None:
            X, y, _ = self.prepare_conductivity_data()

        # Sort by confidence and take top-k
        sorted_hyps = sorted(hypotheses, key=lambda h: h.confidence, reverse=True)
        to_evaluate = sorted_hyps[:top_k]

        results = []
        for h in to_evaluate:
            result = self.run_ablation(h, X, y, **kwargs)
            results.append(result)

        return results

    def summary(self) -> dict:
        """Get summary of ablation studies."""
        if not self._results:
            return {"num_studies": 0}

        results = list(self._results.values())
        significant = [r for r in results if r.is_significant]

        return {
            "num_studies": len(results),
            "num_significant": len(significant),
            "avg_delta_rmse": np.mean([r.delta_rmse for r in results]),
            "avg_improvement": np.mean([
                r.relative_improvement for r in significant
            ]) if significant else 0.0,
            "best_improvement": max(
                [r.relative_improvement for r in significant]
            ) if significant else 0.0,
        }
