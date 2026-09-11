# 01 — Project Specification

## 1. Problem

Government Polytechnic Bhuj runs many institutional committees (TPU/admissions cell, exam committee, anti-ragging committee, etc.). Each committee is a standing responsibility assigned by the Principal to one or more faculty members.

Today the process is entirely manual:

1. The Principal decides who gets which committee.
2. A paper order is typed in a committee-specific format, the faculty's name is filled in, and it is printed.
3. The printed order is delivered to the faculty, and an email is sent.

The failures this causes:

- **No institutional visibility.** A faculty member knows only their own committees. Nobody except the Principal's office knows the full picture.
- **No workload visibility.** There is no way to see that one faculty holds six committees while another holds none.
- **No reliable history.** When a committee is handed to a new faculty, the previous order is a piece of paper in a file. Reconstructing "who held TPU in 2023–24" means searching physical records.
- **Clerical bottleneck.** The college is short on clerical staff, so retyping and formatting orders consumes the Principal's own time.

## 2. What the system does

A Django web application that:

- Authenticates faculty and the Principal using their existing college email addresses (no new passwords to manage).
- Lets any faculty member see their own committee assignments and the full institution-wide assignment list.
- Lets the Principal assign a committee to a faculty member, which **automatically generates a formatted, numbered official order document** from a committee-specific Word template.
- Preserves complete history: when an assignment is replaced, the old record is superseded, never deleted.
- Emails the faculty member with the order attached when an assignment is made.
- Shows a workload view: how many active committees each faculty member holds.

## 3. Actors

| Actor | Role value | Capabilities |
|---|---|---|
| Faculty | `FACULTY` | View own assignments and own order history. View institution-wide directory of active assignments (read-only). Download own order documents. Edit own mobile number only. |
| Principal | `PRINCIPAL` | Everything Faculty can do, plus: create/deactivate faculty records, create/edit committees and their templates, assign and relinquish committees, issue and cancel orders, view all order history, view audit log. |
| Superuser | `is_superuser` | Django admin access. Technical operator only (you). Can change a user's role. Not a business role. |

There is exactly one active Principal at a time. The role is on the user record, so when the Principal changes, the outgoing Principal's role is changed to `FACULTY` and the incoming one's to `PRINCIPAL` — the assignment history stays intact because orders record `issued_by` as a foreign key.

**Design note:** a Principal is also a faculty member and may hold committees. Do not model Principal as a separate entity.

## 4. Core domain concepts

- **Department** — an academic department (Mechanical, Computer, Electrical, …). Faculty belong to one.
- **Committee** — a standing institutional responsibility with a name, a short code, and its own Word order template.
- **Academic Year** — e.g. `2026-27`. Assignments and orders belong to one. Exactly one is marked current.
- **Assignment** — a time-bound record that a faculty member holds a role in a committee, created by an order. This is the central concept. An assignment is **never edited or deleted**; it is superseded, relinquished, or expired.
- **Order** — the official, numbered, dated document that creates one or more assignments. Immutable. Stored permanently as a generated `.docx` file.
- **Audit log entry** — an append-only record of who did what, when.

## 5. Business rules

These are requirements, not suggestions. Each one has a corresponding required test in `docs/05_TESTING.md`.

**BR-1 — Assignments are created only by orders.**
There is no way to create an assignment without an accompanying order. The order is what makes it official.

**BR-2 — One active holder per (committee, role) is the default, but committees may have multiple members.**
A committee has one `CONVENER` and any number of `MEMBER`s. Assigning a new convener to a committee that already has an active convener automatically supersedes the existing one. Adding a member does not affect existing members.

**BR-3 — Supersession is automatic and atomic.**
When a new assignment supersedes an old one, in a single transaction: the new `Assignment` is created with status `ACTIVE`; the old one gets `status = SUPERSEDED`, `end_date` = the new order's date, and `superseded_by` = the new assignment. If any step fails, none of it happens.

**BR-4 — An assignment can end without a replacement.**
The Principal can relinquish a faculty member from a committee with nobody taking over. Status becomes `RELINQUISHED`, and this too requires an order.

**BR-5 — Order numbers are unique, sequential per academic year, and never reused.**
Format: `GPB/{COMMITTEE_CODE}/{ACADEMIC_YEAR}/{SEQ:03d}` — e.g. `GPB/TPU/2026-27/007`. Generated atomically under a row lock. A cancelled order's number is **not** freed for reuse.

**BR-6 — Orders are immutable.**
Once created, `order_no`, `order_date`, `generated_file`, and the assignment links cannot change. A mistake is corrected by issuing a new order that cancels the erroneous one (a corrigendum). Cancelling an order also reverts the assignments it created: their status becomes `CANCELLED`, and any assignment it superseded is restored to `ACTIVE`.

**BR-7 — Generated documents are stored, not regenerated.**
The `.docx` produced at order creation is saved and served forever. If a committee's template is later changed, previously issued orders must still render exactly as originally issued. Never regenerate an order document on demand.

**BR-8 — A faculty member cannot hold the same role in the same committee twice concurrently.**
Enforced by a database constraint on `(faculty, committee, role)` where `status = ACTIVE`.

**BR-9 — Deactivated faculty keep their history.**
A faculty member who leaves the college is marked inactive (cannot log in) but their assignment and order history remains queryable. Their active assignments must be explicitly relinquished by order — deactivation does not silently end them, but the system must warn the Principal if a faculty member with active assignments is being deactivated.

**BR-10 — Only college-domain email addresses can authenticate.**
See `docs/03_SECURITY.md`.

## 6. Screens

### Faculty
- **My Dashboard** — my active committees (name, my role, since when, download order), count badge, and my past committees collapsed below.
- **Institution Directory** — searchable, filterable table of all active assignments across the college: committee, holder, role, department, since. Read-only. This is the screen that solves the visibility problem.
- **Faculty Workload** — list of all faculty with active committee counts, sortable. Read-only for faculty.
- **My Profile** — own details; only mobile number editable.

### Principal (in addition to the above)
- **Assign Committee** — the primary workflow. Select committee → select faculty (searchable dropdown, HTMX) → select role → set order date → preview → issue. On submit: order number generated, `.docx` rendered, assignments created, supersessions applied, email queued. Show the resulting order number and a download link.
- **Relinquish** — end an assignment without replacement, with order.
- **Committees** — manage committees and upload/replace order templates. Show which placeholders the uploaded template contains and validate that required ones are present.
- **Faculty Management** — create faculty records, deactivate, correct details.
- **Order Register** — all orders ever issued, filterable by year/committee/faculty. Download any. Cancel an order (with reason, requires confirmation).
- **Audit Log** — read-only, append-only view of all actions.

## 7. Explicitly out of scope for v1

Do not build these. If they seem necessary, raise it rather than adding it.

- Faculty self-registration
- Faculty accepting/declining an assignment (the Principal's order is final; this is a government institution, not a marketplace)
- Committee meeting minutes, agendas, or attendance
- Legally valid digital signatures (DSC / Aadhaar eSign). The Principal's signature is stamped as a stored image — see `10_SIGNATURE.md` for what that is and isn't.
- PDF output (the college works in Word; `.docx` only — needed later only if the college chooses DSC signing, see `10_SIGNATURE.md`)
- A mobile app
- Bulk import of faculty from Excel — **but** the `FacultyProfile` creation service must be callable from a management command so this can be added cleanly later
- Public (unauthenticated) views of any kind
