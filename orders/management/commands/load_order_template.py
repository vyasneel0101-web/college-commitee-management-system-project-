"""
python manage.py load_order_template path/to/template.docx

Installs the Word template every committee's orders are produced from. Run it
once at setup, and again only if the college changes its order format.
Orders already issued keep their original documents.
"""

from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from core.exceptions import TemplateRejected
from orders.order_template import install_order_template


class Command(BaseCommand):
    help = "Install the order template used for every committee."

    def add_arguments(self, parser):
        parser.add_argument("path", help="The .docx template to install.")

    def handle(self, *args, path, **options):
        source = Path(path)
        if not source.is_file():
            raise CommandError(f"No such file: {source}")
        with source.open("rb") as handle:
            try:
                install_order_template(File(handle, name=source.name))
            except TemplateRejected as exc:
                raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Installed {source.name} as the order template."))
