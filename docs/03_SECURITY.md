# 03 — Security Specification

> **Sprint status.** Most of this document is deferred until after the demo. What applies **today**, in full, is:
>
> - `login_required` on every view except the landing page and login
> - `principal_required` (returning 403) on every Principal-only endpoint
> - Object-level filtering through `Order.objects.visible_to(request.user)` on every order view and download — §2
> - Order documents served only through a permission-checked `FileResponse`, never from `MEDIA_URL` — §3
> - No `fields = "__all__"`; `role` and `is_active` absent from every non-admin form — §2
> - Django's CSRF middleware left enabled, no `@csrf_exempt` anywhere
> - No `|safe` or `mark_safe` on user-supplied content
> - Secrets in `.env`, never in the repo
>
> Deferred: magic-link auth (§1), rate limiting, CSP, `django-axes`, the production settings block (§6), and the threat-test suite (§8). Debt items 3 and 4 in `00_START_HERE.md` §5.
>
> The six rules above cost minutes and are the ones that prevent a faculty member reading another's order. Do not skip them for speed.

This system holds personal data (names, mobile numbers, employment details) of government employees and produces official institutional records. Treat every requirement here as mandatory.

The governing principle: **deny by default**. A view with no explicit permission decision is a bug, not a public page.

---

## 1. Authentication design

### Identity

Email is the identity. There is no separate username. `User.email` is unique and normalized to lowercase before save.

### Method: domain-restricted passwordless login

**Primary: email magic link.** Faculty enter their college email, receive a single-use signed link, click it, and are logged in. Chosen as primary because it works regardless of which provider hosts the college mail.

**Secondary (config-only, enable when confirmed): Google OAuth.** If the college's mail runs on Google Workspace, enable `django-allauth`'s Google provider with a hosted-domain restriction. Both providers can be active simultaneously in allauth, so this is a settings change, not a rewrite. Build the magic link first.

### Domain restriction

```python
ALLOWED_EMAIL_DOMAINS = env.list("ALLOWED_EMAIL_DOMAINS")   # e.g. ["gpbhuj.ac.in"]
```

Enforce at **three** layers — all three, not one:

1. **Login form validation** — reject a non-allowed domain before doing anything else.
2. **allauth adapter** — override `is_open_for_signup()` to return `False` always (no self-signup, per spec), and validate domain in the login flow.
3. **`User.clean()` / a `CheckConstraint`-equivalent validation** — a user record cannot be created with an out-of-domain email, including via the Django admin and management commands.

Layer 3 matters because a superuser fat-fingering an email in the admin should fail, not create a shadow account.

### Magic link requirements

- Token is signed (`django.core.signing.TimestampSigner`) or a hashed random token stored server-side. **Do not** put a raw user ID in the URL.
- **Expiry: 15 minutes.**
- **Single use.** Store a `used_at` timestamp; a second click is rejected with a clear message.
- Bound to the requesting email — a token issued for A cannot log in B.
- The email body states the expiry and says to ignore it if unrequested.
- **No user enumeration:** the response after submitting an email is identical whether or not that account exists. Same message, same status code, same response time (avoid a fast path for the not-found case).
- Rate limit: **5 requests per email per hour** and **20 per IP per hour**. Use `django-ratelimit`. Exceeding it returns a generic "too many attempts, try later" message.
- Log every issue and every consumption to the audit log.

### No-self-signup

`ACCOUNT_ADAPTER` overrides `is_open_for_signup` → `False`. A magic-link request for an email with no existing active `User` sends **no email** and shows the same generic response. Accounts exist only because the Principal created them.

### Sessions

```python
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 8        # 8 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_ENGINE = "django.contrib.sessions.backends.db"
```

- Rotate the session key on login (`django.contrib.auth.login` does this — do not bypass it).
- **On role change or deactivation, invalidate that user's existing sessions.** Otherwise a demoted Principal keeps Principal powers until their cookie expires. Implement by bumping a `session_auth_hash`-affecting field or by clearing their session rows.

---

## 2. Authorization

### Implementation

