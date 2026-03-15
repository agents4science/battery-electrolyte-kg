"""Ingestor for the CALiSol-23 dataset (Nature Scientific Data 2024)."""

from pathlib import Path
from datetime import datetime
from typing import Optional
import csv

import pandas as pd

from .base import BaseIngestor
from ..kg_store.graph import KnowledgeGraph
from ..schema.entities import (
    Molecule, Solvent, Salt, ElectrolyteFormulation, FormulationComponent,
    PropertyMeasurement, MeasurementMethod, EvidenceSource,
    ComponentType, AmountUnit, PropertyType,
)
from ..schema.relations import RelationType


# SMILES data parsed from calisolsmile.csv
CALISOL_SMILES = {
    # Salts
    "LiPF6": "[Li+].F[P-](F)(F)(F)(F)F",
    "LiBF4": "[Li+].F[B-](F)(F)F",
    "LiFSI": "[Li+].[N-](S(=O)(=O)F)S(=O)(=O)F",
    "LiTDI": "[Li+].C(#N)C1=C(N=C([N-]1)C(F)(F)F)C#N",
    "LiPDI": "C(#N)C1=C(N=C(N1)C(C(F)(F)F)(F)F)C#N",
    "LiTFSI": "[Li]N(S(=O)(=O)C(F)(F)F)S(=O)(=O)C(F)(F)F",
    "LiClO4": "[Li+].[O-]Cl(=O)(=O)=O",
    "LiAsF6": "[Li+].F[As-](F)(F)(F)(F)F",
    "LiBOB": "[Li+].O=C1O[B-]2(OC1=O)OC(=O)C(=O)O2",
    "LiCF3SO3": "[Li+].[O-]S(=O)(=O)C(F)(F)F",
    "LiBPFPB": "[Li+].FC(F)(F)C(O[B-]1(OC2(C(F)(F)F)C(F)(F)F)OC2(C(F)(F)F)C(F)(F)F)(C(O1)(C(F)(F)F)C(F)(F)F)C(F)(F)F",
    "LiBMB": "[Li+].O=C(CC(=O)O1)O[B-]1(OC(C1)=O)OC1=O",
    "LiN(CF3SO2)2": "[Li+].C(F)(F)(F)S(=O)(=O)[N-]S(=O)(=O)C(F)(F)F",
    # Solvents
    "EC": "C1COC(=O)O1",
    "PC": "CC1COC(=O)O1",
    "DMC": "COC(=O)OC",
    "EMC": "CCOC(=O)OC",
    "DEC": "CCOC(=O)OCC",
    "DME": "COCCOC",
    "DMSO": "CS(=O)C",
    "AN": "CC#N",
    "MOEMC": "COCCOC(=O)OC",
    "TFP": "C(C(F)(F)F)OP(=O)(OCC(F)(F)F)OCC(F)(F)F",
    "EA": "CCOC(=O)C",
    "MA": "CC(=O)OC",
    "FEC": "C1C(OC(=O)O1)F",
    "DOL": "C1COCO1",
    "2-MeTHF": "CC1CCCO1",
    "DMM": "COCC(C)OC(C)COC",
    "Freon 11": "C(F)(Cl)(Cl)Cl",
    "Methylene chloride": "C(Cl)Cl",
    "THF": "C1CCOC1",
    "Toluene": "CC1=CC=CC=C1",
    "Sulfolane": "O=S1(=O)CCCC1",
    "2-Glyme": "COCCOCCOC",
    "3-Glyme": "COCCOCCOCCOC",
    "4-Glyme": "COCCOCCOCCOCCOC",
    "3-Me-2-Oxazolidinone": "CN1CCOC1=O",
    "3-MeSulfolane": "CC1CCS(=O)(=O)C1",
    "Ethyldiglyme": "CCOCCOCCO",
    "DMF": "CN(C)C=O",
    "Ethylbenzene": "CCC1=CC=CC=C1",
    "Ethylmonoglyme": "COCCO",
    "Benzene": "C1=CC=CC=C1",
    "g-Butyrolactone": "C1CC(=O)OC1",
    "Cumene": "CC(C)C1=CC=CC=C1",
    "Propylsulfone": "CCCS(=O)(=O)CCC",
    "Pseudocumeme": "CC1=CC(=C(C=C1)C)C",
    "TEOS": "CCO[Si](OCC)(OCC)OCC",
    "m-Xylene": "CC1=CC(=CC=C1)C",
    "o-Xylene": "CC1=CC=CC=C1C",
}

