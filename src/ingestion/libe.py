"""Ingestor for the LIBE (Lithium-Ion Battery Electrolyte) dataset (Scientific Data 2021)."""

from pathlib import Path
from datetime import datetime
from typing import Optional
import requests
import json

import pandas as pd

from .base import BaseIngestor
from ..kg_store.graph import KnowledgeGraph
from ..schema.entities import InterphaseSpecies, Molecule, EvidenceSource


class LIBEIngestor(BaseIngestor):
    """
    Ingestor for the LIBE Dataset.

    Dataset: Lithium-Ion Battery Electrolyte (LIBE) dataset
    DOI: 10.6084/m9.figshare.14226464
    Paper: https://doi.org/10.1038/s41597-021-00986-9

    Contains ~17,000 molecules relevant to electrolyte and interphase chemistry
    with DFT-computed properties at the ωB97X-V/def2-TZVPPD/SMD level.
    """

    FIGSHARE_DOI = "10.6084/m9.figshare.14226464"
    PAPER_DOI = "10.1038/s41597-021-00986-9"
    # Direct download URL for the dataset (from Figshare API)
    FIGSHARE_URL = "https://ndownloader.figshare.com/files/28071129"

    def __init__(self, kg: KnowledgeGraph):
        super().__init__(kg, "LIBE Dataset")

    def download(self, output_dir: Path) -> Path:
        """Download the LIBE dataset from Figshare."""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "libe_dataset.json"

        if output_path.exists():
            print(f"Dataset already exists at {output_path}")
            return output_path

        print(f"Downloading LIBE dataset from Figshare...")
        print("Note: This is a large dataset (~500MB), download may take a while.")

        response = requests.get(self.FIGSHARE_URL, timeout=300, stream=True)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"Downloaded to {output_path}")
        return output_path

    def ingest(self, data_path: Path, max_species: Optional[int] = None) -> dict:
        """
        Ingest the LIBE dataset into the KG.

        Args:
            data_path: Path to the downloaded LIBE JSON file
            max_species: Optional limit on number of species to ingest (for testing)

        Returns:
            Dictionary with ingestion statistics
        """
        # Set up provenance
        self._create_agent()
        self._create_source(
            source_type="dataset",
            doi=self.PAPER_DOI,
            url=f"https://doi.org/{self.FIGSHARE_DOI}",
            authors=[
                "Evan Walter Clark Spotte-Smith", "Samuel M Blau",
                "Xiaowei Xie", "Hetal D Patel", "Mingjian Wen",
                "Brandon Wood", "Shyam Dwaraknath", "Kristin Aslaug Persson"
            ],
            publication_date=datetime(2021, 8, 5),
            license="CC BY 4.0",
        )

        stats = {
            "species_created": 0,
            "molecules_created": 0,
            "errors": [],
        }

        # Load data
        print(f"Loading LIBE data from {data_path}...")

        # The LIBE dataset can be in different formats
        if data_path.suffix == ".json":
            data = self._load_json(data_path)
        elif data_path.suffix == ".csv":
            data = self._load_csv(data_path)
        else:
            # Try JSON first
            try:
                data = self._load_json(data_path)
            except Exception:
                data = self._load_csv(data_path)

        # Process species
        species_list = data if isinstance(data, list) else data.get("molecules", data.get("species", []))

        if max_species:
            species_list = species_list[:max_species]

        print(f"Processing {len(species_list)} species...")

        for i, species_data in enumerate(species_list):
            try:
                species = self._create_species(species_data, i)
                if species:
                    stats["species_created"] += 1
            except Exception as e:
                stats["errors"].append(f"Species {i}: {str(e)}")

            if (i + 1) % 1000 == 0:
                print(f"  Processed {i + 1}/{len(species_list)} species...")

        print(f"Ingestion complete: {stats['species_created']} species created")
        return stats

    def _load_json(self, path: Path) -> list:
        """Load data from JSON file."""
        with open(path) as f:
            return json.load(f)

    def _load_csv(self, path: Path) -> list:
        """Load data from CSV file and convert to list of dicts."""
        df = pd.read_csv(path)
        return df.to_dict("records")

    def _create_species(self, data: dict, idx: int) -> Optional[InterphaseSpecies]:
        """Create an interphase species from LIBE data."""
        # Handle actual LIBE format (pymatgen-based)
        molecule_id = data.get("molecule_id", f"libe-{idx}")

        # Extract key fields - handle both simple and pymatgen formats
        smiles = data.get("smiles", data.get("SMILES"))
        inchi = data.get("inchi", data.get("InChI"))

        # Formula can be in different fields
        formula = data.get("formula_alphabetical",
                          data.get("formula",
                          data.get("molecular_formula")))

        # Charge is at top level in LIBE
        charge = data.get("charge", 0)

        # Spin multiplicity may be in nested molecule object
        molecule_obj = data.get("molecule", {})
        spin = data.get("spin_multiplicity",
                       molecule_obj.get("spin_multiplicity", 1))

        # Extract computed properties - LIBE uses different field names
        energy = data.get("final_energy",
                         data.get("energy",
                         data.get("electronic_energy")))
        enthalpy = data.get("enthalpy", data.get("H"))
        entropy = data.get("entropy", data.get("S"))
        free_energy = data.get("free_energy", data.get("G"))

        # Chemical system info
        chem_system = data.get("chemical_system", "")

        # Generate name from molecule_id or formula
        name = data.get("name", molecule_id or formula or f"species_{idx}")

        species = InterphaseSpecies(
            name=name,
            smiles=smiles,
            inchi=inchi,
            formula=formula,
            charge=int(charge) if charge else 0,
            spin_multiplicity=int(spin) if spin else 1,
            energy=float(energy) if energy else None,
            enthalpy=float(enthalpy) if enthalpy else None,
            entropy=float(entropy) if entropy else None,
            free_energy=float(free_energy) if free_energy else None,
            source_dataset="LIBE",
        )

        self.kg.add_interphase_species(species)

        # Add provenance
        self._create_provenance(
            entity_id=species.id,
            entity_type="InterphaseSpecies",
            row_id=str(idx),
        )

        return species


