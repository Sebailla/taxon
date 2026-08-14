"""Thin client for the GBIF Species API.

The cascade UI reads a 6-tier taxonomy (kingdom → phylum → order
→ family → genus → species) that the GBIF backbone already exposes
in two shapes:

- ``/v1/species/{key}`` returns a single taxon row with the
  kingdom/phylum/order/family/genus/species pre-resolved.
- ``/v1/species/{key}/children`` returns the direct children
  with the same breadcrumb columns.

This module wraps both endpoints behind a single Python client
so the backend resolver can compose a path → children query
without thinking about URL construction, pagination, or HTTP
edge cases.

The contract is pure I/O: no caching, no state, no DB. The
caller (the cascade resolver) is responsible for memoising
results when latency matters.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

#: GBIF's public Species API. No auth required, no rate-limit
#: headers needed for the read-only paths this client uses.
GBIF_BASE_URL: str = "https://api.gbif.org/v1"

#: Cascades rarely navigate more than 200 direct children at
#: any level (the largest phylum has ~150,000 species but the
#: genus level is the natural break). 300 is a comfortable cap
#: that keeps the response payload small for the cascade UI.
DEFAULT_CHILD_LIMIT: int = 300


@dataclass(frozen=True)
class GbifTaxon:
    """A single taxon row from the GBIF Species API.

    The fields kept here are the ones the cascade uses to label
    dropdowns and compute the "next rank" hint. Every other
    field of the GBIF response (``numDescendants``, ``issues``,
    ``habitats``, etc.) is dropped — the cascade UI does not
    need them.
    """

    key: int
    nub_key: int
    canonical_name: str
    scientific_name: str
    rank: str
    kingdom: str | None
    phylum: str | None
    order: str | None
    family: str | None
    genus: str | None
    species: str | None
    parent_key: int | None
    parent: str | None
    num_children: int | None


class GbifClient:
    """Stateless HTTP client for the GBIF Species API.

    The client is instantiated once per request and held for
    the lifetime of the request. There is no connection pool
    reuse across requests because httpx's defaults are fine for
    the volumes a single cascade generates (1-2 requests per
    click). The caller can hand the client a timeout to bound
    the worst-case latency.
    """

    def __init__(
        self,
        base_url: str = GBIF_BASE_URL,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        # The transport-injection seam lets tests stub the network
        # without monkey-patching httpx. Production callers leave
        # ``client=None`` so the client owns the HTTP lifecycle.
        self._client = client

    def get_taxon(self, key: int) -> GbifTaxon | None:
        """Return the taxon at ``key`` or ``None`` if it does not exist.

        GBIF returns 404 for missing keys; we translate that to
        ``None`` so callers can branch without exception handling.
        Any other HTTP error is re-raised so the FastAPI exception
        handler renders a 502 with the upstream status.
        """
        response = self._request(lambda c: c.get(f"{self._base_url}/species/{key}"))
        if response is None:
            return None
        return _parse_taxon(response.json())

    def get_children(
        self,
        key: int,
        limit: int = DEFAULT_CHILD_LIMIT,
        offset: int = 0,
        rank: str | None = None,
    ) -> list[GbifTaxon]:
        """Return direct children of ``key``, paginated.

        GBIF paginates with ``limit`` + ``offset``; the cascade
        renders the first page in a single dropdown. The caller
        passes ``offset`` to fetch subsequent pages when the
        chain reaches a genus with thousands of species.

        The optional ``rank`` filter scopes the result to direct
        children at a single rank. The cascade resolver uses
        this to render one dropdown per tier — Chordata's
        children include classes, orders, and families, and the
        resolver picks the next-tier bucket explicitly.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if rank is not None:
            params["rank"] = rank
        response = self._request(
            lambda c: c.get(
                f"{self._base_url}/species/{key}/children",
                params=params,
            )
        )
        if response is None:
            return []
        body = response.json()
        return [_parse_taxon(row) for row in body.get("results", [])]

    def search(
        self,
        name: str,
        rank: str | None = None,
        higher_taxon_key: int | None = None,
        accepted_only: bool = True,
        limit: int = 20,
    ) -> list[GbifTaxon]:
        """Search GBIF for taxa whose canonical name matches ``name``.

        The ``rank`` and ``higherTaxonKey`` filters disambiguate
        GBIF's fuzzy search: 54,284 rows match ``Animalia`` on
        rank alone, but the same query with ``rank=KINGDOM``
        returns just the kingdom. The cascade resolver passes
        both filters for every segment after the first.

        GBIF returns accepted taxa first when
        ``accepted_only=True``. The cascade UI only renders
        accepted taxa, so the resolver short-circuits on the
        first hit.
        """
        params: dict[str, Any] = {
            "q": name,
            "limit": limit,
            "offset": 0,
        }
        if accepted_only:
            params["status"] = "ACCEPTED"
        if rank is not None:
            params["rank"] = rank
        if higher_taxon_key is not None:
            params["higherTaxonKey"] = higher_taxon_key
        response = self._request(lambda c: c.get(f"{self._base_url}/species/search", params=params))
        if response is None:
            return []
        body = response.json()
        return [_parse_taxon(row) for row in body.get("results", [])]

    def _request(
        self, request_fn: Callable[[httpx.Client], httpx.Response]
    ) -> httpx.Response | None:
        """Run a single request. Returns the response on success,
        ``None`` on 404, raises on 5xx."""
        if self._client is not None:
            return self._run_with(self._client, request_fn)
        with httpx.Client(timeout=self._timeout) as client:
            return self._run_with(client, request_fn)

    @staticmethod
    def _run_with(
        client: httpx.Client,
        request_fn: Callable[[httpx.Client], httpx.Response],
    ) -> httpx.Response | None:
        response: httpx.Response = request_fn(client)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response


def _parse_taxon(row: dict[str, Any]) -> GbifTaxon:
    """Translate a raw GBIF row into a :class:`GbifTaxon`.

    The GBIF response uses uppercase rank enums ("KINGDOM",
    "PHYLUM", "ORDER", "FAMILY", "GENUS", "SPECIES"). We keep
    that casing because the cascade UI uses it for the dropdown
    label and any mapping would just be a rename layer.

    Some GBIF responses (e.g. virus kingdoms) ship rows without
    ``canonicalName`` (the GBIF search backend treats those as
    placeholder rows). We fall back to ``scientificName`` (which
    is always populated) so the cascade UI still gets a usable
    label.
    """
    return GbifTaxon(
        key=row["key"],
        nub_key=row.get("nubKey", row["key"]),
        canonical_name=row.get("canonicalName") or row["scientificName"],
        scientific_name=row["scientificName"],
        rank=row["rank"],
        kingdom=row.get("kingdom"),
        phylum=row.get("phylum"),
        order=row.get("order"),
        family=row.get("family"),
        genus=row.get("genus"),
        species=row.get("species"),
        parent_key=row.get("parentKey"),
        parent=row.get("parent"),
        num_children=row.get("numDescendants"),
    )


__all__ = [
    "DEFAULT_CHILD_LIMIT",
    "GBIF_BASE_URL",
    "GbifClient",
    "GbifTaxon",
]
