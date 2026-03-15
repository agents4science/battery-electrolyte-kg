"""Ingestor for curated solvent electrochemical properties."""

from pathlib import Path
from datetime import datetime
from typing import Optional
import json

from .base import BaseIngestor
from ..kg_store.graph import KnowledgeGraph
from ..schema.entities import (
    Molecule, Solvent, Salt, PropertyMeasurement, MeasurementMethod,
    PropertyType,
)
from ..schema.relations import RelationType


# Mapping from JSON property names to PropertyType enum
PROPERTY_MAP = {
    "ionization_energy": PropertyType.IONIZATION_ENERGY,
    "electron_affinity": PropertyType.ELECTRON_AFFINITY,
    "homo_energy": PropertyType.HOMO_ENERGY,
    "lumo_energy": PropertyType.LUMO_ENERGY,
    "oxidation_potential": PropertyType.OXIDATION_POTENTIAL_LI,
    "reduction_potential": PropertyType.REDUCTION_POTENTIAL_LI,
    "dielectric_constant": PropertyType.DIELECTRIC_CONSTANT,
    "thermal_stability": PropertyType.THERMAL_STABILITY,
    "lattice_energy": PropertyType.LATTICE_ENERGY,
    "oxidation_stability": PropertyType.OXIDATION_STABILITY,
}


