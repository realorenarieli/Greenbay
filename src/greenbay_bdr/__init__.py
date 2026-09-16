"""Greenbay BDR outreach tracking, dashboard, and automation scaffolding.

Standard-library only. No third-party dependencies, no network access at import
time. See ``docs/ARCHITECTURE.md`` and ``docs/INTEGRATIONS.md`` for the design
and the go-live checklist.

Honest status: this package renders a dashboard from SAMPLE data and provides
integration *scaffolding* (Clay / Slack). It is NOT yet wired to live Clay,
Gmail, or Google Calendar. Credentials and decisions still required are listed
in ``docs/INTEGRATIONS.md``.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .schema import (
    FUNNEL,
    SEGMENTS,
    STAGE_LABELS,
    OutreachRecord,
    stage_index,
)

__all__ = [
    "FUNNEL",
    "SEGMENTS",
    "STAGE_LABELS",
    "OutreachRecord",
    "stage_index",
    "__version__",
]
