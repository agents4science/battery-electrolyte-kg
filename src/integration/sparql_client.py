"""Base SPARQL client for querying external knowledge graphs."""

from typing import Optional, Any
from dataclasses import dataclass
import requests
import json


@dataclass
class SPARQLResult:
    """Result from a SPARQL query."""
    variables: list[str]
    bindings: list[dict[str, Any]]

    def __len__(self):
        return len(self.bindings)

    def __iter__(self):
        return iter(self.bindings)

    def to_list(self) -> list[dict]:
        """Convert to list of simple dicts."""
        results = []
        for binding in self.bindings:
            row = {}
            for var in self.variables:
                if var in binding:
                    row[var] = binding[var].get("value")
            results.append(row)
        return results


class SPARQLClient:
    """
    Generic SPARQL client for querying RDF endpoints.

    Supports:
    - SELECT queries returning tabular results
    - Standard SPARQL 1.1 syntax
    - JSON result format
    """

    def __init__(self, endpoint: str, timeout: int = 30):
        self.endpoint = endpoint
        self.timeout = timeout
        self.headers = {
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "KnowledgeGraph-Catalysis/1.0 (https://github.com/example/kg-catalysis; kg@example.com)",
        }

    def query(self, sparql: str) -> SPARQLResult:
        """
        Execute a SPARQL SELECT query.

        Args:
            sparql: SPARQL query string

        Returns:
            SPARQLResult with variables and bindings
        """
        try:
            response = requests.post(
                self.endpoint,
                data={"query": sparql},
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()

            data = response.json()

            return SPARQLResult(
                variables=data.get("head", {}).get("vars", []),
                bindings=data.get("results", {}).get("bindings", []),
            )

        except requests.exceptions.RequestException as e:
            print(f"SPARQL query failed: {e}")
            return SPARQLResult(variables=[], bindings=[])

    def ask(self, sparql: str) -> bool:
        """Execute a SPARQL ASK query."""
        try:
            response = requests.post(
                self.endpoint,
                data={"query": sparql},
                headers={"Accept": "application/sparql-results+json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json().get("boolean", False)
        except Exception:
            return False


# Pre-configured endpoints
ENDPOINTS = {
    "idsm": "https://idsm.elixir-czech.cz/sparql/endpoint/idsm",
    "wikidata": "https://query.wikidata.org/sparql",
    "pubchem": "https://idsm.elixir-czech.cz/sparql/endpoint/idsm",  # PubChem via IDSM
    "chebi": "https://idsm.elixir-czech.cz/sparql/endpoint/idsm",  # ChEBI via IDSM
}


def get_client(name: str) -> SPARQLClient:
    """Get a pre-configured SPARQL client."""
    if name not in ENDPOINTS:
        raise ValueError(f"Unknown endpoint: {name}. Available: {list(ENDPOINTS.keys())}")
    return SPARQLClient(ENDPOINTS[name])
