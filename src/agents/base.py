"""Base class for discovery agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from pathlib import Path
import json
import logging

logging.basicConfig(level=logging.INFO)


@dataclass
class AgentResult:
    """Result from an agent execution."""

    agent_name: str
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    outputs: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "agent_name": self.agent_name,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "outputs": self.outputs,
            "metrics": self.metrics,
            "errors": self.errors,
            "provenance": self.provenance,
        }

    def save(self, path: Path):
        """Save result to JSON file."""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, default=str)


class BaseAgent(ABC):
    """
    Base class for all discovery agents.

    Each agent follows a common interface:
    - run(): Execute the agent's main task
    - validate(): Check preconditions
    - report(): Generate human-readable summary
    """

    def __init__(self, kg, name: str = "BaseAgent"):
        """
        Initialize agent with KG reference.

        Args:
            kg: KnowledgeGraph instance or path to KG JSON
            name: Human-readable agent name
        """
        self.name = name
        self.logger = logging.getLogger(name)
        self._kg = None
        self._kg_path = None

        # Handle both KG instance and path
        if isinstance(kg, (str, Path)):
            self._kg_path = Path(kg)
        else:
            self._kg = kg

    @property
    def kg(self):
        """Lazy-load KG if path was provided."""
        if self._kg is None and self._kg_path is not None:
            self._kg = self._load_kg(self._kg_path)
        return self._kg

    def _load_kg(self, path: Path) -> dict:
        """Load KG from JSON file."""
        import gzip

        if path.suffix == '.gz':
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                return json.load(f)
        else:
            with open(path) as f:
                return json.load(f)

    @abstractmethod
    def run(self, **kwargs) -> AgentResult:
        """
        Execute the agent's main task.

        Returns:
            AgentResult with outputs, metrics, and provenance
        """
        pass

    def validate(self) -> bool:
        """
        Validate preconditions for running the agent.

        Returns:
            True if preconditions are met
        """
        if self.kg is None:
            self.logger.error("Knowledge graph not loaded")
            return False
        return True

    def report(self, result: AgentResult) -> str:
        """
        Generate human-readable summary of results.

        Args:
            result: AgentResult from run()

        Returns:
            Formatted string summary
        """
        lines = [
            f"{'='*60}",
            f"Agent: {result.agent_name}",
            f"Time: {result.timestamp}",
            f"Status: {'SUCCESS' if result.success else 'FAILED'}",
            f"{'='*60}",
        ]

        if result.metrics:
            lines.append("\nMetrics:")
            for k, v in result.metrics.items():
                lines.append(f"  {k}: {v}")

        if result.errors:
            lines.append("\nErrors:")
            for e in result.errors:
                lines.append(f"  - {e}")

        return "\n".join(lines)
