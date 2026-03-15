"""Link prediction using KG embeddings."""

from typing import Optional
from pathlib import Path
import numpy as np

from ..kg_store.graph import KnowledgeGraph
from ..schema.hypothesis import HypothesisEdge, HypothesisSource, HypothesisStatus
from ..schema.relations import RelationType


class LinkPredictor:
    """
    Link prediction for KG completion using embeddings.

    Uses PyKEEN for training KG embedding models (TransE, ComplEx, RotatE, etc.)
    to score and rank candidate missing edges.
    """

    def __init__(
        self,
        kg: KnowledgeGraph,
        model_name: str = "TransE",
        embedding_dim: int = 128,
    ):
        self.kg = kg
        self.model_name = model_name
        self.embedding_dim = embedding_dim
        self._model = None
        self._entity_to_id: dict[str, int] = {}
        self._id_to_entity: dict[int, str] = {}
        self._relation_to_id: dict[str, int] = {}
        self._id_to_relation: dict[int, str] = {}

    def prepare_triples(self) -> np.ndarray:
        """Convert KG to triple array for training."""
        triples_list = self.kg.to_triples()

        # Build entity and relation mappings
        entities = set()
        relations = set()
        for s, r, o in triples_list:
            entities.add(s)
            entities.add(o)
            relations.add(r)

        self._entity_to_id = {e: i for i, e in enumerate(sorted(entities))}
        self._id_to_entity = {i: e for e, i in self._entity_to_id.items()}
        self._relation_to_id = {r: i for i, r in enumerate(sorted(relations))}
        self._id_to_relation = {i: r for r, i in self._relation_to_id.items()}

        # Convert to numeric array
        triples = []
        for s, r, o in triples_list:
            if s in self._entity_to_id and o in self._entity_to_id and r in self._relation_to_id:
                triples.append([
                    self._entity_to_id[s],
                    self._relation_to_id[r],
                    self._entity_to_id[o],
                ])

        return np.array(triples, dtype=np.int64) if triples else np.array([], dtype=np.int64)

    def train(
        self,
        epochs: int = 100,
        batch_size: int = 256,
        learning_rate: float = 0.01,
    ) -> dict:
        """
        Train a KG embedding model.

        Returns training statistics.
        """
        try:
            from pykeen.pipeline import pipeline
            from pykeen.triples import TriplesFactory
        except ImportError:
            return self._train_simple(epochs, learning_rate)

        triples = self.prepare_triples()
        if len(triples) == 0:
            return {"error": "No triples to train on"}

        # Create TriplesFactory
        tf = TriplesFactory.from_labeled_triples(
            triples=np.array([
                (self._id_to_entity[h], self._id_to_relation[r], self._id_to_entity[t])
                for h, r, t in triples
            ]),
        )

        # Run training pipeline
        result = pipeline(
            training=tf,
            model=self.model_name,
            model_kwargs={"embedding_dim": self.embedding_dim},
            training_kwargs={
                "num_epochs": epochs,
                "batch_size": batch_size,
            },
            optimizer_kwargs={"lr": learning_rate},
            random_seed=42,
        )

        self._model = result.model

        return {
            "model": self.model_name,
            "num_entities": len(self._entity_to_id),
            "num_relations": len(self._relation_to_id),
            "num_triples": len(triples),
            "epochs": epochs,
            "losses": result.losses if hasattr(result, "losses") else [],
        }

    def _train_simple(self, epochs: int, learning_rate: float) -> dict:
        """
        Simple embedding training without PyKEEN.

        Uses basic TransE implementation.
        """
        triples = self.prepare_triples()
        if len(triples) == 0:
            return {"error": "No triples to train on"}

        num_entities = len(self._entity_to_id)
        num_relations = len(self._relation_to_id)

        # Initialize embeddings
        np.random.seed(42)
        self._entity_embeddings = np.random.randn(num_entities, self.embedding_dim) * 0.1
        self._relation_embeddings = np.random.randn(num_relations, self.embedding_dim) * 0.1

        # Normalize entity embeddings
        self._entity_embeddings /= np.linalg.norm(
            self._entity_embeddings, axis=1, keepdims=True
        )

        losses = []
        for epoch in range(epochs):
            epoch_loss = 0.0

            # Shuffle triples
            np.random.shuffle(triples)

            for h, r, t in triples:
                # TransE: h + r ≈ t
                h_emb = self._entity_embeddings[h]
                r_emb = self._relation_embeddings[r]
                t_emb = self._entity_embeddings[t]

                # Compute loss (distance)
                pred = h_emb + r_emb
                loss = np.sum((pred - t_emb) ** 2)
                epoch_loss += loss

                # Gradient update
                grad = 2 * (pred - t_emb)
                self._entity_embeddings[h] -= learning_rate * grad
                self._relation_embeddings[r] -= learning_rate * grad
                self._entity_embeddings[t] += learning_rate * grad

            # Normalize
            self._entity_embeddings /= np.linalg.norm(
                self._entity_embeddings, axis=1, keepdims=True
            )

            losses.append(epoch_loss / len(triples))

        return {
            "model": "TransE-simple",
            "num_entities": num_entities,
            "num_relations": num_relations,
            "num_triples": len(triples),
            "epochs": epochs,
            "final_loss": losses[-1] if losses else None,
        }

    def score_triple(self, subject: str, relation: str, obj: str) -> float:
        """Score a candidate triple using the trained model."""
        if self._model is not None:
            # Use PyKEEN model
            import torch
            scores = self._model.score_hrt(
                torch.tensor([[
                    self._entity_to_id.get(subject, 0),
                    self._relation_to_id.get(relation, 0),
                    self._entity_to_id.get(obj, 0),
                ]])
            )
            return float(scores[0])

        elif hasattr(self, "_entity_embeddings"):
            # Use simple embeddings
            h_id = self._entity_to_id.get(subject)
            r_id = self._relation_to_id.get(relation)
            t_id = self._entity_to_id.get(obj)

            if h_id is None or r_id is None or t_id is None:
                return float("-inf")

            h_emb = self._entity_embeddings[h_id]
            r_emb = self._relation_embeddings[r_id]
            t_emb = self._entity_embeddings[t_id]

            # TransE: score = -||h + r - t||
            distance = np.linalg.norm(h_emb + r_emb - t_emb)
            return -distance

        return 0.0

    def predict_tails(
        self,
        subject: str,
        relation: str,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """Predict top-k tail entities for (subject, relation, ?)."""
        if subject not in self._entity_to_id or relation not in self._relation_to_id:
            return []

        scores = []
        for entity_id, entity in self._id_to_entity.items():
            if entity != subject:  # Exclude self-loops
                score = self.score_triple(subject, relation, entity)
                scores.append((entity, score))

        # Sort by score (higher is better)
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def predict_heads(
        self,
        relation: str,
        obj: str,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """Predict top-k head entities for (?, relation, object)."""
        if obj not in self._entity_to_id or relation not in self._relation_to_id:
            return []

        scores = []
        for entity_id, entity in self._id_to_entity.items():
            if entity != obj:
                score = self.score_triple(entity, relation, obj)
                scores.append((entity, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def generate_candidates(
        self,
        relations: Optional[list[RelationType]] = None,
        top_k_per_entity: int = 5,
        min_score: float = -float("inf"),
    ) -> list[HypothesisEdge]:
        """
        Generate candidate hypothesis edges using link prediction.

        Returns list of HypothesisEdge objects ranked by confidence.
        """
        if relations is None:
            relations = [
                RelationType.HAS_SOLVENT,
                RelationType.HAS_SALT,
                RelationType.HAS_ADDITIVE,
                RelationType.INCREASES,
                RelationType.DECREASES,
            ]

        candidates = []
        existing_triples = set(self.kg.to_triples())

        for rel in relations:
            rel_str = rel.value

            # Skip if relation not in training data
            if rel_str not in self._relation_to_id:
                continue

            # For each entity, predict tails
            for entity_id in self._entity_to_id:
                predictions = self.predict_tails(entity_id, rel_str, top_k_per_entity)

                for pred_entity, score in predictions:
                    if score < min_score:
                        continue

                    # Check if this is a novel edge
                    if (entity_id, rel_str, pred_entity) in existing_triples:
                        continue

                    # Create hypothesis
                    hypothesis = HypothesisEdge(
                        subject_id=entity_id,
                        subject_type=self._get_entity_type(entity_id),
                        relation=rel,
                        object_id=pred_entity,
                        object_type=self._get_entity_type(pred_entity),
                        status=HypothesisStatus.PROPOSED,
                        source=HypothesisSource.KG_EMBEDDING,
                        confidence=self._score_to_confidence(score),
                        model_name=self.model_name,
                        is_novel=True,
                    )
                    candidates.append(hypothesis)

        # Sort by confidence
        candidates.sort(key=lambda h: h.confidence, reverse=True)
        return candidates

    def _get_entity_type(self, entity_id: str) -> str:
        """Get the type of an entity from the KG."""
        if entity_id in self.kg._formulations:
            return "ElectrolyteFormulation"
        if entity_id in self.kg._solvents:
            return "Solvent"
        if entity_id in self.kg._salts:
            return "Salt"
        if entity_id in self.kg._additives:
            return "Additive"
        if entity_id in self.kg._molecules:
            return "Molecule"
        if entity_id in self.kg._measurements:
            return "PropertyMeasurement"
        if entity_id in self.kg._interphase_species:
            return "InterphaseSpecies"
        return "Unknown"

    def _score_to_confidence(self, score: float) -> float:
        """Convert model score to confidence in [0, 1]."""
        # Sigmoid transformation
        return 1.0 / (1.0 + np.exp(-score))

    def save(self, path: Path) -> None:
        """Save the trained model."""
        import pickle

        data = {
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim,
            "entity_to_id": self._entity_to_id,
            "id_to_entity": self._id_to_entity,
            "relation_to_id": self._relation_to_id,
            "id_to_relation": self._id_to_relation,
        }

        if hasattr(self, "_entity_embeddings"):
            data["entity_embeddings"] = self._entity_embeddings
            data["relation_embeddings"] = self._relation_embeddings

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(data, f)

    @classmethod
    def load(cls, path: Path, kg: KnowledgeGraph) -> "LinkPredictor":
        """Load a trained model."""
        import pickle

        with open(path, "rb") as f:
            data = pickle.load(f)

        predictor = cls(kg, data["model_name"], data["embedding_dim"])
        predictor._entity_to_id = data["entity_to_id"]
        predictor._id_to_entity = data["id_to_entity"]
        predictor._relation_to_id = data["relation_to_id"]
        predictor._id_to_relation = data["id_to_relation"]

        if "entity_embeddings" in data:
            predictor._entity_embeddings = data["entity_embeddings"]
            predictor._relation_embeddings = data["relation_embeddings"]

        return predictor
