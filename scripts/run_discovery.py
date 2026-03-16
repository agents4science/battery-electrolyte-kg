#!/usr/bin/env python3
"""
Run the agentic discovery pipeline on the Knowledge Graph.

This script executes the multi-agent discovery loop:
1. Explorer finds gaps and hypothesis candidates
2. Hypothesis Agent generates proposed KG augmentations
3. Evaluator validates hypotheses
4. Results are saved for human curation

Usage:
    python scripts/run_discovery.py
    python scripts/run_discovery.py --quick  # Fast mode
    python scripts/run_discovery.py --output data/output/discovery
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.orchestrator import DiscoveryOrchestrator


def main():
    parser = argparse.ArgumentParser(
        description="Run the agentic discovery pipeline"
    )
    parser.add_argument(
        "--kg",
        type=Path,
        default=PROJECT_ROOT / "data" / "output" / "knowledge_graph_v7.json.gz",
        help="Path to knowledge graph JSON"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "output" / "discovery",
        help="Output directory for results"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick discovery (fewer analyses)"
    )
    parser.add_argument(
        "--max-hypotheses",
        type=int,
        default=50,
        help="Maximum hypotheses to generate"
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.6,
        help="Minimum confidence threshold"
    )
    parser.add_argument(
        "--validation-threshold",
        type=float,
        default=0.7,
        help="Threshold for hypothesis validation"
    )

    args = parser.parse_args()

    # Check KG exists
    if not args.kg.exists():
        print(f"Error: KG not found at {args.kg}")
        sys.exit(1)

    print("=" * 70)
    print("AGENTIC DISCOVERY PIPELINE")
    print("=" * 70)
    print(f"KG: {args.kg}")
    print(f"Output: {args.output}")
    print(f"Mode: {'Quick' if args.quick else 'Full'}")
    print()

    # Initialize orchestrator
    orchestrator = DiscoveryOrchestrator(args.kg)

    # Run discovery
    if args.quick:
        run = orchestrator.run_quick_discovery()
    else:
        run = orchestrator.run_discovery_loop(
            max_hypotheses=args.max_hypotheses,
            min_confidence=args.min_confidence,
            validation_threshold=args.validation_threshold,
        )

    # Print report
    print()
    print(orchestrator.generate_report(run))

    # Save results
    orchestrator.save_run(run, args.output)
    print(f"\nResults saved to {args.output}")

    # Summary
    print("\n" + "=" * 70)
    print("DISCOVERY COMPLETE")
    print("=" * 70)
    print(f"Validated hypotheses: {len(run.validated_hypotheses)}")
    print(f"Ready for curation: {len(run.ready_for_curation)}")

    if run.validated_hypotheses:
        print("\nNext steps:")
        print("1. Review validated hypotheses in the output JSON")
        print("2. Use the Curator to approve/reject hypotheses")
        print("3. Merge approved hypotheses into the KG")


if __name__ == "__main__":
    main()
