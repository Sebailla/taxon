"""RED-first contract tests for the workspace DDL shape.

Issue #68 introduces three workspace tables —
 :class:`SpeciesExplored`, :class:`SpeciesFolder`, :class:`LinkVisited` —
 all keyed by ``(genus, epithet)`` re-bind columns so they survive the
 ``taxon.import_data`` re-import churn.

These tests pin the shape that is critical to that promise:

- Each table carries ``PRIMARY KEY (genus, epithet)`` (and
  ``source_label`` for ``link_visited``); no other column is part of
  the primary key.
- None of the three tables carries a foreign key into ``taxa.id`` —
  the ``(genus, epithet)`` pair is the durable identity.
- ``Base.metadata.create_all(engine)`` creates all three tables; the
  pre-existing ``taxa`` / ``species_paths`` tables are left untouched.
- The :data:`WORKSPACE_TABLES` constant names the exact table set so
  ``taxon.migrate`` and the lifespan use the same filter.
"""

from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from taxon.api.workspace import (
    WORKSPACE_TABLES,
    LinkVisited,
    SpeciesExplored,
    SpeciesFolder,
)
from taxon.schema import Base


def _engine() -> Engine:
    """In-memory SQLite engine that mirrors the lifespan bootstrap shape."""
    from sqlalchemy import create_engine

    return create_engine("sqlite:///:memory:")


def test_workspace_models_registered_on_base_metadata() -> None:
    """Importing the workspace module registers all three tables on ``Base.metadata``.

    The lifespan's ``Base.metadata.create_all`` for the workspace set
    only works when the models are registered. This test catches the
    regression where someone forgets to subclass :class:`Base`.
    """
    table_names = set(Base.metadata.tables.keys())
    assert "species_explored" in table_names
    assert "species_folders" in table_names
    assert "link_visited" in table_names


def test_workspace_tables_constant_matches_metadata() -> None:
    """:data:`WORKSPACE_TABLES` enumerates exactly the three new tables."""
    assert set(WORKSPACE_TABLES) == {"species_explored", "species_folders", "link_visited"}


def test_create_all_brings_up_three_new_tables() -> None:
    """``Base.metadata.create_all(engine)`` creates the three new tables."""
    engine = _engine()
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables[name] for name in WORKSPACE_TABLES]
    )
    inspector = inspect(engine)
    created = set(inspector.get_table_names())
    assert {"species_explored", "species_folders", "link_visited"}.issubset(created)


def test_species_explored_primary_key_is_genus_epithet() -> None:
    """:class:`SpeciesExplored` carries PRIMARY KEY ``(genus, epithet)`` only.

    The composite primary key is what makes the row orthogonal to
    ``taxa.id`` — bumping ``taxa.id`` does not invalidate this row.
    """
    pk_columns = [col.name for col in SpeciesExplored.__table__.primary_key.columns]
    assert pk_columns == ["genus", "epithet"], pk_columns


def test_species_folders_primary_key_is_genus_epithet() -> None:
    """:class:`SpeciesFolder` carries PRIMARY KEY ``(genus, epithet)`` only.

    The ``path`` column is UNIQUE but NOT part of the primary key;
    keys on ``(genus, epithet)`` so re-imports do not orphan rows.
    """
    pk_columns = [col.name for col in SpeciesFolder.__table__.primary_key.columns]
    assert pk_columns == ["genus", "epithet"], pk_columns


def test_link_visited_primary_key_is_genus_epithet_source() -> None:
    """:class:`LinkVisited` carries PRIMARY KEY ``(genus, epithet, source_label)``.

    The third column is the canonical source name (NOT the URL) so
    the row identity is stable across per-substitution URL changes.
    """
    pk_columns = [col.name for col in LinkVisited.__table__.primary_key.columns]
    assert pk_columns == ["genus", "epithet", "source_label"], pk_columns


def test_species_explored_has_no_foreign_key_to_taxa() -> None:
    """:class:`SpeciesExplored` has NO foreign key into ``taxa``."""
    _assert_no_foreign_keys(SpeciesExplored)


def test_species_folders_has_no_foreign_key_to_taxa() -> None:
    """:class:`SpeciesFolder` has NO foreign key into ``taxa``."""
    _assert_no_foreign_keys(SpeciesFolder)


def test_link_visited_has_no_foreign_key_to_taxa() -> None:
    """:class:`LinkVisited` has NO foreign key into ``taxa``."""
    _assert_no_foreign_keys(LinkVisited)


def _assert_no_foreign_keys(model: type[Base]) -> None:
    """Raise AssertionError when ``model`` declares any foreign key."""
    fks = list(model.__table__.foreign_keys)
    assert not fks, (
        f"{model.__name__} must not declare foreign keys (workspace tables are "
        f"orthogonal to taxa); found: {fks}"
    )
    # ``ForeignKeyConstraint`` covers explicit-table-level constraints
    # that don't appear on individual columns.
    fk_constraints = [c for c in model.__table__.constraints if isinstance(c, ForeignKeyConstraint)]
    assert not fk_constraints, (
        f"{model.__name__} must not declare ForeignKeyConstraint; found: {fk_constraints}"
    )


