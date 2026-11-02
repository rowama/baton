"""Worker profiles (§6.1).

Phase 1 covers loading and vocabulary validation; environment construction,
PATH resolution and secrets arrive with the routing layer.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from . import vocab as vocab_mod
from .data import YamlError, load_yaml
from .models import Issue, WorkerProfile
from .vocab import Vocabulary


class ProfileError(Exception):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("\n".join(str(i) for i in issues))

    def codes(self) -> set[str]:
        return {i.code for i in self.issues}


def validate_profiles(raw: object, vocab: Vocabulary, source: str = "workers.yaml") -> tuple[dict[str, WorkerProfile], list[Issue]]:
    issues: list[Issue] = []
    profiles: dict[str, WorkerProfile] = {}
    if not isinstance(raw, dict):
        return {}, [Issue(code="profile.not_a_mapping", where=source, message="profiles must be a mapping of name -> profile")]
    for name, body in raw.items():
        where = f"{source}:{name}"
        try:
            profile = WorkerProfile.model_validate(body)
        except ValidationError as e:
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                issues.append(Issue(code="profile.invalid", where=f"{where}.{loc}" if loc else where, message=err["msg"]))
            continue
        for cap in profile.capabilities:
            if cap not in vocab.capabilities:
                issues.append(
                    Issue(code="vocab.unknown_capability", where=f"{where}.capabilities", message=f"capability {cap!r} is not in {vocab.id}")
                )
        if profile.tier is not None and profile.tier not in vocab.tiers:
            issues.append(Issue(code="vocab.unknown_tier", where=f"{where}.tier", message=f"tier {profile.tier!r} is not one of {vocab.tiers}"))
        profiles[str(name)] = profile
    return profiles, issues


def load_profiles(path: str | Path, vocab_id: str = vocab_mod.DEFAULT) -> dict[str, WorkerProfile]:
    path = Path(path)
    try:
        raw = load_yaml(path)
    except YamlError as e:
        raise ProfileError([Issue(code="yaml.invalid", where=str(path), message=str(e))]) from e
    profiles, issues = validate_profiles(raw or {}, vocab_mod.load(vocab_id), source=path.name)
    if issues:
        raise ProfileError(issues)
    return profiles
