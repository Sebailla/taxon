"""SQLite-only cascade resolver.

PR #58 replaces the CLB-backed cascade endpoints with a pure
SQLite implementation. The wire shape is preserved 100% so the
cascade UI keeps working without frontend changes.

The three public functions mirror the CLB counterparts one for
one:

- :func:`list_kingdoms` — synthesizes the two CLB roots (Biota +
  Viruses) so the cascade UI's first dropdown keeps showing the same
  two rows regardless of what the local SQLite carries. The synthesis
  is intentional: the local importer does not ingest Biota /
  Viruses (the GBIF backbone ships the superdomain and the kingdom
  rows but not Viruses), and the cascade contract is exactly two
  roots.
- :func:`list_path_children` — descendant lookup against
  ``Taxon`` with the same three roll-up rules the CLB resolver
  applied: phylum → class roll-up, subphylum collapse, family →
  genus roll-up.
- :func:`list_species_under_path` — leaf endpoint that emits every
  species-tier descendant of the genus (species, subspecies, variety,
  form) wrapped in the ``SpeciesListResponse`` envelope.

The module never imports ``httpx``; it is a pure SQLAlchemy
implementation that the FastAPI router hands a session to. The
router module owns the FastAPI surface; this module owns the data
shape.

.. note::

    **Gotcha**: Rows imported via
    :func:`taxon.indented_import.import_indented_dataset` have
    ``display_level IS NULL`` by design (see
    :mod:`taxon.indented_import` module docstring). The cascade
    resolver filters by ``display_level``, so the cascade endpoints
    will return 404 for every path until ``display_level`` is
    populated — either by re-running
    :func:`taxon.import_data.import_dataset` (the established path)
    or by applying :func:`taxon.taxonomy.display_level` at import
    time. The 6-tier lookup and links endpoints are unaffected because
    they filter by ``Taxon.rank``, not ``display_level``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taxon.api.errors import NotFoundError
from taxon.api.hierarchy import (
    TaxonRow,
    _intermediate_ranks_for,
    resolve_path_by_display_level,
)
from taxon.api.schemas import (
    NextTier,
    PathChildrenEnvelope,
    SpeciesListItem,
    SpeciesListResponse,
    TaxonResponse,
)
from taxon.api.species import (
    PAGE_CAP,
    InclusionFilter,
    SpeciesPage,
    _decode_cursor,
    _encode_cursor,
    parse_include,
)
from taxon.schema import Taxon

# CLB-canonical opaque string ids for the two roots the cascade UI
# renders in its first dropdown. CLB never changes these ids across
# releases so the synthesis can hard-code them — the SQLite resolver
# does not need to look anything up for the roots.
_SYNTHETIC_ROOT_IDS: tuple[tuple[str, str], ...] = (
    ("Biota", "5T6MX"),
    ("Viruses", "V"),
)


@dataclass(frozen=True)
class _PathParent:
    """Internal view of a resolved path's deepest taxon."""

    row: TaxonRow


@dataclass(frozen=True)
class _PathResult:
    """Internal bundle returned by :func:`_resolve_path_internal`.

    ``None`` parent means a 404 — the router turns that into a
    NotFoundError.
    """

    parent: _PathParent | None


def list_kingdoms(session: Session) -> list[TaxonResponse]:
    """Return the synthesized Biota + Viruses roots.

    The frontend's first dropdown shows exactly two rows; the wire
    contract is preserved by synthesising both rows server-side with
    the CLB-canonical ids (``5T6MX`` and ``V``). The local SQLite is
    NOT consulted for this endpoint — the GBIF backbone ships neither
    Biota as a ``superdomain`` row nor Viruses, so a SQLite query
    would either return ``[]`` or leak an unrelated superdomain.
    """
    rows = [_synthesize_root(name=name, taxon_id=tid) for name, tid in _SYNTHETIC_ROOT_IDS]
    rows.sort(key=lambda r: str(r["name"]).lower())
    return [TaxonResponse.model_validate(row) for row in rows]


