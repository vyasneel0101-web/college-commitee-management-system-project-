"""
Order numbering, preview and document generation.

docs/02_DATA_MODEL.md, BR-1, BR-5, BR-7, docs/10_SIGNATURE.md, docs/08_DEMO_DATA.md §1.
"""

from dataclasses import dataclass
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage
from jinja2.sandbox import SandboxedEnvironment

from accounts.models import ExternalMember
from assignments.models import LEAD_ROLES, Assignment, AssignmentRole, AssignmentStatus
from assignments.services import (
    assign_committee,
    cancel_assignment,
    current_lead,
    relinquish_assignment,
    restore_ended,
    validate_assignment,
)
from audit import services as audit
from audit.models import AuditAction
from core.exceptions import (
    AssignmentNotActive,
    DomainError,
    CancellationReasonRequired,
    DuplicateAppointment,
    NoAppointments,
    NotPrincipal,
    OrderAlreadyCancelled,
    OrderDateInvalid,
    OrderNotCancellable,
    PreviewOutdated,
    TemplateMissing,
)
from core.models import AcademicYear
from notifications.services import notify_committee

from .models import Order, OrderSequence, OrderTemplate, OrderType

SPECIMEN_LINE = "SPECIMEN — DEMONSTRATION ONLY — NOT AN OFFICIAL ORDER"
DOCUMENT_DATE_FORMAT = "%d-%m-%Y"
SIGNATURE_WIDTH = Mm(38)

# Default for issue_assignment_order(expected_superseded_id=...): no preview to compare with.
NOT_CHECKED = object()


@dataclass(frozen=True)
class AssignmentPreview:
    academic_year: AcademicYear
    expected_order_no: str
    template: object
    previous_holder: object  # the Assignment that would be superseded, or None


def _format_order_no(academic_year, committee, number):
    return f"{settings.INSTITUTION_CODE}/{committee.code}/{academic_year.label}/{number:03d}"


@transaction.atomic
def next_order_no(academic_year, committee) -> str:
    """
    Consume and return the next order number for this committee and year.

    Invariant (BR-5): numbers are unique and never reused; the sequence only
    increases. If the surrounding transaction rolls back, so does the
    increment. select_for_update makes this race-safe on PostgreSQL; on SQLite
    it is a no-op (debt item 1).
    """
    seq, _created = OrderSequence.objects.select_for_update().get_or_create(
        academic_year=academic_year, committee=committee
    )
    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    return _format_order_no(academic_year, committee, seq.last_number)


def peek_next_order_no(academic_year, committee) -> str:
    """The number next_order_no() would return right now. Not reserved; writes nothing."""
    last = (
        OrderSequence.objects.filter(academic_year=academic_year, committee=committee)
        .values_list("last_number", flat=True)
        .first()
    )
    return _format_order_no(academic_year, committee, (last or 0) + 1)


def _on_row(error, index):
    """Tag a domain error with the appointment it concerns, and return it."""
    error.appointment_index = index
    return error


def _check_assignment_order(
    *, committee, appointments, order_date, issued_by, academic_year
):
    """
    Every check an assignment order must pass, for all of its appointments.

    Returns (academic year, template, the lead who would be superseded or None).
    Writes nothing.
    """
    if not issued_by.is_principal:
        raise NotPrincipal()
    if not appointments:
        raise NoAppointments()
    if academic_year is None:
        academic_year = AcademicYear.objects.current()
    if order_date > timezone.localdate():
        raise OrderDateInvalid(_("The order date cannot be in the future."))
    if not academic_year.contains(order_date):
        raise OrderDateInvalid(
            _("The order date %(date)s is outside the academic year %(year)s.")
            % {"date": order_date.strftime(DOCUMENT_DATE_FORMAT), "year": academic_year.label}
        )

    seen = set()
    leads = []
    for index, (holder, role) in enumerate(appointments):
        key = (type(holder).__name__, holder.pk, role)
        if key in seen:
            raise _on_row(
                DuplicateAppointment(
                    _("%(name)s is named twice in the same role on this order.")
                    % {"name": holder.full_name}
                ),
                index,
            )
        seen.add(key)
        if role in LEAD_ROLES:
            leads.append(index)
        try:
            validate_assignment(
                holder=holder, committee=committee, role=role, order_date=order_date
            )
        except DomainError as exc:
            # So the screen can show the message against the person it concerns.
            raise _on_row(exc, index) from None
    if len(leads) > 1:
        raise _on_row(
            DuplicateAppointment(
                _("An order can name only one Presiding Officer or Nodal Officer.")
            ),
            leads[1],
        )

    template = OrderTemplate.objects.active()
    if template is None:
        raise TemplateMissing()
    previous_lead = current_lead(committee) if leads else None

    return academic_year, template, previous_lead


