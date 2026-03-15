"""Wikidata integration via SPARQL endpoint."""

from typing import Optional
from dataclasses import dataclass, field

from .sparql_client import SPARQLClient, ENDPOINTS


@dataclass
class WikidataEntity:
    """Data from Wikidata for a chemical entity."""
    qid: str  # Wikidata QID (e.g., Q123)
    label: Optional[str] = None
    description: Optional[str] = None
    # Chemical identifiers
    cas_number: Optional[str] = None
    pubchem_cid: Optional[int] = None
    chebi_id: Optional[str] = None
    chembl_id: Optional[str] = None
    inchi: Optional[str] = None
    smiles: Optional[str] = None
    # Properties
    melting_point: Optional[str] = None
    boiling_point: Optional[str] = None
    density: Optional[str] = None
    # Classification
    instance_of: list[str] = field(default_factory=list)
    subclass_of: list[str] = field(default_factory=list)
    # Applications
    uses: list[str] = field(default_factory=list)
    # External links
    wikipedia_url: Optional[str] = None


class WikidataClient:
    """
    Client for querying Wikidata.

    Useful for:
    - Getting chemical classifications
    - Finding applications/uses
    - Linking to Wikipedia articles
    - Cross-referencing identifiers
    """

    ENDPOINT = ENDPOINTS["wikidata"]

    # Wikidata property IDs
    PROPS = {
        "cas": "P231",
        "pubchem_cid": "P662",
        "chebi": "P683",
        "chembl": "P592",
        "inchi": "P234",
        "smiles": "P233",
        "melting_point": "P2101",
        "boiling_point": "P2102",
        "density": "P2054",
        "instance_of": "P31",
        "subclass_of": "P279",
        "use": "P366",
    }

    def __init__(self):
        self.sparql = SPARQLClient(self.ENDPOINT, timeout=60)

    def search_by_name(self, name: str, limit: int = 5) -> list[WikidataEntity]:
        """Search Wikidata for chemical entities by name."""
        query = f"""
        SELECT DISTINCT ?item ?itemLabel ?itemDescription WHERE {{
            ?item rdfs:label "{name}"@en .
            ?item wdt:P31/wdt:P279* wd:Q11173 .  # instance of chemical compound
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        LIMIT {limit}
        """

        result = self.sparql.query(query)
        entities = []

        for binding in result.bindings:
            qid = binding.get("item", {}).get("value", "").split("/")[-1]
            entity = WikidataEntity(
                qid=qid,
                label=binding.get("itemLabel", {}).get("value"),
                description=binding.get("itemDescription", {}).get("value"),
            )
            entities.append(entity)

        return entities

    def get_by_cas(self, cas_number: str) -> Optional[WikidataEntity]:
        """Get Wikidata entity by CAS number."""
        query = f"""
        SELECT ?item ?itemLabel ?itemDescription WHERE {{
            ?item wdt:{self.PROPS['cas']} "{cas_number}" .
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        LIMIT 1
        """

        result = self.sparql.query(query)
        if not result.bindings:
            return None

        binding = result.bindings[0]
        qid = binding.get("item", {}).get("value", "").split("/")[-1]

        return self._get_full_entity(qid)

    def get_by_pubchem_cid(self, cid: int) -> Optional[WikidataEntity]:
        """Get Wikidata entity by PubChem CID."""
        query = f"""
        SELECT ?item WHERE {{
            ?item wdt:{self.PROPS['pubchem_cid']} "{cid}" .
        }}
        LIMIT 1
        """

        result = self.sparql.query(query)
        if not result.bindings:
            return None

        qid = result.bindings[0].get("item", {}).get("value", "").split("/")[-1]
        return self._get_full_entity(qid)

    def get_by_smiles(self, smiles: str) -> Optional[WikidataEntity]:
        """Get Wikidata entity by SMILES."""
        # Escape special characters in SMILES
        escaped = smiles.replace("\\", "\\\\").replace('"', '\\"')

        query = f"""
        SELECT ?item WHERE {{
            ?item wdt:{self.PROPS['smiles']} "{escaped}" .
        }}
        LIMIT 1
        """

        result = self.sparql.query(query)
        if not result.bindings:
            return None

        qid = result.bindings[0].get("item", {}).get("value", "").split("/")[-1]
        return self._get_full_entity(qid)

    def _get_full_entity(self, qid: str) -> WikidataEntity:
        """Get full entity data for a QID."""
        query = f"""
        SELECT ?itemLabel ?itemDescription
               ?cas ?pubchem ?chebi ?chembl ?inchi ?smiles
               ?melting ?boiling ?density
               ?useLabel ?instanceLabel ?subclassLabel
               ?wikipedia
        WHERE {{
            BIND(wd:{qid} AS ?item)

            OPTIONAL {{ ?item wdt:{self.PROPS['cas']} ?cas }}
            OPTIONAL {{ ?item wdt:{self.PROPS['pubchem_cid']} ?pubchem }}
            OPTIONAL {{ ?item wdt:{self.PROPS['chebi']} ?chebi }}
            OPTIONAL {{ ?item wdt:{self.PROPS['chembl']} ?chembl }}
            OPTIONAL {{ ?item wdt:{self.PROPS['inchi']} ?inchi }}
            OPTIONAL {{ ?item wdt:{self.PROPS['smiles']} ?smiles }}
            OPTIONAL {{ ?item wdt:{self.PROPS['melting_point']} ?melting }}
            OPTIONAL {{ ?item wdt:{self.PROPS['boiling_point']} ?boiling }}
            OPTIONAL {{ ?item wdt:{self.PROPS['density']} ?density }}
            OPTIONAL {{ ?item wdt:{self.PROPS['use']} ?use }}
            OPTIONAL {{ ?item wdt:{self.PROPS['instance_of']} ?instance }}
            OPTIONAL {{ ?item wdt:{self.PROPS['subclass_of']} ?subclass }}
            OPTIONAL {{
                ?wikipedia schema:about ?item .
                ?wikipedia schema:isPartOf <https://en.wikipedia.org/> .
            }}

            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        """

        result = self.sparql.query(query)

        entity = WikidataEntity(qid=qid)

        uses = set()
        instances = set()
        subclasses = set()

        for binding in result.bindings:
            if not entity.label:
                entity.label = binding.get("itemLabel", {}).get("value")
            if not entity.description:
                entity.description = binding.get("itemDescription", {}).get("value")
            if not entity.cas_number:
                entity.cas_number = binding.get("cas", {}).get("value")
            if not entity.pubchem_cid:
                val = binding.get("pubchem", {}).get("value")
                if val:
                    entity.pubchem_cid = int(val)
            if not entity.chebi_id:
                entity.chebi_id = binding.get("chebi", {}).get("value")
            if not entity.chembl_id:
                entity.chembl_id = binding.get("chembl", {}).get("value")
            if not entity.inchi:
                entity.inchi = binding.get("inchi", {}).get("value")
            if not entity.smiles:
                entity.smiles = binding.get("smiles", {}).get("value")
            if not entity.melting_point:
                entity.melting_point = binding.get("melting", {}).get("value")
            if not entity.boiling_point:
                entity.boiling_point = binding.get("boiling", {}).get("value")
            if not entity.density:
                entity.density = binding.get("density", {}).get("value")
            if not entity.wikipedia_url:
                entity.wikipedia_url = binding.get("wikipedia", {}).get("value")

            use_label = binding.get("useLabel", {}).get("value")
            if use_label:
                uses.add(use_label)

            instance_label = binding.get("instanceLabel", {}).get("value")
            if instance_label:
                instances.add(instance_label)

            subclass_label = binding.get("subclassLabel", {}).get("value")
            if subclass_label:
                subclasses.add(subclass_label)

        entity.uses = list(uses)
        entity.instance_of = list(instances)
        entity.subclass_of = list(subclasses)

        return entity

    def get_battery_electrolyte_compounds(self, limit: int = 50) -> list[WikidataEntity]:
        """Find compounds used as battery electrolytes."""
        query = f"""
        SELECT DISTINCT ?item ?itemLabel ?itemDescription WHERE {{
            # Items used in batteries or as electrolytes
            {{ ?item wdt:P366 wd:Q267298 }}  # use: electrolyte
            UNION
            {{ ?item wdt:P366 wd:Q267291 }}  # use: battery
            UNION
            {{ ?item wdt:P31 wd:Q188749 }}   # instance of: electrolyte

            # Must be a chemical compound
            ?item wdt:P31/wdt:P279* wd:Q11173 .

            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        LIMIT {limit}
        """

        result = self.sparql.query(query)
        entities = []

        for binding in result.bindings:
            qid = binding.get("item", {}).get("value", "").split("/")[-1]
            entity = WikidataEntity(
                qid=qid,
                label=binding.get("itemLabel", {}).get("value"),
                description=binding.get("itemDescription", {}).get("value"),
            )
            entities.append(entity)

        return entities
