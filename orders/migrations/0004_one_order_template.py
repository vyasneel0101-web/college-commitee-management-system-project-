"""
One order template for every committee (the college confirmed a single
format), replacing per-committee versioned templates.

Existing orders keep their stored documents (BR-7); only the link to the
retired per-committee template row is dropped.
"""

import django.db.models.deletion
from django.db import migrations, models

import orders.models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0003_order_references"),
        ("committees", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(model_name="order", name="template_used"),
        migrations.CreateModel(
            name="OrderTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("docx_file", models.FileField(max_length=255, upload_to=orders.models.order_template_path, verbose_name="Word file")),
                ("detected_placeholders", models.JSONField(blank=True, default=list, verbose_name="detected placeholders")),
                ("is_active", models.BooleanField(default=True, verbose_name="in use")),
                ("uploaded_at", models.DateTimeField(auto_now_add=True, verbose_name="installed at")),
            ],
            options={
                "verbose_name": "order template",
                "verbose_name_plural": "order templates",
                "ordering": ["-uploaded_at"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("is_active", True)),
                        fields=("is_active",),
                        name="one_order_template_in_use",
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name="order",
            name="template_used",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="orders.ordertemplate",
                verbose_name="template used",
            ),
        ),
    ]