def test_species_folders_path_column_is_unique() -> None:
    """The ``path`` column carries a UNIQUE constraint.

    The on-disk folder identity is the absolute path; the unique
    constraint catches duplicate rows when the same folder is recorded
    via two distinct (genus, epithet) entries by accident.
    """
    path_column = SpeciesFolder.__table__.columns["path"]
    assert path_column.unique is True


def test_set_explored_persists_by_genus_epithet() -> None:
    """:func:`set_explored` upserts a row keyed by ``(genus, epithet)``.

    The fixture imports a tiny synthetic lineage so the species row
    is resolvable; the assertion is that the row lands in the table
    after a single POST-equivalent call.
    """
    from taxon.api.workspace import set_explored

    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_panthera_tigris(session)
        session.commit()

    with Session(engine) as session:
        set_explored(session, genus="Panthera", epithet="tigris")
    with Session(engine) as session:
        row = session.get(SpeciesExplored, ("Panthera", "tigris"))
        assert row is not None
        assert row.genus == "Panthera"
        assert row.epithet == "tigris"


def test_unset_explored_is_idempotent_on_missing_row() -> None:
    """:func:`unset_explored` is a no-op when no row exists."""
    from taxon.api.workspace import unset_explored

    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        unset_explored(session, genus="Panthera", epithet="tigris")


def test_list_explored_returns_rows_in_order() -> None:
    """:func:`list_explored` returns every row ordered by ``(genus, epithet)``."""
    from taxon.api.workspace import list_explored, set_explored

    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_panthera_tigris(session)
        _seed_panthera_leo(session)
        session.commit()
    with Session(engine) as session:
        set_explored(session, genus="Panthera", epithet="leo")
        set_explored(session, genus="Panthera", epithet="tigris")
    with Session(engine) as session:
        rows = list_explored(session)
        keys = [(r.genus, r.epithet) for r in rows]
    assert keys == [("Panthera", "leo"), ("Panthera", "tigris")]


def test_create_species_folder_persists_row() -> None:
    """:func:`create_species_folder` inserts a ``SpeciesFolder`` row and creates the folder."""
    from taxon.api.workspace import create_species_folder

    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_panthera_tigris(session)
        session.commit()

    with Session(engine) as session:
        row = create_species_folder(session, genus="Panthera", epithet="tigris")
        # Inspect inside the session to avoid detached-instance errors.
        genus = row.genus
        epithet = row.epithet
        path = row.path
    assert genus == "Panthera"
    assert epithet == "tigris"
    assert path
    assert path.endswith("Panthera tigris")


def test_create_species_folder_repeat_raises_409() -> None:
    """A repeat :func:`create_species_folder` call raises :class:`APIError` with status_code=409."""
    import pytest

    from taxon.api.errors import APIError
    from taxon.api.workspace import create_species_folder

    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_panthera_tigris(session)
        session.commit()

    with Session(engine) as session:
        create_species_folder(session, genus="Panthera", epithet="tigris")
    with Session(engine) as session, pytest.raises(APIError) as exc_info:
        create_species_folder(session, genus="Panthera", epithet="tigris")
    assert exc_info.value.status_code == 409


def test_record_link_visited_keys_on_source_label() -> None:
    """:func:`record_link_visited` keys on ``source_label`` (not URL)."""
    from taxon.api.workspace import record_link_visited

    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_panthera_tigris(session)
        session.commit()

    with Session(engine) as session:
        record_link_visited(session, genus="Panthera", epithet="tigris", source="Wikipedia")
    with Session(engine) as session:
        row = session.get(LinkVisited, ("Panthera", "tigris", "Wikipedia"))
    assert row is not None
    assert row.source_label == "Wikipedia"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


PANTHERA_TIGRIS_FIXTURE = (
    "Biota [superdomain] {ID=urn:0}\n"
    "  Animalia [kingdom] {ID=urn:1}\n"
    "    Chordata [phylum] {ID=urn:2}\n"
    "      Mammalia [class] {ID=urn:3}\n"
    "        Carnivora [order] {ID=urn:4}\n"
    "          Felidae [family] {ID=urn:5}\n"
    "            Panthera [genus] {ID=urn:6}\n"
    "              Panthera tigris [species] {ID=urn:7}\n"
    "              Panthera leo [species] {ID=urn:8}\n"
)


def _seed_panthera_tigris(session: Session) -> None:
    """Insert the bare-minimum lineage for ``Panthera tigris``.

    Direct DB writes keep the workspace tests independent of the
    indented-import parser so a parser regression cannot mask a
    workspace regression.
    """
    from taxon.schema import Taxon

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


def _seed_panthera_leo(session: Session) -> None:
    from taxon.schema import Taxon

    session.add(
        Taxon(
            id=8,
            source_id="urn:8",
            parent_id=6,
            rank="species",
            name="Panthera leo",
            display_name="Panthera leo",
        )
    )
