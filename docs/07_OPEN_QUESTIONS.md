# 07 — Open Questions

Answer what you can before Phase 1. For anything unanswered, tell Claude Code to use the stated default — each default is chosen so that changing it later is a small migration, not a redesign.

## Blocking before Phase 1 (data model)

**Q1. Exact email domain.**
You said "@gpbhuj.faculty.in or something". Get the exact string from a real faculty email. This goes in `ALLOWED_EMAIL_DOMAINS`.
*Default:* `gpbhuj.ac.in`, configurable via env — so a wrong guess costs one env-var change.

**Q2. Is the college mail on Google Workspace, Microsoft 365, or an in-house/ISP mail server?**
Check whether faculty log into mail at `mail.google.com`, `outlook.office.com`, or a webmail page with the college's own branding.
*Default:* build magic-link login (works either way), add Google OAuth later as a settings change.

**Q3. Designation list.**
Confirm the real academic designations used in appointment letters. In Gujarat's polytechnics the common set is Lecturer / Head of Department / Principal, sometimes with Assistant and Associate Professor for degree-level staff. Ask for the actual list.
*Default:* the `Designation` choices in `02_DATA_MODEL.md`.

**Q4. Government class list.**
Confirm whether the college records Class I / II / III / IV, or uses pay-level/pay-band terminology instead.
*Default:* Class I–IV.

**Q5. Do committees have roles beyond convener and member?**
Some institutions use Chairperson, Convener, Co-convener, Member Secretary, Member.
*Default:* `CONVENER` and `MEMBER` only. Adding a choice later is a one-line migration, so don't over-model this now.

**Q6. Order number format.**
Ask to see three real orders and copy their numbering exactly. Government offices care about this, and a format that doesn't match theirs makes the output unusable as an official record.
*Default:* `GPB/{COMMITTEE_CODE}/{ACADEMIC_YEAR}/{SEQ:03d}`.

**Q7. Is order numbering per-committee or college-wide sequential?**
This changes the `OrderSequence` key. A single college-wide register per year is also common.
*Default:* per committee per academic year.

## Blocking before Phase 5 (order generation)

**Q8. Get the actual Word files.**
Collect real order templates for at least three different committees. You cannot build or test document generation against a template you invented — and the differences between committees' formats are exactly where surprises live.

**Q9. Do orders list all committee members, or one faculty per order?**
If a single order can appoint a convener plus four members, the render context needs a `{{ member_list }}` loop and the assign flow needs multi-select.
*Default:* one faculty per order, single role. `{{ member_list }}` is listed as an optional placeholder so the model supports it later.

**Q10. Is there a signature block, letterhead image, or office seal in the template?**
`docxtpl` handles static letterheads fine since they live in the template itself. Only raise this if a per-order image needs inserting.

**Q11. Does an order need a "with effect from" date separate from the order date?**
Government orders often are dated one day and effective another.
*Default:* `Assignment.start_date` defaults to the order date but is separately settable, so this is already supported.

## Blocking before Phase 7 (email)

**Q12. SMTP credentials.**
Does the college have an SMTP account you can use, or will you send from a service like Brevo/Resend with the college domain? You need a host, port, username, password, and a permitted From address.
*Default:* console backend in development, decision deferred to Phase 7. Do not let this block Phases 0–6.

**Q13. Should the order document be attached to the email, or only linked?**
Attaching is friendlier for faculty who won't log in; linking keeps the document behind authentication.
*Default:* attach, and also link. The recipient is the subject of the order, so they are entitled to the file.

## Non-blocking but worth asking

**Q14. How many faculty and how many committees?**
Affects nothing architecturally at polytechnic scale, but if it turns out to be 400 faculty you'll want the directory paginated from the start.

**Q15. Who owns this after you graduate?**
If nobody in the college can operate it, it dies. Argues for keeping the Django admin usable as a fallback interface, which the plan already does via `django-unfold` — and for `DEPLOYMENT.md` being written for a non-developer.

**Q16. Does the principal want a printed register of all orders for the year?**
If yes, that's a print-stylesheet view of the order register — already in Phase 9. Confirm the columns they'd want.

**Q17. Any existing paper records to backfill?**
If the Principal wants last year's assignments in the system, you need an import path that creates historical orders with real past dates and numbers. This is a Phase 10 conversation, but knowing now stops you from adding a "no backdated orders" validation that you'd then have to remove.

---

## What to do with unanswered questions

Do not stall. Every default above is deliberately chosen to be cheap to change:

- Q1, Q2, Q12 → environment variables
- Q3, Q4, Q5 → `TextChoices`, changed by migration
- Q6, Q7 → one function, `next_order_no()`
- Q9, Q10, Q11 → template placeholders and the render context

Start Phase 0 today. Get the answers to Q1, Q6, and Q8 in the same week, because those three are the ones your college can most easily hand you and the ones most likely to make the output look wrong if guessed.
