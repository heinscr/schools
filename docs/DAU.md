# Daily Active Users (DAU) tracking

This document describes the DAU feature added to the project.

Definition of "active":
- A user is considered active for a calendar date (site primary timezone) if they trigger at least one qualifying event (page view, search, district selection, etc.) during that date.

Identifiers and deduping rules:
- Logged-in users are deduped by Cognito `sub` (internal `user_id`). Items are stored with SK `USER#<user_id>`.
- Anonymous visitors are assigned a random `anon_id` stored in `localStorage` (key `anon_id_v1`). Items use SK `ANON#<anon_id>`.
- If an anonymous visitor later logs in during the same day and both identifiers are present, a merge operation maps the `ANON` item to the `USER` item for that date to avoid double counting. Merge attempts are done transactionally where supported.

Storage model:
- Single DynamoDB table (existing table) is used. For each active user and date we create/update an item:
  - PK: `METRIC#DAU#YYYY-MM-DD`
  - SK: `USER#<user_id>` or `ANON#<anon_id>`
  - Attributes: `user_type` (logged_in/anonymous), `user_id`, `anon_id`, `first_seen_at`, `last_seen_at`, `source`
- Items are created/updated via `UpdateItem` (idempotent) so multiple events in the same day update timestamps rather than creating duplicates.

Merge rule (anon -> user):
- When both `anon_id` and `user_id` are present for the same date, the backend attempts a transaction that:
  1) Puts (creates) the `USER` item for that date if it does not exist
  2) Deletes the `ANON` item for that date
- If transactions fail, a best-effort fallback attempts to create/update the `USER` item and delete the `ANON` item.

Admin UI and validation:
- Admin-only endpoint: `GET /api/metrics/admin/dau?start=YYYY-MM-DD&end=YYYY-MM-DD` returns per-day counts.
- Frontend admin modal shows DAU over time (7/30/90 days) and allows CSV export.

Privacy and compliance:
- No raw IP addresses or device fingerprints are stored.
- `anon_id` is a random UUID generated client-side and stored in `localStorage` (not derived from PII).
- Tracking respects existing application consent mechanisms; tracking calls can be made conditional on consent in the frontend if needed.

Developer notes:
- Primary timezone: `PRIMARY_TIMEZONE` environment variable (TZ database name) controls which calendar is used; defaults to `UTC`.
- Backend implementation: `backend/services/metrics_service.py` and router `backend/routers/metrics.py`.
- Frontend: `frontend/src/services/metrics.js` and admin UI `frontend/src/components/AdminMetrics.jsx`.
- Tests: basic unit tests in `backend/tests/test_metrics.py` exercise dedupe and merge logic.

How to validate in staging:
1. Visit the site as an anonymous user; the frontend will assign `anon_id` and send `page_view` on load.
2. Use the admin modal to view DAU for today and recent days.
3. Log in as the same user (simulate by using local dev auth) and ensure anon->user merge removes the anonymous count for that date.

