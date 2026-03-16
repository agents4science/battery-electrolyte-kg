"""
Discovery Orchestrator: Coordinates the multi-agent discovery pipeline.

This orchestrator implements the discovery loop from the Practical Pilot:
1. Explorer finds gaps and candidate hypothesis areas
2. Hypothesis Agent proposes KG augmentations
3. Evaluator validates hypotheses
4. Curator (human-in-the-loop) approves final edges

The pipeline produces a "discovery funnel":
    Gaps → Candidates → Hypotheses → Validated → Curated → Merged
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import json
import logging

from .base import AgentResult
from .explorer import ExplorerAgent
from .hypothesis import HypothesisAgent
from .evaluator import EvaluatorAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DiscoveryOrchestrator")


@dataclass
class DiscoveryRun:
    """Record of a complete discovery pipeline run."""

    run_id: str
    timestamp: datetime
    kg_version: str
    stages: dict = field(default_factory=dict)
    funnel: dict = field(default_factory=dict)
    validated_hypotheses: list = field(default_factory=list)
    ready_for_curation: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "kg_version": self.kg_version,
            "stages": self.stages,
            "funnel": self.funnel,
            "validated_hypotheses": self.validated_hypotheses,
            "ready_for_curation": self.ready_for_curation,
            "metrics": self.metrics,
        }

    def save(self, path: Path):
        """Save run record to JSON."""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, default=str)


class DiscoveryOrchestrator:
    """
    Orchestrates the multi-agent discovery pipeline.

    Usage:
        orchestrator = DiscoveryOrchestrator(kg_path)
        run = orchestrator.run_discovery_loop()
        print(run.funnel)  # Discovery funnel statistics
    """

    def __init__(self, kg):
        """
        Initialize orchestrator with KG.

        Args:
            kg: KnowledgeGraph dict or path to KG JSON
        """
        self.kg = kg
        self._load_kg_if_path()
        self.runs: list[DiscoveryRun] = []

    def _load_kg_if_path(self):
        """Load KG if path was provided."""
        import gzip

        if isinstance(self.kg, (str, Path)):
            path = Path(self.kg)
            if path.suffix == '.gz':
                with gzip.open(path, 'rt', encoding='utf-8') as f:
                    self.kg = json.load(f)
            else:
                with open(path) as f:
                    self.kg = json.load(f)

    def run_discovery_loop(
        self,
        # Explorer settings
        explore_coverage: bool = True,
        explore_links: bool = True,
        explore_properties: bool = True,
        # Hypothesis settings
        hypothesis_association: bool = True,
        hypothesis_correlation: bool = True,
        hypothesis_causal: bool = True,
        min_confidence: float = 0.6,
        min_support: int = 5,
        max_hypotheses: int = 50,
        # Evaluator settings
        eval_plausibility: bool = True,
        eval_consistency: bool = True,
        eval_statistical: bool = True,
        validation_threshold: float = 0.7,
    ) -> DiscoveryRun:
        """
        Run the complete discovery loop.

        Returns:
            DiscoveryRun with all results and metrics
        """
        run_id = f"discovery-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        logger.info(f"Starting discovery run: {run_id}")

        run = DiscoveryRun(
            run_id=run_id,
            timestamp=datetime.now(),
            kg_version=self.kg.get("version", "unknown"),
        )

        # Stage 1: Exploration
        logger.info("Stage 1: Running Explorer agent...")
        explorer = ExplorerAgent(self.kg)
        explorer_result = explorer.run(
            analyze_coverage=explore_coverage,
            analyze_links=explore_links,
            analyze_properties=explore_properties,
        )
        run.stages["explorer"] = explorer_result.to_dict()

        gaps_found = explorer_result.outputs.get("total_gaps", 0)
        hypothesis_candidates = explorer.get_hypothesis_candidates(top_k=20)
        run.funnel["gaps_found"] = gaps_found
        run.funnel["hypothesis_candidates"] = len(hypothesis_candidates)

        logger.info(f"  Found {gaps_found} gaps, {len(hypothesis_candidates)} candidates")

        # Stage 2: Hypothesis Generation
        logger.info("Stage 2: Running Hypothesis agent...")
        hypothesis_agent = HypothesisAgent(self.kg)
        hypothesis_result = hypothesis_agent.run(
            run_association_mining=hypothesis_association,
            run_correlation_analysis=hypothesis_correlation,
            run_causal_inference=hypothesis_causal,
            min_confidence=min_confidence,
            min_support=min_support,
            top_k=max_hypotheses,
            explorer_candidates=hypothesis_candidates,
        )
        run.stages["hypothesis"] = hypothesis_result.to_dict()

        hypotheses_generated = hypothesis_result.outputs.get("total_hypotheses", 0)
        run.funnel["hypotheses_generated"] = hypotheses_generated

        logger.info(f"  Generated {hypotheses_generated} hypotheses")

        # Stage 3: Evaluation
        logger.info("Stage 3: Running Evaluator agent...")
        evaluator = EvaluatorAgent(self.kg)
        evaluator_result = evaluator.run(
            hypotheses=hypothesis_result.outputs.get("hypotheses", []),
            run_plausibility=eval_plausibility,
            run_consistency=eval_consistency,
            run_statistical=eval_statistical,
            validation_threshold=validation_threshold,
        )
        run.stages["evaluator"] = evaluator_result.to_dict()

        summary = evaluator_result.outputs.get("summary", {})
        run.funnel["validated"] = summary.get("validated", 0)
        run.funnel["rejected"] = summary.get("rejected", 0)
        run.funnel["inconclusive"] = summary.get("inconclusive", 0)

        logger.info(
            f"  Validated: {summary.get('validated', 0)}, "
            f"Rejected: {summary.get('rejected', 0)}, "
            f"Inconclusive: {summary.get('inconclusive', 0)}"
        )

        # Collect validated hypotheses - merge evaluation results with original hypothesis data
        eval_results = evaluator_result.outputs.get("validated_hypotheses", [])
        original_hypotheses = {h["hypothesis_id"]: h for h in hypothesis_result.outputs.get("hypotheses", [])}

        run.validated_hypotheses = []
        for eval_result in eval_results:
            hyp_id = eval_result.get("hypothesis_id")
            original = original_hypotheses.get(hyp_id, {})
            merged = {**original, **eval_result}  # Merge original hypothesis with eval result
            run.validated_hypotheses.append(merged)

        run.ready_for_curation = evaluator.get_for_curation()

        # Calculate overall metrics
        run.metrics = {
            "total_gaps": gaps_found,
            "total_hypotheses": hypotheses_generated,
            "validation_rate": run.funnel["validated"] / hypotheses_generated if hypotheses_generated > 0 else 0,
            "funnel_conversion": run.funnel["validated"] / gaps_found if gaps_found > 0 else 0,
            "ready_for_curation": len(run.ready_for_curation),
        }

        self.runs.append(run)
        logger.info(f"Discovery run complete: {run.funnel['validated']} validated hypotheses")

        return run

    def run_quick_discovery(self) -> DiscoveryRun:
        """Run a quick discovery with minimal settings."""
        return self.run_discovery_loop(
            explore_links=False,
            hypothesis_correlation=False,
            max_hypotheses=20,
            min_support=10,
        )

    def generate_report(self, run: DiscoveryRun) -> str:
        """Generate a human-readable report for a discovery run."""
        lines = [
            "=" * 70,
            "DISCOVERY PIPELINE REPORT",
            "=" * 70,
            f"Run ID: {run.run_id}",
            f"Timestamp: {run.timestamp}",
            f"KG Version: {run.kg_version}",
            "",
            "DISCOVERY FUNNEL",
            "-" * 40,
            f"  Gaps found:           {run.funnel.get('gaps_found', 0):>6}",
            f"  Hypothesis candidates:{run.funnel.get('hypothesis_candidates', 0):>6}",
            f"  Hypotheses generated: {run.funnel.get('hypotheses_generated', 0):>6}",
            f"  Validated:            {run.funnel.get('validated', 0):>6}",
            f"  Rejected:             {run.funnel.get('rejected', 0):>6}",
            f"  Inconclusive:         {run.funnel.get('inconclusive', 0):>6}",
            "",
            "METRICS",
            "-" * 40,
            f"  Validation rate:      {run.metrics.get('validation_rate', 0):.1%}",
            f"  Funnel conversion:    {run.metrics.get('funnel_conversion', 0):.1%}",
            f"  Ready for curation:   {run.metrics.get('ready_for_curation', 0)}",
            "",
        ]

        if run.validated_hypotheses:
            lines.extend([
                "VALIDATED HYPOTHESES",
                "-" * 40,
            ])
            for i, hyp in enumerate(run.validated_hypotheses[:10], 1):
                subj = hyp.get('subject', {}).get('name', 'unknown')
                obj = hyp.get('object', {}).get('name', 'unknown')
                hyp_type = hyp.get('hypothesis_type', 'unknown')
                conf = hyp.get('confidence', 0)
                lines.append(f"  {i}. {subj} --[{hyp_type}]--> {obj}")
                lines.append(f"     Confidence: {conf:.3f}")

        if run.ready_for_curation:
            lines.extend([
                "",
                "READY FOR CURATION",
                "-" * 40,
            ])
            for item in run.ready_for_curation[:5]:
                lines.append(f"  - {item['hypothesis_id']}: {item['action']}")

        lines.append("=" * 70)
        return "\n".join(lines)

    def save_run(self, run: DiscoveryRun, output_dir: Path):
        """Save discovery run to output directory."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save full run data
        run.save(output_dir / f"{run.run_id}.json")

        # Save report
        report_path = output_dir / f"{run.run_id}_report.txt"
        with open(report_path, 'w') as f:
            f.write(self.generate_report(run))

        logger.info(f"Saved run to {output_dir}")


def run_discovery_pipeline(kg_path: Path, output_dir: Optional[Path] = None) -> DiscoveryRun:
    """
    Convenience function to run the full discovery pipeline.

    Args:
        kg_path: Path to knowledge graph JSON
        output_dir: Optional directory to save results

    Returns:
        DiscoveryRun with results
    """
    orchestrator = DiscoveryOrchestrator(kg_path)
    run = orchestrator.run_discovery_loop()

    if output_dir:
        orchestrator.save_run(run, output_dir)

    print(orchestrator.generate_report(run))
    return run