def _synthesize_root(*, name: str, taxon_id: str) -> dict[str, object]:
    """Build a synthetic root row as a dict for ``TaxonResponse.model_validate``.

    The cascade UI renders the root dropdown from ``TaxonResponse``
    so the synthetic row must carry every attribute the model
    consumes. ``rank`` is ``"superdomain"`` because GBIF's
    indented-tree dataset publishes Biota at that rank and CLB uses
    the same rank for both roots. The dict is used (instead of a
    :class:`TaxonRow` dataclass) so the synthesized id can carry the
    CLB-canonical opaque string ``"5T6MX"`` / ``"V"`` directly
    without coercing to ``int``.
    """
    return {
        "id": taxon_id,
        "name": name,
        "display_name": name,
        "rank": "superdomain",
        "parent_id": None,
        "is_synonym": False,
        "is_extinct": False,
        "is_uncertain": False,
        "is_unassigned": False,
    }


def list_path_children(
    session: Session,
    segments: list[str],
) -> PathChildrenEnvelope | None:
    """Walk ``segments`` against the local SQLite and return the children envelope.

    Mirrors :func:`taxon.api.clb_path_children.list_path_children` on
    the wire so the cascade UI keeps consuming the same envelope.
    Returns ``None`` when any segment fails to resolve — the router
    translates that to a 404 with the failing segment in the detail
    body.

    The path is walked via :func:`resolve_path_by_display_level` so
    off-tuple intermediates (subphylum / infraphylum / parvphylum /
    microphylum / megaclass / subfamily / tribe / subtribe /
    infratribe) fold into the parent bucket without dying on the
    walk. The roll-up rules applied to the children are:

    - **Rule 1 — phylum → class roll-up**: when the parent is a
      phylum and the children include any rank from
      :func:`_intermediate_ranks_for('phylum')` (subphylum,
      infraphylum, parvphylum, microphylum, megaclass), descend one
      level into each intermediate child and aggregate the
      ``class``-rank grandchildren with the direct ``class`` children.
    - **Rule 2 — subphylum collapse**: when the parent is a phylum
      whose only children are ``class``-rank, collapse to a single
      ``class`` tier (no subphylum picker).
    - **Rule 3 — family → genus roll-up**: when the parent is a
      family whose children include any rank from
      :func:`_intermediate_ranks_for('family')` (subfamily, tribe,
      subtribe, infratribe), descend breadth-first through each
      intermediate child and aggregate the ``genus``-rank descendants
      into a single ``genus`` tier.

    All other ranks keep the per-rank-group behaviour: one
    :class:`NextTier` per distinct rank label, ordered by the
    display-bucket sequence so the cascade UI renders the dropdowns
    in the canonical top-down order.
    """
    result = _resolve_path_internal(session, segments)
    if result.parent is None:
        return None
    parent_row = result.parent.row

    children_by_rank = _children_grouped_by_rank(session, parent_row.id)
    flat_children = [child for group in children_by_rank.values() for child in group]

    tier_rollup: list[NextTier] | None
    grouped_for_tiers: dict[str, list[TaxonRow]]
    if parent_row.rank.lower() == "phylum":
        grouped_for_tiers, tier_rollup = _phylum_rollup(session, children_by_rank)
    elif parent_row.rank.lower() == "family":
        grouped_for_tiers, tier_rollup = _family_rollup(session, children_by_rank)
    else:
        grouped_for_tiers = children_by_rank
        tier_rollup = None

    if tier_rollup is None:
        next_tiers = _build_tiers_from_grouping(grouped_for_tiers)
    else:
        next_tiers = tier_rollup

    flat_children = sorted(
        (child for group in grouped_for_tiers.values() for child in group),
        key=lambda r: (r.name.lower(), r.name),
    )

    parent_response = TaxonResponse.model_validate(parent_row)
    child_responses = [TaxonResponse.model_validate(row) for row in flat_children]
    return PathChildrenEnvelope(
        parent=parent_response,
        children=child_responses,
        next_tiers=next_tiers,
    )


