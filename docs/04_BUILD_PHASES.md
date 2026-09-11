# 04 — Build Phases

> **Sprint status: this document is the post-demo roadmap, not today's plan.**
>
> Today follows the five steps in `00_START_HERE.md`, which compress the essential slice of Phases 0 through 6 into about 100 minutes by dropping tests, magic-link auth, PostgreSQL, and the hardening pass.
>
> After the demo, come back here. Map the sprint's output onto the phases below and fill the gaps in this order:
>
> | Phase | Sprint status | What's missing |
> |---|---|---|
> | 0 | Mostly done | Postgres, `pytest`, `ruff`, split prod settings |
> | 1 | Mostly done | Model tests, constraint tests, `AuditLogEntry`, `django-unfold` |
> | 2 | Partial | Magic-link auth, domain restriction, rate limiting, session invalidation, all tests |
> | 3 | Mostly done | Query-count tests, permission tests, `django-tailwind` |
> | 4 | Partial | `relinquish`, `expire`, `restore_superseded`, domain exceptions, and **all twelve test groups** |
> | 5 | Partial | `OrderSequence` under a real row lock, template upload + validation, cancellation/corrigendum, immutability tests |
> | 6 | Partial | Order register filters, faculty management, audit view, the permission matrix test |
> | 7 | Not started | Everything |
> | 8 | Not started | Everything |
> | 9 | Not started | Everything |
>
> **Phase 4's test groups and Phase 5's numbering tests are the highest-value repayment.** They protect order history, which is the one thing in this system that cannot be reconstructed if it breaks.

Nine phases. **One per session.** Each phase ends with a green full test suite and a Git tag. Do not begin a phase until the previous one's exit criteria are met.

The ordering is deliberate: the data model comes before auth, auth before any screen, the assignment engine before document generation, and UI polish last. The most common way this project fails is building screens before the supersession logic works.

---

## Phase 0 — Project skeleton and configuration

**Goal:** a repo that runs, lints, tests, and has no secrets in it.

**Deliverables**
- Django 5.x project, apps created: `core`, `accounts`, `committees`, `assignments`, `orders`, `notifications`, `audit`
- Split settings: `config/settings/base.py`, `dev.py`, `prod.py`, `test.py`
- `django-environ`, `.env.example` committed, `.env` gitignored
- PostgreSQL 18 connection working against a **locally installed server** — **no Docker**. Driver is `psycopg[binary]`. See `docs/09_LOCAL_POSTGRES.md`. *(Sprint used SQLite; this is debt item 1.)*
- `pytest`, `pytest-django`, `factory_boy`, `pytest-cov`, `ruff` configured in `pyproject.toml`
- `AUTH_USER_MODEL = "accounts.User"` set **before any migration is generated**
- `.gitignore`, `README.md` with local setup steps
- `/healthz` endpoint returning 200 with no DB data
- One smoke test that hits `/healthz`

**Exit criteria**
- [ ] `pytest -q` passes (1 test)
- [ ] `ruff check .` and `ruff format --check .` clean
- [ ] `python manage.py migrate` succeeds against the local Postgres 18 instance
- [ ] `grep -r "SECRET_KEY" --include="*.py"` shows only `env("SECRET_KEY")`
- [ ] `AUTH_USER_MODEL` set and **zero migrations exist yet** for other apps

⚠️ Do not run `makemigrations` for any app in this phase except to confirm `accounts` is first in Phase 1.

`git tag phase-0-complete`

---

## Phase 1 — Data model

**Goal:** the complete schema from `02_DATA_MODEL.md`, with every constraint enforced at the database level.

**Deliverables**
- All models: `Department`, `User` (+ `UserManager`), `AcademicYear`, `Committee`, `CommitteeTemplate`, `Order`, `OrderSequence`, `Assignment`, `AuditLogEntry`
- All `Meta.constraints` and indexes as specified
- Custom managers/querysets: `Assignment.objects.active()/for_faculty()/directory()`, `Order.objects.visible_to()`, `User.objects.faculty_with_counts()`, `AcademicYear.objects.current()`
- `factory_boy` factories for every model
- `django-unfold` installed; all models registered in admin with explicit `fields` lists (never `__all__`)
- `AuditLogEntry.save()` raises on update; `delete()` raises; admin permissions all `False`
- Migrations, in the right order, with `accounts` first

**Tests required** (details in `05_TESTING.md` §2)
- Every constraint has a test asserting `IntegrityError` on violation — especially `uniq_active_assignment` and `uniq_active_convener`
- `AcademicYear` single-current constraint
- Audit log immutability
- `PROTECT` behaviour: deleting a referenced `Committee`/`Department`/`User` raises
- Email lowercase normalization
- Every manager method returns what it claims, with a query-count assertion on `directory()`

