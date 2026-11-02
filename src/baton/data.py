"""Shipped data files and strict YAML reading."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]


def path(name: str) -> Path:
    """Directory of shipped data (``vocab``, ``formats``).

    Installed wheels carry it under ``baton/_data`` (see pyproject); a source
    checkout uses the repo-root directories laid out in §4.1.
    """
    packaged = Path(str(resources.files("baton"))) / "_data" / name
    if packaged.is_dir():
        return packaged
    return _REPO_ROOT / name


class YamlError(ValueError):
    pass


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of keeping the last."""


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    loader.flatten_mapping(node)
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            line = key_node.start_mark.line + 1
            raise YamlError(f"duplicate key {key!r} at line {line}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def read_text(p: Path) -> str:
    """Read UTF-8 text, tolerating a BOM (§15.1)."""
    return p.read_text(encoding="utf-8-sig")


def load_yaml(p: Path) -> Any:
    try:
        return yaml.load(read_text(p), Loader=_StrictLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as e:
        raise YamlError(str(e)) from e
