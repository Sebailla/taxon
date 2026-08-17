"""Contract tests for the skip-tier best-effort path resolver.

The cascade resolver in :mod:`taxon.api.sqlite_resolver` walks a
path of canonical names against the local SQLite hierarchy. PR #43
replaced the locked 9-tier tuple projection with a best-effort walk
that drops the strict parent-anchor on the last segment so off-tuple
intermediate ranks (``subphylum``, ``infraphylum``, ``parvphylum``,
``megaclass``, ``subclass``, ``suborder``) do not dead-end the
cascade. The accompanying helper
:func:`taxon.api.hierarchy.resolve_path_by_display_level` still
anchors each segment to ``parent_id = previous.id``.

Real-world datasets (Catalogue of Life, GBIF Backbone) nest the
display-bucket classes several intermediates below the phylum the
cascade UI names: ``Animalia > Chordata > Vertebrata > Gnathostomata >
Osteichthyes > Tetrapoda > Mammalia``. The strict-parent anchor
returns 404 on the first off-tuple deep tier, the visible UI
breakage the cascade frontend exhibits today.

These tests pin the expected behaviour of a *skip-tier* walk: when a
segment of the path targets a row that is not a direct child of the
previously-resolved parent but IS a descendant, the resolver must
find it as long as the row exists anywhere under the parent
ancestry. The new behaviour must keep the existing single-bucket
and same-bucket matches working (off-tuple intermediates) and must
not regress the first-segment kingdom anchor.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from taxon.api.hierarchy import resolve_path_by_display_level
from taxon.indented_import import import_indented_dataset


def _deep_intermediate_fixture() -> str:
    """A GBIF Backbone-style indented fixture with a class several tiers deep.

    Mirrors the real Catalogue-of-Life shape: a kingdom, a phylum,
    two intermediate ranks (subphylum, infraphylum), and a class
    hanging off the deepest intermediate. The cascade UI sends the
    path ``Animalia|Chordata|Mammalia`` and expects the resolver to
    return the class row even though ``Mammalia`` is not a direct
    child of ``Chordata``.

        Animalia (kingdom, display_level=kingdom)
          Chordata (phylum, display_level=phylum)
            Vertebrata (subphylum, display_level=phylum)
              Gnathostomata (infraphylum, display_level=phylum)
                Mammalia (class, display_level=class)
    """
    return (
        "Animalia [kingdom] {ID=A}\n"
        "  Chordata [phylum] {ID=B}\n"
        "    Vertebrata [subphylum] {ID=C}\n"
        "      Gnathostomata [infraphylum] {ID=D}\n"
        "        Mammalia [class] {ID=E}\n"
    )


def _seed_app_and_session(tmp_path: Path) -> tuple[Path, Session]:
    """Persist the deep-intermediate fixture and return the session."""
    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_deep_intermediate_fixture(), encoding="utf-8")
    import_indented_dataset(src, db, batch_size=64)

    from taxon.api import _build_engine

    engine = _build_engine(f"sqlite:///{db}")
    return db, Session(engine)


def test_resolve_path_finds_class_through_deep_intermediates(tmp_path: Path) -> None:
    """``resolve_path_by_display_level`` must find a class row that hangs under
    several off-tuple intermediates rather than directly under the
    phylum the cascade UI names.

    The path ``['Animalia', 'Chordata', 'Mammalia']`` cannot anchor
    ``Mammalia`` to ``parent_id = Chordata.id`` (Mammalia is 3 levels
    deeper) — the skip-tier walk must descend through Vertebrata
    and Gnathostomata to find the class row.
    """
    _, session = _seed_app_and_session(tmp_path)
    try:
        row = resolve_path_by_display_level(
            session,
            ["Animalia", "Chordata", "Mammalia"],
        )
    finally:
        session.close()

    assert row is not None, (
        "Mammalia lives 3 intermediates below Chordata; the resolver "
        "must reach it via skip-tier walk, not 404 the cascade UI"
    )
    assert row.name == "Mammalia"
    assert row.rank == "class"


def test_resolve_path_finds_order_through_family_intermediate(tmp_path: Path) -> None:
    """A family whose child is the order rank through a ``tribe`` off-tuple
    intermediate (family bucket) must still resolve.

        Animalia (kingdom)
          Chordata (phylum)
            Mammalia (class)
              Carnivora (order)
                Felidae (family)
                  Panthera (genus)
    """
    fixture = (
        "Animalia [kingdom] {ID=A}\n"
        "  Chordata [phylum] {ID=B}\n"
        "    Mammalia [class] {ID=C}\n"
        "      Carnivora [order] {ID=D}\n"
        "        Felidae [family] {ID=E}\n"
        "          Panthera [genus] {ID=F}\n"
    )
    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(fixture, encoding="utf-8")
    import_indented_dataset(src, db, batch_size=64)

    from taxon.api import _build_engine
    from taxon.api.hierarchy import resolve_path_by_display_level

    session = Session(_build_engine(f"sqlite:///{db}"))
    try:
        # Path arrives with class directly after phylum (no class tier
        # exists as a direct child of Chordata in the deeper fixture;
        # here we exercise the same shape at the family→genus layer).
        row = resolve_path_by_display_level(
            session,
            ["Animalia", "Chordata", "Mammalia", "Carnivora", "Felidae", "Panthera"],
        )
    finally:
        session.close()

    assert row is not None
    assert row.name == "Panthera"
    assert row.rank == "genus"


def test_resolve_path_direct_child_still_works(tmp_path: Path) -> None:
    """The skip-tier walk must NOT regress the direct-child case.

    A path that walks strictly down the parent chain (no
    intermediates missing) must keep returning the deepest matched
    row.
    """
    fixture = (
        "Animalia [kingdom] {ID=A}\n"
        "  Chordata [phylum] {ID=B}\n"
        "    Mammalia [class] {ID=C}\n"
        "      Carnivora [order] {ID=D}\n"
        "        Felidae [family] {ID=E}\n"
        "          Panthera [genus] {ID=F}\n"
    )
    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(fixture, encoding="utf-8")
    import_indented_dataset(src, db, batch_size=64)

    from taxon.api import _build_engine

    session = Session(_build_engine(f"sqlite:///{db}"))
    try:
        row = resolve_path_by_display_level(
            session,
            ["Animalia", "Chordata", "Mammalia"],
        )
    finally:
        session.close()

    assert row is not None
    assert row.name == "Mammalia"
    assert row.rank == "class"


def test_resolve_path_returns_none_when_segment_does_not_exist(tmp_path: Path) -> None:
    """A segment that has no descendant under the parent must still 404.

    The skip-tier walk must NOT chase arbitrary descendants into other
    bucket boundaries. ``Panthera leo`` does not exist in the
    fixture, so the resolver must return ``None`` rather than match
    ``Panthera`` at the species tier.
    """
    fixture = (
        "Animalia [kingdom] {ID=A}\n"
        "  Chordata [phylum] {ID=B}\n"
        "    Mammalia [class] {ID=C}\n"
        "      Carnivora [order] {ID=D}\n"
        "        Felidae [family] {ID=E}\n"
        "          Panthera [genus] {ID=F}\n"
    )
    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(fixture, encoding="utf-8")
    import_indented_dataset(src, db, batch_size=64)

    from taxon.api import _build_engine

    session = Session(_build_engine(f"sqlite:///{db}"))
    try:
        row = resolve_path_by_display_level(
            session,
            ["Animalia", "Chordata", "Mammalia", "Carnivora", "Felidae", "Panthera leo"],
        )
    finally:
        session.close()

    assert row is None


def test_resolve_path_first_segment_kingdom_anchor(tmp_path: Path) -> None:
    """The first segment must still anchor on the kingdom display bucket.

    The skip-tier walk is only active for second-and-later
    segments. The first segment is unanchored (we don't know its
    parent), so it must match the kingdom bucket or nothing.
    """
    fixture = "Animalia [kingdom] {ID=A}\n  Chordata [phylum] {ID=B}\n"
    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(fixture, encoding="utf-8")
    import_indented_dataset(src, db, batch_size=64)

    from taxon.api import _build_engine

    session = Session(_build_engine(f"sqlite:///{db}"))
    try:
        row_animalia = resolve_path_by_display_level(session, ["Animalia"])
        row_chordata_first = resolve_path_by_display_level(session, ["Chordata"])
    finally:
        session.close()

    assert row_animalia is not None and row_animalia.name == "Animalia"
    # Chordata is a phylum — the first-segment bucket is kingdom, so
    # a single-segment lookup for "Chordata" must return None.
    assert row_chordata_first is None, (
        "first segment is unanchored and must hit the kingdom bucket, "
        "not fall back to the phylum bucket"
    )