**Exit criteria**
- [ ] All model tests pass
- [ ] `makemigrations --check --dry-run` reports nothing missing
- [ ] Django admin loads and every model is browsable
- [ ] No `fields = "__all__"` anywhere: `grep -r '__all__' --include="*.py"` returns nothing in admin/forms

`git tag phase-1-complete`

**Do not build any view in this phase.**

---

## Phase 2 — Authentication and authorization

**Goal:** the right people can get in, nobody else can, and the permission primitives exist.

**Deliverables**
- `django-allauth` configured, self-signup disabled via a custom adapter
- Magic-link login: request form, token issue, email send, callback view, single-use consumption, 15-minute expiry
- Three-layer domain restriction (form, adapter, model validation)
- Rate limiting via `django-ratelimit` on the login request endpoint
- No-enumeration login response
- `PrincipalRequiredMixin` / `principal_required` decorator returning **403**
- `FacultyOwnedObjectMixin`
- Post-login role-based redirect
- Logout as POST-only
- Session settings per `03_SECURITY.md` §1
- Session invalidation on role change / deactivation
- `next`-parameter validation with `url_has_allowed_host_and_scheme`
- Auth events written to the audit log
- Management command: `create_principal` — bootstraps the first Principal account
- Placeholder dashboard views (one line of text each) so the redirect has somewhere to go

**Tests required**
- Valid domain email receives a link; invalid domain does not, and the responses are identical
- Magic link logs the user in; second use fails; expired token fails; tampered token fails; token issued for A does not log in B
- Inactive user cannot log in even with a valid token
- Rate limit triggers at the 6th request in an hour
- `principal_required` returns 403 for faculty, 200 for principal, redirect for anonymous
- Role change invalidates the existing session
- `next=https://evil.example.com` does not redirect off-site
- Non-existent email produces the same response as an existing one

**Exit criteria**
- [ ] All auth tests pass, full suite green
- [ ] You can personally log in end-to-end using a console email backend
- [ ] `check --deploy` clean

`git tag phase-2-complete`

---

## Phase 3 — Read-only faculty experience

**Goal:** the visibility problem is solved. This is the first phase with real user value, and it needs no write logic.

**Deliverables**
- Base template, Tailwind build via `django-tailwind`, HTMX + Alpine (CSP build) as **local static files, not CDN**
- Navigation with role-aware links
- **My Dashboard** — active committees with role and start date, count badge, past committees collapsed
- **Institution Directory** — all active assignments, searchable and filterable by department/committee, HTMX-driven
- **Faculty Workload** — all faculty with active committee counts, sortable
- **My Profile** — view all own fields, edit mobile only
- **Faculty Detail** — field visibility differs by viewer role per the matrix
- Empty states written per `06_UI_DIRECTION.md`
- Seed management command with obviously fake data (`Test Faculty One`, etc.)

**Tests required**
- Faculty dashboard shows only own assignments; another faculty's do not appear
- Directory shows active only, never superseded
- Workload counts match the number of active assignments (build a fixture with mixed statuses)
- Profile POST with `role`, `is_active`, or `designation` in the payload changes none of them
- Faculty viewing another faculty's detail page does not see mobile, joining date, or employee code
- Query-count assertion: directory with 50 assignments issues fewer than 10 queries
- Anonymous access to each view redirects to login

**Exit criteria**
- [ ] Full suite green
- [ ] Screens work at 375px width
- [ ] Keyboard focus is visible on every interactive element
- [ ] No N+1 (query-count tests pass)

`git tag phase-3-complete`

---

## Phase 4 — Assignment engine

**Goal:** the supersession state machine, correct and proven, with **no UI and no document generation**.

This is the highest-risk phase. It is deliberately isolated so its correctness can be established before anything depends on it.

**Deliverables** — all in `assignments/services.py`, all `@transaction.atomic`:
- `assign_committee(*, faculty, committee, role, order, effective_date=None) -> Assignment` — creates the assignment, auto-supersedes the existing active holder of the same role when applicable (BR-2, BR-3)
- `relinquish_assignment(*, assignment, order) -> Assignment` — BR-4
- `expire_assignments_for_year(academic_year)` — batch rollover
- `restore_superseded(*, assignment)` — used by order cancellation (BR-6)
- Domain exceptions: `AssignmentConflict`, `CommitteeInactive`, `FacultyInactive`, `NoCurrentAcademicYear` — specific types, not bare `ValueError`
- Audit log entries for every transition

