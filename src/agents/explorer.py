"""
Explorer Agent: Finds gaps, missing relations, and low-coverage regions in the KG.

This agent analyzes the knowledge graph to identify:
1. Molecules without property measurements
2. Low-coverage regions (solvent combinations with few measurements)
3. Missing cross-dataset links (molecules in one source but not linked)
4. Property coverage gaps (molecules with some but not all properties)
5. Outliers and potential data quality issues
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from .base import BaseAgent, AgentResult


@dataclass
class CandidateGap:
    """A candidate gap or hypothesis area identified by the Explorer."""

    gap_type: str  # e.g., "missing_property", "low_coverage", "missing_link"
    description: str
    entities: list = field(default_factory=list)  # Affected entity IDs
    priority: float = 0.5  # 0-1, higher = more important
    evidence: dict = field(default_factory=dict)  # Supporting data
    actionable: bool = True  # Can this gap be addressed?

    def to_dict(self) -> dict:
        return {
            "gap_type": self.gap_type,
            "description": self.description,
            "entities": self.entities[:10],  # Limit for readability
            "entity_count": len(self.entities),
            "priority": self.priority,
            "evidence": self.evidence,
            "actionable": self.actionable,
        }


class ExplorerAgent(BaseAgent):
    """
    Explores the KG to find gaps and candidate hypothesis areas.

    Implements gap detection strategies:
    - Coverage analysis: Which molecules lack measurements?
    - Cross-dataset linking: Which molecules should be linked but aren't?
    - Property completeness: Which entities have partial property coverage?
    - Outlier detection: Which measurements seem anomalous?
    """

    def __init__(self, kg, name: str = "Explorer"):
        super().__init__(kg, name)
        self.gaps: list[CandidateGap] = []

    def run(
        self,
        analyze_coverage: bool = True,
        analyze_links: bool = True,
        analyze_properties: bool = True,
        analyze_outliers: bool = True,
        top_k: int = 20,
        **kwargs
    ) -> AgentResult:
        """
        Run exploration analysis on the KG.

        Args:
            analyze_coverage: Check for molecules without measurements
            analyze_links: Check for missing cross-dataset links
            analyze_properties: Check for partial property coverage
            analyze_outliers: Check for anomalous measurements
            top_k: Number of top gaps to return per category

        Returns:
            AgentResult with identified gaps
        """
        if not self.validate():
            return AgentResult(
                agent_name=self.name,
                success=False,
                errors=["Validation failed"]
            )

        self.logger.info("Starting KG exploration...")
        self.gaps = []
        metrics = {}

        # Run analyses
        if analyze_coverage:
            coverage_gaps = self._analyze_coverage()
            self.gaps.extend(coverage_gaps)
            metrics["coverage_gaps"] = len(coverage_gaps)

        if analyze_links:
            link_gaps = self._analyze_missing_links()
            self.gaps.extend(link_gaps)
            metrics["link_gaps"] = len(link_gaps)

        if analyze_properties:
            property_gaps = self._analyze_property_completeness()
            self.gaps.extend(property_gaps)
            metrics["property_gaps"] = len(property_gaps)

        if analyze_outliers:
            outlier_gaps = self._analyze_outliers()
            self.gaps.extend(outlier_gaps)
            metrics["outlier_gaps"] = len(outlier_gaps)

        # Sort by priority
        self.gaps.sort(key=lambda g: g.priority, reverse=True)

        # Prepare outputs
        outputs = {
            "total_gaps": len(self.gaps),
            "gaps_by_type": Counter(g.gap_type for g in self.gaps),
            "top_gaps": [g.to_dict() for g in self.gaps[:top_k]],
            "actionable_count": sum(1 for g in self.gaps if g.actionable),
        }

        self.logger.info(f"Found {len(self.gaps)} gaps in KG")

        return AgentResult(
            agent_name=self.name,
            success=True,
            outputs=outputs,
            metrics=metrics,
            provenance={
                "kg_version": self.kg.get("version", "unknown"),
                "analyses_run": {
                    "coverage": analyze_coverage,
                    "links": analyze_links,
                    "properties": analyze_properties,
                    "outliers": analyze_outliers,
                },
            }
        )

    def _analyze_coverage(self) -> list[CandidateGap]:
        """Find molecules without property measurements."""
        gaps = []
        molecules = self.kg.get("molecules", {})
        relations = self.kg.get("relations", [])

        # Build molecule -> measurements map
        mol_measurements = defaultdict(list)
        for subj, rel, obj in relations:
            if rel == "hasMeasurement":
                mol_measurements[subj].append(obj)

        # Find molecules without measurements
        no_measurements = []
        for mol_id in molecules:
            if mol_id not in mol_measurements:
                no_measurements.append(mol_id)

        if no_measurements:
            # Categorize by molecule type
            solvents = self.kg.get("solvents", {})
            salts = self.kg.get("salts", {})

            no_meas_solvents = [m for m in no_measurements if m in solvents]
            no_meas_salts = [m for m in no_measurements if m in salts]
            no_meas_other = [m for m in no_measurements
                           if m not in solvents and m not in salts]

            if no_meas_solvents:
                gaps.append(CandidateGap(
                    gap_type="missing_measurements",
                    description=f"{len(no_meas_solvents)} solvents have no property measurements",
                    entities=no_meas_solvents,
                    priority=0.8,
                    evidence={"molecule_type": "solvent"},
                    actionable=True,
                ))

            if no_meas_salts:
                gaps.append(CandidateGap(
                    gap_type="missing_measurements",
                    description=f"{len(no_meas_salts)} salts have no property measurements",
                    entities=no_meas_salts,
                    priority=0.7,
                    evidence={"molecule_type": "salt"},
                    actionable=True,
                ))

            if no_meas_other:
                gaps.append(CandidateGap(
                    gap_type="missing_measurements",
                    description=f"{len(no_meas_other)} molecules have no property measurements",
                    entities=no_meas_other,
                    priority=0.5,
                    evidence={"molecule_type": "other"},
                    actionable=True,
                ))

        # Find formulations without measurements
        formulations = self.kg.get("formulations", {})
        no_meas_formulations = [f for f in formulations if f not in mol_measurements]

        if no_meas_formulations:
            gaps.append(CandidateGap(
                gap_type="missing_measurements",
                description=f"{len(no_meas_formulations)} formulations have no measurements",
                entities=no_meas_formulations,
                priority=0.9,
                evidence={"entity_type": "formulation"},
                actionable=True,
            ))

        return gaps

    def _analyze_missing_links(self) -> list[CandidateGap]:
        """Find molecules that should be linked but aren't."""
        gaps = []
        molecules = self.kg.get("molecules", {})
        relations = self.kg.get("relations", [])

        # Build SMILES -> molecule IDs map
        smiles_to_mols = defaultdict(list)
        for mol_id, mol in molecules.items():
            smiles = mol.get("smiles")
            if smiles:
                smiles_to_mols[smiles].append(mol_id)

        # Find existing sameAs links
        same_as_links = set()
        for subj, rel, obj in relations:
            if rel == "sameAs":
                same_as_links.add((subj, obj))
                same_as_links.add((obj, subj))

        # Find SMILES with multiple molecules but no sameAs links
        missing_links = []
        for smiles, mol_ids in smiles_to_mols.items():
            if len(mol_ids) > 1:
                # Check if all pairs are linked
                for i, mol1 in enumerate(mol_ids):
                    for mol2 in mol_ids[i+1:]:
                        if (mol1, mol2) not in same_as_links:
                            missing_links.append((mol1, mol2, smiles))

        if missing_links:
            gaps.append(CandidateGap(
                gap_type="missing_sameAs_link",
                description=f"{len(missing_links)} molecule pairs share SMILES but lack sameAs links",
                entities=[f"{m1}↔{m2}" for m1, m2, _ in missing_links[:20]],
                priority=0.85,
                evidence={
                    "link_count": len(missing_links),
                    "sample_smiles": [s for _, _, s in missing_links[:5]],
                },
                actionable=True,
            ))

        return gaps

    def _analyze_property_completeness(self) -> list[CandidateGap]:
        """Find entities with partial property coverage."""
        gaps = []
        measurements = self.kg.get("measurements", {})
        relations = self.kg.get("relations", [])
        solvents = self.kg.get("solvents", {})

        # Define expected property types for solvents
        expected_properties = {
            "ionic_conductivity",
            "ionization_energy",
            "electron_affinity",
        }

        # Build molecule -> property types map
        mol_properties = defaultdict(set)
        for subj, rel, obj in relations:
            if rel == "hasMeasurement" and obj in measurements:
                prop_type = measurements[obj].get("property_type")
                if prop_type:
                    mol_properties[subj].add(prop_type)

        # Find solvents with partial coverage
        partial_coverage = []
        for sol_id in solvents:
            props = mol_properties.get(sol_id, set())
            if props and props != expected_properties:
                missing = expected_properties - props
                if missing:
                    partial_coverage.append({
                        "id": sol_id,
                        "has": list(props),
                        "missing": list(missing),
                    })

        if partial_coverage:
            # Group by missing property
            by_missing = defaultdict(list)
            for item in partial_coverage:
                for prop in item["missing"]:
                    by_missing[prop].append(item["id"])

            for prop, mol_ids in by_missing.items():
                gaps.append(CandidateGap(
                    gap_type="partial_property_coverage",
                    description=f"{len(mol_ids)} solvents missing {prop} measurements",
                    entities=mol_ids,
                    priority=0.7,
                    evidence={
                        "missing_property": prop,
                        "has_other_properties": True,
                    },
                    actionable=True,
                ))

        return gaps

    def _analyze_outliers(self) -> list[CandidateGap]:
        """Find potential outliers and data quality issues."""
        gaps = []
        measurements = self.kg.get("measurements", {})

        # Group measurements by property type
        by_property = defaultdict(list)
        for meas_id, meas in measurements.items():
            prop_type = meas.get("property_type")
            value = meas.get("value")
            if prop_type and value is not None:
                try:
                    by_property[prop_type].append((meas_id, float(value)))
                except (ValueError, TypeError):
                    pass

        # Find outliers using IQR method
        for prop_type, values in by_property.items():
            if len(values) < 10:
                continue

            vals = np.array([v[1] for v in values])
            q1, q3 = np.percentile(vals, [25, 75])
            iqr = q3 - q1
            lower = q1 - 3 * iqr
            upper = q3 + 3 * iqr

            outliers = [(mid, v) for mid, v in values if v < lower or v > upper]

            if outliers and len(outliers) < len(values) * 0.05:  # Less than 5%
                gaps.append(CandidateGap(
                    gap_type="potential_outlier",
                    description=f"{len(outliers)} potential outliers in {prop_type}",
                    entities=[o[0] for o in outliers],
                    priority=0.6,
                    evidence={
                        "property_type": prop_type,
                        "expected_range": [float(lower), float(upper)],
                        "outlier_values": [o[1] for o in outliers[:10]],
                        "total_measurements": len(values),
                    },
                    actionable=False,  # Needs human review
                ))

        return gaps

    def get_hypothesis_candidates(self, top_k: int = 10) -> list[dict]:
        """
        Extract actionable hypothesis candidates from gaps.

        Returns structured candidates for the Hypothesis Agent.
        """
        candidates = []

        for gap in self.gaps:
            if not gap.actionable:
                continue

            if gap.gap_type == "missing_measurements":
                candidates.append({
                    "type": "predict_property",
                    "description": f"Predict properties for {gap.evidence.get('molecule_type', 'entity')}",
                    "target_entities": gap.entities[:100],
                    "priority": gap.priority,
                    "source_gap": gap.gap_type,
                })

            elif gap.gap_type == "missing_sameAs_link":
                candidates.append({
                    "type": "link_entities",
                    "description": "Create sameAs links for matching SMILES",
                    "target_pairs": gap.entities,
                    "priority": gap.priority,
                    "source_gap": gap.gap_type,
                })

            elif gap.gap_type == "partial_property_coverage":
                candidates.append({
                    "type": "complete_properties",
                    "description": f"Predict {gap.evidence.get('missing_property')} for solvents",
                    "target_entities": gap.entities[:100],
                    "missing_property": gap.evidence.get("missing_property"),
                    "priority": gap.priority,
                    "source_gap": gap.gap_type,
                })

        # Sort by priority and return top_k
        candidates.sort(key=lambda c: c["priority"], reverse=True)
        return candidates[:top_k]

    def report(self, result: AgentResult) -> str:
        """Generate human-readable exploration report."""
        lines = [super().report(result)]

        if result.success:
            outputs = result.outputs
            lines.append(f"\nTotal gaps found: {outputs.get('total_gaps', 0)}")
            lines.append(f"Actionable gaps: {outputs.get('actionable_count', 0)}")

            lines.append("\nGaps by type:")
            for gap_type, count in outputs.get("gaps_by_type", {}).items():
                lines.append(f"  {gap_type}: {count}")

            lines.append("\nTop priority gaps:")
            for i, gap in enumerate(outputs.get("top_gaps", [])[:5], 1):
                lines.append(f"  {i}. [{gap['gap_type']}] {gap['description']}")
                lines.append(f"     Priority: {gap['priority']:.2f}, Entities: {gap['entity_count']}")

        return "\n".join(lines)
