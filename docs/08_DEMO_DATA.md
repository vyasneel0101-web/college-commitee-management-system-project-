# 08 — Demo Data and Demo Mode

Every open question from `07_OPEN_QUESTIONS.md` is answered here with a placeholder value so the build can proceed today. **All of these are provisional.** Each one is listed in §5 with the exact file or environment variable to change when the real value arrives.

This file supersedes the defaults in `07_OPEN_QUESTIONS.md`. Read that file for *why* each question matters; read this one for *what to build with now*.

---

## 1. Demo mode — build this in Phase 0

The demo has to look convincing enough that the Principal recognises it as their own process, while being impossible to mistake for the real system. Those two goals conflict, and the resolution is a single flag rather than fake-looking data.

```python
DEMO_MODE = env.bool("DEMO_MODE", default=False)
```

When `DEMO_MODE` is `True`:

1. **Every page shows a fixed banner:** "Demonstration system — data shown is fictional and orders issued here are not official." Persistent, not dismissable, present on print stylesheets too.
2. **Every generated order document gets a specimen line** inserted as the first paragraph: `SPECIMEN — DEMONSTRATION ONLY — NOT AN OFFICIAL ORDER`. Injected by the order service, not by the template, so it applies to every committee's template automatically and cannot be forgotten when a new template is uploaded.
3. **Email sending is disabled** (trivially true during the sprint, since email isn't built)
3b. **Every generated order carries the specimen line**, which also covers the fact that the signature is only an image stamp — the console backend is forced regardless of other settings. A demo must never send mail to a real faculty address.
4. **Seed commands are permitted.** When `DEMO_MODE` is `False`, `seed_demo` refuses to run and exits with an error.

When `DEMO_MODE` is `False`, none of the above appears and the seed command is unavailable.

**Required tests:**
- With `DEMO_MODE=True`, a generated order's text contains the specimen line
- With `DEMO_MODE=False`, it does not
- With `DEMO_MODE=True`, issuing an order queues zero real emails
- With `DEMO_MODE=False`, `seed_demo` raises `CommandError`
- The banner appears in the rendered HTML of the dashboard under demo mode and is absent otherwise

This is worth the hour it takes. A specimen order that escapes into circulation as a real one is the single most damaging thing this project could do to your credibility with the college.

---

## 2. Locked-in demo values

### Identity and auth

| Setting | Demo value |
|---|---|
| `ALLOWED_EMAIL_DOMAINS` | `gpbhuj-demo.local` |
| Auth method | **Sprint:** plain Django username/password, `demo1234` for every seeded user. Magic link and Google OAuth both deferred. |
| Email backend | Console in dev; `locmem` in tests |
| Institution name | Government Polytechnic, Bhuj |
| Institution short code | `GPB` |

Using a `.local` domain for the demo is deliberate — it cannot collide with any real address, so a stray email in development has nowhere to go.

### Order numbering

Format: `GPB/{COMMITTEE_CODE}/{ACADEMIC_YEAR}/{SEQ:03d}` → `GPB/TPU/2026-27/001`

Sequence key: per committee, per academic year.

Keep this in exactly one function, `orders/services.py::next_order_no()`. When the real format arrives it is a single-function change plus its tests.

### Academic years

| Label | Start | End | Current |
|---|---|---|---|
| `2025-26` | 2025-06-01 | 2026-05-31 | No |
| `2026-27` | 2026-06-01 | 2027-05-31 | **Yes** |

Two years, not one — so the demo can show real history and so the per-year sequence logic is exercised.

### Departments

| Code | Name |
|---|---|
| `CE` | Civil Engineering |
| `ME` | Mechanical Engineering |
| `EE` | Electrical Engineering |
| `CO` | Computer Engineering |
| `EC` | Electronics & Communication Engineering |
| `SH` | Science & Humanities |

### Designations

Confirmed as the demo set. Gujarat polytechnics predominantly use Lecturer and Head of Department, so the demo weights toward those:

`LECTURER` (Lecturer) · `HOD` (Head of Department) · `ASST_PROF` (Assistant Professor) · `ASSOC_PROF` (Associate Professor) · `PRINCIPAL` (Principal) · `OTHER` (Other)

### Government class

`CLASS_I` · `CLASS_II` · `CLASS_III` · `CLASS_IV`

Demo faculty are Class I (HOD, Principal) or Class II (Lecturer).

### Assignment roles

`CONVENER` and `MEMBER` only. Do not add more until the college confirms.

### Committees

Twelve, which is enough to make the workload screen and the directory look like a real institution rather than a test fixture.

| Code | Name | Multiple members |
|---|---|---|
| `TPU` | Training & Placement Unit | Yes |
| `EXAM` | Examination Committee | Yes |
| `ARC` | Anti-Ragging Committee | Yes |
| `WGC` | Women's Grievance Redressal Cell | Yes |
| `IQAC` | Internal Quality Assurance Cell | Yes |
| `LIB` | Library Committee | Yes |
| `PUR` | Purchase Committee | Yes |
| `DISC` | Discipline Committee | Yes |
| `SPT` | Sports & Games Committee | Yes |
| `CUL` | Cultural Committee | Yes |
| `ICT` | Website & IT Committee | Yes |
| `ALM` | Alumni Association Cell | No (convener only) |

`ALM` is set to convener-only on purpose, so the `allows_multiple_members` branch is exercised by the seed data rather than only by a unit test.

### Demo faculty

Fifteen faculty plus one Principal. Names are plausible Gujarati names but entirely fictional, and demo mode's banner and specimen line are what prevent confusion — not deliberately silly names, which would undercut the demo.

| Salutation | Name | Designation | Class | Dept | Email (`@gpbhuj-demo.local`) |
|---|---|---|---|---|---|
| Dr. | Rameshbhai Chauhan | Principal | I | — | `principal` |
| Shri | Mihir Patel | Lecturer | II | CO | `mihir.patel` |
| Smt. | Dipti Solanki | Head of Department | I | CO | `dipti.solanki` |
| Shri | Kiran Vasava | Lecturer | II | CO | `kiran.vasava` |
| Dr. | Nilesh Bhatt | Head of Department | I | ME | `nilesh.bhatt` |
| Shri | Jayesh Rathod | Lecturer | II | ME | `jayesh.rathod` |
| Smt. | Hetal Mistry | Lecturer | II | ME | `hetal.mistry` |
| Shri | Bhavesh Gohil | Head of Department | I | CE | `bhavesh.gohil` |
| Smt. | Rekha Damor | Lecturer | II | CE | `rekha.damor` |
| Shri | Ashok Parmar | Lecturer | II | CE | `ashok.parmar` |
| Dr. | Sanjay Trivedi | Head of Department | I | EE | `sanjay.trivedi` |
| Smt. | Pooja Joshi | Lecturer | II | EE | `pooja.joshi` |
| Shri | Ketan Makwana | Head of Department | I | EC | `ketan.makwana` |
| Smt. | Alka Desai | Lecturer | II | EC | `alka.desai` |
| Dr. | Vipul Shah | Head of Department | I | SH | `vipul.shah` |
| Smt. | Meera Pandya | Lecturer | II | SH | `meera.pandya` |

Joining dates spread across 2008–2023. Mobile numbers: use the reserved-for-fiction range, `+919000000001` upward, never a number that could belong to a real person.

**Mihir Patel is deliberately given six active committees** — your original example, and it makes the workload screen immediately legible to your Principal.

---

## 3. Seed command

`python manage.py seed_demo` — idempotent, safe to re-run, refuses to run unless `DEMO_MODE=True`.

It creates, in order:

1. The two academic years, with `2026-27` current
2. The six departments
3. The Principal and fifteen faculty
4. The twelve committees
5. Both order templates from `templates/demo/` (see §4), attached to `TPU` and `EXAM`; the TPU template as a fallback for the other ten
6. `templates/demo/demo_principal_signature.png` attached to the Principal's `signature_image`, so generated orders carry a signature from the first run
7. **Historical assignments in `2025-26`**, then expired — so history is not empty
8. **Current assignments in `2026-27`**, issued through the real `issue_assignment_order` service, not by direct object creation

The last point matters more than it looks. Seeding through the service means the seed data itself is a test of the order pipeline: order numbers get generated, documents get rendered, supersessions get applied. If `seed_demo` runs clean, a large part of your system demonstrably works. Bypassing the service with `Assignment.objects.create()` would produce assignments with no orders, which violates BR-1 and would give you a demo whose download buttons all 404.

Include at least one **hand-over chain** in the seed: `TPU` convener held by Kiran Vasava in 2025-26, superseded by Mihir Patel in 2026-27. And one **cancelled order with a corrigendum**, so the register shows that flow.

Add `seed_demo --reset` to flush and rebuild, also gated on `DEMO_MODE`.

---

## 4. Demo order templates

Two `.docx` templates are provided alongside these docs. Commit them to `templates/demo/` in the repo and also copy them to `tests/fixtures/` for the Phase 5 tests.

**`order_template_TPU.docx`** — formal office order. Times New Roman, letterhead, subject line, a details table, responsibilities paragraph, signature block, copy-forwarded list.

**`order_template_EXAM.docx`** — circular format. Calibri, a member table with Sr./Name/Designation/Role columns, remarks field. Deliberately a different layout from TPU.

Both contain all ten required placeholders plus `{{ principal_signature }}` in the signature block. TPU additionally uses `{{ effective_date }}`; EXAM additionally uses `{{ remarks }}`. Between them they cover the required set and three optional ones, so placeholder validation gets a real workout.

**`demo_principal_signature.png`** is supplied alongside them — a transparent-background signature image for the demo Principal. Replace it with the real Principal's signature when you have one; it uploads through the profile form with no code change.

These are modelled on the general shape of Gujarat technical-education office orders, but they are **guesses at your college's format**. Their job is to make Phase 5 buildable and testable, and to give you something to put in front of your Principal. Expect the real ones to differ in wording, letterhead, and the copy-forwarded list. Nothing about the code needs to change when they do — you upload the real file through the committee template screen and it takes effect for the next order. That is precisely why templates are database records with versions rather than files baked into the repo.

**Optional but recommended for the demo:** replace the text letterhead with your college's actual letterhead image. Templates are static `.docx` files, so pasting the real header into them requires no code at all, and it makes the demo dramatically more persuasive.

---

## 5. Swap-back checklist

When the college gives you the real information, this is the complete list of what changes. Work top to bottom.

| # | Real value received | What to change | Effort |
|---|---|---|---|
| 1 | Actual email domain | `ALLOWED_EMAIL_DOMAINS` env var | 1 minute |
| 2 | Confirmation of Google Workspace | Add allauth Google provider + `hd` restriction in settings | ~1 hour |
| 3 | Real order templates | Upload via the committee template screen. **No code change.** Old orders keep their original files (BR-7). | Per committee, minutes |
| 4 | Real order-number format | `orders/services.py::next_order_no()` + its tests | ~30 minutes |
| 5 | College-wide instead of per-committee numbering | `OrderSequence.unique_together` + a migration + `next_order_no()` | ~1 hour |
| 6 | Real designation list | `Designation` TextChoices + migration | ~20 minutes |
| 7 | Real class/pay-band terminology | `GovtClass` TextChoices + migration | ~20 minutes |
| 8 | Additional committee roles | `AssignmentRole` TextChoices + migration. Re-check the `uniq_active_convener` constraint — if they use Chairperson *and* Convener, that constraint may need to cover both. | ~1 hour |
| 9 | Real departments and committees | Create through the Principal's UI, or a one-off management command | Data entry |
| 10 | Real faculty list | Create through the Principal's UI. If it's a long list, add a CSV import command — the creation service is already designed to be callable from one. | Data entry, or ~2 hours for the importer |
| 11 | Multi-member single orders (Q9) | `{{ member_list }}` loop in the template + multi-select in the assign form + a service change | ~4 hours |
| 12 | SMTP credentials | Env vars, and turn `DEMO_MODE` off | 15 minutes |
| 13 | Going live | `DEMO_MODE=False`, seed data flushed, real Principal account created via `create_principal` | 30 minutes |

Item 8 is the only one with a real chance of forcing a rethink, which is why Q5 is worth asking early even though the demo doesn't need it.

---

## 6. Getting real data out of your college

The demo is your leverage. Some things that help:

**Show, then ask.** Walk the Principal through the assign flow live, generate a specimen order in front of them, and let them download it. Then ask for the real templates. Asking for three Word files after they've seen their own process working is a much easier conversation than asking cold.

**Ask for artefacts, not answers.** "Can you send me three past orders?" gets you a usable reply. "What's your order numbering convention?" gets you a vague one. The real orders answer Q3, Q4, Q6, Q7, Q9, Q10, and Q11 all at once — everything from the numbering format to whether there's a seal, and how the designation is actually written.

**Let the specimen order be wrong.** The single fastest way to get a correct format is to show someone an almost-correct one. A Principal who sees "Shri Mihir Patel, Lecturer" where their orders say something else will tell you immediately, and precisely.

**Ask who else must approve it.** A government institution may need the Head of Department, the DTE office, or an IT/data policy sign-off before this handles real staff records. Better to know at demo stage than after deployment.

---

## 7. One line to add to `CLAUDE.md`

Append this under the security rules:

> **Demo mode is a safety feature, not a convenience.** When `DEMO_MODE=True`, every generated document carries the specimen line and real email sending is disabled. Do not add a code path that bypasses either. `seed_demo` must refuse to run when `DEMO_MODE=False`.
