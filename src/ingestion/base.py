"""Base class for data ingestors."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from datetime import datetime

from ..kg_store.graph import KnowledgeGraph
from ..schema.provenance import Agent, AgentType, ProvenanceRecord, ProvenanceActivity, ActivityType
from ..schema.entities import EvidenceSource


class BaseIngestor(ABC):
    """Base class for data ingestors."""

    def __init__(self, kg: KnowledgeGraph, source_name: str):
        self.kg = kg
        self.source_name = source_name
        self._agent: Optional[Agent] = None
        self._source: Optional[EvidenceSource] = None

    def _create_agent(self, version: str = "1.0.0") -> Agent:
        """Create an agent for this ingestor."""
        agent = Agent(
            name=f"{self.__class__.__name__}",
            agent_type=AgentType.SOFTWARE,
            version=version,
            description=f"Automated ingestor for {self.source_name}",
        )
        self.kg.add_agent(agent)
        self._agent = agent
        return agent

    def _create_source(
        self,
        source_type: str,
        doi: Optional[str] = None,
        url: Optional[str] = None,
        authors: Optional[list[str]] = None,
        publication_date: Optional[datetime] = None,
        license: Optional[str] = None,
    ) -> EvidenceSource:
        """Create an evidence source."""
        source = EvidenceSource(
            source_type=source_type,
            name=self.source_name,
            doi=doi,
            url=url,
            authors=authors or [],
            publication_date=publication_date,
            license=license,
        )
        self.kg.add_source(source)
        self._source = source
        return source

    def _create_provenance(
        self,
        entity_id: str,
        entity_type: str,
        row_id: Optional[str] = None,
        confidence: float = 1.0,
    ) -> ProvenanceRecord:
        """Create a provenance record for an ingested entity."""
        prov = ProvenanceRecord(
            entity_id=entity_id,
            entity_type=entity_type,
            source_ids=[self._source.id] if self._source else [],
            source_doi=self._source.doi if self._source else None,
            source_row_id=row_id,
            agent_id=self._agent.id if self._agent else None,
            extraction_method="structured_ingestion",
            confidence=confidence,
            kg_version=self.kg.version,
        )
        self.kg.add_provenance(prov)
        return prov

    @abstractmethod
    def ingest(self, data_path: Path) -> dict:
        """
        Ingest data from a file into the knowledge graph.

        Returns a summary dict with ingestion statistics.
        """
        pass

    @abstractmethod
    def download(self, output_dir: Path) -> Path:
        """
        Download the dataset to a local directory.

        Returns the path to the downloaded file.
        """
        pass
