"""Post a daily reach-out summary to a Slack incoming webhook.

Guarded by the ``SLACK_WEBHOOK_URL`` environment variable: if it is unset, this
module is a no-op and logs a clear message instead of failing. The webhook URL is
a secret and is never hardcoded.

Copy is deliberately free of em dashes (Greenbay outbound-copy rule; applied here
too for consistency).

Standard library only (``urllib``, ``json``, ``os``, ``logging``).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional

from .metrics import FunnelMetrics

ENV_SLACK_WEBHOOK = "SLACK_WEBHOOK_URL"

logger = logging.getLogger(__name__)


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def format_summary_text(metrics: FunnelMetrics, *, sample: bool = True) -> str:
    """Build the one-message Slack summary string (no em dashes).

    ``sample=True`` prefixes an explicit SAMPLE marker so a Slack reader can
    never mistake illustrative numbers for live outreach.
    """
    prefix = "SAMPLE DATA (not live outreach) | " if sample else ""
    return (
        f"{prefix}Greenbay reach-out daily summary: "
        f"{metrics.first_touches_sent} first-touches, "
        f"{metrics.follow_ups_sent} follow-ups, "
        f"{metrics.replies} replies ({_pct(metrics.reply_rate)} reply rate), "
        f"{metrics.positive_replies} positive, "
        f"{metrics.meetings_booked} meetings booked, "
        f"{metrics.intro_meetings_held} intro meetings held "
        f"({_pct(metrics.meeting_held_rate)} show rate). "
        f"Note: open rate is intentionally excluded (opens are not reliably trackable)."
    )


def post_slack_summary(
    metrics: FunnelMetrics,
    webhook_url: Optional[str] = None,
    *,
    sample: bool = True,
    timeout: float = 15.0,
) -> bool:
    """Post a short daily reach-out summary to a Slack incoming webhook.

    The webhook URL is read from the ``SLACK_WEBHOOK_URL`` env var unless passed
    explicitly. If no URL is available this is a NO-OP: it logs a clear message
    and returns ``False`` (it never raises just because the secret is unset, so
    the daily job does not fail when Slack is not configured yet).

    Returns:
        True if a message was posted, False if skipped (no webhook configured).

    Raises:
        RuntimeError: only if a URL IS configured but the POST fails.
    """
    webhook_url = webhook_url or os.environ.get(ENV_SLACK_WEBHOOK)
    if not webhook_url:
        logger.info(
            "%s is not set; skipping Slack post (no-op). "
            "Set the env var / GitHub secret to enable the daily summary.",
            ENV_SLACK_WEBHOOK,
        )
        return False

    text = format_summary_text(metrics, sample=sample)
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            status = resp.status
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Slack webhook returned HTTP {exc.code}. Check the webhook URL."
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Slack webhook request failed: {exc.reason}") from exc

    logger.info("Posted daily reach-out summary to Slack (HTTP %s).", status)
    return True
