"""
The order template: validation and installation. docs/03_SECURITY.md §5.

One template serves every committee (the college confirmed a single format).
"""

import zipfile

from django.db import transaction
from django.utils.translation import gettext as _
from docx.opc.exceptions import OpcError
from docxtpl import DocxTemplate
from jinja2 import TemplateError, meta
from jinja2.sandbox import SandboxedEnvironment
from lxml.etree import XMLSyntaxError

from audit import services as audit
from audit.models import AuditAction
from core.exceptions import TemplateRejected

from .models import OrderTemplate

# Every template needs these.
CORE_PLACEHOLDERS = frozenset(
    {
        "order_no",
        "order_date",
        "committee_name",
        "academic_year",
        "principal_name",
        "principal_signature",
    }
)
# ...and then either a table of everyone appointed, or the single-person fields.
MEMBER_LIST_PLACEHOLDER = "member_list"
SINGLE_PERSON_PLACEHOLDERS = frozenset(
    {
        "faculty_salutation",
        "faculty_name",
        "faculty_designation",
        "faculty_department",
        "assignment_role",
    }
)
REQUIRED_PLACEHOLDERS = CORE_PLACEHOLDERS | SINGLE_PERSON_PLACEHOLDERS

MAX_TEMPLATE_BYTES = 2 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
ZIP_MAGIC = b"PK\x03\x04"


def validate_template_file(uploaded_file):
    """
    Run the full validation chain and return the sorted placeholder names found.

    Raises TemplateRejected naming the problem. Writes nothing. Order of
    checks: extension, size, magic bytes, zip structure, zip-bomb guard,
    macro parts, parse, required placeholders.
    """
    if not (uploaded_file.name or "").lower().endswith(".docx"):
        raise TemplateRejected(
            _("Only .docx files are accepted. Macro-enabled files such as .docm are rejected.")
        )
    if uploaded_file.size > MAX_TEMPLATE_BYTES:
        raise TemplateRejected(_("The template must be 2 MB or smaller."))

    uploaded_file.seek(0)
    if uploaded_file.read(4) != ZIP_MAGIC:
        raise TemplateRejected(_("The file is not a valid Word document."))
    uploaded_file.seek(0)
    try:
        with zipfile.ZipFile(uploaded_file) as archive:
            entries = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise TemplateRejected(_("The file is not a valid Word document.")) from exc

    if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_BYTES:
        raise TemplateRejected(_("The template expands to more than 20 MB and was rejected."))
    names = {entry.filename.lower() for entry in entries}
    if any(name.endswith("vbaproject.bin") for name in names):
        raise TemplateRejected(
            _("The template contains macros. Save it as a plain .docx and upload again.")
        )
    if "word/document.xml" not in names:
        raise TemplateRejected(_("The file is not a valid Word document."))

    uploaded_file.seek(0)
    try:
        template = DocxTemplate(uploaded_file)
        template.init_docx(reload=False)
        # patch_xml turns docxtpl's row and paragraph tags ({%tr ... %},
        # {%p ... %}) into ordinary Jinja ones; without it a template that
        # loops over a member table fails to parse.
        xml = template.patch_xml(template.get_xml())
        found = meta.find_undeclared_variables(SandboxedEnvironment().parse(xml))
    except (OpcError, KeyError, ValueError, XMLSyntaxError, TemplateError, zipfile.BadZipFile) as exc:
        raise TemplateRejected(
            _("The template could not be read: %(error)s") % {"error": exc}
        ) from exc
    finally:
        uploaded_file.seek(0)

    missing = sorted(CORE_PLACEHOLDERS - found)
    if MEMBER_LIST_PLACEHOLDER not in found:
        # No member table, so the single-person fields must all be present.
        missing += sorted(SINGLE_PERSON_PLACEHOLDERS - found)
    if missing:
        raise TemplateRejected(
            _(
                "The template is missing %(names)s. Add them and upload again, or use "
                "{{ member_list }} to print a table of everyone appointed."
            )
            % {"names": ", ".join("{{ %s }}" % name for name in sorted(set(missing)))}
        )
    return sorted(found)


@transaction.atomic
def install_order_template(uploaded_file):
    """
    Validate `uploaded_file` and make it the template every new order uses.

    Invariants: an invalid file is rejected before anything is written; at
    most one template is in use; earlier ones are kept, because past orders
    were rendered from them (BR-7). Orders already issued are unaffected.
    """
    placeholders = validate_template_file(uploaded_file)
    OrderTemplate.objects.filter(is_active=True).update(is_active=False)
    template = OrderTemplate(detected_placeholders=placeholders, is_active=True)
    template.docx_file.save("order-template.docx", uploaded_file, save=False)
    try:
        template.save()
    except Exception:
        # The transaction discards the row; the stored file must not outlive it.
        template.docx_file.storage.delete(template.docx_file.name)
        raise

    audit.log(
        action=AuditAction.TEMPLATE_UPLOADED,
        obj=template,
        summary="Order template installed",
        detail={"placeholders": placeholders},
    )
    return template
