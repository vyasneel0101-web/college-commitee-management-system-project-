"""
Order numbering, preview and document generation.

docs/02_DATA_MODEL.md, BR-1, BR-5, BR-7, docs/10_SIGNATURE.md, docs/08_DEMO_DATA.md §1.
"""

from dataclasses import dataclass
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage
from jinja2.sandbox import SandboxedEnvironment

from assignments.models import AssignmentRole, AssignmentStatus
from assignments.services import (
    assign_committee,
    cancel_assignment,
    current_convener,
    relinquish_assignment,
    restore_superseded,
    validate_assignment,
)
from audit import services as audit
from audit.models import AuditAction
from core.exceptions import (
    AssignmentNotActive,
    CancellationReasonRequired,
    NotPrincipal,
    OrderAlreadyCancelled,
    OrderDateInvalid,
    OrderNotCancellable,
    PreviewOutdated,
    TemplateMissing,
)
from core.models import AcademicYear

from .models import Order, OrderSequence, OrderType

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


def _check_assignment_order(*, committee, faculty, role, order_date, issued_by, academic_year):
    """Every check an assignment order must pass. Returns (year, template, previous holder)."""
    if not issued_by.is_principal:
        raise NotPrincipal()
    if academic_year is None:
        academic_year = AcademicYear.objects.current()
    if order_date > timezone.localdate():
        raise OrderDateInvalid(_("The order date cannot be in the future."))
    if not academic_year.contains(order_date):
        raise OrderDateInvalid(
            _("The order date %(date)s is outside the academic year %(year)s.")
            % {"date": order_date.strftime(DOCUMENT_DATE_FORMAT), "year": academic_year.label}
        )
    validate_assignment(faculty=faculty, committee=committee, role=role, order_date=order_date)
    template = committee.templates.filter(is_active=True).first()
    if template is None:
        raise TemplateMissing()
    previous_holder = current_convener(committee) if role == AssignmentRole.CONVENER else None
    return academic_year, template, previous_holder


def preview_assignment_order(
    *, committee, faculty, role, order_date, issued_by, academic_year=None
):
    """
    Run every check issue_assignment_order runs and describe what it would do.

    Invariant: writes nothing. The order number shown is expected, not
    reserved; the real number is assigned when the order is issued.
    """
    academic_year, template, previous_holder = _check_assignment_order(
        committee=committee,
        faculty=faculty,
        role=role,
        order_date=order_date,
        issued_by=issued_by,
        academic_year=academic_year,
    )
    return AssignmentPreview(
        academic_year=academic_year,
        expected_order_no=peek_next_order_no(academic_year, committee),
        template=template,
        previous_holder=previous_holder,
    )


