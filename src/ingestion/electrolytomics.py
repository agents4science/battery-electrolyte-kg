"""Ingestor for Electrolytomics dataset (Amanchukwu Lab, Chem. Mater. 2025)."""

from pathlib import Path
from datetime import datetime
from typing import Optional
import hashlib

import pandas as pd

from .base import BaseIngestor
from ..kg_store.graph import KnowledgeGraph, canonicalize_smiles
from ..schema.entities import (
    Molecule, Solvent, Salt, Additive,
    ElectrolyteFormulation, FormulationComponent,
    PropertyMeasurement, MeasurementMethod, EvidenceSource,
    ComponentType, AmountUnit, PropertyType,
)
from ..schema.relations import RelationType
from ..schema.provenance import ProvenanceRecord


# Known molecule names by SMILES (for better naming)
SMILES_TO_NAME = {
    # Carbonates
    "C1COC(=O)O1": "Ethylene carbonate",
    "O=C1OCCO1": "Ethylene carbonate",
    "CC1COC(=O)O1": "Propylene carbonate",
    "COC(=O)OC": "Dimethyl carbonate",
    "CCOC(=O)OC": "Ethyl methyl carbonate",
    "CCOC(=O)OCC": "Diethyl carbonate",
    "C1C(OC(=O)O1)F": "Fluoroethylene carbonate",
    "C=C1OC(=O)O1": "Vinylene carbonate",
    # Glymes
    "COCCOC": "1,2-Dimethoxyethane",
    "COCCOCCOC": "Diglyme",
    "COCCOCCOCCOC": "Triglyme",
    "COCCOCCOCCOCCOC": "Tetraglyme",
    # Other solvents
    "CS(=O)C": "Dimethyl sulfoxide",
    "CC#N": "Acetonitrile",
    "C1CCOC1": "Tetrahydrofuran",
    "C1COCO1": "1,3-Dioxolane",
    "O=S1(=O)CCCC1": "Sulfolane",
    "CN(C)C=O": "Dimethylformamide",
    "C1CC(=O)OC1": "gamma-Butyrolactone",
    # Lithium salts
    "[Li+].F[P-](F)(F)(F)(F)F": "LiPF6",
    "[Li+].F[B-](F)(F)F": "LiBF4",
    "[Li+].C(F)(F)(F)S(=O)(=O)[N-]S(=O)(=O)C(F)(F)F": "LiTFSI",
    "[Li]N(S(=O)(=O)C(F)(F)F)S(=O)(=O)C(F)(F)F": "LiTFSI",
    "[Li+].[N-](S(=O)(=O)F)S(=O)(=O)F": "LiFSI",
    "[Li+].[O-]Cl(=O)(=O)=O": "LiClO4",
    "[Li+].[O-][Cl+3]([O-])([O-])[O-]": "LiClO4",
    "[Li+].O=C1O[B-]2(OC1=O)OC(=O)C(=O)O2": "LiBOB",
    "[Li+].[O-]S(=O)(=O)C(F)(F)F": "LiOTf",
    "F[As-](F)(F)(F)(F)F.[Li+]": "LiAsF6",
    # Sodium salts
    "[Na+].F[P-](F)(F)(F)(F)F": "NaPF6",
    "[Na+].C(F)(F)(F)S(=O)(=O)[N-]S(=O)(=O)C(F)(F)F": "NaTFSI",
    "[Na+].[N-](S(=O)(=O)F)S(=O)(=O)F": "NaFSI",
    "[Na+].[O-]Cl(=O)(=O)=O": "NaClO4",
}


def get_molecule_name(smiles: str) -> str:
    """Get a readable name for a molecule from its SMILES."""
    if not smiles:
        return "Unknown"

    # Try canonical form
    canonical = canonicalize_smiles(smiles)
    if canonical and canonical in SMILES_TO_NAME:
        return SMILES_TO_NAME[canonical]

    # Try original
    if smiles in SMILES_TO_NAME:
        return SMILES_TO_NAME[smiles]

    # Return shortened SMILES as name
    if len(smiles) > 30:
        return smiles[:27] + "..."
    return smiles


