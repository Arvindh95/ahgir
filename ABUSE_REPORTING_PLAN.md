# PicUr — Abuse Reporting & Operator Review

Status: implemented on branch `feat/abuse-reporting` (Phase 1 + Phase 2
+ defence layer). Three items intentionally skipped — see inline notes.
Owner: arvindhsekharan@gmail.com
Last updated: 2026-05-15

## Why this exists

The public security copy currently promises:

> "The in-app admin console exposes only event metadata to authorised
> superadmins. There is no photo viewer for staff anywhere in the app."

That absolute promise is in conflict with the reality of running an
event-photo platform: someone will eventually upload illegal content
(CSAM, harassment material, copyright violation, intimate imagery
without consent). When that happens, an operator MUST be able to
verify the report and take the photo down. Pure "operators never look
at photos" is unsustainable.

This document is the design for an **incident-driven** carve-out:
operators view photo bytes ONLY when a guest has filed a specific
abuse report against that specific photo. The carve-out is recorded in
the event's audit log so the organizer can verify every operator
access after the fact. There is no operator-side photo browsing.

## Public copy update — must ship BEFORE any code that breaks the
## absolute claim

### `frontend/pages/security.tsx` Operator Access section

Current paragraph (paraphrased): operator team has server-level
access used only for support, abuse investigation, valid legal
process, or maintenance, and that access is recorded in an audit log.

Append:

> "Operators do not browse event photos. When a guest files a written
> abuse report against a specific photo, an operator may view that
> specific photo to verify the report and decide whether to leave it,
> quarantine it, or remove it. Every such view is recorded in the
> event's audit log under your own admin console — the audit row
> names the operator, the photo, the report category, and the
> reporter context."

### `frontend/pages/privacy.tsx` §9 Operator Access

Same change, slightly more formal language. The §9 section already
discloses operator server-level access; add the photo-review carve-out
explicitly.

### Reddit + marketing material

If we mention "no photo viewer" in any future outbound copy, append
"except when an abuse report is filed against a specific photo, and
the access is auditable."

## Data model

### New table: `abuse_reports`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `image_id` | UUID FK images(id) ON DELETE CASCADE | Required — reports are per-image |
| `event_id` | UUID FK events(id) ON DELETE CASCADE | Denormalized for fast event-scoped queries |
| `category` | String(32) CHECK (csam, nudity, harassment, copyright, violence, other) | Reporter picks |
| `description` | Text nullable, max 2000 chars | Free text from reporter |
| `reporter_email` | String(255) nullable | Optional |
| `reporter_ip` | String(45) | IPv4 or IPv6 string for rate-limit forensics |
| `status` | String(32) CHECK (pending, reviewing, dismissed, quarantined, removed) DEFAULT 'pending' | |
| `created_at` | TIMESTAMP server_default now | |
| `reviewed_at` | TIMESTAMP nullable | Set when first reviewed |
| `reviewed_by` | UUID FK users(id) ON DELETE SET NULL nullable | Operator who acted |
| `action_taken` | String(32) nullable | dismiss, quarantine, remove |
| `notes` | Text nullable | Operator-only note |

Indexes:
- `(status, created_at desc)` — admin queue listing
- `(event_id)` — for per-event audit join

### `Image.status` adds `quarantined`

New value alongside `pending / indexed / no_faces / failed`. Migration
updates the CHECK constraint. Guest-facing endpoints already filter
`status IN (indexed, no_faces)`, so adding `quarantined` to the enum
without including it in the visible set is exactly the desired effect:
photo bytes remain in MinIO, the DB row remains, but no guest endpoint
will serve it.

## Migrations

Three new migrations, in order:

1. `f9i2j3k4l5_add_image_status_quarantined.py`
   - DROP + recreate `valid_status` CHECK on `images` with the new
     value list.
2. `g0j3k4l5m6_add_abuse_reports.py`
   - CREATE TABLE abuse_reports with FK + indexes + CHECK constraints
     above.
3. (No third migration unless we add denormalized columns later.)

## Backend endpoints

### Public reporting

**`POST /report`** — anonymous, rate-limited per IP.

Request body (JSON):
```json
{
  "image_id": "uuid",
  "category": "csam|nudity|harassment|copyright|violence|other",
  "description": "optional text up to 2000 chars",
  "reporter_email": "optional email"
}
```

