"""Materials Project Electrolyte Genome integration."""

from typing import Optional
from dataclasses import dataclass, field
import os


@dataclass
class ElectrolyteGenomeMolecule:
    """Molecule data from Electrolyte Genome."""
    task_id: str
    smiles: str
    formula: Optional[str] = None
    charge: int = 0
    molecular_weight: Optional[float] = None
    point_group: Optional[str] = None
    # Electrochemical properties
    ionization_energy: Optional[float] = None  # eV
    electron_affinity: Optional[float] = None  # eV
    # Redox potentials (V vs reference electrode)
    oxidation_potential_li: Optional[float] = None
    reduction_potential_li: Optional[float] = None
    oxidation_potential_mg: Optional[float] = None
    reduction_potential_mg: Optional[float] = None
    oxidation_potential_h: Optional[float] = None
    reduction_potential_h: Optional[float] = None
    # Metadata
    functional_groups: list[str] = field(default_factory=list)
    base_molecule: Optional[str] = None


class MaterialsProjectClient:
    """
    Client for Materials Project Electrolyte Genome API.

    Accesses the JCESR Electrolyte Genome dataset containing ~22,000 molecules
    with computed electrochemical properties relevant to battery electrolytes.

    Requires MP_API_KEY environment variable or api_key parameter.
    Get your API key at: https://materialsproject.org/api
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize client.

        Args:
            api_key: Materials Project API key (or set MP_API_KEY env var)
        """
        self.api_key = api_key or os.environ.get("MP_API_KEY")
        self._mprester = None

    def _get_mprester(self):
        """Get or create MPRester instance."""
        if self._mprester is None:
            try:
                from mp_api.client import MPRester
                self._mprester = MPRester(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "mp-api package required. Install with: pip install mp-api"
                )
        return self._mprester

    def check_api_key(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    def search_jcesr(
        self,
        charge: int = 0,
        elements: Optional[list[str]] = None,
        limit: int = 1000,
    ) -> list[ElectrolyteGenomeMolecule]:
        """
        Search JCESR Electrolyte Genome.

        Args:
            charge: Molecular charge filter (0 for neutral)
            elements: List of elements to filter by
            limit: Maximum molecules to return

        Returns:
            List of ElectrolyteGenomeMolecule objects
        """
        if not self.api_key:
            raise ValueError(
                "Materials Project API key required. "
                "Set MP_API_KEY environment variable or pass api_key parameter. "
                "Get your key at: https://materialsproject.org/api"
            )

        mpr = self._get_mprester()

        molecules = []
        try:
            # Calculate chunks needed
            chunk_size = min(100, limit)
            num_chunks = (limit + chunk_size - 1) // chunk_size

            docs = mpr.molecules.jcesr.search(
                charge=charge,
                elements=elements,
                num_chunks=num_chunks,
                chunk_size=chunk_size,
            )

            count = 0
            for doc in docs:
                if count >= limit:
                    break
                mol = self._parse_jcesr_doc(doc)
                if mol:
                    molecules.append(mol)
                    count += 1

        except Exception as e:
            print(f"JCESR API error: {e}")
            raise

        return molecules

    def get_electrolyte_molecules(
        self,
        max_molecules: int = 1000,
    ) -> list[ElectrolyteGenomeMolecule]:
        """
        Get molecules relevant to battery electrolytes.

        Fetches neutral molecules from the JCESR dataset.

        Args:
            max_molecules: Maximum molecules to fetch

        Returns:
            List of ElectrolyteGenomeMolecule objects
        """
        return self.search_jcesr(charge=0, limit=max_molecules)

    def get_molecule_count(self) -> int:
        """Get total count of molecules in JCESR dataset."""
        if not self.api_key:
            raise ValueError("API key required")

        mpr = self._get_mprester()
        try:
            return mpr.molecules.jcesr.count()
        except Exception as e:
            print(f"Error getting count: {e}")
            return 0

    def _parse_jcesr_doc(self, doc) -> Optional[ElectrolyteGenomeMolecule]:
        """Parse a JCESR document into ElectrolyteGenomeMolecule."""
        try:
            # Get molecule ID
            mol_id = ""
            if hasattr(doc, "molecule_id"):
                mol_id = str(doc.molecule_id)
            elif hasattr(doc, "task_id"):
                mol_id = str(doc.task_id)

            # Get SMILES
            smiles = getattr(doc, "smiles", "") or ""
            if not smiles:
                return None

            return ElectrolyteGenomeMolecule(
                task_id=mol_id,
                smiles=smiles,
                formula=getattr(doc, "formula", None),
                charge=getattr(doc, "charge", 0) or 0,
                molecular_weight=getattr(doc, "molecular_weight", None),
                point_group=getattr(doc, "point_group", None),
                ionization_energy=getattr(doc, "IE", None),
                electron_affinity=getattr(doc, "EA", None),
                oxidation_potential_li=self._get_redox(doc, "oxidation", "Li"),
                reduction_potential_li=self._get_redox(doc, "reduction", "Li"),
                oxidation_potential_mg=self._get_redox(doc, "oxidation", "Mg"),
                reduction_potential_mg=self._get_redox(doc, "reduction", "Mg"),
                oxidation_potential_h=self._get_redox(doc, "oxidation", "H"),
                reduction_potential_h=self._get_redox(doc, "reduction", "H"),
                functional_groups=list(getattr(doc, "functional_groups", []) or []),
            )
        except Exception as e:
            print(f"Error parsing JCESR doc: {e}")
            return None

    def _get_redox(self, doc, redox_type: str, electrode: str) -> Optional[float]:
        """Extract redox potential from document."""
        # Try different attribute patterns based on mp-api schema
        patterns = [
            f"{redox_type}_{electrode.lower()}",
            f"{electrode.lower()}_{redox_type}",
            f"{redox_type}_potential_{electrode.lower()}",
        ]
        for pattern in patterns:
            val = getattr(doc, pattern, None)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
        return None