def generate_formulation_id(components: list[tuple[str, float]]) -> str:
    """Generate a deterministic ID for a formulation based on components."""
    # Sort by SMILES for consistency
    sorted_comps = sorted(components, key=lambda x: x[0])
    key = "|".join(f"{s}:{r:.4f}" for s, r in sorted_comps)
    return hashlib.md5(key.encode()).hexdigest()[:16]


class ElectrolytomicsIngestor(BaseIngestor):
    """
    Ingestor for Electrolytomics dataset.

    Dataset: Electrolytomics - unified big data approach for electrolyte design
    Paper DOI: 10.1021/acs.chemmater.4c03196
    Data: ~10K conductivity, ~18K oxidation stability, ~140 CE measurements
    """

    PAPER_DOI = "10.1021/acs.chemmater.4c03196"
    GITHUB_URL = "https://github.com/AmanchukwuLab/electrolytomics"

    def __init__(self, kg: KnowledgeGraph):
        super().__init__(kg, "Electrolytomics")
        self._molecules_by_smiles: dict[str, str] = {}  # canonical_smiles -> molecule_id
        self._formulations_cache: dict[str, str] = {}  # formulation_key -> formulation_id
        self._cond_method: Optional[MeasurementMethod] = None
        self._ie_method: Optional[MeasurementMethod] = None
        self._ce_method: Optional[MeasurementMethod] = None

    def download(self, output_dir: Path) -> Path:
        """Download is handled externally via git clone."""
        output_path = output_dir / "electrolytomics"
        if not output_path.exists():
            raise FileNotFoundError(
                f"Electrolytomics data not found at {output_path}.\n"
                f"Clone from: {self.GITHUB_URL}"
            )
        return output_path

    def _get_or_create_molecule(
        self,
        smiles: str,
        is_salt: bool = False,
        is_additive: bool = False,
    ) -> Optional[str]:
        """Get existing molecule ID or create new one."""
        if not smiles or pd.isna(smiles):
            return None

        # Canonicalize
        canonical = canonicalize_smiles(smiles)
        if not canonical:
            return None

        # Check cache
        if canonical in self._molecules_by_smiles:
            return self._molecules_by_smiles[canonical]

        # Check existing KG
        existing_id = self.kg._find_existing_molecule_by_smiles(canonical)
        if existing_id:
            self._molecules_by_smiles[canonical] = existing_id
            return existing_id

        # Create new molecule
        name = get_molecule_name(smiles)

        if is_salt:
            # Determine cation
            cation = "Li+" if "[Li" in smiles else "Na+" if "[Na" in smiles else None
            mol = Salt(name=name, smiles=canonical, cation=cation)
            mol_id = self.kg.add_salt(mol)
        elif is_additive:
            mol = Additive(name=name, smiles=canonical)
            mol_id = self.kg.add_additive(mol)
        else:
            mol = Solvent(name=name, smiles=canonical)
            mol_id = self.kg.add_solvent(mol)

        self._molecules_by_smiles[canonical] = mol_id

        # Add provenance
        prov = ProvenanceRecord(
            entity_id=mol_id,
            entity_type="Salt" if is_salt else "Additive" if is_additive else "Solvent",
            source_ids=[self._source.id] if self._source else [],
            source_doi=self.PAPER_DOI,
            extraction_method="smiles_from_dataset",
            confidence=1.0,
            kg_version=self.kg.version,
        )
        self.kg.add_provenance(prov)

        return mol_id

    def ingest(self, data_path: Path) -> dict:
        """Ingest all Electrolytomics data."""
        # Set up provenance
        self._create_agent()
        self._create_source(
            source_type="dataset",
            doi=self.PAPER_DOI,
            url=self.GITHUB_URL,
            authors=[
                "Ritesh Kumar", "Minh Canh Vu", "Peiyuan Ma", "Chibueze Amanchukwu"
            ],
            publication_date=datetime(2025, 1, 1),  # Chem. Mater. 2025
            license="MIT",
        )

        # Create measurement methods
        self._cond_method = MeasurementMethod(
            name="Electrolytomics-Conductivity",
            description="Ionic conductivity from Electrolytomics database compilation",
            parameters={"source": "EDB-1"},
        )
        self.kg.add_method(self._cond_method)

        self._ie_method = MeasurementMethod(
            name="DFT-IonizationEnergy",
            description="Vertical ionization energy from Materials Project DFT calculations",
            parameters={"source": "MP_oxstab", "level": "DFT"},
        )
        self.kg.add_method(self._ie_method)

        self._ce_method = MeasurementMethod(
            name="Electrolytomics-CE",
            description="Coulombic efficiency from Electrolytomics database",
            parameters={"source": "EDB-2"},
        )
        self.kg.add_method(self._ce_method)

        stats = {
            "conductivity": {},
            "ionization_energy": {},
            "coulombic_efficiency": {},
        }

        # Ingest conductivity data
        cond_path = data_path / "datasets" / "raw" / "conductivity" / "EDB-1_conductivity.csv"
        if cond_path.exists():
            stats["conductivity"] = self._ingest_conductivity(cond_path)

        # Ingest ionization energy data
        ie_path = data_path / "datasets" / "raw" / "oxstab" / "MP_oxstab.csv"
        if ie_path.exists():
            stats["ionization_energy"] = self._ingest_ionization_energy(ie_path)

        # Ingest Coulombic efficiency data
        ce_path = data_path / "datasets" / "raw" / "CE" / "EDB-2_ce.csv"
        if ce_path.exists():
            stats["coulombic_efficiency"] = self._ingest_coulombic_efficiency(ce_path)

        return stats

    def _ingest_conductivity(self, data_path: Path) -> dict:
        """Ingest conductivity measurements."""
        df = pd.read_csv(data_path)
        print(f"Loaded {len(df)} conductivity records from Electrolytomics")

        stats = {
            "records_processed": 0,
            "records_skipped": 0,
            "formulations_created": 0,
            "measurements_created": 0,
            "molecules_created": 0,
        }

        for idx, row in df.iterrows():
            try:
                # Get solvent SMILES and ratios
                solvents = []
                for i in range(1, 5):
                    smiles = row.get(f'solv_{i}_sm')
                    ratio = row.get(f'solv_ratio_{i}', 0)
                    if pd.notna(smiles) and smiles and ratio > 0:
                        mol_id = self._get_or_create_molecule(smiles, is_salt=False)
                        if mol_id:
                            solvents.append((mol_id, smiles, float(ratio)))
                            if mol_id not in self.kg._molecules:
                                stats["molecules_created"] += 1

                # Get salt
                salt_smiles = row.get('salt_sm')
                salt_id = None
                if pd.notna(salt_smiles) and salt_smiles:
                    salt_id = self._get_or_create_molecule(salt_smiles, is_salt=True)
                    if salt_id and salt_id not in self.kg._molecules:
                        stats["molecules_created"] += 1

                if not solvents or not salt_id:
                    stats["records_skipped"] += 1
                    continue

                # Get or create formulation
                salt_conc = float(row.get('conc_salt', 1.0))
                form_key = self._get_formulation_key(solvents, salt_id, salt_conc)

                if form_key in self._formulations_cache:
                    formulation_id = self._formulations_cache[form_key]
                else:
                    formulation_id = self._create_formulation(
                        solvents, salt_id, salt_conc, idx
                    )
                    self._formulations_cache[form_key] = formulation_id
                    stats["formulations_created"] += 1

                # Get conductivity value (mS/cm -> S/cm)
                conductivity = row.get('conductivity')
                if pd.isna(conductivity) or conductivity <= 0:
                    stats["records_skipped"] += 1
                    continue

                conductivity_s_cm = float(conductivity) / 1000.0  # mS/cm to S/cm

                # Get temperature
                temperature = row.get('temperature', 25.0)
                if pd.isna(temperature):
                    temperature = 25.0

                # Create measurement
                measurement = PropertyMeasurement(
                    property_type=PropertyType.IONIC_CONDUCTIVITY,
                    value=conductivity_s_cm,
                    unit="S/cm",
                    temperature=float(temperature),
                    temperature_unit="C",
                    method_id=self._cond_method.id,
                )
                self.kg.add_measurement(measurement)

                # Link to formulation
                formulation = self.kg.get_formulation(formulation_id)
                if formulation:
                    formulation.measurements.append(measurement.id)
                self.kg.add_relation(
                    formulation_id,
                    RelationType.HAS_MEASUREMENT,
                    measurement.id,
                )

                # Add provenance
                prov = ProvenanceRecord(
                    entity_id=measurement.id,
                    entity_type="PropertyMeasurement",
                    source_ids=[self._source.id] if self._source else [],
                    source_doi=self.PAPER_DOI,
                    source_row_id=f"elytomics-cond-{idx}",
                    extraction_method="structured_dataset",
                    confidence=1.0,
                    kg_version=self.kg.version,
                )
                self.kg.add_provenance(prov)

                stats["measurements_created"] += 1
                stats["records_processed"] += 1

            except Exception as e:
                stats["records_skipped"] += 1

        return stats

    def _ingest_ionization_energy(self, data_path: Path) -> dict:
        """Ingest ionization energy (oxidation stability) data."""
        df = pd.read_csv(data_path)
        print(f"Loaded {len(df)} ionization energy records from Electrolytomics")

        stats = {
            "records_processed": 0,
            "records_skipped": 0,
            "molecules_created": 0,
            "measurements_created": 0,
        }

        for idx, row in df.iterrows():
            try:
                smiles = row.get('smiles')
                ie = row.get('IE')

                if pd.isna(smiles) or not smiles or pd.isna(ie):
                    stats["records_skipped"] += 1
                    continue

                # Get or create molecule
                mol_id = self._get_or_create_molecule(smiles, is_salt=False)
                if not mol_id:
                    stats["records_skipped"] += 1
                    continue

                if mol_id not in self.kg._molecules:
                    stats["molecules_created"] += 1

                # Create measurement
                measurement = PropertyMeasurement(
                    property_type=PropertyType.IONIZATION_ENERGY,
                    value=float(ie),
                    unit="eV",
                    method_id=self._ie_method.id,
                )
                self.kg.add_measurement(measurement)

                # Link to molecule
                self.kg.add_relation(
                    mol_id,
                    RelationType.HAS_MEASUREMENT,
                    measurement.id,
                )

                # Add provenance
                prov = ProvenanceRecord(
                    entity_id=measurement.id,
                    entity_type="PropertyMeasurement",
                    source_ids=[self._source.id] if self._source else [],
                    source_doi=self.PAPER_DOI,
                    source_row_id=f"elytomics-ie-{idx}",
                    extraction_method="dft_calculation",
                    confidence=1.0,
                    kg_version=self.kg.version,
                )
                self.kg.add_provenance(prov)

                stats["measurements_created"] += 1
                stats["records_processed"] += 1

            except Exception as e:
                stats["records_skipped"] += 1

        return stats

    def _ingest_coulombic_efficiency(self, data_path: Path) -> dict:
        """Ingest Coulombic efficiency data."""
        df = pd.read_csv(data_path)
        print(f"Loaded {len(df)} CE records from Electrolytomics")

        stats = {
            "records_processed": 0,
            "records_skipped": 0,
            "formulations_created": 0,
            "measurements_created": 0,
        }

        for idx, row in df.iterrows():
            try:
                # Get solvents
                solvents = []
                for i in range(1, 4):
                    smiles = row.get(f'solvent_{i}_smiles')
                    ratio = row.get(f'solv_{i}_ratio', 0)
                    if pd.notna(smiles) and smiles and ratio > 0:
                        mol_id = self._get_or_create_molecule(smiles, is_salt=False)
                        if mol_id:
                            solvents.append((mol_id, smiles, float(ratio)))

                # Get salts
                salt_ids = []
                for i in range(1, 3):
                    smiles = row.get(f'salt_{i}_smiles')
                    conc = row.get(f'salt_{i}_conc', 0)
                    if pd.notna(smiles) and smiles and conc > 0:
                        mol_id = self._get_or_create_molecule(smiles, is_salt=True)
                        if mol_id:
                            salt_ids.append((mol_id, float(conc)))

                # Get additive
                additive_smiles = row.get('additive_smiles')
                additive_id = None
                if pd.notna(additive_smiles) and additive_smiles:
                    additive_id = self._get_or_create_molecule(additive_smiles, is_additive=True)

                if not solvents or not salt_ids:
                    stats["records_skipped"] += 1
                    continue

                # Create formulation (simplified - use first salt)
                salt_id, salt_conc = salt_ids[0]
                form_key = self._get_formulation_key(solvents, salt_id, salt_conc)

                if form_key in self._formulations_cache:
                    formulation_id = self._formulations_cache[form_key]
                else:
                    formulation_id = self._create_formulation(
                        solvents, salt_id, salt_conc, idx, prefix="ce"
                    )
                    self._formulations_cache[form_key] = formulation_id
                    stats["formulations_created"] += 1

                # Get CE value
                ce = row.get('CE')
                if pd.isna(ce):
                    stats["records_skipped"] += 1
                    continue

                # Create measurement (CE is dimensionless, 0-1)
                measurement = PropertyMeasurement(
                    property_type=PropertyType.COULOMBIC_EFFICIENCY,
                    value=float(ce),
                    unit="dimensionless",
                    method_id=self._ce_method.id,
                )
                self.kg.add_measurement(measurement)

                # Link to formulation
                formulation = self.kg.get_formulation(formulation_id)
                if formulation:
                    formulation.measurements.append(measurement.id)
                self.kg.add_relation(
                    formulation_id,
                    RelationType.HAS_MEASUREMENT,
                    measurement.id,
                )

                # Add provenance
                prov = ProvenanceRecord(
                    entity_id=measurement.id,
                    entity_type="PropertyMeasurement",
                    source_ids=[self._source.id] if self._source else [],
                    source_doi=self.PAPER_DOI,
                    source_row_id=f"elytomics-ce-{idx}",
                    extraction_method="structured_dataset",
                    confidence=1.0,
                    kg_version=self.kg.version,
                )
                self.kg.add_provenance(prov)

                stats["measurements_created"] += 1
                stats["records_processed"] += 1

            except Exception as e:
                stats["records_skipped"] += 1

        return stats

    def _get_formulation_key(
        self,
        solvents: list[tuple[str, str, float]],
        salt_id: str,
        salt_conc: float,
    ) -> str:
        """Generate a unique key for a formulation."""
        # Sort solvents by ID for consistency
        sorted_solvents = sorted(solvents, key=lambda x: x[0])
        parts = [f"salt:{salt_id}:{salt_conc:.4f}"]
        for mol_id, smiles, ratio in sorted_solvents:
            parts.append(f"solv:{mol_id}:{ratio:.4f}")
        return "|".join(parts)

    def _create_formulation(
        self,
        solvents: list[tuple[str, str, float]],
        salt_id: str,
        salt_conc: float,
        row_idx: int,
        prefix: str = "cond",
    ) -> str:
        """Create a new formulation."""
        components = []

        # Add salt component
        salt_comp = FormulationComponent(
            molecule_id=salt_id,
            component_type=ComponentType.SALT,
            amount=salt_conc,
            unit=AmountUnit.MOLALITY,
        )
        components.append(salt_comp)

        # Add solvent components
        solvent_names = []
        for mol_id, smiles, ratio in solvents:
            comp = FormulationComponent(
                molecule_id=mol_id,
                component_type=ComponentType.SOLVENT,
                amount=ratio,
                unit=AmountUnit.WEIGHT_FRACTION,
            )
            components.append(comp)
            solvent_names.append(get_molecule_name(smiles)[:10])

        # Generate name
        salt_mol = self.kg.get_molecule(salt_id)
        salt_name = salt_mol.name if salt_mol else "Salt"
        solvent_str = "-".join(solvent_names[:2])
        if len(solvent_names) > 2:
            solvent_str += f"+{len(solvent_names)-2}"

        formulation = ElectrolyteFormulation(
            name=f"{solvent_str}/{salt_name}-{prefix}{row_idx}",
            components=components,
            source_id=self._source.id if self._source else None,
        )

        self.kg.add_formulation(formulation)

        # Add provenance
        prov = ProvenanceRecord(
            entity_id=formulation.id,
            entity_type="ElectrolyteFormulation",
            source_ids=[self._source.id] if self._source else [],
            source_doi=self.PAPER_DOI,
            source_row_id=f"elytomics-form-{prefix}{row_idx}",
            extraction_method="structured_dataset",
            confidence=1.0,
            kg_version=self.kg.version,
        )
        self.kg.add_provenance(prov)

        return formulation.id
