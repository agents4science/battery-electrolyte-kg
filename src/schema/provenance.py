"""PROV-O aligned provenance model for KG assertions."""

from datetime import datetime
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field
import uuid


def generate_id() -> str:
    return str(uuid.uuid4())


class AgentType(str, Enum):
    """Types of agents that can generate assertions."""
    SOFTWARE = "software"
    HUMAN = "human"
    ORGANIZATION = "organization"


class ActivityType(str, Enum):
    """Types of provenance activities."""
    EXTRACTION = "extraction"  # NLP/parsing from text
    TRANSFORMATION = "transformation"  # ETL, normalization
    INFERENCE = "inference"  # ML model prediction
    CURATION = "curation"  # Human review
    MEASUREMENT = "measurement"  # Lab experiment
    COMPUTATION = "computation"  # DFT, simulation


class Agent(BaseModel):
    """An agent responsible for generating assertions (PROV-O Agent)."""
    id: str = Field(default_factory=generate_id)
    name: str
    agent_type: AgentType
    version: Optional[str] = None  # software version if applicable
    description: Optional[str] = None

    def __hash__(self):
        return hash(self.id)


class ProvenanceActivity(BaseModel):
    """An activity that generates or transforms data (PROV-O Activity)."""
    id: str = Field(default_factory=generate_id)
    activity_type: ActivityType
    description: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    agent_id: str  # who performed this activity
    parameters: dict = Field(default_factory=dict)  # e.g., model hyperparameters
    input_ids: list[str] = Field(default_factory=list)  # input entities
    output_ids: list[str] = Field(default_factory=list)  # output entities

    def __hash__(self):
        return hash(self.id)


class ProvenanceRecord(BaseModel):
    """
    Provenance record for a KG assertion (PROV-O aligned).

    Maps to:
    - prov:wasDerivedFrom -> source_ids
    - prov:wasGeneratedBy -> activity_id
    - prov:wasAttributedTo -> agent_id
    """
    id: str = Field(default_factory=generate_id)

    # What this provenance is attached to
    entity_id: str  # The KG entity/triple this provenance describes
    entity_type: str  # Type of entity (e.g., "formulation", "measurement", "hypothesis")

    # prov:wasDerivedFrom - sources this was derived from
    source_ids: list[str] = Field(default_factory=list)  # EvidenceSource IDs
    source_doi: Optional[str] = None  # Direct DOI reference
    source_row_id: Optional[str] = None  # Dataset row identifier
    evidence_snippet: Optional[str] = None  # Text snippet if extracted from literature

    # prov:wasGeneratedBy - activity that created this
    activity_id: Optional[str] = None
    extraction_method: Optional[str] = None  # e.g., "regex", "NER", "manual"

    # prov:wasAttributedTo - agent responsible
    agent_id: Optional[str] = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    kg_version: str = "0.1.0"
    confidence: float = 1.0  # 0-1 confidence score

    # Validation status
    validated: bool = False
    validation_method: Optional[str] = None
    validation_date: Optional[datetime] = None

    def __hash__(self):
        return hash(self.id)

    def is_complete(self) -> bool:
        """Check if provenance record has minimum required fields."""
        return bool(self.source_ids or self.source_doi or self.activity_id)


class KGVersion(BaseModel):
    """Version snapshot of the knowledge graph."""
    version: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    description: Optional[str] = None
    num_entities: int = 0
    num_triples: int = 0
    parent_version: Optional[str] = None
    changes: list[str] = Field(default_factory=list)  # List of change descriptions