Behaviour:
- Pydantic enforces category enum + length caps + email format.
- Per-IP rate limit (new `abuse_report_rate_limiter`, default 5/hour
  per IP) so the queue can't be DoS'd. Per-email limit too if email
  given.
- Look up the image; reject if not found (404). Do NOT 404
  immediately on a real id — that would leak which UUIDs exist. So:
  on lookup failure return the same generic 200 "thanks" response.
  Real reports against fake UUIDs are harmless; the queue review
  step will dismiss them.

Response (always 200 unless rate limited):
```json
{"message": "Thank you. We will review this report shortly."}
```

No status tracking returned. Reporters who file repeatedly with the
same email could be sent a confirmation email later (out of scope
v1).

### Superadmin review

All routes under `/admin/abuse-reports/*`, require
`get_superadmin_user` dependency.

**`GET /admin/abuse-reports`**
- Query params: `status` (default: pending), `limit`, `offset`,
  `category` filter, `sort=newest|oldest` (default newest).
- Returns abuse reports joined with:
  - Image filename + upload time + uploader (event owner)
  - Event name + slug
  - Reviewed-by (operator email, if any)
- Pagination metadata: `{ items, total, limit, offset }`.
- Photo bytes / URLs NOT returned in this view.

**`GET /admin/abuse-reports/pending-count`**
- Returns `{ "pending": N }`.
- Used by AdminLayout for the nav badge.
- Requires superadmin.

**`POST /admin/abuse-reports/{id}/reveal`**
- Returns a short-lived (5 min) `abuse_review` signed URL for that
  specific image.
- Side effects:
  - Mark report `status='reviewing'`, `reviewed_at=now()`,
    `reviewed_by=current_user.id` if first reveal.
  - Audit log row:
    `action='abuse_review_view'`,
    `actor_type='admin'`,
    `actor_id=operator.id`,
    `event_id=image.event_id`,
    `metadata={report_id, image_id, category, reason}`.
  - The audit row is visible in the event's own audit-log tab; the
    organizer can spot every operator access there.
- The URL points at the existing `/photos/{event}/{image}/abuse_review`
  route (new photo_type — see below).

**`POST /admin/abuse-reports/{id}/quarantine`**
- Marks `Image.status='quarantined'`.
- Marks abuse_report `status='quarantined', action_taken='quarantine'`.
- Cache invalidation:
  `cache_delete_pattern("gallery:{event_id}:*")`,
  `cache_delete_pattern("share:{event_id}:{image_id}")`.
- Audit log `action='abuse_review_quarantine'`.

**`POST /admin/abuse-reports/{id}/delete-photo`**
- Reuses the existing single-photo delete code path (MinIO cleanup,
  CompreFace cleanup, DB delete via cascade-correct ORM).
- Marks abuse_report `status='removed', action_taken='remove'`.
- Audit log `action='abuse_review_delete'` (separate from generic
  `delete` so the audit viewer can distinguish moderator-driven
  removals).

**`POST /admin/abuse-reports/{id}/dismiss`**
- Marks abuse_report `status='dismissed', action_taken='dismiss'`.
- Audit log `action='abuse_review_dismiss'`.

### New photo_type: `abuse_review`

Add `"abuse_review"` to `_VALID_PHOTO_TYPES` in `app/storage.py`. The
signed URL format stays the same `(event_id, image_id, "abuse_review",
expires, sig)`, but:

- `expires_minutes` default lowered to 5 (vs the standard 15).
- The `/photos/{event_id}/{image_id}/{photo_type}` route, when
  `photo_type == "abuse_review"`, BYPASSES the `event.status==active`
  and `image.status IN (indexed, no_faces)` checks (a quarantined
  image MUST be reviewable; a frozen event MUST be reviewable).
- Reading bytes still works on the underlying `original/` MinIO object
  — the abuse_review photo_type is just a different URL signature
  that grants temporary review access. No separate MinIO object is
  written.

### Audit envelope (`audit_logs.actor_type`)

No CHECK constraint change needed — operator reviews are
`actor_type='admin'` with `actor_id=operator.id`. The `action`
strings `abuse_review_view / quarantine / delete / dismiss` are the
distinguishers.

## Frontend changes

### "Report" button placement (shipped)

Two entry points cover every guest-facing photo view:

1. **Lightbox** — `components/PhotoModal.tsx` (used by both
   `pages/e/[slug]/results.tsx` and `pages/e/[slug]/gallery.tsx`) gets
   a flag icon in its action bar alongside Share / Download. User
   clicks a photo → sees the lightbox → can report.
