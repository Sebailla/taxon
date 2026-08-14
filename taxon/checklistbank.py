"""HTTP client + parser for the ChecklistBank API.

ChecklistBank (CLB) is the curated taxonomy source for the
Catalogue of Life (CoL). CLB exposes a JSON REST API at
https://api.checklistbank.org. This client is the single point
of contact with CLB for the cascade resolver.

The cascade resolver uses three operations:

- ``get_taxon(taxon_id, dataset_key="COL2024")`` fetches a single
  taxon by its CLB identifier (an opaque string like "N" for
  Animalia).
- ``get_children(taxon_id, dataset_key)`` lists the direct
  children of a taxon.
- ``search(q, rank, dataset_key)`` finds taxa by name.

The dataset_key defaults to ``COL2024`` (the annual CoL release).
The ``3LR`` magic key is documented as the future upgrade path
but is NOT used in v1.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_DATASET_KEY = "COL2024"
"""Pinned CoL release. The ``3LR`` magic key is the future
upgrade path for "always the latest release" semantics; swap
this constant when that endpoint is verified."""

CLB_BASE_URL = "https://api.checklistbank.org"

DEFAULT_CHILD_LIMIT = 300
"""Cascades rarely navigate more than ~200 direct children at
any level. 300 is a comfortable cap that keeps the response
payload small for the cascade UI."""


@dataclass(frozen=True)
class ChecklistBankTaxon:
    """A single CLB taxon row mapped to the cascade contract.

    Field names mirror the legacy GbifTaxon where possible so the
    cascade UI does not need to change. The CLB integer ``key``
    is replaced by an opaque string ``taxon_id``; the dataset
    key is always present.
    """

    taxon_id: str
    dataset_key: str
    canonical_name: str
    scientific_name: str
    rank: str
    parent_id: str | None = None
    label_html: str | None = None  # CLB renders italics in labelHtml
    count: int | None = None  # CLB's `count` = total descendants
    child_count: int | None = None  # CLB's `childCount` = direct children
    status: str | None = None  # accepted / synonym / ...


class ChecklistBankClient:
    """HTTP client + parser for the ChecklistBank API.

    The transport seam (``client=``) lets tests inject an
    ``httpx.MockTransport`` without monkey-patching. Production
    callers leave the default and the client owns the HTTP
    lifecycle.
    """

    def __init__(
        self,
        base_url: str = CLB_BASE_URL,
        dataset_key: str = DEFAULT_DATASET_KEY,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._dataset_key = dataset_key
        self._timeout = timeout_seconds
        # The transport-injection seam lets tests stub the network
        # without monkey-patching httpx. Production callers leave
        # ``client=None`` so the client owns the HTTP lifecycle.
        self._client = client

    def get_taxon(self, taxon_id: str, dataset_key: str | None = None) -> ChecklistBankTaxon | None:
        """Return the taxon at ``taxon_id`` or ``None`` if missing.

        CLB returns 404 for missing keys; we translate that to
        ``None`` so callers can branch without exception handling.
        Any other HTTP error is re-raised so the FastAPI exception
        handler renders a 502 with the upstream status.
        """
        effective_key = dataset_key if dataset_key is not None else self._dataset_key
        response = self._request(
            lambda c: c.get(f"{self._base_url}/dataset/{effective_key}/nameusage/{taxon_id}")
        )
        if response is None:
            return None
        return _parse_taxon(response.json())

    def get_children(
        self,
        taxon_id: str,
        dataset_key: str | None = None,
        limit: int = DEFAULT_CHILD_LIMIT,
        offset: int = 0,
        rank: str | None = None,
    ) -> list[ChecklistBankTaxon]:
        """Return direct children of ``taxon_id``, paginated.

        CLB paginates with ``limit`` + ``offset``; the cascade
        renders the first page in a single dropdown. The caller
        passes ``offset`` to fetch subsequent pages when the
        chain reaches a genus with thousands of species.

        The optional ``rank`` filter scopes the result to direct
        children at a single rank. The cascade resolver uses
        this to render one dropdown per tier — Chordata's
        children include classes, orders, and families, and the
        resolver picks the next-tier bucket explicitly.

        The resolver also passes ``rank="subphylum"`` to probe
        whether a phylum has subphylum children; an empty
        response triggers the subphylum-collapse rule in PR #2b.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if rank is not None:
            params["rank"] = rank
        effective_key = dataset_key if dataset_key is not None else self._dataset_key
        response = self._request(
            lambda c: c.get(
                f"{self._base_url}/dataset/{effective_key}/tree/{taxon_id}/children",
                params=params,
            )
        )
        if response is None:
            return []
        body = response.json()
        return [_parse_taxon(row) for row in body.get("result", [])]

    def list_roots(
        self,
        dataset_key: str | None = None,
        limit: int = 20,
    ) -> list[ChecklistBankTaxon]:
        """Return the root-tier taxa of ``dataset_key``.

        ChecklistBank exposes the ``/dataset/{key}/tree`` endpoint which
        lists the root nodes (Biota + Viruses for ``COL2024``). The
        cascade UI uses this as the initial dropdown so the user can
        pick a top-level clade before drilling into kingdoms or virus
        realms.

        The endpoint carries the same row shape as
        ``/tree/{id}/children`` (flat: ``id``, ``name``, ``rank``,
        ``parentId``, ...); the parser handles both transparently.
        """
        params: dict[str, Any] = {"limit": limit}
        effective_key = dataset_key if dataset_key is not None else self._dataset_key
        response = self._request(
            lambda c: c.get(
                f"{self._base_url}/dataset/{effective_key}/tree",
                params=params,
            )
        )
        if response is None:
            return []
        body = response.json()
        return [_parse_taxon(row) for row in body.get("result", [])]

    def search(
        self,
        q: str,
        rank: str | None = None,
        dataset_key: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ChecklistBankTaxon]:
        """Search CLB for taxa whose name matches ``q``.

        The ``rank`` filter disambiguates CLB's fuzzy search:
        ``Animalia`` matches at every rank, but the same query
        with ``rank=kingdom`` returns just the kingdom. The
        cascade resolver passes a ``rank`` filter for every
        segment after the first.
        """
        params: dict[str, Any] = {"q": q, "limit": limit, "offset": offset}
        if rank is not None:
            params["rank"] = rank
        effective_key = dataset_key if dataset_key is not None else self._dataset_key
        response = self._request(
            lambda c: c.get(
                f"{self._base_url}/dataset/{effective_key}/nameusage/search",
                params=params,
            )
        )
        if response is None:
            return []
        body = response.json()
        return [_parse_taxon(row) for row in body.get("result", [])]

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


