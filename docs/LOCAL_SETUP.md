# Running CAMS locally on Windows

Open http://127.0.0.1:8000/login/ while the server is running.

Double-click `start-local.cmd` in the project folder to start it again.
Keep its terminal open. Press Ctrl+C to stop the server. If port 8000 is
already in use, use the existing server or stop it before starting another.

Alternatively, open PowerShell in this folder:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

No virtual-environment activation or global Python command is required.

## Demo accounts

| Account | Email | Password |
|---|---|---|
| Principal | principal@gpbhuj-demo.local | demo1234 |
| Test Faculty 01 | faculty01@gpbhuj-demo.local | demo1234 |
| Test Faculty 03 | faculty03@gpbhuj-demo.local | demo1234 |

The login page has buttons that fill these credentials. These are local demo
credentials only. DEMO_MODE remains enabled; generated documents are specimens
and real email delivery is disabled. The Principal account is a business-role
account, not a Django superuser.

## What runs

Python 3.12.14 and Django 5.2.17 serve both the backend and HTML frontend in
one process. There is no Node package manifest or separate frontend build.
Tailwind and Google Fonts load from CDNs, so the intended styling needs internet.

| Folder | Purpose |
|---|---|
| config | URLs, development/test settings, WSGI and ASGI entry points |
| accounts | Email/password login, faculty, departments, profile and permissions |
| committees | Committee records and management pages |
| assignments | Current and past memberships, directory and status transitions |
| orders | Preview, numbering, Word rendering, protected downloads, removal and cancellation |
| notifications | In-app notices and unread counts |
| audit | Append-only action records and admin registration |
| core | Academic years, shared record protections, landing page and demo seeding |
| templates | HTML screens, inline JavaScript/CSS, demo Word template and signature |
| tests | Automated database, service, permission, form and document tests |
| docs | Specifications, reference images and implementation/deployment notes |

Requests pass through Django authentication and role checks, then forms and
transactional services. Services update SQLite records and render Word orders.
The saved order file is served through an authenticated download view. Files in
`media` are not publicly served.

## Local environment and database

The ignored `.env` contains a generated secret key, localhost hosts/origins,
development settings, Asia/Kolkata timezone and `DATABASE_URL=sqlite:///db.sqlite3`.
SQLite needs no separate server. Its WAL mode and IMMEDIATE transactions are
configured in base settings. The custom user model is `accounts.User`.

The initial demo has 16 users, 6 departments, 13 committees, 30 orders and
32 assignments (25 active, 2 superseded, 5 expired). Names are explicitly fake.
Keep `db.sqlite3` and `media` together when preserving this demo's records.
Do not run `seed_demo --reset` unless intentionally discarding the demo database.

Installed dependencies are exactly those already declared in
`requirements.txt` and `requirements-dev.txt`, plus their required dependencies.
The virtual environment uses the app-bundled Python runtime; if that runtime is
removed, recreate `.venv` with an installed Python 3.12.

## Fresh setup on another machine

With Python 3.12 installed:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Replace the placeholder SECRET_KEY in `.env` with a generated random value,
then run:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

## Verification on 19 October 2026

- Django system check: no issues.
- Migration consistency: no model changes missing migrations.
- All migrations applied successfully to the new SQLite database.
- Existing automated suite: 224 tests passed, including permissions, assignment
  transitions, order documents, rollback handling and notifications.
- `pip check`: no broken requirements.
- Python sources compiled successfully; 127 Django static files collected.
- Demo seeding exercised the real order services and generated 30 Word files.
- SQLite integrity and foreign-key checks passed; all HTML templates compiled.
- All 30 stored Word archives validated and contained the specimen marker.
- Faculty and Principal browser login, dashboard, assignment preview and styled
  workload page verified. Main pages and authenticated download passed HTTP checks.

Run checks again with:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pytest -q
```

## Limits and documentation differences

This setup is for localhost demonstration. Production deployment, PostgreSQL,
real email, magic links, background workers, offline CSS and PDF conversion were
deliberately not added. No dependency or major feature was added.

Some older specifications and README statements are stale: tests and in-app
notifications now exist; workload and faculty management are Principal-only;
orders use one shared template; roles include Presiding Officer, Nodal Officer
and External Member. DEBT.md claims an `/audit/` UI exists, but the current URL
configuration does not expose it. Audit records still exist in the database.
Those differences were recorded rather than changing the application's scope.
