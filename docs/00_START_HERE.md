# 00 — START HERE

**Claude Code: read this file first, then `CLAUDE.md`, then `02_DATA_MODEL.md`. Skim the rest so you know what exists; don't act on it yet.**

---

## The situation

This is the real CAMS project — not a throwaway. But there is a demo to a college Principal and teachers in roughly two hours, so today's session is a **speed sprint on real foundations**.

That means: real models, real field names, real services layer, real constraints. And temporarily: SQLite instead of PostgreSQL, no test suite, no magic-link auth, Tailwind from a CDN.

Everything cut today is listed in §5 as explicit debt with a repayment order. The point of building on real foundations is that tomorrow you add Postgres and tests rather than starting over.

## Rules for this session

1. **You handle all file placement.** The user hands you a folder of documents. File them yourself — root, `docs/`, `templates/demo/`, `tests/fixtures/`. Never ask the user to move, copy, or rename anything.
2. **You handle all git.** `git init` locally, commit after every working step with conventional messages. **No GitHub, no remote, no push** — that comes after the demo. Never ask the user to run a git command.
3. **Make decisions yourself.** Do not ask the user to choose between options. Pick, state what you picked in one line, move on. Time is the binding constraint.
4. **This file overrides `CLAUDE.md` where they conflict**, for today only. Specifically: SQLite, no tests, no `django-allauth`, no `django-unfold`, no `django-tailwind`, no `django-q2`, no Docker. Everything else in `CLAUDE.md` still applies — especially the services layer, explicit form field lists, protected file downloads, and never deleting orders or assignments.
5. **Note the debt in your first commit message.** SQLite and the missing test suite are temporary and must not be forgotten.
6. **Stop at the end of each step** and show the user what works. Do not run ahead.

## Expected file layout

```
CLAUDE.md                     root — development rules
docs/00 … 10                  specification
templates/demo/               order templates + signature image
tests/fixtures/               same templates, for tests added later
.env  .env.example            config
```

---

## The five steps

Work through these in order. Roughly 100 minutes total. Stop after each and report.

### Step 1 — Project skeleton and landing page (15 min)

- Django 5 project `config`, settings split `base.py` / `dev.py`, reading `DATABASE_URL`, `DEBUG`, `DEMO_MODE`, `INSTITUTION_NAME`, `INSTITUTION_CODE` from `.env` via `django-environ`
- Apps: `accounts`, `committees`, `assignments`, `orders`, `core`
- **Custom `User` model in `accounts`, with `AUTH_USER_MODEL = "accounts.User"` set in settings BEFORE the first `makemigrations`.** This is the one irreversible mistake available today. Verify it before migrating.
- `requirements.txt`: `django`, `django-environ`, `docxtpl`, `python-docx`, `Pillow`
- `.gitignore`, and `.env` created from `.env.example` with a generated `SECRET_KEY`
- `base.html` with Tailwind from CDN, institution header, nav, and the demo banner from `08_DEMO_DATA.md` §1
- A real landing page (`index.html`) with a Sign in button
- `migrate`, then `runserver`

Follow `06_UI_DIRECTION.md` for the palette even at this stage — it costs nothing to pick a restrained one now, and retrofitting is slower.

### Step 2 — Models, admin, seed data (20 min)

- All models per `02_DATA_MODEL.md`, with the constraints. SQLite supports partial unique indexes, so `uniq_active_assignment` and `uniq_active_convener` both work — keep them.
- Custom managers: `Assignment.objects.active()`, `.for_faculty()`, `.directory()`, `Order.objects.visible_to()`, `User.objects.faculty_with_counts()`
- Register everything in the plain Django admin with **explicit `fields` lists**, never `__all__`
- `seed_demo` management command per `08_DEMO_DATA.md` §3, including attaching `demo_principal_signature.png` to the Principal
- Run it and report the counts

### Step 3 — Auth and read-only screens (25 min)

- Plain Django username/password login at `/login/`. Password `demo1234` for all seeded users. **Magic-link auth is deferred** — see the debt list.
- A `principal_required` decorator returning 403, and `login_required` on every other view
- `/dashboard/` — my active committees, count badge, past committees with status pills
- `/directory/` — all active assignments, plain GET filter box
- `/workload/` — all faculty with active committee counts, sorted descending
- `/profile/` — own details, mobile editable only. `role` and `is_active` must not appear in the form's field list.
- `select_related` on every list view