**Tests required — the most important set in the project**
1. Assigning a convener to an empty committee creates one `ACTIVE` assignment
2. Assigning a new convener supersedes the old one: old is `SUPERSEDED`, `end_date` = new order date, `superseded_by` points to the new assignment, and exactly one `ACTIVE` convener remains
3. Adding a member does **not** affect existing members
4. Assigning the same faculty to the same committee+role twice raises `AssignmentConflict` and creates nothing
5. Relinquishing sets `RELINQUISHED` with `end_date` and `ending_order`, and leaves no active holder
6. Assigning to an inactive committee raises
7. Assigning an inactive faculty raises
8. **Atomicity:** force a failure mid-service (patch a save to raise); assert the database is unchanged — no orphan assignment, no half-superseded record
9. `expire_assignments_for_year` transitions only that year's `ACTIVE` rows
10. `restore_superseded` returns a superseded assignment to `ACTIVE` and clears `end_date` and `superseded_by`
11. Full lifecycle: A → B → C hand-overs produce a correct chain, and querying history returns all three in order
12. History is intact after every operation: total assignment row count only ever increases

**Exit criteria**
- [ ] All 12 test groups pass
- [ ] Test coverage on `assignments/services.py` is **100%**
- [ ] `grep -rn "\.delete()" assignments/ orders/` finds nothing in application code
- [ ] Full suite green

`git tag phase-4-complete`

---

## Phase 5 — Order generation

**Goal:** issuing an order produces a correctly numbered, correctly rendered, permanently stored `.docx`.

**Deliverables**
- `orders/services.py::next_order_no()` with `select_for_update` per `02_DATA_MODEL.md`
- `orders/services.py::issue_assignment_order(...)` — one atomic transaction that: generates the number, builds the render context from DB objects, renders via `docxtpl` with a sandboxed Jinja env, saves the file, creates the `Order`, calls `assign_committee`, writes audit entries
- `issue_relinquishment_order(...)`
- `cancel_order(*, order, reason, cancelling_order)` — marks cancelled, sets assignments to `CANCELLED`, restores superseded ones (BR-6)
- `CommitteeTemplate` upload with the full validation chain from `03_SECURITY.md` §5 and placeholder detection
- Protected download view per `03_SECURITY.md` §3
- One realistic sample `.docx` template committed to `tests/fixtures/` for testing

**Tests required**
1. Order number format is exactly `GPB/TPU/2026-27/001`
2. Sequential numbering: three orders for the same committee+year give `001`, `002`, `003`
3. Different committees have independent sequences
4. **Concurrency:** two threads/connections issuing simultaneously produce two distinct numbers, never a duplicate (use `TransactionTestCase`)
5. Cancelling order `002` and issuing another gives `004` — the number is not reused
6. Rendered `.docx` contains the faculty name, committee name, order number, and date (open the output with `python-docx` and assert on text)
7. Changing a committee's template does **not** alter a previously issued order's stored file (BR-7) — assert byte-for-byte identity
8. `render_context` is stored and matches what was rendered
9. Order fields are immutable: attempting to change `order_no` on a saved order raises
10. Full atomicity: a docx render failure leaves no `Order`, no `Assignment`, and does not consume a sequence number *(note: if you choose to let the sequence advance on rollback, document that explicitly — gaps are acceptable in a register, duplicates are not)*
11. Template upload rejections: `.docm`, oversized, corrupt zip, `vbaProject.bin` present, missing required placeholder — five separate tests
12. Download: owner gets 200, other faculty gets 404, principal gets 200, anonymous redirects
13. Anonymous request to the raw media path for an order file does not return the file
14. Cancellation restores the previously superseded assignment to `ACTIVE`

**Exit criteria**
- [ ] All tests pass, coverage on `orders/services.py` is 100%
- [ ] You have manually opened a generated `.docx` and confirmed it looks like a real college order
- [ ] Full suite green

`git tag phase-5-complete`

---

## Phase 6 — Principal workflows (UI)

**Goal:** the Principal can do the whole job through the browser.

**Deliverables**
- **Assign Committee** flow: committee select → HTMX faculty search dropdown → role → order date → **preview** → issue. Preview shows what will happen, including "this will supersede Mihir Patel as Convener," before anything is written.
- Faculty search endpoint with all §4 restrictions
- **Relinquish** flow with confirmation
- **Order Register** — filterable list, detail view, download
- **Cancel order** — two-step confirmation, reason required
- **Committee management** — create, edit, template upload with placeholder feedback
- **Faculty management** — create, edit, deactivate (with an active-assignment warning)
- **Audit log** view, read-only
- Success/error messaging via `django.contrib.messages`, worded per `06_UI_DIRECTION.md`