def list_species_under_path(
    session: Session,
    segments: list[str],
    include: str | None,
    cursor: str | None,
) -> SpeciesListResponse:
    """Walk ``segments`` and return the species-tier leaf envelope.

    The path is walked via :func:`resolve_path_by_display_level`.
    When the deepest resolved taxon is a genus, every descendant at
    the ``species`` display bucket (species, subspecies, variety,
    form) is returned — the resolver rolls up to the display bucket
    rather than stopping at the strict ``species`` rank so the
    cascade UI surfaces every species-tier child.

    The function applies the same ``include`` filter and 500-row
    pagination cap as
    :func:`taxon.api.species.list_species_page`; the ``rank=`` filter
    is replaced by ``display_level='species'`` to roll up
    subspecies / variety / form descendants.
    """
    parent = resolve_path_by_display_level(session, segments)
    if parent is None:
        raise NotFoundError(f"taxon not found: {segments[-1]!r}")
    inclusion = parse_include(include)
    page = _list_species_page_under_parent(
        session,
        parent_id=parent.id,
        inclusion=inclusion,
        cursor=cursor,
    )
    return SpeciesListResponse(
        items=[
            SpeciesListItem(
                id=row.id,
                name=row.name,
                display_name=row.display_name,
                rank=row.rank,
                parent_id=row.parent_id,
                parent_segments=segments,
                is_synonym=row.is_synonym,
                is_extinct=row.is_extinct,
                is_uncertain=row.is_uncertain,
                is_unassigned=row.is_unassigned,
            )
            for row in page.rows
        ],
        next_cursor=page.next_cursor,
    )


def _list_species_page_under_parent(
    session: Session,
    *,
    parent_id: int,
    inclusion: InclusionFilter,
    cursor: str | None,
) -> SpeciesPage:
    """Paginate the display_level == ``species`` descendants of ``parent_id``.

    Mirror of :func:`taxon.api.species.list_species_page` that filters
    on ``display_level`` instead of ``rank`` so subspecies / variety /
    form descendants roll up alongside strict species rows. The
    function descends recursively through the species display bucket
    so multi-level species trees (species → subspecies) flatten into
    a single ordered list. The cursor encodes the canonical name so
    re-imports do not invalidate pagination state.
    """
    after_name: str | None = None
    if cursor:
        after_name = _decode_cursor(cursor)

    collected: list[TaxonRow] = _flatten_species_subtree(
        session,
        parent_id=parent_id,
        inclusion=inclusion,
    )
    collected.sort(key=lambda r: (r.name.lower(), r.name))

    start = 0
    if after_name is not None:
        # Binary search for the first row whose name is strictly
        # greater than the cursor's name. The list is already sorted
        # so a linear scan is fine for the typical <1000 rows case
        # the species-list endpoint handles.
        for idx, row in enumerate(collected):
            if row.name.lower() > after_name.lower():
                start = idx
                break
        else:
            start = len(collected)

    page_rows = collected[start : start + PAGE_CAP + 1]
    next_cursor: str | None = None
    if len(page_rows) > PAGE_CAP:
        page_rows = page_rows[:PAGE_CAP]
        next_cursor = _encode_cursor(page_rows[-1].name)
    return SpeciesPage(rows=page_rows, next_cursor=next_cursor)


def _flatten_species_subtree(
    session: Session,
    *,
    parent_id: int,
    inclusion: InclusionFilter,
) -> list[TaxonRow]:
    """Walk the species-tier subtree under ``parent_id`` and return every match.

    A species can be a parent of subspecies (also at the species
    display bucket); the cascade UI surfaces the entire subtree as
    one ordered list so the user can pick a leaf without first
    drilling through species → subspecies. The walk terminates when
    a level yields no further species-tier children.
    """
    collected: list[TaxonRow] = []
    frontier = [parent_id]
    seen: set[int] = set()
    while frontier:
        next_frontier: list[int] = []
        for node_id in frontier:
            if node_id in seen:
                continue
            seen.add(node_id)
            stmt = (
                select(Taxon)
                .where(Taxon.parent_id == node_id)
                .where(func.lower(Taxon.display_level) == "species")
                .where(inclusion.marker_predicate())
                .order_by(func.lower(Taxon.name), Taxon.name)
            )
            children = [_row_to_dataclass(t) for t in session.scalars(stmt).all()]
            for child in children:
                collected.append(child)
                next_frontier.append(child.id)
        if not next_frontier:
            break
        frontier = next_frontier
    return collected


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_path_internal(
    session: Session,
    segments: list[str],
) -> _PathResult:
    """Resolve the deepest segment against the local SQLite hierarchy.

    The cascade UI's first call uses ``/api/kingdoms`` (a separate
    endpoint); ``/api/path-children`` always receives a non-empty
    path. When the path starts with ``Biota`` or ``Viruses`` the
    resolver strips that segment (the synthesized roots do not have
    a real ``id`` to anchor on) and resolves the remainder against
    the SQLite hierarchy.

    ``None`` is returned when any non-root segment fails to resolve
    so the router emits a 404.
    """
    if not segments:
        return _PathResult(parent=None)

    remaining = list(segments)
    if remaining and remaining[0].lower() in {name.lower() for name, _ in _SYNTHETIC_ROOT_IDS}:
        remaining = remaining[1:]

    deepest = resolve_path_by_display_level(session, remaining)
    if deepest is None:
        return _PathResult(parent=None)
    return _PathResult(
        parent=_PathParent(row=deepest),
    )


