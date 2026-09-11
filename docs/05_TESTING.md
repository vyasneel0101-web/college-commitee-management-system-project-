# 05 — Testing Specification

> **Sprint status: no tests are written today.** This is a deliberate, time-boxed decision, recorded as debt item 2 in `00_START_HERE.md` §5 — not an abandonment of the standard.
>
> Do not write placeholder or fake tests during the sprint. An empty suite is honest; a suite of assertions that always pass is worse than nothing, because it creates false confidence in exactly the logic that protects order history.
>
> **Repayment order after the demo**, highest value first:
> 1. §4 — the assignment engine's twelve test groups. This is the supersession logic; a regression here silently corrupts history.
> 2. §5 — order numbering and document immutability.
> 3. §3 — the permission matrix, including the completeness test.
> 4. Everything else.
>
> Steps 1 and 2 are roughly a day's work and are what make the system trustworthy enough for real records.

Tests are the deliverable that makes "no bugs, no broken flows" a checkable claim instead of a hope. This document says what must be tested and how.

---

## 1. Setup

- `pytest` + `pytest-django` + `pytest-cov` + `factory_boy`
- Database: **PostgreSQL** once tests exist. The concurrency test in §5 is meaningless on SQLite, which ignores `select_for_update`. Repay debt item 1 before or alongside debt item 2.
- `--reuse-db` locally for speed; fresh DB in CI
- Email backend: `locmem` in tests
- File storage in tests: a `tmp_path`-based `MEDIA_ROOT` so tests never write into the real media directory
- Factories for every model, in `<app>/tests/factories.py`

Layout:
```
<app>/tests/
    factories.py
    test_models.py        # constraints, managers, properties
    test_services.py      # business logic
    test_views.py         # status codes, context, rendering
    test_permissions.py   # who can reach what
```

### Rules for writing tests

1. **A test must fail if the feature is removed.** Before considering a test done, mentally delete the feature and confirm the test breaks. If it wouldn't, the test is decoration.
2. **Never assert only on a status code** for a business operation. Assert on database state.
3. **Never mock the thing under test.** Mock only external boundaries: SMTP, the clock, file storage.
4. **One behaviour per test**, with a name that states the behaviour: `test_assigning_new_convener_supersedes_existing_holder`.
5. **No test may depend on another test's side effects** or on execution order.
6. **When a test fails, fix the code.** Changing the assertion to match buggy output is prohibited. If the test itself was wrong, say so explicitly and explain why before changing it.

---

## 2. Model layer — required tests

**Constraints (each asserts `IntegrityError` via `pytest.raises`, inside `transaction.atomic()`):**
- `uniq_active_assignment` — same faculty + committee + role, both `ACTIVE`
- `uniq_active_convener` — two `ACTIVE` conveners for one committee
- Same faculty as `ACTIVE` convener in two *different* committees **succeeds** (guards against an over-broad constraint)
- Superseded duplicate is allowed: one `ACTIVE` + one `SUPERSEDED` for the same faculty/committee/role succeeds
- `active_has_no_end_date`
- `end_date >= start_date`
- `AcademicYear` — two rows with `is_current=True`
- `AcademicYear.end_date > start_date`
- `Order.order_no` uniqueness
- `Order` cancellation requires a reason
- `CommitteeTemplate` — two `is_active=True` for one committee
- `User.email` uniqueness, including differing only by case

**Behaviour:**
- Email is lowercased on save; `Test@X.com` and `test@x.com` collide
- Out-of-domain email fails validation at the model layer
- `UserManager.create_user` requires an email; `create_superuser` sets the right flags
- Mobile validator accepts `9876543210` and `+919876543210`, rejects `12345`, `98765abcde`, and a 15-digit string
- `PROTECT`: deleting a `Department`, `Committee`, `User`, or `AcademicYear` referenced by an order raises `ProtectedError`
- `AuditLogEntry`: `save()` on an existing instance raises; `delete()` raises; admin add/change/delete permissions are all `False`
- `Committee.code` cannot change once an order references the committee

**Managers:**
- `Assignment.objects.active()` excludes all four non-active statuses (parametrize over them)
- `Assignment.objects.for_faculty(u)` returns all statuses for `u` and nothing for anyone else
- `Order.objects.visible_to()` — principal sees all; faculty sees only orders that created or ended their own assignments; faculty sees zero of an unrelated faculty's orders
- `User.objects.faculty_with_counts()` — counts only `ACTIVE`; a faculty with 3 active + 2 superseded shows 3
- `AcademicYear.objects.current()` raises a specific exception when none is marked current

**Performance:**
- `Assignment.objects.directory()` with 50 rows: assert query count with `django_assert_num_queries`. Set a hard ceiling (e.g. 6) so a future template change that adds an N+1 fails the build.

---

## 3. The permission matrix test

Implement `03_SECURITY.md` §2's table as a single parametrized test. This is the backbone of the security story.

