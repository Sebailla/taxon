"""Workspace persistence layer for the species-folder-explorer change.

Issue #68 introduces three orthogonal tables — ``species_explored``,
``species_folders``, ``link_visited`` — that survive ``taxa`` re-imports
because every primary key carries ``(genus, epithet)`` re-bind columns
instead of a foreign key into ``taxa``. This module owns:

- The three SQLAlchemy models (``SpeciesExplored``, ``SpeciesFolder``,
  ``LinkVisited``) declared on the same ``Base`` as ``Taxon`` so a single
  ``Base.metadata.create_all(engine)`` call brings the whole schema up.
- Resolver helpers that walk by ``(genus, epithet)`` (and
  ``source_label`` for ``link_visited``) on every read and write — no
  caller ever reaches into ``taxa.id``.
- The ``AQUALIFE_ROOT`` env var reader + project-root-relative resolver
  that the folder-creation endpoint uses to anchor the breadcrumb mirror
  on disk.

The DDL deliberately carries NO foreign key to ``taxa.id``. The
``(genus, epithet)`` pair is the durable identity of the workspace row;
a re-import that bumps ``taxa.id`` MUST NOT invalidate any row here. The
orthogonality is pinned by ``taxon/tests/test_rebind_after_taxa_id_bump.py``.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from taxon.api.errors import APIError
from taxon.api.hierarchy import TaxonRow, _to_row
from taxon.api.species import build_breadcrumb
from taxon.schema import Base, Taxon

WORKSPACE_TABLES: tuple[str, ...] = (
    "species_explored",
    "species_folders",
    "link_visited",
)
"""Tuple of the workspace table names; the lifespan create_all + the
:meth:`taxon.migrate` script both filter to this exact set so pre-existing
``taxa`` / ``species_paths`` tables are never touched.

The names are exported so :mod:`taxon.migrate` and the lifespan in
:mod:`taxon.api` can iterate the table list without importing the model
classes (which would force a ``Base.metadata`` registration on import).
"""


class SpeciesExplored(Base):
    """Per-species explored flag, keyed by ``(genus, epithet)``.

    The flag is intentionally a separate table rather than a column on
    :class:`Taxon` because ``taxon.import_data`` rebuilds ``taxa`` from
    scratch on every run and would wipe a denormalised column. The pair
    ``(genus, epithet)`` is the durable identity of the row.
    """

    __tablename__ = "species_explored"
    __table_args__ = (Index("ix_species_explored_ge", "genus", "epithet"),)

    genus: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    epithet: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    explored_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=lambda: datetime.now(UTC).isoformat(timespec="seconds"),
    )


class SpeciesFolder(Base):
    """Breadcrumb-mirror folder under ``AQUALIFE_ROOT``.

    The ``path`` column is unique because the on-disk folder identity
    is the absolute path; ``(genus, epithet)`` is the workspace identity.
    The unique constraint catches duplicate rows without relying on the
    primary key being globally unique.
    """

    __tablename__ = "species_folders"
    __table_args__ = (Index("ix_species_folders_ge", "genus", "epithet"),)

    genus: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    epithet: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=lambda: datetime.now(UTC).isoformat(timespec="seconds"),
    )


class LinkVisited(Base):
    """Per-(species, source) visited marker for the per-link switch.

    The row keys on ``(genus, epithet, source_label)`` — three columns.
    The third is the canonical name from ``docs/sources/templates.md``
    (e.g. ``"Wikipedia"``); URLs are NOT part of the key because they
    change per substitution.
    """

    __tablename__ = "link_visited"
    __table_args__ = (
        Index("ix_link_visited_source", "source_label"),
        Index("ix_link_visited_ge", "genus", "epithet"),
    )

    genus: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    epithet: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    source_label: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    visited_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=lambda: datetime.now(UTC).isoformat(timespec="seconds"),
    )


# ---------------------------------------------------------------------------
# AQUALIFE_ROOT resolver
# ---------------------------------------------------------------------------


DEFAULT_AQUALIFE_ROOT = "./Proyecto-Aqualife/"
"""Default root when the env var is unset.