class CuratedPropertiesIngestor(BaseIngestor):
    """
    Ingestor for curated solvent electrochemical properties.

    This ingestor:
    1. Loads curated property data from JSON
    2. Matches molecules to existing KG entries by SMILES
    3. Adds property measurements
    4. Creates SAME_AS relations for matched molecules
    """

    def __init__(self, kg: KnowledgeGraph):
        super().__init__(kg, "Curated Electrochemical Properties")
        self._method: Optional[MeasurementMethod] = None
        self._smiles_to_molecule: dict[str, str] = {}  # SMILES -> molecule_id

    def download(self, output_dir: Path) -> Path:
        """No download needed - data is curated locally."""
        output_path = output_dir / "solvent_electrochemical_properties.json"
        if not output_path.exists():
            raise FileNotFoundError(
                f"Curated properties file not found at {output_path}"
            )
        return output_path

    def ingest(self, data_path: Path) -> dict:
        """Ingest curated electrochemical properties."""
        # Set up provenance
        self._create_agent()
        self._create_source(
            source_type="curation",
            doi=None,
            url=None,
            authors=["Literature compilation"],
            publication_date=datetime(2024, 7, 15),
            license="CC BY 4.0",
        )

        # Create measurement method
        self._method = MeasurementMethod(
            name="Literature-DFT",
            description="DFT computed properties from literature",
            parameters={
                "level": "B3LYP/6-31+G(d) typical",
                "source": "Multiple publications",
            },
        )
        self.kg.add_method(self._method)

        # Build SMILES index from existing KG molecules
        self._build_smiles_index()

        # Load curated data
        with open(data_path) as f:
            data = json.load(f)

        stats = {
            "solvents_matched": 0,
            "solvents_created": 0,
            "salts_matched": 0,
            "salts_created": 0,
            "measurements_created": 0,
            "same_as_relations": 0,
            "errors": [],
        }

        # Process solvents
        for solvent_data in data.get("solvents", []):
            try:
                result = self._process_solvent(solvent_data)
                stats["solvents_matched"] += result.get("matched", 0)
                stats["solvents_created"] += result.get("created", 0)
                stats["measurements_created"] += result.get("measurements", 0)
                stats["same_as_relations"] += result.get("same_as", 0)
            except Exception as e:
                stats["errors"].append(f"Solvent {solvent_data.get('name')}: {e}")

        # Process salts
        for salt_data in data.get("salts", []):
            try:
                result = self._process_salt(salt_data)
                stats["salts_matched"] += result.get("matched", 0)
                stats["salts_created"] += result.get("created", 0)
                stats["measurements_created"] += result.get("measurements", 0)
                stats["same_as_relations"] += result.get("same_as", 0)
            except Exception as e:
                stats["errors"].append(f"Salt {salt_data.get('name')}: {e}")

        return stats

    def _build_smiles_index(self) -> None:
        """Build index of SMILES to molecule IDs from existing KG."""
        # Index all molecules (using private attributes)
        for mol_id, mol in self.kg._molecules.items():
            smiles = mol.smiles
            if smiles:
                # Normalize SMILES (basic - remove whitespace)
                normalized = smiles.strip()
                self._smiles_to_molecule[normalized] = mol_id

        # Also index solvents (which are also molecules but separate dict)
        for sol_id, sol in self.kg._solvents.items():
            smiles = sol.smiles
            if smiles:
                normalized = smiles.strip()
                self._smiles_to_molecule[normalized] = sol_id

        # And salts
        for salt_id, salt in self.kg._salts.items():
            smiles = salt.smiles
            if smiles:
                normalized = smiles.strip()
                self._smiles_to_molecule[normalized] = salt_id

        print(f"Built SMILES index with {len(self._smiles_to_molecule)} entries")

    def _find_molecule_by_smiles(self, smiles: str) -> Optional[str]:
        """Find existing molecule by SMILES."""
        if not smiles:
            return None

        normalized = smiles.strip()

        # Try exact match
        if normalized in self._smiles_to_molecule:
            return self._smiles_to_molecule[normalized]

        # Try some common SMILES variations
        variations = [
            normalized,
            normalized.replace("=", ""),  # Remove explicit double bonds
        ]

        for var in variations:
            if var in self._smiles_to_molecule:
                return self._smiles_to_molecule[var]

        return None

    def _process_solvent(self, data: dict) -> dict:
        """Process a solvent entry."""
        result = {"matched": 0, "created": 0, "measurements": 0, "same_as": 0}

        smiles = data.get("smiles", "")
        name = data.get("name", "")
        abbrev = data.get("abbreviation", "")

        # Try to find existing molecule
        existing_id = self._find_molecule_by_smiles(smiles)

        if existing_id:
            molecule_id = existing_id
            result["matched"] = 1
        else:
            # Create new solvent
            solvent = Solvent(
                name=name,
                smiles=smiles,
                cas_number=data.get("cas_number"),
                pubchem_cid=data.get("pubchem_cid"),
                molecular_weight=data.get("molecular_weight"),
                synonyms=[abbrev] if abbrev else [],
            )
            self.kg.add_solvent(solvent)
            molecule_id = solvent.id
            result["created"] = 1

            # Add provenance
            self._create_provenance(
                entity_id=solvent.id,
                entity_type="Solvent",
                row_id=f"curated-{abbrev}",
                confidence=1.0,
            )

        # Add property measurements
        properties = data.get("properties", {})
        for prop_name, prop_data in properties.items():
            prop_type = PROPERTY_MAP.get(prop_name)
            if not prop_type:
                continue

            value = prop_data.get("value")
            if value is None:
                continue

            measurement = PropertyMeasurement(
                property_type=prop_type,
                value=float(value),
                unit=prop_data.get("unit", ""),
                method_id=self._method.id if self._method else None,
                notes=prop_data.get("reference"),
            )
            self.kg.add_measurement(measurement)

            # Link to molecule
            self.kg.add_relation(
                molecule_id,
                RelationType.HAS_MEASUREMENT,
                measurement.id,
            )

            # Link to property type
            self.kg.add_relation(
                measurement.id,
                RelationType.MEASURES_PROPERTY,
                prop_type.entity_id,
            )

            result["measurements"] += 1

        # Create SAME_AS relations to other molecules with same SMILES
        same_as_count = self._create_same_as_relations(molecule_id, smiles)
        result["same_as"] = same_as_count

        return result

    def _process_salt(self, data: dict) -> dict:
        """Process a salt entry."""
        result = {"matched": 0, "created": 0, "measurements": 0, "same_as": 0}

        smiles = data.get("smiles", "")
        name = data.get("name", "")
        abbrev = data.get("abbreviation", "")

        # Try to find existing molecule
        existing_id = self._find_molecule_by_smiles(smiles)

        if existing_id:
            molecule_id = existing_id
            result["matched"] = 1
        else:
            # Create new salt
            salt = Salt(
                name=name,
                smiles=smiles,
                cas_number=data.get("cas_number"),
                pubchem_cid=data.get("pubchem_cid"),
                molecular_weight=data.get("molecular_weight"),
                cation=data.get("cation"),
                anion=data.get("anion"),
                synonyms=[abbrev] if abbrev else [],
            )
            self.kg.add_salt(salt)
            molecule_id = salt.id
            result["created"] = 1

            # Add provenance
            self._create_provenance(
                entity_id=salt.id,
                entity_type="Salt",
                row_id=f"curated-{abbrev}",
                confidence=1.0,
            )

        # Add property measurements
        properties = data.get("properties", {})
        for prop_name, prop_data in properties.items():
            prop_type = PROPERTY_MAP.get(prop_name)
            if not prop_type:
                continue

            value = prop_data.get("value")
            if value is None:
                continue

            measurement = PropertyMeasurement(
                property_type=prop_type,
                value=float(value),
                unit=prop_data.get("unit", ""),
                method_id=self._method.id if self._method else None,
                notes=prop_data.get("reference"),
            )
            self.kg.add_measurement(measurement)

            # Link to molecule
            self.kg.add_relation(
                molecule_id,
                RelationType.HAS_MEASUREMENT,
                measurement.id,
            )

            # Link to property type
            self.kg.add_relation(
                measurement.id,
                RelationType.MEASURES_PROPERTY,
                prop_type.entity_id,
            )

            result["measurements"] += 1

        # Create SAME_AS relations
        same_as_count = self._create_same_as_relations(molecule_id, smiles)
        result["same_as"] = same_as_count

        return result

    def _create_same_as_relations(self, molecule_id: str, smiles: str) -> int:
        """Create SAME_AS relations to other molecules with matching SMILES."""
        count = 0
        normalized = smiles.strip()

        # Find all molecules with same SMILES
        for mol_id, mol in self.kg._molecules.items():
            if mol_id == molecule_id:
                continue
            if mol.smiles and mol.smiles.strip() == normalized:
                # Create bidirectional SAME_AS
                self.kg.add_relation(molecule_id, RelationType.SAME_AS, mol_id)
                self.kg.add_relation(mol_id, RelationType.SAME_AS, molecule_id)
                count += 1

        return count
