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
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage
from jinja2.sandbox import SandboxedEnvironment

from assignments.models import AssignmentRole
from assignments.services import assign_committee, current_convener, validate_assignment
from audit import services as audit
from audit.models import AuditAction
from core.exceptions import NotPrincipal, OrderDateInvalid, PreviewOutdated, TemplateMissing
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