def _children_grouped_by_rank(
    session: Session,
    parent_id: int,
) -> dict[str, list[TaxonRow]]:
    """Fetch every direct child of ``parent_id`` grouped by rank.

    A plain query without a ``display_level`` filter so off-tuple
    ranks surface in the grouping; the roll-up helpers decide which
    groups to collapse. Returns a dict keyed by lower-cased rank.
    """
    stmt = (
        select(Taxon)
        .where(Taxon.parent_id == parent_id)
        .order_by(func.lower(Taxon.name), Taxon.name)
    )
    grouped: dict[str, list[TaxonRow]] = {}
    for child in session.scalars(stmt).all():
        grouped.setdefault(child.rank.lower(), []).append(_row_to_dataclass(child))
    return grouped


def _row_to_dataclass(taxon: Taxon) -> TaxonRow:
    """Convert a SQLAlchemy ``Taxon`` row into a :class:`TaxonRow`.

    Mirrors :func:`taxon.api.hierarchy._to_row` but is duplicated here
    so this module stays decoupled from the legacy rank-anchored
    resolver. Both helpers produce identical dataclasses.
    """
    return TaxonRow(
        id=taxon.id,
        name=taxon.name,
        display_name=taxon.display_name,
        rank=taxon.rank,
        parent_id=taxon.parent_id,
        is_synonym=taxon.is_synonym,
        is_extinct=taxon.is_extinct,
        is_uncertain=taxon.is_uncertain,
        is_unassigned=taxon.is_unassigned,
    )


# Rank-by-rank roll-up rules. Each helper takes the children grouped
# by their actual rank and returns the wire-shaped grouping plus the
# tier list. The wire envelope exposes one tier per group; the roll-up
# helpers collapse intermediate ranks into a single tier so the
# cascade UI does not render empty dropdowns for off-tuple ranks.


def _phylum_rollup(
    session: Session,
    children_by_rank: dict[str, list[TaxonRow]],
) -> tuple[dict[str, list[TaxonRow]], list[NextTier] | None]:
    """Apply Rule 1 + Rule 2 to a phylum parent's children.

    Rule 1 fires when the phylum has any child at the off-tuple
    intermediate ranks (subphylum / infraphylum / parvphylum /
    microphylum / megaclass). The resolver descends through every
    intermediate child breadth-first until it reaches the
    ``class`` rank — multi-level descent handles real-world datasets
    that nest intermediates several tiers deep (e.g. Chordata →
    Vertebrata → Gnathostomata → Osteichthyes → Tetrapoda →
    Mammalia). Rule 2 fires when the phylum has only direct
    ``class`` children — the resolver still emits a single ``class``
    tier but skips the recursion.
    """
    intermediates = _intermediate_ranks_for("phylum")
    has_intermediates = any(rank in intermediates for rank in children_by_rank)

    if not has_intermediates:
        if "class" in children_by_rank and len(children_by_rank) == 1:
            class_children = children_by_rank["class"]
            return (
                {"class": class_children},
                [_build_tier("class", class_children)],
            )
        return children_by_rank, None

    aggregated_classes: list[TaxonRow] = _collect_descendants_by_rank(
        session,
        start_nodes=[child for rank in intermediates for child in children_by_rank.get(rank, [])],
        target_rank="class",
        intermediate_ranks=tuple(sorted(intermediates)),
    )
    aggregated_classes.extend(children_by_rank.get("class", []))

    if aggregated_classes:
        aggregated_classes = sorted(aggregated_classes, key=lambda r: (r.name.lower(), r.name))
        return (
            {"class": aggregated_classes},
            [_build_tier("class", aggregated_classes)],
        )

    return children_by_rank, None


