"""Ingestor for the Conductivity/EIS electrolyte dataset (Scientific Data 2023)."""

from pathlib import Path
from datetime import datetime
from typing import Optional
import requests
import zipfile
import io

import pandas as pd

from .base import BaseIngestor
from ..kg_store.graph import KnowledgeGraph
from ..schema.entities import (
    Solvent, Salt, ElectrolyteFormulation, FormulationComponent,
    PropertyMeasurement, MeasurementMethod, EvidenceSource,
    ComponentType, AmountUnit, PropertyType,
)
from ..schema.relations import RelationType


# Known molecule identities for the dataset
MOLECULE_DATA = {
    "EC": {
        "name": "Ethylene carbonate",
        "smiles": "O=C1OCCO1",
        "cas_number": "96-49-1",
        "pubchem_cid": 7303,
        "molecular_weight": 88.06,
    },
    "PC": {
        "name": "Propylene carbonate",
        "smiles": "CC1COC(=O)O1",
        "cas_number": "108-32-7",
        "pubchem_cid": 7924,
        "molecular_weight": 102.09,
    },
    "EMC": {
        "name": "Ethyl methyl carbonate",
        "smiles": "CCOC(=O)OC",
        "cas_number": "623-53-0",
        "pubchem_cid": 522046,
        "molecular_weight": 104.11,
    },
    "DMC": {
        "name": "Dimethyl carbonate",
        "smiles": "COC(=O)OC",
        "cas_number": "616-38-6",
        "pubchem_cid": 12021,
        "molecular_weight": 90.08,
    },
    "LiPF6": {
        "name": "Lithium hexafluorophosphate",
        "smiles": "[Li+].F[P-](F)(F)(F)(F)F",
        "cas_number": "21324-40-3",
        "pubchem_cid": 23688284,
        "molecular_weight": 151.91,
        "cation": "Li+",
        "anion": "PF6-",
    },
}


