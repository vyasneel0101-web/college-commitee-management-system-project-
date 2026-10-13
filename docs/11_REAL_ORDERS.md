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

Observed, across three orders:

| Role seen | Order |
|---|---|
| Presiding Officer | Internal Complaint Committee |
| Member | all three |
| External Member | Internal Complaint Committee |
| નોડલ ઓફિસર (Nodal Officer) | Academic Bank of Credits |
| સભ્ય (Member) | Academic Bank of Credits |

"Convener" appears in none of them. The role list must become data the office
can extend, not a fixed pair in code — or at minimum a longer `TextChoices`
including Presiding Officer, Nodal Officer, Member and External Member.

**This also breaks the `uniq_active_convener` constraint as written.** The rule
is really "at most one *presiding* role per committee", and which roles count
as presiding is now a property of the role, not a hardcoded value.

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

## 5. The order number format is different

Observed: `મપોભુ/GPB/૪૨૯`, `સપોભુ/GPB[ESTT]564`, `સપોભુ/GPB/મહેમ/૨૧૪`.

So the real shape is roughly:

```
<institution in Gujarati>/GPB[/<section>]/<serial>
```

- There is a **section token** — `ESTT` (establishment), `મહેમ` — not a
  committee code.
- The serial looks like a single running number per section, in the hundreds
  (429, 564, 214), **not** a per-committee sequence restarting at 001.
- Gujarati orders print the numerals in Gujarati (૪૨૯).
- No academic year appears in the number at all.

Our `GPB/TPU/2026-27/001` is wrong on every count. `next_order_no()` and
`OrderSequence` must change — the sequence key is the section (or the whole
office), not the committee.

**Still to confirm with the office:** what the section tokens mean, whether the
serial restarts each calendar year or each academic year, and who allocates it.

## 6. Orders cite references

Two of the three begin with the authority they act under:

- "વંચાણે લીધા: જી.ટી.યુ. ના પરિપત્ર ક્રમાંક ... તા. 04/02/23"
- "Reference: 1) The sexual harassment of women at workplace ... Act, 2013 …"

The order needs an optional free-text references block, printed above the body.

## 7. Both languages are in use

Two Gujarati, one English, from the same office. The interface strings are
already wrapped for translation; the templates themselves carry the language,
so a Gujarati committee template produces a Gujarati order with no code change.
Gujarati numerals in the order number would need a conversion step.

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

| # | Change | Size |
|---|---|---|
| 1 | One order creates many assignments: model, service, assign flow, `{{ member_list }}` in the template | ~4–6 hrs |
| 2 | Configurable roles, and "one presiding role per committee" replacing the convener constraint | ~2 hrs |
| 3 | External members who are not users | ~2 hrs |
| 4 | Rename faculty → staff in model help, interface copy and screens | ~1 hr |
| 5 | New numbering: section-based serial, no academic year | ~1–2 hrs |
| 6 | References block on orders | ~30 min |
| 7 | Real departments, real committees, real templates | data entry |

Roughly **10–14 hours**, and it touches the parts of the data model that were
most settled. Better now than after the college is depending on it.

## Questions for the office

1. What do the section tokens mean (`ESTT`, `મહેમ`), and who allocates the serial?
2. Does the serial restart on 1 January, on 1 June, or never?
3. What is the full list of roles used across committees?
4. How often is an external member appointed, and what detail is printed about them?
5. The full department list, including Mining.
6. Should the system print Gujarati numerals in order numbers?
