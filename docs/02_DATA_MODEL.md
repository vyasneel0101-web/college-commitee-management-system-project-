# 02 — Data Model

This is the contract. Field names here are the field names in code. If you believe a field is wrong or missing, say so before implementing, not after.

## Critical implementation order

**The custom `User` model must exist in the very first migration of the `accounts` app, before any other app's migrations run.** Swapping `AUTH_USER_MODEL` after tables exist is a painful manual migration. Set `AUTH_USER_MODEL = "accounts.User"` in settings before the first `makemigrations`.

---

## `accounts.Department`

| Field | Type | Notes |
|---|---|---|
| `name` | `CharField(120)` | unique. e.g. "Computer Engineering" |
| `code` | `CharField(10)` | unique, uppercase. e.g. "CE" |
| `is_active` | `BooleanField(default=True)` | |

`__str__` returns `name`. Ordered by `name`.

---

## `accounts.User`

Custom user model. Email **is** the identity — there is no username field.

```python
USERNAME_FIELD = "email"
REQUIRED_FIELDS = []   # email + password handled by manager
```

Inherit from `AbstractBaseUser` + `PermissionsMixin` with a custom `UserManager` implementing `create_user(email, ...)` and `create_superuser(email, ...)`. Do **not** subclass `AbstractUser` and leave a vestigial `username` column.

| Field | Type | Notes |
|---|---|---|
| `email` | `EmailField` | **unique**, primary identity. Normalized to lowercase on save. |
| `full_name` | `CharField(150)` | As it should appear on official orders. Include the honorific separately if needed — see note below. |
| `role` | `CharField(20, choices=Role)` | `FACULTY` / `PRINCIPAL`. Default `FACULTY`. **Never user-editable.** |
| `designation` | `CharField(40, choices=Designation)` | Academic post — see choices below |
| `govt_class` | `CharField(20, choices=GovtClass)` | Government pay class — see choices below |
| `department` | `FK(Department, on_delete=PROTECT, null=True)` | Nullable because the Principal may not sit in a department |
| `employee_code` | `CharField(30, blank=True)` | College/government staff ID if one exists. Unique when non-blank. |
| `joining_date` | `DateField(null=True)` | Date of joining the institution |
| `mobile` | `CharField(15, blank=True)` | Validated: exactly 10 digits, or `+91` followed by 10 digits |
| `signature_image` | `ImageField(upload_to="signatures/", null=True, blank=True)` | The Principal's signature, stamped into every generated order. PNG/JPEG, under 1 MB. See `10_SIGNATURE.md`. |
| `is_active` | `BooleanField(default=True)` | Controls login. Deactivation ≠ deletion. |
| `is_staff` | `BooleanField(default=False)` | Django admin access only. Not a business role. |
| `date_joined` | `DateTimeField(auto_now_add=True)` | Record creation, distinct from `joining_date` |
| `created_by` | `FK("self", on_delete=SET_NULL, null=True, related_name="created_users")` | Which Principal created this record |

**Choices:**

```python
class Role(models.TextChoices):
    FACULTY = "FACULTY", _("Faculty")
    PRINCIPAL = "PRINCIPAL", _("Principal")

class Designation(models.TextChoices):
    LECTURER = "LECTURER", _("Lecturer")
    ASSISTANT_PROFESSOR = "ASST_PROF", _("Assistant Professor")
    ASSOCIATE_PROFESSOR = "ASSOC_PROF", _("Associate Professor")
    PROFESSOR = "PROFESSOR", _("Professor")
    HEAD_OF_DEPARTMENT = "HOD", _("Head of Department")
    PRINCIPAL = "PRINCIPAL", _("Principal")
    OTHER = "OTHER", _("Other")

class GovtClass(models.TextChoices):
    CLASS_I = "CLASS_I", _("Class I")
    CLASS_II = "CLASS_II", _("Class II")
    CLASS_III = "CLASS_III", _("Class III")
    CLASS_IV = "CLASS_IV", _("Class IV")
```

> **Confirm these lists with the college before building** (see `07_OPEN_QUESTIONS.md`). They are easy to extend later via migration, but getting them right now avoids re-issuing orders with wrong designations.

**Properties / methods:**
- `is_principal` → `self.role == Role.PRINCIPAL`
- `active_assignments` → queryset of assignments with `status=ACTIVE`
- `active_committee_count` → count of the above. Do not use this in list views; annotate the queryset instead.

