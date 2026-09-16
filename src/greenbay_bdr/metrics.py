"""Compute an honest BDR funnel from a list of :class:`OutreachRecord`.

WHAT IS INTENTIONALLY EXCLUDED: there is no "open rate" anywhere in this module.
Email opens are not reliably measurable. The Gmail API exposes no open event, and
the only workaround (a tracking pixel) is unreliable: Gmail proxies and prefetches
images through Google's servers, so a pixel fetch usually reflects Google caching
rather than a human open, and image-blocking clients never load it at all. Showing
an open rate would be fabricating a metric, so we do not compute one. See
``docs/INTEGRATIONS.md`` and the integration research for sources.

Everything here is derived arithmetically from the records passed in. No network,
no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from .schema import FUNNEL, SEGMENTS, OutreachRecord, stage_index


def _safe_rate(numerator: int, denominator: int) -> float:
    """Return numerator/denominator, or 0.0 when denominator is 0."""
    return (numerator / denominator) if denominator else 0.0


@dataclass
class WeeklyPoint:
    """One ISO-week bucket of activity."""

    iso_week: str          # e.g. "2026-W32"
    week_start: date       # Monday of that ISO week
    first_touches: int = 0
    meetings_booked: int = 0


@dataclass
class SegmentBreakdown:
    """Per-segment funnel slice."""

    segment: str
    contacts: int = 0
    first_touches: int = 0
    replies: int = 0
    positive_replies: int = 0
    meetings_booked: int = 0

    @property
    def reply_rate(self) -> float:
        return _safe_rate(self.replies, self.first_touches)


@dataclass
class NextAction:
    """An open follow-up / next action surfaced for a human."""

    company: str
    contact_name: str
    segment: str
    stage: str
    owner: str
    action: str
    reference_date: Optional[date] = None


@dataclass
class FunnelMetrics:
    """The full set of computed metrics for a dashboard render."""

    generated_for_count: int
    stage_counts: dict[str, int]           # cumulative: reached stage-or-beyond
    first_touches_sent: int
    follow_ups_sent: int
    replies: int
    positive_replies: int
    neutral_replies: int
    negative_replies: int
    meetings_booked: int
    intro_meetings_held: int
    by_segment: list[SegmentBreakdown]
    weekly: list[WeeklyPoint]
    next_actions: list[NextAction]

    # ---- derived rates (all guard against division by zero) --------------
    @property
    def reply_rate(self) -> float:
        """Replies / first-touches sent."""
        return _safe_rate(self.replies, self.first_touches_sent)

    @property
    def positive_reply_rate(self) -> float:
        """Positive replies / first-touches sent (share of outreach that got
        a positive reply). This is the quality signal, more meaningful than raw
        reply rate."""
        return _safe_rate(self.positive_replies, self.first_touches_sent)

    @property
    def positive_share_of_replies(self) -> float:
        """Of the replies received, the share that were positive."""
        return _safe_rate(self.positive_replies, self.replies)

    @property
    def meeting_booked_rate(self) -> float:
        """Meetings booked / first-touches sent."""
        return _safe_rate(self.meetings_booked, self.first_touches_sent)

    @property
    def meeting_held_rate(self) -> float:
        """Intro meetings held / meetings booked (show rate)."""
        return _safe_rate(self.intro_meetings_held, self.meetings_booked)


def _iso_week_key(d: date) -> tuple[str, date]:
    """Return ("YYYY-Www", monday_of_that_week) for a date."""
    iso_year, iso_week, _ = d.isocalendar()
    # Monday of the ISO week:
    monday = date.fromisocalendar(iso_year, iso_week, 1)
    return f"{iso_year}-W{iso_week:02d}", monday


def compute_weekly_trend(records: list[OutreachRecord]) -> list[WeeklyPoint]:
    """First-touches (by first_touch_date) and meetings booked (by meeting_date)
    bucketed per ISO week, sorted chronologically. Weeks with any activity from
    either measure appear; the range is filled so there are no gaps between the
    first and last active week."""
    buckets: dict[str, WeeklyPoint] = {}

    def _bucket(d: date) -> WeeklyPoint:
        key, monday = _iso_week_key(d)
        if key not in buckets:
            buckets[key] = WeeklyPoint(iso_week=key, week_start=monday)
        return buckets[key]

    for r in records:
        if r.first_touch_date is not None and r.reached("first_touch"):
            _bucket(r.first_touch_date).first_touches += 1
        if r.meeting_booked and r.meeting_date is not None:
            _bucket(r.meeting_date).meetings_booked += 1

    if not buckets:
        return []

    # Fill gaps between the earliest and latest active week so the trend line
    # has no invisible holes.
    points = sorted(buckets.values(), key=lambda p: p.week_start)
    first_start = points[0].week_start
    last_start = points[-1].week_start
    filled: list[WeeklyPoint] = []
    cursor = first_start
    while cursor <= last_start:
        key, monday = _iso_week_key(cursor)
        filled.append(buckets.get(key, WeeklyPoint(iso_week=key, week_start=monday)))
        # advance one week
        cursor = date.fromordinal(cursor.toordinal() + 7)
    return filled


def compute_segment_breakdown(records: list[OutreachRecord]) -> list[SegmentBreakdown]:
    """Per-segment slice, in the canonical :data:`SEGMENTS` order, with any
    extra/unknown segments appended alphabetically."""
    seen: dict[str, SegmentBreakdown] = {}

    def _get(segment: str) -> SegmentBreakdown:
        if segment not in seen:
            seen[segment] = SegmentBreakdown(segment=segment)
        return seen[segment]

    for r in records:
        sb = _get(r.segment)
        sb.contacts += 1
        if r.reached("first_touch"):
            sb.first_touches += 1
        if r.replied:
            sb.replies += 1
            if r.reply_sentiment == "positive":
                sb.positive_replies += 1
        if r.meeting_booked:
            sb.meetings_booked += 1

    ordered: list[SegmentBreakdown] = [seen[s] for s in SEGMENTS if s in seen]
    extras = sorted(s for s in seen if s not in SEGMENTS)
    ordered.extend(seen[s] for s in extras)
    return ordered


def compute_next_actions(
    records: list[OutreachRecord],
    today: Optional[date] = None,
    stale_touch_days: int = 4,
) -> list[NextAction]:
    """Surface open follow-ups / next actions a human should act on.

    Rules (in priority order per record):
      1. Replied but no meeting booked -> "Reply received, book the meeting".
      2. Meeting booked but not yet held -> "Meeting booked, confirm / prep".
      3. First touch or follow-up sent, no reply, last touch older than
         ``stale_touch_days`` -> "Due for follow-up".
    Records that have already held the intro meeting, or are still pre-outreach,
    produce no action.
    """
    today = today or date.today()
    actions: list[NextAction] = []
    for r in records:
        if r.stage == "intro_meeting_held":
            continue
        if r.replied and not r.meeting_booked:
            actions.append(
                NextAction(
                    company=r.company,
                    contact_name=r.contact_name,
                    segment=r.segment,
                    stage=r.stage,
                    owner=r.owner,
                    action="Reply received, book the intro meeting",
                    reference_date=r.last_touch_date,
                )
            )
        elif r.meeting_booked and r.stage != "intro_meeting_held":
            actions.append(
                NextAction(
                    company=r.company,
                    contact_name=r.contact_name,
                    segment=r.segment,
                    stage=r.stage,
                    owner=r.owner,
                    action="Meeting booked, confirm and prep Oren",
                    reference_date=r.meeting_date,
                )
            )
        elif r.reached("first_touch") and not r.replied:
            ref = r.last_touch_date or r.first_touch_date
            if ref is not None and (today - ref).days >= stale_touch_days:
                actions.append(
                    NextAction(
                        company=r.company,
                        contact_name=r.contact_name,
                        segment=r.segment,
                        stage=r.stage,
                        owner=r.owner,
                        action=f"No reply in {(today - ref).days} days, due for follow-up",
                        reference_date=ref,
                    )
                )

    # Most-recent reference date first so the freshest items lead.
    actions.sort(key=lambda a: (a.reference_date or date.min), reverse=True)
    return actions


def compute_metrics(
    records: list[OutreachRecord],
    today: Optional[date] = None,
) -> FunnelMetrics:
    """Compute the full :class:`FunnelMetrics` from a list of records.

    NOTE: no open rate is computed here, by design (see module docstring).
    """
    stage_counts = {stage: 0 for stage in FUNNEL}
    for r in records:
        rank = r.stage_rank
        for i, stage in enumerate(FUNNEL):
            if rank >= i:
                stage_counts[stage] += 1

    first_touches_sent = sum(1 for r in records if r.reached("first_touch"))
    follow_ups_sent = sum(r.follow_ups_sent for r in records if r.reached("first_touch"))

    replies = sum(1 for r in records if r.replied)
    positive_replies = sum(1 for r in records if r.reply_sentiment == "positive")
    neutral_replies = sum(1 for r in records if r.reply_sentiment == "neutral")
    negative_replies = sum(1 for r in records if r.reply_sentiment == "negative")

    meetings_booked = sum(1 for r in records if r.meeting_booked)
    intro_meetings_held = sum(1 for r in records if r.stage == "intro_meeting_held")

    return FunnelMetrics(
        generated_for_count=len(records),
        stage_counts=stage_counts,
        first_touches_sent=first_touches_sent,
        follow_ups_sent=follow_ups_sent,
        replies=replies,
        positive_replies=positive_replies,
        neutral_replies=neutral_replies,
        negative_replies=negative_replies,
        meetings_booked=meetings_booked,
        intro_meetings_held=intro_meetings_held,
        by_segment=compute_segment_breakdown(records),
        weekly=compute_weekly_trend(records),
        next_actions=compute_next_actions(records, today=today),
    )
