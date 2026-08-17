"""RED-first contract tests for the ``search_taxon`` ranking order.

The ``arbol-col-browse`` change ships the "Find taxon" autocomplete
with a deterministic ranking rule:

1. **Exact** match (canonical ``name`` equals ``q``) wins.
2. **Prefix** match (canonical ``name`` starts with ``q``) is
   second.
3. **Substring** match (canonical ``name`` or
   ``display_name`` contains ``q``) is third.
4. Within each tier, ties break by ``display_name`` length
   ascending so the "closest" hit sits at the top.

The ranking is enforced by :func:`taxon.api.tree.search_taxon`.
These tests pin each tier without depending on the ``col.db``
shape.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def _ranking_fixture() -> str:
    """Lineage that exercises every ranking tier.

    Layout::

        Panthera [genus]                 <- exact for q=Panthera, prefix for q=Pan
          Panthera onca [species]       <- substring for q=Panthera (name starts), exact for display
          Panthera pardus [species]
        Pandorina [genus]                <- prefix for q=Pan
        Selenotypus [genus]              <- unrelated, must never appear for q=Panthera
        Eukarya [kingdom]                <- prefix for q=Euk
        Pseudeukarya [kingdom]           <- substring for q=Euk
    """
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Panthera [genus] {ID=urn:1}\n"
        "    Panthera onca [species] {ID=urn:2}\n"
        "    Panthera pardus [species] {ID=urn:3}\n"
        "  Pandorina [genus] {ID=urn:4}\n"
        "  Selenotypus [genus] {ID=urn:5}\n"
        "  Eukarya [kingdom] {ID=urn:6}\n"
        "  Pseudeukarya [kingdom] {ID=urn:7}\n"
    )


def _client(tmp_path: Path) -> TestClient:
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_ranking_fixture(), encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    return TestClient(create_app(database_url=f"sqlite:///{db}"))


def _name_list(items: list[dict[str, object]]) -> list[str]:
    return [str(item["name"]) for item in items]


def _relevance_list(items: list[dict[str, object]]) -> list[str]:
    return [str(item["relevance"]) for item in items]


# ---------------------------------------------------------------------------
# Tier 1: exact match wins
# ---------------------------------------------------------------------------


def test_search_exact_match_is_at_index_zero(tmp_path: Path) -> None:
    """``Panthera`` returns the exact match ``Panthera`` first."""
    client = _client(tmp_path)
    with client:
        body = client.get("/api/tree/search?q=Panthera").json()

    items = body["items"]
    assert items, items
    assert items[0]["name"] == "Panthera"
    assert items[0]["relevance"] == "exact"


def test_search_exact_match_beats_prefix_substring(tmp_path: Path) -> None:
    """Exact matches precede both Panthera onca (prefix) and Pandorina (prefix)."""
    client = _client(tmp_path)
    with client:
        body = client.get("/api/tree/search?q=Panthera").json()

    names = _name_list(body["items"])
    # Panthera exact comes first; Panthera onca / Panthera pardus /
    # Pandorina are prefix matches below.
    assert names[0] == "Panthera"
    assert "Selenotypus" not in names


# ---------------------------------------------------------------------------
# Tier 2: prefix beats substring
# ---------------------------------------------------------------------------


def test_search_prefix_beats_substring_for_q_Euk(tmp_path: Path) -> None:
    """``Euk`` returns ``Eukarya`` before ``Pseudeukarya`` (substring match)."""
    client = _client(tmp_path)
    with client:
        body = client.get("/api/tree/search?q=Euk").json()

    items = body["items"]
    assert items, items
    names = _name_list(items)
    euk_index = names.index("Eukarya")
    pseudo_index = names.index("Pseudeukarya")
    assert euk_index < pseudo_index, (items, names)


def test_search_relevance_matches_name_match_tier(tmp_path: Path) -> None:
    """``relevance`` mirrors the match rule applied to the canonical ``name``.

    Eukarya is a name-prefix match (``Eukarya``.startswith(``euk``)),
    Pseudeukarya is a substring match because its name does not
    start with ``euk`` -- even though ``display_name`` contains it.
    """
    client = _client(tmp_path)
    with client:
        body = client.get("/api/tree/search?q=Euk").json()

    items = body["items"]
    assert items, items
    relevance = _relevance_list(items)
    names = _name_list(items)
    rel_by_name = dict(zip(names, relevance))
    assert rel_by_name["Eukarya"] == "prefix", rel_by_name
    # Pseudeukarya is a substring match on `name` because
    # `name.startswith("euk")` is False.
    assert rel_by_name["Pseudeukarya"] == "substring", rel_by_name


# ---------------------------------------------------------------------------
# Tier 3: tie-break by display_name length ascending
# ---------------------------------------------------------------------------


def test_search_ties_break_by_display_name_length(tmp_path: Path) -> None:
    """Two prefix rows with the same lower-case ``name`` are tie-broken by ``display_name`` length.

    Build a fixture where two species share the prefix ``Pseudeu``:
    ``Pseudeukarya short`` and ``Pseudeukarya very long display``.
    The shorter ``display_name`` wins the tie-break.
    """
    fixture = (
        "Pseudeukarya short [kingdom] {ID=urn:1}\n"
        "Pseudeukarya very long display name [kingdom] {ID=urn:2}\n"
    )
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(fixture, encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    client = TestClient(create_app(database_url=f"sqlite:///{db}"))

    with client:
        body = client.get("/api/tree/search?q=Pseudeukarya").json()

    items = body["items"]
    assert len(items) >= 2, items
    # First hit is the shorter display_name.
    assert items[0]["display_name"] == "Pseudeukarya short [kingdom]"
    # Second hit is the longer one.
    longer = next(it for it in items if "very long" in str(it["display_name"]))
    assert items[0]["id"] != longer["id"]


# ---------------------------------------------------------------------------
# Performance target — p95 latency under 200ms against the live DB
# ---------------------------------------------------------------------------


def test_search_returns_200ms_for_typical_query(tmp_path: Path) -> None:
    """Smoke test — the search responds with a 200 + items body under 200ms.

    The full p95 target is verified against the real ``col.db`` in
    the apply-progress notes; this fixture pins the wire contract on
    a small in-memory SQLite so a regression in the SQL / endpoint
    is caught even when ``col.db`` is unavailable.
    """
    import time

    client = _client(tmp_path)
    with client:
        t0 = time.perf_counter()
        response = client.get("/api/tree/search?q=Panthera")
        elapsed_ms = (time.perf_counter() - t0) * 1000

    assert response.status_code == 200
    assert elapsed_ms < 200, f"search took {elapsed_ms:.1f}ms"
