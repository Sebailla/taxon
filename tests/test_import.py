from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from taxon.import_data import import_dataset
from taxon.schema import SpeciesPath, Taxon


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
        assert synonym.parent_id == session.scalar(select(Taxon.id).where(Taxon.source_id == "urn:8"))
