"""Display-level bucketing for the cascade UI.

The Cascade renders up to 8 dropdowns, one per display_level bucket:

    realm -> kingdom -> phylum -> class -> order -> family -> genus -> species

CoL ships 40+ distinct ranks. The mapping below collapses them into 8
visible buckets so the UI stays manageable. Each taxon has a
``display_level`` column populated at import time; the cascade reads
that column to filter which children show up at each dropdown.

Historical ranks that no modern taxonomy uses (``proles``, ``natio``,
``aberration``, ``lusus``, ``mutatio``, ``morph``, the year-numeric
ranks that the .txtree parser accidentally emits) are not in the
mapping. They map to ``None`` and are excluded from the cascade UI.
The rows stay in the DB and are reachable via ``/api/search?q=...``
once the search endpoint lands.

The whitelist below is the source of truth. Adding a new rank means
deciding which bucket it belongs to. Wrong mappings cause silently
wrong UI (a row never appears in any dropdown).
"""

from __future__ import annotations

from typing import Final

#: Canonical 8 display levels. The order also drives the cascade:
#: a child of bucket X is shown when the user picks a parent whose
#: bucket is one step "above" X in this list.
DISPLAY_LEVELS: Final[tuple[str, ...]] = (
    "realm",
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
)

#: Rank -> display_level mapping. Ranks not in this map are excluded
#: from the cascade. The mapping is whitelisted (no defaults) so
#: adding a new rank is a deliberate choice.
RANK_TO_DISPLAY_LEVEL: Final[dict[str, str]] = {
    # realm
    "domain": "realm",
    "superdomain": "realm",
    "subdomain": "realm",
    "realm": "realm",
    # kingdom
    "kingdom": "kingdom",
    "subkingdom": "kingdom",
    # phylum
    "phylum": "phylum",
    "subphylum": "phylum",
    "infraphylum": "phylum",
    "parvphylum": "phylum",
    "microphylum": "phylum",
    "megaclass": "phylum",
    # class
    "class": "class",
    "subclass": "class",
    "infraclass": "class",
    "magnorder": "class",
    "superorder": "class",
    # order
    "order": "order",
    "suborder": "order",
    "infraorder": "order",
    "parvorder": "order",
    # family
    "superfamily": "family",
    "family": "family",
    "subfamily": "family",
    "tribe": "family",
    "subtribe": "family",
    "infratribe": "family",
    # genus
    "genus": "genus",
    "subgenus": "genus",
    # species
    "species": "species",
    "subspecies": "species",
    "variety": "species",
    "subvariety": "species",
    "form": "species",
    "subform": "species",
    "forma_specialis": "species",
}


def display_level(rank: str) -> str | None:
    """Map a CoL rank name to its display_level bucket.

    Returns ``None`` for ranks that should not appear in the cascade
    (unranked, historical ranks, and the year-numeric noise that the
    .txtree parser accidentally emits). The caller decides what to
    do with ``None`` — the cascade UI uses it as a filter, the search
    endpoint can use it as an empty-result hint.

    The lookup is case-insensitive. CoL's parser emits lowercase
    canonical names (``"species"``, ``"unranked"``) but the
    :class:`Taxon` table stores the rank as CoL publishes it; we
    normalise here so the importer can call ``display_level`` with
    whatever case the row carries.
    """
    return RANK_TO_DISPLAY_LEVEL.get(rank.lower() if rank else "")


def is_cascade_visible(rank: str) -> bool:
    """True when the rank has a bucket in the cascade.

    Equivalent to ``display_level(rank) is not None`` but reads
    better at the call site.
    """
    return RANK_TO_DISPLAY_LEVEL.get(rank) is not None


__all__ = [
    "DISPLAY_LEVELS",
    "RANK_TO_DISPLAY_LEVEL",
    "display_level",
    "is_cascade_visible",
]