- A `PrincipalRequiredMixin` (and `principal_required` decorator) that checks `request.user.is_principal`. It returns **403, not a redirect to login**, for an authenticated non-Principal — a redirect leaks that the URL exists and is confusing.
- A `FacultyOwnedObjectMixin` for views where a faculty may access only their own records.
- **Object-level checks happen in the queryset, not after fetching.** Always:
  ```python
  order = get_object_or_404(Order.objects.visible_to(request.user), pk=pk)
  ```
  Never:
  ```python
  order = get_object_or_404(Order, pk=pk)
  if not can_view(request.user, order): raise PermissionDenied  # too late, and easy to forget
  ```
- Role checks happen server-side on every request. Hiding a button in a template is UX, not security. Every hidden button's endpoint has its own test asserting 403.

### Endpoint permission matrix

Every endpoint. `403` means authenticated but forbidden. Anonymous access to anything except the first three rows redirects to login.

| Method | Path | Anonymous | Faculty | Principal | Object rule |
|---|---|---|---|---|---|
| GET | `/` | → login | → dashboard | → dashboard | |
| GET/POST | `/login/` | ✅ | → dashboard | → dashboard | Sprint: plain username/password. Later: rate-limited magic link at `/auth/login/`. |
| GET | `/auth/magic/<token>/` | ✅ | → dashboard | → dashboard | Deferred. Single use, 15 min. |
| POST | `/auth/logout/` | 403 | ✅ | ✅ | POST only, CSRF |
| GET | `/healthz` | ✅ | ✅ | ✅ | No DB data in response |
| GET | `/dashboard/` | → login | ✅ own data only | ✅ | |
| GET | `/directory/` | → login | ✅ read-only | ✅ | Active assignments only |
| GET | `/workload/` | → login | ✅ read-only | ✅ | Counts only, no contact details for faculty role |
| GET | `/profile/` | → login | ✅ own | ✅ own | |
| POST | `/profile/` | → login | ✅ **mobile only** | ✅ mobile only | Form lists exactly one field |
| GET | `/assignments/mine/` | → login | ✅ own, all statuses | ✅ own | |
| GET | `/faculty/<pk>/` | → login | ✅ limited fields | ✅ full | Faculty see name, dept, designation, committees — **not** mobile, joining date, or employee code |
| GET | `/orders/` | → login | ✅ own only | ✅ all | `Order.objects.visible_to(user)` |
| GET | `/orders/<pk>/` | → login | ✅ own only | ✅ all | Same queryset. 404 (not 403) for others' orders — don't confirm existence |
| GET | `/orders/<pk>/download/` | → login | ✅ own only | ✅ all | Permission-checked `FileResponse`. See §3. |
| GET/POST | `/orders/assign/` | → login | **403** | ✅ | The core workflow |
| POST | `/orders/assign/preview/` | → login | **403** | ✅ | HTMX partial; no DB write |
| GET/POST | `/orders/relinquish/<assignment_pk>/` | → login | **403** | ✅ | |
| POST | `/orders/<pk>/cancel/` | → login | **403** | ✅ | Requires reason; confirmation step |
| GET | `/htmx/faculty-search/` | → login | **403** | ✅ | Returns ≤ 20 rows, name + dept only. Rate limited. See §4. |
| GET | `/committees/` | → login | ✅ read-only | ✅ | |
| GET/POST | `/committees/new/` | → login | **403** | ✅ | |
| GET/POST | `/committees/<pk>/edit/` | → login | **403** | ✅ | `code` immutable once orders exist |
| POST | `/committees/<pk>/template/` | → login | **403** | ✅ | File validation per §5 |
| GET | `/committees/<pk>/template/<v>/download/` | → login | **403** | ✅ | |
| GET | `/faculty/` | → login | **403** | ✅ | Management list |
| GET/POST | `/faculty/new/` | → login | **403** | ✅ | `role` not in form fields |
| GET/POST | `/faculty/<pk>/edit/` | → login | **403** | ✅ | `role`, `is_active` not in this form |
| POST | `/faculty/<pk>/deactivate/` | → login | **403** | ✅ | Warns if active assignments exist |
| GET | `/audit/` | → login | **403** | ✅ | Read-only, no add/edit/delete route exists |
| any | `/admin/` | → login | **403** | **403** | `is_staff` + `is_superuser` only |