@transaction.atomic
def issue_assignment_order(
    *,
    committee,
    faculty,
    role,
    order_date,
    issued_by,
    academic_year=None,
    effective_date=None,
    remarks="",
    expected_superseded_id=NOT_CHECKED,
    request=None,
):
    """
    Issue one assignment order: validate, number, render, store, record, assign.

    Invariants:
    - All or nothing. The order row, the assignment, any supersession, the
      sequence increment and the audit entries commit together; on failure
      the stored file is removed and nothing remains.
    - BR-1: the assignment exists only together with the order that created it.
    - BR-5: the number comes from next_order_no() and is never reused.
    - BR-7: the rendered .docx is stored once and never regenerated.
    - If `expected_superseded_id` is given (the holder the Principal saw in
      the preview, or None), the order is refused when the holder who would
      actually be superseded is different.
    - Under DEMO_MODE the specimen line is the first paragraph of the
      document. There is no argument that turns it off.
    - The render context is built from database objects only and rendered in
      a sandboxed Jinja environment.
    """
    academic_year, template, previous_holder = _check_assignment_order(
        committee=committee,
        faculty=faculty,
        role=role,
        order_date=order_date,
        issued_by=issued_by,
        academic_year=academic_year,
    )
    if expected_superseded_id is not NOT_CHECKED:
        actual_superseded_id = previous_holder.pk if previous_holder else None
        if actual_superseded_id != expected_superseded_id:
            raise PreviewOutdated()
    effective_date = effective_date or order_date

    order_no = next_order_no(academic_year, committee)
    context = {
        "order_no": order_no,
        "order_date": order_date.strftime(DOCUMENT_DATE_FORMAT),
        "faculty_salutation": faculty.salutation,
        "faculty_name": faculty.full_name,
        "faculty_designation": faculty.get_designation_display(),
        "faculty_department": faculty.department.name if faculty.department else "",
        "faculty_employee_code": faculty.employee_code,
        "committee_name": committee.name,
        "committee_description": committee.description,
        "assignment_role": str(AssignmentRole(role).label),
        "academic_year": academic_year.label,
        "principal_name": issued_by.full_name,
        "effective_date": effective_date.strftime(DOCUMENT_DATE_FORMAT),
        "previous_holder_name": previous_holder.faculty.full_name if previous_holder else "",
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
    )
    order.generated_file.save(f"{order_no}.docx", ContentFile(buffer.getvalue()), save=False)
    try:
        order.save()
        assignment = assign_committee(
            faculty=faculty,
            committee=committee,
            role=role,
            order=order,
            effective_date=effective_date,
        )
    except Exception:
        # The transaction discards the rows; the stored file must not outlive them.
        order.generated_file.storage.delete(order.generated_file.name)
        raise

    audit.log(
        action=AuditAction.ORDER_ISSUED,
        actor=issued_by,
        obj=order,
        summary=f"{order_no} issued: {faculty.full_name}, {context['assignment_role']} of {committee.name}",
        detail={
            "order_type": OrderType.ASSIGNMENT,
            "assignment_id": assignment.pk,
            "superseded_assignment_id": previous_holder.pk if previous_holder else None,
            "template_version": template.version,
            "demo_mode": settings.DEMO_MODE,
        },
        request=request,
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

    faculty = assignment.faculty
    committee = assignment.committee
    role_label = str(AssignmentRole(assignment.role).label)
    order_no = next_order_no(academic_year, committee)
    department = ", " + faculty.department.name if faculty.department else ""
    subject = "Relinquishment of {}, {} for the academic year {}.".format(
        role_label, committee.name, academic_year.label
    )
    body = [
        "{} {}, {}{}, is hereby relieved of the duties of {} of the {} of this institute "
        "with effect from {}.".format(
            faculty.salutation,
            faculty.full_name,
            faculty.get_designation_display(),
            department,
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
        "faculty_salutation": faculty.salutation,
        "faculty_name": faculty.full_name,
        "faculty_designation": faculty.get_designation_display(),
        "faculty_department": faculty.department.name if faculty.department else "",
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
            order_no, faculty.full_name, role_label, committee.name
        ),
        detail={
            "order_type": OrderType.RELINQUISHMENT,
            "assignment_id": assignment.pk,
            "demo_mode": settings.DEMO_MODE,
        },
        request=request,
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
    created = list(order.created_assignments.select_related("faculty", "committee"))
    restored = list(
        order.ended_assignments.select_related("faculty", "committee").filter(
            status=AssignmentStatus.SUPERSEDED
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
                assignment.faculty.salutation,
                assignment.faculty.full_name,
                assignment.get_role_display(),
                assignment.committee.name,
            )
        )
    for assignment in restored:
        body.append(
            "{} {} shall continue as {} of the {} as before.".format(
                assignment.faculty.salutation,
                assignment.faculty.full_name,
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
        "withdrawn": [a.faculty.full_name for a in created],
        "restored": [a.faculty.full_name for a in restored],
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
    # would be ACTIVE for a moment and break uniq_active_convener.
    for assignment in created:
        cancel_assignment(assignment=assignment, cancelling_order=corrigendum)
    for assignment in restored:
        restore_superseded(assignment=assignment, actor=issued_by)

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
    return corrigendum
