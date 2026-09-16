# Integrations: go-live checklist

Exactly what credentials and decisions are needed to move from the sample
dashboard to live outreach tracking and automation. Grounded in the integration
research; plan-gating is stated honestly. Nothing here is wired yet.

## Quick status

| Capability | Status | Blocker to go live |
|---|---|---|
| Render dashboard from a CSV | Working now | none (uses sample data) |
| Slack daily summary | Scaffolded | needs `SLACK_WEBHOOK_URL` |
| Clay read via CSV export | Working now | manual export step |
| Clay read via Public API | Stub (UNCERTAIN) | verify endpoint + API key |
| Clay write via inbound webhook | Scaffolded (CONFIRMED path) | webhook URL + plan |
| Gmail send / draft / reply detect | Not built | OAuth or SA + DWD, scopes |
| Calendar intro-meeting detection | Not built | SA + DWD + admin authz |
| Calendly booking webhook | Not built | Calendly paid tier + subscription |

## 1. Clay

- **Decide the plan.** Free ($0), Launch ($185/mo), Growth ($495/mo), Enterprise
  (custom). The gotcha: the **Public API is on all plans**, but the **in-table
  HTTP API column** used to *push enriched rows out* to our store is gated to
  **Growth ($495/mo)+**. Advanced reads (joins/ranges/pagination past ~100 rows),
  the People/Company Lookup API, data-warehouse sync, and auto-delete/passthrough
  webhooks are **Enterprise-only**. The MCP server needs Launch minimum.
- **Get the workspace API key.** Single static workspace key (no OAuth, no
  rotation), from Settings > Account or `clay api-keys create` (shown once).
  Store as the `CLAY_API_KEY` secret.
- **Pick the table and get its id.** Store as `CLAY_TABLE_ID`.
- **Create the inbound webhook** on the reach-out table (its URL is the write
  path and is itself a secret). Store as `CLAY_WEBHOOK_URL`. Note the
  **50,000-submission lifetime cap** per non-Enterprise webhook (persists after
  row deletion; create a new webhook once hit, or use Enterprise
  passthrough/auto-delete tables). Writes are **async** — a 200 means "accepted",
  not "enriched".
- **UNCERTAIN:** the Public API's exact read endpoint and whether it fits our
  needs; programmatic row **update**; scheduled bulk export. Verify against
  current Clay docs before depending on any of these. Until then, CSV export
  (manual) and inbound webhook (write) are the reliable paths.

## 2. Gmail (send, drafts, reply detection)

- **Auth model — pick one on `greenbay.solutions`:**
  - **Service account + domain-wide delegation (recommended for unattended
    org-wide automation).** A Workspace admin authorizes the service account's
    client id + scopes in the Admin console; the service account can then act on
    behalf of the sending user without per-user consent.
  - **Per-user OAuth 2.0.** Simpler, no admin needed, but each user authorizes
    and tokens must be refreshed.
- **Least-privilege scopes:** `gmail.send` (send), `gmail.compose` (drafts +
  send), `gmail.readonly` (reply detection), `gmail.labels` (pipeline-state
  labels).
- **Reply push:** Gmail uses `users.watch` -> **Google Cloud Pub/Sub** (not a
  direct HTTPS webhook). Stand up a Google Cloud project with a Pub/Sub topic and
  subscription for the push channel; renew the watch before it expires.
- **Positive-reply** is our own classifier on the reply body; Gmail returns the
  reply, not the sentiment.
- **Opens are not trackable** — do not add open tracking; no open rate is shown.

## 3. Google Calendar (intro-meeting detection)

- **Service account + domain-wide delegation**, authorized by a Workspace admin,
  is the clean backbone for org-controlled, unattended monitoring of Oren's
  calendar (per-user OAuth is the fallback).
- Use `events.watch` (HTTPS webhook channel) -> on notify, call
  `events.list(syncToken)` for the incremental change, then classify the event as
  an intro meeting in our own code. Channels expire and must be renewed. A
  polling fallback (`events.list` with `syncToken`/`updatedMin`) works without
  webhooks at higher latency. Do **not** use `freebusy` for this — it only
  returns busy/free blocks.

## 4. Booking tool — decide which

- **Calendly (preferred if used):** create a webhook subscription on
  `invitee.created` (and `invitee.canceled`) pointing at our endpoint — a clean,
  real-time "meeting booked" trigger. **Calendly webhook subscriptions are a
  paid-plan feature; confirm the current tier.**
- **Google Appointment Schedules:** **no native webhook.** Booked appointments
  land on Google Calendar as events, so fall back to the Calendar `events.watch`
  detection above.

## 5. Slack (`#reach-out`)

- Create an **incoming webhook** for the `#reach-out` channel. Store as
  `SLACK_WEBHOOK_URL`. `src/greenbay_bdr/notify.py` posts the daily summary; with
  the secret unset it is a safe no-op.

## Secrets the GitHub Action expects

Set these as repository secrets (Settings > Secrets and variables > Actions).
All are optional for the sample dashboard build; each unlocks a capability.

| Secret | Used by | Purpose |
|---|---|---|
| `SLACK_WEBHOOK_URL` | `notify.py`, daily workflow | post the daily reach-out summary to `#reach-out` |
| `CLAY_API_KEY` | `clay_adapter.read_table_via_public_api` | Clay Public API auth (static workspace key) |
| `CLAY_TABLE_ID` | `clay_adapter.read_table_via_public_api` | which Clay table to read |
| `CLAY_WEBHOOK_URL` | `clay_adapter.write_rows_via_inbound_webhook` | Clay inbound-webhook write target (the URL is the secret) |

Gmail and Calendar credentials (service-account JSON or OAuth client + tokens,
Pub/Sub config) and any Calendly token are **not yet consumed by code** in this
repo; add them when those integrations are built.

## Plan-gating and hard limits, honestly

- Clay outbound HTTP push column: **Growth ~$495/mo**.
- Clay advanced reads / lookup API / passthrough webhooks: **Enterprise**.
- Clay inbound webhook: **50,000-submission lifetime cap** (non-Enterprise).
- Calendly webhooks: **paid tier**.
- Email **opens**: **not trackable** — excluded by design.
- Google Appointment Schedules: **no native webhook** — use Calendar watch.
