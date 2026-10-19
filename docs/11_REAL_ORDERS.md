# 11 — What the real orders tell us

Three genuine orders from the college, photographed on 13 Oct 2026 and kept in
`docs/real_orders/`. They replace the guesses in `docs/08_DEMO_DATA.md` §4.

This document records what they show and what must change. **Read it before
touching the data model again.**

| File | Order | Language | People named |
|---|---|---|---|
| `01_nba_criteria_8_3_gujarati` | NBA Criteria 8.3 feedback duty, No. GPB/૪૨૯, 20/04/2026 | Gujarati | 2 |
| `02_internal_complaint_committee_english` | Internal Complaint Committee, No. GPB[ESTT]564, 1/5/2024 | English | 7 |
| `03_academic_bank_of_credits_gujarati` | Academic Bank of Credits, No. GPB/મહેમ/૨૧૪, 09/02/2023 | Gujarati | 8 |

---

## 1. One order names many people — confirmed

All three orders appoint between two and eight people in a single numbered
document, as a table. Q9 in `docs/07_OPEN_QUESTIONS.md` is answered: the
default of one faculty per order is **wrong**.

This is the largest change. An order must create several assignments at once,
and the document must render a member table rather than one name.

## 2. The roles are not "convener" and "member"

Observed, across three orders, and confirmed by the college as the **complete**
list — there are no others:

| Role | Seen in |
|---|---|
| Presiding Officer | Internal Complaint Committee |
| Nodal Officer | Academic Bank of Credits |
| Member | all three |
| External Member | Internal Complaint Committee |

"Convener" appears in none of them and is being removed.

**This replaces the `uniq_active_convener` constraint.** The real rule is that a
committee has at most one person in charge: one Presiding Officer *or* one
Nodal Officer, never both and never two. Member and External Member are
unlimited.

## 3. Some members are not college staff

The Internal Complaint Committee includes **Ms. A. C. Jani, Founder, Sakhi
Sangini and Kutch Mahila Vikas Sangathan** — an external member, with an
organisation instead of a department. The current model requires every
assignment to point at a `User` with a college email address. That cannot
represent her.

An external member needs a name, a description of who they are, and no sign-in.

## 4. Non-teaching staff are appointed too

The same order names **Ms. G. V. Jobanputra, Counter attendant, Library**. The
word "faculty" is too narrow throughout the interface and the model: these are
staff, and some are not teaching staff.

## 5. The order number format is different — deferred

Observed: `મપોભુ/GPB/૪૨૯`, `સપોભુ/GPB <handwritten> 564`, `સપોભુ/GPB/મહેમ/૨૧૪`.

The serials are in the hundreds (429, 564, 214), carry no academic year, and
at least one has a handwritten token between `GPB` and the serial that I could
not read reliably from the photograph — do not trust any transcription of it
until the office confirms what it is.

**Decision (13 Oct 2026): keep `GPB/{COMMITTEE}/{YEAR}/{SEQ:03d}` for now.**
Changing it is a single function, `orders/services.py::next_order_no()`, so it
costs nothing to defer until the office explains their scheme.

## 6. Orders cite references

Two of the three begin with the authority they act under:

- "વંચાણે લીધા: જી.ટી.યુ. ના પરિપત્ર ક્રમાંક ... તા. 04/02/23"
- "Reference: 1) The sexual harassment of women at workplace ... Act, 2013 …"

The order needs an optional free-text references block, printed above the body.

## 7. Language: English only

Two of the three orders are in Gujarati, but the college has confirmed the
system only needs to produce **English** orders. Interface strings stay wrapped
for translation, since that costs nothing, but no Gujarati templates, fonts or
numeral conversion are needed.

## 8. Letterhead and footer details

Printed letterhead: college crest, est. 1987, bilingual name, "Opp. Hill
Garden, Bhuj - Kutch. 370 001", `www.gpbhuj.ac.in`,
`gp-bhuj-dte@gujarat.gov.in`, phone 9428546433. Subject lines are underlined.
The signature block reads આચાર્યશ્રી / Principal with the college name beneath,
and every order ends with a copy-forwarded list.

All of this lives in the uploaded template, so none of it needs code.

## 9. A department we do not have

Order 3 names **માઇનીંગ (Mining)**. The seeded department list is incomplete;
the real list must come from the office.

---

## What this means for the build

| # | Change | Status |
|---|---|---|
| 1 | One order creates many assignments, with `{{ member_list }}` in the template | **Done** |
| 2 | The four real roles, and one person in charge per committee | **Done** |
| 3 | External members who are not users | **Done** |
| 4 | References block on orders | **Done** |
| 5 | A template matching their multi-member format | **Done** — `templates/demo/order_template_COMMITTEE.docx` |
| 6 | Rename faculty → staff throughout the interface copy | Pending, ~1 hr |
| 7 | New numbering scheme | Deferred until the office explains theirs |
| 8 | Real departments, committees and templates | Data entry, once the office sends them |

## Questions for the office

1. What do the section tokens mean (`ESTT`, `મહેમ`), and who allocates the serial?
2. Does the serial restart on 1 January, on 1 June, or never?
3. What is the full list of roles used across committees?
4. How often is an external member appointed, and what detail is printed about them?
5. The full department list, including Mining.
6. Should the system print Gujarati numerals in order numbers?
