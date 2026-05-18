from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pharmacies", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="pharmacy",
            name="city",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="pharmacy",
            name="region",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
