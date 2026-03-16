"""Entity type definitions for the electrolyte KG."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


def generate_id() -> str:
    """Generate a unique identifier."""
    return str(uuid.uuid4())


class ComponentType(str, Enum):
    """Types of electrolyte components."""
    SOLVENT = "solvent"
    SALT = "salt"
    ADDITIVE = "additive"


class AmountUnit(str, Enum):
    """Units for component amounts."""
    MOLARITY = "M"  # mol/L
    MOLALITY = "m"  # mol/kg
    MASS_FRACTION = "mass_fraction"
    VOLUME_FRACTION = "volume_fraction"
    WEIGHT_FRACTION = "weight_fraction"  # For CALiSol-23 ratios
    WEIGHT_PERCENT = "wt%"
    GRAMS = "g"
    MILLIGRAMS = "mg"


class PropertyType(str, Enum):
    """Types of measured properties."""
    IONIC_CONDUCTIVITY = "ionic_conductivity"  # S/cm
    ACTIVATION_ENERGY = "activation_energy"  # eV or kJ/mol
    RESISTANCE = "resistance"  # Ohm
    VISCOSITY = "viscosity"  # cP or mPa·s
    DENSITY = "density"  # g/cm³
    ELECTROCHEMICAL_WINDOW = "electrochemical_window"  # V
    # Electrolyte Genome / Materials Project properties
    IONIZATION_ENERGY = "ionization_energy"  # eV
    ELECTRON_AFFINITY = "electron_affinity"  # eV
    OXIDATION_POTENTIAL_LI = "oxidation_potential_li"  # V vs Li/Li+
    REDUCTION_POTENTIAL_LI = "reduction_potential_li"  # V vs Li/Li+
    OXIDATION_POTENTIAL_MG = "oxidation_potential_mg"  # V vs Mg/Mg2+
    REDUCTION_POTENTIAL_MG = "reduction_potential_mg"  # V vs Mg/Mg2+
    OXIDATION_POTENTIAL_H = "oxidation_potential_h"  # V vs H+/H2
    REDUCTION_POTENTIAL_H = "reduction_potential_h"  # V vs H+/H2
    # Curated solvent properties
    HOMO_ENERGY = "homo_energy"  # eV
    LUMO_ENERGY = "lumo_energy"  # eV
    DIELECTRIC_CONSTANT = "dielectric_constant"  # dimensionless
    THERMAL_STABILITY = "thermal_stability"  # C (decomposition temp)
    LATTICE_ENERGY = "lattice_energy"  # kJ/mol
    OXIDATION_STABILITY = "oxidation_stability"  # V vs Li/Li+
    # Battery performance metrics
    COULOMBIC_EFFICIENCY = "coulombic_efficiency"  # dimensionless (0-1)

    @property
    def entity_id(self) -> str:
        """Get deterministic entity ID for this property type."""
        return f"property_type:{self.value}"


class PropertyTypeEntity(BaseModel):
    """Property type as a KG entity for grounding hypotheses."""
    id: str
    name: str
    description: Optional[str] = None
    unit: Optional[str] = None

    @classmethod
    def from_enum(cls, prop_type: PropertyType) -> "PropertyTypeEntity":
        """Create entity from PropertyType enum."""
        descriptions = {
            PropertyType.IONIC_CONDUCTIVITY: "Measure of ion transport capability",
            PropertyType.ACTIVATION_ENERGY: "Energy barrier for ionic conduction",
            PropertyType.RESISTANCE: "Electrical resistance of electrolyte",
            PropertyType.VISCOSITY: "Resistance to flow",
            PropertyType.DENSITY: "Mass per unit volume",
            PropertyType.ELECTROCHEMICAL_WINDOW: "Stable voltage range",
            PropertyType.IONIZATION_ENERGY: "Energy to remove electron (vertical IE)",
            PropertyType.ELECTRON_AFFINITY: "Energy released when adding electron (vertical EA)",
            PropertyType.OXIDATION_POTENTIAL_LI: "Oxidation potential vs Li/Li+ reference",
            PropertyType.REDUCTION_POTENTIAL_LI: "Reduction potential vs Li/Li+ reference",
            PropertyType.OXIDATION_POTENTIAL_MG: "Oxidation potential vs Mg/Mg2+ reference",
            PropertyType.REDUCTION_POTENTIAL_MG: "Reduction potential vs Mg/Mg2+ reference",
            PropertyType.OXIDATION_POTENTIAL_H: "Oxidation potential vs H+/H2 reference",
            PropertyType.REDUCTION_POTENTIAL_H: "Reduction potential vs H+/H2 reference",
            PropertyType.HOMO_ENERGY: "Highest occupied molecular orbital energy",
            PropertyType.LUMO_ENERGY: "Lowest unoccupied molecular orbital energy",
            PropertyType.DIELECTRIC_CONSTANT: "Relative permittivity of solvent",
            PropertyType.THERMAL_STABILITY: "Thermal decomposition temperature",
            PropertyType.LATTICE_ENERGY: "Energy to separate salt into ions",
            PropertyType.OXIDATION_STABILITY: "Voltage at which oxidation begins",
            PropertyType.COULOMBIC_EFFICIENCY: "Ratio of discharge to charge capacity",
        }
        units = {
            PropertyType.IONIC_CONDUCTIVITY: "S/cm",
            PropertyType.ACTIVATION_ENERGY: "eV",
            PropertyType.RESISTANCE: "Ohm",
            PropertyType.VISCOSITY: "cP",
            PropertyType.DENSITY: "g/cm³",
            PropertyType.ELECTROCHEMICAL_WINDOW: "V",
            PropertyType.IONIZATION_ENERGY: "eV",
            PropertyType.ELECTRON_AFFINITY: "eV",
            PropertyType.OXIDATION_POTENTIAL_LI: "V",
            PropertyType.REDUCTION_POTENTIAL_LI: "V",
            PropertyType.OXIDATION_POTENTIAL_MG: "V",
            PropertyType.REDUCTION_POTENTIAL_MG: "V",
            PropertyType.OXIDATION_POTENTIAL_H: "V",
            PropertyType.REDUCTION_POTENTIAL_H: "V",
            PropertyType.HOMO_ENERGY: "eV",
            PropertyType.LUMO_ENERGY: "eV",
            PropertyType.DIELECTRIC_CONSTANT: "dimensionless",
            PropertyType.THERMAL_STABILITY: "C",
            PropertyType.LATTICE_ENERGY: "kJ/mol",
            PropertyType.OXIDATION_STABILITY: "V",
            PropertyType.COULOMBIC_EFFICIENCY: "dimensionless",
        }
        return cls(
            id=prop_type.entity_id,
            name=prop_type.value.replace("_", " ").title(),
            description=descriptions.get(prop_type),
            unit=units.get(prop_type),
        )


class Molecule(BaseModel):
    """Canonical chemical identity."""
    id: str = Field(default_factory=generate_id)
    name: str
    smiles: Optional[str] = None
    inchi: Optional[str] = None
    inchi_key: Optional[str] = None
    pubchem_cid: Optional[int] = None
    cas_number: Optional[str] = None
    molecular_weight: Optional[float] = None  # g/mol
    synonyms: list[str] = Field(default_factory=list)

    def __hash__(self):
        return hash(self.id)


class Solvent(Molecule):
    """Solvent molecule (e.g., EC, PC, EMC, DMC)."""
    component_type: ComponentType = ComponentType.SOLVENT
    boiling_point: Optional[float] = None  # °C
    melting_point: Optional[float] = None  # °C
    dielectric_constant: Optional[float] = None


class Salt(Molecule):
    """Salt molecule (e.g., LiPF₆, LiTFSI)."""
    component_type: ComponentType = ComponentType.SALT
    cation: Optional[str] = None
    anion: Optional[str] = None


class Additive(Molecule):
    """Additive molecule (e.g., VC, FEC)."""
    component_type: ComponentType = ComponentType.ADDITIVE
    additive_function: Optional[str] = None  # e.g., "SEI former", "flame retardant"


class FormulationComponent(BaseModel):
    """A component within a formulation with its amount."""
    id: str = Field(default_factory=generate_id)
    molecule_id: str
    component_type: ComponentType
    amount: float
    unit: AmountUnit

    def __hash__(self):
        return hash(self.id)


class MeasurementMethod(BaseModel):
    """Method used for property measurement."""
    id: str = Field(default_factory=generate_id)
    name: str  # e.g., "EIS", "Arrhenius fit"
    description: Optional[str] = None
    equipment: Optional[str] = None
    parameters: dict = Field(default_factory=dict)  # e.g., frequency range, temperature


class PropertyMeasurement(BaseModel):
    """A measured property value."""
    id: str = Field(default_factory=generate_id)
    property_type: PropertyType
    value: float
    unit: str
    uncertainty: Optional[float] = None
    temperature: Optional[float] = None  # °C or K
    temperature_unit: str = "C"
    method_id: Optional[str] = None
    measurement_date: Optional[datetime] = None
    raw_data_reference: Optional[str] = None  # pointer to raw data (e.g., EIS spectra)

    def __hash__(self):
        return hash(self.id)


class ElectrolyteFormulation(BaseModel):
    """An electrolyte formulation (composition)."""
    id: str = Field(default_factory=generate_id)
    name: Optional[str] = None
    components: list[FormulationComponent] = Field(default_factory=list)
    measurements: list[str] = Field(default_factory=list)  # measurement IDs
    source_id: Optional[str] = None  # evidence source ID
    batch_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def __hash__(self):
        return hash(self.id)

    def get_component_by_type(self, comp_type: ComponentType) -> list[FormulationComponent]:
        """Get all components of a specific type."""
        return [c for c in self.components if c.component_type == comp_type]


class InterphaseSpecies(BaseModel):
    """SEI/interphase species (from LIBE or similar)."""
    id: str = Field(default_factory=generate_id)
    name: str
    smiles: Optional[str] = None
    inchi: Optional[str] = None
    formula: Optional[str] = None
    charge: int = 0
    spin_multiplicity: int = 1
    # DFT-computed properties
    energy: Optional[float] = None  # eV
    enthalpy: Optional[float] = None  # kJ/mol
    entropy: Optional[float] = None  # J/mol·K
    free_energy: Optional[float] = None  # kJ/mol
    # Source
    source_dataset: Optional[str] = None  # e.g., "LIBE"

    def __hash__(self):
        return hash(self.id)


class EvidenceSource(BaseModel):
    """Source of evidence (dataset, paper, patent)."""
    id: str = Field(default_factory=generate_id)
    source_type: str  # "dataset", "paper", "patent"
    name: str
    doi: Optional[str] = None
    patent_id: Optional[str] = None
    url: Optional[str] = None
    publication_date: Optional[datetime] = None
    authors: list[str] = Field(default_factory=list)
    license: Optional[str] = None

    def __hash__(self):
        return hash(self.id)
