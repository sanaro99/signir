"""Evidence-bearing event records; validation is structural, not linguistic proof."""
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Span(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)


class Mention(StrictModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    kind: Literal["person", "thing", "place", "time", "other"]
    # How the source refers to it. Pointing (IX-3p:i), classifiers and pronouns refer
    # without naming, so a different or missing label is weaker evidence of an error.
    form: Literal["lexical", "name", "fingerspelled", "pointing", "classifier", "pronoun"] = "lexical"
    alternatives: list[str] = Field(default_factory=list)  # competing readings (ambiguity)
    # Other words this mention can express (lexicon synonyms, word family). Not ambiguity:
    # used only to avoid MISSING when a synonym is present, never to establish equality.
    concepts: list[str] = Field(default_factory=list)
    evidence: list[Span] = Field(min_length=1)


class Role(StrictModel):
    role: Literal["agent", "patient", "recipient", "experiencer", "location", "instrument"]
    mention_id: str
    # syntactic: English grammar. word_order: plain-verb subject-verb-object gloss order
    # without a topic marker (weak evidence). explicit_annotation / resolved_locus: gloss.
    basis: Literal["syntactic", "word_order", "explicit_annotation", "resolved_locus"]
    evidence: list[Span] = Field(min_length=1)


class Polarity(StrictModel):
    value: Literal["positive", "negative", "unknown"]
    # nonmanual: the gloss's head-shake marker (Graph.nonmanual) decides polarity.
    basis: Literal["syntactic", "explicit_annotation", "lexical_negator", "nonmanual", "unknown"]
    evidence: list[Span]

    @model_validator(mode="after")
    def supported(self):
        if self.value != "unknown" and (not self.evidence or self.basis == "unknown"):
            raise ValueError("known polarity requires evidence and basis")
        if self.value == "unknown" and self.basis != "unknown":
            raise ValueError("unknown polarity must have unknown basis")
        return self


class Scope(StrictModel):
    kind: Literal["asserted", "conditional", "question", "reported", "possible",
                  "obligatory", "unknown"]
    parent_event: str | None = None
    evidence: list[Span]

    @model_validator(mode="after")
    def supported(self):
        if self.kind != "unknown" and not self.evidence:
            raise ValueError("known scope requires evidence")
        return self


class Quantity(StrictModel):
    mention_id: str
    kind: Literal["count", "money", "duration", "age", "identifier", "other"]
    unit: str = Field(min_length=1)
    value: str
    relation: Literal["eq", "ge", "gt", "le", "lt", "range", "approx"]
    upper: str | None = None
    evidence: list[Span] = Field(min_length=1)

    @model_validator(mode="after")
    def bounds(self):
        try:
            low = Decimal(self.value)
            high = Decimal(self.upper) if self.upper is not None else None
        except InvalidOperation as exc:
            raise ValueError("quantities require decimal strings") from exc
        if not low.is_finite() or (high is not None and not high.is_finite()):
            raise ValueError("quantities must be finite")
        if self.relation == "range":
            if high is None or high < low:
                raise ValueError("range requires ordered upper bound")
        elif high is not None:
            raise ValueError("upper is only valid for range")
        if self.kind == "count" and (low < 0 or low != low.to_integral_value() or
                                    (high is not None and high != high.to_integral_value())):
            raise ValueError("counts must be nonnegative integers")
        if self.kind == "identifier" and self.relation != "eq":
            raise ValueError("identifiers require exact comparison")
        return self


class Event(StrictModel):
    id: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    # classifier and directional predicates show participants through handshape/movement.
    form: Literal["lexical", "classifier", "directional", "fingerspelled"] = "lexical"
    alternatives: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    evidence: list[Span] = Field(min_length=1)
    participants: list[str]
    roles: list[Role]
    roles_complete: bool = False
    polarity: Polarity
    scope: Scope
    quantities: list[Quantity]


class NonManual(StrictModel):
    """A gloss non-manual marker. value False means annotated as absent, not unknown."""
    label: Literal["negation", "topic", "yes_no_question", "wh_question", "conditional"]
    value: bool
    evidence: list[Span] = Field(default_factory=list)  # empty for utterance-level labels


class Unresolved(StrictModel):
    reason: Literal["lexical_ambiguity", "unsupported_scope", "unresolved_role",
                    "unresolved_reference", "unresolved_quantity", "unparsed_content"]
    detail: str = Field(min_length=1)
    evidence: list[Span] = Field(min_length=1)


class Graph(StrictModel):
    version: Literal["2.0"] = "2.0"
    language: Literal["english", "gloss"]
    text: str = Field(min_length=1)
    mentions: list[Mention] = Field(max_length=256)
    events: list[Event] = Field(max_length=64)
    unresolved: list[Unresolved] = Field(max_length=256)
    nonmanual: list[NonManual] = Field(default_factory=list, max_length=16)

    def marker(self, label):
        """True/False when the marker is annotated, None when not supplied."""
        return next((m.value for m in self.nonmanual if m.label == label), None)

    @model_validator(mode="after")
    def integrity(self):
        mentions = {m.id: m for m in self.mentions}
        events = {e.id: e for e in self.events}
        ids = [m.id for m in self.mentions] + [e.id for e in self.events]
        if len(set(ids)) != len(ids):
            raise ValueError("mention and event IDs must be unique")
        labels = [m.label for m in self.nonmanual]
        if len(set(labels)) != len(labels):
            raise ValueError("duplicate non-manual marker")
        if self.language == "english" and self.nonmanual:
            raise ValueError("non-manual markers belong to the gloss")
        topic = self.marker("topic") is True
        for event in self.events:
            if len(set(event.participants)) != len(event.participants):
                raise ValueError("duplicate event participant")
            if not set(event.participants) <= mentions.keys():
                raise ValueError("dangling participant reference")
            if any(r.mention_id not in event.participants for r in event.roles):
                raise ValueError("role must reference an event participant")
            if event.roles_complete and (not event.roles or
                    {r.mention_id for r in event.roles} != set(event.participants)):
                raise ValueError("complete role inventory must cover every represented participant")
            if any(q.mention_id not in event.participants for q in event.quantities):
                raise ValueError("quantity must reference an event participant")
            role_keys = [(r.role, r.mention_id) for r in event.roles]
            if len(set(role_keys)) != len(role_keys):
                raise ValueError("duplicate role assignment")
            if self.language == "gloss":
                if any(r.basis == "syntactic" for r in event.roles):
                    raise ValueError("gloss roles require word order, explicit annotation or resolved loci")
                if any(r.basis == "word_order" for r in event.roles) and (topic or event.form != "lexical"):
                    raise ValueError("word-order roles need a plain lexical verb without topic marking")
                if event.polarity.value == "positive" and event.polarity.basis not in ("explicit_annotation",
                                                                                     "nonmanual"):
                    raise ValueError("positive gloss polarity requires explicit annotation or a non-manual label")
                if event.polarity.basis == "nonmanual" and self.marker("negation") != (
                        event.polarity.value == "negative"):
                    raise ValueError("non-manual polarity must agree with the annotated negation marker")
            else:
                if any(r.basis in ("word_order", "resolved_locus") for r in event.roles):
                    raise ValueError("word-order and locus role evidence belong to the gloss")
                if event.polarity.basis == "nonmanual" or event.form != "lexical":
                    raise ValueError("non-manual polarity and sign forms belong to the gloss")
            seen = {event.id}
            parent = event.scope.parent_event
            while parent is not None:
                if parent not in events or parent in seen:
                    raise ValueError("dangling or cyclic parent event")
                seen.add(parent)
                parent = events[parent].scope.parent_event

        def visit(value):
            if isinstance(value, Span):
                if value.end <= value.start or value.end > len(self.text):
                    raise ValueError("invalid evidence offsets")
                if self.text[value.start:value.end] != value.text:
                    raise ValueError("evidence differs from original text")
            elif isinstance(value, BaseModel):
                for name in type(value).model_fields:
                    visit(getattr(value, name))
            elif isinstance(value, list):
                for item in value:
                    visit(item)
        visit(self)
        return self
