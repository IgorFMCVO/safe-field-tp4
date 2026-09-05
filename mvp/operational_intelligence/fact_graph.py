"""Occurrence-scoped, source-traceable fact graph."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import threading

from .models import Fact
from .storage import atomic_json


class FactRelationType(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    RELATED = "RELATED"


@dataclass(frozen=True, slots=True)
class FactRelation:
    source_fact: str
    target_fact: str
    relation: FactRelationType
    source_segments: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "source_fact": self.source_fact,
            "target_fact": self.target_fact,
            "relation": self.relation.value,
            "source_segments": list(self.source_segments),
        }


class FactGraph:
    def __init__(self, path: Path):
        self.path = path
        self._facts: dict[str, Fact] = {}
        self._relations: list[FactRelation] = []
        self._lock = threading.RLock()
        self._save()

    def add_fact(self, fact: Fact) -> None:
        with self._lock:
            existing = self._facts.get(fact.fact_id)
            if existing and existing.to_dict() != fact.to_dict():
                raise ValueError(f"Conflicting duplicate fact_id: {fact.fact_id}")
            self._facts[fact.fact_id] = fact
            self._save()

    def has_fact(self, fact_id: str) -> bool:
        with self._lock:
            return fact_id in self._facts

    def get_fact(self, fact_id: str) -> Fact | None:
        with self._lock:
            return self._facts.get(fact_id)

    def add_relation(self, relation: FactRelation) -> None:
        with self._lock:
            if relation.source_fact not in self._facts or relation.target_fact not in self._facts:
                raise ValueError("Fact relation endpoints must exist")
            if not relation.source_segments:
                raise ValueError("Fact relation must preserve source segments")
            if relation not in self._relations:
                self._relations.append(relation)
                self._save()

    def _save(self) -> None:
        atomic_json(
            self.path,
            {
                "facts": [fact.to_dict() for fact in self._facts.values()],
                "relations": [relation.to_dict() for relation in self._relations],
            },
        )
