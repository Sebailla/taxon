"""Load the captured search templates and build per-species dispatch URLs."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

_TABLE_ROW = re.compile(r"^\|\s*(?P<source>[^|]+?)\s*\|\s*`(?P<url>[^`]+)`(?:\s*\([^)]*\))?\s*\|$")


@dataclass(frozen=True)
class SearchTemplate:
    source: str
    url_template: str


@dataclass(frozen=True)
class SearchLink:
    source: str
    label: str
    url: str


def load_templates(path: Path | str) -> tuple[SearchTemplate, ...]:
    """Parse ordered template table rows without normalizing their URL bytes."""
    templates: list[SearchTemplate] = []
    with Path(path).open(encoding="utf-8") as file:
        for line in file:
            match = _TABLE_ROW.fullmatch(line.rstrip("\r\n"))
            if match is None:
                continue
            templates.append(
                SearchTemplate(
                    source=match.group("source"),
                    url_template=match.group("url"),
                )
            )
    if len(templates) != 12:
        raise ValueError(f"Expected exactly 12 search templates, found {len(templates)}")
    if any(template.url_template.count("{q}") != 1 for template in templates):
        raise ValueError("Every search template must contain exactly one {q} placeholder")
    return tuple(templates)


def build_search_links(species: str, templates: Iterable[SearchTemplate]) -> tuple[SearchLink, ...]:
    """Substitute one encoded species query into each ordered template."""
    encoded = quote_plus(species, safe="")
    return tuple(
        SearchLink(
            source=template.source,
            label=template.source,
            url=template.url_template.replace("{q}", encoded),
        )
        for template in templates
    )
