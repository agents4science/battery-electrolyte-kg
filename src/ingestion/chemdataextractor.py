"""Ingestor for ChemDataExtractor Battery Database v2 conductivity data."""

from pathlib import Path
from datetime import datetime
from typing import Optional
import re
import csv

import pandas as pd

from .base import BaseIngestor
from ..kg_store.graph import KnowledgeGraph
from ..schema.entities import (
    Molecule, Solvent, Salt,
    PropertyMeasurement, MeasurementMethod, EvidenceSource,
    PropertyType,
)
from ..schema.relations import RelationType


# Known electrolyte materials with SMILES
# Maps common names/abbreviations to canonical SMILES
KNOWN_ELECTROLYTE_SMILES = {
    # Lithium salts
    "lipf6": "[Li+].F[P-](F)(F)(F)(F)F",
    "lithium hexafluorophosphate": "[Li+].F[P-](F)(F)(F)(F)F",
    "libf4": "[Li+].F[B-](F)(F)F",
    "lithium tetrafluoroborate": "[Li+].F[B-](F)(F)F",
    "litfsi": "[Li+].C(F)(F)(F)S(=O)(=O)[N-]S(=O)(=O)C(F)(F)F",
    "lithium bis(trifluoromethanesulfonyl)imide": "[Li+].C(F)(F)(F)S(=O)(=O)[N-]S(=O)(=O)C(F)(F)F",
    "lifsi": "[Li+].[N-](S(=O)(=O)F)S(=O)(=O)F",
    "lithium bis(fluorosulfonyl)imide": "[Li+].[N-](S(=O)(=O)F)S(=O)(=O)F",
    "liclo4": "[Li+].[O-]Cl(=O)(=O)=O",
    "lithium perchlorate": "[Li+].[O-]Cl(=O)(=O)=O",
    "libob": "[Li+].O=C1O[B-]2(OC1=O)OC(=O)C(=O)O2",
    "lithium bis(oxalato)borate": "[Li+].O=C1O[B-]2(OC1=O)OC(=O)C(=O)O2",
    "licf3so3": "[Li+].[O-]S(=O)(=O)C(F)(F)F",
    "lithium triflate": "[Li+].[O-]S(=O)(=O)C(F)(F)F",
    "lithium trifluoromethanesulfonate": "[Li+].[O-]S(=O)(=O)C(F)(F)F",
    "liasf6": "[Li+].F[As-](F)(F)(F)(F)F",
    "lithium hexafluoroarsenate": "[Li+].F[As-](F)(F)(F)(F)F",

    # Sodium salts
    "napf6": "[Na+].F[P-](F)(F)(F)(F)F",
    "sodium hexafluorophosphate": "[Na+].F[P-](F)(F)(F)(F)F",
    "natfsi": "[Na+].C(F)(F)(F)S(=O)(=O)[N-]S(=O)(=O)C(F)(F)F",
    "sodium bis(trifluoromethanesulfonyl)imide": "[Na+].C(F)(F)(F)S(=O)(=O)[N-]S(=O)(=O)C(F)(F)F",
    "nafsi": "[Na+].[N-](S(=O)(=O)F)S(=O)(=O)F",
    "naclo4": "[Na+].[O-]Cl(=O)(=O)=O",
    "sodium perchlorate": "[Na+].[O-]Cl(=O)(=O)=O",

    # Carbonates
    "ec": "C1COC(=O)O1",
    "ethylene carbonate": "C1COC(=O)O1",
    "pc": "CC1COC(=O)O1",
    "propylene carbonate": "CC1COC(=O)O1",
    "dmc": "COC(=O)OC",
    "dimethyl carbonate": "COC(=O)OC",
    "emc": "CCOC(=O)OC",
    "ethyl methyl carbonate": "CCOC(=O)OC",
    "dec": "CCOC(=O)OCC",
    "diethyl carbonate": "CCOC(=O)OCC",
    "fec": "C1C(OC(=O)O1)F",
    "fluoroethylene carbonate": "C1C(OC(=O)O1)F",
    "vc": "C=C1OC(=O)O1",
    "vinylene carbonate": "C=C1OC(=O)O1",

    # Glymes
    "dme": "COCCOC",
    "dimethoxyethane": "COCCOC",
    "1,2-dimethoxyethane": "COCCOC",
    "diglyme": "COCCOCCOC",
    "triglyme": "COCCOCCOCCOC",
    "tetraglyme": "COCCOCCOCCOCCOC",
    "tetraethylene glycol dimethyl ether": "COCCOCCOCCOCCOC",

    # Other solvents
    "dmso": "CS(=O)C",
    "dimethyl sulfoxide": "CS(=O)C",
    "acetonitrile": "CC#N",
    "thf": "C1CCOC1",
    "tetrahydrofuran": "C1CCOC1",
    "dol": "C1COCO1",
    "1,3-dioxolane": "C1COCO1",
    "sulfolane": "O=S1(=O)CCCC1",
    "dmf": "CN(C)C=O",
    "dimethylformamide": "CN(C)C=O",
    "gbl": "C1CC(=O)OC1",
    "gamma-butyrolactone": "C1CC(=O)OC1",
    "g-butyrolactone": "C1CC(=O)OC1",

    # Solid electrolytes
    "li10gep2s12": None,  # LGPS - solid electrolyte (no SMILES)
    "lgps": None,
    "li7la3zr2o12": None,  # LLZO garnet
    "llzo": None,
    "li3ps4": None,
    "na3ps4": None,
    "li6ps5cl": None,  # Argyrodite
    "nasicon": None,
    "lipon": None,
}


