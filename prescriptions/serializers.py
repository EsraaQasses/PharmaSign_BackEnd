from rest_framework import serializers

from common.choices import PrescriptionStatusChoices, SignStatusChoices
from common.uploads import (
    validate_audio_upload,
    validate_image_upload,
    validate_video_upload,
)
from patients.models import PatientProfile, PatientSession
from transcriptions.validators import validate_transcription_audio_upload

from .models import Prescription, PrescriptionItem


def build_prescription_patient_payload(patient):
    return {
        "id": patient.id,
        "full_name": patient.full_name,
        "phone_number": patient.phone_number or patient.user.phone_number or "",
    }


def build_prescription_pharmacist_payload(pharmacist):
    return {
        "id": pharmacist.id,
        "full_name": pharmacist.full_name,
    }


def build_prescription_pharmacy_payload(pharmacy):
    return {
        "id": pharmacy.id,
        "name": pharmacy.name,
        "address": pharmacy.address,
        "phone_number": pharmacy.phone_number,
    }


def build_file_url(serializer, file_field):
    if not file_field:
        return None
    try:
        url = file_field.url
    except ValueError:
        return None
    request = serializer.context.get("request")
    if request:
        return request.build_absolute_uri(url)
    return url


class PrescriptionItemContractSerializer(serializers.ModelSerializer):
    medication_name = serializers.CharField(source="medicine_name", read_only=True)
    instructions = serializers.CharField(source="instructions_text", read_only=True)
    image_url = serializers.SerializerMethodField()
    audio_url = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
    raw_transcript = serializers.SerializerMethodField()
    approved_instruction_text = serializers.SerializerMethodField()
    gloss_text = serializers.CharField(source="supporting_text", read_only=True)
    transcription_status = serializers.SerializerMethodField()

    class Meta:
        model = PrescriptionItem
        fields = (
            "id",
            "medication_name",
            "dosage",
            "frequency",
            "duration",
            "instructions",
            "quantity",
            "price",
            "image_url",
            "audio_url",
            "video_url",
            "transcription_status",
            "raw_transcript",
            "approved_instruction_text",
            "gloss_text",
            "supporting_text",
            "sign_status",
            "is_confirmed",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_image_url(self, obj):
        return build_file_url(self, obj.medicine_image)

    def get_audio_url(self, obj):
        return build_file_url(self, obj.instructions_audio)

    def get_video_url(self, obj):
        return build_file_url(self, obj.sign_language_video)

    def get_raw_transcript(self, obj):
        return obj.instructions_transcript_raw or None

    def get_approved_instruction_text(self, obj):
        return obj.instructions_text or None

    def get_transcription_status(self, obj):
        if obj.instructions_text.strip():
            return "approved"
        return obj.transcription_status


class PrescriptionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionItem
        fields = (
            "id",
            "prescription",
            "medicine_name",
            "dosage",
            "frequency",
            "duration",
            "instructions_text",
            "medicine_image",
            "price",
            "quantity",
            "instructions_audio",
            "transcription_status",
            "transcription_provider",
            "transcription_requested_at",
            "transcription_completed_at",
            "transcription_error_message",
            "instructions_transcript_raw",
            "instructions_transcript_edited",
            "sign_language_video",
            "supporting_text",
            "sign_status",
            "is_confirmed",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "prescription", "created_at", "updated_at")


class SafePrescriptionItemSerializer(serializers.ModelSerializer):
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = PrescriptionItem
        fields = (
            "id",
            "medicine_name",
            "dosage",
            "frequency",
            "duration",
            "instructions_text",
            "supporting_text",
            "sign_status",
            "sign_language_video",
            "video_url",
        )
        read_only_fields = fields

    def get_video_url(self, obj):
        if not obj.sign_language_video:
            return None
        return obj.sign_language_video.url


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
            "medicine_name",
            "dosage",
            "frequency",
            "duration",
            "instructions_text",
            "medicine_image",
            "price",
            "quantity",
            "instructions_audio",
            "instructions_transcript_raw",
            "instructions_transcript_edited",
            "sign_language_video",
            "supporting_text",
            "sign_status",
            "is_confirmed",
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
            "medicine_name",
            "dosage",
            "frequency",
            "duration",
            "instructions_text",
            "medicine_image",
            "price",
            "quantity",
            "instructions_audio",
            "instructions_transcript_raw",
            "instructions_transcript_edited",
            "sign_language_video",
            "supporting_text",
            "sign_status",
            "is_confirmed",
        )