# Full names for common compounds
COMPOUND_NAMES = {
    "EC": "Ethylene carbonate",
    "PC": "Propylene carbonate",
    "DMC": "Dimethyl carbonate",
    "EMC": "Ethyl methyl carbonate",
    "DEC": "Diethyl carbonate",
    "DME": "Dimethoxyethane",
    "DMSO": "Dimethyl sulfoxide",
    "AN": "Acetonitrile",
    "FEC": "Fluoroethylene carbonate",
    "DOL": "Dioxolane",
    "THF": "Tetrahydrofuran",
    "DMF": "Dimethylformamide",
    "LiPF6": "Lithium hexafluorophosphate",
    "LiBF4": "Lithium tetrafluoroborate",
    "LiFSI": "Lithium bis(fluorosulfonyl)imide",
    "LiTFSI": "Lithium bis(trifluoromethanesulfonyl)imide",
    "LiClO4": "Lithium perchlorate",
    "LiBOB": "Lithium bis(oxalato)borate",
}

# Solvent columns in the dataset
SOLVENT_COLUMNS = [
    "EC", "PC", "DMC", "EMC", "DEC", "DME", "DMSO", "AN", "MOEMC", "TFP",
    "EA", "MA", "FEC", "DOL", "2-MeTHF", "DMM", "Freon 11", "Methylene chloride",
    "THF", "Toluene", "Sulfolane", "2-Glyme", "3-Glyme", "4-Glyme",
    "3-Me-2-Oxazolidinone", "3-MeSulfolane", "Ethyldiglyme", "DMF",
    "Ethylbenzene", "Ethylmonoglyme", "Benzene", "g-Butyrolactone",
    "Cumene", "Propylsulfone", "Pseudocumeme", "TEOS", "m-Xylene", "o-Xylene",
]


