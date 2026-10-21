# Orders register and Faculty search verification

## Latest refinement: readable order actions

The Issued to column now explains what the numbered order did in a complete
sentence, for example: "Dr. Test Faculty 10 removed as Presiding Officer from
bhavix team." Appointed, Removed, Withdrawn and Restored tags accompany each
message. Saved role and staff/organisation details remain below it.

Replacement orders also name the superseded holder. Corrections explain which
order they cancelled and the recorded reason. A subsequently cancelled order
keeps its original action message and shows a separate cancellation note.
Assignment status remains separate: an original appointment still says appointed
even when its assignment was relinquished later. Missing historical roles are
not inferred from a name. Faculty search remains name-only.

- Complete suite: **262 passed**, using
  `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.venv/order-summary-tests-20261021`.
  The default Windows pytest temporary directory was inaccessible; a verified
  fresh directory under the ignored virtual environment resolved that test-setup
  error. Use a new temporary directory name for a future run.
- Django system check and migration consistency check passed.
- Live localhost HTTP login and register rendering verified the example above.
  All 34 order records, 36 assignment records and 34 stored document checksums
  matched before and after the live check.
- Focused tests cover each action, supersession, cancellation/restoration,
  historical versus current status, saved committee names and escaped user text.
  Existing permission, query-count and Faculty-search checks remain green.
- Scope: read-only presentation helpers, list-query preloading, recipient markup
  and two scoped CSS rules. No services, schema, stored contexts, documents or
  permissions changed. Browser visual verification was not repeated.

## Earlier name-search and recipient-detail refinement

The user subsequently requested **Faculty name search only**. Department and
committee matching/code priority were removed, and their tests now assert that
those fields do not match. Partial names, whitespace/case handling, counts and
Principal-only access remain covered.

The register now groups each recipient's saved name/salutation, role and
designation/department or organisation. Each name and role is paired with its own
status/effect tag. Correction details come from the corrected order when recorded;
otherwise the UI explicitly states that staff details were not recorded, rather
than guessing an identity. Saved documents and contexts are never modified.

This refinement passed **256 tests**, Django and migration checks, and live
localhost HTTP checks. Source packages below describe the earlier verification
run; the current search specification is name-only. No fresh browser visual check
was possible because browser automation still could not start.

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
