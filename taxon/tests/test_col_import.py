"""Integration tests for the CoL DwC-A import path.

These tests use the small real-row fixture under
``tests/fixtures/col_subset.tsv`` to exercise the full SQLite
ingestion path: parser → ``Taxon`` rows → parent-id wiring →
``SpeciesPath`` rows.

The fixture has 34 rows across 6 canonical ranks plus a synonym
and an extinct species, mixed in non-depth-first order (CoL
delivers rows unordered). The import is expected to handle that
without manual pre-sorting.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from taxon.col_import import import_col_dataset
from taxon.schema import SpeciesPath, Taxon

FIXTURE = Path(__file__).parent / "fixtures" / "col_subset.tsv"


def fixture_lines() -> Iterable[str]:
    with FIXTURE.open(encoding="utf-8", newline="") as file:
        yield from file


def test_col_import_persists_all_fixture_rows(tmp_path: Path) -> None:
    database = tmp_path / "taxon.db"

    counts = import_col_dataset(FIXTURE, database)

    assert counts.total_taxa == 63
    engine = create_engine(f"sqlite:///{database}")
    with Session(engine) as session:
        rows = session.scalars(select(Taxon)).all()
        assert len(rows) == 63


def test_col_import_wires_parent_ids_via_two_pass_strategy(tmp_path: Path) -> None:
    """CoL rows arrive out of order; the importer must resolve parent
    source_ids even when the parent row appears later in the file."""
    database = tmp_path / "taxon.db"

    import_col_dataset(FIXTURE, database)

    engine = create_engine(f"sqlite:///{database}")
    with Session(engine) as session:
        # NNWV (species) parent should be 84LYY (its genus).
        nnwv = session.scalar(select(Taxon).where(Taxon.source_id == "NNWV"))
        assert nnwv is not None
        parent = session.get(Taxon, nnwv.parent_id)
        assert parent is not None
        assert parent.source_id == "84LYY"


def test_col_import_projects_species_paths_from_resolved_columns(tmp_path: Path) -> None:
    """CoL populates kingdom → genus per row in its own columns, so the
    importer does not need a recursive walk to build the breadcrumb."""
    database = tmp_path / "taxon.db"

    import_col_dataset(FIXTURE, database)

    engine = create_engine(f"sqlite:///{database}")
    with Session(engine) as session:
        paths = session.scalars(select(SpeciesPath)).all()
        # The fixture has 18 species rows (15 from the original
        # WoRMS-style seed plus 3 from the appended parents).
        assert len(paths) == 18

        # Buffonellaria cornuta (NNWV) — extinct, kingdom Animalia,
        # phylum Bryozoa (its phylum is column 64 of the fixture).
        nnwv_path = session.scalar(select(SpeciesPath).where(SpeciesPath.species_id == "NNWV"))
        assert nnwv_path is not None
        assert nnwv_path.kingdom == "Animalia"
        assert nnwv_path.species == "Buffonellaria cornuta"
        assert nnwv_path.is_extinct is True
        assert nnwv_path.genus == "Buffonellaria"
        assert nnwv_path.display_name == "Buffonellaria cornuta Guha & Gopikrishna, 2007"


def test_col_import_marks_synonym_status(tmp_path: Path) -> None:
    """63J5L is the genus Paracoccidium with status=synonym in the fixture."""
    database = tmp_path / "taxon.db"

    import_col_dataset(FIXTURE, database)

    engine = create_engine(f"sqlite:///{database}")
    with Session(engine) as session:
        taxon = session.scalar(select(Taxon).where(Taxon.source_id == "63J5L"))
        assert taxon is not None
        assert taxon.is_synonym is True
        assert taxon.rank == "genus"
