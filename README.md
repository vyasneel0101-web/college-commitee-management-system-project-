# CAMS — Committee Assignment Management System

Government Polytechnic, Bhuj.

A Django application that digitises the assignment of institutional committees to faculty. The Principal assigns a committee, the system generates a numbered official order from that committee's Word template, emails the faculty member, and keeps a permanent, tamper-resistant history. Faculty can see their own responsibilities and the full institution-wide picture — which the paper process never allowed.

## Status

**Demo sprint.** Building the essential slice in about 100 minutes for a demonstration to the college, on real foundations — real models, real field names, real services layer, real constraints.

Temporary: SQLite, plain password auth, Tailwind from CDN, no test suite. Every shortcut is listed as repayable debt in `docs/00_START_HERE.md` §5.

**Claude Code: read `docs/00_START_HERE.md` first.** It defines the five steps and overrides `CLAUDE.md` where they conflict.

`docs/04_BUILD_PHASES.md` is the post-demo roadmap.

## Documentation

Read in this order:

| File | Contents |
|---|---|
| `CLAUDE.md` | Standing rules for all development. Loaded automatically by Claude Code. |
| `docs/00_START_HERE.md` | **Read first.** The five sprint steps, walkthrough, and debt list |
| `docs/01_PROJECT_SPEC.md` | Actors, features, business rules BR-1 to BR-10 |
| `docs/02_DATA_MODEL.md` | Every model, field, constraint, and the assignment state machine |
| `docs/03_SECURITY.md` | Auth design, endpoint permission matrix, threat checklist T1–T20 |
| `docs/04_BUILD_PHASES.md` | The build plan, with exit criteria per phase |
| `docs/05_TESTING.md` | Required test cases and coverage gates |
| `docs/06_UI_DIRECTION.md` | Visual direction and interface copy rules |
| `docs/07_OPEN_QUESTIONS.md` | What still needs confirming with the college |
| `docs/08_DEMO_DATA.md` | Demo values, seed data, and demo-mode safety |
| `docs/09_LOCAL_POSTGRES.md` | Local PostgreSQL 18 setup (after the demo) |
| `docs/10_SIGNATURE.md` | How the Principal's signature works, and the real options later |

## Local setup

**1. Database**

SQLite, no setup required. PostgreSQL comes after the demo — see `docs/09_LOCAL_POSTGRES.md`.

**2. Environment**

```bash
cp .env.example .env
```

Generate a secret key and paste it into `.env`:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

**3. Python environment**

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
```

Dependencies are installed during Phase 0.

## Repository layout

```
CLAUDE.md              Development rules, loaded by Claude Code
docs/                  Specification
templates/demo/        Placeholder Word order templates + demo signature image
tests/fixtures/        The same templates, used by the Phase 5 tests
.env.example           Every environment variable, documented
```

## Demo mode

`DEMO_MODE=True` puts a `SPECIMEN — NOT AN OFFICIAL ORDER` line on every generated document, shows a permanent banner in the interface, and disables real email sending. It is on by default in `.env.example` and must stay on until the system holds real records.

The order templates in `templates/demo/` are placeholders written to resemble Gujarat technical-education office orders. They are not the college's real formats. Replace them through the committee template screen when the real files arrive — no code change is needed, and previously issued orders keep their original documents.

`demo_principal_signature.png` is a stand-in signature, stamped into every generated order. It is a rubber stamp, not a digital signature, and must never be presented as one. See `docs/10_SIGNATURE.md`.

## Quality gates

During the sprint, each step must pass:

```bash
python manage.py makemigrations --check --dry-run
python manage.py runserver     # and the page actually loads
```

After the demo, the full bar returns:

```bash
ruff check . && ruff format --check .
python manage.py check --deploy --settings=config.settings.prod
pytest -q
pytest --cov --cov-report=term-missing --cov-fail-under=85
```

A phase is not complete if an earlier phase's tests are failing.
