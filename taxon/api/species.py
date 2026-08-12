r"""Species-list helpers: include-filter parsing, pagination, breadcrumbs.

Sub-PR 2C builds the species-list, species-lookup, and links endpoints
on top of the resolver from :mod:`taxon.api.hierarchy`. This module
holds the helpers the router needs:

- :class:`InclusionFilter` — parses the ``include`` query parameter
  into the set of inclusion classes the response should cover.
- :func:`species_list_page` — paginates the direct species children of
  a genus using a 500-item cap and a deterministic cursor.
- :func:`build_breadcrumb` — walks the parent chain of a taxon to
  emit the Kingdom → … → Genus breadcrumb the lookup endpoint returns.

The cap and cursor strategy follow the \`species-list-by-genus\` spec:
the first 500 rows return ``next_cursor=None``; the next page is
addressed by the cursor; rows are ordered alphabetically by canonical
``name`` so the same query yields the same order across calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from taxon.api.hierarchy import (
    PATH_RANKS,
    TaxonRow,
    _to_row,
    resolve_path,
)
from taxon.schema import Taxon

PAGE_CAP: Final[int] = 500


@dataclass(frozen=True)
class InclusionFilter:
    """Parsed ``include`` query parameter.

    The four toggles correspond to the marker flags on :class:`Taxon`.
    By default every toggle is ``False`` so the response carries only
    accepted species — ``is_synonym``, ``is_extinct``, ``is_uncertain``,
    and ``is_unassigned`` are all ``False``.

    Unknown ``include`` values are silently ignored; the parser only
    honours the four canonical names listed in the
    ``inclusion-filters`` spec.
    """

    synonyms: bool = False
    extinct: bool = False
    uncertain: bool = False
    unassigned: bool = False

    @property
    def accepted_only(self) -> bool:
        """Return ``True`` when every toggle is off (the spec default)."""
        return not any(
            (
                self.synonyms,
                self.extinct,
                self.uncertain,
                self.unassigned,
            )
        )

    def marker_predicate(self) -> ColumnElement[bool]:
        """Return a SQLAlchemy filter that widens the species list per toggle.

        The spec rules are:

        - Default accepted-only: keep species whose every marker is False.
        - Any toggle enabled: keep accepted species plus the species
          matching the enabled toggle(s). With all four toggles on,
          every species passes.

        Concretely the predicate is ``accepted OR (any enabled toggle)``
        where ``accepted`` means "all four marker flags are False" and
        the OR is over the enabled toggles only. The accepted clause is
        always present so the response always includes the accepted
        species regardless of how many toggles the user flips.
        """
        enabled = []
        if self.synonyms:
            enabled.append(Taxon.is_synonym.is_(True))
        if self.extinct:
            enabled.append(Taxon.is_extinct.is_(True))
        if self.uncertain:
            enabled.append(Taxon.is_uncertain.is_(True))
        if self.unassigned:
            enabled.append(Taxon.is_unassigned.is_(True))

        accepted = ~or_(
            Taxon.is_synonym.is_(True),
            Taxon.is_extinct.is_(True),
            Taxon.is_uncertain.is_(True),
            Taxon.is_unassigned.is_(True),
        )

        if not enabled:
            return accepted
        # accepted OR (any enabled toggle) keeps accepted species
        # alongside the additional inclusion classes the user enabled.
        return or_(accepted, *enabled)


_KNOWN_TOGGLES: Final[frozenset[str]] = frozenset(
    {"synonyms", "extinct", "uncertain", "unassigned"}
)


def parse_include(raw: str | None) -> InclusionFilter:
    """Parse the ``include`` query parameter into an :class:`InclusionFilter`.

    Accepts a CSV string (``"synonyms,extinct"``). Empty or missing
    input returns the default accepted-only filter. Unknown values
    are silently ignored — the spec mandates tolerant parsing.
    """
    if not raw:
        return InclusionFilter()
    parts = {part.strip().lower() for part in raw.split(",")}
    return InclusionFilter(
        synonyms="synonyms" in parts,
        extinct="extinct" in parts,
        uncertain="uncertain" in parts,
        unassigned="unassigned" in parts,
    )


@dataclass(frozen=True)
class SpeciesPage:
    """A page of species rows plus the cursor for the next page (if any)."""

    rows: list[TaxonRow]
    next_cursor: str | None


def _encode_cursor(last_name: str) -> str:
    """Encode the cursor as the canonical name of the last row in the page.

    Using the name (not the id) keeps the cursor stable across database
    re-imports — names are immutable once captured, ids are not.
    """
    return f"name:{last_name}"


def _decode_cursor(cursor: str) -> str:
    """Strip the ``name:`` prefix and return the bare canonical name."""
    if not cursor.startswith("name:"):
        raise ValueError(f"invalid cursor: {cursor!r}")
    return cursor[len("name:") :]


def list_species_page(
    session: Session,
    *,
    parent_id: int,
    inclusion: InclusionFilter,
    cursor: str | None = None,
) -> SpeciesPage:
    """Return one page of direct species children of ``parent_id``.

    The page is capped at :data:`PAGE_CAP` rows; when more rows exist
    the response carries a ``next_cursor`` so the caller can fetch the
    next page. Rows are ordered alphabetically by canonical ``name``
    so paginated requests are deterministic.
    """
    after_name: str | None = None
    if cursor:
        after_name = _decode_cursor(cursor)

    stmt = (
        select(Taxon)
        .where(Taxon.parent_id == parent_id)
        .where(func.lower(Taxon.rank) == "species")
        .where(inclusion.marker_predicate())
        .order_by(func.lower(Taxon.name), Taxon.name)
    )
    if after_name is not None:
        # Cursor advances to rows whose canonical name is strictly
        # greater than the cursor's name. The tie-breaker on ``Taxon.name``
        # keeps the order deterministic even when two taxa share a
        # case-folded name.
        stmt = stmt.where(func.lower(Taxon.name) > after_name.lower())

    rows = [_to_row(t) for t in session.scalars(stmt.limit(PAGE_CAP + 1)).all()]
    next_cursor: str | None = None
    if len(rows) > PAGE_CAP:
        rows = rows[:PAGE_CAP]
        next_cursor = _encode_cursor(rows[-1].name)
    return SpeciesPage(rows=rows, next_cursor=next_cursor)


def build_breadcrumb(session: Session, taxon_id: int) -> list[str]:
    """Walk the parent chain of ``taxon_id`` and return the breadcrumb.

    The breadcrumb is ordered Kingdom → Phylum → Class → Order →
    Family → Genus. The taxon's own name is NOT included; the lookup
    endpoint already returns the species name separately and the
    disambiguation candidates render the breadcrumb as the path that
    uniquely identifies the species.

    Ranks that did not exist in the lineage are skipped — the cascade
    can be sparse, but the breadcrumb always reads top-down. If the
    chain includes a superdomain (Biota) we skip it so the breadcrumb
    matches the cascade's Kingdom-first UX.
    """
    chain: list[str] = []
    current_id: int | None = taxon_id
    seen: set[int] = set()
    while current_id is not None and current_id not in seen:
        seen.add(current_id)
        taxon = session.get(Taxon, current_id)
        if taxon is None:
            break
        parent_id = taxon.parent_id
        if parent_id is None:
            # The current taxon is a root (no parent). We stop here;
            # the breadcrumb includes the rank below the root only if
            # the root itself is the species being resolved — which
            # cannot happen for our cascade because we only resolve
            # species, which always have a genus parent.
            break
        parent = session.get(Taxon, parent_id)
        if parent is None:
            break
        chain.append(parent.name)
        current_id = parent.id

    chain.reverse()

    # Drop the leading superdomain (Biota) when present so the
    # breadcrumb starts at Kingdom, matching the cascade UI's first
    # dropdown.
    if len(chain) > 1 and chain[0].lower() == "biota":
        chain = chain[1:]

    return chain


def find_species_by_pair(
    session: Session,
    *,
    parent_segments: list[str],
    epithet: str,
) -> list[TaxonRow]:
    """Return every species whose ``(genus, epithet)`` pair matches.

    The genus is resolved by walking ``parent_segments``. WoRMS stores
    the species ``name`` as the canonical ``"<genus> <epithet>"`` pair
    (e.g. ``Girardinichthys multiradiatus``); the lookup joins the
    resolved genus's name with the supplied epithet and matches the
    case-folded result against ``Taxon.name``.

    Multiple matches indicate the lookup is ambiguous and the caller
    should raise :class:`AmbiguousError` with the breadcrumb of each.
    """
    genus = resolve_path(session, parent_segments)
    if genus is None:
        return []
    # Build the canonical "Genus epithet" name the dataset stores.
    canonical = f"{genus.name} {epithet}"
    stmt = (
        select(Taxon)
        .where(Taxon.parent_id == genus.id)
        .where(func.lower(Taxon.rank) == "species")
        .where(func.lower(Taxon.name) == canonical.lower())
    )
    return [_to_row(t) for t in session.scalars(stmt).all()]


__all__ = [
    "PAGE_CAP",
    "InclusionFilter",
    "SpeciesPage",
    "build_breadcrumb",
    "find_species_by_pair",
    "list_species_page",
    "parse_include",
]


# Re-export ``PATH_RANKS`` so callers can still reach it from this module.
_ = PATH_RANKS