**Test requirement:** implement this table as a parametrized test. See `05_TESTING.md` §3.

---

## 3. Protected file serving — the most likely thing to get wrong

Order documents contain names, designations, and departments of government employees. They must never be reachable by guessing a URL.

**Rules:**

1. Orders and templates are stored under a `MEDIA_ROOT` that the web server **does not** serve directly. In production, do not add a `location` block or static route for it. It is not in `STATICFILES_DIRS` and not collected by `collectstatic`.
2. All downloads go through a view that: requires login → resolves the object via `Order.objects.visible_to(request.user)` → returns `FileResponse(..., as_attachment=True)`.
3. Filenames on disk include a random component (`get_random_string(12)`) in addition to the order number, so that even if the storage location leaks, paths are not enumerable.
4. Response headers on downloads: `Content-Disposition: attachment; filename="..."`, `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`.
5. Every download is written to the audit log (`ORDER_DOWNLOADED`).
6. In development, `DEBUG`-mode media serving must be limited to nothing under the orders path. Do not use `static()` on `MEDIA_URL` for these.

If you later move to S3, use time-limited signed URLs generated inside the same permission-checked view. Never public-read buckets.

---

## 4. The faculty search endpoint

The HTMX searchable dropdown is a staff directory lookup. Left unprotected it is a personal-data scraping endpoint.

- Principal only (`403` for faculty).
- Minimum query length: 2 characters. Shorter returns an empty result, not the full list.
- Returns at most 20 results.
- Returns only `id`, `full_name`, `designation`, `department.code`, and `active_committee_count`. **No email, no mobile, no employee code, no joining date.**
- Rate limited: 30 requests/minute per user.
- Only `is_active=True` users.
- Query uses `icontains` on `full_name` and `employee_code` via the ORM. No raw SQL, no string-formatted queries.

---

## 5. File upload validation (committee templates)

Uploaded `.docx` templates are the only user-supplied files in the system. Validate all of:

1. **Extension** in `{.docx}` only. `.docm`, `.doc`, `.dotm` rejected — macro-enabled formats are never accepted.
2. **Size** ≤ 2 MB, checked before reading.
3. **Magic bytes** — a `.docx` is a ZIP; verify the `PK\x03\x04` header. Do not trust the browser's `Content-Type`.
4. **Structure** — open with `python-docx`/`docxtpl` inside a try/except; a file that fails to parse is rejected with a readable error.
5. **Zip-bomb guard** — inspect `zipfile` entry sizes; reject if the uncompressed total exceeds 20 MB.
6. **No macro parts** — reject if the archive contains `vbaProject.bin`.
7. **Filename sanitized** — never use the uploaded name on disk. Generate the stored name yourself.
8. **Placeholder check** — required placeholders present, per `02_DATA_MODEL.md`.

Rendering happens with `docxtpl`, which uses Jinja2. **Jinja2 with a user-supplied template is remote code execution.** Because templates come only from the Principal here, the risk is contained, but:
- Use `docxtpl`'s sandboxed environment (`jinja_env` with `SandboxedEnvironment`).
- Never pass a template file uploaded by a non-Principal.
- Never build the render context from URL parameters. It is built server-side from database objects only.

---

## 6. Django hardening settings

Production settings module. `python manage.py check --deploy` must be clean.

```python
DEBUG = False                       # from env; must be False in production
SECRET_KEY = env("SECRET_KEY")      # never a default value in code
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False        # HTMX needs to read it; SameSite covers us
CSRF_COOKIE_SAMESITE = "Lax"

X_FRAME_OPTIONS = "DENY"

DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200
```

**Content Security Policy** via `django-csp`. Because HTMX and Alpine are involved, aim for:
- `default-src 'self'`
- `script-src 'self'` — bundle HTMX and Alpine as static files rather than CDN, so no `unsafe-inline` and no third-party origin is needed. Alpine's default build needs `unsafe-eval`; use the **CSP build of Alpine** to avoid it.
- `style-src 'self'` — Tailwind is compiled to a static file, so no inline styles needed.
- `img-src 'self' data:`
- `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'self'`

If you cannot avoid `unsafe-eval` or `unsafe-inline`, tell me and explain why rather than quietly adding it.

