from pathlib import Path

from django.conf import settings
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

from common.choices import PrescriptionStatusChoices, SignStatusChoices
from common.uploads import (
    validate_audio_upload,
    validate_image_upload,
    validate_video_upload,
)
from patients.models import PatientProfile, PatientSession
from transcriptions.validators import validate_transcription_audio_upload

from .models import (
    Prescription,
    PrescriptionAccessLog,
    PrescriptionItem,
    SignQualityReport,
)


def validate_unit_price_value(value):
    if value < 0:
        raise serializers.ValidationError("Unit price must not be negative.")
    return value


def validate_billing_quantity_value(value):
    if value is not None and value <= 0:
        raise serializers.ValidationError("Quantity must be greater than zero.")
    return value


def require_create_pricing(serializer, attrs):
    if serializer.partial:
        return
    errors = {}
    initial_data = getattr(serializer, "initial_data", {}) or {}
    has_unit_price = "unit_price" in attrs or "unit_price" in initial_data
    has_legacy_price = "price" in attrs or "price" in initial_data
    has_quantity = "quantity" in attrs or "quantity" in initial_data
    if not has_unit_price and not has_legacy_price:
        errors["unit_price"] = ["This field is required."]
    if not has_quantity:
        errors["quantity"] = ["This field is required."]
    if errors:
        raise serializers.ValidationError(errors)


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


def stable_error(detail, code):
    return serializers.ValidationError({"detail": detail, "code": code})


def validate_item_image_upload(uploaded_file):
    extension = Path(getattr(uploaded_file, "name", "") or "").suffix.lower()
    if extension not in settings.PHARMASIGN_ALLOWED_IMAGE_EXTENSIONS:
        raise stable_error("Unsupported image file type.", "unsupported_image_type")
    if uploaded_file.size > settings.PHARMASIGN_MAX_IMAGE_UPLOAD_BYTES:
        raise stable_error("Image file is too large.", "image_too_large")

    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    if (
        content_type
        and content_type not in settings.PHARMASIGN_ALLOWED_IMAGE_CONTENT_TYPES
    ):
        raise stable_error("Unsupported image file type.", "unsupported_image_type")

    position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else None
    try:
        Image.open(uploaded_file).verify()
    except (UnidentifiedImageError, OSError):
        raise stable_error("Invalid image file.", "invalid_image_file")
    finally:
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(position or 0)
    return uploaded_file


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
            "unit_price",
            "line_total",
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
        return None

    def get_raw_transcript(self, obj):
        return obj.instructions_transcript_raw or None

    def get_approved_instruction_text(self, obj):
        return obj.instructions_transcript_edited or None

    def get_transcription_status(self, obj):
        if obj.instructions_transcript_edited.strip():
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
            "unit_price",
            "quantity",
            "line_total",
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
        read_only_fields = (
            "id",
            "prescription",
            "line_total",
            "created_at",
            "updated_at",
        )


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
    def validate_price(self, value):
        return validate_unit_price_value(value)

    def validate_unit_price(self, value):
        return validate_unit_price_value(value)

    def validate_quantity(self, value):
        return validate_billing_quantity_value(value)

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
            "unit_price",
            "quantity",
            "line_total",
            "instructions_audio",
            "instructions_transcript_raw",
            "instructions_transcript_edited",
            "sign_language_video",
            "supporting_text",
            "sign_status",
            "is_confirmed",
        )
        read_only_fields = ("line_total",)

    def validate(self, attrs):
        require_create_pricing(self, attrs)
        if "unit_price" not in attrs and "price" in attrs:
            attrs["unit_price"] = attrs["price"]
        if "price" not in attrs and "unit_price" in attrs:
            attrs["price"] = attrs["unit_price"]
        return attrs


class PrescriptionItemUpdateSerializer(serializers.ModelSerializer):
    def validate_price(self, value):
        return validate_unit_price_value(value)

    def validate_unit_price(self, value):
        return validate_unit_price_value(value)

    def validate_quantity(self, value):
        return validate_billing_quantity_value(value)

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
            "unit_price",
            "quantity",
            "line_total",
            "instructions_audio",
            "instructions_transcript_raw",
            "instructions_transcript_edited",
            "sign_language_video",
            "supporting_text",
            "sign_status",
            "is_confirmed",
        )
        read_only_fields = ("line_total",)

    def validate(self, attrs):
        if "unit_price" not in attrs and "price" in attrs:
            attrs["unit_price"] = attrs["price"]
        if "price" not in attrs and "unit_price" in attrs:
            attrs["price"] = attrs["unit_price"]
        return attrs


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
            "total_price",
            "currency",
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
            "total_price",
            "currency",
        )

    def get_patient(self, obj):
        return build_prescription_patient_payload(obj.patient)

    def get_pharmacist(self, obj):
        return build_prescription_pharmacist_payload(obj.pharmacist)

    def get_pharmacy(self, obj):
        return build_prescription_pharmacy_payload(obj.pharmacy)


