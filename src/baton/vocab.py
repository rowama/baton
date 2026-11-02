"""Capability vocabularies (§5.6). Several versions may be supported side by side."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from . import data
from .models import Requires
from .data import load_yaml


class Vocabulary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    capabilities: dict[str, str]
    tiers: list[str]
    numeric: dict[str, str] = Field(default_factory=dict)
    sme_defaults: dict[str, Requires] = Field(default_factory=dict)
    vendor_denylist: list[str] = Field(default_factory=list)

    def tier_rank(self, tier: str) -> int:
        return self.tiers.index(tier)

    def find_vendor_string(self, text: str) -> str | None:
        """Return the first denylisted vendor string found in ``text`` (case-insensitive)."""
        lowered = text.lower()
        for entry in self.vendor_denylist:
            if entry.lower() in lowered:
                return entry
        return None


class UnknownVocabulary(LookupError):
    pass


def _file_for(vocab_id: str) -> Path:
    # "baton-capabilities/1" -> vocab/baton-capabilities-1.yaml
    name, sep, version = vocab_id.partition("/")
    if not sep or not version.isdigit():
        raise UnknownVocabulary(vocab_id)
    return data.path("vocab") / f"{name}-{version}.yaml"


def supported() -> list[str]:
    ids = []
    for f in sorted(data.path("vocab").glob("*.yaml")):
        name, _, version = f.stem.rpartition("-")
        ids.append(f"{name}/{version}")
    return ids


@cache
def load(vocab_id: str) -> Vocabulary:
    path = _file_for(vocab_id)
    if not path.is_file():
        raise UnknownVocabulary(vocab_id)
    vocab = Vocabulary.model_validate(load_yaml(path))
    if vocab.id != vocab_id:
        raise ValueError(f"{path}: declares id {vocab.id!r}, expected {vocab_id!r}")
    return vocab


DEFAULT = "baton-capabilities/1"
