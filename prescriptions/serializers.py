from rest_framework import serializers

from common.choices import PrescriptionStatusChoices
from common.uploads import (
    validate_audio_upload,
    validate_image_upload,
    validate_video_upload,
)
from patients.models import PatientProfile
from patients.serializers import PatientProfileSerializer
from pharmacies.serializers import PharmacistProfileSerializer, PharmacySerializer

from .models import Prescription, PrescriptionItem


class PrescriptionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionItem
        fields = (
            'id',
            'prescription',
            'medicine_name',
            'medicine_image',
            'price',
            'quantity',
            'instructions_audio',
            'transcription_status',
            'transcription_provider',
            'transcription_requested_at',
            'transcription_completed_at',
            'transcription_error_message',
            'instructions_transcript_raw',
            'instructions_transcript_edited',
            'sign_language_video',
            'supporting_text',
            'is_confirmed',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'prescription', 'created_at', 'updated_at')


class PrescriptionItemCreateSerializer(serializers.ModelSerializer):
    def validate_medicine_image(self, value):
        if value:
            validate_image_upload(value)
        return value

    def validate_instructions_audio(self, value):
        if value:
            validate_audio_upload(value)
        return value

    def validate_sign_language_video(self, value):
        if value:
            validate_video_upload(value)
        return value

    class Meta:
        model = PrescriptionItem
        fields = (
            'medicine_name',
            'medicine_image',
            'price',
            'quantity',
            'instructions_audio',
            'instructions_transcript_raw',
            'instructions_transcript_edited',
            'sign_language_video',
            'supporting_text',
            'is_confirmed',
        )


class PrescriptionItemUpdateSerializer(serializers.ModelSerializer):
    def validate_medicine_image(self, value):
        if value:
            validate_image_upload(value)
        return value

    def validate_instructions_audio(self, value):
        if value:
            validate_audio_upload(value)
        return value

    def validate_sign_language_video(self, value):
        if value:
            validate_video_upload(value)
        return value

    class Meta:
        model = PrescriptionItem
        fields = (
            'medicine_name',
            'medicine_image',
            'price',
            'quantity',
            'instructions_audio',
            'instructions_transcript_raw',
            'instructions_transcript_edited',
            'sign_language_video',
            'supporting_text',
            'is_confirmed',
        )


class PrescriptionSerializer(serializers.ModelSerializer):
    patient = PatientProfileSerializer(read_only=True)
    pharmacist = PharmacistProfileSerializer(read_only=True)
    pharmacy = PharmacySerializer(read_only=True)
    items = PrescriptionItemSerializer(many=True, read_only=True)

    class Meta:
        model = Prescription
        fields = (
            'id',
            'patient',
            'pharmacist',
            'pharmacy',
            'doctor_name',
            'doctor_specialty',
            'status',
            'prescribed_at',
            'delivered_at',
            'notes',
            'reused_from',
            'created_at',
            'updated_at',
            'items',
        )
        read_only_fields = (
            'id',
            'patient',
            'pharmacist',
            'pharmacy',
            'status',
            'created_at',
            'updated_at',
            'items',
        )


class PrescriptionCreateSerializer(serializers.ModelSerializer):
    patient = serializers.PrimaryKeyRelatedField(queryset=PatientProfile.objects.all())

    class Meta:
        model = Prescription
        fields = (
            'patient',
            'doctor_name',
            'doctor_specialty',
            'prescribed_at',
            'notes',
            'reused_from',
        )


class PrescriptionConfirmSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[PrescriptionStatusChoices.CONFIRMED],
        default=PrescriptionStatusChoices.CONFIRMED,
    )


class PrescriptionItemTranscriptionRequestSerializer(serializers.Serializer):
    force = serializers.BooleanField(default=False)
