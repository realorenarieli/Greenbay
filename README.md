# Greenbay BDR outreach tracking + dashboard + automation

Foundation for Greenbay's automated BDR: track outreach in a Clay-style
"reach-out" table, render a **daily reach-out dashboard**, and scaffold the
automation where founder Oren is pulled in at exactly one point — when an intro
meeting lands on his calendar.

Greenbay is fleet orchestration: allocating future work, resolving real-time
operational failures with solutions, and retrospecting repeating issues. Electric
is part of that, not a charging product.

## Honest current state

- **Runnable now:** a polished light/dark HTML dashboard generated from **sample
  data**, plus integration scaffolding (Clay adapter, Slack notifier) and the
  metrics/loaders/schema behind it. Standard-library Python only — no pip
  installs, no pandas; charts are inline SVG generated in Python.
- **Not yet live:** it is **not** connected to live Clay, Gmail, or Google
  Calendar. Every number in the committed dashboard is illustrative sample data,
  clearly banner-labeled as such. Going live needs credentials and a few
  decisions — see [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md).
- **Deliberately excluded:** email **open rate**. Opens are not reliably
  trackable (Gmail exposes no open event; pixel tracking is unreliable), so we do
  not compute or display one.

## Quickstart

Requires Python 3.9+ (standard library only).

```bash
python scripts/build_dashboard.py
# -> writes docs/dashboard.html from data/sample_outreach.csv
```

Open `docs/dashboard.html` in any browser (works offline, light and dark).

Options:

```bash
python scripts/build_dashboard.py path/to/your.csv      # use other data (CSV or JSON)
python scripts/build_dashboard.py --out /tmp/dash.html  # custom output path
python scripts/build_dashboard.py --slack               # also post daily summary (needs SLACK_WEBHOOK_URL)
python scripts/build_dashboard.py --no-sample           # drop the SAMPLE banner (only when wired to real data)
```

## Layout

```
src/greenbay_bdr/
  schema.py         reach-out record + funnel stages + segments
  loaders.py        load records from CSV / JSON
  metrics.py        honest BDR funnel metrics (no open rate, by design)
  dashboard.py      light/dark HTML dashboard, inline-SVG charts
  clay_adapter.py   Clay CSV read + Public API stub + inbound-webhook write
  notify.py         daily Slack summary (guarded by SLACK_WEBHOOK_URL)
scripts/build_dashboard.py   load -> metrics -> docs/dashboard.html
data/sample_outreach.csv     SAMPLE data (~50 rows)
docs/dashboard.html          committed sample render (viewable)
.github/workflows/daily-dashboard.yml   daily + manual rebuild
```

## Where to look next

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the end-to-end design: the
  brain/hands operating split, standing outreach rules, why our own store is
  canonical and Clay is the enrichment edge, the full automation pipeline, and
  the single "Oren only at the intro meeting" boundary.
- [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md) — the go-live checklist: exact
  credentials, decisions, plan-gating, and the secrets the GitHub Action expects.
