# UI save point and approved design

## First Save Point

- User-visible name: **First Save Point**.
- Local annotated Git tag: `first-save-point`.
- Commit: `b6789b367f6b70a95a4b7cd7c619bf9bc5aa5f10`.
- Captured before any Option A changes, with a clean working tree.
- This preserves tracked source code, not the ignored database, `.env`, media,
  virtual environment or runtime logs. Never reset those to change the UI.

The user approved **Option A: Institutional Workspace**. If the college's
reviewer does not like it, the requested alternative is **Option B: Modern
Official Register**. Wait for that instruction; do not automatically switch.
Preserve this tag when making later commits. For a future switch, use it as a
source reference and change frontend files only, preserving later unrelated work.
Do not use a destructive repository-wide reset.

## Implemented presentation

- Navy desktop sidebar with the existing role-based links, clear active sections
  on nested pages, and account tools in the header.
- Below 1200px, an accessible menu drawer: Escape/backdrop/close control, focus
  containment and focus return. Without JavaScript the navigation stays visible.
- Principal management shortcuts and Faculty personal shortcuts use existing
  routes and template context. Counts refer only to the signed-in user's actual
  committees; no institution-wide statistics are invented or newly queried.
- Login presentation, readable tables, aligned workload entries, labelled mobile
  rows, consistent forms, distinct destructive-action styling and order progress.
- Current committees appear before the longer notification list on the dashboard.
- Assignment row labels stay associated after adding or reordering rows.
- Existing demo notices, specimen wording, confirmations, error messages,
  download controls and print behaviour remain in place.
- Django Admin receives restrained branding and colour overrides only. Its
  theme switch, controls, model permissions and navigation remain Django's.

`templates/ui/` holds shared styles, navigation, icons, the order progress
indicator and presentation JavaScript. Styles are included through Django
templates so no settings change, new build tool or dependency is required.
Tailwind and fonts still use the existing CDNs.

## Boundaries

No application Python, models, migrations, services, forms, URLs, settings,
authentication, permissions, dependencies or generated Word templates changed.
HTML form actions, HTTP methods, input names/values and formset management
fields are retained. The small assignment JavaScript adjustment keeps labels
and the mobile cell wrapper correct during the existing reorder operation.

## Verification

- Existing 224-test regression suite passed.
- Five additional UI tests cover Faculty navigation privacy, selected parent
  sections on management forms, and unique labelled assignment inputs with the
  existing CSRF and formset fields.
- Complete combined run: **229 passed**.
- Django system check passed; migration check reports no changes.
- Compared form methods, actions, field attributes and option values on 16
  pages against First Save Point; all matched.
- Admin index, user list and change form rendered successfully using a temporary
  user inside a transaction that was rolled back.
- Browser checks: Faculty/Principal sign-in, desktop dashboard and faculty form,
  mobile menu focus and Escape return, adding/reordering assignment rows,
  preview and return-to-edit. Browser console showed no errors during checks.
- Responsive checks at 375px, 1024px and 1440px. At 375px, checked dashboard,
  assignment, orders, faculty list/create, committees, profile, directory and
  workload without horizontal overflow.
- Print CSS retains black-and-white tables, hidden navigation and expansion of
  past sections. Physical printing was not performed.

One initial test run hit a Windows permission error in the shared pytest temp
directory. Re-running with a new isolated `--basetemp` under `.venv` resolved it;
no application code or assertions were changed to hide the error.

Full check command (use a fresh temporary directory name for a later run):

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.venv/ui-test-temp-next
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Production hardening, offline assets, new analytics, API changes and database
changes are outside this UI task. Automated checks reduce regression risk;
college acceptance testing remains a separate review.
