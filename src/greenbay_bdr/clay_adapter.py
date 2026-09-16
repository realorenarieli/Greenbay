"""Clay integration adapter - honest about what is CONFIRMED vs UNCERTAIN.

Grounding (see the integration research and ``docs/INTEGRATIONS.md``):

  Clay is a table + async-enrichment engine, NOT a low-latency request/response
  API. In this system Clay is the LIST / ENRICHMENT EDGE and the human-facing
  "reach-out table". It is NOT our real-time system of record; our own datastore
  is canonical (see ``docs/ARCHITECTURE.md``). Treat Clay as eventually-consistent.

Three functions, matching the three real Clay data paths:

  * ``read_table_from_csv_export`` - CONFIRMED, the reliable read path.
  * ``read_table_via_public_api``  - the young/UNCERTAIN Public API (read-only
    Tables). Verify the endpoint against live docs; fails gracefully.
  * ``write_rows_via_inbound_webhook`` - CONFIRMED write path (async).

Credentials are read from environment variables; nothing is hardcoded.
Standard library only (``urllib``, ``json``, ``os``).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Optional, Union

from .loaders import load_records_from_csv, records_from_payload
from .schema import OutreachRecord

PathLike = Union[str, Path]

# Environment variable names this module reads (never hardcode secrets).
ENV_API_KEY = "CLAY_API_KEY"
ENV_TABLE_ID = "CLAY_TABLE_ID"
ENV_WEBHOOK_URL = "CLAY_WEBHOOK_URL"

# Documented, non-Enterprise lifetime cap on submissions per inbound webhook.
# (CONFIRMED in research. The cap persists even after deleting rows; create a
# new webhook once hit, or use an Enterprise auto-delete/passthrough table.)
INBOUND_WEBHOOK_SUBMISSION_CAP = 50_000


# ---------------------------------------------------------------------------
# READ path 1 - CSV export (CONFIRMED, reliable)
# ---------------------------------------------------------------------------
def read_table_from_csv_export(path: PathLike) -> list[OutreachRecord]:
    """Load a Clay reach-out table from a manual CSV export.

    CONFIRMED: Clay supports manual CSV export from the table UI. This is the
    reliable read path and a drop-in for :func:`loaders.load_records_from_csv`.

    NOT CONFIRMED: scheduled / automated CSV export is not a documented
    first-class Clay feature; treat CSV export as a manual step (a human clicks
    export, or you drop the file into ``data/``). For unattended reads, prefer
    the inbound-webhook write path plus your own store as the canonical source.
    """
    return load_records_from_csv(path)


# ---------------------------------------------------------------------------
# READ path 2 - Public API (UNCERTAIN, young)
# ---------------------------------------------------------------------------
def read_table_via_public_api(
    api_key: Optional[str] = None,
    table_id: Optional[str] = None,
    *,
    base_url: Optional[str] = None,
    limit: int = 100,
    timeout: float = 30.0,
) -> list[OutreachRecord]:
    """Read rows from a Clay table via the Public API. STUB - VERIFY BEFORE USE.

    STATUS: UNCERTAIN. Clay reportedly launched a Public REST API (mid-2026)
    whose Tables surface is READ-ONLY: you can query/read rows but cannot create
    tables, add fields, or write records through it. Basic row reads work on any
    plan; advanced querying (joins, ranges, pagination beyond ~100 rows) is an
    Enterprise "API table sync" feature. Third-party reviews from the same period
    still describe Clay as having no versioned public endpoint catalog and no
    OpenAPI spec, so the maturity picture is genuinely conflicting.

    Because the exact endpoint path and response schema are NOT reliably
    documented, this function does not invent them. It requires you to pass an
    explicit ``base_url`` (the verified endpoint from current Clay docs) and it
    fails with an informative error rather than guessing. When you do wire it up,
    map the returned rows through :func:`loaders.records_from_payload`.

    Auth: CONFIRMED to be a single static workspace API key (no OAuth, no
    rotation), sent as a bearer token. Read it from the ``CLAY_API_KEY`` env var.

    Raises:
        NotImplementedError: if ``base_url`` is not supplied (the safe default,
            so we never pretend to call an endpoint we have not verified).
        RuntimeError: on missing credentials or an HTTP/transport failure.
    """
    api_key = api_key or os.environ.get(ENV_API_KEY)
    table_id = table_id or os.environ.get(ENV_TABLE_ID)

    if not api_key:
        raise RuntimeError(
            f"Clay Public API key not provided. Set the {ENV_API_KEY} env var or "
            "pass api_key=. (CONFIRMED: auth is a single static workspace key.)"
        )
    if not table_id:
        raise RuntimeError(
            f"Clay table id not provided. Set the {ENV_TABLE_ID} env var or pass "
            "table_id=."
        )
    if not base_url:
        raise NotImplementedError(
            "Clay Public API endpoint is UNCERTAIN and intentionally not "
            "hardcoded. Verify the exact read endpoint against current Clay docs "
            "(https://university.clay.com/docs/using-clay-as-an-api), then pass it "
            "as base_url=... so this function can call the real, verified URL. "
            "For a reliable read today, use read_table_from_csv_export() instead."
        )

    # If a verified base_url IS supplied, make a best-effort GET. The exact query
    # params / pagination cursor must be adjusted to match the live API.
    url = f"{base_url.rstrip('/')}/{table_id}?limit={int(limit)}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Clay Public API returned HTTP {exc.code} for {url}. The endpoint or "
            "auth may be wrong, or this capability may be plan-gated. Verify "
            "against current Clay docs."
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Clay Public API request failed: {exc.reason}") from exc

    # The response shape is not guaranteed; adapt this mapping to the live schema.
    return records_from_payload(payload)


# ---------------------------------------------------------------------------
# WRITE path - inbound webhook (CONFIRMED)
# ---------------------------------------------------------------------------
def _row_to_dict(row: Union[OutreachRecord, dict[str, Any]]) -> dict[str, Any]:
    """Normalize a record or plain dict into a JSON-serializable dict."""
    if isinstance(row, OutreachRecord):
        out: dict[str, Any] = {}
        for k, v in vars(row).items():
            # dates -> ISO strings so json.dumps works
            out[k] = v.isoformat() if hasattr(v, "isoformat") else v
        return out
    return dict(row)


def write_rows_via_inbound_webhook(
    rows: Iterable[Union[OutreachRecord, dict[str, Any]]],
    webhook_url: Optional[str] = None,
    *,
    timeout: float = 30.0,
    header_token: Optional[str] = None,
) -> list[int]:
    """POST rows to a Clay table's inbound webhook. CONFIRMED write mechanism.

    CONFIRMED: The primary way to WRITE into Clay is an inbound webhook. You
    create a table whose source is a webhook; Clay gives you a unique URL; you
    POST JSON, and each POST becomes a row that then runs through the table's
    enrichment columns.

    IMPORTANT async behavior (CONFIRMED): the POST is fire-and-async. Clay
    acknowledges receipt but enrichment happens over the following minutes; the
    enriched result is NOT returned in the HTTP response. Do not treat a 200 as
    "row is enriched" - only as "row was accepted".

    Submission cap (CONFIRMED): non-Enterprise webhooks have a lifetime cap of
    %(cap)s submissions that persists even after rows are deleted; once hit, you
    must create a new webhook (or use an Enterprise auto-delete/passthrough
    table). This function does not track the running total for you.

    Not confirmed: programmatic UPDATE of an existing row. The webhook path is
    insert-a-row; updating a specific existing row via API is not documented.

    Auth: the webhook URL is itself the secret; an optional header token may be
    configured on the table. Read the URL from ``CLAY_WEBHOOK_URL``; never
    hardcode it.

    Returns:
        A list of HTTP status codes, one per row POSTed (rows are sent
        individually because each POST creates one row).

    Raises:
        RuntimeError: on missing webhook URL or a transport failure.
    """
    webhook_url = webhook_url or os.environ.get(ENV_WEBHOOK_URL)
    if not webhook_url:
        raise RuntimeError(
            f"Clay inbound webhook URL not provided. Set the {ENV_WEBHOOK_URL} env "
            "var or pass webhook_url=. (The URL is the secret; do not hardcode it.)"
        )

    headers = {"Content-Type": "application/json"}
    if header_token:
        headers["x-clay-webhook-auth"] = header_token

    statuses: list[int] = []
    for row in rows:
        body = json.dumps(_row_to_dict(row)).encode("utf-8")
        req = urllib.request.Request(
            webhook_url, data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                statuses.append(resp.status)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"Clay inbound webhook returned HTTP {exc.code}. Check the URL and "
                "(if configured) the header token."
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Clay inbound webhook request failed: {exc.reason}"
            ) from exc
    return statuses


# Interpolate the cap into the docstring once, at import time.
write_rows_via_inbound_webhook.__doc__ = (
    write_rows_via_inbound_webhook.__doc__ or ""
) % {"cap": f"{INBOUND_WEBHOOK_SUBMISSION_CAP:,}"}
