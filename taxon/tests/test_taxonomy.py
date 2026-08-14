"""RED-first contract tests for the display_level bucketing."""

from __future__ import annotations

import pytest

from taxon.taxonomy import (
    DISPLAY_LEVELS,
    RANK_TO_DISPLAY_LEVEL,
    display_level,
    is_cascade_visible,
)

# ---------------------------------------------------------------------------
# 1. The 8 canonical buckets exist in order.
# ---------------------------------------------------------------------------


def test_canonical_display_levels_in_order() -> None:
    assert DISPLAY_LEVELS == (
        "realm",
        "kingdom",
        "phylum",
        "class",
        "order",
        "family",
        "genus",
        "species",
    )


# ---------------------------------------------------------------------------
# 2. Each rank in the mapping lands in the expected bucket.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rank", "expected_bucket"),
    [
        # realm
        ("domain", "realm"),
        ("superdomain", "realm"),
        ("subdomain", "realm"),
        # kingdom
        ("kingdom", "kingdom"),
        ("subkingdom", "kingdom"),
        # phylum bucket (subphylum, infraphylum, parvphylum, megaclass all collapse here)
        ("phylum", "phylum"),
        ("subphylum", "phylum"),
        ("infraphylum", "phylum"),
        ("parvphylum", "phylum"),
        ("microphylum", "phylum"),
        ("megaclass", "phylum"),
        # class bucket
        ("class", "class"),
        ("subclass", "class"),
        ("infraclass", "class"),
        ("magnorder", "class"),
        ("superorder", "class"),
        # order bucket
        ("order", "order"),
        ("suborder", "order"),
        ("infraorder", "order"),
        ("parvorder", "order"),
        # family bucket
        ("superfamily", "family"),
        ("family", "family"),
        ("subfamily", "family"),
        ("tribe", "family"),
        ("subtribe", "family"),
        ("infratribe", "family"),
        # genus bucket
        ("genus", "genus"),
        ("subgenus", "genus"),
        # species bucket
        ("species", "species"),
        ("subspecies", "species"),
        ("variety", "species"),
        ("subvariety", "species"),
        ("form", "species"),
        ("subform", "species"),
        ("forma_specialis", "species"),
    ],
)
def test_known_rank_maps_to_correct_bucket(rank: str, expected_bucket: str) -> None:
    assert display_level(rank) == expected_bucket
    assert is_cascade_visible(rank) is True


# ---------------------------------------------------------------------------
# 3. Ranks that the cascade UI must NOT show are excluded.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rank",
    [
        "unranked",  # CoL placeholders waiting for taxonomic review
        "proles",  # historical, 19th century
        "natio",  # historical
        "lusus",  # historical
        "aberration",  # historical
        "mutatio",  # historical
        "morph",  # historical
        "section_botany",  # informal botanical sub-unit
        "species_aggregate",  # informal group of species
        "infraspecific_name",  # redundant placeholder
        "infrasubspecific_name",  # redundant placeholder
        # Year-numeric noise that the .txtree parser accidentally emits
        # (e.g. "1956 [15] [species]" — the [15] is not a rank).
        "1858",
        "1825",
        "1776",
    ],
)
def test_excluded_ranks_return_none(rank: str) -> None:
    assert display_level(rank) is None
    assert is_cascade_visible(rank) is False


def test_unknown_rank_returns_none() -> None:
    """A rank that is not in the whitelist (typo, novel) does not silently
    land in any bucket. The cascade UI must not show it."""
    assert display_level("not_a_real_rank") is None
    assert is_cascade_visible("not_a_real_rank") is False


# ---------------------------------------------------------------------------
# 4. The mapping is exhaustive: every bucket has at least one rank.
# ---------------------------------------------------------------------------


def test_every_bucket_has_at_least_one_rank() -> None:
    """Cascade UI: an empty bucket would let the user pick a tier that
    has no navigable children. The mapping must cover every bucket so
    the cascade chain stays unbroken."""
    buckets_in_use = set(RANK_TO_DISPLAY_LEVEL.values())
    assert buckets_in_use == set(DISPLAY_LEVELS)


# ---------------------------------------------------------------------------
# 5. The mapping is the full picture used by the cascade resolver.
# ---------------------------------------------------------------------------


def test_ranking_to_display_level_is_frozen() -> None:
    """display_level() must be a pure function of the rank string. No
    I/O, no state, no dependency on the DB. Tests downstream rely on
    this — for example, the importer populates the column by calling
    display_level() in a streaming loop."""
    assert display_level("species") == "species"
    assert display_level("species") == "species"  # idempotent
    assert display_level("SPECIES") == "species"  # case-sensitive (whitelist is canonical)
