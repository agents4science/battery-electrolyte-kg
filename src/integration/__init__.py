"""External Knowledge Graph integration."""

from .sparql_client import SPARQLClient
from .pubchem import PubChemClient
from .wikidata import WikidataClient
from .enrichment import MoleculeEnricher
from .materials_project import MaterialsProjectClient, ElectrolyteGenomeMolecule

__all__ = [
    "SPARQLClient",
    "PubChemClient",
    "WikidataClient",
    "MoleculeEnricher",
    "MaterialsProjectClient",
    "ElectrolyteGenomeMolecule",
]
