"""Main pipeline for KG discovery."""

from pathlib import Path
from datetime import datetime
import json

from .kg_store import KnowledgeGraph
from .ingestion import ConductivityDatasetIngestor, LIBEIngestor
from .ingestion.libe import create_sample_libe_data
from .hypothesis import HypothesisGenerator
from .evaluation import DiscoveryMetrics, TimeSliceEvaluator, AblationStudy
from .schema.entities import PropertyType


class ElectrolyteKGPipeline:
    """
    End-to-end pipeline for electrolyte KG discovery.

    Steps:
    1. Data ingestion (Conductivity dataset, LIBE)
    2. KG construction with provenance
    3. Hypothesis generation (link prediction + rule mining)
    4. Evaluation (time-slice, ablation)
    5. Validation and curation
    """

    def __init__(self, data_dir: Path, output_dir: Path):
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.kg = KnowledgeGraph(version="0.1.0")
        self.hypothesis_generator = HypothesisGenerator(self.kg)
        self.discovery_metrics = DiscoveryMetrics()

    def run(
        self,
        download_data: bool = True,
        use_sample_libe: bool = True,  # Use sample data instead of full LIBE
        train_epochs: int = 50,
        max_hypotheses: int = 20,
    ) -> dict:
        """
        Run the full discovery pipeline.

        Args:
            download_data: Whether to download datasets
            use_sample_libe: Use sample LIBE data (faster for testing)
            train_epochs: Number of epochs for embedding training
            max_hypotheses: Maximum hypotheses to generate

        Returns:
            Dictionary with pipeline results
        """
        results = {
            "start_time": datetime.utcnow().isoformat(),
            "stages": {},
        }

        print("=" * 60)
        print("ELECTROLYTE KG DISCOVERY PIPELINE")
        print("=" * 60)

        # Stage 1: Data Ingestion
        print("\n[Stage 1/5] Data Ingestion")
        print("-" * 40)
        results["stages"]["ingestion"] = self._run_ingestion(
            download_data, use_sample_libe
        )

        # Stage 2: KG Statistics
        print("\n[Stage 2/5] KG Construction")
        print("-" * 40)
        results["stages"]["kg_stats"] = self._report_kg_stats()

        # Stage 3: Hypothesis Generation
        print("\n[Stage 3/5] Hypothesis Generation")
        print("-" * 40)
        results["stages"]["hypothesis"] = self._run_hypothesis_generation(
            train_epochs, max_hypotheses
        )

        # Stage 4: Evaluation
        print("\n[Stage 4/5] Evaluation")
        print("-" * 40)
        results["stages"]["evaluation"] = self._run_evaluation()

        # Stage 5: Summary
        print("\n[Stage 5/5] Summary & Export")
        print("-" * 40)
        results["stages"]["summary"] = self._generate_summary()

        results["end_time"] = datetime.utcnow().isoformat()

        # Save results
        self._save_results(results)

        return results

    def _run_ingestion(self, download: bool, use_sample_libe: bool) -> dict:
        """Run data ingestion stage."""
        stats = {}

        # Conductivity dataset
        print("Ingesting conductivity dataset...")
        cond_ingestor = ConductivityDatasetIngestor(self.kg)

        cond_path = self.data_dir / "conductivity_dataframe.csv"
        if download and not cond_path.exists():
            try:
                cond_path = cond_ingestor.download(self.data_dir)
            except Exception as e:
                print(f"  Warning: Could not download conductivity data: {e}")
                print("  Creating sample data instead...")
                self._create_sample_conductivity_data(cond_path)

        if cond_path.exists():
            cond_stats = cond_ingestor.ingest(cond_path)
            stats["conductivity"] = cond_stats
            print(f"  Formulations: {cond_stats['formulations_created']}")
            print(f"  Measurements: {cond_stats['measurements_created']}")
        else:
            print("  Skipped: conductivity data not available")

        # LIBE dataset
        print("\nIngesting LIBE dataset...")
        libe_ingestor = LIBEIngestor(self.kg)

        libe_path = self.data_dir / "libe_sample.json"
        if use_sample_libe:
            if not libe_path.exists():
                create_sample_libe_data(libe_path, num_samples=200)
            libe_stats = libe_ingestor.ingest(libe_path)
        else:
            libe_path = self.data_dir / "libe_dataset.json"
            if download and not libe_path.exists():
                try:
                    libe_path = libe_ingestor.download(self.data_dir)
                except Exception as e:
                    print(f"  Warning: Could not download LIBE: {e}")
                    create_sample_libe_data(libe_path, num_samples=200)

            if libe_path.exists():
                libe_stats = libe_ingestor.ingest(libe_path, max_species=1000)
            else:
                libe_stats = {"species_created": 0}

        stats["libe"] = libe_stats
        print(f"  Species: {libe_stats['species_created']}")

        return stats

    def _create_sample_conductivity_data(self, path: Path) -> None:
        """Create sample conductivity data for testing."""
        import pandas as pd
        import numpy as np

        np.random.seed(42)
        n_samples = 100

        data = {
            "m_EC": np.random.uniform(0.5, 3.0, n_samples),
            "m_PC": np.random.uniform(0, 2.0, n_samples),
            "m_EMC": np.random.uniform(1.0, 4.0, n_samples),
            "m_LiPF6": np.random.uniform(0.5, 2.0, n_samples),
            "temperature": np.random.choice([15, 25, 35, 45], n_samples),
            "conductivity": np.random.uniform(0.005, 0.015, n_samples),
        }

        # Make conductivity correlate with composition
        data["conductivity"] += 0.002 * data["m_EC"]
        data["conductivity"] -= 0.001 * data["m_PC"]
        data["conductivity"] += 0.001 * data["m_EMC"]
        data["conductivity"] += 0.003 * data["m_LiPF6"]
        data["conductivity"] += 0.0002 * (data["temperature"] - 25)

        df = pd.DataFrame(data)
        df.to_csv(path, index=False)
        print(f"  Created sample conductivity data at {path}")

    def _report_kg_stats(self) -> dict:
        """Report KG statistics."""
        stats = self.kg.stats()

        print(f"  Molecules: {stats['num_molecules']}")
        print(f"    Solvents: {stats['num_solvents']}")
        print(f"    Salts: {stats['num_salts']}")
        print(f"    Additives: {stats['num_additives']}")
        print(f"  Formulations: {stats['num_formulations']}")
        print(f"  Measurements: {stats['num_measurements']}")
        print(f"  Interphase species: {stats['num_interphase_species']}")
        print(f"  Relations: {stats['num_relations']}")
        print(f"  Provenance completeness: {stats['provenance_completeness']:.1%}")

        return stats

    def _run_hypothesis_generation(
        self,
        train_epochs: int,
        max_hypotheses: int,
    ) -> dict:
        """Run hypothesis generation stage."""
        stats = {}

        # Train link predictor
        print("Training link prediction model...")
        train_stats = self.hypothesis_generator.train_link_predictor(
            model_name="TransE",
            embedding_dim=64,
            epochs=train_epochs,
        )
        stats["link_prediction_training"] = train_stats
        print(f"  Model: {train_stats.get('model', 'N/A')}")
        print(f"  Entities: {train_stats.get('num_entities', 0)}")
        print(f"  Relations: {train_stats.get('num_relations', 0)}")

        # Run rule mining
        print("\nRunning rule mining...")
        mining_stats = self.hypothesis_generator.run_rule_mining(
            property_type=PropertyType.IONIC_CONDUCTIVITY,
            min_support=2,
            min_confidence=0.4,
        )
        stats["rule_mining"] = mining_stats
        print(f"  Patterns found: {mining_stats['num_patterns']}")
        print(f"  Threshold rules: {mining_stats['num_threshold_rules']}")

        # Generate hypotheses
        print("\nGenerating hypotheses...")
        batch = self.hypothesis_generator.generate_hypotheses(
            use_link_prediction=True,
            use_rule_mining=True,
            max_candidates=max_hypotheses,
            min_confidence=0.1,  # Lower threshold to include property-effect hypotheses
        )
        stats["batch"] = {
            "num_proposed": batch.num_proposed,
            "num_novel": batch.num_novel,
        }
        print(f"  Proposed: {batch.num_proposed}")
        print(f"  Novel: {batch.num_novel}")

        # Show top hypotheses
        print("\nTop hypotheses:")
        for i, h in enumerate(batch.hypotheses[:5], 1):
            print(f"  {i}. [{h.confidence:.3f}] {h.subject_type}:{h.subject_id[:8]} "
                  f"--{h.relation.value}--> {h.object_type}:{h.object_id[:8]}")
            if h.explanation:
                print(f"     {h.explanation[:60]}...")

        return stats

    def _run_evaluation(self) -> dict:
        """Run evaluation stage."""
        stats = {}

        # Update discovery metrics
        hypotheses = list(self.kg._hypotheses.values())
        self.discovery_metrics.update_from_hypotheses(hypotheses)
        self.discovery_metrics.provenance_completeness = self.kg.get_provenance_completeness()

        stats["discovery"] = self.discovery_metrics.to_dict()

        # Run ablation studies if we have enough data
        if len(self.kg._formulations) >= 20:
            print("Running ablation studies...")
            ablation = AblationStudy(self.kg)
            X, y, _ = ablation.prepare_conductivity_data()

            if len(X) >= 20:
                ablation_results = ablation.run_all_ablations(
                    hypotheses=hypotheses,
                    X=X,
                    y=y,
                    top_k=5,
                    n_folds=3,
                )
                stats["ablation"] = ablation.summary()
                print(f"  Studies run: {stats['ablation']['num_studies']}")
                print(f"  Significant: {stats['ablation']['num_significant']}")
            else:
                print("  Skipped: not enough data for cross-validation")
                stats["ablation"] = {"skipped": True}
        else:
            print("  Skipped: not enough formulations")
            stats["ablation"] = {"skipped": True}

        return stats

    def _generate_summary(self) -> dict:
        """Generate final summary."""
        summary = self.hypothesis_generator.summary()

        print(f"Total hypotheses: {summary['total_hypotheses']}")
        print(f"  Validated: {summary['by_status'].get('validated', 0)}")
        print(f"  Rejected: {summary['by_status'].get('rejected', 0)}")
        print(f"  Pending: {summary['by_status'].get('proposed', 0)}")
        print(f"Average confidence: {summary['avg_confidence']:.3f}")

        return summary

    def _save_results(self, results: dict) -> None:
        """Save all results to disk."""
        # Save KG
        kg_path = self.output_dir / "knowledge_graph.json"
        self.kg.save(kg_path)
        print(f"\nKG saved to: {kg_path}")

        # Save hypotheses
        hyp_path = self.output_dir / "hypotheses.json"
        self.hypothesis_generator.save_hypotheses(hyp_path)
        print(f"Hypotheses saved to: {hyp_path}")

        # Save pipeline results
        results_path = self.output_dir / "pipeline_results.json"
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Results saved to: {results_path}")


def main():
    """Run the pipeline."""
    import argparse

    parser = argparse.ArgumentParser(description="Electrolyte KG Discovery Pipeline")
    parser.add_argument("--data-dir", type=str, default="data/raw",
                        help="Directory for raw data")
    parser.add_argument("--output-dir", type=str, default="data/output",
                        help="Directory for outputs")
    parser.add_argument("--no-download", action="store_true",
                        help="Skip downloading data")
    parser.add_argument("--full-libe", action="store_true",
                        help="Use full LIBE dataset (slow)")
    parser.add_argument("--epochs", type=int, default=50,
                        help="Training epochs")
    parser.add_argument("--max-hypotheses", type=int, default=20,
                        help="Max hypotheses to generate")

    args = parser.parse_args()

    pipeline = ElectrolyteKGPipeline(
        data_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
    )

    results = pipeline.run(
        download_data=not args.no_download,
        use_sample_libe=not args.full_libe,
        train_epochs=args.epochs,
        max_hypotheses=args.max_hypotheses,
    )

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
