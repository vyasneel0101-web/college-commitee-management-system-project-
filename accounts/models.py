from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Count, Q
from django.db.models.functions import Upper
from django.utils.translation import gettext_lazy as _

from .validators import validate_mobile, validate_signature_image


class Department(models.Model):
    name = models.CharField(_("name"), max_length=120, unique=True)
    code = models.CharField(_("code"), max_length=10, unique=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("department")
        verbose_name_plural = _("departments")
        constraints = [
            models.CheckConstraint(
                condition=Q(code=Upper("code")),
                name="department_code_uppercase",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


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


class UserQuerySet(models.QuerySet):
    def faculty_with_counts(self):
        """
        Active staff annotated with `active_count`, their number of ACTIVE
        assignments, busiest first. Superusers are technical operators, not
        staff, and are excluded.
        """
        return (
            self.filter(is_active=True, is_superuser=False)
            .select_related("department")
            # "ACTIVE" is AssignmentStatus.ACTIVE; imported by value to avoid
            # a circular import between accounts and assignments.
            .annotate(active_count=Count("assignments", filter=Q(assignments__status="ACTIVE")))
            .order_by("-active_count", "full_name")
        )


class UserManager(BaseUserManager.from_queryset(UserQuerySet)):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    A member of staff. Email is the identity; there is no username.

    `role` is never user-editable: it appears only in the Django admin for
    superusers and in management commands. docs/02_DATA_MODEL.md.
    """

    email = models.EmailField(_("email address"), unique=True)
    salutation = models.CharField(_("salutation"), max_length=10, blank=True)
    full_name = models.CharField(_("full name"), max_length=150)
    role = models.CharField(
        _("role"), max_length=20, choices=Role.choices, default=Role.FACULTY
    )
    designation = models.CharField(
        _("designation"), max_length=40, choices=Designation.choices
    )
    govt_class = models.CharField(
        _("government class"), max_length=20, choices=GovtClass.choices
    )
    department = models.ForeignKey(
        Department,
        verbose_name=_("department"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    employee_code = models.CharField(_("employee code"), max_length=30, blank=True)
    joining_date = models.DateField(_("joining date"), null=True, blank=True)
    mobile = models.CharField(
        _("mobile"), max_length=15, blank=True, validators=[validate_mobile]
    )
    signature_image = models.ImageField(
        _("signature image"),
        upload_to="signatures/",
        null=True,
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg"]),
            validate_signature_image,
        ],
    )
    is_active = models.BooleanField(_("active"), default=True)
    is_staff = models.BooleanField(_("admin access"), default=False)
    date_joined = models.DateTimeField(_("record created"), auto_now_add=True)
    created_by = models.ForeignKey(
        "self",
        verbose_name=_("created by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_users",
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["full_name"]
        verbose_name = _("user")
        verbose_name_plural = _("users")
        constraints = [
            models.UniqueConstraint(
                fields=["employee_code"],
                condition=~Q(employee_code=""),
                name="uniq_employee_code_when_set",
            ),
        ]

    def __str__(self):
        return self.full_name or self.email

    def clean(self):
        super().clean()
        self.email = self.email.strip().lower()

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name

    @property
    def is_principal(self):
        return self.role == Role.PRINCIPAL

    @property
    def active_assignments(self):
        return self.assignments.active()

    @property
    def active_committee_count(self):
        """One query per call. In list views use User.objects.faculty_with_counts()."""
        return self.active_assignments.count()
