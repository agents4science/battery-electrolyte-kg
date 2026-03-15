"""Simple triple store for RDF-style operations."""

from typing import Optional, Iterator
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Triple:
    """An RDF-style triple."""
    subject: str
    predicate: str
    object: str
    provenance_id: Optional[str] = None

    def __hash__(self):
        return hash((self.subject, self.predicate, self.object))

    def __eq__(self, other):
        if not isinstance(other, Triple):
            return False
        return (
            self.subject == other.subject and
            self.predicate == other.predicate and
            self.object == other.object
        )


class TripleStore:
    """
    Simple in-memory triple store with indexing for fast queries.

    Supports SPARQL-like pattern matching: (s, p, o) where any can be None (wildcard).
    """

    def __init__(self):
        self._triples: set[Triple] = set()
        # Indexes for fast lookup
        self._spo: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self._pos: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self._osp: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    def add(
        self,
        subject: str,
        predicate: str,
        obj: str,
        provenance_id: Optional[str] = None,
    ) -> Triple:
        """Add a triple to the store."""
        triple = Triple(subject, predicate, obj, provenance_id)
        self._triples.add(triple)

        # Update indexes
        self._spo[subject][predicate].add(obj)
        self._pos[predicate][obj].add(subject)
        self._osp[obj][subject].add(predicate)

        return triple

    def remove(self, subject: str, predicate: str, obj: str) -> bool:
        """Remove a triple from the store."""
        triple = Triple(subject, predicate, obj)
        if triple not in self._triples:
            return False

        self._triples.discard(triple)

        # Update indexes
        self._spo[subject][predicate].discard(obj)
        self._pos[predicate][obj].discard(subject)
        self._osp[obj][subject].discard(predicate)

        return True

    def query(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
    ) -> Iterator[Triple]:
        """
        Query triples matching the pattern.

        None values act as wildcards matching anything.
        """
        if subject is not None and predicate is not None and obj is not None:
            # Exact match
            triple = Triple(subject, predicate, obj)
            if triple in self._triples:
                yield triple

        elif subject is not None and predicate is not None:
            # Match (s, p, ?)
            for o in self._spo.get(subject, {}).get(predicate, set()):
                yield Triple(subject, predicate, o)

        elif predicate is not None and obj is not None:
            # Match (?, p, o)
            for s in self._pos.get(predicate, {}).get(obj, set()):
                yield Triple(s, predicate, obj)

        elif subject is not None and obj is not None:
            # Match (s, ?, o)
            for p in self._osp.get(obj, {}).get(subject, set()):
                yield Triple(subject, p, obj)

        elif subject is not None:
            # Match (s, ?, ?)
            for p, objects in self._spo.get(subject, {}).items():
                for o in objects:
                    yield Triple(subject, p, o)

        elif predicate is not None:
            # Match (?, p, ?)
            for o, subjects in self._pos.get(predicate, {}).items():
                for s in subjects:
                    yield Triple(s, predicate, o)

        elif obj is not None:
            # Match (?, ?, o)
            for s, predicates in self._osp.get(obj, {}).items():
                for p in predicates:
                    yield Triple(s, p, obj)

        else:
            # Match all
            yield from self._triples

    def __len__(self) -> int:
        return len(self._triples)

    def __iter__(self) -> Iterator[Triple]:
        return iter(self._triples)

    def subjects(self) -> set[str]:
        """Get all unique subjects."""
        return set(self._spo.keys())

    def predicates(self) -> set[str]:
        """Get all unique predicates."""
        return set(self._pos.keys())

    def objects(self) -> set[str]:
        """Get all unique objects."""
        return set(self._osp.keys())

    def to_list(self) -> list[tuple[str, str, str]]:
        """Export as list of tuples."""
        return [(t.subject, t.predicate, t.object) for t in self._triples]