**Honorific note:** orders are addressed to e.g. "Shri M. R. Patel, Lecturer". Store `full_name` as the plain name and add a separate `salutation` field (`CharField(10, blank=True)`, e.g. "Shri", "Smt.", "Dr.") so the order template can compose the line. Do not bake the honorific into `full_name`.

---

## `core.AcademicYear`

| Field | Type | Notes |
|---|---|---|
| `label` | `CharField(9)` | unique. Format `YYYY-YY`, e.g. `2026-27`. Validated by regex. |
| `start_date` | `DateField` | |
| `end_date` | `DateField` | Must be after `start_date` (`CheckConstraint`) |
| `is_current` | `BooleanField(default=False)` | |

**Constraint:** at most one row with `is_current=True`. Use a `UniqueConstraint` with `condition=Q(is_current=True)` and a fixed expression, or enforce in a service that flips the others in the same transaction. Prefer the constraint.

`AcademicYear.objects.current()` on a custom manager. If no current year exists, raise a clear application error at order-creation time rather than silently using the latest.

---

## `committees.Committee`

| Field | Type | Notes |
|---|---|---|
| `name` | `CharField(200)` | unique. e.g. "Training & Placement Unit" |
| `code` | `CharField(15)` | unique, uppercase, alphanumeric only. Used in order numbers. e.g. `TPU` |
| `description` | `TextField(blank=True)` | Purpose/responsibilities, shown on the dashboard |
| `allows_multiple_members` | `BooleanField(default=True)` | If `False`, only a `CONVENER` may be assigned |
| `is_active` | `BooleanField(default=True)` | Inactive committees cannot receive new assignments; existing ones remain visible |
| `created_at` / `updated_at` | timestamps | |

**`code` is immutable after the committee's first order is issued** — it is embedded in order numbers. Enforce this in the form/service layer and test it.

## `committees.CommitteeTemplate`

Templates are **versioned**. A committee's template can be replaced, but old versions are retained because they document how past orders were produced.

| Field | Type | Notes |
|---|---|---|
| `committee` | `FK(Committee, on_delete=PROTECT, related_name="templates")` | |
| `version` | `PositiveIntegerField` | Auto-incremented per committee |
| `docx_file` | `FileField(upload_to="templates/%Y/")` | Validated: `.docx` only, ≤ 2 MB, content-type checked, `.docm` rejected |
| `is_active` | `BooleanField(default=True)` | The version used for new orders |
| `uploaded_by` | `FK(User, on_delete=PROTECT)` | |
| `uploaded_at` | `DateTimeField(auto_now_add=True)` | |
| `detected_placeholders` | `JSONField(default=list)` | Placeholders found by parsing the uploaded file |

**Constraints:** `unique_together = (committee, version)`; at most one `is_active=True` per committee.

**On upload, parse the docx and verify these required placeholders are present.** Reject the upload with a specific error listing what is missing:

```
{{ order_no }}          {{ order_date }}        {{ faculty_salutation }}
{{ faculty_name }}      {{ faculty_designation }} {{ faculty_department }}
{{ committee_name }}    {{ assignment_role }}   {{ academic_year }}
{{ principal_name }}    {{ principal_signature }}
```

`{{ principal_signature }}` is rendered as a `docxtpl` `InlineImage` from the Principal's `signature_image`. See `10_SIGNATURE.md` for the exact call.

Optional placeholders that may appear: `{{ faculty_employee_code }}`, `{{ committee_description }}`, `{{ previous_holder_name }}`, `{{ effective_date }}`, `{{ remarks }}`, `{{ member_list }}`.

---

## `orders.Order`

**Immutable after creation.** No application code modifies an existing `Order` except to set the cancellation fields.