def normalize_name(name: str) -> str:
    """Normalize a chemical name for lookup."""
    # Lowercase, remove extra spaces
    name = name.lower().strip()
    # Remove common suffixes/patterns
    name = re.sub(r'\s*@\s*\w+', '', name)  # Remove @ patterns like "@ C"
    name = re.sub(r'\s*/\s*', '/', name)  # Normalize slashes
    name = re.sub(r'\s+', ' ', name)  # Collapse whitespace
    return name


def parse_conductivity_unit(unit_str: str) -> tuple[float, str]:
    """
    Parse conductivity unit and return (multiplier, normalized_unit).

    Returns multiplier to convert to S/cm.
    """
    unit_str = unit_str.lower().strip()

    # Common patterns
    if 'ms' in unit_str or 'millisiemens' in unit_str:
        return 0.001, "S/cm"  # mS/cm -> S/cm
    elif 'μs' in unit_str or 'us' in unit_str or 'microsiemens' in unit_str:
        return 0.000001, "S/cm"  # μS/cm -> S/cm
    elif 's/cm' in unit_str or 'scm' in unit_str:
        return 1.0, "S/cm"
    elif 's/m' in unit_str:
        return 0.01, "S/cm"  # S/m -> S/cm

    # Default: assume S/cm
    return 1.0, "S/cm"


def is_electrolyte_material(name: str, extracted_name: str) -> bool:
    """Check if the material is likely an electrolyte (vs electrode material)."""
    name_lower = normalize_name(name)

    # Positive indicators for electrolytes
    electrolyte_keywords = [
        'electrolyte', 'salt', 'carbonate', 'glyme', 'tfsi', 'fsi',
        'pf6', 'bf4', 'clo4', 'triflate', 'perchlorate', 'sulfone',
        'sulfolane', 'acetonitrile', 'dme', 'thf', 'dioxolane',
        'polymer electrolyte', 'gel electrolyte', 'solid electrolyte',
        'ionic liquid', 'lgps', 'llzo', 'nasicon', 'argyrodite',
        'li3ps4', 'na3ps4', 'li6ps5', 'li7la3zr2o12', 'li10gep2s12',
    ]

    # Negative indicators (electrode materials)
    electrode_keywords = [
        'cathode', 'anode', 'licoo2', 'limno2', 'linio2', 'lfp',
        'lifepo4', 'graphite', 'silicon', 'carbon nanotube', 'cnt',
        'mno2', 'v2o5', 'tio2', 'nmc', 'nca', 'lmo', 'electrode',
    ]

    # Check for electrode keywords (exclude these)
    for kw in electrode_keywords:
        if kw in name_lower:
            return False

    # Check for electrolyte keywords
    for kw in electrolyte_keywords:
        if kw in name_lower:
            return True

    # Check known materials
    if name_lower in KNOWN_ELECTROLYTE_SMILES:
        return True

    # Also check parsed formula for Li/Na salts
    if extracted_name:
        try:
            ext = eval(extracted_name) if extracted_name.startswith('[') else []
            for item in ext:
                if isinstance(item, dict):
                    # Look for Li or Na with common anion elements
                    has_li_or_na = 'Li' in item or 'Na' in item
                    has_anion = any(k in item for k in ['P', 'F', 'S', 'B', 'Cl', 'N'])
                    if has_li_or_na and has_anion:
                        return True
        except:
            pass

    return False