def preview_assignment_order(
    *, committee, appointments, order_date, issued_by, academic_year=None
):
    """
    Run every check issue_assignment_order runs and describe what it would do.

    Invariant: writes nothing. The order number shown is expected, not
    reserved; the real number is assigned when the order is issued.
    """
    academic_year, template, previous_lead = _check_assignment_order(
        committee=committee,
        appointments=appointments,
        order_date=order_date,
        issued_by=issued_by,
        academic_year=academic_year,
    )
    return AssignmentPreview(
        academic_year=academic_year,
        expected_order_no=peek_next_order_no(academic_year, committee),
        template=template,
        previous_holder=previous_lead,
    )


def _member_rows(appointments):
    """The table of people as the order document prints it."""
    rows = []
    for number, (holder, role) in enumerate(appointments, start=1):
        external = isinstance(holder, ExternalMember)
        rows.append(
            {
                "sr": number,
                "salutation": holder.salutation,
                "name": holder.full_name,
                "designation": holder.organisation
                if external
                else holder.get_designation_display(),
                "department": ""
                if external
                else (holder.department.name if holder.department else ""),
                "role": str(AssignmentRole(role).label),
                "is_external": external,
            }
        )
    return rows


@transaction.atomic
def issue_assignment_order(
    *,
    committee,
    appointments,
    order_date,
    issued_by,
    academic_year=None,
    effective_date=None,
    remarks="",
    references="",
    expected_superseded_id=NOT_CHECKED,
    request=None,
):
    """
    Issue one order appointing one or more people to a committee.

    `appointments` is a sequence of (holder, role) pairs, where a holder is a
    User or an ExternalMember. Real orders name between two and eight people
    (docs/11_REAL_ORDERS.md §1).

    Invariants:
    - All or nothing. The order row, every assignment, any supersession, the
      sequence increment and the audit entries commit together; on failure the
      stored file is removed and nothing remains.
    - BR-1: assignments exist only together with the order that created them.
    - BR-5: the number comes from next_order_no() and is never reused.
    - BR-7: the rendered .docx is stored once and never regenerated.
    - At most one person in charge is named, and appointing them supersedes
      the committee's current lead.
    - If `expected_superseded_id` is given (what the Principal saw in the
      preview, or None), the order is refused when the lead who would actually
      be superseded is different.
    - Under DEMO_MODE the specimen line is the first paragraph. There is no
      argument that turns it off.
    """
    appointments = list(appointments)
    academic_year, template, previous_lead = _check_assignment_order(
        committee=committee,
        appointments=appointments,
        order_date=order_date,
        issued_by=issued_by,
        academic_year=academic_year,
    )
    if expected_superseded_id is not NOT_CHECKED:
        actual_superseded_id = previous_lead.pk if previous_lead else None
        if actual_superseded_id != expected_superseded_id:
            raise PreviewOutdated()
    effective_date = effective_date or order_date

    order_no = next_order_no(academic_year, committee)
    members = _member_rows(appointments)
    first = members[0]
    context = {
        "order_no": order_no,
        "order_date": order_date.strftime(DOCUMENT_DATE_FORMAT),
        # Singular placeholders describe the first person named, so a template
        # written for one appointee still renders correctly.
        "faculty_salutation": first["salutation"],
        "faculty_name": first["name"],
        "faculty_designation": first["designation"],
        "faculty_department": first["department"],
        "faculty_employee_code": getattr(appointments[0][0], "employee_code", ""),
        "assignment_role": first["role"],
        # The table, for templates that print every person.
        "member_list": members,
        "member_count": len(members),
        "committee_name": committee.name,
        "committee_description": committee.description,
        "academic_year": academic_year.label,
        "principal_name": issued_by.full_name,
        "effective_date": effective_date.strftime(DOCUMENT_DATE_FORMAT),
        "previous_holder_name": previous_lead.holder_name if previous_lead else "",
        "references": references,
        "remarks": remarks or "—",
    }
    signature = issued_by.signature_image
    render_context = {**context, "principal_signature": signature.name if signature else ""}

    document = DocxTemplate(template.docx_file.path)
    # InlineImage must be built on the same DocxTemplate that renders it.
    context["principal_signature"] = (
        InlineImage(document, signature.path, width=SIGNATURE_WIDTH) if signature else ""
    )
    document.render(context, jinja_env=SandboxedEnvironment(), autoescape=True)
    if settings.DEMO_MODE:
        _insert_specimen_line(document.docx)
    buffer = BytesIO()
    document.save(buffer)

    order = Order(
        order_no=order_no,
        order_date=order_date,
        academic_year=academic_year,
        committee=committee,
        order_type=OrderType.ASSIGNMENT,
        issued_by=issued_by,
        template_used=template,
        render_context=render_context,
        remarks=remarks,
        references=references,
    )
    order.generated_file.save(f"{order_no}.docx", ContentFile(buffer.getvalue()), save=False)
    try:
        order.save()
        created = [
            assign_committee(
                holder=holder,
                committee=committee,
                role=role,
                order=order,
                effective_date=effective_date,
            )
            for holder, role in appointments
        ]
    except Exception:
        # The transaction discards the rows; the stored file must not outlive them.
        order.generated_file.storage.delete(order.generated_file.name)
        raise

    named = ", ".join(row["name"] for row in members)
    audit.log(
        action=AuditAction.ORDER_ISSUED,
        actor=issued_by,
        obj=order,
        summary=f"{order_no} issued: {named} — {committee.name}"[:255],
        detail={
            "order_type": OrderType.ASSIGNMENT,
            "assignment_ids": [a.pk for a in created],
            "superseded_assignment_id": previous_lead.pk if previous_lead else None,
            "template_id": template.pk,
            "demo_mode": settings.DEMO_MODE,
        },
        request=request,
    )
    appointed = "; ".join(f"{row['name']} appointed {row['role']}" for row in members)
    message = f"{committee.name}: {appointed}."
    if previous_lead is not None:
        message += (
            f" {previous_lead.holder_name} is no longer {previous_lead.get_role_display()}."
        )
    notify_committee(
        committee=committee,
        order=order,
        message=f"{message} Order {order_no}.",
        also=[previous_lead.faculty] if previous_lead and previous_lead.faculty else [],
        exclude=issued_by,
    )
    return order


