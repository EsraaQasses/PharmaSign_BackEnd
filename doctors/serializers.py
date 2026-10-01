from rest_framework import serializers

from patients.models import PatientProfile

from .models import DoctorProfile, MedicalVisit, MedicalVisitMedication


class DoctorProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorProfile
        fields = (
            "id",
            "full_name",
            "specialty",
            "license_number",
            "workplace",
            "phone_number",
            "is_approved",
        )
        read_only_fields = ("id", "is_approved")


class MedicalVisitMedicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalVisitMedication
        fields = (
            "id",
            "medicine_name",
            "dosage",
            "frequency",
            "duration",
            "doctor_instructions",
            "notes",
        )
        read_only_fields = ("id",)


class MedicalVisitSerializer(serializers.ModelSerializer):
    medications = MedicalVisitMedicationSerializer(many=True)
    doctor = DoctorProfileSerializer(read_only=True)
    patient = serializers.PrimaryKeyRelatedField(queryset=PatientProfile.objects.all())

    class Meta:
        model = MedicalVisit
        fields = (
            "id",
            "patient",
            "doctor",
            "visited_at",
            "diagnosis",
            "doctor_notes",
            "follow_up_notes",
            "follow_up_at",
            "medications",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "doctor", "created_at", "updated_at")

    def create(self, validated_data):
        medications = validated_data.pop("medications", [])
        visit = MedicalVisit.objects.create(**validated_data)
        MedicalVisitMedication.objects.bulk_create(
            [MedicalVisitMedication(visit=visit, **item) for item in medications]
        )
        return visit

    def update(self, instance, validated_data):
        medications = validated_data.pop("medications", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if medications is not None:
            instance.medications.all().delete()
            MedicalVisitMedication.objects.bulk_create(
                [MedicalVisitMedication(visit=instance, **item) for item in medications]
            )
        return instance
