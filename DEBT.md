# DEBT — what the demo sprint borrowed

Every item here was a deliberate choice to reach a working demonstration in one
sitting, not an oversight. Each one is listed with why it matters and what
repaying it costs. Repay in the order given.

**Items 1, 2 and 3 must be repaid before this system holds a single real
faculty record.**

| # | Debt | Why it matters | Fix | Effort |
|---|---|---|---|---|
| 1 | SQLite instead of PostgreSQL 18 | `select_for_update` is silently ignored on SQLite, so order numbering is not race-safe. Fine with one Principal clicking one button; not fine in production. | Change `DATABASE_URL`, fresh `migrate`. See `docs/09_LOCAL_POSTGRES.md`. | ~1 hour |
| 2 | No test suite | Nothing prevents a regression in the supersession logic, which is what protects order history. | `docs/05_TESTING.md` §4 and §5 first — the assignment engine and order numbering. | ~1 day |
| 3 | Password auth instead of magic links | Shared demo passwords, no domain restriction. | `docs/03_SECURITY.md` §1. | ~0.5 day |
| 4 | No permission matrix test | A new endpoint can ship unprotected and nobody notices. | `docs/05_TESTING.md` §3. | ~0.5 day |
| 5 | Signature is a stored image | A rubber stamp, not a signature — anyone who reaches the file can produce a signed-looking order. | `docs/10_SIGNATURE.md`. Needs a policy decision from the college first. | Policy, then 1–3 days |
| 7 | No email notifications | Faculty are not told when an order concerns them. | Phase 7 in `docs/04_BUILD_PHASES.md`. | ~1 day |
| 9 | Tailwind via CDN | Fine for a demo; slow, unversioned, and needs the network in production. | `django-tailwind`. | ~1 hour |
| 10 | Templates are guesses | Generated orders will not match the college's real format. | Upload the real files through the committee template screen — no code change. | Data entry |

## Taken on during the sprint, beyond the original list

| # | Debt | Why it matters | Fix |
|---|---|---|---|
| 11 | Runs on Python 3.14, not 3.12 | 3.12 was not installed on the build machine. Django 5.2 supports 3.14, so nothing is broken, but the stated stack and the deployed stack differ. | Agree one version and pin it in `requirements.txt` and the deployment notes. |
| 12 | No `prod.py` settings module | `config/settings/dev.py` is the only environment. `check --deploy` cannot be run meaningfully, and `wsgi.py` defaults to dev settings. | Add `config/settings/prod.py` per `docs/03_SECURITY.md` §6. |
| 14 | No `/healthz` endpoint | Nothing for a host to poll to know the app is alive. | Phase 0 deliverable; a few lines. |
| 15 | Argon2 password hasher not configured | Django's default PBKDF2 is acceptable but weaker than the specified Argon2. | `pip install django[argon2]` and set `PASSWORD_HASHERS`. |
| 16 | Admin shows a 500 page when a second academic year is marked current | The database constraint does the right thing and refuses the write, but the user sees a crash instead of a readable message. | Validate in `AcademicYearAdmin.clean()` or flip the other rows in a service. |
| 17 | Order files can be orphaned on a rolled-back outer transaction | `issue_assignment_order` deletes its file if the service itself fails, but a rollback *after* it returns leaves the file on disk. The database stays correct; only disk space is wasted. | Move file writes to `transaction.on_commit`, or add a periodic sweep for files no order references. |
| 18 | Google Fonts loaded from a CDN | The interface depends on a third-party request, and falls back to system fonts offline. | Serve the font files locally alongside the Tailwind build (item 9). |

## Paid off

| # | Debt | Repaid by |
|---|---|---|
| 6 | No audit log UI | `/audit/`, Principal only, filterable and paginated, read-only |
| 8 | No order cancellation / corrigendum | `cancel_order` issues a corrigendum, voids what the order created and restores what it displaced; `issue_relinquishment_order` covers BR-4 |
| 13 | No faculty or committee management screens | Faculty add/correct/deactivate and committee add/edit plus template upload, all Principal-only |

An item is struck off only when its fix is committed and verified. Everything
above was checked end to end: 33 checks for the order lifecycle and 40 for the
management screens, each run inside a transaction that was rolled back.

## Still the priority

Debts 1, 2 and 3 — PostgreSQL, a test suite and real authentication — are
unchanged and still gate real records. Today's work added features; it did not
make the system safer to put staff data into.
