from django.utils.translation import gettext_lazy as _


class DomainError(Exception):
    """
    A business rule was violated. The message is written for the person using
    the system and may be shown to them as-is.
    """

    default_message = _("This action is not allowed.")

    def __init__(self, message=None):
        self.message = message or self.default_message
        super().__init__(self.message)

    def __str__(self):
        return str(self.message)


class RecordImmutable(DomainError):
    default_message = _("Official records cannot be changed or deleted.")


class NoCurrentAcademicYear(DomainError):
    default_message = _(
        "No academic year is marked as current. Mark one as current before issuing orders."
    )


class NotPrincipal(DomainError):
    default_message = _("Only the Principal can issue orders.")


class AssignmentConflict(DomainError):
    default_message = _("This faculty member already holds this role in this committee.")


class CommitteeInactive(DomainError):
    default_message = _("This committee is inactive and cannot receive new assignments.")


class FacultyInactive(DomainError):
    default_message = _("This faculty member is inactive and cannot be assigned.")


class RoleNotAllowed(DomainError):
    default_message = _("This committee has a convener only and does not take members.")


class OrderDateInvalid(DomainError):
    default_message = _("The order date is not valid.")


class TemplateMissing(DomainError):
    default_message = _(
        "This committee has no active order template. Upload one before issuing orders."
    )


class TemplateRejected(DomainError):
    default_message = _("The template was rejected.")
