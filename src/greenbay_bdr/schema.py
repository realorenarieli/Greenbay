"""Data schema for Greenbay BDR outreach tracking.

This module defines the shape of a single reach-out record. The fields mirror a
Clay "reach-out" table so that a Clay CSV export (or an inbound-webhook payload)
maps onto ``OutreachRecord`` with minimal translation. Clay is the human-facing
list/enrichment edge; see ``docs/ARCHITECTURE.md`` for why our own store, not
Clay, is the canonical system of record.

Nothing here is a secret and nothing here is live: these are plain data
definitions used by the loaders, metrics, and dashboard modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# Funnel stages
# ---------------------------------------------------------------------------
# Ordered top-to-bottom. A record's ``stage`` is the FURTHEST stage it has
# reached; the funnel metric counts a record toward every stage at or before
# its current one (a "replied" record has, by definition, also been sourced,
# enriched, first-touched and followed up).

FUNNEL: tuple[str, ...] = (
    "sourced",             # contact identified / added to the list
    "enriched",            # Clay enrichment completed (email, title, etc.)
    "first_touch",         # first outreach email sent
    "followed_up",         # at least one follow-up sent
    "replied",             # prospect replied (any sentiment)
    "meeting_booked",      # an intro meeting was booked
    "intro_meeting_held",  # the intro meeting actually happened (Oren involved)
)

# Human-readable labels for the dashboard.
STAGE_LABELS: dict[str, str] = {
    "sourced": "Sourced",
    "enriched": "Enriched",
    "first_touch": "First touch",
    "followed_up": "Followed up",
    "replied": "Replied",
    "meeting_booked": "Meeting booked",
    "intro_meeting_held": "Intro meeting held",
}

# Canonical prospect segments (ICP cuts). Kept as a tuple so the dashboard can
# show them in a stable order even when a segment has zero rows.
SEGMENTS: tuple[str, ...] = (
    "Transit / bus fleets",
    "Logistics / last-mile",
    "Municipal fleets",
    "EV fleet operators",
)

# Allowed reply-sentiment values (None means "no reply / not classified").
REPLY_SENTIMENTS: tuple[str, ...] = ("positive", "neutral", "negative")


def stage_index(stage: str) -> int:
    """Return the ordinal position of ``stage`` in :data:`FUNNEL`.

    Raises ``ValueError`` for an unknown stage so bad data fails loudly rather
    than silently landing at the top of the funnel.
    """
    try:
        return FUNNEL.index(stage)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(
            f"unknown funnel stage {stage!r}; expected one of {FUNNEL}"
        ) from exc


@dataclass
class OutreachRecord:
    """A single reach-out row, mirroring a Clay reach-out table.

    Dates are ``datetime.date`` or ``None``. Booleans are real booleans. The
    loaders are responsible for parsing raw CSV/JSON strings into these types.
    """

    company: str
    contact_name: str
    title: str
    email: str
    segment: str
    source: str
    stage: str
    first_touch_date: Optional[date] = None
    last_touch_date: Optional[date] = None
    touches: int = 0
    replied: bool = False
    reply_sentiment: Optional[str] = None
    meeting_booked: bool = False
    meeting_date: Optional[date] = None
    owner: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        # Validate the categorical fields early so downstream metrics can trust
        # them. We do not mutate the data, only reject clearly-invalid rows.
        if self.stage not in FUNNEL:
            raise ValueError(
                f"{self.company!r}: unknown stage {self.stage!r}; "
                f"expected one of {FUNNEL}"
            )
        if self.reply_sentiment is not None and self.reply_sentiment not in REPLY_SENTIMENTS:
            raise ValueError(
                f"{self.company!r}: unknown reply_sentiment "
                f"{self.reply_sentiment!r}; expected one of {REPLY_SENTIMENTS} or None"
            )

    @property
    def stage_rank(self) -> int:
        """Ordinal position of this record's stage in the funnel."""
        return stage_index(self.stage)

    def reached(self, stage: str) -> bool:
        """True if this record has reached ``stage`` or gone beyond it."""
        return self.stage_rank >= stage_index(stage)

    @property
    def follow_ups_sent(self) -> int:
        """Follow-ups sent = touches beyond the first. Never negative."""
        return max(0, self.touches - 1)
