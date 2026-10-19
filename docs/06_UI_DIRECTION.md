# 06 — UI Direction

## Brief

The users are government polytechnic faculty and a Principal, aged roughly 30–60, on desktop browsers in offices and on phones between classes. Many are not habitual web-app users. The system replaces paper, so it must feel as legible and unambiguous as a well-typed official document — but faster.

**Primary job of the interface:** make "who holds what" answerable in one glance, and make issuing an order take under a minute.

This is a record-keeping instrument for a government institution. It should feel precise, calm, and trustworthy. Not playful, not startup-y, not a dashboard bristling with sparklines nobody asked for.

## Design direction

**Reference feeling:** a well-set official register — clear ruled structure, generous whitespace, unambiguous hierarchy. Think institutional stationery rendered properly for a screen, not a SaaS template.

**Avoid these, they are the generic defaults:**
- Cream background (#F4F1EA) with a terracotta accent
- Everything chopped into identical rounded cards with the same soft grey shadow
- Gradient washes as decoration
- Tracked-out ALL-CAPS eyebrow labels above every heading
- `01 / 02 / 03` numbered markers on content that isn't a sequence
- A `→` glued to the end of every link and button
- Emoji in the UI

**Palette** — propose 4–6 named hex values and show them to me before building. Constraints:
- One primary accent used for actions only, never decoration
- A distinct semantic colour for superseded/inactive states — history must be visually distinguishable from active at a glance, and not by colour alone (use weight or an explicit label too, for accessibility and for printing)
- Contrast ≥ 4.5:1 for all text
- The interface will be printed. Test that the palette survives a black-and-white print.

**Typography** — one or two families, chosen deliberately. Names and committee titles are the content; set them at a size that respects that. Tabular figures for the committee-count column so numbers align. Line length under 80 characters in any prose block.

**Layout**
- Tables, not cards, for the directory and register. This is tabular data; a card grid makes it harder to scan and harder to print.
- Left-aligned. No centred body text.
- Sticky table headers on long lists.
- The count badge on the dashboard is the one place to be bold. Everything around it stays quiet.

**Motion** — only in response to a user action: an HTMX swap, a dropdown opening, a confirmation appearing. No scroll-triggered reveals, no fade-up on page load, no hover transitions on every row. Respect `prefers-reduced-motion`.

## Component conventions

- **Faculty search dropdown** — the signature interaction. Type-ahead via HTMX with a 300 ms debounce, keyboard navigable (arrow keys, Enter, Escape), showing name, department code, and current committee count per result. The count is there so the Principal sees they are about to hand a seventh committee to someone already holding six. That is the feature, not a decoration.
- **Preview before issue** — a distinct step, visually separated from the form, stating in plain sentences what will happen: which order number will be generated, who gains the role, and who loses it. The confirm button says **Issue order**.
- **Status pills** — Active, Superseded, Relinquished, Expired, Cancelled. Text label always present; colour is secondary.
- **HTMX regions** — every swap target has a loading indicator and an `aria-live="polite"` wrapper so screen readers announce changes.
- **Confirmation for destructive-feeling actions** — cancelling an order and deactivating faculty both require a typed reason and an explicit confirm. Nothing irreversible happens on a single click.

## Copy rules

Words are interface content. Write them with the same care as the layout.

- Sentence case everywhere. No Title Case buttons, no ALL CAPS labels.
- Buttons name what happens: **Issue order**, **Assign committee**, **Save changes**, **Cancel order**. Not "Submit", not "OK".
- An action keeps its name through the whole flow. The button that says *Issue order* produces the message *Order issued.*
- Errors say what happened and what to do, in the interface's voice. No apologies, no vagueness.
  - Good: "This committee already has an active convener. Issuing this order will supersede Mihir Patel."
  - Good: "The template is missing `{{ order_no }}`. Add it and upload again."
  - Bad: "Oops! Something went wrong 😕"
  - Bad: "Error: validation failed"
- Empty states are invitations, not dead ends.
  - Faculty dashboard, no committees: "You currently hold no committees. Assignments issued by the Principal will appear here."
  - Order register, empty: "No orders issued yet. Assign a committee to issue the first one."
- Use the vocabulary the college uses. **Order**, **committee**, **convener**, **member**, **relinquish**, **corrigendum**, **academic year**. Do not invent softer synonyms — these words are what the office already says, and matching them is what makes the software feel native to the institution.
- Never surface internal terms: no "record", "entity", "instance", "FK", "queryset", "status enum".

## Quality floor

Not optional, and not worth announcing in the UI:

- Responsive from 375px up. Tables become stacked rows on narrow screens with the column label retained.
- Visible keyboard focus on every interactive element. Full flows completable without a mouse.
- All inputs have real `<label>` elements, not placeholder-only.
- `prefers-reduced-motion` honoured.
- A **print stylesheet** for the directory, the order register, and the order detail page: navigation hidden, black on white, table borders visible, page-break rules sensible. This office prints things; treat print as a real target, not an afterthought.

## Sprint constraints

Tailwind comes from the CDN (`https://cdn.tailwindcss.com`) for now, so only core utility classes are available — no custom theme config, no `@apply`. Pick your palette as inline arbitrary values (`bg-[#1e3a5f]`) or stay within Tailwind's built-in scales. No HTMX and no Alpine during the sprint; use plain GET forms and, where genuinely needed, a few lines of vanilla JS for the faculty filter box.

Everything else in this document still applies. The quality floor below is not a polish-phase luxury — focus rings and 375px support cost nothing if done as you go and are slow to retrofit.

## Process

Before writing UI code in Phase 3, produce a short plan: palette (4–6 named hex values), typefaces and their roles, a one-sentence layout concept, and ASCII wireframes for the dashboard and the assign flow. Show it to me. Then check it against the "avoid" list above — if any part is a default you'd produce for any project rather than a choice made for this one, revise it and say what changed and why.
