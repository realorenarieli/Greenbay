# Architecture

Greenbay's automated BDR: how outreach gets tracked, dashboarded, and automated,
and the single point where founder Oren gets pulled in. This document is the
design in plain language. It is grounded in the integration research; where a
capability is not certain, it says so. Nothing here hardcodes a secret.

## Operating model: brain / hands

- **Brain (Claude).** Decides who to reach out to, drafts copy, classifies
  replies, and decides when a human is needed. Reasoning and judgement live here.
- **Hands (Chief of Staff, via connectors).** Executes: sends Gmail, reads
  threads, watches the calendar, posts to Slack, pushes/pulls Clay rows. The
  hands do only what the brain instructs, through the integrations in
  `docs/INTEGRATIONS.md`.

The split matters for safety: the brain never holds long-lived credentials, and
the hands never decide tone or targeting on their own.

## Standing outreach rules (operating rules, not code constants)

These are business rules the automation must honor. They are written here rather
than hardcoded so they can be reviewed and changed without a code deploy.

1. **Greenbay is fleet orchestration.** Three jobs: allocate future work,
   resolve real-time operational failures with solutions, and retrospect
   repeating issues. Electric is part of the picture, not a charging product.
   Outreach copy must reflect this, never positioning Greenbay as an EV-charging
   tool.
2. **Every prospect outbound BCCs** `shira.golan@greenbay.solutions` and
   `george.belias@greenbay.solutions`. No exceptions on cold prospect sends.
3. **Oren's Gmail signature and logo** are used on outbound from his address.
4. **No em dashes** in outbound copy.
5. **Draft for approval when tone is sensitive.** Use Gmail drafts
   (`drafts.create`) and hold for a human when the message is delicate; send
   directly only for routine, low-risk touches.
6. **Prioritize closeable 2026 revenue over cold volume.** Favor warm,
   in-ICP, near-term-closeable prospects over raw send count.

## Data-source strategy: our store is canonical, Clay is the edge

**Our own tracking store is the system of record. Clay is the list / enrichment
edge and the human-facing "reach-out table" — it is not the real-time database.**

Why, honestly (from the research):

- Clay is a **table + async-enrichment engine**, not a low-latency
  request/response API. A write (inbound webhook) triggers enrichment that
  completes over **minutes**, and the enriched result is not returned in the POST
  response.
- Clay reads are limited. A young Public API can read rows, but advanced querying
  (joins, ranges, pagination past ~100 rows) is Enterprise-gated, and the
  maturity of that API is genuinely uncertain across sources.
- Programmatic **update** of a specific existing row is not clearly documented.
- Scheduled bulk CSV export is not a first-class feature (treat CSV export as
  manual).

So we treat Clay as eventually-consistent enrichment at the edges: push contacts
in for enrichment, pull enriched rows back out, but keep our own datastore as the
canonical source the dashboard reads from. This isolates the dashboard from
Clay's latency and read limits, and from Gmail/Calendar quota. Oren can still
think of the Clay reach-out table as "the list"; under the hood our store is
authoritative.

> Current repo state: there is no live datastore yet. The dashboard reads a
> SAMPLE CSV (`data/sample_outreach.csv`). The store is the intended canonical
> layer once integrations are wired.

## The automation pipeline (end to end)

```
  [1] SOURCE + ENRICH            [2] OUTREACH               [3] REPLY DETECTION
  Clay table (inbound webhook)   Gmail messages.send        Gmail threads +
  push contacts in, enrich  ->   (BCC shira + george),  ->  history.list, pushed
  pull enriched rows back        drafts for sensitive       by users.watch -> Pub/Sub;
  out to our store               tone                       classify sentiment
        |                              |                            |
        v                              v                            v
  [4] FOLLOW-UP CLOCKS          [5] MEETING BOOKED          [6] OREN INVOLVED
  our store tracks last_touch;  Calendly invitee.created    an INTRO MEETING lands
  schedule follow-ups until     webhook (preferred), or     on Oren's calendar ->
  reply or cadence ends         Calendar events.watch       notify Oren (Slack /
                                fallback                     email). ONLY here.
```

