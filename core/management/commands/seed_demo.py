"""
python manage.py seed_demo [--reset]

Demo data per docs/08_DEMO_DATA.md §2 and §3. Refuses to run unless
DEMO_MODE is True. Every order and assignment is created through the real
services, so a clean run exercises the whole order pipeline.
"""

import shutil
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Department, Designation, GovtClass, Role, User
from accounts.validators import validate_signature_image
from assignments.models import Assignment, AssignmentRole, AssignmentStatus
from assignments.services import expire_assignments_for_year
from audit.models import AuditLogEntry
from committees.models import Committee, CommitteeTemplate
from committees.services import upload_committee_template
from core.models import AcademicYear
from orders.models import Order, OrderSequence
from orders.services import issue_assignment_order

DEMO_DIR = settings.BASE_DIR / "templates" / "demo"
EMAIL_DOMAIN = "gpbhuj-demo.local"
DEMO_PASSWORD = "demo1234"
DEMO_MEDIA_SUBDIRS = ("orders", "templates", "signatures")

ACADEMIC_YEARS = [
    ("2025-26", date(2025, 6, 1), date(2026, 5, 31), False),
    ("2026-27", date(2026, 6, 1), date(2027, 5, 31), True),
]

DEPARTMENTS = [
    ("CE", "Civil Engineering"),
    ("ME", "Mechanical Engineering"),
    ("EE", "Electrical Engineering"),
    ("CO", "Computer Engineering"),
    ("EC", "Electronics & Communication Engineering"),
    ("SH", "Science & Humanities"),
]

# (code, name, allows multiple members)
COMMITTEES = [
    ("TPU", "Training & Placement Unit", True),
    ("EXAM", "Examination Committee", True),
    ("ARC", "Anti-Ragging Committee", True),
    ("WGC", "Women's Grievance Redressal Cell", True),
    ("IQAC", "Internal Quality Assurance Cell", True),
    ("LIB", "Library Committee", True),
    ("PUR", "Purchase Committee", True),
    ("DISC", "Discipline Committee", True),
    ("SPT", "Sports & Games Committee", True),
    ("CUL", "Cultural Committee", True),
    ("ICT", "Website & IT Committee", True),
    ("ALM", "Alumni Association Cell", False),
]

LEC, HOD = Designation.LECTURER, Designation.HEAD_OF_DEPARTMENT
C1, C2 = GovtClass.CLASS_I, GovtClass.CLASS_II

# Fictional people. (email local part, salutation, full name, designation, class, dept, joined)
PRINCIPAL = ("principal", "Dr.", "Rameshbhai Chauhan", Designation.PRINCIPAL, C1, None, date(2008, 7, 1))
FACULTY = [
    ("mihir.patel", "Shri", "Mihir Patel", LEC, C2, "CO", date(2012, 8, 16)),
    ("dipti.solanki", "Smt.", "Dipti Solanki", HOD, C1, "CO", date(2009, 6, 22)),
    ("kiran.vasava", "Shri", "Kiran Vasava", LEC, C2, "CO", date(2016, 1, 11)),
    ("nilesh.bhatt", "Dr.", "Nilesh Bhatt", HOD, C1, "ME", date(2008, 12, 1)),
    ("jayesh.rathod", "Shri", "Jayesh Rathod", LEC, C2, "ME", date(2018, 7, 2)),
    ("hetal.mistry", "Smt.", "Hetal Mistry", LEC, C2, "ME", date(2020, 2, 17)),
    ("bhavesh.gohil", "Shri", "Bhavesh Gohil", HOD, C1, "CE", date(2010, 9, 6)),
    ("rekha.damor", "Smt.", "Rekha Damor", LEC, C2, "CE", date(2019, 8, 1)),
    ("ashok.parmar", "Shri", "Ashok Parmar", LEC, C2, "CE", date(2014, 3, 24)),
    ("sanjay.trivedi", "Dr.", "Sanjay Trivedi", HOD, C1, "EE", date(2011, 6, 15)),
    ("pooja.joshi", "Smt.", "Pooja Joshi", LEC, C2, "EE", date(2021, 7, 12)),
    ("ketan.makwana", "Shri", "Ketan Makwana", HOD, C1, "EC", date(2013, 1, 7)),
    ("alka.desai", "Smt.", "Alka Desai", LEC, C2, "EC", date(2017, 10, 9)),
    ("vipul.shah", "Dr.", "Vipul Shah", HOD, C1, "SH", date(2015, 5, 4)),
    ("meera.pandya", "Smt.", "Meera Pandya", LEC, C2, "SH", date(2023, 6, 19)),
]

