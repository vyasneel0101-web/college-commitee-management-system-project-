# Orders register and Faculty search verification

## Changes

- The order register previously displayed only `created_assignments`. A removal
  or corrigendum creates an order without creating a new assignment, so its
  recipient and status columns appeared empty.
- Removal orders now show the people and roles from their saved render context.
  This keeps the history visible even after cancellation clears `ending_order`
  while restoring a membership. Older single-person contexts and related rows
  have explicit fallbacks.
- Corrigenda show the withdrawn/restored people from their saved context.
  The column is labelled "Assignment / order effect" so a historical correction
  is not mistaken for a person's current assignment status.
- Assignment orders retain their current membership status labels. Staff and
  external-member relations are loaded together to avoid per-row queries.
- The Principal's Faculty page now has a GET search form, validation, clear
  control, result count and empty-result message. It searches partial staff
  names, department names and current committee names. Exact department and
  committee codes take priority, case-insensitively: `CO` must not match every
  committee simply because "committee" starts with "co".
- Committee matching uses a subquery so users appear once and retain their full
  active committee count. Deactivated staff remain searchable as before;
  technical superusers remain excluded.

## Scope

Only read queries, search-form validation, templates and regression tests changed.
No dependency, database schema, stored order, assignment transition, generated
document, route, authentication or permission rule was changed. The existing
First Save Point tag remains available.

## Checks

- Final complete regression run: **250 passed**, **87% Python statement
  coverage** across the seven application packages (including migrations and
  management commands). The test command was:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.venv/final-fixes-tests-20261021-b --cov=accounts --cov=assignments --cov=orders --cov=committees --cov=notifications --cov=audit --cov=core --cov-report=term:skip-covered
  ```

  Use a new temporary directory name for a future run.
- New tests first reproduced missing removal/correction details, query growth
  with external appointments, missing search, and the short-code edge case.
- Added tests cover single/bulk removal, internal/external people, cancellation,
  restored history, unchanged documents and stable query counts.
- Search tests cover partial/case-insensitive input, exact codes, current versus
  ended memberships, unchanged counts, duplicate prevention, deactivated users,
  users without a department, empty/overlong/HTML input and Principal-only access.
- Django system check, migration consistency, Python compilation and `pip check`
  passed. No migration was generated.
- Live localhost checks verified the reported `GPB/BK/2026-27/002` removal row,
  names/departments/committee searches, empty results, main pages and an
  authenticated document download.
- SQLite integrity and foreign-key checks passed. All 34 saved Word archives
  opened and contained the specimen marker. Order/assignment values and document
  checksums matched before and after verification (34 orders, 36 assignments).
- Browser automation could not start because its runtime failed; no browser
  visual verification is claimed for this change. Live HTTP and Django rendering
  were checked instead. Mobile markup follows the existing labelled table/form
  layout, but a fresh visual mobile check was not completed.

Coverage reports indicate which code was exercised, not proof that every possible
bug has been eliminated. Existing deployment debt and manual acceptance testing
remain separate from these fixes.
