from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_alter_phoneotp_purpose")]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("admin", "Admin"),
                    ("pharmacist", "Pharmacist"),
                    ("doctor", "Doctor"),
                    ("patient", "Patient"),
                ],
                default="patient",
                max_length=20,
            ),
        ),
    ]
