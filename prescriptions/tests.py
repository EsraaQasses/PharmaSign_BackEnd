import io
import os
import shutil
from datetime import date
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from common.choices import (
    GenderChoices,
    PrescriptionStatusChoices,
    RoleChoices,
    SignStatusChoices,
    TranscriptionStatusChoices,
)
from organizations.models import Organization, OrganizationStaffProfile
from patients.models import PatientProfile, PatientSession
from pharmacies.models import PharmacistProfile, Pharmacy
from transcriptions.exceptions import AudioTranscriptionError

from .models import Prescription, PrescriptionAccessLog, PrescriptionItem


class PrescriptionPermissionTests(APITestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name="Org A")
        self.org_b = Organization.objects.create(name="Org B")

        self.patient_one_user = User.objects.create_user(
            email="patient.one@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        self.patient_one = PatientProfile.objects.create(
            user=self.patient_one_user,
            organization=self.org_a,
            full_name="Patient One",
            birth_date=date(1995, 1, 1),
            gender=GenderChoices.MALE,
        )

        self.patient_two_user = User.objects.create_user(
            email="patient.two@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        self.patient_two = PatientProfile.objects.create(
            user=self.patient_two_user,
            organization=self.org_b,
            full_name="Patient Two",
            birth_date=date(1996, 1, 1),
            gender=GenderChoices.FEMALE,
        )

        self.pharmacist_user = User.objects.create_user(
            email="pharmacist.allowed@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        self.pharmacy = Pharmacy.objects.create(
            name="Contracted Pharmacy",
            address="Damascus",
            organization=self.org_a,
            is_contracted_with_organization=True,
        )
        self.pharmacist = PharmacistProfile.objects.create(
            user=self.pharmacist_user,
            pharmacy=self.pharmacy,
            full_name="Allowed Pharmacist",
            is_approved=True,
        )

        self.prescription = Prescription.objects.create(
            patient=self.patient_two,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            doctor_name="Doctor Two",
        )

    def test_patient_cannot_access_another_patients_prescription(self):
        self.client.force_authenticate(self.patient_one_user)
        response = self.client.get(
            reverse("prescription-detail", kwargs={"pk": self.prescription.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pharmacist_can_only_create_prescription_for_allowed_patient_scope(self):
        self.client.force_authenticate(self.pharmacist_user)

        allowed_response = self.client.post(
            reverse("prescription-list"),
            {
                "patient": self.patient_one.id,
                "doctor_name": "Doctor Allowed",
                "doctor_specialty": "General",
            },
            format="json",
        )
        denied_response = self.client.post(
            reverse("prescription-list"),
            {
                "patient": self.patient_two.id,
                "doctor_name": "Doctor Denied",
                "doctor_specialty": "General",
            },
            format="json",
        )

        self.assertEqual(allowed_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(denied_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_without_manage_patients_cannot_retrieve_prescription(self):
        staff_user = User.objects.create_user(
            email="staff.no.patient.access@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=staff_user,
            organization=self.org_b,
            can_manage_patients=False,
            can_manage_pharmacists=True,
        )

        self.client.force_authenticate(staff_user)
        response = self.client.get(
            reverse("prescription-detail", kwargs={"pk": self.prescription.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_from_other_organization_cannot_retrieve_prescription_object(self):
        staff_user = User.objects.create_user(
            email="staff.other.org@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=staff_user,
            organization=self.org_a,
            can_manage_patients=True,
            can_manage_pharmacists=False,
        )

        self.client.force_authenticate(staff_user)
        response = self.client.get(
            reverse("prescription-detail", kwargs={"pk": self.prescription.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PharmacistPrescriptionMVPTests(APITestCase):
    def setUp(self):
        self.patient_user = User.objects.create_user(
            email="mvp.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
            phone_number="7000001",
        )
        self.patient = PatientProfile.objects.create(
            user=self.patient_user,
            full_name="MVP Patient",
            phone_number="7000001",
        )
        self.other_patient_user = User.objects.create_user(
            email="mvp.other.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
            phone_number="7000002",
        )
        self.other_patient = PatientProfile.objects.create(
            user=self.other_patient_user,
            full_name="Other MVP Patient",
            phone_number="7000002",
        )
        self.pharmacist_user = User.objects.create_user(
            email="mvp.pharmacist@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
            phone_number="7000003",
        )
        self.pharmacy = Pharmacy.objects.create(
            name="MVP Pharmacy",
            address="Damascus",
            phone_number="0111111111",
        )
        self.pharmacist = PharmacistProfile.objects.create(
            user=self.pharmacist_user,
            pharmacy=self.pharmacy,
            full_name="MVP Pharmacist",
            is_approved=True,
        )
        self.other_pharmacist_user = User.objects.create_user(
            email="mvp.other.pharmacist@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
            phone_number="7000004",
        )
        self.other_pharmacy = Pharmacy.objects.create(
            name="Other MVP Pharmacy",
            address="Aleppo",
        )
        self.other_pharmacist = PharmacistProfile.objects.create(
            user=self.other_pharmacist_user,
            pharmacy=self.other_pharmacy,
            full_name="Other MVP Pharmacist",
            is_approved=True,
        )
        self.unapproved_user = User.objects.create_user(
            email="mvp.unapproved@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
            phone_number="7000005",
        )
        self.unapproved_pharmacy = Pharmacy.objects.create(
            name="Unapproved MVP Pharmacy",
            address="Homs",
        )
        self.unapproved_pharmacist = PharmacistProfile.objects.create(
            user=self.unapproved_user,
            pharmacy=self.unapproved_pharmacy,
            full_name="Unapproved MVP Pharmacist",
            is_approved=False,
        )
        self.session = PatientSession.objects.create(
            patient=self.patient,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            status=PatientSession.STATUS_ACTIVE,
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )
        self.client.force_authenticate(self.pharmacist_user)

    def _create_payload(self, **overrides):
        payload = {
            "session_id": self.session.id,
            "patient_id": self.patient.id,
            "doctor_name": "Dr. Ahmad",
            "diagnosis": "Flu",
            "notes": "Take medicines after food",
            "items": [
                {
                    "medicine_name": "Paracetamol",
                    "dosage": "500mg",
                    "frequency": "3 times daily",
                    "duration": "5 days",
                    "instructions_text": (
                        "Take one tablet after food three times a day"
                    ),
                }
            ],
        }
        payload.update(overrides)
        return payload

    def _create_prescription(self, with_item=True, pharmacist=None, patient=None):
        pharmacist = pharmacist or self.pharmacist
        patient = patient or self.patient
        prescription = Prescription.objects.create(
            patient=patient,
            pharmacist=pharmacist,
            pharmacy=pharmacist.pharmacy,
            session=self.session if pharmacist == self.pharmacist else None,
            doctor_name="Draft Doctor",
            diagnosis="Draft Diagnosis",
        )
        if with_item:
            PrescriptionItem.objects.create(
                prescription=prescription,
                medicine_name="Draft Med",
                dosage="10mg",
                frequency="daily",
                duration="2 days",
                instructions_text="Take daily",
            )
        return prescription

    def assert_safe_prescription_nested_shapes(self, payload):
        self.assertEqual(
            set(payload["patient"].keys()),
            {"id", "full_name", "phone_number"},
        )
        self.assertEqual(
            set(payload["pharmacist"].keys()),
            {"id", "full_name"},
        )
        self.assertEqual(
            set(payload["pharmacy"].keys()),
            {"id", "name", "address", "phone_number"},
        )
        self.assertIn("items", payload)
        if payload["items"]:
            self.assertEqual(
                set(payload["items"][0].keys()),
                {
                    "id",
                    "medicine_name",
                    "dosage",
                    "frequency",
                    "duration",
                    "instructions_text",
                    "sign_status",
                },
            )
            blocked_item_fields = {
                "prescription",
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
                "is_confirmed",
                "created_at",
                "updated_at",
            }
            self.assertTrue(blocked_item_fields.isdisjoint(payload["items"][0].keys()))
        self.assertNotIn("email", payload["pharmacist"])
        self.assertNotIn("license_number", payload["pharmacist"])
        self.assertNotIn("is_approved", payload["pharmacist"])
        self.assertNotIn("pharmacy", payload["pharmacist"])
        self.assertNotIn("owner_user", payload["pharmacy"])
        self.assertNotIn("latitude", payload["pharmacy"])
        self.assertNotIn("longitude", payload["pharmacy"])
        self.assertNotIn("organization", payload["pharmacy"])
        self.assertNotIn("is_contracted_with_organization", payload["pharmacy"])

    def test_approved_pharmacist_can_create_prescription_with_valid_active_session(
        self,
    ):
        self.patient.qr_code_value = "sensitive-static-qr"
        self.patient.qr_is_active = True
        self.patient.save(update_fields=["qr_code_value", "qr_is_active", "updated_at"])

        response = self.client.post(
            reverse("pharmacist-prescriptions"),
            self._create_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], PrescriptionStatusChoices.DRAFT)
        self.assertEqual(response.data["session_id"], self.session.id)
        self.assertEqual(response.data["patient"]["id"], self.patient.id)
        self.assertEqual(
            set(response.data["patient"].keys()),
            {"id", "full_name", "phone_number"},
        )
        self.assertNotIn("qr_code_value", response.data["patient"])
        self.assert_safe_prescription_nested_shapes(response.data)
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(
            response.data["items"][0]["sign_status"], SignStatusChoices.PENDING
        )

    def test_unapproved_pharmacist_cannot_create_prescription(self):
        self.client.force_authenticate(self.unapproved_user)
        session = PatientSession.objects.create(
            patient=self.patient,
            pharmacist=self.unapproved_pharmacist,
            pharmacy=self.unapproved_pharmacy,
            status=PatientSession.STATUS_ACTIVE,
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )

        response = self.client.post(
            reverse("pharmacist-prescriptions"),
            self._create_payload(session_id=session.id),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Pharmacist account is not approved.")

    def test_pharmacist_cannot_create_prescription_without_session(self):
        response = self.client.post(
            reverse("pharmacist-prescriptions"),
            {
                "patient_id": self.patient.id,
                "doctor_name": "Dr. Ahmad",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("session_id", response.data)

    def test_pharmacist_cannot_use_expired_or_completed_session(self):
        expired_session = PatientSession.objects.create(
            patient=self.patient,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            status=PatientSession.STATUS_ACTIVE,
            expires_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        completed_session = PatientSession.objects.create(
            patient=self.patient,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            status=PatientSession.STATUS_COMPLETED,
            ended_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )

        expired_response = self.client.post(
            reverse("pharmacist-prescriptions"),
            self._create_payload(session_id=expired_session.id),
            format="json",
        )
        completed_response = self.client.post(
            reverse("pharmacist-prescriptions"),
            self._create_payload(session_id=completed_session.id),
            format="json",
        )

        self.assertEqual(expired_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(completed_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            expired_response.data["detail"][0],
            "A valid active patient session is required to create a prescription.",
        )

    def test_pharmacist_cannot_use_session_belonging_to_another_pharmacist(self):
        other_session = PatientSession.objects.create(
            patient=self.patient,
            pharmacist=self.other_pharmacist,
            pharmacy=self.other_pharmacy,
            status=PatientSession.STATUS_ACTIVE,
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )

        response = self.client.post(
            reverse("pharmacist-prescriptions"),
            self._create_payload(session_id=other_session.id),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"][0], "Invalid patient session.")

    def test_patient_id_must_match_session_patient(self):
        response = self.client.post(
            reverse("pharmacist-prescriptions"),
            self._create_payload(patient_id=self.other_patient.id),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"][0],
            "Session patient does not match requested patient.",
        )

    def test_pharmacist_can_list_only_own_prescriptions(self):
        own = self._create_prescription()
        other = self._create_prescription(pharmacist=self.other_pharmacist)

        response = self.client.get(reverse("pharmacist-prescriptions"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data}
        self.assertIn(own.id, ids)
        self.assertNotIn(other.id, ids)
        self.assertEqual(response.data[0]["item_count"], 1)

    def test_pharmacist_can_filter_prescriptions(self):
        draft = self._create_prescription()
        submitted = self._create_prescription()
        submitted.status = PrescriptionStatusChoices.SUBMITTED
        submitted.submitted_at = timezone.now()
        submitted.save(update_fields=["status", "submitted_at", "updated_at"])

        response = self.client.get(
            reverse("pharmacist-prescriptions"),
            {"status": PrescriptionStatusChoices.DRAFT, "patient_id": self.patient.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data}
        self.assertIn(draft.id, ids)
        self.assertNotIn(submitted.id, ids)

    def test_pharmacist_can_retrieve_own_prescription(self):
        prescription = self._create_prescription()

        response = self.client.get(
            reverse(
                "pharmacist-prescription-detail",
                kwargs={"prescription_id": prescription.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], prescription.id)
        self.assert_safe_prescription_nested_shapes(response.data)

    def test_pharmacist_cannot_retrieve_another_pharmacists_prescription(self):
        prescription = self._create_prescription(pharmacist=self.other_pharmacist)

        response = self.client.get(
            reverse(
                "pharmacist-prescription-detail",
                kwargs={"prescription_id": prescription.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pharmacist_can_update_draft_prescription(self):
        prescription = self._create_prescription()

        response = self.client.patch(
            reverse(
                "pharmacist-prescription-detail",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "doctor_name": "Dr. Updated",
                "diagnosis": "Updated",
                "notes": "Updated notes",
                "status": PrescriptionStatusChoices.SUBMITTED,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prescription.refresh_from_db()
        self.assertEqual(prescription.doctor_name, "Dr. Updated")
        self.assertEqual(prescription.status, PrescriptionStatusChoices.DRAFT)

    def test_pharmacist_cannot_update_submitted_prescription(self):
        prescription = self._create_prescription()
        prescription.status = PrescriptionStatusChoices.SUBMITTED
        prescription.submitted_at = timezone.now()
        prescription.save(update_fields=["status", "submitted_at", "updated_at"])

        response = self.client.patch(
            reverse(
                "pharmacist-prescription-detail",
                kwargs={"prescription_id": prescription.id},
            ),
            {"doctor_name": "Blocked"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "Only draft prescriptions can be modified.",
        )

    def test_pharmacist_can_add_update_delete_item_while_draft(self):
        prescription = self._create_prescription(with_item=False)

        add_response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "medicine_name": "Ibuprofen",
                "dosage": "400mg",
                "frequency": "twice daily",
                "duration": "3 days",
                "instructions_text": "Take after food",
            },
            format="json",
        )
        item_id = add_response.data["id"]
        update_response = self.client.patch(
            reverse(
                "pharmacist-prescription-item-detail",
                kwargs={"prescription_id": prescription.id, "item_id": item_id},
            ),
            {"frequency": "daily"},
            format="json",
        )
        delete_response = self.client.delete(
            reverse(
                "pharmacist-prescription-item-detail",
                kwargs={"prescription_id": prescription.id, "item_id": item_id},
            )
        )

        self.assertEqual(add_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(add_response.data["sign_status"], SignStatusChoices.PENDING)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["frequency"], "daily")
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def test_pharmacist_cannot_add_update_delete_item_after_submit(self):
        prescription = self._create_prescription()
        item = prescription.items.first()
        prescription.status = PrescriptionStatusChoices.SUBMITTED
        prescription.submitted_at = timezone.now()
        prescription.save(update_fields=["status", "submitted_at", "updated_at"])

        add_response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {"medicine_name": "Blocked"},
            format="json",
        )
        update_response = self.client.patch(
            reverse(
                "pharmacist-prescription-item-detail",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"frequency": "blocked"},
            format="json",
        )
        delete_response = self.client.delete(
            reverse(
                "pharmacist-prescription-item-detail",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            )
        )

        self.assertEqual(add_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(update_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(delete_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submit_fails_without_items(self):
        prescription = self._create_prescription(with_item=False)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-submit",
                kwargs={"prescription_id": prescription.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"][0],
            "Prescription must contain at least one medication item before submission.",
        )

    def test_submit_succeeds_with_at_least_one_item(self):
        prescription = self._create_prescription()

        response = self.client.post(
            reverse(
                "pharmacist-prescription-submit",
                kwargs={"prescription_id": prescription.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prescription.refresh_from_db()
        self.assertEqual(prescription.status, PrescriptionStatusChoices.SUBMITTED)
        self.assertIsNotNone(prescription.submitted_at)
        self.assertEqual(
            response.data["detail"], "Prescription submitted successfully."
        )

    def test_patient_can_list_submitted_prescriptions_but_not_drafts_by_default(self):
        draft = self._create_prescription()
        submitted = self._create_prescription()
        submitted.status = PrescriptionStatusChoices.SUBMITTED
        submitted.submitted_at = timezone.now()
        submitted.save(update_fields=["status", "submitted_at", "updated_at"])

        self.client.force_authenticate(self.patient_user)
        response = self.client.get(reverse("patient-prescription-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(submitted.id, ids)
        self.assertNotIn(draft.id, ids)

    def test_patient_can_retrieve_own_submitted_prescription(self):
        prescription = self._create_prescription()
        self.patient.qr_code_value = "patient-prescription-qr"
        self.patient.qr_is_active = True
        self.patient.save(update_fields=["qr_code_value", "qr_is_active", "updated_at"])
        prescription.status = PrescriptionStatusChoices.SUBMITTED
        prescription.submitted_at = timezone.now()
        prescription.save(update_fields=["status", "submitted_at", "updated_at"])

        self.client.force_authenticate(self.patient_user)
        response = self.client.get(
            reverse("patient-prescription-detail", kwargs={"pk": prescription.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], prescription.id)
        self.assertEqual(
            set(response.data["patient"].keys()),
            {"id", "full_name", "phone_number"},
        )
        self.assertNotIn("qr_code_value", response.data["patient"])
        self.assert_safe_prescription_nested_shapes(response.data)

    def test_patient_prescription_list_uses_safe_nested_shapes(self):
        prescription = self._create_prescription()
        prescription.status = PrescriptionStatusChoices.SUBMITTED
        prescription.submitted_at = timezone.now()
        prescription.save(update_fields=["status", "submitted_at", "updated_at"])

        self.client.force_authenticate(self.patient_user)
        response = self.client.get(reverse("patient-prescription-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assert_safe_prescription_nested_shapes(response.data["results"][0])

    def build_audio_upload(self, *, content_type="audio/mpeg", size=128):
        return SimpleUploadedFile(
            "instructions.mp3",
            b"a" * size,
            content_type=content_type,
        )

    @patch("prescriptions.views.transcribe_audio_file")
    def test_approved_pharmacist_can_transcribe_audio_for_own_draft_item(
        self, mock_transcribe
    ):
        mock_transcribe.return_value = "Take one tablet after food three times a day"
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"audio": self.build_audio_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Audio transcribed successfully.")
        item.refresh_from_db()
        self.assertEqual(
            item.instructions_text,
            "Take one tablet after food three times a day",
        )
        self.assertEqual(
            item.instructions_transcript_raw,
            "Take one tablet after food three times a day",
        )
        self.assertEqual(
            item.instructions_transcript_edited,
            "Take one tablet after food three times a day",
        )
        self.assertEqual(
            item.transcription_status,
            TranscriptionStatusChoices.COMPLETED,
        )
        self.assertEqual(item.transcription_provider, "groq_whisper")
        self.assertFalse(item.instructions_audio)
        self.assertEqual(
            set(response.data["item"].keys()),
            {
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
                "sign_status",
            },
        )
        mock_transcribe.assert_called_once()

    def test_transcribe_audio_requires_audio_file(self):
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("audio", response.data)

    def test_transcribe_audio_rejects_unsupported_audio_type(self):
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"audio": self.build_audio_upload(content_type="application/octet-stream")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["audio"][0], "Unsupported audio file type.")

    @override_settings(MAX_AUDIO_UPLOAD_SIZE_MB=1)
    def test_transcribe_audio_rejects_large_audio_file(self):
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"audio": self.build_audio_upload(size=(1024 * 1024) + 1)},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["audio"][0],
            "Audio file size must not exceed 1MB.",
        )

    def test_unapproved_pharmacist_cannot_transcribe_audio(self):
        self.client.force_authenticate(self.unapproved_user)
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"audio": self.build_audio_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Pharmacist account is not approved.")

    def test_pharmacist_cannot_transcribe_another_pharmacists_item(self):
        prescription = self._create_prescription(pharmacist=self.other_pharmacist)
        item = prescription.items.first()

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"audio": self.build_audio_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_cannot_transcribe_audio(self):
        prescription = self._create_prescription()
        item = prescription.items.first()
        self.client.force_authenticate(self.patient_user)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"audio": self.build_audio_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_submitted_prescription_cannot_be_transcribed(self):
        prescription = self._create_prescription()
        item = prescription.items.first()
        prescription.status = PrescriptionStatusChoices.SUBMITTED
        prescription.submitted_at = timezone.now()
        prescription.save(update_fields=["status", "submitted_at", "updated_at"])

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"audio": self.build_audio_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"], "Only draft prescriptions can be modified."
        )

    @patch("prescriptions.views.transcribe_audio_file")
    def test_whisper_failure_sets_failed_status_and_keeps_existing_text(
        self, mock_transcribe
    ):
        mock_transcribe.side_effect = AudioTranscriptionError("provider failed")
        prescription = self._create_prescription()
        item = prescription.items.first()
        item.instructions_text = "Existing text"
        item.save(update_fields=["instructions_text", "updated_at"])

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"audio": self.build_audio_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(
            response.data["detail"],
            "Audio transcription failed. Please try again.",
        )
        item.refresh_from_db()
        self.assertEqual(item.instructions_text, "Existing text")
        self.assertEqual(item.transcription_status, TranscriptionStatusChoices.FAILED)
        self.assertEqual(item.transcription_provider, "groq_whisper")
        self.assertEqual(
            item.transcription_error_message,
            "provider failed",
        )

    @patch("prescriptions.views.logger")
    @override_settings(DEBUG=True)
    @patch("prescriptions.views.transcribe_audio_file")
    def test_whisper_failure_logs_exception_during_debug(
        self, mock_transcribe, mock_logger
    ):
        mock_transcribe.side_effect = AudioTranscriptionError("debug provider failed")
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"audio": self.build_audio_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        mock_logger.exception.assert_called_once_with(
            "Audio transcription provider failed."
        )

    @patch("prescriptions.views.logger")
    @override_settings(DEBUG=False)
    @patch("prescriptions.views.transcribe_audio_file")
    def test_whisper_failure_does_not_log_exception_when_not_debug(
        self, mock_transcribe, mock_logger
    ):
        mock_transcribe.side_effect = AudioTranscriptionError("provider failed")
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"audio": self.build_audio_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        mock_logger.exception.assert_not_called()

    def test_patient_cannot_retrieve_another_patients_prescription(self):
        prescription = self._create_prescription(patient=self.other_patient)
        prescription.status = PrescriptionStatusChoices.SUBMITTED
        prescription.submitted_at = timezone.now()
        prescription.save(update_fields=["status", "submitted_at", "updated_at"])

        self.client.force_authenticate(self.patient_user)
        response = self.client.get(
            reverse("patient-prescription-detail", kwargs={"pk": prescription.id})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PrescriptionMediaUploadTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Upload Org")
        self.patient_user = User.objects.create_user(
            email="upload.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        self.patient = PatientProfile.objects.create(
            user=self.patient_user,
            organization=self.organization,
            full_name="Upload Patient",
            birth_date=date(1997, 3, 1),
            gender=GenderChoices.MALE,
        )
        self.pharmacist_user = User.objects.create_user(
            email="upload.pharmacist@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        self.pharmacy = Pharmacy.objects.create(
            name="Upload Pharmacy",
            address="Damascus",
            organization=self.organization,
            is_contracted_with_organization=True,
        )
        self.pharmacist = PharmacistProfile.objects.create(
            user=self.pharmacist_user,
            pharmacy=self.pharmacy,
            full_name="Upload Pharmacist",
            is_approved=True,
        )
        self.prescription = Prescription.objects.create(
            patient=self.patient,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            doctor_name="Upload Doctor",
        )
        self.client.force_authenticate(self.pharmacist_user)

    def _build_valid_png_upload(self, filename):
        buffer = io.BytesIO()
        image = Image.new("RGB", (1, 1), color="white")
        image.save(buffer, format="PNG")
        return SimpleUploadedFile(
            filename,
            buffer.getvalue(),
            content_type="image/png",
        )

    def test_add_item_rejects_invalid_audio_extension(self):
        invalid_audio = SimpleUploadedFile(
            "instructions.exe",
            b"not-audio",
            content_type="application/octet-stream",
        )

        response = self.client.post(
            reverse("prescription-add-item", kwargs={"pk": self.prescription.pk}),
            {
                "medicine_name": "Test Med",
                "price": "10.00",
                "instructions_audio": invalid_audio,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("instructions_audio", response.data)

    def test_add_item_rejects_invalid_image_binary(self):
        invalid_image = SimpleUploadedFile(
            "fake-image.png",
            b"not-a-real-image",
            content_type="image/png",
        )

        response = self.client.post(
            reverse("prescription-add-item", kwargs={"pk": self.prescription.pk}),
            {
                "medicine_name": "Test Med",
                "price": "10.00",
                "medicine_image": invalid_image,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("medicine_image", response.data)

    def test_add_item_stores_media_with_generated_filename(self):
        media_root = os.path.abspath("test_media_storage")
        os.makedirs(media_root, exist_ok=True)
        try:
            with override_settings(
                MEDIA_ROOT=media_root,
                FILE_UPLOAD_PERMISSIONS=None,
                FILE_UPLOAD_DIRECTORY_PERMISSIONS=None,
            ):
                valid_image = self._build_valid_png_upload("unsafe original name.png")

                response = self.client.post(
                    reverse(
                        "prescription-add-item", kwargs={"pk": self.prescription.pk}
                    ),
                    {
                        "medicine_name": "Stored Med",
                        "price": "15.00",
                        "medicine_image": valid_image,
                    },
                    format="multipart",
                )

                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                item_id = response.data["id"]
                item = Prescription.objects.get(pk=self.prescription.pk).items.get(
                    pk=item_id
                )
                self.assertTrue(
                    item.medicine_image.name.startswith(
                        f"prescriptions/{self.prescription.pk}/images/"
                    )
                )
                self.assertNotIn("unsafe original name", item.medicine_image.name)
                item.medicine_image.delete(save=False)
        finally:
            shutil.rmtree(media_root, ignore_errors=True)


class PrescriptionTranscriptionPipelineTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Transcription Org")
        self.patient_user = User.objects.create_user(
            email="transcription.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        self.patient = PatientProfile.objects.create(
            user=self.patient_user,
            organization=self.organization,
            full_name="Transcription Patient",
            birth_date=date(1997, 4, 1),
            gender=GenderChoices.MALE,
        )
        self.pharmacist_user = User.objects.create_user(
            email="transcription.pharmacist@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        self.pharmacy = Pharmacy.objects.create(
            name="Transcription Pharmacy",
            address="Damascus",
            organization=self.organization,
            is_contracted_with_organization=True,
        )
        self.pharmacist = PharmacistProfile.objects.create(
            user=self.pharmacist_user,
            pharmacy=self.pharmacy,
            full_name="Transcription Pharmacist",
            is_approved=True,
        )
        self.prescription = Prescription.objects.create(
            patient=self.patient,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            doctor_name="Transcription Doctor",
        )
        self.audio_file = SimpleUploadedFile(
            "instructions.mp3",
            b"fake-audio-content",
            content_type="audio/mpeg",
        )
        self.item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine_name="Transcription Med",
            price="20.00",
            instructions_audio=self.audio_file,
        )
        self.client.force_authenticate(self.pharmacist_user)

    @override_settings(PHARMASIGN_TRANSCRIPTION_PROVIDER="placeholder")
    def test_owner_pharmacist_can_transcribe_item(self):
        response = self.client.post(
            reverse("prescription-item-transcribe", kwargs={"pk": self.item.pk}),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.item.refresh_from_db()
        self.assertEqual(
            self.item.transcription_status,
            TranscriptionStatusChoices.COMPLETED,
        )
        self.assertEqual(self.item.transcription_provider, "placeholder")
        self.assertTrue(self.item.instructions_transcript_raw)
        self.assertEqual(
            self.item.instructions_transcript_edited,
            self.item.instructions_transcript_raw,
        )
        self.assertTrue(
            PrescriptionAccessLog.objects.filter(
                prescription=self.prescription,
                accessed_by=self.pharmacist_user,
                access_type="transcribe",
            ).exists()
        )

    def test_transcribe_rejects_item_without_audio(self):
        item_without_audio = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine_name="No Audio Med",
            price="11.00",
        )

        response = self.client.post(
            reverse(
                "prescription-item-transcribe", kwargs={"pk": item_without_audio.pk}
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "Cannot transcribe an item without instructions audio.",
        )

    @override_settings(PHARMASIGN_TRANSCRIPTION_PROVIDER="failing")
    def test_transcription_failure_marks_item_failed(self):
        response = self.client.post(
            reverse("prescription-item-transcribe", kwargs={"pk": self.item.pk}),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.item.refresh_from_db()
        self.assertEqual(
            self.item.transcription_status,
            TranscriptionStatusChoices.FAILED,
        )
        self.assertEqual(self.item.transcription_provider, "failing")
        self.assertTrue(self.item.transcription_error_message)

    def test_other_pharmacist_cannot_transcribe_foreign_item(self):
        other_user = User.objects.create_user(
            email="transcription.other@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        other_pharmacy = Pharmacy.objects.create(
            name="Other Pharmacy", address="Aleppo"
        )
        PharmacistProfile.objects.create(
            user=other_user,
            pharmacy=other_pharmacy,
            full_name="Other Pharmacist",
            is_approved=True,
        )

        self.client.force_authenticate(other_user)
        response = self.client.post(
            reverse("prescription-item-transcribe", kwargs={"pk": self.item.pk}),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
