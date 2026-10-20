"""Exact corpus labels with explicit reviewed alternatives and provenance."""
import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .schema import StrictModel


class Entry(StrictModel):
    label: str = Field(min_length=1)
    concepts: list[str] = Field(min_length=1)
    kind: Literal["predicate", "person", "thing", "place", "time", "other"]
    provenance: str = Field(min_length=1)


class Lexicon(StrictModel):
    version: str = Field(min_length=1)
    entries: list[Entry]

    @model_validator(mode="after")
    def unique(self):
        if len({e.label for e in self.entries}) != len(self.entries):
            raise ValueError("duplicate lexicon label")
        if any(not c.strip() for e in self.entries for c in e.concepts):
            raise ValueError("empty concept")
        return self

    @classmethod
    def load(cls, path):
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))

    def hints(self, text):
        labels = set(re.findall(r"\S+", text))
        return [e.model_dump() for e in self.entries if e.label in labels]

    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()

    def validate_graph(self, graph):
        """Reviewed alternatives cannot be silently resolved by a model proposal."""
        for record in [*graph.mentions, *graph.events]:
            is_event = hasattr(record, "predicate")
            kind = "predicate" if is_event else record.kind
            primary = record.predicate if is_event else record.label
            labels = {token for span in record.evidence for token in re.findall(r"\S+", span.text)}
            relevant = [entry for entry in self.entries if entry.kind == kind and entry.label in labels]
            if not relevant:
                continue
            candidates = {c.casefold() for entry in relevant for c in entry.concepts}
            proposed = {primary.casefold(), *(s.casefold() for s in record.alternatives)}
            if primary.casefold() not in candidates or not candidates <= proposed:
                raise ValueError("graph drops or contradicts reviewed lexical candidates")
