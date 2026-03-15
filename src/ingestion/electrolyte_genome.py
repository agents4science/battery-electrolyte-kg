"""Ingestor for Materials Project Electrolyte Genome dataset."""

from pathlib import Path
from datetime import datetime
from typing import Optional
import json

from .base import BaseIngestor
from ..kg_store.graph import KnowledgeGraph
from ..schema.entities import (
    Molecule, PropertyMeasurement, MeasurementMethod, EvidenceSource,
    PropertyType,
)
from ..schema.relations import RelationType
from ..integration.materials_project import (
    MaterialsProjectClient,
    ElectrolyteGenomeMolecule,
)


class ElectrolyteGenomeIngestor(BaseIngestor):
    """
    Ingestor for the Materials Project Electrolyte Genome dataset.

    Dataset: JCESR Electrolyte Genome
    Description: ~22,000 molecules with computed electrochemical properties
    Properties: Ionization energy, electron affinity, redox potentials
    Paper: https://doi.org/10.1016/j.commatsci.2015.02.050
    """

    PAPER_DOI = "10.1016/j.commatsci.2015.02.050"
    SOURCE_URL = "https://materialsproject.org/molecules"

    def __init__(
        self,
        kg: KnowledgeGraph,
        api_key: Optional[str] = None,
    ):
        super().__init__(kg, "Materials Project Electrolyte Genome")
        self.client = MaterialsProjectClient(api_key=api_key)
        self._method: Optional[MeasurementMethod] = None
        self._molecules_added: set[str] = set()  # Track by SMILES to avoid duplicates

    def download(self, output_dir: Path, max_molecules: int = 5000) -> Path:
        """
        Download molecules from the Electrolyte Genome API.

        Note: This fetches from the API rather than downloading a file.
        Results are cached to a JSON file for subsequent runs.

        Args:
            output_dir: Directory to save cached data
            max_molecules: Maximum molecules to fetch

        Returns:
            Path to cached JSON file
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "electrolyte_genome.json"

        if output_path.exists():
            print(f"Cached data exists at {output_path}")
            return output_path

        if not self.client.check_api_key():
            raise ValueError(
                "Materials Project API key required.\n"
                "Set MP_API_KEY environment variable or pass api_key to constructor.\n"
                "Get your key at: https://materialsproject.org/api"
            )

        print("Fetching Electrolyte Genome molecules from Materials Project API...")
        print("This may take a few minutes...")

        # Fetch molecules
        molecules = self.client.get_electrolyte_molecules(max_molecules=max_molecules)

        print(f"Fetched {len(molecules)} molecules")

        # Save to cache
        data = [self._molecule_to_dict(m) for m in molecules]
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Cached to {output_path}")
        return output_path

    def ingest(self, data_path: Path, max_molecules: int = 5000) -> dict:
        """
        Ingest Electrolyte Genome data into the KG.

        Args:
            data_path: Path to cached JSON file
            max_molecules: Max molecules if fetching from API
        """
        # Set up provenance
        self._create_agent()
        self._create_source(
            source_type="dataset",
            doi=self.PAPER_DOI,
            url=self.SOURCE_URL,
            authors=[
                "Xiaohui Qu", "Anubhav Jain", "Nav Nidhi Rajput",
                "Lei Cheng", "Yong Zhang", "Shyue Ping Ong",
                "Miriam Bbeher", "Kristin A. Persson",
            ],
            publication_date=datetime(2015, 4, 1),
            license="CC BY 4.0",
        )

        # Create DFT method
        self._method = MeasurementMethod(
            name="DFT-B3LYP",
            description="Density Functional Theory calculation",
            parameters={
                "functional": "B3LYP",
                "basis_set": "6-31+G(d)",
                "solvent_model": "PCM",
                "software": "Gaussian/Q-Chem",
            },
        )
        self.kg.add_method(self._method)

        # Load data from cache or API
        if data_path.exists():
            print(f"Loading from cache: {data_path}")
            with open(data_path) as f:
                data = json.load(f)
            molecules = [self._dict_to_molecule(d) for d in data]
        else:
            # Fetch from API
            if not self.client.check_api_key():
                raise ValueError(
                    "No cached data and no API key configured.\n"
                    "Either provide cached data or set MP_API_KEY environment variable."
                )
            print("Fetching from Materials Project API...")
            molecules = self.client.get_electrolyte_molecules(max_molecules=max_molecules)

        print(f"Processing {len(molecules)} molecules...")

        # Process molecules
        stats = self._process_molecules(molecules)

        return stats

    def _process_molecules(
        self,
        molecules: list[ElectrolyteGenomeMolecule],
    ) -> dict:
        """Process fetched molecules into the KG."""
        stats = {
            "molecules_created": 0,
            "measurements_created": 0,
            "duplicates_skipped": 0,
            "errors": [],
        }

        for mol in molecules:
            try:
                # Skip duplicates by SMILES
                if mol.smiles in self._molecules_added:
                    stats["duplicates_skipped"] += 1
                    continue

                # Create molecule entity
                molecule = self._create_molecule(mol)
                if molecule:
                    stats["molecules_created"] += 1
                    self._molecules_added.add(mol.smiles)

                    # Create property measurements
                    measurements = self._create_measurements(mol, molecule)
                    stats["measurements_created"] += len(measurements)

            except Exception as e:
                stats["errors"].append(f"{mol.task_id}: {str(e)}")

        return stats

    def _create_molecule(
        self,
        mol: ElectrolyteGenomeMolecule,
    ) -> Optional[Molecule]:
        """Create a Molecule entity from Electrolyte Genome data."""
        if not mol.smiles:
            return None

        molecule = Molecule(
            name=mol.formula or mol.smiles[:50],
            smiles=mol.smiles,
            molecular_weight=mol.molecular_weight,
            synonyms=[mol.task_id] + mol.functional_groups,
        )

        self.kg.add_molecule(molecule)

        # Add provenance
        self._create_provenance(
            entity_id=molecule.id,
            entity_type="Molecule",
            row_id=mol.task_id,
            confidence=1.0,
        )

        return molecule

    def _create_measurements(
        self,
        mol: ElectrolyteGenomeMolecule,
        molecule: Molecule,
    ) -> list[PropertyMeasurement]:
        """Create PropertyMeasurement entities for computed properties."""
        measurements = []

        # Map of property attributes to PropertyType
        property_map = [
            ("ionization_energy", PropertyType.IONIZATION_ENERGY, "eV"),
            ("electron_affinity", PropertyType.ELECTRON_AFFINITY, "eV"),
            ("oxidation_potential_li", PropertyType.OXIDATION_POTENTIAL_LI, "V"),
            ("reduction_potential_li", PropertyType.REDUCTION_POTENTIAL_LI, "V"),
            ("oxidation_potential_mg", PropertyType.OXIDATION_POTENTIAL_MG, "V"),
            ("reduction_potential_mg", PropertyType.REDUCTION_POTENTIAL_MG, "V"),
            ("oxidation_potential_h", PropertyType.OXIDATION_POTENTIAL_H, "V"),
            ("reduction_potential_h", PropertyType.REDUCTION_POTENTIAL_H, "V"),
        ]

        for attr, prop_type, unit in property_map:
            value = getattr(mol, attr, None)
            if value is not None:
                measurement = PropertyMeasurement(
                    property_type=prop_type,
                    value=float(value),
                    unit=unit,
                    method_id=self._method.id if self._method else None,
                )
                self.kg.add_measurement(measurement)

                # Link molecule to measurement
                self.kg.add_relation(
                    molecule.id,
                    RelationType.HAS_MEASUREMENT,
                    measurement.id,
                )

                # Link measurement to property type
                self.kg.add_relation(
                    measurement.id,
                    RelationType.MEASURES_PROPERTY,
                    prop_type.entity_id,
                )

                # Add provenance
                self._create_provenance(
                    entity_id=measurement.id,
                    entity_type="PropertyMeasurement",
                    row_id=mol.task_id,
                    confidence=1.0,  # DFT calculations are deterministic
                )

                measurements.append(measurement)

        return measurements

    def _molecule_to_dict(self, mol: ElectrolyteGenomeMolecule) -> dict:
        """Convert molecule to dict for JSON serialization."""
        return {
            "task_id": mol.task_id,
            "smiles": mol.smiles,
            "formula": mol.formula,
            "charge": mol.charge,
            "molecular_weight": mol.molecular_weight,
            "point_group": mol.point_group,
            "ionization_energy": mol.ionization_energy,
            "electron_affinity": mol.electron_affinity,
            "oxidation_potential_li": mol.oxidation_potential_li,
            "reduction_potential_li": mol.reduction_potential_li,
            "oxidation_potential_mg": mol.oxidation_potential_mg,
            "reduction_potential_mg": mol.reduction_potential_mg,
            "oxidation_potential_h": mol.oxidation_potential_h,
            "reduction_potential_h": mol.reduction_potential_h,
            "functional_groups": mol.functional_groups,
            "base_molecule": mol.base_molecule,
        }

    def _dict_to_molecule(self, data: dict) -> ElectrolyteGenomeMolecule:
        """Convert dict to ElectrolyteGenomeMolecule."""
        return ElectrolyteGenomeMolecule(
            task_id=data.get("task_id", ""),
            smiles=data.get("smiles", ""),
            formula=data.get("formula"),
            charge=data.get("charge", 0),
            molecular_weight=data.get("molecular_weight"),
            point_group=data.get("point_group"),
            ionization_energy=data.get("ionization_energy"),
            electron_affinity=data.get("electron_affinity"),
            oxidation_potential_li=data.get("oxidation_potential_li"),
            reduction_potential_li=data.get("reduction_potential_li"),
            oxidation_potential_mg=data.get("oxidation_potential_mg"),
            reduction_potential_mg=data.get("reduction_potential_mg"),
            oxidation_potential_h=data.get("oxidation_potential_h"),
            reduction_potential_h=data.get("reduction_potential_h"),
            functional_groups=data.get("functional_groups", []),
            base_molecule=data.get("base_molecule"),
        )