def _family_rollup(
    session: Session,
    children_by_rank: dict[str, list[TaxonRow]],
) -> tuple[dict[str, list[TaxonRow]], list[NextTier] | None]:
    """Apply Rule 3 to a family parent's children.

    When the family has any child at the off-tuple intermediate
    ranks (subfamily / tribe / subtribe / infratribe), the resolver
    descends breadth-first through each, collects the ``genus``-rank
    descendants, and emits a single ``genus`` tier. When no
    ``genus`` descendants exist (e.g. a fossil family whose
    subfamily leaves are also leaves), the resolver falls back to
    the per-rank-group behaviour so the cascade UI renders the
    subfamily dropdown.
    """
    intermediates = _intermediate_ranks_for("family")
    has_intermediates = any(rank in intermediates for rank in children_by_rank)
    if not has_intermediates:
        return children_by_rank, None

    aggregated_genera: list[TaxonRow] = _collect_descendants_by_rank(
        session,
        start_nodes=[child for rank in intermediates for child in children_by_rank.get(rank, [])],
        target_rank="genus",
        intermediate_ranks=tuple(sorted(intermediates)),
    )

    if aggregated_genera:
        return (
            {"genus": aggregated_genera},
            [_build_tier("genus", aggregated_genera)],
        )
    return children_by_rank, None


def _collect_descendants_by_rank(
    session: Session,
    start_nodes: list[TaxonRow],
    *,
    target_rank: str,
    intermediate_ranks: tuple[str, ...],
) -> list[TaxonRow]:
    """Walk the subtree breadth-first and aggregate every ``target_rank`` descendant.

    The helper terminates when a level yields no new intermediate
    children — defensive against datasets that grow an extra rank
    not listed in ``intermediate_ranks``. The returned order mirrors
    the order each level emits the children so the cascade UI renders
    the genus dropdown in the same sequence the user would see in a
    tree walk.
    """
    if not start_nodes:
        return []
    collected: list[TaxonRow] = []
    frontier = list(start_nodes)
    intermediate_set = set(intermediate_ranks)
    while frontier:
        next_frontier: list[TaxonRow] = []
        for node in frontier:
            children = _children_grouped_by_rank(session, node.id)
            for rank, group in children.items():
                if rank == target_rank:
                    collected.extend(group)
                elif rank in intermediate_set:
                    next_frontier.extend(group)
        if not next_frontier:
            break
        frontier = next_frontier
    return collected


def _build_tiers_from_grouping(
    grouping: dict[str, list[TaxonRow]],
) -> list[NextTier]:
    """Build one :class:`NextTier` per rank group.

    The tier order mirrors the rank order within the grouping so the
    cascade UI renders dropdowns in the dataset's natural order. The
    ``label`` is the capitalised rank; ``examples`` carry up to three
    canonical names for tooltips.
    """
    tiers: list[NextTier] = []
    for rank, value in grouping.items():
        tiers.append(_build_tier(rank, value))
    return tiers


def _build_tier(rank: str, children: list[TaxonRow]) -> NextTier:
    """Build a single :class:`NextTier` from a rank label and its children."""
    return NextTier(
        rank=rank,
        label=_capitalize(rank),
        examples=[child.name for child in children[:3]],
        children=[TaxonResponse.model_validate(child) for child in children],
    )


def _capitalize(s: str) -> str:
    """Capitalise the first character of ``s`` (rest unchanged).

    Mirrors :func:`taxon.api.clb_path_children._capitalize` so the
    wire labels stay consistent across the CLB and SQLite backends.
    """
    if not s:
        return s
    return s[0].upper() + s[1:]


__all__ = [
    "list_kingdoms",
    "list_path_children",
    "list_species_under_path",
]
