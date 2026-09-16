"""Render a self-contained light/dark HTML dashboard from computed metrics.

Design follows the data-viz skill's reference palette:
  * Funnel  -> single-hue ORDINAL blue ramp (light-to-dark by stage depth).
  * Segments-> CATEGORICAL slots (blue / orange / aqua / yellow), identity also
               carried by a direct label so it is never color-alone.
  * Weekly  -> two series (first-touches = blue, meetings booked = orange) on a
               SINGLE axis (both are counts), with a legend and end-labels.
All charts are inline SVG generated here in Python. No external assets, no
network: the file works offline and renders in light and dark via
prefers-color-scheme plus an in-page theme toggle.

A prominent SAMPLE banner is always rendered when ``sample=True`` (the default)
so nobody mistakes illustrative rows for live outreach.
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from .metrics import FunnelMetrics
from .schema import STAGE_LABELS

PathLike = Union[str, Path]

# --- palette (from dataviz references/palette.md) -------------------------
# Declared once as CSS custom properties; dark values swap under both the OS
# media query and the data-theme toggle scope, per the reference pattern.
_CSS = """
:root {
  color-scheme: light dark;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--page);
  color: var(--text-primary);
  -webkit-font-smoothing: antialiased;
}
.viz-root {
  color-scheme: light;
  --page: #f9f9f7;
  --surface-1: #fcfcfb;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --muted: #898781;
  --grid: #e1e0d9;
  --baseline: #c3c2b7;
  --border: rgba(11,11,11,0.10);
  --good: #0ca30c;
  --success-text: #006300;
  --warning: #fab219;
  --critical: #d03b3b;
  /* categorical slots */
  --series-1: #2a78d6;  /* blue */
  --series-2: #eb6834;  /* orange */
  --series-3: #1baf7a;  /* aqua */
  --series-4: #eda100;  /* yellow */
  /* ordinal blue ramp for the funnel (light: no lighter than step 250) */
  --funnel-1: #86b6ef;
  --funnel-2: #5598e7;
  --funnel-3: #3987e5;
  --funnel-4: #2a78d6;
  --funnel-5: #1c5cab;
  --funnel-6: #184f95;
  --funnel-7: #0d366b;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) .viz-root {
    color-scheme: dark;
    --page: #0d0d0d;
    --surface-1: #1a1a19;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --muted: #898781;
    --grid: #2c2c2a;
    --baseline: #383835;
    --border: rgba(255,255,255,0.10);
    --good: #0ca30c;
    --success-text: #0ca30c;
    --warning: #fab219;
    --critical: #d03b3b;
    --series-1: #3987e5;
    --series-2: #d95926;
    --series-3: #199e70;
    --series-4: #c98500;
    /* ordinal blue ramp (dark: no darker than step 600) */
    --funnel-1: #cde2fb;
    --funnel-2: #9ec5f4;
    --funnel-3: #86b6ef;
    --funnel-4: #5598e7;
    --funnel-5: #3987e5;
    --funnel-6: #256abf;
    --funnel-7: #184f95;
  }
}
:root[data-theme="dark"] .viz-root {
  color-scheme: dark;
  --page: #0d0d0d;
  --surface-1: #1a1a19;
  --text-primary: #ffffff;
  --text-secondary: #c3c2b7;
  --muted: #898781;
  --grid: #2c2c2a;
  --baseline: #383835;
  --border: rgba(255,255,255,0.10);
  --good: #0ca30c;
  --success-text: #0ca30c;
  --warning: #fab219;
  --critical: #d03b3b;
  --series-1: #3987e5;
  --series-2: #d95926;
  --series-3: #199e70;
  --series-4: #c98500;
  --funnel-1: #cde2fb;
  --funnel-2: #9ec5f4;
  --funnel-3: #86b6ef;
  --funnel-4: #5598e7;
  --funnel-5: #3987e5;
  --funnel-6: #256abf;
  --funnel-7: #184f95;
}
.wrap { max-width: 1040px; margin: 0 auto; padding: 24px 20px 64px; }
header.top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
h1 { font-size: 22px; margin: 0 0 4px; }
.sub { color: var(--text-secondary); font-size: 13px; margin: 0; }
.toggle {
  border: 1px solid var(--border); background: var(--surface-1); color: var(--text-primary);
  border-radius: 8px; padding: 7px 12px; font: inherit; font-size: 13px; cursor: pointer;
}
.banner {
  margin: 18px 0 22px; border-radius: 10px; padding: 12px 16px;
  background: color-mix(in srgb, var(--warning) 18%, var(--surface-1));
  border: 1px solid color-mix(in srgb, var(--warning) 55%, var(--border));
  color: var(--text-primary); font-size: 14px; line-height: 1.5;
}
.banner strong { letter-spacing: 0.02em; }
.grid-kpi { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 26px; }
.tile { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.tile .label { color: var(--text-secondary); font-size: 12px; margin: 0 0 6px; }
.tile .value { font-size: 30px; font-weight: 600; margin: 0; line-height: 1.1; }
.tile .foot { color: var(--muted); font-size: 12px; margin: 6px 0 0; }
section.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 18px 20px; margin-bottom: 22px; }
section.card h2 { font-size: 16px; margin: 0 0 2px; }
section.card .desc { color: var(--text-secondary); font-size: 13px; margin: 0 0 14px; }
svg { max-width: 100%; height: auto; display: block; }
.legend { display: flex; gap: 18px; flex-wrap: wrap; margin: 4px 0 12px; font-size: 13px; color: var(--text-secondary); }
.legend .item { display: inline-flex; align-items: center; gap: 7px; }
.legend .swatch { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--grid); }
th { color: var(--text-secondary); font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; border: 1px solid var(--border); color: var(--text-secondary); }
footer.foot { color: var(--muted); font-size: 12px; margin-top: 8px; line-height: 1.6; }
a { color: var(--series-1); }
"""

_TOGGLE_JS = """
(function () {
  var btn = document.getElementById('theme-toggle');
  if (!btn) return;
  btn.addEventListener('click', function () {
    var root = document.documentElement;
    var cur = root.getAttribute('data-theme');
    var dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    var isDark = cur ? cur === 'dark' : dark;
    root.setAttribute('data-theme', isDark ? 'light' : 'dark');
  });
})();
"""


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _fmt_int(value: int) -> str:
    return f"{value:,}"


def _nice_ceil(value: int) -> int:
    """Round up to a clean axis maximum (>= 1)."""
    if value <= 5:
        return max(value, 1)
    step = 5 if value <= 25 else 10 if value <= 100 else 50
    return ((value + step - 1) // step) * step


# ---------------------------------------------------------------------------
# KPI tiles
# ---------------------------------------------------------------------------
def _kpi_tiles(m: FunnelMetrics) -> str:
    tiles = [
        ("Contacts", _fmt_int(m.generated_for_count), "in the reach-out table"),
        ("First-touches sent", _fmt_int(m.first_touches_sent), f"{_fmt_int(m.follow_ups_sent)} follow-ups"),
        ("Reply rate", _fmt_pct(m.reply_rate), f"{_fmt_int(m.replies)} replies"),
        ("Positive replies", _fmt_int(m.positive_replies), f"{_fmt_pct(m.positive_share_of_replies)} of replies"),
        ("Meetings booked", _fmt_int(m.meetings_booked), f"{_fmt_pct(m.meeting_booked_rate)} of first-touches"),
        ("Intro meetings held", _fmt_int(m.intro_meetings_held), f"{_fmt_pct(m.meeting_held_rate)} show rate"),
    ]
    cells = []
    for label, value, foot in tiles:
        cells.append(
            f'<div class="tile"><p class="label">{_esc(label)}</p>'
            f'<p class="value">{_esc(value)}</p>'
            f'<p class="foot">{_esc(foot)}</p></div>'
        )
    return '<div class="grid-kpi">' + "".join(cells) + "</div>"


# ---------------------------------------------------------------------------
# Funnel chart (horizontal ordinal bars)
# ---------------------------------------------------------------------------
def _svg_funnel(m: FunnelMetrics) -> str:
    stages = list(STAGE_LABELS.keys())
    counts = [m.stage_counts[s] for s in stages]
    top = max(counts) if counts else 1
    top = top or 1

    row_h = 34
    gap = 10
    left = 140          # label gutter
    right = 56          # value gutter
    width = 720
    plot_w = width - left - right
    height = len(stages) * (row_h + gap) + gap

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Outreach funnel by stage" font-family="system-ui, sans-serif">'
    ]
    for i, stage in enumerate(stages):
        y = gap + i * (row_h + gap)
        count = counts[i]
        bar_w = (count / top) * plot_w if top else 0
        # keep a visible sliver even for zero so the row reads as present
        draw_w = max(bar_w, 2)
        color = f"var(--funnel-{i + 1})"
        label = STAGE_LABELS[stage]
        pct = (count / top * 100) if top else 0
        parts.append(
            f'<text x="{left - 10}" y="{y + row_h / 2}" text-anchor="end" '
            f'dominant-baseline="central" font-size="13" fill="var(--text-secondary)">'
            f'{_esc(label)}</text>'
        )
        parts.append(
            f'<rect x="{left}" y="{y}" width="{draw_w:.1f}" height="{row_h}" rx="4" '
            f'fill="{color}"><title>{_esc(label)}: {count} contacts '
            f'({pct:.0f}% of top of funnel)</title></rect>'
        )
        parts.append(
            f'<text x="{left + draw_w + 8:.1f}" y="{y + row_h / 2}" '
            f'dominant-baseline="central" font-size="13" font-weight="600" '
            f'fill="var(--text-primary)">{count}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Weekly trend (two-series line chart, single axis)
# ---------------------------------------------------------------------------
def _svg_weekly(m: FunnelMetrics) -> str:
    weeks = m.weekly
    if not weeks:
        return '<p class="desc">No dated activity to chart yet.</p>'

    width = 720
    height = 300
    left = 40
    right = 60
    top = 16
    bottom = 46
    plot_w = width - left - right
    plot_h = height - top - bottom

    ft_vals = [w.first_touches for w in weeks]
    mb_vals = [w.meetings_booked for w in weeks]
    y_max = _nice_ceil(max(ft_vals + mb_vals + [1]))

    n = len(weeks)
    def x_at(i: int) -> float:
        if n == 1:
            return left + plot_w / 2
        return left + (i / (n - 1)) * plot_w
    def y_at(v: int) -> float:
        return top + plot_h - (v / y_max) * plot_h

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Weekly first-touches and meetings booked" '
        f'font-family="system-ui, sans-serif">'
    ]

    # gridlines + y ticks
    ticks = 4
    for t in range(ticks + 1):
        val = y_max * t / ticks
        yy = y_at(val)
        parts.append(
            f'<line x1="{left}" y1="{yy:.1f}" x2="{left + plot_w}" y2="{yy:.1f}" '
            f'stroke="var(--grid)" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 8}" y="{yy:.1f}" text-anchor="end" '
            f'dominant-baseline="central" font-size="11" fill="var(--muted)" '
            f'font-variant-numeric="tabular-nums">{val:.0f}</text>'
        )

    # x labels (ISO week short)
    for i, w in enumerate(weeks):
        xx = x_at(i)
        wk = w.iso_week.split("-")[-1]  # e.g. W32
        parts.append(
            f'<text x="{xx:.1f}" y="{top + plot_h + 18}" text-anchor="middle" '
            f'font-size="11" fill="var(--muted)">{_esc(wk)}</text>'
        )

    def polyline(vals: list[int], color: str, name: str) -> str:
        pts = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in enumerate(vals))
        seg = [f'<polyline points="{pts}" fill="none" stroke="{color}" '
               f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>']
        for i, v in enumerate(vals):
            seg.append(
                f'<circle cx="{x_at(i):.1f}" cy="{y_at(v):.1f}" r="4" fill="{color}" '
                f'stroke="var(--surface-1)" stroke-width="2">'
                f'<title>{_esc(weeks[i].iso_week)}, {name}: {v}</title></circle>'
            )
        # end label
        seg.append(
            f'<text x="{x_at(len(vals) - 1) + 8:.1f}" y="{y_at(vals[-1]):.1f}" '
            f'dominant-baseline="central" font-size="12" font-weight="600" '
            f'fill="var(--text-primary)">{vals[-1]}</text>'
        )
        return "".join(seg)

    parts.append(polyline(ft_vals, "var(--series-1)", "First-touches"))
    parts.append(polyline(mb_vals, "var(--series-2)", "Meetings booked"))
    parts.append("</svg>")

    legend = (
        '<div class="legend">'
        '<span class="item"><span class="swatch" style="background:var(--series-1)"></span>First-touches sent</span>'
        '<span class="item"><span class="swatch" style="background:var(--series-2)"></span>Meetings booked</span>'
        "</div>"
    )
    return legend + "".join(parts)


# ---------------------------------------------------------------------------
# By-segment breakdown (categorical horizontal bars + detail table)
# ---------------------------------------------------------------------------
def _svg_segments(m: FunnelMetrics) -> str:
    segs = m.by_segment
    if not segs:
        return '<p class="desc">No segment data.</p>'

    top = max((s.contacts for s in segs), default=1) or 1
    row_h = 30
    gap = 12
    left = 170
    right = 50
    width = 720
    plot_w = width - left - right
    height = len(segs) * (row_h + gap) + gap

    slot = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"]
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Contacts by segment" font-family="system-ui, sans-serif">'
    ]
    for i, s in enumerate(segs):
        y = gap + i * (row_h + gap)
        color = slot[i % len(slot)]
        bar_w = max((s.contacts / top) * plot_w, 2)
        parts.append(
            f'<text x="{left - 10}" y="{y + row_h / 2}" text-anchor="end" '
            f'dominant-baseline="central" font-size="12" fill="var(--text-secondary)">'
            f'{_esc(s.segment)}</text>'
        )
        parts.append(
            f'<rect x="{left}" y="{y}" width="{bar_w:.1f}" height="{row_h}" rx="4" '
            f'fill="{color}"><title>{_esc(s.segment)}: {s.contacts} contacts, '
            f'{s.first_touches} first-touches, {s.meetings_booked} meetings</title></rect>'
        )
        parts.append(
            f'<text x="{left + bar_w + 8:.1f}" y="{y + row_h / 2}" '
            f'dominant-baseline="central" font-size="12" font-weight="600" '
            f'fill="var(--text-primary)">{s.contacts}</text>'
        )
    parts.append("</svg>")

    # detail table
    rows = []
    for s in segs:
        rows.append(
            f"<tr><td>{_esc(s.segment)}</td>"
            f'<td class="num">{s.contacts}</td>'
            f'<td class="num">{s.first_touches}</td>'
            f'<td class="num">{s.replies}</td>'
            f'<td class="num">{_fmt_pct(s.reply_rate)}</td>'
            f'<td class="num">{s.meetings_booked}</td></tr>'
        )
    table = (
        '<table><thead><tr><th>Segment</th>'
        '<th class="num">Contacts</th><th class="num">First-touches</th>'
        '<th class="num">Replies</th><th class="num">Reply rate</th>'
        '<th class="num">Meetings</th></tr></thead><tbody>'
        + "".join(rows) + "</tbody></table>"
    )
    return "".join(parts) + '<div style="margin-top:14px">' + table + "</div>"


# ---------------------------------------------------------------------------
# Next actions table
# ---------------------------------------------------------------------------
def _next_actions_table(m: FunnelMetrics, limit: int = 15) -> str:
    actions = m.next_actions[:limit]
    if not actions:
        return '<p class="desc">No open follow-ups. Everything is either pre-outreach or already held.</p>'
    rows = []
    for a in actions:
        ref = a.reference_date.isoformat() if a.reference_date else ""
        rows.append(
            f"<tr><td>{_esc(a.company)}</td>"
            f"<td>{_esc(a.contact_name)}</td>"
            f"<td>{_esc(a.segment)}</td>"
            f'<td><span class="pill">{_esc(STAGE_LABELS.get(a.stage, a.stage))}</span></td>'
            f"<td>{_esc(a.action)}</td>"
            f'<td class="num">{_esc(ref)}</td></tr>'
        )
    more = ""
    if len(m.next_actions) > limit:
        more = f'<p class="desc" style="margin-top:10px">Showing {limit} of {len(m.next_actions)} open actions.</p>'
    return (
        '<table><thead><tr><th>Company</th><th>Contact</th><th>Segment</th>'
        '<th>Stage</th><th>Next action</th><th class="num">As of</th></tr></thead>'
        "<tbody>" + "".join(rows) + "</tbody></table>" + more
    )


# ---------------------------------------------------------------------------
# Full page
# ---------------------------------------------------------------------------
def render_dashboard(
    metrics: FunnelMetrics,
    *,
    generated_at: Optional[datetime] = None,
    source_label: str = "data/sample_outreach.csv",
    sample: bool = True,
) -> str:
    """Return the complete HTML document string for the dashboard."""
    generated_at = generated_at or datetime.now()
    ts = generated_at.strftime("%Y-%m-%d %H:%M %Z").strip()

    banner = ""
    if sample:
        banner = (
            '<div class="banner" role="alert">'
            "<strong>SAMPLE DATA - NOT LIVE OUTREACH.</strong> "
            "Every number on this page is generated from illustrative sample rows "
            f"(<code>{_esc(source_label)}</code>) to demonstrate the dashboard. "
            "These are not real prospects, real sends, or real meetings. Do not "
            "read them as Greenbay performance. Live figures appear only once real "
            "Clay / Gmail / Calendar data is wired in (see docs/INTEGRATIONS.md)."
            "</div>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Greenbay BDR reach-out dashboard</title>
<style>{_CSS}</style>
</head>
<body>
<div class="viz-root">
  <div class="wrap">
    <header class="top">
      <div>
        <h1>Greenbay BDR reach-out dashboard</h1>
        <p class="sub">Generated {_esc(ts)} &middot; source: {_esc(source_label)}</p>
      </div>
      <button id="theme-toggle" class="toggle" type="button">Toggle light / dark</button>
    </header>

    {banner}

    {_kpi_tiles(metrics)}

    <section class="card">
      <h2>Outreach funnel</h2>
      <p class="desc">Contacts that reached each stage or beyond. Opens are intentionally
      excluded: email opens are not reliably trackable, so no open rate is shown.</p>
      {_svg_funnel(metrics)}
    </section>

    <section class="card">
      <h2>Weekly trend</h2>
      <p class="desc">First-touches sent and meetings booked per ISO week.</p>
      {_svg_weekly(metrics)}
    </section>

    <section class="card">
      <h2>By segment</h2>
      <p class="desc">Contacts per segment, with the funnel detail beneath.</p>
      {_svg_segments(metrics)}
    </section>

    <section class="card">
      <h2>Open follow-ups and next actions</h2>
      <p class="desc">What needs a human next. Oren is only pulled in when an intro
      meeting lands on his calendar (see docs/ARCHITECTURE.md).</p>
      {_next_actions_table(metrics)}
    </section>

    <footer class="foot">
      Greenbay is fleet orchestration: allocating future work, resolving real-time
      operational failures, and retrospecting repeating issues. Electric is part of
      that, not a charging product. This dashboard is scaffolding rendered from sample
      data; it is not yet connected to live Clay, Gmail, or Google Calendar.
    </footer>
  </div>
</div>
<script>{_TOGGLE_JS}</script>
</body>
</html>
"""


def write_dashboard(
    metrics: FunnelMetrics,
    out_path: PathLike,
    *,
    generated_at: Optional[datetime] = None,
    source_label: str = "data/sample_outreach.csv",
    sample: bool = True,
) -> Path:
    """Render and write the dashboard HTML to ``out_path``. Returns the path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html_doc = render_dashboard(
        metrics,
        generated_at=generated_at,
        source_label=source_label,
        sample=sample,
    )
    out_path.write_text(html_doc, encoding="utf-8")
    return out_path
