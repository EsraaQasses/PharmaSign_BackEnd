from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("doctors", "0001_initial"),
        ("prescriptions", "0010_encrypt_existing_prescription_medical_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="prescription",
            name="medical_visit",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="prescriptions",
                to="doctors.medicalvisit",
            ),
        ),
        migrations.AddIndex(
            model_name="prescription",
            index=models.Index(fields=["medical_visit"], name="prescripti_medical_641f4b_idx"),
        ),
    ]