1. **Source + enrich (Clay).** New contacts are POSTed to a Clay table's inbound
   webhook (CONFIRMED write path). Clay enriches asynchronously. Enriched rows
   are pulled back out via a condition-gated HTTP API column (CONFIRMED push
   mechanism, but Growth-plan-gated at ~$495/mo) or basic Public API reads, and
   land in our store. `src/greenbay_bdr/clay_adapter.py` implements the CSV read,
   a clearly-marked Public API stub, and the inbound-webhook write.
2. **Outreach (Gmail).** `messages.send` for routine touches; `drafts.create`
   when tone is sensitive (rule 5). Every prospect send BCCs Shira and George
   (rule 2). We store the `threadId` of each send for reply detection. Labels
   (e.g. `Outreach-Sent`, `Replied`) act as lightweight pipeline state.
3. **Reply detection (Gmail).** Replies share the send's thread. We notice them
   incrementally via `history.list` (with a stored `historyId`), pushed by
   `users.watch` to Google Cloud Pub/Sub. Positive-vs-neutral-vs-negative is a
   **content-classification step we build** on top of the detected reply; Gmail
   gives us the reply, not the sentiment.
   - **Opens are deliberately not tracked.** The Gmail API exposes no open event,
     and pixel tracking is unreliable (Gmail proxies/prefetches images, and
     image-blockers never load the pixel). No open rate is computed or shown.
4. **Follow-up clocks.** Our store holds `last_touch_date` and cadence; the
   automation schedules the next follow-up until a reply arrives or the cadence
   ends. The dashboard's "open follow-ups / next actions" surfaces what is due.
5. **Meeting booked.** The cleanest trigger is Calendly's `invitee.created`
   webhook (CONFIRMED, real time; note it is a paid-plan feature). If the team
   uses Google Appointment Schedules instead, there is **no native webhook** —
   fall back to Google Calendar `events.watch` -> `events.list(syncToken)` and
   classify the new event as an intro meeting by our own rules.
6. **The single Oren trigger.** **Oren is pulled in at exactly one point: when an
   intro meeting lands on his calendar.** Everything upstream — sourcing,
   enrichment, sending, follow-ups, reply handling, booking — runs without Oren.
   When an intro meeting is detected on his calendar, the automation notifies him
   (Slack `#reach-out` and/or email) with the context he needs to show up. He is
   not asked to approve sends, triage replies, or manage the funnel. This
   boundary is deliberate and should stay explicit in any future change.

## What is CONFIRMED-possible vs needs Oren's confirmation/credentials

**CONFIRMED-possible (well-documented, buildable today):**

- Gmail send/draft, reply detection via threads + `history.list` + `users.watch`
  (Pub/Sub), label-based pipeline state.
- Google Calendar `events.watch` -> `events.list(syncToken)` for intro-meeting
  detection; service account + domain-wide delegation for org-controlled,
  unattended monitoring of Oren's calendar.
- Calendly `invitee.created` webhook as the booking trigger (if Calendly is used;
  paid tier).
- Clay inbound-webhook writes; basic Public API reads; manual CSV export.
- This dashboard and Slack daily summary from our own store.

**Needs Oren's confirmation / credentials (see `docs/INTEGRATIONS.md`):**

- Which Clay plan the workspace is on (outbound HTTP push needs Growth ~$495/mo;
  advanced reads / lookup / passthrough need Enterprise) and the workspace API
  key + table id.
- A Workspace admin authorizing a **service account with domain-wide delegation**
  on `greenbay.solutions` for Gmail + Calendar scopes (otherwise per-user OAuth).
- Which booking tool is in use: Calendly (webhook, confirm paid tier) vs Google
  Appointment Schedules (no webhook -> Calendar watch).
- OAuth scope approval and a Google Cloud project with Pub/Sub for Gmail push.
- A Slack incoming webhook for `#reach-out`.

**Explicitly do NOT rely on:** email open tracking; Clay as a low-latency
queryable API or for programmatic row updates; a generic Clay "row-changed" event
stream (use a condition-gated HTTP column); Calendar `freebusy` for detecting a
specific new meeting.
