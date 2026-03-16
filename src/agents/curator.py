"""
Curator Agent: Human-in-the-loop validation and KG integration.

This agent handles:
1. Presenting validated hypotheses for human review
2. Recording approval/rejection decisions with rationale
3. Merging approved hypotheses into the KG with full provenance
4. Maintaining rejected hypotheses as negative evidence
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional
import json
import gzip
import hashlib

from .base import BaseAgent, AgentResult


@dataclass
class CurationDecision:
    """Record of a human curation decision."""

    hypothesis_id: str
    decision: Literal["approved", "rejected", "deferred"]
    curator: str = "human"
    rationale: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    modifications: dict = field(default_factory=dict)  # Any edits to the hypothesis

    def to_dict(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "decision": self.decision,
            "curator": self.curator,
            "rationale": self.rationale,
            "timestamp": self.timestamp.isoformat(),
            "modifications": self.modifications,
        }


@dataclass
class MergedEdge:
    """Record of an edge merged into the KG."""

    edge_id: str
    subject_id: str
    relation_type: str
    object_id: str
    hypothesis_id: str
    confidence: float
    provenance: dict
    merged_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "subject_id": self.subject_id,
            "relation_type": self.relation_type,
            "object_id": self.object_id,
            "hypothesis_id": self.hypothesis_id,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "merged_at": self.merged_at.isoformat(),
        }


class CuratorAgent(BaseAgent):
    """
    Manages human-in-the-loop curation of discovered hypotheses.

    Workflow:
    1. Load validated hypotheses from Evaluator
    2. Present for human review (via CLI or UI)
    3. Record decisions with rationale
    4. Merge approved hypotheses into KG with provenance
    5. Store rejected hypotheses as negative evidence
    """

    def __init__(self, kg, name: str = "Curator"):
        super().__init__(kg, name)
        self.decisions: list[CurationDecision] = []
        self.merged_edges: list[MergedEdge] = []
        self.pending_hypotheses: list[dict] = []

    def run(
        self,
        hypotheses: list[dict],
        auto_approve_threshold: Optional[float] = None,
        **kwargs
    ) -> AgentResult:
        """
        Process hypotheses for curation.

        Args:
            hypotheses: List of validated hypothesis dicts
            auto_approve_threshold: If set, auto-approve hypotheses above this confidence

        Returns:
            AgentResult with curation summary
        """
        if not self.validate():
            return AgentResult(
                agent_name=self.name,
                success=False,
                errors=["Validation failed"]
            )

        self.logger.info(f"Processing {len(hypotheses)} hypotheses for curation...")
        self.pending_hypotheses = hypotheses
        self.decisions = []

        metrics = {
            "total_hypotheses": len(hypotheses),
            "auto_approved": 0,
            "pending_review": 0,
        }

        # Auto-approve high-confidence hypotheses if threshold set
        if auto_approve_threshold is not None:
            for hyp in hypotheses:
                conf = hyp.get("confidence", 0)
                if conf >= auto_approve_threshold:
                    decision = CurationDecision(
                        hypothesis_id=hyp.get("hypothesis_id", "unknown"),
                        decision="approved",
                        curator="auto",
                        rationale=f"Auto-approved: confidence {conf:.3f} >= threshold {auto_approve_threshold}",
                    )
                    self.decisions.append(decision)
                    metrics["auto_approved"] += 1

        metrics["pending_review"] = len(hypotheses) - metrics["auto_approved"]

        outputs = {
            "pending_hypotheses": [h for h in hypotheses if not self._is_decided(h)],
            "decisions": [d.to_dict() for d in self.decisions],
            "summary": {
                "total": len(hypotheses),
                "auto_approved": metrics["auto_approved"],
                "pending": metrics["pending_review"],
            }
        }

        self.logger.info(
            f"Curation: {metrics['auto_approved']} auto-approved, "
            f"{metrics['pending_review']} pending review"
        )

        return AgentResult(
            agent_name=self.name,
            success=True,
            outputs=outputs,
            metrics=metrics,
            provenance={
                "kg_version": self.kg.get("version", "unknown"),
                "auto_approve_threshold": auto_approve_threshold,
            }
        )

    def _is_decided(self, hypothesis: dict) -> bool:
        """Check if hypothesis already has a decision."""
        hyp_id = hypothesis.get("hypothesis_id")
        return any(d.hypothesis_id == hyp_id for d in self.decisions)

    def approve(
        self,
        hypothesis_id: str,
        rationale: str = "",
        curator: str = "human",
        modifications: Optional[dict] = None
    ) -> CurationDecision:
        """Approve a hypothesis for merging into KG."""
        decision = CurationDecision(
            hypothesis_id=hypothesis_id,
            decision="approved",
            curator=curator,
            rationale=rationale,
            modifications=modifications or {},
        )
        self.decisions.append(decision)
        self.logger.info(f"Approved hypothesis: {hypothesis_id}")
        return decision

    def reject(
        self,
        hypothesis_id: str,
        rationale: str,
        curator: str = "human"
    ) -> CurationDecision:
        """Reject a hypothesis (stored as negative evidence)."""
        decision = CurationDecision(
            hypothesis_id=hypothesis_id,
            decision="rejected",
            curator=curator,
            rationale=rationale,
        )
        self.decisions.append(decision)
        self.logger.info(f"Rejected hypothesis: {hypothesis_id}")
        return decision

    def defer(
        self,
        hypothesis_id: str,
        rationale: str = "Needs more evidence",
        curator: str = "human"
    ) -> CurationDecision:
        """Defer decision on a hypothesis."""
        decision = CurationDecision(
            hypothesis_id=hypothesis_id,
            decision="deferred",
            curator=curator,
            rationale=rationale,
        )
        self.decisions.append(decision)
        self.logger.info(f"Deferred hypothesis: {hypothesis_id}")
        return decision

    def merge_approved(self) -> list[MergedEdge]:
        """
        Merge all approved hypotheses into the KG.

        Returns list of merged edges.
        """
        approved = [d for d in self.decisions if d.decision == "approved"]
        hyp_lookup = {h.get("hypothesis_id"): h for h in self.pending_hypotheses}

        merged = []
        relations = self.kg.get("relations", [])
        hypotheses_store = self.kg.get("hypotheses", {})

        for decision in approved:
            hyp = hyp_lookup.get(decision.hypothesis_id)
            if not hyp:
                continue

            # Apply any modifications
            if decision.modifications:
                hyp = {**hyp, **decision.modifications}

            # Extract edge components
            subject_id = hyp.get("subject", {}).get("id", "")
            object_id = hyp.get("object", {}).get("id", "")
            relation_type = hyp.get("hypothesis_type", "")

            if not all([subject_id, object_id, relation_type]):
                self.logger.warning(f"Skipping incomplete hypothesis: {decision.hypothesis_id}")
                continue

            # Check if edge already exists
            edge_exists = any(
                r[0] == subject_id and r[1] == relation_type and r[2] == object_id
                for r in relations
            )

            if edge_exists:
                self.logger.info(f"Edge already exists, skipping: {decision.hypothesis_id}")
                continue

            # Create edge ID
            edge_id = f"edge-{hashlib.md5(f'{subject_id}:{relation_type}:{object_id}'.encode()).hexdigest()[:12]}"

            # Build provenance
            provenance = {
                "source": "discovery_pipeline",
                "hypothesis_id": decision.hypothesis_id,
                "original_confidence": hyp.get("original_confidence", hyp.get("confidence")),
                "validated_confidence": hyp.get("confidence"),
                "evidence": hyp.get("evidence", {}),
                "curator": decision.curator,
                "curation_rationale": decision.rationale,
                "merged_at": datetime.now().isoformat(),
            }

            # Add to KG relations
            relations.append([subject_id, relation_type, object_id])

            # Store in hypotheses with validated status
            hypotheses_store[decision.hypothesis_id] = {
                **hyp,
                "status": "validated",
                "merged": True,
                "edge_id": edge_id,
                "curation": decision.to_dict(),
            }

            merged_edge = MergedEdge(
                edge_id=edge_id,
                subject_id=subject_id,
                relation_type=relation_type,
                object_id=object_id,
                hypothesis_id=decision.hypothesis_id,
                confidence=hyp.get("confidence", 0),
                provenance=provenance,
            )
            merged.append(merged_edge)
            self.merged_edges.append(merged_edge)

        # Update KG
        self.kg["relations"] = relations
        self.kg["hypotheses"] = hypotheses_store

        self.logger.info(f"Merged {len(merged)} edges into KG")
        return merged

    def store_rejected_as_negative_evidence(self):
        """Store rejected hypotheses as negative evidence in the KG."""
        rejected = [d for d in self.decisions if d.decision == "rejected"]
        hyp_lookup = {h.get("hypothesis_id"): h for h in self.pending_hypotheses}

        negative_evidence = self.kg.get("negative_evidence", {})

        for decision in rejected:
            hyp = hyp_lookup.get(decision.hypothesis_id)
            if not hyp:
                continue

            negative_evidence[decision.hypothesis_id] = {
                **hyp,
                "status": "rejected",
                "rejection_rationale": decision.rationale,
                "rejected_by": decision.curator,
                "rejected_at": decision.timestamp.isoformat(),
            }

        self.kg["negative_evidence"] = negative_evidence
        self.logger.info(f"Stored {len(rejected)} rejected hypotheses as negative evidence")

    def save_kg(self, path: Path):
        """Save the updated KG to file."""
        path = Path(path)

        if path.suffix == '.gz':
            with gzip.open(path, 'wt', encoding='utf-8') as f:
                json.dump(self.kg, f, default=str)
        else:
            with open(path, 'w') as f:
                json.dump(self.kg, f, indent=2, default=str)

        self.logger.info(f"Saved KG to {path}")

    def get_pending_for_review(self) -> list[dict]:
        """Get hypotheses pending human review."""
        decided_ids = {d.hypothesis_id for d in self.decisions}
        return [h for h in self.pending_hypotheses
                if h.get("hypothesis_id") not in decided_ids]

    def get_curation_summary(self) -> dict:
        """Get summary of curation decisions."""
        by_decision = {"approved": 0, "rejected": 0, "deferred": 0}
        for d in self.decisions:
            by_decision[d.decision] = by_decision.get(d.decision, 0) + 1

        return {
            "total_decisions": len(self.decisions),
            "by_decision": by_decision,
            "merged_edges": len(self.merged_edges),
            "pending_review": len(self.get_pending_for_review()),
        }

    def report(self, result: AgentResult) -> str:
        """Generate human-readable curation report."""
        lines = [super().report(result)]

        if result.success:
            summary = result.outputs.get("summary", {})
            lines.append(f"\nCuration Summary:")
            lines.append(f"  Total hypotheses: {summary.get('total', 0)}")
            lines.append(f"  Auto-approved: {summary.get('auto_approved', 0)}")
            lines.append(f"  Pending review: {summary.get('pending', 0)}")

            pending = result.outputs.get("pending_hypotheses", [])
            if pending:
                lines.append(f"\nPending Hypotheses for Review:")
                for i, hyp in enumerate(pending[:10], 1):
                    subj = hyp.get('subject', {}).get('name', 'unknown')
                    obj = hyp.get('object', {}).get('name', 'unknown')
                    rel = hyp.get('hypothesis_type', 'unknown')
                    conf = hyp.get('confidence', 0)
                    lines.append(f"  {i}. {subj} --[{rel}]--> {obj} (conf={conf:.3f})")

        return "\n".join(lines)


def interactive_curation(curator: CuratorAgent) -> None:
    """
    Interactive CLI for hypothesis curation.

    Allows human to review and approve/reject hypotheses one by one.
    """
    pending = curator.get_pending_for_review()

    if not pending:
        print("No hypotheses pending review.")
        return

    print(f"\n{'='*60}")
    print(f"INTERACTIVE CURATION - {len(pending)} hypotheses to review")
    print(f"{'='*60}")
    print("Commands: (a)pprove, (r)eject, (d)efer, (s)kip, (q)uit\n")

    for i, hyp in enumerate(pending, 1):
        print(f"\n--- Hypothesis {i}/{len(pending)} ---")
        print(f"ID: {hyp.get('hypothesis_id')}")
        print(f"Type: {hyp.get('hypothesis_type')}")
        print(f"Subject: {hyp.get('subject', {}).get('name')} ({hyp.get('subject', {}).get('id', '')[:20]}...)")
        print(f"Object: {hyp.get('object', {}).get('name')} ({hyp.get('object', {}).get('id', '')[:20]}...)")
        print(f"Confidence: {hyp.get('confidence', 0):.3f}")
        print(f"Explanation: {hyp.get('explanation', 'N/A')}")

        evidence = hyp.get('evidence', {})
        if evidence:
            print("Evidence:")
            for k, v in list(evidence.items())[:5]:
                print(f"  {k}: {v}")

        while True:
            cmd = input("\nDecision [a/r/d/s/q]: ").strip().lower()

            if cmd == 'a':
                rationale = input("Rationale (optional): ").strip()
                curator.approve(hyp['hypothesis_id'], rationale)
                break
            elif cmd == 'r':
                rationale = input("Rejection reason (required): ").strip()
                if not rationale:
                    print("Rejection requires a rationale.")
                    continue
                curator.reject(hyp['hypothesis_id'], rationale)
                break
            elif cmd == 'd':
                rationale = input("Deferral reason (optional): ").strip() or "Needs more evidence"
                curator.defer(hyp['hypothesis_id'], rationale)
                break
            elif cmd == 's':
                print("Skipped.")
                break
            elif cmd == 'q':
                print("Curation session ended.")
                return
            else:
                print("Invalid command. Use a/r/d/s/q")

    print(f"\n{'='*60}")
    print("CURATION COMPLETE")
    print(f"{'='*60}")
    summary = curator.get_curation_summary()
    print(f"Approved: {summary['by_decision']['approved']}")
    print(f"Rejected: {summary['by_decision']['rejected']}")
    print(f"Deferred: {summary['by_decision']['deferred']}")