### Step 4 — Assign flow and order generation (25 min)

The core workflow. Principal only. All logic in `assignments/services.py` and `orders/services.py`, each wrapped in `transaction.atomic()`.

- `/assign/` — committee, faculty (a searchable `<select>` or a small JS filter box; no HTMX), role, order date defaulting to today
- Before submit, show a confirmation line naming who will be superseded, if anyone
- On submit, in one transaction: generate the order number → build the docxtpl context → stamp the signature image → render the committee's template → save the file → create the `Order` → create the `Assignment` → supersede the previous holder per BR-3
- Signature handling per `10_SIGNATURE.md`
- `/orders/` — the register, Principal only
- `/orders/<pk>/download/` — login required, resolved through `Order.objects.visible_to(user)`, returning `FileResponse(as_attachment=True)`. Never served from `MEDIA_URL`.
- Success page showing the order number and a download link

### Step 5 — Polish (15 min)

- Visual pass following `06_UI_DIRECTION.md`. Tables not cards, sentence case, real empty-state copy, tabular figures on count columns, visible focus rings, works at 375px.
- Print stylesheet for `/directory/` and the order pages
- Write `DEBT.md` from §5 below
- No new features

Then hand back to the user for the walkthrough in §4.

---

## 4. Demo walkthrough — give this to the user at the end

Five minutes, in this order. They should click through it once themselves before presenting.

1. **Log in as a faculty member**, not the Principal. Dashboard: "today a faculty member only knows their own committees." Then the directory: "this is the part that doesn't exist on paper."
2. **Workload screen.** "Mihir sir is holding six. Nobody could see that before."
3. **Log in as Principal, assign a committee.** Pick TPU, search for a faculty member, note the line warning who will be superseded, issue it.
4. **Download the order, open it in Word.** This is the moment. Say nothing while they read.
5. **Return to the previous holder's dashboard.** The committee has moved to their past list, and their old order still downloads unchanged.
6. **Then ask for the real templates.** "This format is my guess — send me three real orders and the next version prints exactly like yours."

**If time runs out, cut in this order:** polish → order register → workload → directory. **Never cut steps 3 and 4.** That sequence is the entire pitch.

---

## 5. Debt taken on today

Write this to `DEBT.md` at the end of Step 5. Repay in this order after the demo.

| # | Debt | Why it matters | Fix |
|---|---|---|---|
| 1 | SQLite instead of PostgreSQL | `select_for_update` silently does nothing, so order numbering isn't race-safe. Fine with one Principal clicking one button; not fine in production. | Change `DATABASE_URL`, fresh `migrate`. See `09_LOCAL_POSTGRES.md`. ~1 hour |
| 2 | No test suite | Nothing prevents a regression in the supersession logic, which is what protects order history | `05_TESTING.md` §4 and §5 first — the assignment engine and order numbering. ~1 day |
| 3 | Password auth instead of magic links | Shared demo passwords, no domain restriction | `03_SECURITY.md` §1. ~0.5 day |
| 4 | No permission matrix test | A new endpoint can ship unprotected and nobody notices | `05_TESTING.md` §3 |
| 5 | Signature is a stored image | A rubber stamp, not a signature — anyone who reaches the file can produce a signed-looking order | `10_SIGNATURE.md`. Needs a policy decision from the college first. |
| 6 | No audit log UI | Actions recorded but not viewable | `01_PROJECT_SPEC.md` §6 |
| 7 | No email notifications | Faculty aren't told | Phase 7 in `04_BUILD_PHASES.md` |
| 8 | No order cancellation / corrigendum | A mistaken order can't be corrected properly (BR-6) | Phase 5 in `04_BUILD_PHASES.md` |
| 9 | Tailwind via CDN | Fine for a demo; slow and unversioned in production | `django-tailwind`. ~1 hour |
| 10 | Templates are guesses | Generated orders won't match the college's real format | Upload the real files through the committee template screen — no code change |

Items 1, 2 and 3 must be repaid before this touches a single real faculty record.

`04_BUILD_PHASES.md` holds the full nine-phase plan that this sprint short-circuits. After the demo, that document becomes the roadmap again, and today's output is a partial but real version of its Phases 0 through 6.
