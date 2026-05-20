from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "prescriptions",
            "0005_prescription_currency_prescription_total_price_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="signqualityreport",
            name="admin_notes",
            field=models.TextField(blank=True, default=""),
        ),
    ]