| Field | Type | Notes |
|---|---|---|
| `order_no` | `CharField(60)` | **unique**, `db_index=True`. Format per BR-5. Generated atomically. |
| `order_date` | `DateField` | The official date on the document. `DateField`, not datetime. Cannot be in the future. |
| `academic_year` | `FK(AcademicYear, on_delete=PROTECT)` | |
| `committee` | `FK(Committee, on_delete=PROTECT, related_name="orders")` | |
| `order_type` | `CharField(20, choices=OrderType)` | `ASSIGNMENT` / `RELINQUISHMENT` / `CORRIGENDUM` |
| `issued_by` | `FK(User, on_delete=PROTECT, related_name="issued_orders")` | The Principal at time of issue |
| `generated_file` | `FileField(upload_to=order_file_path)` | The rendered `.docx`. Stored permanently. |
| `template_used` | `FK(CommitteeTemplate, on_delete=PROTECT)` | Which template version produced this file |
| `render_context` | `JSONField` | The exact context dict passed to docxtpl. Lets you prove what was rendered. |
| `remarks` | `TextField(blank=True)` | Free-text note from the Principal |
| `is_cancelled` | `BooleanField(default=False)` | |
| `cancelled_by_order` | `FK("self", null=True, on_delete=PROTECT, related_name="cancels")` | The corrigendum that cancelled this |
| `cancellation_reason` | `TextField(blank=True)` | Required when `is_cancelled=True` (`CheckConstraint`) |
| `created_at` | `DateTimeField(auto_now_add=True)` | |

`order_file_path` puts files under `orders/{academic_year}/{committee_code}/{order_no_slug}.docx`. Sanitize the order number for filesystem safety (replace `/` with `-`).

**`on_delete=PROTECT` everywhere is deliberate.** Deleting a department, committee, or user must fail loudly if orders reference it.

### Order number generation

Do **not** use `Order.objects.filter(...).count() + 1`. That has a race condition and reuses numbers after cancellation.

Use a dedicated sequence table:

```python
class OrderSequence(models.Model):
    academic_year = FK(AcademicYear, on_delete=PROTECT)
    committee = FK(Committee, on_delete=PROTECT)
    last_number = PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("academic_year", "committee")
```

In `orders/services.py`:

```python
@transaction.atomic
def next_order_no(academic_year, committee) -> str:
    seq, _ = OrderSequence.objects.select_for_update().get_or_create(
        academic_year=academic_year, committee=committee
    )
    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    return f"GPB/{committee.code}/{academic_year.label}/{seq.last_number:03d}"
```

`select_for_update()` is what makes this safe **on PostgreSQL**. On SQLite it is silently a no-op, so two simultaneous submissions could in principle collide. Acceptable now — one Principal, one button — and it is the first thing the Postgres migration fixes. Keep the code exactly as written so nothing changes at migration time. The concurrency test in `05_TESTING.md` becomes meaningful then.

---

## `assignments.Assignment`

The heart of the system. **Never updated except to transition status. Never deleted.**

| Field | Type | Notes |
|---|---|---|
| `faculty` | `FK(User, on_delete=PROTECT, related_name="assignments")` | |
| `committee` | `FK(Committee, on_delete=PROTECT, related_name="assignments")` | |
| `role` | `CharField(20, choices=AssignmentRole)` | `CONVENER` / `MEMBER` |
| `academic_year` | `FK(AcademicYear, on_delete=PROTECT)` | |
| `status` | `CharField(20, choices=AssignmentStatus, db_index=True)` | See state machine |
| `start_date` | `DateField` | Equals the issuing order's `order_date` unless an explicit effective date is given |
| `end_date` | `DateField(null=True, blank=True)` | Set when the assignment ends. Null while active. |
| `issuing_order` | `FK(Order, on_delete=PROTECT, related_name="created_assignments")` | The order that created this |
| `ending_order` | `FK(Order, null=True, on_delete=PROTECT, related_name="ended_assignments")` | The order that ended this |
| `superseded_by` | `FK("self", null=True, on_delete=SET_NULL, related_name="supersedes")` | The assignment that replaced this one |
| `created_at` | `DateTimeField(auto_now_add=True)` | |

```python
class AssignmentRole(models.TextChoices):
    CONVENER = "CONVENER", _("Convener")
    MEMBER = "MEMBER", _("Member")

class AssignmentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("Active")
    SUPERSEDED = "SUPERSEDED", _("Superseded")       # replaced by another faculty
    RELINQUISHED = "RELINQUISHED", _("Relinquished") # ended, no replacement
    EXPIRED = "EXPIRED", _("Expired")                # academic year ended
    CANCELLED = "CANCELLED", _("Cancelled")          # issuing order was cancelled
```

### Constraints (implement as `Meta.constraints`)

1. **One active holder per (faculty, committee, role):**
   `UniqueConstraint(fields=["faculty", "committee", "role"], condition=Q(status="ACTIVE"), name="uniq_active_assignment")`