class ChemDataExtractorIngestor(BaseIngestor):
    """
    Ingestor for ChemDataExtractor Battery Database v2 conductivity data.

    Dataset: Auto-generated battery materials database
    DOI: 10.6084/m9.figshare.18154715 (dataset)
    Paper DOI: 10.1038/s41597-020-00602-2 (original)
    Data: ~12,700 conductivity measurements with DOI references
    """

    DATASET_DOI = "10.6084/m9.figshare.18154715"
    PAPER_DOI = "10.1038/s41597-020-00602-2"

    def __init__(self, kg: KnowledgeGraph):
        super().__init__(kg, "ChemDataExtractor-Battery-v2")
        self._materials: dict[str, Molecule] = {}
        self._method: Optional[MeasurementMethod] = None
        self._sources_by_doi: dict[str, EvidenceSource] = {}

    def download(self, output_dir: Path) -> Path:
        """Download is handled externally."""
        output_path = output_dir / "battery-2022.csv"
        if not output_path.exists():
            raise FileNotFoundError(
                f"ChemDataExtractor data not found at {output_path}.\n"
                f"Download from: https://figshare.com/articles/dataset/18154715"
            )
        return output_path

    def _get_or_create_source(self, doi: str, title: str, journal: str, date: str) -> EvidenceSource:
        """Get or create an evidence source for a specific DOI."""
        if doi in self._sources_by_doi:
            return self._sources_by_doi[doi]

        # Parse date
        pub_date = None
        if date:
            try:
                if isinstance(date, list):
                    # Format like ['28', '2', '2018'] -> 2018-02-28
                    pub_date = datetime(int(date[2]), int(date[1]), int(date[0]))
                else:
                    pub_date = datetime.fromisoformat(date.split('T')[0])
            except:
                pass

        source = EvidenceSource(
            source_type="paper",
            name=title[:100] if title else f"DOI:{doi}",
            doi=doi,
            publication_date=pub_date,
        )
        self.kg.add_source(source)
        self._sources_by_doi[doi] = source
        return source

    def ingest(self, data_path: Path) -> dict:
        """Ingest ChemDataExtractor conductivity data."""
        # Set up base provenance
        self._create_agent()
        self._create_source(
            source_type="dataset",
            doi=self.DATASET_DOI,
            url="https://figshare.com/articles/dataset/18154715",
            authors=["Shu Huang", "Jacqueline M. Cole"],
            publication_date=datetime(2022, 3, 7),
            license="CC BY 4.0",
        )

        # Create measurement method
        self._method = MeasurementMethod(
            name="Literature-Extracted",
            description="Conductivity values auto-extracted from literature using ChemDataExtractor NLP",
            parameters={
                "extraction_tool": "ChemDataExtractor",
                "classification": "BatteryBERT",
            },
        )
        self.kg.add_method(self._method)

        # Load data
        df = pd.read_csv(data_path)
        print(f"Loaded {len(df)} total records from ChemDataExtractor")

        # Filter to conductivity only
        cond_df = df[df['Property'] == 'Conductivity'].copy()
        print(f"Found {len(cond_df)} conductivity records")

        # Process records
        stats = self._process_conductivity_records(cond_df)

        return stats

    def _process_conductivity_records(self, df: pd.DataFrame) -> dict:
        """Process conductivity records."""
        stats = {
            "records_processed": 0,
            "records_skipped_non_electrolyte": 0,
            "records_skipped_invalid": 0,
            "materials_created": 0,
            "materials_matched": 0,
            "measurements_created": 0,
            "unique_dois": set(),
            "errors": [],
        }

        for idx, row in df.iterrows():
            try:
                name = str(row.get('Name', ''))
                value = row.get('Value')
                unit = str(row.get('Raw_unit', 'S/cm'))
                doi = str(row.get('DOI', ''))
                extracted_name = str(row.get('Extracted_name', ''))
                title = str(row.get('Title', ''))
                journal = str(row.get('Journal', ''))
                date = row.get('Date', '')

                # Skip invalid values
                if pd.isna(value) or value <= 0:
                    stats["records_skipped_invalid"] += 1
                    continue

                # Check if this is an electrolyte material
                if not is_electrolyte_material(name, extracted_name):
                    stats["records_skipped_non_electrolyte"] += 1
                    continue

                # Normalize the name for lookup
                norm_name = normalize_name(name)

                # Try to find SMILES
                smiles = KNOWN_ELECTROLYTE_SMILES.get(norm_name)

                # Get or create material
                material_id = self._get_or_create_material(name, smiles)
                if not material_id:
                    stats["records_skipped_invalid"] += 1
                    continue

                if material_id in self._materials:
                    stats["materials_matched"] += 1
                else:
                    stats["materials_created"] += 1
                    self._materials[material_id] = self.kg.get_molecule(material_id)

                # Parse and normalize conductivity
                multiplier, norm_unit = parse_conductivity_unit(unit)
                norm_value = float(value) * multiplier

                # Skip unreasonably high/low values
                if norm_value > 1.0 or norm_value < 1e-12:
                    stats["records_skipped_invalid"] += 1
                    continue

                # Get source for this specific paper
                paper_source = self._get_or_create_source(doi, title, journal, str(date))
                stats["unique_dois"].add(doi)

                # Create measurement
                measurement = PropertyMeasurement(
                    property_type=PropertyType.IONIC_CONDUCTIVITY,
                    value=norm_value,
                    unit=norm_unit,
                    method_id=self._method.id if self._method else None,
                )
                self.kg.add_measurement(measurement)

                # Link measurement to material
                self.kg.add_relation(
                    material_id,
                    RelationType.HAS_MEASUREMENT,
                    measurement.id,
                )

                # Add provenance linking to the specific paper DOI (not the dataset DOI)
                from ..schema.provenance import ProvenanceRecord
                prov = ProvenanceRecord(
                    entity_id=measurement.id,
                    entity_type="PropertyMeasurement",
                    source_ids=[paper_source.id],
                    source_doi=doi,  # Paper DOI, not dataset DOI
                    source_row_id=f"cde-{idx}",
                    agent_id=self._agent.id if self._agent else None,
                    extraction_method="nlp_chemdataextractor",
                    confidence=0.8,  # NLP-extracted, slightly lower confidence
                    kg_version=self.kg.version,
                )
                self.kg.add_provenance(prov)

                stats["measurements_created"] += 1
                stats["records_processed"] += 1

            except Exception as e:
                stats["errors"].append(f"Row {idx}: {str(e)}")

        stats["unique_dois"] = len(stats["unique_dois"])
        return stats

    def _get_or_create_material(self, name: str, smiles: Optional[str]) -> Optional[str]:
        """Get existing material or create new one."""
        # Try to find by SMILES first
        if smiles:
            existing_id = self.kg._find_existing_molecule_by_smiles(smiles)
            if existing_id:
                return existing_id

        # Check if we've already created this material
        norm_name = normalize_name(name)
        for mat_id, mat in self._materials.items():
            if normalize_name(mat.name) == norm_name:
                return mat_id

        # Create new material
        # Determine if it's a salt or solvent based on name
        is_salt = any(kw in norm_name for kw in [
            'li', 'na', 'salt', 'pf6', 'bf4', 'tfsi', 'fsi', 'clo4', 'triflate'
        ])

        if is_salt:
            material = Salt(
                name=name,
                smiles=smiles,
            )
            material_id = self.kg.add_salt(material)
        else:
            material = Solvent(
                name=name,
                smiles=smiles,
            )
            material_id = self.kg.add_solvent(material)

        # Add provenance for new material
        self._create_provenance(
            entity_id=material_id,
            entity_type="Salt" if is_salt else "Solvent",
            row_id=f"material-{norm_name[:30]}",
            confidence=0.9,
        )

        self._materials[material_id] = material
        return material_id