class PrescriptionSerializer(serializers.ModelSerializer):
    patient = serializers.SerializerMethodField()
    pharmacist = serializers.SerializerMethodField()
    pharmacy = serializers.SerializerMethodField()
    session_id = serializers.IntegerField(source="session.id", read_only=True)
    items = PrescriptionItemContractSerializer(many=True, read_only=True)

    class Meta:
        model = Prescription
        fields = (
            "id",
            "patient",
            "pharmacist",
            "pharmacy",
            "session_id",
            "session",
            "doctor_name",
            "doctor_specialty",
            "diagnosis",
            "status",
            "prescribed_at",
            "submitted_at",
            "delivered_at",
            "notes",
            "reused_from",
            "created_at",
            "updated_at",
            "items",
        )
        read_only_fields = (
            "id",
            "patient",
            "pharmacist",
            "pharmacy",
            "session",
            "status",
            "created_at",
            "updated_at",
            "items",
        )

    def get_patient(self, obj):
        return build_prescription_patient_payload(obj.patient)

    def get_pharmacist(self, obj):
        return build_prescription_pharmacist_payload(obj.pharmacist)

    def get_pharmacy(self, obj):
        return build_prescription_pharmacy_payload(obj.pharmacy)


class PrescriptionCreateSerializer(serializers.ModelSerializer):
    patient = serializers.PrimaryKeyRelatedField(queryset=PatientProfile.objects.all())

    class Meta:
        model = Prescription
        fields = (
            "patient",
            "doctor_name",
            "doctor_specialty",
            "diagnosis",
            "prescribed_at",
            "notes",
            "reused_from",
        )


class PrescriptionConfirmSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[PrescriptionStatusChoices.CONFIRMED],
        default=PrescriptionStatusChoices.CONFIRMED,
    )


class PrescriptionItemTranscriptionRequestSerializer(serializers.Serializer):
    force = serializers.BooleanField(default=False)


class PharmacistPrescriptionItemInputSerializer(serializers.Serializer):
    medicine_name = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )
    medication_name = serializers.CharField(
        max_length=255, required=False, allow_blank=True, write_only=True
    )
    dosage = serializers.CharField(max_length=100, required=False, allow_blank=True)
    frequency = serializers.CharField(max_length=100, required=False, allow_blank=True)
    duration = serializers.CharField(max_length=100, required=False, allow_blank=True)
    instructions_text = serializers.CharField(required=False, allow_blank=True)
    instructions = serializers.CharField(
        required=False, allow_blank=True, write_only=True
    )

    def validate(self, attrs):
        medicine_name = attrs.pop("medication_name", None) or attrs.get("medicine_name")
        instructions_text = attrs.pop("instructions", None)
        if medicine_name is not None:
            attrs["medicine_name"] = medicine_name
        if instructions_text is not None:
            attrs["instructions_text"] = instructions_text
        if not self.partial and not attrs.get("medicine_name"):
            raise serializers.ValidationError(
                {"medication_name": "This field is required."}
            )
        return attrs


class PharmacistPrescriptionItemSerializer(PrescriptionItemContractSerializer):
    pass


class PharmacistPrescriptionItemAudioTranscriptionSerializer(serializers.Serializer):
    audio = serializers.FileField()

    def validate_audio(self, value):
        return validate_transcription_audio_upload(value)


class ApproveTranscriptSerializer(serializers.Serializer):
    approved_instruction_text = serializers.CharField(required=True, allow_blank=False)


class TranscribedPrescriptionItemSerializer(serializers.ModelSerializer):
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = PrescriptionItem
        fields = (
            "id",
            "medicine_name",
            "dosage",
            "frequency",
            "duration",
            "instructions_text",
            "transcription_status",
            "transcription_provider",
            "instructions_transcript_raw",
            "instructions_transcript_edited",
            "supporting_text",
            "sign_status",
            "sign_language_video",
            "video_url",
        )
        read_only_fields = fields

    def get_video_url(self, obj):
        if not obj.sign_language_video:
            return None
        return obj.sign_language_video.url