CON, MEM = AssignmentRole.CONVENER, AssignmentRole.MEMBER

# (committee, faculty, role, order date), issued in this order.
HISTORY_2025_26 = [
    ("TPU", "kiran.vasava", CON, date(2025, 6, 16)),
    ("EXAM", "nilesh.bhatt", CON, date(2025, 6, 16)),
    ("ARC", "dipti.solanki", CON, date(2025, 6, 18)),
    ("SPT", "jayesh.rathod", CON, date(2025, 6, 20)),
    ("LIB", "mihir.patel", MEM, date(2025, 7, 1)),
    ("CUL", "hetal.mistry", MEM, date(2025, 7, 3)),
    # In-year hand-over: supersedes Nilesh Bhatt.
    ("EXAM", "sanjay.trivedi", CON, date(2025, 11, 10)),
]
# Standing appointment carried into 2026-27, where Mihir Patel supersedes it.
CARRIED_FORWARD = {("TPU", "kiran.vasava", CON)}

CURRENT_2026_27 = [
    ("TPU", "mihir.patel", CON, date(2026, 6, 15)),
    ("TPU", "pooja.joshi", MEM, date(2026, 6, 15)),
    ("EXAM", "sanjay.trivedi", CON, date(2026, 6, 16)),
    ("EXAM", "mihir.patel", MEM, date(2026, 6, 16)),
    ("IQAC", "dipti.solanki", CON, date(2026, 6, 17)),
    ("IQAC", "mihir.patel", MEM, date(2026, 6, 17)),
    ("ARC", "ketan.makwana", CON, date(2026, 6, 18)),
    ("ARC", "dipti.solanki", MEM, date(2026, 6, 18)),
    ("WGC", "rekha.damor", CON, date(2026, 6, 19)),
    ("WGC", "hetal.mistry", MEM, date(2026, 6, 19)),
    ("LIB", "alka.desai", CON, date(2026, 6, 22)),
    ("LIB", "mihir.patel", MEM, date(2026, 6, 22)),
    ("PUR", "nilesh.bhatt", CON, date(2026, 6, 23)),
    ("DISC", "bhavesh.gohil", CON, date(2026, 6, 24)),
    ("DISC", "mihir.patel", MEM, date(2026, 6, 24)),
    ("SPT", "jayesh.rathod", CON, date(2026, 7, 1)),
    ("SPT", "ashok.parmar", MEM, date(2026, 7, 1)),
    ("CUL", "hetal.mistry", CON, date(2026, 7, 2)),
    ("CUL", "pooja.joshi", MEM, date(2026, 7, 2)),
    ("ICT", "mihir.patel", CON, date(2026, 7, 6)),
    ("ICT", "kiran.vasava", MEM, date(2026, 7, 6)),
    ("ALM", "vipul.shah", CON, date(2026, 7, 8)),
]

REMARKS = {
    "EXAM": "Duties for the semester-end examinations will be allotted by the convener.",
}


