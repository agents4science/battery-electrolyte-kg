"""
Agentic AI modules for KG-driven discovery.

This package implements the multi-agent architecture from the Practical Pilot Plan:
- Explorer: Finds gaps, missing relations, low-coverage regions
- Hypothesis: Proposes KG augmentations via embeddings + rule mining
- Evaluator: Tests hypotheses via predictive deltas and ablation
- Curator: Human-in-the-loop validation (future)
"""

from .base import BaseAgent
from .explorer import ExplorerAgent
from .hypothesis import HypothesisAgent
from .evaluator import EvaluatorAgent

__all__ = [
    "BaseAgent",
    "ExplorerAgent",
    "HypothesisAgent",
    "EvaluatorAgent",
]
