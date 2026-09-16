"""Load :class:`OutreachRecord` lists from CSV and JSON.

The CSV path is the reliable, drop-in one: a Clay reach-out table exported to
CSV (or ``data/sample_outreach.csv``) can be loaded directly. The JSON path
accepts either a top-level list of objects or an object with a ``records`` list,
which matches the shape you would receive from a Clay inbound webhook payload or
your own store.

Standard library only (``csv``, ``json``, ``datetime``).
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional, Union

from .schema import OutreachRecord

PathLike = Union[str, Path]

# The canonical field order used by the sample CSV and expected on import.
CSV_FIELDS: tuple[str, ...] = (
    "company",
    "contact_name",
    "title",
    "email",
    "segment",
    "source",
    "stage",
    "first_touch_date",
    "last_touch_date",
    "touches",
    "replied",
    "reply_sentiment",
    "meeting_booked",
    "meeting_date",
    "owner",
    "notes",
)

_TRUE = {"true", "1", "yes", "y", "t"}
_FALSE = {"false", "0", "no", "n", "f", ""}


def _parse_date(value: Any) -> Optional[date]:
    """Parse an ISO date (YYYY-MM-DD). Empty / None -> None."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"invalid date {value!r} (expected YYYY-MM-DD)") from exc


def _parse_bool(value: Any) -> bool:
    """Parse a truthy/falsey cell. Unknown values raise, to fail loudly."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError(f"invalid boolean {value!r}")


def _parse_int(value: Any) -> int:
    if value is None or str(value).strip() == "":
        return 0
    return int(str(value).strip())


def _parse_sentiment(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _record_from_mapping(row: dict[str, Any]) -> OutreachRecord:
    """Build one :class:`OutreachRecord` from a raw string-keyed mapping."""
    return OutreachRecord(
        company=str(row.get("company", "")).strip(),
        contact_name=str(row.get("contact_name", "")).strip(),
        title=str(row.get("title", "")).strip(),
        email=str(row.get("email", "")).strip(),
        segment=str(row.get("segment", "")).strip(),
        source=str(row.get("source", "")).strip(),
        stage=str(row.get("stage", "")).strip(),
        first_touch_date=_parse_date(row.get("first_touch_date")),
        last_touch_date=_parse_date(row.get("last_touch_date")),
        touches=_parse_int(row.get("touches")),
        replied=_parse_bool(row.get("replied", False)),
        reply_sentiment=_parse_sentiment(row.get("reply_sentiment")),
        meeting_booked=_parse_bool(row.get("meeting_booked", False)),
        meeting_date=_parse_date(row.get("meeting_date")),
        owner=str(row.get("owner", "")).strip(),
        notes=str(row.get("notes", "")).strip(),
    )


def load_records_from_csv(path: PathLike) -> list[OutreachRecord]:
    """Load records from a CSV file with a header row.

    Works as a drop-in for a Clay reach-out table exported to CSV, as long as
    the column names match :data:`CSV_FIELDS`. Extra columns are ignored;
    missing optional columns default sensibly.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: empty file / no header row")
        records: list[OutreachRecord] = []
        for lineno, row in enumerate(reader, start=2):  # header is line 1
            try:
                records.append(_record_from_mapping(row))
            except ValueError as exc:
                raise ValueError(f"{path}:{lineno}: {exc}") from exc
    return records


def load_records_from_json(source: PathLike) -> list[OutreachRecord]:
    """Load records from a JSON file.

    Accepts either a top-level JSON array of objects, or an object with a
    ``"records"`` array (the latter matches a Clay inbound-webhook style
    payload). Field names match :data:`CSV_FIELDS`.
    """
    path = Path(source)
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    return records_from_payload(payload)


def records_from_payload(payload: Any) -> list[OutreachRecord]:
    """Turn an already-parsed JSON payload into records.

    Useful when the JSON arrives over the wire (e.g. a webhook body) rather than
    from a file.
    """
    if isinstance(payload, dict):
        rows: Iterable[Any] = payload.get("records", [])
    elif isinstance(payload, list):
        rows = payload
    else:
        raise ValueError("JSON payload must be a list or an object with 'records'")

    records: list[OutreachRecord] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"record #{i} is not an object")
        try:
            records.append(_record_from_mapping(row))
        except ValueError as exc:
            raise ValueError(f"record #{i}: {exc}") from exc
    return records


def load_records(path: PathLike) -> list[OutreachRecord]:
    """Dispatch on file extension: ``.json`` -> JSON, otherwise CSV."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        return load_records_from_json(path)
    return load_records_from_csv(path)