class AdminPrescriptionLogListSerializer(serializers.ModelSerializer):
    patient = serializers.SerializerMethodField()
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    pharmacy = serializers.SerializerMethodField()
    pharmacy_name = serializers.CharField(source="pharmacy.name", read_only=True)
    pharmacist = serializers.SerializerMethodField()
    pharmacist_name = serializers.CharField(source="pharmacist.full_name", read_only=True)
    date = serializers.SerializerMethodField()
    medicines_count = serializers.SerializerMethodField()

    class Meta:
        model = Prescription
        fields = (
            "id",
            "patient",
            "patient_name",
            "pharmacy",
            "pharmacy_name",
            "pharmacist",
            "pharmacist_name",
            "doctor_name",
            "doctor_specialty",
            "diagnosis",
            "date",
            "prescribed_at",
            "submitted_at",
            "delivered_at",
            "medicines_count",
            "status",
            "notes",
            "total_price",
            "currency",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_patient(self, obj):
        return {
            "id": obj.patient_id,
            "full_name": obj.patient.full_name,
            "phone_number": obj.patient.phone_number or obj.patient.user.phone_number or "",
        }

    def get_pharmacy(self, obj):
        return {
            "id": obj.pharmacy_id,
            "name": obj.pharmacy.name,
        }

    def get_pharmacist(self, obj):
        return {
            "id": obj.pharmacist_id,
            "full_name": obj.pharmacist.full_name,
        }

    def get_date(self, obj):
        return obj.submitted_at or obj.prescribed_at or obj.created_at

    def get_medicines_count(self, obj):
        if hasattr(obj, "medicines_count"):
            return obj.medicines_count
        return obj.items.count()


class AdminPrescriptionLogItemSerializer(serializers.ModelSerializer):
    instructions = serializers.CharField(source="instructions_text", read_only=True)
    raw_transcript = serializers.CharField(
        source="instructions_transcript_raw",
        read_only=True,
    )
    edited_transcript = serializers.CharField(
        source="instructions_transcript_edited",
        read_only=True,
    )
    sign_video_url = serializers.SerializerMethodField()

    class Meta:
        model = PrescriptionItem
        fields = (
            "id",
            "medicine_name",
            "dosage",
            "frequency",
            "duration",
            "instructions",
            "unit_price",
            "quantity",
            "line_total",
            "transcription_status",
            "sign_status",
            "raw_transcript",
            "edited_transcript",
            "sign_video_url",
        )
        read_only_fields = fields

    def get_sign_video_url(self, obj):
        return build_file_url(self, obj.sign_language_video)


class AdminPrescriptionAccessLogSerializer(serializers.ModelSerializer):
    accessed_by = serializers.SerializerMethodField()

    class Meta:
        model = PrescriptionAccessLog
        fields = (
            "id",
            "accessed_by",
            "access_type",
            "timestamp",
        )
        read_only_fields = fields

    def get_accessed_by(self, obj):
        if obj.accessed_by_id is None:
            return None
        return {
            "id": obj.accessed_by_id,
            "role": obj.accessed_by.role,
            "email": obj.accessed_by.email,
            "phone_number": obj.accessed_by.phone_number,
        }


class AdminPrescriptionLogDetailSerializer(serializers.ModelSerializer):
    patient = serializers.SerializerMethodField()
    pharmacy = serializers.SerializerMethodField()
    pharmacist = serializers.SerializerMethodField()
    medicines_count = serializers.SerializerMethodField()
    items = AdminPrescriptionLogItemSerializer(many=True, read_only=True)
    access_logs = AdminPrescriptionAccessLogSerializer(many=True, read_only=True)

    class Meta:
        model = Prescription
        fields = (
            "id",
            "patient",
            "pharmacy",
            "pharmacist",
            "doctor_name",
            "doctor_specialty",
            "diagnosis",
            "status",
            "prescribed_at",
            "submitted_at",
            "delivered_at",
            "notes",
            "total_price",
            "currency",
            "medicines_count",
            "items",
            "access_logs",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_patient(self, obj):
        return {
            "id": obj.patient_id,
            "full_name": obj.patient.full_name,
            "phone_number": obj.patient.phone_number or obj.patient.user.phone_number or "",
            "gender": obj.patient.gender,
            "birth_date": obj.patient.birth_date,
            "hearing_disability_level": obj.patient.hearing_disability_level,
        }

    def get_pharmacy(self, obj):
        return {
            "id": obj.pharmacy_id,
            "name": obj.pharmacy.name,
            "phone_number": obj.pharmacy.phone_number,
            "address": obj.pharmacy.address,
        }

    def get_pharmacist(self, obj):
        return {
            "id": obj.pharmacist_id,
            "full_name": obj.pharmacist.full_name,
            "license_number": obj.pharmacist.license_number,
        }

    def get_medicines_count(self, obj):
        if hasattr(obj, "medicines_count"):
            return obj.medicines_count
        return obj.items.count()


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
    image = serializers.FileField(required=False, write_only=True)
    image_file = serializers.FileField(required=False, write_only=True)
    medication_image = serializers.FileField(required=False, write_only=True)
    medicine_image = serializers.FileField(required=False, write_only=True)
    price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
    )
    unit_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
    )

    def validate_price(self, value):
        return validate_unit_price_value(value)

    def validate_unit_price(self, value):
        return validate_unit_price_value(value)

    def validate_quantity(self, value):
        return validate_billing_quantity_value(value)

    def validate(self, attrs):
        medicine_name = attrs.pop("medication_name", None) or attrs.get("medicine_name")
        instructions_text = attrs.pop("instructions", None)
        image = (
            attrs.pop("image", None)
            or attrs.pop("image_file", None)
            or attrs.pop("medication_image", None)
            or attrs.pop("medicine_image", None)
        )
        if medicine_name is not None:
            attrs["medicine_name"] = medicine_name
        if instructions_text is not None:
            attrs["instructions_text"] = instructions_text
        if image is not None:
            attrs["medicine_image"] = validate_item_image_upload(image)
        require_create_pricing(self, attrs)
        if "unit_price" not in attrs and "price" in attrs:
            attrs["unit_price"] = attrs["price"]
        if "price" not in attrs and "unit_price" in attrs:
            attrs["price"] = attrs["unit_price"]
        if not self.partial and not attrs.get("medicine_name"):
            raise serializers.ValidationError(
                {"medication_name": "This field is required."}
            )
        return attrs