2. **One active convener per committee:**
   `UniqueConstraint(fields=["committee"], condition=Q(status="ACTIVE", role="CONVENER"), name="uniq_active_convener")`
3. **Active assignments have no end date:**
   `CheckConstraint(check=Q(status="ACTIVE", end_date__isnull=True) | ~Q(status="ACTIVE"), name="active_has_no_end_date")`
4. **Non-active assignments have an end date** (except `CANCELLED`, which may not):
   `CheckConstraint(...)` — state it explicitly.
5. **`end_date >= start_date`** when `end_date` is not null.

**On SQLite (current state):** partial unique indexes are supported, so all five constraints above work as written — keep them. What SQLite does *not* honour is `select_for_update`, which it silently ignores; that affects order-number generation only, and is safe with a single Principal issuing orders one at a time. Tracked as debt item 1 in `00_START_HERE.md` §5.

### State machine

```
                    ┌──────────────────────────────────┐
                    │            (no record)           │
                    └────────────────┬─────────────────┘
                                     │ assign_committee()  [creates Order]
                                     ▼
                              ┌─────────────┐
                    ┌─────────│   ACTIVE    │─────────┐
                    │         └──────┬──────┘         │
     new holder     │                │                │  issuing order
     assigned       │                │ relinquish()   │  cancelled
                    ▼                ▼                ▼
             ┌────────────┐   ┌──────────────┐  ┌───────────┐
             │ SUPERSEDED │   │ RELINQUISHED │  │ CANCELLED │
             └────────────┘   └──────────────┘  └───────────┘
                    │
                    │  (academic year rollover, batch job)
                    ▼
              ┌───────────┐
              │  EXPIRED  │
              └───────────┘

All non-ACTIVE states are terminal, EXCEPT: cancelling an order restores any
assignment that order superseded back to ACTIVE (see BR-6).
```

**Transitions are implemented only in `assignments/services.py`.** No view or admin action sets `status` directly.

---

## `audit.AuditLogEntry`

Append-only. No update or delete, ever.

| Field | Type | Notes |
|---|---|---|
| `actor` | `FK(User, null=True, on_delete=SET_NULL)` | Null for system actions |
| `action` | `CharField(60, db_index=True)` | e.g. `ORDER_ISSUED`, `ORDER_CANCELLED`, `ASSIGNMENT_SUPERSEDED`, `FACULTY_CREATED`, `FACULTY_DEACTIVATED`, `TEMPLATE_UPLOADED`, `LOGIN_SUCCESS`, `LOGIN_FAILED`, `ROLE_CHANGED` |
| `object_type` | `CharField(60)` | Model name |
| `object_id` | `CharField(40)` | |
| `summary` | `CharField(255)` | Human-readable one-liner for the log view |
| `detail` | `JSONField(default=dict)` | Changed fields, before/after. **Never store the full document or any secret.** |
| `ip_address` | `GenericIPAddressField(null=True)` | From `X-Forwarded-For` handled correctly behind the proxy |
| `user_agent` | `CharField(300, blank=True)` | |
| `created_at` | `DateTimeField(auto_now_add=True, db_index=True)` | |

Write via `audit.services.log(...)`. Override `save()` to raise on update (`if self.pk: raise`), and override `delete()` to raise. The audit `ModelAdmin` has `has_add_permission`, `has_change_permission`, and `has_delete_permission` all returning `False`.

---

## Query patterns to implement as managers

Put these on custom managers/querysets so views stay thin and permission logic is centralized:

- `Assignment.objects.active()` — `status=ACTIVE`
- `Assignment.objects.for_faculty(user)` — that user's assignments, all statuses
- `Assignment.objects.directory()` — active assignments with `select_related("faculty", "committee", "faculty__department")`, for the institution-wide table
- `Order.objects.visible_to(user)` — all orders if Principal; only orders whose created or ended assignments involve that user, if Faculty. **Every order detail and download view goes through this.**
- `User.objects.faculty_with_counts()` — annotated with `Count("assignments", filter=Q(assignments__status="ACTIVE"))` for the workload screen

## Indexes

Beyond the implicit FK indexes, add:
- `Assignment`: composite index on `(status, committee)` and on `(faculty, status)`
- `Order`: index on `order_date`, and `(academic_year, committee)`
- `AuditLogEntry`: `(created_at)`, `(actor, created_at)`