```python
# tests/test_permission_matrix.py

MATRIX = [
    # (method, url_name, url_kwargs_factory, anon_expect, faculty_expect, principal_expect)
    ("GET",  "dashboard",       None,          "redirect", 200, 200),
    ("GET",  "orders:assign",   None,          "redirect", 403, 200),
    ("GET",  "orders:download", order_kwargs,  "redirect", 404, 200),
    ("GET",  "htmx:faculty_search", None,      "redirect", 403, 200),
    # ... every row of the matrix
]

@pytest.mark.parametrize("method,name,kwargs_fn,anon,faculty,principal", MATRIX)
def test_permission_matrix(...):
    ...
```

**Plus a completeness test** — this is what stops a new endpoint from silently shipping unprotected:

```python
def test_every_url_pattern_appears_in_matrix():
    """Fails when a new endpoint is added without a permission decision."""
    all_names = collect_url_names(get_resolver())
    tested = {row[1] for row in MATRIX}
    assert all_names - tested - DOCUMENTED_EXEMPTIONS == set()
```

`DOCUMENTED_EXEMPTIONS` is a short, explicitly commented set: `healthz`, `login`, `magic_link_callback`, static/media, admin. Anything else added to it requires justification in the commit message.

**And an anonymous sweep:**

```python
def test_no_view_returns_200_to_anonymous_user():
    """Every URL except documented exemptions must reject anonymous access."""
```

---

## 4. Assignment engine — required tests (Phase 4)

These twelve groups are non-negotiable. Coverage on `assignments/services.py` must be **100%**.

| # | Test | Assertion |
|---|---|---|
| 1 | Assign convener to empty committee | 1 row, `ACTIVE`, `start_date` = order date, `issuing_order` set |
| 2 | Assign new convener over existing | Old: `SUPERSEDED`, `end_date` = new order date, `superseded_by` = new. Exactly 1 `ACTIVE` convener. 2 rows total. |
| 3 | Add member to committee with members | Existing members unchanged, all still `ACTIVE` |
| 4 | Duplicate active assignment | `AssignmentConflict` raised; row count unchanged |
| 5 | Relinquish | `RELINQUISHED`, `end_date` set, `ending_order` set, `superseded_by` null, zero `ACTIVE` holders |
| 6 | Assign to inactive committee | `CommitteeInactive` raised, nothing created |
| 7 | Assign inactive faculty | `FacultyInactive` raised, nothing created |
| 8 | **Atomicity** | Patch a save inside the service to raise; assert `Assignment.objects.count()` and `Order.objects.count()` are both unchanged from before the call |
| 9 | `expire_assignments_for_year` | Only that year's `ACTIVE` rows become `EXPIRED`; other years and non-active statuses untouched |
| 10 | `restore_superseded` | Back to `ACTIVE`, `end_date` and `superseded_by` cleared |
| 11 | Three-way chain A→B→C | Chain links correct in both directions; history query returns 3 rows in date order; exactly 1 `ACTIVE` |
| 12 | **History preservation** | After a sequence of 10 mixed operations, total row count equals total operations that create rows; no row was ever deleted (compare max PK to count) |

Test 8 and test 12 are the ones that catch the failure modes you actually care about. Do not let them be skipped.

---

## 5. Order generation — required tests (Phase 5)

Coverage on `orders/services.py` must be **100%**.

**Numbering:**
- Format exactly matches `GPB/TPU/2026-27/001` (regex assertion)
- Three sequential orders → `001`, `002`, `003`
- Separate committees keep independent sequences
- Separate academic years keep independent sequences
- **Concurrency test** — use `TransactionTestCase` with two threads and separate DB connections (or two processes) issuing simultaneously; assert two distinct order numbers and no `IntegrityError`. This test is the whole reason for `select_for_update`; without it you have no evidence the lock works.
- Cancelling an order does not free its number: cancel `002`, issue again, get `004`

**Rendering:**
- Generated `.docx` opens with `python-docx` and its text contains the faculty name, salutation, committee name, order number, order date, and role
- Every required placeholder is substituted — no `{{` remains in the output text
- Template with a missing optional placeholder still renders
- `render_context` stored on the order equals the dict passed to `docxtpl`

**Immutability (BR-6, BR-7):**
- Read a generated file's bytes → upload a new template version → re-read the original order's file → **bytes identical**
- Setting `order.order_no = "X"` and saving raises
- No URL pattern exists for editing an order (assert `NoReverseMatch` for a plausible edit name)

**Cancellation:**
- Cancelling sets `is_cancelled`, requires a reason, links `cancelled_by_order`
- Assignments created by the cancelled order become `CANCELLED`
- An assignment the cancelled order had superseded returns to `ACTIVE`
- The cancelled order's file still exists and is still downloadable (it is part of the record)

