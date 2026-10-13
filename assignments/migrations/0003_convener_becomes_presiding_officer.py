"""
"Convener" was a guess; the college's real orders use Presiding Officer,
Nodal Officer, Member and External Member (docs/11_REAL_ORDERS.md §2).
"""

from django.db import migrations


def convener_to_presiding_officer(apps, schema_editor):
    apps.get_model("assignments", "Assignment").objects.filter(role="CONVENER").update(
        role="PRESIDING_OFFICER"
    )


def presiding_officer_to_convener(apps, schema_editor):
    apps.get_model("assignments", "Assignment").objects.filter(
        role="PRESIDING_OFFICER"
    ).update(role="CONVENER")


class Migration(migrations.Migration):
    dependencies = [("assignments", "0002_remove_assignment_uniq_active_convener_and_more")]

    operations = [
        migrations.RunPython(convener_to_presiding_officer, presiding_officer_to_convener),
    ]
