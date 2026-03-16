"""Ingestor for Electrolytomics ML-predicted properties for candidate molecules."""

from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd

from .base import BaseIngestor
from ..kg_store.graph import KnowledgeGraph, canonicalize_smiles
from ..schema.entities import (
    Molecule, Solvent, Salt,
    PropertyMeasurement, MeasurementMethod,
    PropertyType,
)
from ..schema.relations import RelationType
from ..schema.provenance import ProvenanceRecord


class MLPredictionsIngestor(BaseIngestor):
    """
    Ingestor for Electrolytomics ML-predicted properties.

    Dataset: ML predictions for eMolecules candidate electrolytes
    Paper DOI: 10.1021/acs.chemmater.4c03196
    Data: ~76K molecules with predicted conductivity, IE, and CE
    Method: Chemprop/LightGBM models trained on experimental data
    """

    PAPER_DOI = "10.1021/acs.chemmater.4c03196"
    GITHUB_URL = "https://github.com/AmanchukwuLab/electrolytomics"

    def __init__(self, kg: KnowledgeGraph):
        super().__init__(kg, "Electrolytomics-ML-Predictions")
        self._molecules_by_smiles: dict[str, str] = {}
        self._cond_method: Optional[MeasurementMethod] = None
        self._ie_method: Optional[MeasurementMethod] = None
        self._ce_method: Optional[MeasurementMethod] = None
        self._salt_id: Optional[str] = None

    def download(self, output_dir: Path) -> Path:
        """Download is handled externally."""
        return output_dir

    def ingest(self, data_path: Path) -> dict:
        """Ingest ML predictions."""
        # Set up provenance
        self._create_agent()
        self._create_source(
            source_type="ml_predictions",
            doi=self.PAPER_DOI,
            url=self.GITHUB_URL,
            authors=[
                "Ritesh Kumar", "Minh Canh Vu", "Peiyuan Ma", "Chibueze Amanchukwu"
            ],
            publication_date=datetime(2025, 1, 1),
            license="MIT",
        )

        # Create measurement methods for ML predictions
        self._cond_method = MeasurementMethod(
            name="ML-Predicted-Conductivity",
            description="Ionic conductivity predicted by Chemprop/LightGBM ensemble",
            parameters={
                "model": "Chemprop + LightGBM ensemble",
                "training_data": "EDB-1 experimental conductivity",
                "prediction_type": "virtual_screening",
            },
        )
        self.kg.add_method(self._cond_method)

        self._ie_method = MeasurementMethod(
            name="ML-Predicted-IE",
            description="Ionization energy predicted by ML model",
            parameters={
                "model": "Chemprop + LightGBM ensemble",
                "training_data": "Materials Project DFT IE values",
                "prediction_type": "virtual_screening",
            },
        )
        self.kg.add_method(self._ie_method)

        self._ce_method = MeasurementMethod(
            name="ML-Predicted-CE",
            description="Coulombic efficiency predicted by ML model",
            parameters={
                "model": "Chemprop + LightGBM ensemble",
                "training_data": "EDB-2 experimental CE",
                "prediction_type": "virtual_screening",
            },
        )
        self.kg.add_method(self._ce_method)

        # Ensure LiFSI salt exists
        lifsi_smiles = "[Li+].[N-](S(=O)(=O)F)S(=O)(=O)F"
        self._salt_id = self._get_or_create_molecule(lifsi_smiles, is_salt=True, name="LiFSI")

        stats = {
            "records_processed": 0,
            "records_skipped": 0,
            "molecules_created": 0,
            "molecules_matched": 0,
            "conductivity_predictions": 0,
            "ie_predictions": 0,
            "ce_predictions": 0,
        }

        # Load predictions file
        pred_file = data_path / "datasets" / "predicted" / "conductivity" / "emolecules_predicted_cond_oxstab_ce.csv"
        if not pred_file.exists():
            print(f"Predictions file not found: {pred_file}")
            return stats

        df = pd.read_csv(pred_file)
        print(f"Loaded {len(df)} ML predictions from Electrolytomics")

        # Process in batches for efficiency
        batch_size = 1000
        for batch_start in range(0, len(df), batch_size):
            batch_end = min(batch_start + batch_size, len(df))
            batch_df = df.iloc[batch_start:batch_end]

            for idx, row in batch_df.iterrows():
                try:
                    result = self._process_prediction(row, idx)
                    if result:
                        stats["records_processed"] += 1
                        if result.get("new_molecule"):
                            stats["molecules_created"] += 1
                        else:
                            stats["molecules_matched"] += 1
                        if result.get("conductivity"):
                            stats["conductivity_predictions"] += 1
                        if result.get("ie"):
                            stats["ie_predictions"] += 1
                        if result.get("ce"):
                            stats["ce_predictions"] += 1
                    else:
                        stats["records_skipped"] += 1
                except Exception as e:
                    stats["records_skipped"] += 1

            # Progress update
            if batch_end % 10000 == 0:
                print(f"  Processed {batch_end}/{len(df)} records...")

        return stats

    def _get_or_create_molecule(
        self,
        smiles: str,
        is_salt: bool = False,
        name: Optional[str] = None,
    ) -> Optional[str]:
        """Get existing molecule ID or create new one."""
        if not smiles or pd.isna(smiles):
            return None

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
        mol_name = name if name else canonical[:50]

        if is_salt:
            mol = Salt(name=mol_name, smiles=canonical)
            mol_id = self.kg.add_salt(mol)
        else:
            mol = Solvent(name=mol_name, smiles=canonical)
            mol_id = self.kg.add_solvent(mol)

        self._molecules_by_smiles[canonical] = mol_id

        # Add provenance for new molecule
        prov = ProvenanceRecord(
            entity_id=mol_id,
            entity_type="Salt" if is_salt else "Solvent",
            source_ids=[self._source.id] if self._source else [],
            source_doi=self.PAPER_DOI,
            source_row_id=f"emolecules-{mol_name[:20]}",
            extraction_method="smiles_from_emolecules",
            confidence=1.0,
            kg_version=self.kg.version,
        )
        self.kg.add_provenance(prov)

        return mol_id

    def _process_prediction(self, row: pd.Series, idx: int) -> Optional[dict]:
        """Process a single prediction row."""
        solvent_smiles = row.get('solv_comb_sm')

        if pd.isna(solvent_smiles) or not solvent_smiles:
            return None

        # Check if molecule already exists
        canonical = canonicalize_smiles(solvent_smiles)
        is_new = canonical not in self._molecules_by_smiles and \
                 self.kg._find_existing_molecule_by_smiles(canonical) is None

        # Get or create molecule
        mol_id = self._get_or_create_molecule(solvent_smiles)
        if not mol_id:
            return None

        result = {"new_molecule": is_new}

        # Get predicted values
        cond_log = row.get('conductivity_log')
        ie = row.get('IE')
        log_ci = row.get('log_CI')

        # Add conductivity prediction (convert from log10(mS/cm) to S/cm)
        if pd.notna(cond_log):
            cond_ms_cm = 10 ** float(cond_log)  # mS/cm
            cond_s_cm = cond_ms_cm / 1000.0  # S/cm

            # Only add reasonable values
            if 1e-12 < cond_s_cm < 1.0:
                measurement = PropertyMeasurement(
                    property_type=PropertyType.IONIC_CONDUCTIVITY,
                    value=cond_s_cm,
                    unit="S/cm",
                    method_id=self._cond_method.id,
                )
                self.kg.add_measurement(measurement)
                self.kg.add_relation(mol_id, RelationType.HAS_MEASUREMENT, measurement.id)

                # Add provenance (ML prediction, lower confidence)
                prov = ProvenanceRecord(
                    entity_id=measurement.id,
                    entity_type="PropertyMeasurement",
                    source_ids=[self._source.id] if self._source else [],
                    source_doi=self.PAPER_DOI,
                    source_row_id=f"ml-cond-{idx}",
                    extraction_method="ml_prediction",
                    confidence=0.6,  # Lower confidence for ML predictions
                    kg_version=self.kg.version,
                )
                self.kg.add_provenance(prov)
                result["conductivity"] = True

        # Add ionization energy prediction
        if pd.notna(ie) and 2.0 < float(ie) < 15.0:
            measurement = PropertyMeasurement(
                property_type=PropertyType.IONIZATION_ENERGY,
                value=float(ie),
                unit="eV",
                method_id=self._ie_method.id,
            )
            self.kg.add_measurement(measurement)
            self.kg.add_relation(mol_id, RelationType.HAS_MEASUREMENT, measurement.id)

            prov = ProvenanceRecord(
                entity_id=measurement.id,
                entity_type="PropertyMeasurement",
                source_ids=[self._source.id] if self._source else [],
                source_doi=self.PAPER_DOI,
                source_row_id=f"ml-ie-{idx}",
                extraction_method="ml_prediction",
                confidence=0.6,
                kg_version=self.kg.version,
            )
            self.kg.add_provenance(prov)
            result["ie"] = True

        # Add Coulombic efficiency prediction (convert from log10(1-CE))
        if pd.notna(log_ci):
            ce = 1.0 - (10 ** float(log_ci))
            if 0.0 < ce < 1.0:
                measurement = PropertyMeasurement(
                    property_type=PropertyType.COULOMBIC_EFFICIENCY,
                    value=ce,
                    unit="dimensionless",
                    method_id=self._ce_method.id,
                )
                self.kg.add_measurement(measurement)
                self.kg.add_relation(mol_id, RelationType.HAS_MEASUREMENT, measurement.id)

                prov = ProvenanceRecord(
                    entity_id=measurement.id,
                    entity_type="PropertyMeasurement",
                    source_ids=[self._source.id] if self._source else [],
                    source_doi=self.PAPER_DOI,
                    source_row_id=f"ml-ce-{idx}",
                    extraction_method="ml_prediction",
                    confidence=0.6,
                    kg_version=self.kg.version,
                )
                self.kg.add_provenance(prov)
                result["ce"] = True

        return result