class ConductivityDatasetIngestor(BaseIngestor):
    """
    Ingestor for the HI Münster Conductivity Dataset.

    Dataset: Conductivity experiments for electrolyte formulations and their automated analysis
    DOI: 10.5281/zenodo.7244939
    Paper: https://doi.org/10.1038/s41597-023-01936-3
    """

    ZENODO_DOI = "10.5281/zenodo.7244939"
    ZENODO_URL = "https://zenodo.org/api/records/7244939/files/Conductivtiy_experiment.csv/content"
    PAPER_DOI = "10.1038/s41597-023-01936-3"

    def __init__(self, kg: KnowledgeGraph):
        super().__init__(kg, "HI Münster Conductivity Dataset")
        self._solvents: dict[str, Solvent] = {}
        self._salt: Optional[Salt] = None
        self._method: Optional[MeasurementMethod] = None

    def download(self, output_dir: Path) -> Path:
        """Download the dataset from Zenodo."""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "conductivity_dataframe.csv"

        if output_path.exists():
            print(f"Dataset already exists at {output_path}")
            return output_path

        print(f"Downloading conductivity dataset from Zenodo...")
        response = requests.get(self.ZENODO_URL, timeout=60)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(response.content)

        print(f"Downloaded to {output_path}")
        return output_path

    def ingest(self, data_path: Path) -> dict:
        """Ingest the conductivity dataset into the KG."""
        # Set up provenance
        self._create_agent()
        self._create_source(
            source_type="dataset",
            doi=self.PAPER_DOI,
            url=f"https://doi.org/{self.ZENODO_DOI}",
            authors=[
                "Fuzhan Rahmanian", "Monika Vogler", "Christian Wölke",
                "Peng Yan", "Stefan Fuchs", "Martin Winter",
                "Isidora Cekic-Laskovic", "Helge Sören Stein"
            ],
            publication_date=datetime(2023, 1, 19),
            license="CC BY 4.0",
        )

        # Create known molecules
        self._create_molecules()

        # Create EIS measurement method
        self._method = MeasurementMethod(
            name="EIS",
            description="Electrochemical Impedance Spectroscopy",
            equipment="BioLogic VMP-300 potentiostat",
            parameters={
                "frequency_range": "1 MHz - 100 mHz",
                "amplitude": "10 mV",
            },
        )
        self.kg.add_method(self._method)

        # Load and process data
        # Handle both comma and semicolon separated files
        try:
            df = pd.read_csv(data_path, sep=';')
            # Check if this is the real Zenodo dataset
            if 'LiPF_6' in df.columns:
                # Skip header rows (symbol/unit rows)
                df = df.iloc[2:].reset_index(drop=True)
                # Rename columns to match our expected format
                df = df.rename(columns={
                    'LiPF_6': 'm_LiPF6',
                    'EC': 'm_EC',
                    'PC': 'm_PC',
                    'EMC': 'm_EMC',
                    'EIS_conductivity': 'conductivity',
                })
                # Convert numeric columns
                for col in ['m_EC', 'm_PC', 'm_EMC', 'm_LiPF6', 'temperature', 'conductivity']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
        except Exception:
            df = pd.read_csv(data_path)

        stats = self._process_dataframe(df)

        return stats

    def _create_molecules(self) -> None:
        """Create solvent and salt molecules."""
        # Create solvents
        for abbrev in ["EC", "PC", "EMC"]:
            data = MOLECULE_DATA[abbrev]
            solvent = Solvent(
                name=data["name"],
                smiles=data["smiles"],
                cas_number=data["cas_number"],
                pubchem_cid=data["pubchem_cid"],
                molecular_weight=data["molecular_weight"],
                synonyms=[abbrev],
            )
            self.kg.add_solvent(solvent)
            self._solvents[abbrev] = solvent

        # Create salt
        data = MOLECULE_DATA["LiPF6"]
        self._salt = Salt(
            name=data["name"],
            smiles=data["smiles"],
            cas_number=data["cas_number"],
            pubchem_cid=data["pubchem_cid"],
            molecular_weight=data["molecular_weight"],
            cation=data["cation"],
            anion=data["anion"],
            synonyms=["LiPF6", "LiPF₆"],
        )
        self.kg.add_salt(self._salt)

    def _process_dataframe(self, df: pd.DataFrame) -> dict:
        """Process the conductivity dataframe."""
        stats = {
            "formulations_created": 0,
            "measurements_created": 0,
            "rows_processed": 0,
            "errors": [],
        }

        # Group by unique formulations
        # The dataset has columns like: m_EC, m_PC, m_EMC, m_LiPF6 (masses in g)
        # and temperature, conductivity columns

        # Identify mass columns
        mass_cols = [c for c in df.columns if c.startswith("m_")]
        if not mass_cols:
            # Try alternative column names
            mass_cols = ["EC", "PC", "EMC", "LiPF6"]

        formulation_cache = {}

        for idx, row in df.iterrows():
            try:
                # Create formulation key from masses
                form_key = self._get_formulation_key(row, mass_cols)

                if form_key not in formulation_cache:
                    # Create new formulation
                    formulation = self._create_formulation(row, mass_cols, idx)
                    formulation_cache[form_key] = formulation
                    stats["formulations_created"] += 1
                else:
                    formulation = formulation_cache[form_key]

                # Add measurement
                measurement = self._create_measurement(row, formulation, idx)
                if measurement:
                    stats["measurements_created"] += 1

                stats["rows_processed"] += 1

            except Exception as e:
                stats["errors"].append(f"Row {idx}: {str(e)}")

        return stats

    def _get_formulation_key(self, row: pd.Series, mass_cols: list) -> str:
        """Generate a unique key for a formulation based on masses."""
        masses = []
        for col in sorted(mass_cols):
            val = row.get(col, row.get(f"m_{col}", 0))
            masses.append(f"{col}:{val:.4f}")
        return "|".join(masses)

    def _create_formulation(
        self,
        row: pd.Series,
        mass_cols: list,
        row_idx: int,
    ) -> ElectrolyteFormulation:
        """Create a formulation from a dataframe row."""
        components = []

        # Add solvents
        for abbrev, solvent in self._solvents.items():
            mass_col = f"m_{abbrev}" if f"m_{abbrev}" in row.index else abbrev
            if mass_col in row.index:
                mass = row[mass_col]
                if pd.notna(mass) and mass > 0:
                    comp = FormulationComponent(
                        molecule_id=solvent.id,
                        component_type=ComponentType.SOLVENT,
                        amount=float(mass),
                        unit=AmountUnit.GRAMS,
                    )
                    components.append(comp)

        # Add salt
        salt_col = "m_LiPF6" if "m_LiPF6" in row.index else "LiPF6"
        if salt_col in row.index:
            salt_mass = row[salt_col]
            if pd.notna(salt_mass) and salt_mass > 0:
                comp = FormulationComponent(
                    molecule_id=self._salt.id,
                    component_type=ComponentType.SALT,
                    amount=float(salt_mass),
                    unit=AmountUnit.GRAMS,
                )
                components.append(comp)

        # Create formulation
        formulation = ElectrolyteFormulation(
            name=f"EC-PC-EMC-LiPF6-{row_idx}",
            components=components,
            source_id=self._source.id,
            batch_id=str(row.get("batch", row_idx)),
        )

        self.kg.add_formulation(formulation)

        # Add provenance
        self._create_provenance(
            entity_id=formulation.id,
            entity_type="ElectrolyteFormulation",
            row_id=str(row_idx),
        )

        return formulation

    def _create_measurement(
        self,
        row: pd.Series,
        formulation: ElectrolyteFormulation,
        row_idx: int,
    ) -> Optional[PropertyMeasurement]:
        """Create a conductivity measurement from a dataframe row."""
        # Look for conductivity column
        cond_col = None
        for c in ["conductivity", "Conductivity", "sigma", "ionic_conductivity"]:
            if c in row.index:
                cond_col = c
                break

        if cond_col is None or pd.isna(row[cond_col]):
            return None

        # Get temperature
        temp_col = None
        for c in ["temperature", "Temperature", "T", "temp"]:
            if c in row.index:
                temp_col = c
                break

        temp = row[temp_col] if temp_col and pd.notna(row.get(temp_col)) else 25.0

        # Create measurement
        measurement = PropertyMeasurement(
            property_type=PropertyType.IONIC_CONDUCTIVITY,
            value=float(row[cond_col]),
            unit="S/cm",
            temperature=float(temp),
            temperature_unit="C",
            method_id=self._method.id if self._method else None,
        )

        self.kg.add_measurement(measurement)

        # Link to formulation
        formulation.measurements.append(measurement.id)
        self.kg.add_relation(
            formulation.id,
            RelationType.HAS_MEASUREMENT,
            measurement.id,
        )

        # Add provenance
        self._create_provenance(
            entity_id=measurement.id,
            entity_type="PropertyMeasurement",
            row_id=str(row_idx),
        )

        return measurement