def _insert_specimen_line(document):
    """Make the demo specimen line the first paragraph of the document body."""
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(SPECIMEN_LINE)
    run.bold = True
    body = document.element.body
    body.remove(paragraph._p)
    body.insert(0, paragraph._p)


def _build_plain_order(*, heading, subject, body_paragraphs, order_no, order_date, issued_by):
    """
    Build a relinquishment or corrigendum document.

    These are not rendered from a committee template: a committee's template
    says "is hereby appointed", which would be false on an order that ends or
    withdraws an appointment. The layout follows the same office-order shape.
    """
    document = DocxDocument()

    for line, bold in ((settings.INSTITUTION_NAME.upper(), True), ("Kutch - 370001", False)):
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.add_run(line).bold = bold

    reference = document.add_paragraph()
    reference.add_run(
        "No: {}\t\tDate: {}".format(order_no, order_date.strftime(DOCUMENT_DATE_FORMAT))
    )

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run(heading).bold = True

    document.add_paragraph().add_run("Subject: " + subject).bold = True
    for text in body_paragraphs:
        document.add_paragraph(text)

    document.add_paragraph()
    signature = document.add_paragraph()
    signature.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    if issued_by.signature_image:
        signature.add_run().add_picture(issued_by.signature_image.path, width=SIGNATURE_WIDTH)
    for line in (issued_by.full_name, "Principal", settings.INSTITUTION_NAME):
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        paragraph.add_run(line)

    if settings.DEMO_MODE:
        _insert_specimen_line(document)
    buffer = BytesIO()
    document.save(buffer)
    return buffer


def _store_order(order, buffer):
    """Attach the rendered document and save; remove the file if the row cannot be written."""
    order.generated_file.save(
        order.order_no + ".docx", ContentFile(buffer.getvalue()), save=False
    )
    try:
        order.save()
    except Exception:
        order.generated_file.storage.delete(order.generated_file.name)
        raise
    return order


