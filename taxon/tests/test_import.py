from __future__ import annotations

import tracemalloc
from pathlib import Path

from sqlalchemy import create_engine, func, insert, select
from sqlalchemy.orm import Session

from taxon.import_data import _populate_species_paths, import_dataset
from taxon.schema import Base, SpeciesPath, Taxon


def write_fixture(path: Path) -> None:
    path.write_text(
        "Biota [superdomain] {ID=urn:1}\n"
        "  Animalia [kingdom] {ID=urn:2}\n"
        "    Chordata [phylum] {ID=urn:3}\n"
        "      Actinopterygii [class] {ID=urn:4}\n"
        "        Cyprinodontiformes [order] {ID=urn:5}\n"
        "          Goodeidae [family] {ID=urn:6}\n"
        "            Girardinichthys [genus] {ID=urn:7}\n"
        "              †Girardinichthys multiradiatus [species] {ID=urn:8}\n"
        "                =Girardinichthys multiradiata [species] {ID=urn:9}\n",
        encoding="utf-8",
    )


def test_import_rebuilds_taxa_and_or_folds_species_path_markers(tmp_path: Path) -> None:
    source = tmp_path / "dataset-2011.txt"
    database = tmp_path / "taxon.db"
    write_fixture(source)

    counts = import_dataset(source, database, batch_size=3)

    assert counts.total_taxa == 9
    assert counts.total_species == 2
    assert counts.synonym == 1
    assert counts.extinct == 1
    assert counts.uncertain == 0
    assert counts.unassigned == 0

    engine = create_engine(f"sqlite:///{database}")
    with Session(engine) as session:
        paths = session.scalars(select(SpeciesPath).order_by(SpeciesPath.species_id)).all()
        assert len(paths) == 2
        assert paths[0].kingdom == "Animalia"
        assert paths[0].genus == "Girardinichthys"
        assert paths[0].species == "Girardinichthys multiradiatus"
        assert paths[0].is_extinct is True
        assert paths[1].is_synonym is True
        assert paths[1].is_extinct is True


def test_import_is_idempotent_and_batches_real_parser_rows(tmp_path: Path) -> None:
    source = tmp_path / "dataset-2011.txt"
    database = tmp_path / "taxon.db"
    write_fixture(source)

    first = import_dataset(source, database, batch_size=2)
    second = import_dataset(source, database, batch_size=4)

    assert second == first
    engine = create_engine(f"sqlite:///{database}")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Taxon)) == 9
        assert session.scalar(select(func.count()).select_from(SpeciesPath)) == 2
        synonym = session.scalar(select(Taxon).where(Taxon.source_id == "urn:9"))
        assert synonym is not None
        assert synonym.parent_id == session.scalar(
            select(Taxon.id).where(Taxon.source_id == "urn:8")
        )


def _write_wide_fixture(path: Path, *, kingdoms: int, species_per_genus: int) -> int:
    """Build a wide WoRMS-shaped fixture: K kingdoms x S species per genus."""
    lines: list[str] = ["Biota [superdomain] {ID=urn:0}"]
    counter = 1
    for k in range(kingdoms):
        kingdom_id = f"urn:{counter}"
        counter += 1
        lines.append(f"  Kingdom{k} [kingdom] {{ID={kingdom_id}}}")
        phylum_id = f"urn:{counter}"
        counter += 1
        lines.append(f"    Phylum{k} [phylum] {{ID={phylum_id}}}")
        class_id = f"urn:{counter}"
        counter += 1
        lines.append(f"      Class{k} [class] {{ID={class_id}}}")
        order_id = f"urn:{counter}"
        counter += 1
        lines.append(f"        Order{k} [order] {{ID={order_id}}}")
        family_id = f"urn:{counter}"
        counter += 1
        lines.append(f"          Family{k} [family] {{ID={family_id}}}")
        genus_id = f"urn:{counter}"
        counter += 1
        lines.append(f"            Genus{k} [genus] {{ID={genus_id}}}")
        for s in range(species_per_genus):
            species_id = f"urn:{counter}"
            counter += 1
            lines.append(f"              Species{k}_{s} [species] {{ID={species_id}}}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def test_species_paths_projection_keeps_stack_bounded(tmp_path: Path) -> None:
    """The species_paths pass holds only the open-ancestor chain, not every
    taxon ever visited, so the working stack stays tiny no matter how wide the
    input is. We assert the bound directly on the in-memory projection.
    """
    source = tmp_path / "dataset-2011.txt"
    total = _write_wide_fixture(source, kingdoms=200, species_per_genus=50)
    database = tmp_path / "taxon.db"

    counts = import_dataset(source, database, batch_size=500)
    assert counts.total_taxa == total
    assert counts.total_species == 200 * 50

    engine = create_engine(f"sqlite:///{database}")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SpeciesPath)) == 200 * 50
        last = session.scalar(
            select(SpeciesPath)
            .where(SpeciesPath.species == "Species0_0")
            .order_by(SpeciesPath.species_id)
        )
        assert last is not None
        assert last.kingdom == "Kingdom0"
        assert last.phylum == "Phylum0"
        assert last.class_name == "Class0"
        assert last.order == "Order0"
        assert last.family == "Family0"
        assert last.genus == "Genus0"


def test_species_paths_projection_peak_memory_is_bounded(tmp_path: Path) -> None:
    """Re-running just the projection phase on a large in-memory SQLite
    database should complete with a small peak resident allocation, confirming
    the O(depth) bound rather than O(total taxa).
    """
    source = tmp_path / "dataset-2011.txt"
    total = _write_wide_fixture(source, kingdoms=300, species_per_genus=50)
    build_db = tmp_path / "build.db"
    import_dataset(source, build_db, batch_size=1_000)

    project_db = tmp_path / "project.db"
    project_engine = create_engine(f"sqlite:///{project_db}")
    Base.metadata.create_all(project_engine)

    source_engine = create_engine(f"sqlite:///{build_db}")
    with source_engine.connect() as connection:
        rows = [dict(r) for r in connection.execute(select(Taxon).order_by(Taxon.id)).mappings()]
    with project_engine.begin() as connection:
        connection.execute(insert(Taxon), rows)

    tracemalloc.start()
    _populate_species_paths(project_engine)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    with project_engine.connect() as connection:
        species_count = connection.execute(
            select(func.count()).select_from(SpeciesPath)
        ).scalar_one()
    assert species_count == 300 * 50

    assert total > 10_000, "fixture should be at least 10k taxa to exercise the bound"
    assert peak < 8 * 1024 * 1024, f"projection peak {peak} bytes exceeds 8 MiB bound"