def create_sample_libe_data(output_path: Path, num_samples: int = 100) -> None:
    """
    Create sample LIBE-like data for testing without downloading the full dataset.

    This generates synthetic data matching the LIBE format.
    """
    import random

    # Common electrolyte-related species
    species_templates = [
        {"formula": "C3H4O3", "smiles": "O=C1OCCO1", "name": "Ethylene carbonate"},
        {"formula": "C4H6O3", "smiles": "CC1COC(=O)O1", "name": "Propylene carbonate"},
        {"formula": "C4H8O3", "smiles": "CCOC(=O)OC", "name": "Ethyl methyl carbonate"},
        {"formula": "Li", "smiles": "[Li]", "name": "Lithium atom"},
        {"formula": "LiF", "smiles": "[Li]F", "name": "Lithium fluoride"},
        {"formula": "LiO", "smiles": "[Li]O", "name": "Lithium oxide"},
        {"formula": "PF6", "smiles": "F[P-](F)(F)(F)(F)F", "name": "Hexafluorophosphate"},
        {"formula": "CO3", "smiles": "[O-]C([O-])=O", "name": "Carbonate"},
        {"formula": "C2H4O", "smiles": "CC=O", "name": "Acetaldehyde"},
        {"formula": "CO2", "smiles": "O=C=O", "name": "Carbon dioxide"},
    ]

    data = []
    for i in range(num_samples):
        template = random.choice(species_templates)
        species = {
            "name": f"{template['name']}_variant_{i}",
            "formula": template["formula"],
            "smiles": template["smiles"],
            "charge": random.choice([0, 0, 0, -1, 1]),
            "spin_multiplicity": random.choice([1, 1, 1, 2]),
            "energy": random.uniform(-500, -100),
            "enthalpy": random.uniform(-400, 0),
            "entropy": random.uniform(100, 500),
            "free_energy": random.uniform(-300, 0),
        }
        data.append(species)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Created sample LIBE data with {num_samples} species at {output_path}")