@transaction.atomic
def issue_relinquishment_order(
    *, assignment, order_date, issued_by, remarks="", academic_year=None, request=None
):
    """
    End an assignment with no replacement, by order (BR-4).

    Invariants: same atomicity and numbering rules as an assignment order.
    The assignment row is never deleted; it becomes RELINQUISHED with this
    order as its ending_order.
    """
    if not issued_by.is_principal:
        raise NotPrincipal()
    if assignment.status != AssignmentStatus.ACTIVE:
        raise AssignmentNotActive()
    if academic_year is None:
        academic_year = AcademicYear.objects.current()
    if order_date > timezone.localdate():
        raise OrderDateInvalid(_("The order date cannot be in the future."))
    if not academic_year.contains(order_date):
        raise OrderDateInvalid(
            _("The order date %(date)s is outside the academic year %(year)s.")
            % {"date": order_date.strftime(DOCUMENT_DATE_FORMAT), "year": academic_year.label}
        )

    holder = assignment.holder
    committee = assignment.committee
    role_label = str(AssignmentRole(assignment.role).label)
    order_no = next_order_no(academic_year, committee)
    subject = "Relinquishment of {}, {} for the academic year {}.".format(
        role_label, committee.name, academic_year.label
    )
    body = [
        "{} {}, {}, is hereby relieved of the duties of {} of the {} of this institute "
        "with effect from {}.".format(
            holder.salutation,
            holder.full_name,
            assignment.holder_detail,
            role_label,
            committee.name,
            order_date.strftime(DOCUMENT_DATE_FORMAT),
        ),
        "The charge shall be handed over to this office until further orders.",
        "This is issued with the approval of the competent authority.",
    ]
    if remarks:
        body.append("Remarks: " + remarks)

    render_context = {
        "order_no": order_no,
        "order_date": order_date.strftime(DOCUMENT_DATE_FORMAT),
        "faculty_salutation": holder.salutation,
        "faculty_name": holder.full_name,
        "faculty_designation": assignment.holder_detail,
        "faculty_department": "",
        "committee_name": committee.name,
        "assignment_role": role_label,
        "academic_year": academic_year.label,
        "principal_name": issued_by.full_name,
        "principal_signature": issued_by.signature_image.name if issued_by.signature_image else "",
        "remarks": remarks or "-",
    }
    buffer = _build_plain_order(
        heading="OFFICE ORDER",
        subject=subject,
        body_paragraphs=body,
        order_no=order_no,
        order_date=order_date,
        issued_by=issued_by,
    )
    order = _store_order(
        Order(
            order_no=order_no,
            order_date=order_date,
            academic_year=academic_year,
            committee=committee,
            order_type=OrderType.RELINQUISHMENT,
            issued_by=issued_by,
            template_used=None,
            render_context=render_context,
            remarks=remarks,
        ),
        buffer,
    )
    relinquish_assignment(assignment=assignment, order=order)
    audit.log(
        action=AuditAction.ORDER_ISSUED,
        actor=issued_by,
        obj=order,
        summary="{} issued: {} relinquishes {} of {}".format(
            order_no, holder.full_name, role_label, committee.name
        ),
        detail={
            "order_type": OrderType.RELINQUISHMENT,
            "assignment_id": assignment.pk,
            "demo_mode": settings.DEMO_MODE,
        },
        request=request,
    )
    notify_committee(
        committee=committee,
        order=order,
        message=f"{committee.name}: {holder.full_name} removed as {role_label}. Order {order_no}.",
        also=[assignment.faculty] if assignment.faculty else [],
        exclude=issued_by,
    )
    return order


