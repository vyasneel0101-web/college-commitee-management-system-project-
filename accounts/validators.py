from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _
from PIL import Image

SIGNATURE_MAX_BYTES = 1024 * 1024
SIGNATURE_FORMATS = {"PNG", "JPEG"}

validate_mobile = RegexValidator(
    regex=r"^(\+91)?\d{10}$",
    message=_("Enter a 10-digit mobile number, optionally starting with +91."),
)


def validate_signature_image(file):
    """Accept only a PNG or JPEG under 1 MB that Pillow can open. docs/10_SIGNATURE.md."""
    if file.size > SIGNATURE_MAX_BYTES:
        raise ValidationError(_("The signature image must be smaller than 1 MB."))
    try:
        file.seek(0)
        with Image.open(file) as image:
            image.verify()
            image_format = image.format
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise ValidationError(
            _("The signature image could not be read. Upload a PNG or JPEG file.")
        ) from exc
    finally:
        file.seek(0)
    if image_format not in SIGNATURE_FORMATS:
        raise ValidationError(_("The signature image must be a PNG or JPEG file."))