**Tests required**
- Every endpoint in the `03_SECURITY.md` matrix — this is where the parametrized permission test is completed
- Assign flow POST creates order + assignment + supersession; the resulting page shows the order number
- Preview endpoint writes nothing to the database (assert row counts unchanged)
- Assign form rejects a future order date
- Cancel requires a reason
- Faculty search: 403 for faculty; 1-char query returns empty; result cap respected; response body contains no email or mobile string
- Deactivating faculty with active assignments produces a warning and does not silently end them
- CSRF: POST without a token fails on every write endpoint
- XSS: a committee description of `<script>alert(1)</script>` renders escaped

**Exit criteria**
- [ ] Permission matrix test covers 100% of URL patterns — assert this programmatically by comparing tested paths against `get_resolver().reverse_dict`
- [ ] Full suite green
- [ ] You have personally walked the full assign → order → download flow

`git tag phase-6-complete`

---

## Phase 7 — Notifications

**Goal:** faculty are emailed when assigned, without the request blocking on it.

**Deliverables**
- `django-q2` configured with a cluster
- HTML + plain-text email templates: assignment issued, relinquishment, magic link
- Order `.docx` attached to the assignment email
- Task queued **after** the transaction commits (`transaction.on_commit`) — never inside it, or you may email about an order that rolled back
- Retry with backoff; failures logged and surfaced in the audit log
- `notifications` model or log recording sent/failed per order, visible to the Principal
- SMTP config from env; console backend in dev; `locmem` in tests

**Tests required**
- Assignment email queued exactly once per order
- Email queued only on commit: a rolled-back transaction queues nothing
- Recipient is the affected faculty; the Principal is copied; nobody else
- Order file is attached
- Send failure does not roll back the order — the order is official regardless of email delivery
- Failure is recorded and retried
- Magic-link email contains a working link and no other user's data

**Exit criteria**
- [ ] Full suite green
- [ ] A real test email has been sent and received (use your own address)

`git tag phase-7-complete`

---

## Phase 8 — Security hardening and audit pass

**Goal:** work through `03_SECURITY.md` §8 as a checklist and prove each item.

**Deliverables**
- Production settings complete per §6, `check --deploy` clean
- `django-csp` configured with no `unsafe-inline` and no `unsafe-eval`
- `django-axes` for admin lockout
- Structured logging, with a test asserting no token or secret appears in log output
- Admin URL from env
- A written `SECURITY_AUDIT.md` in the repo: the §8 table with, for each row, the test name that proves it and the result
- Dependency audit: `pip-audit`, all findings resolved or documented
- A test that fails if any view lacks a login requirement — enumerate URL patterns, request each anonymously, assert none returns 200 except the documented exceptions

**Exit criteria**
- [ ] All 20 threats in §8 have a named passing test
- [ ] `pip-audit` clean
- [ ] `check --deploy` produces zero warnings
- [ ] Coverage ≥ 90% overall, 100% on all `services.py`
- [ ] Full suite green

`git tag phase-8-complete`

---

## Phase 9 — UI polish and deployment

**Goal:** it looks like something a government institution would be glad to use, and it runs somewhere real.

**Deliverables**
- Visual pass per `06_UI_DIRECTION.md`
- Responsive down to 375px; every screen checked
- Accessibility: visible focus rings, `aria-live` on HTMX-swapped regions, labels on all inputs, contrast ≥ 4.5:1, `prefers-reduced-motion` respected
- Loading and error states on every HTMX interaction
- A **print stylesheet** for the directory and order register — this office prints things
- Deployment to Railway or Render: Postgres, `whitenoise`, `gunicorn`, `django-q2` worker process, env vars set, migrations on release
- `pg_dump` backup procedure documented in `README.md`
- `DEPLOYMENT.md`: environment variables, first-run steps (`create_principal`, create `AcademicYear`, create departments, create committees, upload templates), rollback procedure

**Exit criteria**
- [ ] Deployed and reachable over HTTPS
- [ ] `DEBUG = False` verified in production
- [ ] Full flow works in production with a real email
- [ ] Full suite green against the production settings module
- [ ] A backup has been taken and a restore tested

`git tag v1.0.0`

---

## Phase summary

| Phase | Focus | Risk |
|---|---|---|
| 0 | Skeleton, config | Low |
| 1 | Data model | **High** — mistakes here are expensive |
| 2 | Auth | High |
| 3 | Faculty read-only screens | Low |
| 4 | Assignment engine | **Highest** — the state machine |
| 5 | Order generation | **High** — numbering and immutability |
| 6 | Principal UI | Medium |
| 7 | Email | Low |
| 8 | Security audit | High |
| 9 | Polish, deploy | Medium |

If you have limited time, Phases 0–6 are a defensible, demonstrable project. Do not skip Phase 4's tests to reach Phase 6 faster.