def _parse_taxon(row: dict[str, Any]) -> ChecklistBankTaxon:
    """Translate a raw CLB row into a :class:`ChecklistBankTaxon`.

    CLB returns three distinct row shapes:

    - ``/tree/{id}/children`` rows are flat: ``id``, ``name``,
      ``rank``, ``childCount``, ``count``, ``labelHtml``,
      ``status``, ``datasetKey``, ``parentId``.
    - ``/nameusage/search`` rows nest the canonical fields under
      ``usage`` (``usage.id``, ``usage.name.scientificName``,
      ``usage.name.rank``, ``usage.status``, ``usage.datasetKey``,
      ``usage.parentId``, ...) and add a ``classification[]``
      breadcrumb at the top level.
    - ``/nameusage/{id}`` (single taxon lookup) wraps the whole
      payload under ``usage`` and adds a few metadata fields
      (``created``, ``modified``) at the root.

    The parser normalises all three to the same dataclass.
    Detection is by presence — if ``row["usage"]`` exists it is
    the canonical source; otherwise the row is already flat.

    Missing optional fields coerce to ``None`` so callers can
    branch without ``KeyError``. The cascade uses ``name`` for
    dropdown labels — CLB does not separate canonical from
    scientific names; ``canonical_name`` and
    ``scientific_name`` carry the same value so the cascade UI
    does not need to branch on backend.
    """
    payload: dict[str, Any] = row.get("usage", row)
    return ChecklistBankTaxon(
        taxon_id=str(payload.get("id") or row.get("id", "")),
        dataset_key=str(payload.get("datasetKey", row.get("datasetKey", DEFAULT_DATASET_KEY))),
        canonical_name=_extract_name(payload, row),
        scientific_name=_extract_name(payload, row),
        rank=_extract_rank(payload, row),
        parent_id=_coerce_optional_str(payload.get("parentId", row.get("parentId"))),
        label_html=payload.get("labelHtml", row.get("labelHtml")),
        count=payload.get("count", row.get("count")),
        child_count=payload.get("childCount", row.get("childCount")),
        status=payload.get("status", row.get("status")),
    )


def _extract_name(payload: dict[str, Any], row: dict[str, Any]) -> str:
    """Resolve a display name from a CLB row.

    Priority: ``payload["name"]["scientificName"]`` (live nested
    shape) → ``payload["name"]`` (if it's already a string) →
    ``row["name"]`` (flat shape) → ``""``.
    """
    nested = payload.get("name")
    if isinstance(nested, dict):
        scientific = nested.get("scientificName")
        if isinstance(scientific, str) and scientific:
            return scientific
    if isinstance(nested, str) and nested:
        return nested
    flat = row.get("name")
    if isinstance(flat, str):
        return flat
    return ""


def _extract_rank(payload: dict[str, Any], row: dict[str, Any]) -> str:
    """Resolve the rank string from a CLB row.

    Priority: ``payload.name.rank`` (live nested shape, where
    ``name`` is a dict carrying ``rank`` + ``scientificName``) →
    ``payload.rank`` (live envelope shape) → ``row.rank`` (flat
    children shape) → ``""``.
    """
    nested = payload.get("name")
    if isinstance(nested, dict):
        rank = nested.get("rank")
        if isinstance(rank, str) and rank:
            return rank
    rank = payload.get("rank")
    if isinstance(rank, str) and rank:
        return rank
    flat = row.get("rank")
    if isinstance(flat, str):
        return flat
    return ""


def _coerce_optional_str(value: Any) -> str | None:
    """Coerce a CLB field to ``str | None``. CLB sometimes returns
    integers for ids (``datasetKey`` is an int) so we stringify
    everything except ``None``."""
    if value is None:
        return None
    return str(value)


__all__ = [
    "CLB_BASE_URL",
    "DEFAULT_CHILD_LIMIT",
    "DEFAULT_DATASET_KEY",
    "ChecklistBankClient",
    "ChecklistBankTaxon",
]