**Other requirements:**
- Argon2 password hasher configured (`django[argon2]`) even though passwords are barely used — the superuser has one.
- `AUTH_PASSWORD_VALIDATORS` at Django defaults plus a 12-character minimum for the superuser.
- `django-axes` for lockout on repeated failed admin logins.
- Structured logging: log all 4xx/5xx, all auth events, all order issuance. **Never log tokens, session keys, magic-link URLs, or `SECRET_KEY`.**
- Admin at a non-default path from env (`ADMIN_URL`), e.g. `/manage-a7f3/`. Obscurity is not security, but it removes the bulk of automated scanning noise.
- `.env` in `.gitignore`. Commit `.env.example` with placeholders.

---

## 7. Data protection

- **Principle of least data on screen.** The directory and workload views show name, department, designation, committee, and role. Mobile numbers and joining dates are visible only to the Principal and to the owner.
- No personal data in URLs or query strings — no `?email=...`. Use primary keys.
- No personal data in the audit log's `detail` beyond changed field names and values necessary to reconstruct the change.
- Email notifications go **only** to the affected faculty member and, as a copy, to the Principal. Never BCC a list.
- Database backups: document a `pg_dump` schedule in the deployment notes. An institution's order register with no backup is a liability.
- `DEBUG = False` in production means Django's error pages never leak stack traces. Verify with a deliberate 500 in staging.

---

## 8. Threat checklist to verify before handover

Each of these has a required test. Verify, don't assume.

| # | Threat | Mitigation to verify |
|---|---|---|
| T1 | Faculty views another faculty's order by changing the URL ID | `Order.objects.visible_to()` on every order view; test returns 404 |
| T2 | Faculty escalates to Principal by posting `role=PRINCIPAL` to the profile form | `role` absent from all non-admin form field lists; test posting it changes nothing |
| T3 | Order document downloaded without login by guessing the media path | Media not web-served; test anonymous GET to the file path fails |
| T4 | Magic link reused, or shared and reused | Single-use `used_at`; test second use fails |
| T5 | Magic link brute-forced | Signed/hashed token, 15-min expiry, rate limit; test invalid token fails |
| T6 | Outsider with a personal Gmail logs in | Three-layer domain check; test rejection at each layer |
| T7 | Two orders issued simultaneously get the same number | `select_for_update`; concurrency test |
| T8 | Faculty scrapes the staff directory via the HTMX search endpoint | Principal-only, min query length, capped results, rate limited; test 403 for faculty |
| T9 | Malicious `.docx` template uploaded (macros, zip bomb, RCE via Jinja) | Full validation chain §5 + sandboxed Jinja env; test each rejection |
| T10 | Order edited after issue to change a name | No edit path exists; test that the update view returns 405/404 and the service raises |
| T11 | Assignment history destroyed via a delete | No `.delete()` on `Order`/`Assignment`; admin delete permission disabled; test |
| T12 | Audit log tampered with | `save()` raises on update, `delete()` raises, admin permissions all `False`; test |
| T13 | Demoted Principal retains access via an old session | Session invalidation on role change; test |
| T14 | CSRF on the assign-committee POST | Django CSRF middleware, no `@csrf_exempt` anywhere; test POST without token fails |
| T15 | XSS via a committee description or remarks field | Django auto-escaping; **no `|safe` and no `mark_safe` on any user-supplied content**; test with a `<script>` payload |
| T16 | SQL injection via the faculty search | ORM only, no raw SQL; test with a quote-heavy payload |
| T17 | Deactivated faculty still logs in | `is_active` checked by the auth backend; test |
| T18 | Cancelled order's number reused, letting two documents share a number | Sequence table never decrements; test |
| T19 | Open redirect on the post-login `next` parameter | Validate `next` against allowed hosts (`url_has_allowed_host_and_scheme`); test with an external URL |
| T20 | Clickjacking of the assign form | `X_FRAME_OPTIONS = "DENY"`, CSP `frame-ancestors 'none'`; test header present |

**`@csrf_exempt` must not appear anywhere in this codebase.** If you think you need it for an HTMX endpoint, you don't — send the token in the `hx-headers` attribute on `<body>`.