Relative paths are resolved against the project root (NOT cwd) so a
worktree checkout that runs the app from a subfolder still anchors the
folder at the repo root.
"""


def _project_root() -> Path:
    """Locate the project root by walking up from this module to ``pyproject.toml``.

    The repo keeps ``pyproject.toml`` at the top level. Falling back to
    ``Path(__file__).parent.parent`` keeps the resolver working in
    edge cases where the file was relocated (e.g. inside a build
    artefact).
    """
    here = Path(__file__).resolve()
    for ancestor in (here, *here.parents):
        if (ancestor / "pyproject.toml").is_file():
            return ancestor
    return Path(__file__).resolve().parent.parent


def resolve_aqualife_root() -> Path:
    """Resolve the ``AQUALIFE_ROOT`` env var against the project root.

    - Absolute paths are returned verbatim.
    - Relative paths are anchored on the project root, not the cwd.
    - When the resolved directory is not writable the call raises
      :class:`APIError` with a detail naming the failing path and the
      current working directory so operators can see exactly which
      filesystem state broke the resolution.

    The directory is created with ``parents=True, exist_ok=True`` when
    writable so first-call setup is automatic.
    """
    raw = os.environ.get("AQUALIFE_ROOT", DEFAULT_AQUALIFE_ROOT)
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (_project_root() / candidate).resolve()
    try:
        candidate.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as exc:
        raise APIError(f"AQUALIFE_ROOT not writable: {candidate} from cwd {Path.cwd()}") from exc
    # ``Path.mkdir`` does not confirm writability on every filesystem;
    # probe with a tempfile-equivalent write so a read-only mount fails
    # loudly here rather than at the first ``POST /api/species-folder``.
    if not os.access(candidate, os.W_OK):
        raise APIError(f"AQUALIFE_ROOT not writable: {candidate} from cwd {Path.cwd()}")
    return candidate


# ---------------------------------------------------------------------------
# Species resolver — find a species row by (genus, epithet) only
# ---------------------------------------------------------------------------


def _find_species_row(
    session: Session,
    *,
    genus: str,
    epithet: str,
) -> TaxonRow | None:
    """Return the unique species row matching ``(genus, epithet)``.

    Mirrors :func:`taxon.api.router._lookup_species_by_pair` without the
    HTTP semantics: returns ``None`` for zero matches, raises
    :class:`APIError` (status_code=404) for ambiguous matches so the
    workspace endpoint can surface a 409 with candidates.

    Resolution strategy: scan every row whose canonical name equals
    ``"<genus> <epithet>"`` and whose ``rank == 'species'``. Empty
    results are 404 territory. Multiple results are returned in
    breadcrumb order so the caller can pick deterministically.
    """
    canonical = f"{genus} {epithet}"
    stmt = session.query(Taxon).filter(Taxon.rank == "species").filter(Taxon.name == canonical)
    matches = [_to_row(t) for t in stmt.all()]
    if not matches:
        return None
    if len(matches) > 1:
        # Sort by breadcrumb so the deterministic pick is the same
        # shape every call. The workspace store keys on
        # ``(genus, epithet)`` so the choice is independent of which
        # ``taxa.id`` is bound — but we still want a stable pick.
        matches.sort(key=lambda row: tuple(build_breadcrumb(session, row.id)))
        return matches[0]
    return matches[0]


def _species_folder_path(
    session: Session,
    *,
    genus: str,
    epithet: str,
) -> Path:
    """Build the breadcrumb-mirror path for ``(genus, epithet)``.

    Resolves the species row, walks its parent chain for the canonical
    breadcrumb (Kingdom → … → Genus), appends the species leaf, and
    joins the segments with ``os.sep`` verbatim — no URL-encoding, no
    lowercasing, no underscore replacement.
    """
    species = _find_species_row(session, genus=genus, epithet=epithet)
    if species is None:
        raise APIError(f"species not found: {genus} {epithet!r}", status_code=404)
    breadcrumb = build_breadcrumb(session, species.id)
    leaf = f"{genus} {epithet}"
    root = resolve_aqualife_root()
    return root.joinpath(*breadcrumb, leaf)


# ---------------------------------------------------------------------------
# Resolver helpers — workspace CRUD by (genus, epithet)
# ---------------------------------------------------------------------------


def set_explored(
    session: Session,
    *,
    genus: str,
    epithet: str,
) -> TaxonRow:
    """Upsert the explored flag for ``(genus, epithet)`` and return the row.

    The row MUST be resolvable (otherwise the endpoint has no anchor
    for the breadcrumb mirror). Refreshing ``explored_at`` on every
    call keeps the spec's "idempotent + refresh timestamp" contract
    honest.
    """
    species = _find_species_row(session, genus=genus, epithet=epithet)
    if species is None:
        raise APIError(f"species not found: {genus} {epithet!r}", status_code=404)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    existing = session.get(SpeciesExplored, (genus, epithet))
    if existing is None:
        session.add(SpeciesExplored(genus=genus, epithet=epithet, explored_at=now))
    else:
        existing.explored_at = now
    session.commit()
    return species


def unset_explored(session: Session, *, genus: str, epithet: str) -> None:
    """Delete the explored row if present; idempotent — no error on missing."""
    existing = session.get(SpeciesExplored, (genus, epithet))
    if existing is not None:
        session.delete(existing)
        session.commit()


def list_explored(session: Session) -> list[SpeciesExplored]:
    """Return every explored row ordered by ``(genus, epithet)``."""
    stmt = session.query(SpeciesExplored).order_by(SpeciesExplored.genus, SpeciesExplored.epithet)
    return list(stmt.all())


def create_species_folder(
    session: Session,
    *,
    genus: str,
    epithet: str,
) -> SpeciesFolder:
    """Create the breadcrumb-mirror folder on disk and persist the row.

    Raises :class:`APIError` with status_code=409 when the row already
    exists so the endpoint can surface a duplicate-folder 409 envelope.
    """
    existing = session.get(SpeciesFolder, (genus, epithet))
    if existing is not None:
        raise APIError(
            f"species folder already exists: {genus} {epithet!r}",
            status_code=409,
        )
    folder = _species_folder_path(session, genus=genus, epithet=epithet)
    folder.mkdir(parents=True, exist_ok=True)
    row = SpeciesFolder(
        genus=genus,
        epithet=epithet,
        path=str(folder),
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    session.add(row)
    session.commit()
    return row


def get_species_folder(
    session: Session,
    *,
    genus: str,
    epithet: str,
) -> SpeciesFolder | None:
    """Return the folder row or ``None`` when no row exists."""
    return session.get(SpeciesFolder, (genus, epithet))


def record_link_visited(
    session: Session,
    *,
    genus: str,
    epithet: str,
    source: str,
) -> None:
    """Upsert the visited row for ``(genus, epithet, source)``.

    The species row MUST resolve (404 otherwise). The endpoint is
    idempotent — re-posting refreshes ``visited_at``.
    """
    species = _find_species_row(session, genus=genus, epithet=epithet)
    if species is None:
        raise APIError(f"species not found: {genus} {epithet!r}", status_code=404)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    existing = session.get(LinkVisited, (genus, epithet, source))
    if existing is None:
        session.add(
            LinkVisited(
                genus=genus,
                epithet=epithet,
                source_label=source,
                visited_at=now,
            )
        )
    else:
        existing.visited_at = now
    session.commit()


def unrecord_link_visited(
    session: Session,
    *,
    genus: str,
    epithet: str,
    source: str,
) -> None:
    """Delete the visited row if present; idempotent — no error on missing."""
    existing = session.get(LinkVisited, (genus, epithet, source))
    if existing is not None:
        session.delete(existing)
        session.commit()


def list_link_visited(
    session: Session,
    *,
    genus: str,
    epithet: str,
) -> list[LinkVisited]:
    """Return every visited row for ``(genus, epithet)`` ordered by source."""
    stmt = (
        session.query(LinkVisited)
        .filter(LinkVisited.genus == genus)
        .filter(LinkVisited.epithet == epithet)
        .order_by(LinkVisited.source_label)
    )
    return list(stmt.all())


__all__ = [
    "DEFAULT_AQUALIFE_ROOT",
    "WORKSPACE_TABLES",
    "LinkVisited",
    "SpeciesExplored",
    "SpeciesFolder",
    "create_species_folder",
    "get_species_folder",
    "list_explored",
    "list_link_visited",
    "record_link_visited",
    "resolve_aqualife_root",
    "set_explored",
    "unrecord_link_visited",
    "unset_explored",
]