**Template upload rejections** — five separate tests, each asserting a specific error message:
- `.docm` extension
- File > 2 MB
- Corrupt/non-zip file
- Archive containing `vbaProject.bin`
- Missing a required placeholder (error names the missing placeholder)

**Download security:**
- Owner faculty: 200, correct `Content-Disposition`, `Cache-Control: private, no-store`
- Unrelated faculty: **404** (not 403 — do not confirm the order exists)
- Principal: 200
- Anonymous: redirect to login
- Direct request to the raw `MEDIA_URL` path for an order file does not serve the file
- Download writes an `ORDER_DOWNLOADED` audit entry

---

## 6. Security tests

One named test per threat in `03_SECURITY.md` §8, T1–T20. Record the mapping in `SECURITY_AUDIT.md`. The ones that need specific technique:

- **T2 (privilege escalation):** POST to `/profile/` with `role=PRINCIPAL`, `is_active=False`, `designation=PRINCIPAL`, `department=<other>`, `employee_code=X` all in one payload. Refetch the user from the DB and assert every one of those fields is unchanged. This is the single most valuable security test in the project.
- **T4/T5 (magic link):** second use, expiry (freeze time or inject a clock), tampered signature, token for A used by B.
- **T6 (domain):** rejected at the form, at the adapter, and at the model — three tests, not one.
- **T14 (CSRF):** use a test client with `enforce_csrf_checks=True` and POST to every write endpoint without a token; assert 403.
- **T15 (XSS):** store `<script>alert(1)</script>` in a committee description and in order remarks; assert the rendered HTML contains the escaped form and not the raw tag. Also `grep` the templates: `|safe` and `mark_safe` must not appear on any user-supplied value.
- **T19 (open redirect):** `?next=https://evil.example.com`, `?next=//evil.example.com`, `?next=/legit/` — first two must not redirect off-site, third must work.
- **T20 (headers):** assert `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and the CSP header are present on a normal page response.

**Log-hygiene test:** trigger a magic-link request and an order issuance with logging captured; assert the captured output contains no token substring, no session key, and not the `SECRET_KEY` value.

---

## 7. Notification tests

- Exactly one email queued per issued order
- `transaction.on_commit` respected: within a rolled-back atomic block, zero emails queued
- Recipients are exactly `[faculty.email]` with the principal on cc
- `.docx` attached, with the right filename
- SMTP failure does not roll back the order (patch send to raise; assert the order still exists)
- Failure recorded and marked for retry
- Magic-link email contains a resolvable link and no other user's data

---

## 8. Gates

Every phase must pass all of these before sign-off:

```bash
ruff check .
ruff format --check .
python manage.py makemigrations --check --dry-run
python manage.py check --deploy --settings=config.settings.prod
pytest -q
pytest --cov --cov-report=term-missing --cov-fail-under=85
```

**Coverage requirements:**

| Scope | Minimum |
|---|---|
| Overall | 85% (90% from Phase 8) |
| `assignments/services.py` | **100%** |
| `orders/services.py` | **100%** |
| `accounts/` auth code | **100%** |
| All `views.py` | 95% |
| Templates, settings, migrations | excluded |

Coverage is a floor, not a goal. 100% coverage with weak assertions is worse than 85% with real ones, because it hides the gap.

**CI:** a GitHub Actions workflow running the gates on every push, with a Postgres service container. Set this up in Phase 0 so it never becomes a chore later.

---

## 9. Manual test script (before showing anyone)

Automated tests do not catch "the button is off the screen" or "the order says `{{ faculty_name }}`." Walk this by hand at the end of Phase 6 and again at Phase 9:

1. Log in as Principal via magic link. Confirm the link expires after use.
2. Create a department, an academic year, a committee; upload a real template.
3. Create three faculty accounts.
4. Assign the committee's convener role to Faculty A. Download the order. **Open it in Word.** Confirm formatting, numbering, and date are correct and printable.
5. Assign the same role to Faculty B. Confirm the preview warned about superseding A, that A's dashboard now shows it under past committees, and that the directory shows B.
6. Confirm A's order from step 4 is still downloadable and unchanged.
7. Log in as Faculty A. Confirm: own dashboard correct, directory visible, no assign button anywhere, and typing `/orders/assign/` in the address bar gives 403.
8. As Faculty A, try to open Faculty B's order URL by changing the ID. Confirm 404.
9. Cancel B's order with a reason. Confirm A is restored as active and the register shows both the cancelled order and the corrigendum.
10. Assign five more committees to Faculty A. Confirm the workload screen reads 6.
11. Deactivate Faculty C. Confirm they cannot log in and their history is still visible to the Principal.
12. Check the audit log contains every action from steps 1–11.
13. Resize the browser to 375px and repeat steps 5 and 7.
14. Print the directory page. Confirm it is legible on paper.

Write the result of each step in `MANUAL_TEST_LOG.md` and commit it. When your college asks whether this is reliable, that file is the answer.
