from sqlalchemy import Boolean, Index, String, create_engine, inspect
from sqlalchemy.orm import Session

from taxon.schema import Base, SpeciesPath, Taxon


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
    assert any(
        isinstance(index, Index) and tuple(column.name for column in index.columns) == ("species",)
        for index in SpeciesPath.__table__.indexes
    )
