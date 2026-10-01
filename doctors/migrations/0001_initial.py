from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

import common.fields


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("patients", "0009_encrypt_existing_patient_medical_info"),
    ]

    operations = [
        migrations.CreateModel(
            name="DoctorProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("full_name", models.CharField(max_length=255)),
                ("specialty", models.CharField(blank=True, max_length=255)),
                ("license_number", models.CharField(blank=True, max_length=100)),
                ("workplace", models.CharField(blank=True, max_length=255)),
                ("phone_number", models.CharField(blank=True, max_length=20)),
                ("is_approved", models.BooleanField(db_index=True, default=False)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="doctor_profile", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("full_name",)},
        ),
        migrations.CreateModel(
            name="MedicalVisit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("visited_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("diagnosis", common.fields.EncryptedTextField(blank=True)),
                ("doctor_notes", common.fields.EncryptedTextField(blank=True)),
                ("follow_up_notes", common.fields.EncryptedTextField(blank=True)),
                ("follow_up_at", models.DateTimeField(blank=True, null=True)),
                ("doctor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="medical_visits", to="doctors.doctorprofile")),
                ("patient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="medical_visits", to="patients.patientprofile")),
            ],
            options={"ordering": ("-visited_at", "-created_at")},
        ),
        migrations.CreateModel(
            name="MedicalVisitMedication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("medicine_name", models.CharField(max_length=255)),
                ("dosage", models.CharField(blank=True, max_length=100)),
                ("frequency", models.CharField(blank=True, max_length=100)),
                ("duration", models.CharField(blank=True, max_length=100)),
                ("doctor_instructions", common.fields.EncryptedTextField(blank=True)),
                ("notes", common.fields.EncryptedTextField(blank=True)),
                ("visit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="medications", to="doctors.medicalvisit")),
            ],
            options={"ordering": ("created_at",)},
        ),
        migrations.AddIndex(model_name="doctorprofile", index=models.Index(fields=["is_approved"], name="doctors_doc_is_appr_04e403_idx")),
        migrations.AddIndex(model_name="doctorprofile", index=models.Index(fields=["specialty"], name="doctors_doc_special_4eab69_idx")),
        migrations.AddIndex(model_name="medicalvisit", index=models.Index(fields=["patient", "-visited_at"], name="doctors_med_patient_1d770e_idx")),
        migrations.AddIndex(model_name="medicalvisit", index=models.Index(fields=["doctor", "-visited_at"], name="doctors_med_doctor__ac1d3d_idx")),
        migrations.AddIndex(model_name="medicalvisitmedication", index=models.Index(fields=["visit", "medicine_name"], name="doctors_med_visit_i_65bcdc_idx")),
    ]
