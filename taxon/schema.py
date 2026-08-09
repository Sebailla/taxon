"""SQLAlchemy models for the imported taxonomy and species projection."""

from __future__ import annotations

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
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("taxa.id"), nullable=True)
    rank: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)


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