class Command(BaseCommand):
    help = "Load fictional demo data. Refuses to run unless DEMO_MODE is True."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Flush the database and demo media, then rebuild everything.",
        )

    def handle(self, *args, reset=False, **options):
        if not settings.DEMO_MODE:
            raise CommandError(
                "seed_demo refuses to run because DEMO_MODE is False. "
                "Demo data must never enter a live system."
            )
        if reset:
            self._reset()

        with transaction.atomic():
            years = self._academic_years()
            departments = self._departments()
            principal = self._person(PRINCIPAL, departments, Role.PRINCIPAL, mobile_index=1)
            faculty = {
                row[0]: self._person(row, departments, Role.FACULTY, mobile_index=index)
                for index, row in enumerate(FACULTY, start=2)
            }
            committees = self._committees()
            self._templates(committees, principal)
            self._signature(principal)

        if Order.objects.exists():
            self.stdout.write(
                self.style.WARNING(
                    "Orders already exist, so assignments were not seeded again. "
                    "Run with --reset to rebuild everything."
                )
            )
        else:
            with transaction.atomic():
                self._assignments(years, committees, principal, faculty)

        self._report()

    def _reset(self):
        self.stdout.write("Flushing the database and demo media.")
        call_command("flush", interactive=False, verbosity=0)
        media_root = Path(settings.MEDIA_ROOT).resolve()
        for name in DEMO_MEDIA_SUBDIRS:
            target = (media_root / name).resolve()
            if target.parent == media_root and target.is_dir():
                shutil.rmtree(target)

    def _academic_years(self):
        years = {}
        for label, start, end, is_current in ACADEMIC_YEARS:
            years[label], _created = AcademicYear.objects.get_or_create(
                label=label,
                defaults={"start_date": start, "end_date": end, "is_current": is_current},
            )
        return years

    def _departments(self):
        return {
            code: Department.objects.get_or_create(code=code, defaults={"name": name})[0]
            for code, name in DEPARTMENTS
        }

    def _person(self, row, departments, role, *, mobile_index):
        local, salutation, full_name, designation, govt_class, dept_code, joined = row
        user, created = User.objects.get_or_create(
            email=f"{local}@{EMAIL_DOMAIN}",
            defaults={
                "salutation": salutation,
                "full_name": full_name,
                "role": role,
                "designation": designation,
                "govt_class": govt_class,
                "department": departments.get(dept_code),
                "joining_date": joined,
                # Reserved-for-fiction range, never a real number.
                "mobile": f"+9190000000{mobile_index:02d}",
            },
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password"])
        return user

    def _committees(self):
        return {
            code: Committee.objects.get_or_create(
                code=code, defaults={"name": name, "allows_multiple_members": multiple}
            )[0]
            for code, name, multiple in COMMITTEES
        }

    def _templates(self, committees, principal):
        for code, committee in committees.items():
            if committee.templates.exists():
                continue
            # EXAM has its own circular format; TPU's office order is the fallback.
            source = DEMO_DIR / (
                "order_template_EXAM.docx" if code == "EXAM" else "order_template_TPU.docx"
            )
            with source.open("rb") as handle:
                upload_committee_template(
                    committee=committee,
                    uploaded_file=File(handle, name=source.name),
                    uploaded_by=principal,
                )

    def _signature(self, principal):
        if principal.signature_image:
            return
        source = DEMO_DIR / "demo_principal_signature.png"
        with source.open("rb") as handle:
            image = File(handle, name=source.name)
            validate_signature_image(image)
            principal.signature_image.save(source.name, image, save=True)

    def _assignments(self, years, committees, principal, faculty):
        def issue(row, academic_year):
            code, local, role, order_date = row
            return issue_assignment_order(
                committee=committees[code],
                faculty=faculty[local],
                role=role,
                order_date=order_date,
                issued_by=principal,
                academic_year=academic_year,
                remarks=REMARKS.get(code, ""),
            )

        carried = []
        for row in HISTORY_2025_26:
            order = issue(row, years["2025-26"])
            if row[:3] in CARRIED_FORWARD:
                carried.append(order.created_assignments.get())
        expire_assignments_for_year(years["2025-26"], carry_forward=carried)

        for row in CURRENT_2026_27:
            issue(row, years["2026-27"])

    def _report(self):
        active = Assignment.objects.active()
        counts = [
            ("Academic years", AcademicYear.objects.count()),
            ("Departments", Department.objects.count()),
            ("Users", User.objects.count()),
            ("  Principal", User.objects.filter(role=Role.PRINCIPAL).count()),
            ("  Faculty", User.objects.filter(role=Role.FACULTY).count()),
            ("Committees", Committee.objects.count()),
            ("Committee templates", CommitteeTemplate.objects.count()),
            ("Orders", Order.objects.count()),
            ("Order sequences", OrderSequence.objects.count()),
            ("Assignments", Assignment.objects.count()),
        ]
        counts += [
            (f"  {status.label.lower()}", Assignment.objects.filter(status=status).count())
            for status in AssignmentStatus
        ]
        counts.append(("Audit log entries", AuditLogEntry.objects.count()))

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        for label, value in counts:
            self.stdout.write(f"{label:<22}{value:>4}")
        self.stdout.write(f"Active assignments    {active.count():>4}")
        self.stdout.write("Heaviest workloads:")
        for user in User.objects.faculty_with_counts()[:3]:
            self.stdout.write(f"  {user.full_name:<20}{user.active_count:>2}")
