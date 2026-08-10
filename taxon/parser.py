"""Streaming parser for the indentation-based WoRMS taxonomy dump."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import TypedDict

_LINE_PATTERN = re.compile(
    r"^(?P<label>.+?) \[(?P<rank>[^]]+)] \{ID=(?P<source_id>\S+)(?:\s+.*)?}$"
)

_AUTHOR_TOKEN = r"[A-Z][\w.\-'’]*"
_INITIAL_TOKEN = r"[A-Z]\.?"
_APOSTROPHE_PARTICLE = r"(?:d|D)[’']"
_SPACE_PARTICLE = r"(?:de|du|van|von|da|di|do|la|le|los|las)\s+"
_CONNECTOR_TOKEN = r"(?:\s+(?:in|non)\s+" + _AUTHOR_TOKEN + r")?"
_AUTHOR_LIST = (
    r"(?:"
    + r"(?:"
    + _APOSTROPHE_PARTICLE
    + r")?"
    + r"(?:"
    + _SPACE_PARTICLE
    + r")?"
    + r"(?:(?:in|non)\s+)?"
    + _AUTHOR_TOKEN
    + _CONNECTOR_TOKEN
    + r"(?:\s+"
    + _INITIAL_TOKEN
    + r")*"
    + r"(?:\s+"
    + _AUTHOR_TOKEN
    + _CONNECTOR_TOKEN
    + r")?"
    + r"(?:"
    + r"(?:\s*,\s*|\s+(?:&|and)\s+)"
    + _AUTHOR_TOKEN
    + _CONNECTOR_TOKEN
    + r"(?:\s+"
    + _INITIAL_TOKEN
    + r")*"
    + r"(?:\s+"
    + _AUTHOR_TOKEN
    + _CONNECTOR_TOKEN
    + r")?"
    + r")*"
    + r")"
)
_PARENS_CITATION = r"\(\s*" + _AUTHOR_LIST + r"\s*,\s*\d{4}\s*\)"
_CITATION_PARENS_PLUS_AUTHOR = r"\s*" + _PARENS_CITATION + r"\s+" + _AUTHOR_LIST + r"\s*,\s*\d{4}"
_CITATION_PARENS_ALONE = r"\s*" + _PARENS_CITATION
_CITATION_AUTHOR_ALONE = r"\s+" + _AUTHOR_LIST + r"\s*,\s*\d{4}"
_TRAILING_CITATION = re.compile(
    r"(?:"
    + _CITATION_PARENS_PLUS_AUTHOR
    + r"|"
    + _CITATION_PARENS_ALONE
    + r"|"
    + _CITATION_AUTHOR_ALONE
    + r")\s*$"
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
        markers, residual = _extract_markers(label)
        canonical = _split_canonical(residual)
        source_id = match.group("source_id")
        rank = match.group("rank")

        while stack and stack[-1][0] >= indent_level:
            stack.pop()
        parent_id = stack[-1][1] if stack else None

        yield (
            parent_id,
            ParsedTaxon(
                source_id=source_id,
                rank=rank,
                name=canonical,
                display_name=f"{label} [{rank}]",
                is_synonym=markers["is_synonym"],
                is_extinct=markers["is_extinct"],
                is_uncertain=markers["is_uncertain"],
                is_unassigned=markers["is_unassigned"],
            ),
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


_EMPTY_PARENS = re.compile(r"\s*\(\s*\)\s*")


def _split_canonical(residual: str) -> str:
    """Return the canonical (citation-free) name from the post-marker residual.

    The verbatim source label still lives in ``display_name``. This function only
    feeds the deduplication-friendly column used by the hierarchy and lookup
    specs, which require case-insensitive matching against the bare name.

    Rules (applied iteratively from the end of the string):

    1. Strip a trailing parenthetical author-year block such as
       ``(Shipley, 1896)`` or ``(Cable & Quick, 1954)``. If the parenthesised
       group does not contain a four-digit year, it is part of the canonical
       name (for example a subgenus like ``(Acanthosentis)``) and is kept.
    2. Strip a trailing ``, Author(s), <year>`` citation. Author tokens may
       include ``&``/``and`` conjunctions, ``in``/``non`` connectors, and
       comma-separated multi-author lists.
    """
    result = residual
    previous: str | None = None
    while result != previous:
        previous = result
        match = _TRAILING_CITATION.search(result)
        if match is not None:
            result = result[: match.start()].rstrip()
            continue
        empty = _EMPTY_PARENS.search(result)
        if empty is not None and empty.end() == len(result):
            result = result[: empty.start()].rstrip()
    return result