2. **Public share page** — `pages/share/[event_id]/[image_id].tsx`
   shows a "Report this photo" link below the Find Your Photos CTA.

Skipped intentionally: per-card hover-only flag overlays on the
results / gallery grid cards. The lightbox flag is one extra click
but matches the industry-standard report pattern (Reddit, Instagram,
Facebook) and avoids inviting trolling via easy in-grid reporting.

### `components/ReportPhotoModal.tsx`

Fields:
- Category dropdown (CSAM / Nudity without consent / Harassment /
  Copyright / Violence / Other)
- Description textarea (optional, hint "Explain what we should look
  for")
- Email (optional, hint "We won't share this with the event organizer
  — only used if our team needs more info")
- Submit button → `POST /report`
- Generic success state "Thanks. We will review this report shortly."
- No status tracking link.

### Superadmin abuse-review dashboard

Two routes, both superadmin-only:

#### `/admin/abuse-queue` — queue listing

Top-level nav entry inside the AdminLayout superadmin section
(`components/AdminLayout.tsx`, alongside the existing `/admin/superadmin`
link). The nav link shows a small red badge with the pending-report
count, fetched via `GET /admin/abuse-reports/pending-count` on layout
mount and refreshed when the queue page reloads. Zero count = no badge.

Page layout:

- **Header**: title "Abuse Review Queue" + the pending count repeated
  prominently. A `[Refresh]` button next to it.
- **Filter row**: pills for status (default: pending; others: reviewing
  / dismissed / quarantined / removed) and a dropdown for category
  (all / csam / nudity / harassment / copyright / violence / other).
- **Sort**: default = newest first. Toggle to oldest first.
- **Table** of reports (one row per report). Columns:
  - Category (color-coded badge — csam = red, harassment = orange,
    etc.)
  - Event name (text-only here, links live on the review screen).
    Helps the operator triage by event without leaking event navigation
    from the queue.
  - Filename + uploaded-at
  - Reported-at (relative + absolute on hover)
  - Reporter email (or `—` if anonymous)
  - Description (truncated to ~80 chars + ellipsis)
  - Status badge
  - `[Review →]` button on the right
- **Pagination**: 25/page, server-driven via `limit/offset` on the
  list endpoint.
- **Empty state**: when no rows match the filter, render "No reports
  matching these filters." with a link to clear filters.

The queue listing renders ONLY metadata. No thumbnail, no signed URL,
no photo bytes — those require the explicit reveal step on the review
page. This preserves the "no photo viewer for staff" promise except
when a report is explicitly being reviewed.

#### `/admin/abuse-queue/[report_id]` — review screen

Clicking `[Review →]` on any row navigates to a dedicated page (NOT a
modal). Dedicated route reasons:

- Deep-linkable: the on-call rotation can paste a review URL into
  Slack/email without losing the modal state.
- Browser back stack works correctly — operators can navigate between
  queue and review without modal re-renders.
- Mobile-friendly: a full screen handles the photo + actions better
  than a stacked modal.
- The audit row is written when the page loads (single reveal call),
  so refreshing the page is idempotent — `POST /admin/abuse-reports/
  {id}/reveal` only updates `reviewed_at` / `reviewed_by` on the first
  call.

Page layout (two-column on desktop, stacked on mobile):

- **Left / main column** — image viewer:
  - On page mount, call `POST /admin/abuse-reports/{id}/reveal`
    → receive the signed `abuse_review` URL.
  - Until the reveal completes, render a skeleton with a small
    "Loading photo for review…" message. Photo bytes never render
    before the audit row is written.
  - Once URL is in hand, render the photo at `max-height: 80vh`,
    object-contain, dark background.
  - Below the image: filename + dimensions + uploaded-at + uploader
    (event owner email, click-through to `/admin/users` if needed).

- **Right / sidebar column** — report context + actions:
  - Category badge (large)
  - Description (full text, no truncation)
  - Reporter email + reporter IP (operator may need IP for repeat-
    abuse review)
  - Reported-at + reviewed-at + reviewed-by (so two operators looking
    at the same report can see who acted first)
  - Event name → link to `/admin/events/{event_id}` for cross-
    referencing the full event audit log
  - Action buttons, vertically stacked, each with `confirm()` prompt:
    - `[Dismiss]` — neutral grey, "Mark as not abuse"
    - `[Quarantine]` — yellow, "Hide from guests; keep bytes for
      potential law-enforcement request"
    - `[Delete photo]` — red, "Remove permanently. Cannot be undone."
  - After any action: redirect back to the queue with a toast.

- **Top of page**: breadcrumb `← Back to queue` + "Report
  {id-short}".

If the report is already in a terminal status (`dismissed` /
`removed`), the action buttons are disabled and a banner reads "This
report was already actioned by {reviewer} on {date}." The photo can
still be revealed (for record review), but a fresh audit row is
written every time — this is intentional, so re-opening a closed
report is also traceable.

### New endpoint: `GET /admin/abuse-reports/pending-count`

- Returns `{"pending": N}`.
- Used by `AdminLayout` for the nav badge.
- Cached for 30 s on the client (fetched once per layout mount); the
  queue page refresh explicitly busts that cache.
- Requires `get_superadmin_user`.

### Cross-cutting UX details

- The queue + review pages live ONLY behind the superadmin guard
  (`is_superadmin` flag on `User`). A regular admin who somehow lands
  on the URL sees the existing 403 page.
- The Plan & Usage hide pattern (already shipped in `c8fa221`) is the
  reference for nav visibility: queue link only renders when
  `isSuperadmin === true`.
- Pending-count badge color: red dot if N > 0, no dot otherwise. The
  badge does NOT show the actual count above 99 — render "99+" to
  keep the chip narrow.
- All four action endpoints (reveal / quarantine / delete / dismiss)
  share a single audit-row helper so the metadata schema stays
  consistent across actions.

### Public copy updates

Already discussed above. Ship as part of the same PR as the
backend so the policy and the code arrive together.

## Implementation phasing

Two-phase rollout:

**Phase 1 — wiring (no live abuse reports yet)**
- All migrations
- All backend endpoints (including `pending-count`)
- AdminLayout nav badge (will show 0 until reports exist)
- Empty admin queue page + review screen route (renders 404 with no
  data, but reachable)
- Updated privacy + security copy

Deploy Phase 1 and verify with a smoke-test report from a non-prod
account.

**Phase 2 — reporter UI**
- Report button + modal on results / gallery / share pages

Splitting like this prevents the awkward state where the public can
file reports but operators have no way to see them.

## Tests

Test coverage is split across four files so each one stays focused:

```
backend/tests/test_abuse_reporting.py        # core reporting + review flow
backend/tests/test_abuse_review_audit.py     # audit-log content + envelope
backend/tests/test_report_abuse_defence.py   # rate limits + anti-abuse
backend/tests/test_abuse_migrations.py       # schema/CHECK constraints
frontend/__tests__/abuse-*.test.tsx          # UI behaviour
```

Every test below cites which feature it exercises — there should be
no feature in the plan without a corresponding test entry.

### Migrations & schema (`test_abuse_migrations.py`)

1. **`f9i2j3k4l5_add_image_status_quarantined`**
   - Upgrade allows `Image.status = 'quarantined'` via raw SQL.
   - Pre-upgrade rows with old statuses still pass the new CHECK.
   - Downgrade rejects `'quarantined'` and restores the old CHECK.

2. **`g0j3k4l5m6_add_abuse_reports`**
   - Upgrade creates the table with expected columns, FKs, indexes,
     CHECK on `category` and `status`.
   - `image_id` FK has `ON DELETE CASCADE` — deleting the image
     cascades the abuse_report row.
   - `event_id` FK has `ON DELETE CASCADE` — deleting the event
     cascades.
   - `reviewed_by` FK has `ON DELETE SET NULL` — deleting the
     operator user leaves the report intact with `reviewed_by=null`.
   - Index `(status, created_at desc)` exists.
   - Downgrade drops the table cleanly.

### Public POST /report (`test_abuse_reporting.py::TestPublicReport`)

3. **Happy path**
   - Valid payload returns 200 with the fixed thanks message string
     (no echo of inputs).
   - Persists exactly one row with `status='pending'`,
     `reporter_ip` set.
   - `reporter_email` is lowercased when persisted.

4. **Validation**
   - Invalid category → 422.
   - Description > 2000 chars → 422.
   - Invalid email format → 422.
   - Missing `image_id` → 422.

5. **Anti-enumeration**
   - Real image_id and fake UUID both return 200 with identical
     body bytes.
   - Response timing for real vs fake image_id falls within ±20ms
     (constant-time floor applied).

6. **Idempotency / duplicates**
   - Same image_id from different IPs → multiple rows persist.
   - Same image_id from same IP within the per-image window → 200
     but no second row (silent dedupe + duplicate count surfaces in
     admin queue, tested in §10).

7. **Request shape defence**
   - Missing `X-Requested-With: XMLHttpRequest` → 403 (CSRF
     middleware applies to /report).
   - Populated honeypot field (`website`) → 200 with no row
     created.

### Public POST /report — rate limits (`test_report_abuse_defence.py`)

8. **Layered limits**
   - 6th report from same IP within the per-IP window → 429.
   - 16th report from contiguous IPs in the same /24 → 429.
   - 4th report on the same image_id from any source within 24h →
     200 silent-dropped (no row, no 429).
   - 31st report on the same event_id within the hour → 429.
   - 6th report with the same `reporter_email` → 429.
   - Category does NOT change the limit — `csam` and `other` are
     equally rate-limited.

9. **Bot defence**
   - Missing Turnstile token in production env → 403.
   - Invalid Turnstile token (mocked verify endpoint returns
     `success=false`) → 403.
   - Turnstile verify endpoint network failure (mocked) → 200,
     report accepted (fail-open) AND a warning is logged.
   - Honeypot populated → silent 200, no row, no rate-limit
     consumption.

10. **Reporter reputation soft-ban**
    - Seed 5 reports from IP X with 4 already in `dismissed` status.
      6th report from IP X returns 200 BUT creates no row AND
      writes a `soft_ban_drop` audit row.
    - Seed 10 reports from IP X with 9 dismissed → permanent soft
      ban. Operator's `Clear ban` endpoint resets it; next report
      from IP X is accepted again.
    - Soft-ban check uses 30-day rolling window — 31-day-old
      dismissed reports do not count.

11. **Self-report flag**
    - Reporter IP matches the IP of any recent `audit_logs.actor_id
      = event.owner_user_id` action → admin queue response sets
      `is_possible_self_report=true` on that row.
    - Reporter IP differs → flag is false.
    - The 24h window applies — older owner actions don't flag.

### Admin queue listing (`test_abuse_reporting.py::TestAdminQueue`)

12. **Auth**
    - `GET /admin/abuse-reports` — no auth → 401, regular admin →
      403, superadmin → 200.
    - Same matrix for `GET /admin/abuse-reports/pending-count`,
      `POST /admin/abuse-reports/{id}/{action}`.

13. **Filtering & paging**
    - Default returns `pending` rows only.
    - `status` filter accepts every legal value and rejects
      garbage (422).
    - `category` filter narrows results.
    - `sort=newest` returns descending by `created_at`;
      `sort=oldest` ascending.
    - `limit` + `offset` slice correctly; response includes
      `{items, total, limit, offset}`.
    - No photo URL fields appear in any item — assert the response
      schema explicitly.

14. **Pending count**
    - `GET /admin/abuse-reports/pending-count` returns the count of
      `status='pending'` rows.
    - Quarantine / dismiss / delete action decrements the count
      surfaced on the next call (no stale cache from the action
      endpoint).

15. **Duplicate roll-up + reputation sort**
    - When N duplicates exist for the same image_id, the admin
      response shows ONE row with `duplicate_count=N`.
    - With sort `reputation`, rows from low-dismiss-rate IPs sort
      above high-dismiss-rate IPs even within the same created_at
      bucket.

### POST /reveal (`test_abuse_reporting.py::TestReveal`)

16. **State + audit**
    - First reveal sets `status='reviewing'`, `reviewed_at`,
      `reviewed_by`.
    - Subsequent reveals do NOT clobber `reviewed_at` /
      `reviewed_by` (first-reviewer wins).
    - Every reveal call writes a fresh `abuse_review_view` audit
      row — even on a terminal-status report (re-open is also
      traceable).
    - Reveal on a non-existent report → 404.

17. **Signed URL**
    - Returned URL has `photo_type='abuse_review'`, expires in 5
      min (settings-driven).
    - URL signature verifies against the existing signer.
    - Tampered query string → 403 on the underlying photo route.
    - Expired URL → 403.

### POST /quarantine (`test_abuse_reporting.py::TestQuarantine`)

18. **State**
    - Sets `Image.status='quarantined'`,
      `abuse_report.status='quarantined'`,
      `action_taken='quarantine'`.
    - Terminal-status report → 409 with helpful error (doesn't
      double-act).

19. **Cache invalidation**
    - Calls `cache_delete_pattern("gallery:{event_id}:*")` and
      `cache_delete_pattern("share:{event_id}:{image_id}")`
      exactly once (mocked).

20. **Guest invisibility**
    - `GET /e/{slug}/gallery` excludes quarantined images.
    - `GET /scan` excludes quarantined images.
    - `GET /share/{event}/{image}` returns 404 for quarantined.
    - Regular signed `/photos/.../original` URL returns 404 for
      quarantined (cache/public-URL freshness).
    - `/photos/.../abuse_review` signed URL STILL serves the bytes.

21. **Audit row**
    - `action='abuse_review_quarantine'`, `actor_type='admin'`,
      `metadata` includes `{report_id, image_id, category}`.

### POST /delete-photo (`test_abuse_reporting.py::TestDelete`)

22. **State + cleanup**
    - MinIO `original/` + `thumb/` objects removed (mocked storage
      client receives both calls).
    - CompreFace `delete-by-subject` called for each Face row
      (mocked).
    - Face rows + Image row removed.
    - `abuse_report.status='removed'`, `action_taken='remove'`.
    - Terminal-status report → 409.

23. **Cascade**
    - Other abuse_reports against the same image (e.g. duplicates)
      cascade-delete with the image.

24. **Audit row**
    - `action='abuse_review_delete'`, metadata includes
      `{report_id, image_id, original_filename}` for forensics.

### POST /dismiss (`test_abuse_reporting.py::TestDismiss`)

25. **State**
    - Sets `abuse_report.status='dismissed'`,
      `action_taken='dismiss'`.
    - Image status untouched.
    - Terminal-status report → 409.

26. **Audit row**
    - `action='abuse_review_dismiss'`, metadata includes
      `{report_id, image_id, category}`.

### abuse_review photo_type (`test_abuse_reporting.py::TestReviewPhotoType`)

27. **Bypass logic**
    - Signed URL serves bytes when `event.status='frozen'`.
    - Serves bytes when `image.status='quarantined'`.
    - Serves bytes when `image.status='pending'`.

28. **Signature**
    - Expired signature → 403.
    - Tampered sig → 403.
    - Wrong photo_type → 403.

29. **MinIO mapping**
    - Reading `abuse_review` resolves to the same underlying
      `original/` MinIO object — no separate write.

### Audit envelope (`test_abuse_review_audit.py`)

30. **Per-event visibility**
    - Event-owner audit-log endpoint surfaces every
      `abuse_review_*` row for their event.
    - Other admins do NOT see those rows.

31. **Schema**
    - All four `abuse_review_*` actions write rows with
      `actor_type='admin'`, `actor_id=operator.id`,
      `event_id=image.event_id`.
    - `metadata` JSON parses cleanly and contains the keys named
      per action above.

32. **No spillover**
    - Customer-facing event activity feed (the analytics
      `recent_activity` filter shipped in `91c08d0`) excludes
      `abuse_review_*` actions. Operator activity stays in the
      audit log, not the customer feed.

### Frontend tests

#### `frontend/__tests__/abuse-report-modal.test.tsx`

33. **ReportPhotoModal**
    - Category required — submit disabled until selected.
    - Description max-length client-side hint at 2000 chars.
    - Submit calls `/report` with payload including the honeypot
      field set to empty string.
    - On 200 shows the generic success state and no echo of the
      submitted text.
    - On 429 shows a non-leaky "Please try again later" message.

#### `frontend/__tests__/abuse-report-buttons.test.tsx`

34. **Report button placement**
    - Hover-only flag icon appears on each photo card in
      `pages/e/[slug]/results.tsx` and `pages/e/[slug]/gallery.tsx`.
    - "Report this photo" link rendered on `pages/share/[event_id]/
      [image_id].tsx`.

#### `frontend/__tests__/abuse-queue.test.tsx`

35. **AdminLayout nav badge**
    - Renders no badge when `pending=0`.
    - Renders red dot with count when `1 ≤ pending ≤ 99`.
    - Renders `99+` when `pending > 99`.
    - Only renders when `isSuperadmin === true`.

36. **`/admin/abuse-queue` page**
    - Loads reports via `GET /admin/abuse-reports`.
    - Filter pills toggle status; URL query updates so the page is
      shareable / bookmarkable.
    - Category dropdown narrows results.
    - Sort toggle flips newest ↔ oldest.
    - Pagination "next" advances offset without dropping filters.
    - Empty state renders "No reports matching these filters."
    - `[Review →]` navigates to `/admin/abuse-queue/{id}`.

#### `frontend/__tests__/abuse-review-screen.test.tsx`

37. **`/admin/abuse-queue/[report_id]` review screen**
    - On mount, fires `POST /reveal` exactly once.
    - Photo does NOT render until reveal resolves (skeleton shown).
    - Once URL resolves, photo renders with `max-height: 80vh`.
    - Sidebar shows category, description, reporter email/IP,
      reported-at, reviewed-by.
    - Each action button has a `confirm()` prompt and on confirm
      calls the matching endpoint.
    - On success redirects to `/admin/abuse-queue` and shows a
      toast.
    - Terminal-status report → action buttons disabled + "already
      actioned by X on Y" banner shown.
    - Refreshing the page re-fires reveal (idempotent state, new
      audit row each time — expected and verified in §16).

38. **Auth guard**
    - Regular admin loading `/admin/abuse-queue` or `/admin/
      abuse-queue/{id}` sees the 403 page; no API calls fire.

### Privacy attestation (skipped)

39. **`frontend/SECURITY_AUDIT.md`** — operator-facing internal
    attestation doc. Skipped on the abuse-reporting PR: public-facing
    `privacy.tsx` §9 + `security.tsx` Operator Access are already
    updated with the carve-out paragraph and are what guests, lawyers,
    and compliance reviewers actually read. SECURITY_AUDIT.md is an
    internal reference doc and adds no runtime / public-facing signal.
    Revisit only if SECURITY_AUDIT.md becomes a compliance artifact.

### Test execution gate

40. **CI**
    - All four backend test files run in the existing pytest
      non-hypothesis lane (no new markers).
    - Frontend tests run in the existing `frontend/__tests__` lane.
    - Deploy continues to gate on test workflow_run success (no
      change to `.github/workflows/deploy.yml`).

## Preventing abuse OF the reporting system

The reporting mechanism itself is an attack surface. A bad actor can:

- Flood the queue so legitimate reports drown.
- Mass-target a photographer to force review burden and temporary
  quarantine on legitimate photos.
- Cycle IPs / VPNs to evade rate limits.
- Spoof someone else's email as `reporter_email` to associate them with
  reports.
- Mark everything CSAM (most-severe category) to force urgent action.
- Use timing / response variation to enumerate which image_ids exist.
- Automate the form via headless browser / curl loops.

Counter-measures, layered:

### Rate limiting (multi-keyed)

Single per-IP cap is trivially bypassed with a VPN. Apply ALL of:

- **Per-IP**: 5/hour (already in plan). Hard cap.
- **Per-/24 subnet (IPv4) and per-/64 (IPv6)**: 15/hour. Defeats
  trivial IP rotation in the same provider range.
- **Per-image_id**: 3 reports/24h from any source. The 4th+ identical
  report on the same image is silently dropped (still returns 200).
  Operator dashboard surfaces the "+N duplicate reports" count next to
  the original row, so coordinated mass-reports still influence
  priority but don't multiply queue rows.
- **Per-event_id**: 30/hour total across all images. Catches mass-
  targeting a single photographer.
- **Per-reporter_email** (if given): 5/hour. Email is unverified so
  treat as a soft signal — not a hard authentication.
- **Category does NOT affect the limit.** Equal weight for csam vs.
  other; otherwise attackers always pick csam to bypass.

All limits use the existing `rate_limiter` Redis-backed primitive.
Apply ALL limits before enqueuing — first hit = 429.

### Bot / automation defence

- **Honeypot field** in `ReportPhotoModal`: hidden CSS input
  (`name="website"`, `display:none`); if populated, silently drop with
  generic 200. Bots filling every field land here.
- **Turnstile / hCaptcha** challenge after the first report from a
  given IP in a 24h window. Free tier covers expected volume. Token
  validated server-side before the report row is created. If the
  Turnstile call fails open (network down on Cloudflare side), log it
  but accept the report — the per-IP cap still applies.
- **`X-Requested-With: XMLHttpRequest` check** already lives in the
  CSRF middleware — keep it on `/report` too, so trivial
  `curl https://picur.my/api/report -d ...` is rejected.

### Reporter reputation (soft ban)

Track per-IP (and per-email if given) over a rolling 30-day window:

- Count: reports filed, dismissed, removed, quarantined.
- **Dismiss-rate ≥ 80% with ≥ 5 reports** → silently drop further
  reports from that IP for 7 days (return 200, don't enqueue, don't
  rate-limit-error). Bypass is invisible to the abuser.
- **Dismiss-rate ≥ 90% with ≥ 10 reports** → permanent soft-ban on
  that IP until manually cleared by an operator. Operator dashboard
  shows the silent-drop log with `Clear ban` action.

The drop log is itself audit-logged so an organizer / operator can
reconstruct the silent-drop decision later.

### Anti-enumeration of image_ids

Already in plan: a report against a non-existent UUID returns 200,
not 404. Add:

- **Constant-time response**: the route always does the lookup +
  fixed-delay (50ms) before returning, so a "real id" and "fake id"
  can't be distinguished by response time.
- **No image metadata** in the 200 response — `{"message": "Thank
  you..."}` is fixed text, no echoing of fields the client sent.

### Operator-side ergonomics that reduce abuse impact

- **Same-source dismiss-all button** on the queue page: when N
  reports from a single reporter_email or IP land in the queue,
  operator can mark-all-dismiss with one confirm prompt. Each
  dismissal still writes its own audit row.
- **Duplicate-roll-up display**: as above, "+N duplicate reports on
  this image" badge instead of N separate rows.
- **Sort by reporter-reputation** *(skipped — recomputes dismiss-rate
  per row on every list call, expensive once the table has tens of
  thousands of rows; revisit if the queue grows enough that operators
  need it). Duplicate-roll-up + ban-state badges already surface the
  signal inline.*

### Self-reporting defence

Event owners shouldn't game the system by reporting their own
content (e.g. to force takedown via operator review faster than the
normal delete flow):

- If `reporter_ip` matches the IP of any `audit_logs.actor_id =
  event.owner_user_id` action in the last 24h on the same event,
  flag with a "possible self-report" badge in the queue. Doesn't
  auto-dismiss — operator decides — but it surfaces the signal.
- The owner already has direct delete access, so legitimate
  takedowns don't need /report.

### Tests for reporting-mechanism abuse

`backend/tests/test_report_abuse_defence.py`:

1. Per-/24 subnet limit fires at the 16th report from a contiguous
   range of source IPs.
2. 4th report on the same image_id returns 200 but creates no row.
3. 31st report on the same event_id returns 429.
4. Honeypot field populated → silent 200, no row created.
5. Turnstile token missing/invalid → 403.
6. Soft-ban after 5 reports with 4 dismissed: 6th report returns 200
   but creates no row, and a `soft_ban_drop` audit row exists.
7. Fake image_id and real image_id have response times within ±20ms
   of each other.
8. Self-report signal: reporter IP that matches event-owner IP gets
   the `is_possible_self_report=true` flag in the admin queue
   response.

### Escalation knobs (deferred unless abuse becomes severe)

- Require login + email-verified account for reports above some
  daily floor (e.g. anonymous reports stop after the daily quota,
  authenticated reports continue).
- AbuseIPDB / Cloudflare Threat Score lookup at report time —
  high-score IPs get auto-quarantined into a manual-review-only
  queue.
- Geographic / ASN allowlists if abuse is concentrated in known
  hostile ranges.
- Bond posting via Stripe — refundable $1 hold on the card that's
  forfeited if the report is dismissed for bad faith. Heavy hammer,
  only if everything else fails.

## Out of scope (deferred)

- Automated CSAM hash matching (NCMEC PhotoDNA / IWF) — requires
  registration, vetting, infra. Manual review only for v1.
- Auto-reporting to law enforcement (NCMEC CyberTipline / SaferNet).
- Email notification to organizer on each operator reveal — was
  considered, deferred at user's call. Trail still exists in the
  per-event audit log.
- Reporter-facing "your report status" page.
- Bulk operations on multiple reports.
- Rate limit per reporter_email beyond IP.
- Appeal flow for organizers who think a takedown was wrong.

## Operational notes

- The KMS key from the SSE-S3 setup is critical for reading
  quarantined photos. Already documented in
  `frontend/SECURITY_AUDIT.md`.
- Quarantined photos preserve disk usage. Retention policy will NOT
  auto-delete them — they sit indefinitely until manually deleted.
  Worth a follow-up to add a 90-day auto-purge for quarantined
  photos that haven't been touched. Out of scope v1.
