"""PubChem integration via IDSM SPARQL endpoint and REST API."""

from typing import Optional
from dataclasses import dataclass, field
import requests

from .sparql_client import SPARQLClient, ENDPOINTS


@dataclass
class PubChemCompound:
    """Data from PubChem for a compound."""
    cid: int
    name: Optional[str] = None
    iupac_name: Optional[str] = None
    smiles: Optional[str] = None
    inchi: Optional[str] = None
    inchi_key: Optional[str] = None
    molecular_formula: Optional[str] = None
    molecular_weight: Optional[float] = None
    synonyms: list[str] = field(default_factory=list)
    # Safety/hazard info
    ghs_hazards: list[str] = field(default_factory=list)
    # Physical properties
    boiling_point: Optional[str] = None
    melting_point: Optional[str] = None
    density: Optional[str] = None
    # Links
    chebi_id: Optional[str] = None
    chembl_id: Optional[str] = None


class PubChemClient:
    """
    Client for querying PubChem data.

    Uses:
    - IDSM SPARQL endpoint for linked data queries
    - PubChem REST API for detailed compound info
    """

    SPARQL_ENDPOINT = ENDPOINTS["idsm"]
    REST_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

    # SPARQL prefixes for PubChem queries
    PREFIXES = """
    PREFIX compound: <http://rdf.ncbi.nlm.nih.gov/pubchem/compound/>
    PREFIX sio: <http://semanticscience.org/resource/>
    PREFIX obo: <http://purl.obolibrary.org/obo/>
    PREFIX dcterms: <http://purl.org/dc/terms/>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX chebi: <http://purl.obolibrary.org/obo/chebi/>
    """

    def __init__(self):
        self.sparql = SPARQLClient(self.SPARQL_ENDPOINT, timeout=60)

    def get_compound_by_cid(self, cid: int) -> Optional[PubChemCompound]:
        """Get compound data by PubChem CID using REST API."""
        try:
            # Get basic properties
            url = f"{self.REST_BASE}/compound/cid/{cid}/property/MolecularFormula,MolecularWeight,CanonicalSMILES,InChI,InChIKey,IUPACName/JSON"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            props = data.get("PropertyTable", {}).get("Properties", [{}])[0]

            compound = PubChemCompound(
                cid=cid,
                iupac_name=props.get("IUPACName"),
                smiles=props.get("CanonicalSMILES"),
                inchi=props.get("InChI"),
                inchi_key=props.get("InChIKey"),
                molecular_formula=props.get("MolecularFormula"),
                molecular_weight=props.get("MolecularWeight"),
            )

            # Get synonyms
            syn_url = f"{self.REST_BASE}/compound/cid/{cid}/synonyms/JSON"
            syn_response = requests.get(syn_url, timeout=30)
            if syn_response.ok:
                syn_data = syn_response.json()
                synonyms = syn_data.get("InformationList", {}).get("Information", [{}])[0].get("Synonym", [])
                compound.synonyms = synonyms[:20]  # Limit to 20
                if synonyms:
                    compound.name = synonyms[0]

            return compound

        except Exception as e:
            print(f"PubChem REST API error for CID {cid}: {e}")
            return None

    def search_by_name(self, name: str) -> list[PubChemCompound]:
        """Search PubChem by compound name."""
        try:
            url = f"{self.REST_BASE}/compound/name/{requests.utils.quote(name)}/cids/JSON"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            cids = data.get("IdentifierList", {}).get("CID", [])[:5]  # Top 5

            compounds = []
            for cid in cids:
                compound = self.get_compound_by_cid(cid)
                if compound:
                    compounds.append(compound)

            return compounds

        except Exception as e:
            print(f"PubChem search error for '{name}': {e}")
            return []

    def search_by_smiles(self, smiles: str) -> Optional[PubChemCompound]:
        """Search PubChem by SMILES string."""
        try:
            url = f"{self.REST_BASE}/compound/smiles/{requests.utils.quote(smiles)}/cids/JSON"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            cids = data.get("IdentifierList", {}).get("CID", [])
            if cids:
                return self.get_compound_by_cid(cids[0])

            return None

        except Exception as e:
            print(f"PubChem SMILES search error: {e}")
            return None

    def get_chebi_mapping(self, cid: int) -> Optional[str]:
        """Get ChEBI ID for a PubChem compound via SPARQL."""
        query = f"""
        {self.PREFIXES}

        SELECT ?chebi WHERE {{
            ?compound a sio:CHEMINF_000043 .
            ?compound sio:SIO_000011 ?chebi .
            ?chebi a obo:CHEBI_24431 .
            FILTER(CONTAINS(STR(?compound), "{cid}"))
        }}
        LIMIT 1
        """

        result = self.sparql.query(query)
        if result.bindings:
            chebi_uri = result.bindings[0].get("chebi", {}).get("value", "")
            if "CHEBI_" in chebi_uri:
                return chebi_uri.split("CHEBI_")[-1]
        return None

    def get_related_compounds(self, cid: int, relation: str = "similar") -> list[int]:
        """
        Get related compounds from PubChem.

        Args:
            cid: PubChem CID
            relation: "similar", "parent", "component", etc.
        """
        try:
            url = f"{self.REST_BASE}/compound/cid/{cid}/cids/JSON?cids_type={relation}_2d"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            return data.get("IdentifierList", {}).get("CID", [])[:10]

        except Exception:
            return []

    def get_safety_info(self, cid: int) -> dict:
        """Get GHS safety information for a compound."""
        try:
            url = f"{self.REST_BASE}/compound/cid/{cid}/property/GHSHazardStatements/JSON"
            response = requests.get(url, timeout=30)

            if response.ok:
                data = response.json()
                props = data.get("PropertyTable", {}).get("Properties", [{}])[0]
                return {"ghs_hazards": props.get("GHSHazardStatements", [])}

            return {}

        except Exception:
            return {}