@transaction.atomic
def cancel_order(*, order, reason, issued_by, order_date=None, request=None):
    """
    Withdraw a mistaken order by issuing a corrigendum (BR-6).

    Invariants:
    - the cancelled order is never edited beyond its cancellation fields and
      never deleted; its document stays downloadable as part of the record;
    - its number is not released: the corrigendum takes a fresh one;
    - assignments it created become CANCELLED;
    - assignments it superseded return to ACTIVE, unless the role has since
      been filled again, in which case nothing is written and the Principal
      is told to cancel the later order first.
    """
    if not issued_by.is_principal:
        raise NotPrincipal()
    if order.is_cancelled:
        raise OrderAlreadyCancelled()
    if order.order_type == OrderType.CORRIGENDUM:
        raise OrderNotCancellable()
    reason = (reason or "").strip()
    if not reason:
        raise CancellationReasonRequired()
    order_date = order_date or timezone.localdate()
    if order_date > timezone.localdate():
        raise OrderDateInvalid(_("The order date cannot be in the future."))
    academic_year = AcademicYear.objects.current()

    order_no = next_order_no(academic_year, order.committee)
    subject = "Corrigendum to Order No. {} dated {}.".format(
        order.order_no, order.order_date.strftime(DOCUMENT_DATE_FORMAT)
    )
    created = list(
        order.created_assignments.select_related("faculty", "external_member", "committee")
    )
    restored = list(
        order.ended_assignments.select_related(
            "faculty", "external_member", "committee"
        ).filter(
            status__in=[AssignmentStatus.SUPERSEDED, AssignmentStatus.RELINQUISHED]
        )
    )
    body = [
        "Order No. {} dated {} regarding the {} is hereby cancelled with immediate effect.".format(
            order.order_no,
            order.order_date.strftime(DOCUMENT_DATE_FORMAT),
            order.committee.name,
        ),
        "Reason: " + reason,
    ]
    for assignment in created:
        body.append(
            "The appointment of {} {} as {} of the {} stands withdrawn.".format(
                assignment.holder.salutation,
                assignment.holder_name,
                assignment.get_role_display(),
                assignment.committee.name,
            )
        )
    for assignment in restored:
        body.append(
            "{} {} shall continue as {} of the {} as before.".format(
                assignment.holder.salutation,
                assignment.holder_name,
                assignment.get_role_display(),
                assignment.committee.name,
            )
        )
    body.append("This is issued with the approval of the competent authority.")

    render_context = {
        "order_no": order_no,
        "order_date": order_date.strftime(DOCUMENT_DATE_FORMAT),
        "cancelled_order_no": order.order_no,
        "cancelled_order_date": order.order_date.strftime(DOCUMENT_DATE_FORMAT),
        "committee_name": order.committee.name,
        "academic_year": academic_year.label,
        "principal_name": issued_by.full_name,
        "principal_signature": issued_by.signature_image.name if issued_by.signature_image else "",
        "cancellation_reason": reason,
        "withdrawn": [a.holder_name for a in created],
        "restored": [a.holder_name for a in restored],
    }
    buffer = _build_plain_order(
        heading="CORRIGENDUM",
        subject=subject,
        body_paragraphs=body,
        order_no=order_no,
        order_date=order_date,
        issued_by=issued_by,
    )
    corrigendum = _store_order(
        Order(
            order_no=order_no,
            order_date=order_date,
            academic_year=academic_year,
            committee=order.committee,
            order_type=OrderType.CORRIGENDUM,
            issued_by=issued_by,
            template_used=None,
            render_context=render_context,
            remarks=reason,
        ),
        buffer,
    )

    # Void what the order created before restoring what it displaced, or both
    # would be ACTIVE for a moment and break uniq_active_lead.
    for assignment in created:
        cancel_assignment(assignment=assignment, cancelling_order=corrigendum)
    for assignment in restored:
        restore_ended(assignment=assignment, actor=issued_by)

    order.is_cancelled = True
    order.cancelled_by_order = corrigendum
    order.cancellation_reason = reason
    order.save(update_fields=["is_cancelled", "cancelled_by_order", "cancellation_reason"])
    audit.log(
        action=AuditAction.ORDER_CANCELLED,
        actor=issued_by,
        obj=order,
        summary="{} cancelled by {}".format(order.order_no, order_no),
        detail={
            "corrigendum_order_no": order_no,
            "reason": reason,
            "cancelled_assignments": [a.pk for a in created],
            "restored_assignments": [a.pk for a in restored],
        },
        request=request,
    )
    changes = [f"{a.holder_name} is no longer {a.get_role_display()}" for a in created]
    changes += [f"{a.holder_name} is {a.get_role_display()} again" for a in restored]
    message = f"{order.committee.name}: order {order.order_no} cancelled by {order_no}."
    if changes:
        message += " " + "; ".join(changes) + "."
    notify_committee(
        committee=order.committee,
        order=corrigendum,
        message=message,
        also=[a.faculty for a in created if a.faculty],
        exclude=issued_by,
    )
    return corrigendum
