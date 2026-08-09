"""Streaming parser for the indentation-based WoRMS taxonomy dump."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import TypedDict

_LINE_PATTERN = re.compile(
    r"^(?P<label>.+?) \[(?P<rank>[^]]+)] \{ID=(?P<source_id>\S+)(?:\s+.*)?}$"
)


class ParsedTaxon(TypedDict):
    source_id: str
    rank: str
    name: str
    display_name: str
    is_synonym: bool
    is_extinct: bool
    is_uncertain: bool
    is_unassigned: bool


def parse_taxa(lines: Iterable[str]) -> Iterator[tuple[str | None, ParsedTaxon]]:
    """Yield source-parent IDs and parsed taxa while retaining only ancestor state."""
    stack: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\r\n")
        if not line:
            continue

        leading_spaces = len(line) - len(line.lstrip(" "))
        if leading_spaces % 2:
            raise ValueError(f"Line {line_number}: indentation must be a multiple of two spaces")
        indent_level = leading_spaces // 2

        match = _LINE_PATTERN.fullmatch(line[leading_spaces:])
        if match is None:
            raise ValueError(f"Line {line_number}: malformed taxon record")

        label = match.group("label")
        markers, name = _extract_markers(label)
        source_id = match.group("source_id")
        rank = match.group("rank")

        while stack and stack[-1][0] >= indent_level:
            stack.pop()
        parent_id = stack[-1][1] if stack else None

        yield parent_id, ParsedTaxon(
            source_id=source_id,
            rank=rank,
            name=name,
            display_name=f"{label} [{rank}]",
            is_synonym=markers["is_synonym"],
            is_extinct=markers["is_extinct"],
            is_uncertain=markers["is_uncertain"],
            is_unassigned=markers["is_unassigned"],
        )
        stack.append((indent_level, source_id))


def _extract_markers(label: str) -> tuple[dict[str, bool], str]:
    remaining = label
    markers = {
        "is_synonym": False,
        "is_extinct": False,
        "is_uncertain": False,
        "is_unassigned": False,
    }
    prefixes = (
        ("[unassigned]", "is_unassigned"),
        ("=", "is_synonym"),
        ("†", "is_extinct"),
        ("?", "is_uncertain"),
    )
    matched = True
    while matched:
        matched = False
        for prefix, key in prefixes:
            if remaining.startswith(prefix):
                markers[key] = True
                remaining = remaining[len(prefix) :].lstrip()
                matched = True
                break
    if not remaining:
        raise ValueError("Taxon name cannot be empty")
    return markers, remaining
