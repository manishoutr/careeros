# Job sources: what we fetch, on what terms

CareerOS syncs real listings only from sources whose own published terms
permit it. This file records the first-party evidence and how the code
complies. Sources are re-checked when terms change materially.

## Remotive

- Terms source: the API's own legal notice, returned in every response
  from https://remotive.com/api/remote-jobs (field `0-legal-notice`).
- What it says (verbatim key points): "API documentation and access is
  granted so that developers can share our jobs further. Please do not
  submit Remotive jobs to third Party websites, including but not limited
  to: Jooble, Neuvoo, Google Jobs, LinkedIn Jobs. Please link back to the
  URL found" [notice truncated in the API response].
- How CareerOS complies: listings keep the original Remotive job URL and
  the UI links out to it ("apply ↗"); we display, we never re-submit
  listings to any third-party job board; the source is shown on the card.
- Rate behaviour: its legal notice advises at most 4 requests a day, so the
  automatic refresh never runs more often than every 6 hours (enforced
  server-side, floor 6h). Remotive also delays jobs 24h.

## Arbeitnow

- Terms source: https://www.arbeitnow.com/job-board-api (public API
  documentation; free job-board API, no key required).
- How CareerOS complies: original application URL preserved and linked;
  source shown on the card; one request per manual sync.

## Greenhouse company boards

- Terms source: https://developers.greenhouse.io/job-board.html
  (Greenhouse Job Board API documentation). These endpoints serve the
  JSON behind each company's own public careers board.
- Boards used by default (verified live 2026-11-22): airbnb, cloudflare,
  figma, stripe, databricks, gitlab, coinbase, razorpay, groww, druva, mongodb,
  twilio, okta, zscaler, datadog, elastic (all returned HTTP 200 on 2026-11-22). Override with CAREEROS_GREENHOUSE_BOARDS.
- How CareerOS complies: each listing links to the company's own
  `absolute_url` on boards.greenhouse.io; company name shown; at most 100
  most-recent listings per board per sync; one request per board per
  sync; 60 listings per board, entry-level/India/remote roles first.

## What we deliberately do not do

- No scraping of LinkedIn, Naukri, Indeed or any site whose terms
  restrict automated access.
- No faster polling than every 6 hours, however a sync is triggered. All
  triggers (background thread, search-time staleness check, scheduled GitHub
  Action calling POST /api/jobs/sync) share one cooldown and one-at-a-time lock.
- No fictional listings: demo seeds are disabled by default and purged at startup.
- No re-publishing of listings to other job platforms.
- Expired or removed listings are flagged (`is_expired`) and hidden from
  search within one sync, so we never present a dead listing as open.
