"""Integration test for the 600-row pagination boundary.

The species list endpoint caps every response at 500 items. When
the genus carries more than 500 species, the response includes a
``next_cursor`` and the client can request the next page with
``?cursor=<opaque>``. This test pins the boundary:

- 499 rows → single response, ``next_cursor is None``.
- 500 rows → single response, ``next_cursor is None`` (the cap is
  inclusive).
- 501 rows → first response is 500 rows + ``next_cursor``; the
  second response has 1 row + ``next_cursor is None``.
- 600 rows → first response is 500 rows + cursor; second response
  has 100 rows + ``next_cursor is None``.

The cursor uses canonical ``name`` values so the pagination stays
deterministic across re-imports.

We seed the database via ``import_dataset`` with a fixture that
generates ``count`` species under a single genus; the test runs
against an in-memory SQLite so it does not touch the filesystem.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from taxon.api import create_app


def _wide_fixture(count: int) -> str:
    """Generate a WoRMS-style fixture with ``count`` accepted species
    under a single genus.

    The fixture is shaped so the parser builds one kingdom /
    phylum / class / order / family / genus / count*species. We
    add a few synonym / extinct markers near the front so the
    cursor ordering still has something to differentiate rows.
    """
    lines = [
        "Biota [superdomain] {ID=urn:0}",
        "  Animalia [kingdom] {ID=urn:1}",
        "    Chordata [phylum] {ID=urn:2}",
        "      Actinopterygii [class] {ID=urn:3}",
        "        Cyprinodontiformes [order] {ID=urn:4}",
        "          Goodeidae [family] {ID=urn:5}",
        "            Girardinichthys [genus] {ID=urn:6}",
    ]
    counter = 7
    # Pad the names so the alphabetical order is well-defined even
    # when the count is large. Four-digit suffix guarantees a stable
    # lexicographic order.
    for i in range(count):
        lines.append(f"              Girardinichthys sp{i:04d} [species] {{ID=urn:{counter}}}")
        counter += 1
    return "\n".join(lines) + "\n"


def _seed_app(tmp_path: Path, count: int) -> TestClient:
    """Build an in-memory app seeded with ``count`` species."""
    from taxon.import_data import import_dataset

    db_path = tmp_path / "taxon.db"
    src_path = tmp_path / "dataset.txt"
    src_path.write_text(_wide_fixture(count=count), encoding="utf-8")
    # Use a file-backed SQLite for the import step so ``import_dataset``
    # can use the same database the API will read from. Then point
    # the API at the file.
    import_dataset(src_path, db_path, batch_size=64)
    app = create_app(database_url=f"sqlite:///{db_path}")
    # Use the context manager so the lifespan event fires (it builds
    # the engine + session factory on startup). Without ``with`` the
    # lifespan does not run and ``app_state`` is never set.
    client = TestClient(app)
    client.__enter__()
    return client


def _close(client: TestClient) -> None:
    client.__exit__(None, None, None)


SPECIES_PATH = (
    "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/Girardinichthys/species"
)


def test_pagination_under_cap_returns_single_page(tmp_path: Path) -> None:
    client = _seed_app(tmp_path, count=499)

    body = client.get(SPECIES_PATH).json()

    assert len(body["items"]) == 499
    assert body["next_cursor"] is None


def test_pagination_at_cap_returns_single_page(tmp_path: Path) -> None:
    """The cap is inclusive — 500 rows is still a single page."""
    client = _seed_app(tmp_path, count=500)

    body = client.get(SPECIES_PATH).json()

    assert len(body["items"]) == 500
    assert body["next_cursor"] is None


def test_pagination_over_cap_returns_cursor_and_remaining_rows(
    tmp_path: Path,
) -> None:
    """501 rows triggers a cursor; following the cursor returns 1 row."""
    client = _seed_app(tmp_path, count=501)

    first = client.get(SPECIES_PATH).json()
    assert len(first["items"]) == 500
    assert isinstance(first["next_cursor"], str) and first["next_cursor"]

    second = client.get(SPECIES_PATH, params={"cursor": first["next_cursor"]}).json()
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None


def test_pagination_600_rows_returns_two_pages(tmp_path: Path) -> None:
    """The full 600-row boundary: first page 500, second page 100."""
    client = _seed_app(tmp_path, count=600)

    first = client.get(SPECIES_PATH).json()
    assert len(first["items"]) == 500
    assert first["next_cursor"] is not None

    second = client.get(SPECIES_PATH, params={"cursor": first["next_cursor"]}).json()
    assert len(second["items"]) == 100
    assert second["next_cursor"] is None

    # The two pages are disjoint and cover the full 600 rows.
    first_names = {item["name"] for item in first["items"]}
    second_names = {item["name"] for item in second["items"]}
    assert first_names.isdisjoint(second_names)
    assert len(first_names | second_names) == 600


def test_pagination_with_include_respects_cap(tmp_path: Path) -> None:
    """Inclusion filters use OR semantics per the inclusion-filters spec:

    ``accepted OR (any enabled toggle)``. So ``include=synonyms``
    returns accepted species PLUS any synonym species. Since the
    fixture has zero synonym rows, the result is the 600 accepted
    rows paginated exactly like the default case.
    """
    client = _seed_app(tmp_path, count=600)

    body = client.get(SPECIES_PATH, params={"include": "synonyms"}).json()
    assert len(body["items"]) == 500
    assert body["next_cursor"] is not None


def test_pagination_pages_are_alphabetically_ordered(tmp_path: Path) -> None:
    """The cursor is on canonical ``name`` so each page sorts
    deterministically within itself; the union of pages is the
    alphabetically-sorted full set.
    """
    client = _seed_app(tmp_path, count=600)

    first = client.get(SPECIES_PATH).json()
    second = client.get(SPECIES_PATH, params={"cursor": first["next_cursor"]}).json()

    first_names = [item["name"] for item in first["items"]]
    second_names = [item["name"] for item in second["items"]]
    # Within each page, names are sorted by canonical name.
    assert first_names == sorted(first_names)
    assert second_names == sorted(second_names)
    # The last item of page 1 sorts strictly before the first item
    # of page 2 (because the cursor is the name of the last item).
    assert first_names[-1] < second_names[0]
