"""Per-committee templates are retired in favour of one order template."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("committees", "0001_initial"),
        ("orders", "0004_one_order_template"),
    ]

    operations = [migrations.DeleteModel(name="CommitteeTemplate")]
