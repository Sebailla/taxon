"""Contract tests for the synthesized-Biota root of the cascade.

When the cascade UI's first dropdown (``/api/kingdoms``) renders the
two synthesized roots (``Biota`` and ``Viruses``) and the user picks
one of them, the front-end sends a follow-up ``/api/path-children?path=
|Biota`` to fetch the next dropdown's options. The local SQLite
hierarchy does not carry a ``Biota`` row (GBIF Backbone ships Biota
as an implicit superdomain, not a SQLite row), so the resolver used
to 404 the request and the cascade dead-ended at the very first
level.

These tests pin the fix:

- ``path = ['Biota']`` must return every kingdom-rank row in the
  local hierarchy as a child of the synthesized Biota parent.
- ``path = ['Viruses']`` must return the same shape so a future
  virus-side branch does the right thing.
- The synthesized parent must carry ``name='Biota'`` (or
  ``'Viruses'``) and ``rank='superdomain'`` so the front-end's
  fixed-tier renderer knows the result represents the root tier.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from taxon.api.sqlite_resolver import list_path_children


def _seed_app_and_session(tmp_path: Path) -> Session:
    """Persist a small multi-kingdom fixture and return the session."""
    fixture = (
        "Eukaryota [domain] {ID=root:eu}\n"
        "  Animalia [kingdom] {ID=A}\n"
        "    Chordata [phylum] {ID=B}\n"
        "      Mammalia [class] {ID=C}\n"
        "  Plantae [kingdom] {ID=D}\n"
        "    Tracheophyta [phylum] {ID=E}\n"
        "  Fungi [kingdom] {ID=F}\n"
        "    Basidiomycota [phylum] {ID=G}\n"
    )
    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(fixture, encoding="utf-8")
    from taxon.api import _build_engine
    from taxon.indented_import import import_indented_dataset

    import_indented_dataset(src, db, batch_size=64)
    return Session(_build_engine(f"sqlite:///{db}"))


def test_path_children_with_biota_root_returns_kingdom_tier(tmp_path: Path) -> None:
    """``path=['Biota']`` must return a synthesized Biota parent and every kingdom row."""
    session = _seed_app_and_session(tmp_path)
    try:
        env = list_path_children(session, ["Biota"])
    finally:
        session.close()

    assert env is not None, "Biota is the synthesis root; the cascade must answer"
    assert env.parent.name == "Biota"
    assert env.parent.rank == "superdomain"
    kingdom_names = {child.name for child in env.children}
    assert {"Animalia", "Plantae", "Fungi"}.issubset(kingdom_names), (
        f"expected every kingdom-rank row under Biota; got {sorted(kingdom_names)}"
    )
    kingdom_tier = next(
        (t for t in (env.next_tiers or []) if t.rank == "kingdom"),
        None,
    )
    assert kingdom_tier is not None, "next_tiers must include a kingdom bucket"
    assert {"Animalia", "Plantae", "Fungi"}.issubset({c.name for c in kingdom_tier.children})


def test_path_children_with_viruses_root_returns_kingdom_tier(tmp_path: Path) -> None:
    """``path=['Viruses']`` mirrors the Biota contract so the cascade stays symmetric."""
    session = _seed_app_and_session(tmp_path)
    try:
        env = list_path_children(session, ["Viruses"])
    finally:
        session.close()

    assert env is not None
    assert env.parent.name == "Viruses"
    assert env.parent.rank == "superdomain"
    # Virus-only fixtures would expose different kingdom names; the
    # contract is the synthesized parent + kingdom next_tiers tier.
    virus_tier = next(
        (t for t in (env.next_tiers or []) if t.rank == "kingdom"),
        None,
    )
    assert virus_tier is not None


def test_path_children_with_biota_then_kingdom_resolves_chain(tmp_path: Path) -> None:
    """``path=['Biota', 'Animalia']`` must walk to the kingdom row and return the phylum tier."""
    session = _seed_app_and_session(tmp_path)
    try:
        env = list_path_children(session, ["Biota", "Animalia"])
    finally:
        session.close()

    assert env is not None
    assert env.parent.name == "Animalia"
    assert env.parent.rank == "kingdom"
    phylum_tier = next(
        (t for t in (env.next_tiers or []) if t.rank == "phylum"),
        None,
    )
    assert phylum_tier is not None
    assert {c.name for c in phylum_tier.children} == {"Chordata"}


def test_species_list_strips_synth_root_before_resolving_genus(tmp_path: Path) -> None:
    """``/api/species-list?path=Biota|...|Panthera`` must reach the Panthera genus row.

    The cascade UI prefixes every user-built path with ``Biota`` (or
    ``Viruses``) when it dispatches the breadcrumb, so the species
    leaf endpoint must drop the synthesized segment before walking
    the remainder — mirroring the contract :func:`list_path_children`
    established for the intermediate-tiers envelopes.
    """
    from taxon.api.sqlite_resolver import list_species_under_path

    fixture = (
        "Eukaryota [domain] {ID=root:eu}\n"
        "  Animalia [kingdom] {ID=A}\n"
        "    Chordata [phylum] {ID=B}\n"
        "      Mammalia [class] {ID=C}\n"
        "        Carnivora [order] {ID=D}\n"
        "          Felidae [family] {ID=E}\n"
        "            Panthera [genus] {ID=F}\n"
        "              Panthera leo [species] {ID=G}\n"
        "              Panthera onca [species] {ID=H}\n"
    )
    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(fixture, encoding="utf-8")
    from taxon.api import _build_engine
    from taxon.indented_import import import_indented_dataset

    import_indented_dataset(src, db, batch_size=64)
    session = Session(_build_engine(f"sqlite:///{db}"))
    try:
        resp = list_species_under_path(
            session,
            ["Biota", "Animalia", "Chordata", "Mammalia", "Carnivora", "Felidae", "Panthera"],
            include=None,
            cursor=None,
        )
    finally:
        session.close()

    item_names = {item.name for item in resp.items}
    assert {"Panthera leo", "Panthera onca"}.issubset(item_names)
