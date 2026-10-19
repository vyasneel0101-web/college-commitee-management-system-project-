# CLAUDE.md — Standing rules for this repository

Project: **CAMS** — Committee Assignment Management System, Government Polytechnic Bhuj.
Replaces a paper-based process by which the Principal assigns institutional committees to faculty and issues official orders.

This is a government institution's record-keeping system. Orders generated here are official documents. Treat correctness and auditability as more important than speed or elegance.

Full specification lives in `docs/`. **Read `docs/00_START_HERE.md` first** — it defines the current session's scope and overrides this file where they conflict. Then read `docs/02_DATA_MODEL.md` before any task that touches models or business logic.

**Current state: a two-hour demo sprint on real foundations.** Models, field names, services layer and constraints are real. SQLite, plain password auth, CDN Tailwind and the absent test suite are temporary, and every one of them is listed as repayable debt in `docs/00_START_HERE.md` §5.

---

## Stack — do not substitute

- Python 3.12, Django 5.x
- **Database: SQLite for now**, PostgreSQL 18 later. Read from `DATABASE_URL` so the switch is one env var. SQLite does support partial unique indexes, so all the constraints in `docs/02_DATA_MODEL.md` work today — but `select_for_update` silently does nothing on SQLite, so order numbering is not race-safe until the move to Postgres. Tracked as debt item 1 in `docs/00_START_HERE.md` §5. Postgres setup notes are in `docs/09_LOCAL_POSTGRES.md`.
- `django-allauth` for authentication
- Tailwind CSS via `django-tailwind`, HTMX, Alpine.js
- `django-unfold` for the Django admin theme
- `docxtpl` for order document generation
- `django-q2` for background tasks
- `django-environ` for configuration
- `Pillow` for the signature image
- **Deferred until after the demo:** `django-allauth`, `django-unfold`, `django-tailwind`, `django-q2`, `pytest`/`pytest-django`/`factory_boy`, `ruff`. Tailwind comes from a CDN for now; auth is plain Django username/password.

**Do not add a dependency without asking me first.** State what it does, why the stdlib or an existing dependency is insufficient, and its maintenance status.

---

## Architecture rules

1. **Business logic lives in `services/`, not in views, not in models, not in forms.**
   Any operation that writes to more than one row or table goes in a service function. Views validate input, call a service, and render. Example: `assignments/services.py::assign_committee(...)`.

2. **Every state-changing service function is wrapped in `transaction.atomic()`.**
   Assignment supersession and order creation must be all-or-nothing. A committee that is handed over but whose order failed to generate is a corrupted record.

3. **Never delete or overwrite an assignment or an order.** Supersede, cancel, or expire. See the state machine in `docs/02_DATA_MODEL.md`. There are no `.delete()` calls on `Order` or `Assignment` in application code, ever.

4. **Orders are immutable after creation.** No view, form, or service may modify `Order.order_no`, `Order.order_date`, or `Order.generated_file`. A mistake is corrected by issuing a corrigendum order, not by editing.

5. **Fat services, thin views.** A view function longer than ~40 lines is a signal that logic belongs in a service.

6. **Use `select_related` / `prefetch_related` on every list view.** The dashboard must not N+1. If you write a template loop over a queryset that touches a foreign key, the queryset must have prefetched it.

---

## Security rules — non-negotiable

These are stated in full in `docs/03_SECURITY.md`. The ones most commonly violated:

1. **Deny by default.** Every view is protected. There is no `@login_required`-less view except the login page, the magic-link callback, and the health check. If you add a view, you add its permission test in the same commit.

2. **Never serve generated order files from `MEDIA_URL`.** Order `.docx` files contain faculty names, designations, and official signatures. They are served only through a permission-checked view that returns a `FileResponse`. `MEDIA_ROOT` for orders is outside the web root and never in `STATICFILES_DIRS`.

3. **Never use `fields = "__all__"`** in a `ModelForm` or `ModelAdmin`. List fields explicitly. Implicit field inclusion is how a user ends up able to set their own `role`.

4. **Never trust an ID from a URL or form.** Filter the queryset by what the requesting user is allowed to see, then look up inside it. `get_object_or_404(Order.objects.visible_to(request.user), pk=pk)` — not `Order.objects.get(pk=pk)` followed by a check.

5. **Role is never settable by a user.** `User.role` is editable only in the Django admin by a superuser, or by a management command. It appears in no public form's field list.

6. **Every uploaded file is validated** — extension, content-type sniff, size cap, and `.docx` only (never `.docm`; macros are rejected).

7. **No secrets in the repo.** All config through `django-environ`. `.env` is gitignored. `.env.example` is committed with placeholder values.

8. **Signatures.** The Principal's signature is a stored image stamped into every order. This is a rubber stamp, not a digital signature, and must never be described to the college as one. See `docs/10_SIGNATURE.md`.

9. **Demo mode is a safety feature, not a convenience.** When `DEMO_MODE=True`, every generated document carries the specimen line and real email sending is disabled. Do not add a code path that bypasses either. `seed_demo` must refuse to run when `DEMO_MODE=False`. Full spec in `docs/08_DEMO_DATA.md`.

---

## Definition of done

**During the demo sprint** a step is complete when:

- [ ] Code written and it actually runs — you have loaded the page or run the command yourself
- [ ] `python manage.py makemigrations --check --dry-run` reports no missing migrations
- [ ] Every new endpoint has `login_required`, and Principal-only endpoints have `principal_required`
- [ ] No `fields = "__all__"` and no `role` or `is_active` in any non-admin form
- [ ] Committed locally with a conventional message
- [ ] Docstrings on service functions stating the invariant they maintain

When you report a step complete, say what you deliberately skipped.

**After the demo**, the full bar applies: tests that fail if the feature breaks, permission tests per endpoint, `pytest -q` green across the whole suite, `ruff` clean, and `check --deploy` with no new warnings. See `docs/05_TESTING.md`.

---

## Things that will waste my time — don't do them

- Do not stub a function with `pass` or `TODO` and describe the phase as complete.
- Do not write a test that asserts `True`, asserts only a 200 status code, or mocks the thing it claims to test. (No tests are expected during the sprint — but a fake one is worse than none.)
- Do not "fix" a failing test by changing the assertion to match the buggy output. Fix the code, or tell me the test was wrong and why.
- Do not silently catch exceptions. If an order fails to generate, the transaction rolls back and the error surfaces.
- Do not generate seed or demo data that looks like real faculty records. Use obviously fake names (`Test Faculty One`) so demo data can never be mistaken for a real order.
- Do not refactor code outside the current phase's scope without asking.

---

## Git

Run every git command yourself — `git init`, `add`, `commit` after each working step, using Conventional Commits. **Local only: no GitHub, no remote, no push** until after the demo. Never ask the user to run a git command, and never ask them to move or rename a file.

## Conventions

- Commits: Conventional Commits (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `chore:`). One logical change per commit.
- Apps: `accounts`, `committees`, `assignments`, `orders`, `notifications`, `audit`, `core`.
- Naming: models singular (`Assignment`), services as verbs (`assign_committee`, `supersede_assignment`), test files `test_<module>.py`.
- Timezone: `Asia/Kolkata`. `USE_TZ = True`. Store UTC, display IST. Order dates are `DateField` (a date, not an instant) because an official order is dated by day.
- All user-facing strings through `gettext_lazy` — the college may want Gujarati later. Do not add translation files yet, just wrap the strings.