class PharmacistPrescriptionSerializer(serializers.ModelSerializer):
    patient = serializers.SerializerMethodField()
    pharmacist = serializers.SerializerMethodField()
    pharmacy = serializers.SerializerMethodField()
    session_id = serializers.IntegerField(source="session.id", read_only=True)
    items = PharmacistPrescriptionItemSerializer(many=True, read_only=True)

    class Meta:
        model = Prescription
        fields = (
            "id",
            "patient",
            "pharmacist",
            "pharmacy",
            "session",
            "session_id",
            "doctor_name",
            "doctor_specialty",
            "diagnosis",
            "status",
            "prescribed_at",
            "submitted_at",
            "delivered_at",
            "notes",
            "items",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_patient(self, obj):
        return build_prescription_patient_payload(obj.patient)

    def get_pharmacist(self, obj):
        return build_prescription_pharmacist_payload(obj.pharmacist)

    def get_pharmacy(self, obj):
        return build_prescription_pharmacy_payload(obj.pharmacy)


class PharmacistPrescriptionListSerializer(PharmacistPrescriptionSerializer):
    item_count = serializers.SerializerMethodField()

    class Meta(PharmacistPrescriptionSerializer.Meta):
        fields = PharmacistPrescriptionSerializer.Meta.fields + ("item_count",)
        read_only_fields = fields

    def get_item_count(self, obj):
        if hasattr(obj, "item_count"):
            return obj.item_count
        return obj.items.count()


class PharmacistPrescriptionCreateSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    patient_id = serializers.IntegerField()
    doctor_name = serializers.CharField(max_length=255)
    doctor_specialty = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )
    diagnosis = serializers.CharField(max_length=255, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    items = PharmacistPrescriptionItemInputSerializer(many=True, required=False)

    def validate(self, attrs):
        request = self.context["request"]
        pharmacist = request.user.pharmacist_profile
        try:
            session = PatientSession.objects.select_related(
                "patient",
                "patient__user",
                "pharmacist",
                "pharmacy",
            ).get(pk=attrs["session_id"])
        except PatientSession.DoesNotExist:
            raise serializers.ValidationError({"detail": "Invalid patient session."})

        if session.pharmacist_id != pharmacist.id:
            raise serializers.ValidationError({"detail": "Invalid patient session."})
        if session.patient_id != attrs["patient_id"]:
            raise serializers.ValidationError(
                {"detail": "Session patient does not match requested patient."}
            )
        if session.status != PatientSession.STATUS_ACTIVE or session.ended_at:
            raise serializers.ValidationError(
                {
                    "detail": "A valid active patient session is required to create a prescription."
                }
            )
        if session.expires_at and session.expires_at <= self.context["now"]():
            raise serializers.ValidationError(
                {
                    "detail": "A valid active patient session is required to create a prescription."
                }
            )
        attrs["session"] = session
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        pharmacist = request.user.pharmacist_profile
        items_data = validated_data.pop("items", [])
        session = validated_data.pop("session")
        validated_data.pop("session_id", None)
        validated_data.pop("patient_id", None)
        prescription = Prescription.objects.create(
            patient=session.patient,
            pharmacist=pharmacist,
            pharmacy=pharmacist.pharmacy,
            session=session,
            status=PrescriptionStatusChoices.DRAFT,
            **validated_data,
        )
        for item_data in items_data:
            PrescriptionItem.objects.create(
                prescription=prescription,
                sign_status=SignStatusChoices.PENDING,
                **item_data,
            )
        return prescription


class PharmacistPrescriptionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prescription
        fields = ("doctor_name", "doctor_specialty", "diagnosis", "notes")


class PharmacistPrescriptionSubmitSerializer(serializers.Serializer):
    def validate(self, attrs):
        prescription = self.context["prescription"]
        if not prescription.items.exists():
            raise serializers.ValidationError(
                {
                    "detail": (
                        "Prescription must contain at least one medication item before submission."
                    )
                }
            )
        return attrs
