from datetime import datetime
from typing import Any, cast

from sqlalchemy import Boolean, String, create_engine, inspect
from sqlalchemy.orm import Session
from sqlalchemy.sql.schema import Column

from taxon.schema import Base, SpeciesPath, Taxon, TaxonDescendantCount


def test_taxon_model_persists_parent_markers_and_required_indexes() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        root = Taxon(
            source_id="urn:root",
            parent_id=None,
            rank="kingdom",
            name="Animalia",
            display_name="Animalia [kingdom]",
        )
        session.add(root)
        session.flush()
        child = Taxon(
            source_id="urn:species",
            parent_id=root.id,
            rank="species",
            name="Example species",
            display_name="=†Example species [species]",
            is_synonym=True,
            is_extinct=True,
        )
        session.add(child)
        session.commit()

        stored = session.get(Taxon, child.id)
        assert stored is not None
        assert stored.parent_id == root.id
        assert stored.is_synonym is True
        assert stored.is_extinct is True
        assert stored.is_uncertain is False
        assert stored.is_unassigned is False

    inspector = inspect(engine)
    index_columns = {tuple(index["column_names"]) for index in inspector.get_indexes("taxa")}
    assert ("parent_id", "name") in index_columns
    assert ("rank",) in index_columns


def test_species_path_has_complete_breadcrumb_markers_and_species_index() -> None:
    columns = SpeciesPath.__table__.columns

    assert set(columns.keys()) == {
        "id",
        "species_id",
        "kingdom",
        "phylum",
        "class_name",
        "order",
        "family",
        "genus",
        "species",
        "display_name",
        "is_synonym",
        "is_extinct",
        "is_uncertain",
        "is_unassigned",
    }
    assert isinstance(columns["species_id"].type, String)
    assert isinstance(columns["is_synonym"].type, Boolean)
    assert {foreign_key.target_fullname for foreign_key in columns["species_id"].foreign_keys} == {
        "taxa.source_id"
    }
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    species_index_columns = {
        tuple(index["column_names"]) for index in inspector.get_indexes("species_paths")
    }
    assert ("species",) in species_index_columns


# ---------------------------------------------------------------------------
# descendant-counts-projection: TaxonDescendantCount ORM
# ---------------------------------------------------------------------------
#
# Pins the new ``taxon_descendant_counts`` table that materialises
# ``(species_count, total_count)`` for every parent whose
# ``direct_children_count`` exceeds ``SPECIES_COUNT_LAZY_NULL_THRESHOLD``.
# The schema lives on ``Base.metadata`` next to ``Taxon`` and
# ``SpeciesPath`` because the projection is FK'd to ``taxa.id`` and is
# invalidated by a re-import — same lifecycle as ``SpeciesPath``.


def test_taxon_descendant_count_table_exists_with_four_columns() -> None:
    """``TaxonDescendantCount`` declares the four columns the spec pins.

    The projection carries exactly: ``taxon_id`` (PK, FK to ``taxa.id``),
    ``species_count`` (INT), ``total_count`` (INT), and ``computed_at``
    (ISO-8601 string). No secondary indexes — ``taxon_id`` is the
    primary key and every access is a point lookup or an ``IN``-list
    over the PK.
    """
    columns = TaxonDescendantCount.__table__.columns
    assert set(columns.keys()) == {"taxon_id", "species_count", "total_count", "computed_at"}


def test_taxon_descendant_count_pk_is_taxon_id() -> None:
    """``taxon_id`` is the PRIMARY KEY and FK to ``taxa.id``.

    The single-column PK is the rowid B-tree, which is sufficient for
    every read path the production code uses (point lookup by PK or
    ``IN``-list over PKs). The FK to ``taxa.id`` enforces referential
    integrity: a re-import that drops `taxa` rows cascades the
    projection rows via the FK relationship.
    """
    pk_cols = cast(list[Column[Any]], list(TaxonDescendantCount.__table__.primary_key.columns))  # type: ignore[attr-defined]
    assert [col.name for col in pk_cols] == ["taxon_id"]
    fk_targets = {fk.target_fullname for fk in TaxonDescendantCount.__table__.foreign_keys}
    assert "taxa.id" in fk_targets


def test_taxon_descendant_count_computed_at_default_is_iso8601_string() -> None:
    """``computed_at`` defaults to an ISO-8601 UTC string.

    SQLite has no TIMESTAMP type, and the rest of the codebase
    normalises on ``String`` + ``datetime.now(UTC).isoformat(...)
    (``SpeciesExplored.explored_at`` in
    ``taxon/api/workspace.py:67``). The default must produce a string
    that ``datetime.fromisoformat`` can round-trip.
    """
    computed_at_col = TaxonDescendantCount.__table__.columns["computed_at"]
    assert isinstance(computed_at_col.type, String)
    # The default is a lambda; SQLAlchemy invokes it with a single
    # ``ExecutableContext`` argument at row-insert time. The lambda
    # must ignore that argument and return the ISO-8601 string.
    default_callable = computed_at_col.default.arg
    assert callable(default_callable)
    # Round-trip: the lambda must produce something ``fromisoformat``
    # can parse back to a datetime. SQLAlchemy passes a context object
    # at insert time; we pass ``None`` here as a stand-in.
    produced = default_callable(None)
    assert isinstance(produced, str)
    parsed = datetime.fromisoformat(produced)
    assert parsed.tzinfo is not None
    # The default was authored to use ``timespec="seconds"``; the
    # produced string MUST NOT carry microseconds or the wire surface
    # becomes noisy.
    assert "." not in produced, f"computed_at default must use timespec=seconds; got {produced!r}"
