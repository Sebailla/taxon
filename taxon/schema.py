"""SQLAlchemy models for the imported taxonomy and species projection."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MarkerColumns:
    is_synonym: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_extinct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_uncertain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_unassigned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Taxon(MarkerColumns, Base):
    __tablename__ = "taxa"
    __table_args__ = (
        Index("ix_taxa_parent_name", "parent_id", "name"),
        Index("ix_taxa_rank", "rank"),
        Index("ix_taxa_display_level", "display_level"),
        Index("ix_taxa_parent_rank_name", "parent_id", "rank", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("taxa.id"), nullable=True)
    rank: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    #: Cascade bucket for the UI. ``None`` when the rank is excluded
    #: from the cascade (unranked, historical ranks, year-numeric noise).
    #: See :mod:`taxon.taxonomy` for the mapping.
    display_level: Mapped[str | None] = mapped_column(String, nullable=True)


class SpeciesPath(MarkerColumns, Base):
    __tablename__ = "species_paths"
    __table_args__ = (Index("ix_species_paths_species", "species"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    species_id: Mapped[str] = mapped_column(
        ForeignKey("taxa.source_id"), nullable=False, unique=True
    )
    kingdom: Mapped[str | None] = mapped_column(String, nullable=True)
    phylum: Mapped[str | None] = mapped_column(String, nullable=True)
    class_name: Mapped[str | None] = mapped_column(String, nullable=True)
    order: Mapped[str | None] = mapped_column(String, nullable=True)
    family: Mapped[str | None] = mapped_column(String, nullable=True)
    genus: Mapped[str | None] = mapped_column(String, nullable=True)
    species: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)


class TaxonDescendantCount(Base):
    """Cached ``(species_count, total_count)`` for a threshold-exceeding parent.

    The ``descendant-counts-projection`` change materialises one row
    per taxon whose ``direct_children_count`` exceeds
    :data:`taxon.api.tree.SPECIES_COUNT_LAZY_NULL_THRESHOLD`. The
    projection is consulted on the read path before the threshold
    guard and the recursive CTE so :func:`taxon.api.tree._count_descendant_species`
    can serve cached ``species_count`` values in O(1) for ``Animalia``,
    ``Eukaryota``, ``Methanobacteriota`` and any future threshold-
    exceeding parent.

    Unlike the workspace tables in :mod:`taxon.api.workspace`, this
    row is keyed by ``taxa.id`` and is therefore invalidated by a
    re-import; :func:`taxon.api.projections.materialize_all` rebuilds
    it as the last step of ``taxon.import_data``.

    Schema mirrors :class:`SpeciesExplored` (``taxon/api/workspace.py``)
    for the ``computed_at`` column: SQLite has no ``TIMESTAMP`` type
    and the rest of the codebase normalises on ``String`` +
    ``datetime.now(UTC).isoformat(timespec="seconds")``.
    """

    __tablename__ = "taxon_descendant_counts"

    taxon_id: Mapped[int] = mapped_column(ForeignKey("taxa.id"), primary_key=True)
    species_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=lambda: datetime.now(UTC).isoformat(timespec="seconds"),
    )
