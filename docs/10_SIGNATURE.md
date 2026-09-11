# 10 — Signatures

## What we are building today

The Principal uploads one image of their signature. It is stored on their `User` record as `signature_image`, and every generated order has it stamped in automatically at the `{{ principal_signature }}` placeholder. No per-order action, no printing, no scanning.

Both demo templates already contain the placeholder, positioned above the Principal's name in the signature block.

## Implementation

`User.signature_image` — `ImageField(upload_to="signatures/", null=True, blank=True)`

In `orders/services.py`, when building the docxtpl context:

```python
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

tpl = DocxTemplate(committee.docx_template.path)

context = {
    "order_no": order_no,
    "order_date": order_date.strftime("%d-%m-%Y"),
    "faculty_salutation": faculty.salutation,
    "faculty_name": faculty.full_name,
    "faculty_designation": faculty.get_designation_display(),
    "faculty_department": faculty.department.name if faculty.department else "",
    "committee_name": committee.name,
    "assignment_role": role_label,
    "academic_year": academic_year.label,
    "principal_name": principal.full_name,
    "effective_date": effective_date.strftime("%d-%m-%Y"),
    "remarks": remarks or "—",
    "principal_signature": (
        InlineImage(tpl, principal.signature_image.path, width=Mm(38))
        if principal.signature_image
        else ""
    ),
}
```

Notes that will save time:

- `InlineImage` needs the **same `DocxTemplate` instance** that you later call `.render()` on. Building it against a different instance produces a broken image reference.
- `width=Mm(38)` is about right for a signature in an A4 order. Height scales automatically.
- Keep the `else ""` fallback. A missing signature should produce an order without one, not a 500.
- The demo signature PNG has a transparent background, so it sits correctly over the document.
- Store the signature outside the web root, like order documents. It is the one file in the system that most needs protecting.

## Uploading it

For the sprint, the seed command attaches `templates/demo/demo_principal_signature.png`. Add a field to the Principal's profile form so a real image can be uploaded through the UI — it's a one-line addition and it makes the demo answer the obvious question ("can I use mine?") with a yes.

Validate on upload: PNG or JPEG only, under 1 MB, and reject anything that fails to open with Pillow.

## What this is not

**A stored image stamped automatically is a rubber stamp, not a signature.** It carries no cryptographic proof and no non-repudiation. Anyone who can reach the image file, the database, or the assign endpoint can produce a document bearing the Principal's signature, and the Principal has no way to prove they didn't issue it.

That is acceptable for a demonstration and for internal administrative orders where the institution accepts it. It is not acceptable as evidence, and it should never be presented to the college as a digital signature in the legal sense.

**Say this unprompted when demonstrating.** Being the person who flags it is far better than being the person it gets discovered on:

> "The signature here is a stored image, which is right for showing the flow but isn't secure for real orders. For live use we'd either add your DSC token — you sign the PDF yourself and the system verifies it — or use an authenticated approval with a tamper-evident audit trail. I'd want your view on which."

That converts the weakness into the question that gets you a decision.

## The real options, for after the demo

A DSC private key lives on a USB crypto token and must stay in the Principal's sole control. It cannot be copied to a server for automatic signing — that destroys non-repudiation and breaches the subscriber agreement. So fully automatic legally-valid signing is not available at any price without a commercial eSign service.

**Option A — Internal e-approval.** Free, fully automatic. The Principal clicks "Approve & issue"; the system records the authenticated user, timestamp and IP in the immutable audit log, computes a SHA-256 hash of the document, stamps a verification line into the footer, and exposes a page where anyone can check a hash against the register. Not a legally recognised signature, but strong authentication plus tamper evidence. Usually sufficient for internal administrative orders.

**Option B — Real DSC, signed on the Principal's own machine.** Free if they already hold a Class 3 DSC, which most government principals do. The system generates a PDF, the Principal signs it with emSigner or Adobe Reader, uploads it back, and the system verifies the signature cryptographically with `pyHanko` and marks the order `SIGNED`. Still fully paperless. Costs about thirty seconds per order.

**Option C — Aadhaar eSign via a licensed ASP.** Best experience — OTP signing entirely in the browser — but requires a commercial agreement with eMudhra, NSDL, Protean or Digio, KYC onboarding, and roughly ₹5–20 per signature. The college would have to contract this; a student cannot set it up.

**Recommended path:** Option A as the default flow, Option B as an upgrade, with a single `OrderSignature` model recording `method` (`IMAGE_STAMP` / `E_APPROVAL` / `DSC` / `ESIGN`), signer, timestamp, document hash, and an optional signed file. Today's image stamp becomes the first `method` value, so nothing needs rewriting when the college decides.

Options B and C require PDF output, since DSC and PAdES signing only work on PDF. That means keeping `docxtpl` for the template mechanism and converting with headless LibreOffice — a real deployment dependency. Don't take it on until the college has chosen.

## The question to ask the college

> "Do these committee orders need a legally valid digital signature under the IT Act, or is an authenticated approval with a full audit trail enough for internal administrative orders?"

For internal committee assignments the answer is usually the latter, since DSCs tend to be mandated where a statute requires a signed document. But this is a policy call for the institution, not a technical one — and not legal advice. Get it answered before building B or C.
