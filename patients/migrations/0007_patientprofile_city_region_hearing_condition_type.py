from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0006_patientmedicalinfo_blood_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="patientprofile",
            name="city",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="patientprofile",
            name="region",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="patientprofile",
            name="hearing_condition_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("hard_of_hearing", "ضعيف سمع"),
                    ("deaf_from_birth", "أصم منذ الولادة"),
                    ("deaf_due_to_accident", "أصم بسبب حادث"),
                ],
                default="",
                max_length=50,
            ),
        ),
    ]