class CALiSol23Ingestor(BaseIngestor):
    """
    Ingestor for the CALiSol-23 Dataset.

    Dataset: Conductivity Atlas for Lithium salts and Solvents
    DOI: 10.1038/s41597-024-03575-8
    Paper: Nature Scientific Data (2024)
    Data: 13,825 conductivity measurements across 38 solvents and 14 lithium salts
    """

    PAPER_DOI = "10.1038/s41597-024-03575-8"
    GITHUB_URL = "https://github.com/Pele0599/CALiSol-23"

    def __init__(self, kg: KnowledgeGraph):
        super().__init__(kg, "CALiSol-23")
        self._solvents: dict[str, Solvent] = {}
        self._salts: dict[str, Salt] = {}
        self._method: Optional[MeasurementMethod] = None

    def download(self, output_dir: Path) -> Path:
        """Download is handled externally - returns expected path."""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "calisol23_dataset.csv"
        if not output_path.exists():
            raise FileNotFoundError(
                f"CALiSol-23 dataset not found at {output_path}.\n"
                f"Download from: {self.GITHUB_URL}"
            )
        return output_path

    def ingest(self, data_path: Path) -> dict:
        """Ingest the CALiSol-23 dataset into the KG."""
        # Set up provenance
        self._create_agent()
        self._create_source(
            source_type="dataset",
            doi=self.PAPER_DOI,
            url=self.GITHUB_URL,
            authors=[
                "Paolo de Blasio", "Jonas Elsborg", "Tejs Vegge",
                "Eibar Flores", "Arghya Bhowmik",
            ],
            publication_date=datetime(2024, 7, 6),
            license="CC BY 4.0",
        )

        # Create measurement method
        self._method = MeasurementMethod(
            name="Conductivity-Literature",
            description="Ionic conductivity from literature compilation",
            parameters={
                "compilation": "CALiSol-23",
                "sources": "27 experimental articles",
            },
        )
        self.kg.add_method(self._method)

        # Load data
        df = pd.read_csv(data_path)
        print(f"Loaded {len(df)} measurements from CALiSol-23")

        # Create molecules
        self._create_molecules(df)

        # Process measurements
        stats = self._process_dataframe(df)

        return stats

    def _create_molecules(self, df: pd.DataFrame) -> None:
        """Create solvent and salt molecules from the dataset."""
        # Identify which solvents are actually used
        used_solvents = set()
        for col in SOLVENT_COLUMNS:
            if col in df.columns:
                if (df[col] > 0).any():
                    used_solvents.add(col)

        print(f"Creating {len(used_solvents)} solvents...")

        # Create solvents
        for abbrev in used_solvents:
            smiles = CALISOL_SMILES.get(abbrev)
            if not smiles:
                continue

            name = COMPOUND_NAMES.get(abbrev, abbrev)
            solvent = Solvent(
                name=name,
                smiles=smiles,
                synonyms=[abbrev],
            )
            self.kg.add_solvent(solvent)
            self._solvents[abbrev] = solvent

            # Add provenance
            self._create_provenance(
                entity_id=solvent.id,
                entity_type="Solvent",
                row_id=f"solvent-{abbrev}",
                confidence=1.0,
            )

        # Identify which salts are used
        used_salts = df["salt"].unique()
        print(f"Creating {len(used_salts)} salts...")

        # Create salts
        for salt_name in used_salts:
            smiles = CALISOL_SMILES.get(salt_name)
            if not smiles:
                continue

            full_name = COMPOUND_NAMES.get(salt_name, salt_name)
            salt = Salt(
                name=full_name,
                smiles=smiles,
                cation="Li+",
                anion=salt_name.replace("Li", ""),
                synonyms=[salt_name],
            )
            self.kg.add_salt(salt)
            self._salts[salt_name] = salt

            # Add provenance
            self._create_provenance(
                entity_id=salt.id,
                entity_type="Salt",
                row_id=f"salt-{salt_name}",
                confidence=1.0,
            )

    def _process_dataframe(self, df: pd.DataFrame) -> dict:
        """Process the CALiSol-23 dataframe."""
        stats = {
            "formulations_created": 0,
            "measurements_created": 0,
            "rows_processed": 0,
            "rows_skipped": 0,
            "errors": [],
        }

        formulation_cache = {}

        for idx, row in df.iterrows():
            try:
                # Get formulation key
                form_key = self._get_formulation_key(row)

                if form_key not in formulation_cache:
                    # Create new formulation
                    formulation = self._create_formulation(row, idx)
                    if formulation:
                        formulation_cache[form_key] = formulation
                        stats["formulations_created"] += 1
                    else:
                        stats["rows_skipped"] += 1
                        continue
                else:
                    formulation = formulation_cache[form_key]

                # Create measurement
                measurement = self._create_measurement(row, formulation, idx)
                if measurement:
                    stats["measurements_created"] += 1

                stats["rows_processed"] += 1

            except Exception as e:
                stats["errors"].append(f"Row {idx}: {str(e)}")

        return stats

    def _get_formulation_key(self, row: pd.Series) -> str:
        """Generate unique formulation key."""
        parts = [f"salt:{row['salt']}"]

        # Add solvent ratios
        for col in SOLVENT_COLUMNS:
            if col in row.index:
                val = row[col]
                if pd.notna(val) and val > 0:
                    parts.append(f"{col}:{val:.4f}")

        # Add concentration
        parts.append(f"c:{row['c']:.4f}")

        return "|".join(parts)

    def _create_formulation(
        self,
        row: pd.Series,
        row_idx: int,
    ) -> Optional[ElectrolyteFormulation]:
        """Create a formulation from a dataframe row."""
        components = []

        # Get salt
        salt_name = row["salt"]
        salt = self._salts.get(salt_name)
        if not salt:
            return None

        # Add salt component (concentration-based)
        concentration = float(row["c"])
        c_units = row.get("c units", "mol/kg")

        salt_comp = FormulationComponent(
            molecule_id=salt.id,
            component_type=ComponentType.SALT,
            amount=concentration,
            unit=AmountUnit.MOLALITY if "kg" in str(c_units) else AmountUnit.MOLARITY,
        )
        components.append(salt_comp)

        # Add solvent components
        solvent_parts = []
        for col in SOLVENT_COLUMNS:
            if col in row.index:
                ratio = row[col]
                if pd.notna(ratio) and ratio > 0:
                    solvent = self._solvents.get(col)
                    if solvent:
                        comp = FormulationComponent(
                            molecule_id=solvent.id,
                            component_type=ComponentType.SOLVENT,
                            amount=float(ratio),
                            unit=AmountUnit.WEIGHT_FRACTION,
                        )
                        components.append(comp)
                        solvent_parts.append(col)

        if not solvent_parts:
            return None

        # Create formulation name
        solvent_str = "-".join(sorted(solvent_parts)[:3])
        if len(solvent_parts) > 3:
            solvent_str += f"+{len(solvent_parts)-3}"

        formulation = ElectrolyteFormulation(
            name=f"{solvent_str}/{salt_name}-{row_idx}",
            components=components,
            source_id=self._source.id,
        )

        self.kg.add_formulation(formulation)

        # Add provenance
        self._create_provenance(
            entity_id=formulation.id,
            entity_type="ElectrolyteFormulation",
            row_id=str(row_idx),
            confidence=1.0,
        )

        return formulation

    def _create_measurement(
        self,
        row: pd.Series,
        formulation: ElectrolyteFormulation,
        row_idx: int,
    ) -> Optional[PropertyMeasurement]:
        """Create a conductivity measurement."""
        conductivity = row.get("k")
        if pd.isna(conductivity):
            return None

        temperature = row.get("T", 298.15)  # Default to 25C in Kelvin

        # Convert K to C if needed
        if temperature > 200:  # Likely in Kelvin
            temp_c = temperature - 273.15
        else:
            temp_c = temperature

        measurement = PropertyMeasurement(
            property_type=PropertyType.IONIC_CONDUCTIVITY,
            value=float(conductivity),
            unit="S/cm",
            temperature=float(temp_c),
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

        # Add provenance (DOI is tracked in source)
        self._create_provenance(
            entity_id=measurement.id,
            entity_type="PropertyMeasurement",
            row_id=str(row_idx),
            confidence=1.0,
        )

        return measurement
