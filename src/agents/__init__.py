"""
Agentic AI modules for KG-driven discovery.

This package implements the multi-agent architecture from the Practical Pilot Plan:
- Explorer: Finds gaps, missing relations, low-coverage regions
- Hypothesis: Proposes KG augmentations via embeddings + rule mining
- Evaluator: Tests hypotheses via predictive deltas and ablation
- Curator: Human-in-the-loop validation and KG integration
- Orchestrator: Coordinates the discovery pipeline
"""

from .base import BaseAgent
from .explorer import ExplorerAgent
from .hypothesis import HypothesisAgent
from .evaluator import EvaluatorAgent
from .curator import CuratorAgent
from .orchestrator import DiscoveryOrchestrator, run_discovery_pipeline

__all__ = [
    "BaseAgent",
    "ExplorerAgent",
    "HypothesisAgent",
    "EvaluatorAgent",
    "CuratorAgent",
    "DiscoveryOrchestrator",
    "run_discovery_pipeline",
]
