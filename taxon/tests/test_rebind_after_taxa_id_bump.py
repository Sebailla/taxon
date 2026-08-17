"""Pin that re-imports that recreate ``taxa`` do NOT invalidate workspace rows.

Issue #68 introduces three workspace tables that are keyed by
``(genus, epithet)`` re-bind columns — explicitly NOT by foreign keys
into ``taxa.id``. The reason: ``taxon.import_data`` rebuilds ``taxa``
from scratch on every run, which bumps ``taxa.id`` autoincrement
values. A foreign key into ``taxa.id`` would orphan every workspace
row on every re-import; the ``(genus, epithet)`` pair is the durable
identity instead.

The fixture simulates a re-import by mutating ``taxa.id`` for
``Panthera tigris`` (preserving the row but giving it a new id) and
asserts that every workspace read still resolves the same rows.
"""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from taxon.api.workspace import (
    WORKSPACE_TABLES,
    LinkVisited,
    SpeciesExplored,
    SpeciesFolder,
)
from taxon.schema import Base, Taxon


def _engine() -> Engine:
    from sqlalchemy import create_engine

    return create_engine("sqlite:///:memory:")


def _seed_lineage(session: Session) -> None:
    """Insert the bare-minimum lineage for ``Panthera tigris``."""
    session.add(
        Taxon(
            id=1,
            source_id="urn:1",
            parent_id=None,
            rank="kingdom",
            name="Animalia",
            display_name="Animalia",
        )
    )
    session.add(
        Taxon(
            id=2,
            source_id="urn:2",
            parent_id=1,
            rank="phylum",
            name="Chordata",
            display_name="Chordata",
        )
    )
    session.add(
        Taxon(
            id=3,
            source_id="urn:3",
            parent_id=2,
            rank="class",
            name="Mammalia",
            display_name="Mammalia",
        )
    )
    session.add(
        Taxon(
            id=4,
            source_id="urn:4",
            parent_id=3,
            rank="order",
            name="Carnivora",
            display_name="Carnivora",
        )
    )
    session.add(
        Taxon(
            id=5,
            source_id="urn:5",
            parent_id=4,
            rank="family",
            name="Felidae",
            display_name="Felidae",
        )
    )
    session.add(
        Taxon(
            id=6,
            source_id="urn:6",
            parent_id=5,
            rank="genus",
            name="Panthera",
            display_name="Panthera",
        )
    )
    session.add(
        Taxon(
            id=7,
            source_id="urn:7",
            parent_id=6,
            rank="species",
            name="Panthera tigris",
            display_name="Panthera tigris",
        )
    )
    session.commit()


def _bump_taxon_id(session: Session, *, old_id: int, new_id: int) -> None:
    """Simulate the re-import churn by reassigning ``taxa.id`` for ``Panthera tigris``.

    The session's identity map MUST be cleared so a fresh SELECT after
    the bump returns the new id. SQLAlchemy's ``session.expire_all``
    forces the next attribute access to re-query.
    """
    from sqlalchemy import text as sql_text

    # Re-parent the species row to a new id so any FK that survived
    # would have to point at the new id. The parent chain stays the
    # same — only ``Panthera tigris.id`` is bumped.
    session.execute(
        sql_text("UPDATE taxa SET id = :new WHERE id = :old"),
        {"new": new_id, "old": old_id},
    )
    session.commit()
    session.expire_all()


def test_explored_row_survives_taxa_id_bump() -> None:
    """``species_explored`` row remains queryable after a manual ``taxa.id`` bump."""
    from taxon.api.workspace import set_explored

    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_lineage(session)
        set_explored(session, genus="Panthera", epithet="tigris")

    with Session(engine) as session:
        _bump_taxon_id(session, old_id=7, new_id=99)
        row = session.get(SpeciesExplored, ("Panthera", "tigris"))

    assert row is not None
    assert row.genus == "Panthera"
    assert row.epithet == "tigris"


def test_species_folder_row_survives_taxa_id_bump() -> None:
    """``species_folders`` row remains queryable after a manual ``taxa.id`` bump."""
    from taxon.api.workspace import create_species_folder, get_species_folder

    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_lineage(session)
        create_species_folder(session, genus="Panthera", epithet="tigris")

    with Session(engine) as session:
        _bump_taxon_id(session, old_id=7, new_id=99)
        row = get_species_folder(session, genus="Panthera", epithet="tigris")

    assert row is not None
    assert row.genus == "Panthera"
    assert row.epithet == "tigris"
    assert row.path


def test_link_visited_rows_survive_taxa_id_bump() -> None:
    """``link_visited`` rows remain queryable after a manual ``taxa.id`` bump."""
    from taxon.api.workspace import (
        list_link_visited,
        record_link_visited,
    )

    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_lineage(session)
        record_link_visited(session, genus="Panthera", epithet="tigris", source="Wikipedia")
        record_link_visited(session, genus="Panthera", epithet="tigris", source="Google")

    with Session(engine) as session:
        _bump_taxon_id(session, old_id=7, new_id=99)
        rows = list_link_visited(session, genus="Panthera", epithet="tigris")

    sources = sorted(row.source_label for row in rows)
    assert sources == ["Google", "Wikipedia"]


def test_workspace_tables_have_no_fk_to_taxa_id() -> None:
    """The three workspace tables declare no foreign key into ``taxa``.

    The re-bind discipline is only meaningful when no FK exists to
    invalidate; this is the structural pin that protects the rebind
    tests above from regression.
    """
    from sqlalchemy import ForeignKeyConstraint

    for model in (SpeciesExplored, SpeciesFolder, LinkVisited):
        fks = list(model.__table__.foreign_keys)
        fk_constraints = [
            c
            for c in model.__table__.constraints  # type: ignore[attr-defined]
            if isinstance(c, ForeignKeyConstraint)
        ]
        assert not fks, f"{model.__name__} has FKs: {fks}"
        assert not fk_constraints, f"{model.__name__} has ForeignKeyConstraint: {fk_constraints}"


def test_workspace_tables_constant_excludes_taxa_and_species_paths() -> None:
    """The :data:`WORKSPACE_TABLES` constant enumerates ONLY the three new tables.

    Operators rely on this constant to bootstrap just the workspace
    tables without touching ``taxa`` or ``species_paths``; if it ever
    silently grew to include those, a re-run of ``taxon.migrate apply``
    could mask pre-existing data churn.
    """
    assert "taxa" not in WORKSPACE_TABLES
    assert "species_paths" not in WORKSPACE_TABLES
