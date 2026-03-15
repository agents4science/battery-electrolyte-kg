#!/usr/bin/env python3
"""
Run the Electrolyte KG Discovery Pipeline.

This script demonstrates the full discovery loop:
1. Ingest structured datasets (Conductivity/EIS, LIBE)
2. Build a knowledge graph with provenance
3. Generate hypothesis edges using embeddings and rule mining
4. Evaluate hypotheses via ablation studies
5. Export results

Usage:
    python run_pipeline.py
    python run_pipeline.py --epochs 100 --max-hypotheses 50
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline import ElectrolyteKGPipeline


def main():
    """Run the discovery pipeline."""
    # Configure paths
    project_dir = Path(__file__).parent
    data_dir = project_dir / "data" / "raw"
    output_dir = project_dir / "data" / "output"

    print("\n" + "=" * 60)
    print("AGENTIC KG DISCOVERY FOR BATTERY ELECTROLYTES")
    print("=" * 60)
    print(f"\nData directory: {data_dir}")
    print(f"Output directory: {output_dir}")

    # Create pipeline
    pipeline = ElectrolyteKGPipeline(
        data_dir=data_dir,
        output_dir=output_dir,
    )

    # Run with sample data for quick demo
    results = pipeline.run(
        download_data=True,
        use_sample_libe=True,  # Use sample for faster execution
        train_epochs=30,
        max_hypotheses=15,
    )

    # Print final summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    kg_stats = results["stages"]["kg_stats"]
    print(f"\nKnowledge Graph:")
    print(f"  - {kg_stats['num_formulations']} electrolyte formulations")
    print(f"  - {kg_stats['num_measurements']} property measurements")
    print(f"  - {kg_stats['num_interphase_species']} interphase species")
    print(f"  - {kg_stats['num_relations']} relations")

    hyp_stats = results["stages"]["hypothesis"]
    print(f"\nHypothesis Generation:")
    print(f"  - {hyp_stats['batch']['num_proposed']} hypotheses proposed")
    print(f"  - {hyp_stats['batch']['num_novel']} novel edges")

    summary = results["stages"]["summary"]
    print(f"\nValidation:")
    print(f"  - {summary['by_status'].get('validated', 0)} validated")
    print(f"  - {summary['by_status'].get('rejected', 0)} rejected")

    print(f"\nOutputs saved to: {output_dir}")
    print("\nFiles:")
    print(f"  - knowledge_graph.json (full KG with provenance)")
    print(f"  - hypotheses.json (all generated hypotheses)")
    print(f"  - pipeline_results.json (execution metrics)")

    return results


if __name__ == "__main__":
    main()