class PharmacistPrescriptionItemSerializer(PrescriptionItemContractSerializer):
    pass


class PharmacistPrescriptionItemAudioTranscriptionSerializer(serializers.Serializer):
    audio = serializers.FileField(required=False)
    audio_file = serializers.FileField(required=False, write_only=True)
    voice = serializers.FileField(required=False, write_only=True)

    def validate(self, attrs):
        audio = (
            attrs.get("audio")
            or attrs.get("audio_file")
            or attrs.get("voice")
        )
        if audio is None:
            raise stable_error("Audio file is required.", "missing_audio_file")
        attrs["audio"] = validate_transcription_audio_upload(audio)
        return attrs


class ApproveTranscriptSerializer(serializers.Serializer):
    approved_instruction_text = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if "approved_instruction_text" not in attrs:
            raise stable_error(
                "Approved instruction text is required.",
                "missing_approved_instruction_text",
            )
        return attrs

    def validate_approved_instruction_text(self, value):
        if not value.strip():
            raise stable_error(
                "Approved instruction text is required.",
                "missing_approved_instruction_text",
            )
        return value.strip()


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
            "total_price",
            "currency",
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


class SignQualityReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignQualityReport
        fields = (
            "id",
            "prescription",
            "prescription_item",
            "medicine_name",
            "approved_instruction_text",
            "report_type",
            "status",
            "created_at",
        )
        read_only_fields = fields


class PatientSignQualityReportCreateSerializer(serializers.Serializer):
    REPORT_TYPE_ALIASES = {
        "sign_unclear": SignQualityReport.REPORT_TYPE_SIGN_UNCLEAR,
        "الإشارة غير واضحة": SignQualityReport.REPORT_TYPE_SIGN_UNCLEAR,
    }

    report_type = serializers.CharField(required=False, allow_blank=True)

    def validate_report_type(self, value):
        value = value or SignQualityReport.REPORT_TYPE_SIGN_UNCLEAR
        try:
            return self.REPORT_TYPE_ALIASES[value]
        except KeyError:
            raise stable_error("Invalid report type.", "invalid_report_type")

    def validate(self, attrs):
        if "report_type" not in attrs:
            attrs["report_type"] = SignQualityReport.REPORT_TYPE_SIGN_UNCLEAR
        return attrs


class AdminSignQualityReportSerializer(serializers.ModelSerializer):
    patient = serializers.SerializerMethodField()
    prescription = serializers.IntegerField(source="prescription_id", read_only=True)
    prescription_item = serializers.IntegerField(
        source="prescription_item_id",
        read_only=True,
    )

    class Meta:
        model = SignQualityReport
        fields = (
            "id",
            "patient",
            "prescription",
            "prescription_item",
            "medicine_name",
            "approved_instruction_text",
            "report_type",
            "status",
            "created_at",
        )
        read_only_fields = fields

    def get_patient(self, obj):
        return build_prescription_patient_payload(obj.patient)


class AdminSignQualityReportUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignQualityReport
        fields = ("status",)
