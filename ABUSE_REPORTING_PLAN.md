# PicUr — Abuse Reporting & Operator Review

Status: draft, not yet implemented
Owner: arvindhsekharan@gmail.com
Last updated: 2026-05-14

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
  `category` filter.
- Returns abuse reports joined with:
  - Image filename + upload time + uploader (event owner)
  - Event name + slug
- Photo bytes / URLs NOT returned in this view.

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

### "Report" button placement

Three locations on guest-facing pages:

1. `pages/e/[slug]/results.tsx` — on each matched photo card, a small
   flag icon → opens ReportPhotoModal pre-filled with image_id.
2. `pages/e/[slug]/gallery.tsx` — same flag icon on each gallery
   photo.
3. `pages/share/[event_id]/[image_id].tsx` — public share page gets a
   "Report this photo" link in the footer.

The flag icon should be unobtrusive — opaque hover-only overlay,
small target. We don't want to invite trolling.

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

### Superadmin `/admin/abuse-queue` page

Linked from the existing superadmin nav. Lists pending reports by
default, with filter pills for status (pending / reviewing /
dismissed / quarantined / removed) and category.

Each row shows:
- Category badge + filename + event name (link to event detail) +
  reported-at + reporter email (if given) + truncated description.

Row actions: `[Review]` opens a modal. The modal does:
1. Calls `POST /reveal` → receives the signed URL.
2. Renders the photo inside the modal (max 80vh, scroll, dark
   background).
3. Below the photo: `[Dismiss]` `[Quarantine]` `[Delete]` buttons
   with confirmation prompts.

The Review modal cannot be open without the reveal API call
completing — there is no path where the photo is rendered without an
audit row already written.

### Public copy updates

Already discussed above. Ship as part of the same PR as the
backend so the policy and the code arrive together.

## Implementation phasing

Two-phase rollout:

**Phase 1 — wiring (no live abuse reports yet)**
- All migrations
- All backend endpoints
- Empty admin queue page
- Updated privacy + security copy

Deploy Phase 1 and verify with a smoke-test report from a non-prod
account.

**Phase 2 — reporter UI**
- Report button + modal on results / gallery / share pages

Splitting like this prevents the awkward state where the public can
file reports but operators have no way to see them.

## Tests

### Unit / route tests

`backend/tests/test_abuse_reporting.py`

1. **Public POST /report**
   - Valid payload returns 200 with thanks message.
   - Same image_id can be reported multiple times — both rows
     persist.
   - Per-IP rate limiter: 6th report from same IP within window
     returns 429.
   - Invalid category returns 422 at Pydantic.
   - Oversized description returns 422.
   - Non-existent image_id still returns 200 (anti-enumeration).
   - reporter_email if given is normalised to lowercase.

2. **Admin queue endpoints (auth)**
   - `GET /admin/abuse-reports` requires superadmin (regular admin
     gets 403, no auth gets 401).
   - Default returns pending reports only.
   - Status filter works.
   - Category filter works.
   - Photo URLs are NOT in the response — only metadata.

3. **POST /reveal**
   - First reveal sets `status='reviewing'`, `reviewed_at`,
     `reviewed_by`.
   - Reveal logs an `abuse_review_view` audit row with operator id,
     image id, report id, category.
   - Returned URL has photo_type='abuse_review' and is signature-
     verifiable.
   - Subsequent reveals of the same report do NOT clobber the
     original reviewed_at / reviewed_by (idempotent re-review).
   - Reveal on a non-existent report returns 404.

4. **POST /quarantine**
   - Sets `Image.status='quarantined'`, `abuse_report.status=
     'quarantined'`, `action_taken='quarantine'`.
   - Invalidates gallery + share caches for the event.
   - Audit log `abuse_review_quarantine` row created.
   - Quarantined image NO LONGER appears in guest gallery (gallery
     test).
   - Quarantined image still serves on `/photos/.../abuse_review`
     signed URL (review still works).

5. **POST /delete-photo**
   - Deletes from MinIO (mocked), removes Face rows, removes Image
     row, sets `abuse_report.status='removed'`,
     `action_taken='remove'`.
   - Audit log `abuse_review_delete`.

6. **POST /dismiss**
   - Sets `abuse_report.status='dismissed'`,
     `action_taken='dismiss'`.
   - Audit log `abuse_review_dismiss`.

7. **abuse_review photo_type**
   - Valid signed URL serves bytes even when:
     - Event is frozen.
     - Image is quarantined.
     - Image is in `pending` status.
   - Expired signature returns 403.
   - Tampered sig returns 403.

8. **Image.status='quarantined' guest invisibility**
   - `GET /e/{slug}/gallery` does NOT return quarantined images.
   - `GET /scan` does NOT return quarantined images.
   - `GET /share/{event}/{image}` returns 404 for quarantined image.
   - But the regular signed photo URL also returns 404 for
     quarantined images (cache/public-URL freshness already enforces
     `status IN (indexed, no_faces)`).

### Frontend tests (visual / manual)

- Report button visible on results, gallery, share — hover-only.
- ReportPhotoModal validates category required, submits, shows
  generic success.
- Admin /abuse-queue lists reports with filter chips working.
- Review modal opens, fetches photo via signed URL, all three action
  buttons work + confirm prompts.

### Privacy attestation test

Add a paragraph to `frontend/SECURITY_AUDIT.md` describing the
operator-access carve-out and how it remains falsifiable (per-event
audit log surfacing every `abuse_review_view`).

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
