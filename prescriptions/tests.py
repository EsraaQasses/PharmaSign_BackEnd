import io
import json
import os
import shutil
from datetime import date, timedelta
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

from .constants import DOCTOR_SPECIALTY_LABELS
from .models import (
    Prescription,
    PrescriptionAccessLog,
    PrescriptionItem,
    SignQualityReport,
)
from .services import SignGenerationError


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

    def test_legacy_prescription_create_is_disabled_without_session(self):
        self.client.force_authenticate(self.pharmacist_user)

        response = self.client.post(
            reverse("prescription-list"),
            {
                "patient": self.patient_one.id,
                "doctor_name": "Doctor Allowed",
                "doctor_specialty": "General",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            (
                "Use /api/pharmacist/prescriptions/ with a valid active patient "
                "session to create prescriptions."
            ),
        )

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


class SignQualityReportTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Quality Org")
        self.patient_user = User.objects.create_user(
            email="quality.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
            phone_number="7100001",
        )
        self.patient = PatientProfile.objects.create(
            user=self.patient_user,
            organization=self.organization,
            full_name="Quality Patient",
            phone_number="7100001",
        )
        self.other_patient_user = User.objects.create_user(
            email="quality.other.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
            phone_number="7100002",
        )
        self.other_patient = PatientProfile.objects.create(
            user=self.other_patient_user,
            organization=self.organization,
            full_name="Other Quality Patient",
            phone_number="7100002",
        )
        self.pharmacist_user = User.objects.create_user(
            email="quality.pharmacist@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
            phone_number="7100003",
        )
        self.pharmacy = Pharmacy.objects.create(
            name="Quality Pharmacy",
            address="Damascus",
            city="Damascus",
            region="Mazza",
            phone_number="011710000",
            organization=self.organization,
            is_contracted_with_organization=True,
        )
        self.pharmacist = PharmacistProfile.objects.create(
            user=self.pharmacist_user,
            pharmacy=self.pharmacy,
            full_name="Quality Pharmacist",
            is_approved=True,
        )
        self.prescription = Prescription.objects.create(
            patient=self.patient,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            doctor_name="Quality Doctor",
            doctor_specialty="Quality Specialty",
            status=PrescriptionStatusChoices.SUBMITTED,
        )
        self.item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine_name="Snapshot Med",
            instructions_text="Instruction fallback",
            instructions_transcript_raw="Raw transcript fallback",
            instructions_transcript_edited="Approved instruction snapshot",
            supporting_text="Generated gloss",
            sign_status=SignStatusChoices.COMPLETED,
        )
        self.other_item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine_name="Other Snapshot Med",
            instructions_text="Other instruction",
            sign_status=SignStatusChoices.PENDING,
        )

    def report_url(self, item=None):
        return reverse(
            "patient-report-sign-issue",
            kwargs={"item_id": (item or self.item).id},
        )

    def test_patient_can_report_own_prescription_item(self):
        self.client.force_authenticate(self.patient_user)

        response = self.client.post(
            self.report_url(),
            {"report_type": "sign_unclear"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        report = SignQualityReport.objects.get()
        self.assertEqual(report.patient, self.patient)
        self.assertEqual(report.prescription, self.prescription)
        self.assertEqual(report.prescription_item, self.item)
        self.assertNotEqual(report.prescription_item, self.other_item)
        self.assertEqual(response.data["report"]["report_type"], "sign_unclear")
        self.assertEqual(response.data["report"]["status"], "open")

    def test_patient_can_report_with_arabic_report_type_alias(self):
        self.client.force_authenticate(self.patient_user)

        response = self.client.post(
            self.report_url(),
            {"report_type": "الإشارة غير واضحة"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["report"]["report_type"], "sign_unclear")

    def test_patient_cannot_report_another_patients_item(self):
        self.client.force_authenticate(self.other_patient_user)

        response = self.client.post(
            self.report_url(),
            {"report_type": "sign_unclear"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "item_not_found")
        self.assertFalse(SignQualityReport.objects.exists())

    def test_unauthenticated_report_request_fails(self):
        response = self.client.post(
            self.report_url(),
            {"report_type": "sign_unclear"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_pharmacist_cannot_use_patient_report_endpoint(self):
        self.client.force_authenticate(self.pharmacist_user)

        response = self.client.post(
            self.report_url(),
            {"report_type": "sign_unclear"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(SignQualityReport.objects.exists())

    def test_duplicate_open_report_returns_existing_report(self):
        self.client.force_authenticate(self.patient_user)
        first_response = self.client.post(
            self.report_url(),
            {"report_type": "sign_unclear"},
            format="json",
        )

        duplicate_response = self.client.post(
            self.report_url(),
            {"report_type": "sign_unclear"},
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(duplicate_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(duplicate_response.data["code"], "sign_quality_report_exists")
        self.assertEqual(SignQualityReport.objects.count(), 1)
        self.assertEqual(
            duplicate_response.data["report"]["id"],
            first_response.data["report"]["id"],
        )

    def test_invalid_report_type_fails(self):
        self.client.force_authenticate(self.patient_user)

        response = self.client.post(
            self.report_url(),
            {"report_type": "other"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "invalid_report_type")

    def test_report_stores_item_snapshots_and_does_not_mutate_sources(self):
        original_prescription_status = self.prescription.status
        original_sign_status = self.item.sign_status
        self.client.force_authenticate(self.patient_user)

        response = self.client.post(
            self.report_url(),
            {"report_type": "sign_unclear"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        report = SignQualityReport.objects.get()
        self.assertEqual(report.medicine_name, "Snapshot Med")
        self.assertEqual(
            report.approved_instruction_text,
            "Instruction fallback",
        )
        self.prescription.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.prescription.status, original_prescription_status)
        self.assertEqual(self.item.sign_status, original_sign_status)

    def test_report_snapshot_falls_back_to_raw_transcript(self):
        self.item.instructions_text = ""
        self.item.instructions_transcript_edited = ""
        self.item.save(
            update_fields=[
                "instructions_text",
                "instructions_transcript_edited",
                "updated_at",
            ]
        )
        self.client.force_authenticate(self.patient_user)

        response = self.client.post(
            self.report_url(),
            {"report_type": "sign_unclear"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            SignQualityReport.objects.get().approved_instruction_text,
            "Raw transcript fallback",
        )

    def test_admin_can_list_reports(self):
        report = SignQualityReport.objects.create(
            patient=self.patient,
            prescription=self.prescription,
            prescription_item=self.item,
            medicine_name=self.item.medicine_name,
            approved_instruction_text=self.item.instructions_transcript_edited,
            report_type=SignQualityReport.REPORT_TYPE_SIGN_UNCLEAR,
            admin_notes="Initial follow-up note",
        )
        admin_user = User.objects.create_user(
            email="quality.admin@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=admin_user,
            organization=self.organization,
            can_manage_patients=True,
            can_manage_pharmacists=False,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.get(reverse("admin-sign-quality-report-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]["id"], report.id)
        self.assertEqual(response.data["results"][0]["patient"]["id"], self.patient.id)
        self.assertEqual(
            response.data["results"][0]["patient"]["full_name"],
            self.patient.full_name,
        )
        self.assertEqual(
            response.data["results"][0]["patient"]["phone_number"],
            self.patient.phone_number,
        )
        self.assertEqual(
            response.data["results"][0]["doctor_name"],
            self.prescription.doctor_name,
        )
        self.assertEqual(
            response.data["results"][0]["doctor_specialty"],
            self.prescription.doctor_specialty,
        )
        self.assertEqual(
            response.data["results"][0]["pharmacist"]["id"],
            self.pharmacist.id,
        )
        self.assertEqual(
            response.data["results"][0]["pharmacist"]["full_name"],
            self.pharmacist.full_name,
        )
        self.assertEqual(
            response.data["results"][0]["pharmacist"]["phone_number"],
            self.pharmacist_user.phone_number,
        )
        self.assertEqual(
            response.data["results"][0]["pharmacy"]["id"],
            self.pharmacy.id,
        )
        self.assertEqual(
            response.data["results"][0]["pharmacy"]["name"],
            self.pharmacy.name,
        )
        self.assertEqual(
            response.data["results"][0]["pharmacy"]["phone_number"],
            self.pharmacy.phone_number,
        )
        self.assertEqual(
            response.data["results"][0]["pharmacy"]["city"],
            self.pharmacy.city,
        )
        self.assertEqual(
            response.data["results"][0]["pharmacy"]["region"],
            self.pharmacy.region,
        )
        self.assertEqual(
            response.data["results"][0]["prescription"]["id"],
            self.prescription.id,
        )
        self.assertEqual(
            response.data["results"][0]["prescription_item"]["id"],
            self.item.id,
        )
        self.assertEqual(
            response.data["results"][0]["prescription_item"]["medicine_name"],
            self.item.medicine_name,
        )
        self.assertNotEqual(
            response.data["results"][0]["prescription_item"]["id"],
            self.other_item.id,
        )
        self.assertNotIn("items", response.data["results"][0]["prescription"])
        self.assertEqual(response.data["results"][0]["medicine_name"], "Snapshot Med")
        self.assertEqual(
            response.data["results"][0]["admin_notes"],
            "Initial follow-up note",
        )

    def test_admin_report_detail_includes_contact_context(self):
        report = SignQualityReport.objects.create(
            patient=self.patient,
            prescription=self.prescription,
            prescription_item=self.item,
            medicine_name=self.item.medicine_name,
            approved_instruction_text=self.item.instructions_transcript_edited,
            report_type=SignQualityReport.REPORT_TYPE_SIGN_UNCLEAR,
        )
        admin_user = User.objects.create_user(
            email="quality.admin.detail@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=admin_user,
            organization=self.organization,
            can_manage_patients=True,
            can_manage_pharmacists=False,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.get(
            reverse("admin-sign-quality-report-detail", kwargs={"pk": report.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pharmacist"]["id"], self.pharmacist.id)
        self.assertEqual(response.data["pharmacy"]["id"], self.pharmacy.id)
        self.assertEqual(response.data["prescription_item"]["id"], self.item.id)
        self.assertNotIn("items", response.data["prescription"])
        self.assertEqual(response.data["admin_notes"], "")

    def test_admin_can_filter_reports_by_search_and_prescription_item_id(self):
        report = SignQualityReport.objects.create(
            patient=self.patient,
            prescription=self.prescription,
            prescription_item=self.item,
            medicine_name=self.item.medicine_name,
            approved_instruction_text=self.item.instructions_text,
            report_type=SignQualityReport.REPORT_TYPE_SIGN_UNCLEAR,
        )
        other_report = SignQualityReport.objects.create(
            patient=self.patient,
            prescription=self.prescription,
            prescription_item=self.other_item,
            medicine_name=self.other_item.medicine_name,
            approved_instruction_text=self.other_item.instructions_text,
            report_type=SignQualityReport.REPORT_TYPE_SIGN_UNCLEAR,
            status=SignQualityReport.STATUS_REVIEWED,
        )
        admin_user = User.objects.create_user(
            email="quality.admin.filter@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=admin_user,
            organization=self.organization,
            can_manage_patients=True,
            can_manage_pharmacists=False,
        )
        self.client.force_authenticate(admin_user)

        by_item = self.client.get(
            reverse("admin-sign-quality-report-list"),
            {"prescription_item_id": self.item.id},
        )
        by_search = self.client.get(
            reverse("admin-sign-quality-report-list"),
            {"search": "Snapshot Med"},
        )
        by_status = self.client.get(
            reverse("admin-sign-quality-report-list"),
            {"status": SignQualityReport.STATUS_REVIEWED},
        )

        self.assertEqual(by_item.status_code, status.HTTP_200_OK)
        self.assertEqual(by_item.data["count"], 1)
        self.assertEqual(by_item.data["results"][0]["id"], report.id)
        self.assertEqual(by_search.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(by_search.data["count"], 1)
        self.assertEqual(by_status.status_code, status.HTTP_200_OK)
        self.assertEqual(by_status.data["results"][0]["id"], other_report.id)

    def test_admin_can_update_report_status(self):
        report = SignQualityReport.objects.create(
            patient=self.patient,
            prescription=self.prescription,
            prescription_item=self.item,
            medicine_name=self.item.medicine_name,
            approved_instruction_text=self.item.instructions_transcript_edited,
            report_type=SignQualityReport.REPORT_TYPE_SIGN_UNCLEAR,
        )
        admin_user = User.objects.create_user(
            email="quality.admin.update@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=admin_user,
            organization=self.organization,
            can_manage_patients=True,
            can_manage_pharmacists=False,
        )
        self.client.force_authenticate(admin_user)

        for target_status in (
            SignQualityReport.STATUS_REVIEWED,
            SignQualityReport.STATUS_RESOLVED,
            SignQualityReport.STATUS_DISMISSED,
        ):
            response = self.client.patch(
                reverse("admin-sign-quality-report-detail", kwargs={"pk": report.id}),
                {
                    "status": target_status,
                    "patient": self.other_patient.id,
                    "prescription": 999999,
                    "prescription_item": self.other_item.id,
                    "medicine_name": "Changed",
                    "approved_instruction_text": "Changed",
                    "report_type": "changed",
                    "pharmacist": 999999,
                    "pharmacy": 999999,
                    "admin_notes": f"Follow-up note {target_status}",
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            report.refresh_from_db()
            self.assertEqual(report.status, target_status)
            self.assertEqual(report.admin_notes, f"Follow-up note {target_status}")
        self.assertEqual(report.patient, self.patient)
        self.assertEqual(report.prescription, self.prescription)
        self.assertEqual(report.prescription_item, self.item)
        self.assertEqual(report.medicine_name, self.item.medicine_name)
        self.assertEqual(
            report.approved_instruction_text,
            self.item.instructions_transcript_edited,
        )
        self.assertEqual(
            report.report_type,
            SignQualityReport.REPORT_TYPE_SIGN_UNCLEAR,
        )

    def test_non_admin_cannot_list_reports(self):
        self.client.force_authenticate(self.patient_user)

        response = self.client.get(reverse("admin-sign-quality-report-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AdminPrescriptionLogPhaseETests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Admin Logs Org")
        self.admin_user = User.objects.create_user(
            email="admin.logs@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        self.patient_user = User.objects.create_user(
            email="logs.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
            phone_number="7200001",
        )
        self.patient = PatientProfile.objects.create(
            user=self.patient_user,
            organization=self.organization,
            full_name="Log Patient",
            phone_number="7200001",
            birth_date=date(1993, 4, 5),
            gender=GenderChoices.FEMALE,
            hearing_disability_level="moderate",
        )
        self.pharmacist_user = User.objects.create_user(
            email="logs.pharmacist@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
            phone_number="7200002",
        )
        self.pharmacy = Pharmacy.objects.create(
            name="Log Pharmacy",
            address="Log Address",
            phone_number="011720000",
            organization=self.organization,
        )
        self.pharmacist = PharmacistProfile.objects.create(
            user=self.pharmacist_user,
            pharmacy=self.pharmacy,
            full_name="Log Pharmacist",
            license_number="LOG-LIC",
            is_approved=True,
        )
        self.prescribed_at = timezone.now() - timedelta(days=2)
        self.submitted_at = timezone.now() - timedelta(days=1)
        self.prescription = Prescription.objects.create(
            patient=self.patient,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            doctor_name="Log Doctor",
            doctor_specialty="General",
            diagnosis="Log Diagnosis",
            status=PrescriptionStatusChoices.SUBMITTED,
            prescribed_at=self.prescribed_at,
            submitted_at=self.submitted_at,
            notes="Log notes",
        )
        self.item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine_name="Log Medicine",
            dosage="10mg",
            frequency="daily",
            duration="7 days",
            instructions_text="Take after food",
            unit_price="1200.00",
            quantity="2",
            transcription_status=TranscriptionStatusChoices.COMPLETED,
            instructions_transcript_raw="Raw transcript",
            instructions_transcript_edited="Edited transcript",
            sign_status=SignStatusChoices.COMPLETED,
        )
        PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine_name="Second Log Medicine",
            unit_price="800.00",
            quantity="3",
        )
        PrescriptionAccessLog.objects.create(
            prescription=self.prescription,
            accessed_by=self.pharmacist_user,
            access_type="view",
        )
        self.other_prescription = Prescription.objects.create(
            patient=self.patient,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            doctor_name="Other Doctor",
            status=PrescriptionStatusChoices.DRAFT,
            prescribed_at=timezone.now() - timedelta(days=10),
        )

    def test_admin_can_list_prescription_logs(self):
        SignQualityReport.objects.create(
            patient=self.patient,
            prescription=self.prescription,
            prescription_item=self.item,
            medicine_name=self.item.medicine_name,
            status=SignQualityReport.STATUS_OPEN,
        )
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(reverse("admin-prescription-log-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 2)
        row = response.data["results"][0]
        self.assertEqual(
            set(row.keys()),
            {
                "id",
                "operation_id",
                "patient",
                "pharmacist",
                "pharmacy",
                "sent_date",
                "medicines_count",
                "linked_quality_report_status",
            },
        )
        self.assertEqual(row["operation_id"], row["id"])
        self.assertEqual(row["patient"]["full_name"], "Log Patient")
        self.assertEqual(row["pharmacist"]["full_name"], "Log Pharmacist")
        self.assertEqual(row["pharmacy"]["name"], "Log Pharmacy")
        self.assertEqual(row["medicines_count"], 2)
        self.assertEqual(
            row["linked_quality_report_status"], SignQualityReport.STATUS_OPEN
        )
        sensitive_fields = {
            "dosage",
            "frequency",
            "duration",
            "instructions_text",
            "instructions_transcript_raw",
            "instructions_transcript_edited",
            "diagnosis",
            "notes",
            "items",
            "total_price",
            "currency",
        }
        self.assertTrue(sensitive_fields.isdisjoint(row.keys()))

    def test_non_admin_cannot_list_prescription_logs(self):
        self.client.force_authenticate(self.patient_user)

        response = self.client.get(reverse("admin-prescription-log-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_response_is_paginated_and_includes_medicines_count(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse("admin-prescription-log-list"),
            {"page_size": 1},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIn("medicines_count", response.data["results"][0])

    def test_list_search_works_by_patient_name_or_prescription_id(self):
        self.client.force_authenticate(self.admin_user)

        name_response = self.client.get(
            reverse("admin-prescription-log-list"),
            {"search": "Log Patient"},
        )
        id_response = self.client.get(
            reverse("admin-prescription-log-list"),
            {"search": str(self.prescription.id)},
        )

        self.assertEqual(name_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(name_response.data["count"], 1)
        self.assertEqual(id_response.status_code, status.HTTP_200_OK)
        self.assertIn(
            self.prescription.id,
            {row["id"] for row in id_response.data["results"]},
        )

    def test_status_filter_works(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse("admin-prescription-log-list"),
            {"status": PrescriptionStatusChoices.SUBMITTED},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["results"])
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.prescription.id, ids)
        self.assertNotIn(self.other_prescription.id, ids)

    def test_quality_report_status_filter_works(self):
        SignQualityReport.objects.create(
            patient=self.patient,
            prescription=self.prescription,
            prescription_item=self.item,
            medicine_name=self.item.medicine_name,
            status=SignQualityReport.STATUS_OPEN,
        )
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse("admin-prescription-log-list"),
            {"quality_report_status": SignQualityReport.STATUS_OPEN},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.prescription.id)
        self.assertEqual(
            response.data["results"][0]["linked_quality_report_status"],
            SignQualityReport.STATUS_OPEN,
        )

    def test_pharmacy_filter_works(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse("admin-prescription-log-list"),
            {"pharmacy_id": self.pharmacy.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 2)
        self.assertTrue(
            all(
                row["pharmacy"]["id"] == self.pharmacy.id
                for row in response.data["results"]
            )
        )

    def test_date_from_date_to_filters_work(self):
        self.client.force_authenticate(self.admin_user)
        target_date = self.submitted_at.date().isoformat()

        response = self.client.get(
            reverse("admin-prescription-log-list"),
            {
                "date_from": target_date,
                "date_to": target_date,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.prescription.id, ids)
        self.assertNotIn(self.other_prescription.id, ids)

    def test_admin_can_retrieve_prescription_log_detail(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse(
                "admin-prescription-log-detail", kwargs={"pk": self.prescription.id}
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.prescription.id)
        self.assertEqual(response.data["patient"]["full_name"], "Log Patient")
        self.assertEqual(response.data["pharmacy"]["name"], "Log Pharmacy")
        self.assertEqual(response.data["pharmacist"]["license_number"], "LOG-LIC")
        self.assertEqual(response.data["total_price"], "4800.00")
        self.assertEqual(response.data["currency"], "SYP")

    def test_detail_includes_items_and_access_logs(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse(
                "admin-prescription-log-detail", kwargs={"pk": self.prescription.id}
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["medicines_count"], 2)
        self.assertEqual(len(response.data["items"]), 2)
        first_item = response.data["items"][0]
        self.assertIn("instructions", first_item)
        self.assertIn("unit_price", first_item)
        self.assertIn("quantity", first_item)
        self.assertIn("line_total", first_item)
        self.assertIn("raw_transcript", first_item)
        self.assertIn("edited_transcript", first_item)
        self.assertTrue(response.data["access_logs"])
        log = response.data["access_logs"][0]
        self.assertEqual(log["accessed_by"]["id"], self.pharmacist_user.id)
        self.assertEqual(log["accessed_by"]["role"], RoleChoices.PHARMACIST)

    def test_existing_prescription_detail_endpoint_still_works_for_admin(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse("prescription-detail", kwargs={"pk": self.prescription.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.prescription.id)


class AdminActivityLogTests(APITestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name="Activity Org A")
        self.org_b = Organization.objects.create(name="Activity Org B")
        self.admin_user = User.objects.create_user(
            email="activity.admin@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=self.admin_user,
            organization=self.org_a,
            can_manage_patients=True,
        )
        self.superuser = User.objects.create_superuser(
            email="activity.superuser@example.com",
            password="StrongPass123!",
        )
        self.patient_user = User.objects.create_user(
            email="activity.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        self.pharmacist_user = User.objects.create_user(
            email="activity.pharmacist@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        self.patient = PatientProfile.objects.create(
            user=self.patient_user,
            organization=self.org_a,
            full_name="Activity Patient",
        )
        self.pharmacy = Pharmacy.objects.create(
            name="Activity Pharmacy",
            address="Activity Address",
            organization=self.org_a,
            is_contracted_with_organization=True,
        )
        self.pharmacist = PharmacistProfile.objects.create(
            user=self.pharmacist_user,
            pharmacy=self.pharmacy,
            full_name="Activity Pharmacist",
            license_number="ACT-LIC",
            is_approved=True,
        )
        self.submitted_at = timezone.now() - timedelta(days=1)
        self.prescription = Prescription.objects.create(
            patient=self.patient,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            doctor_name="Sensitive Doctor",
            doctor_specialty="Sensitive Specialty",
            diagnosis="Sensitive Diagnosis",
            status=PrescriptionStatusChoices.SUBMITTED,
            prescribed_at=timezone.now() - timedelta(days=2),
            submitted_at=self.submitted_at,
            notes="Sensitive prescription notes",
        )
        self.item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine_name="Sensitive Medicine",
            dosage="Sensitive Dosage",
            frequency="Sensitive Frequency",
            duration="Sensitive Duration",
            instructions_text="Sensitive Instructions",
            instructions_transcript_raw="Sensitive Raw Transcript",
            instructions_transcript_edited="Sensitive Edited Transcript",
            supporting_text="Sensitive Sign Text",
            sign_status=SignStatusChoices.COMPLETED,
            unit_price="1000.00",
            quantity="1",
        )
        self.report = SignQualityReport.objects.create(
            patient=self.patient,
            prescription=self.prescription,
            prescription_item=self.item,
            medicine_name=self.item.medicine_name,
            approved_instruction_text="Sensitive Approved Instruction",
            status=SignQualityReport.STATUS_OPEN,
            admin_notes="Sensitive admin note",
        )

        self.other_patient_user = User.objects.create_user(
            email="activity.other.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        self.other_pharmacist_user = User.objects.create_user(
            email="activity.other.pharmacist@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        self.other_patient = PatientProfile.objects.create(
            user=self.other_patient_user,
            organization=self.org_b,
            full_name="Other Activity Patient",
        )
        self.other_pharmacy = Pharmacy.objects.create(
            name="Other Activity Pharmacy",
            address="Other Address",
            organization=self.org_b,
            is_contracted_with_organization=True,
        )
        self.other_pharmacist = PharmacistProfile.objects.create(
            user=self.other_pharmacist_user,
            pharmacy=self.other_pharmacy,
            full_name="Other Activity Pharmacist",
            is_approved=True,
        )
        self.other_prescription = Prescription.objects.create(
            patient=self.other_patient,
            pharmacist=self.other_pharmacist,
            pharmacy=self.other_pharmacy,
            doctor_name="Other Doctor",
            status=PrescriptionStatusChoices.SUBMITTED,
            submitted_at=timezone.now(),
        )

    def _rows(self, user=None, params=None):
        if user is not None:
            self.client.force_authenticate(user)
        response = self.client.get(reverse("admin-activity-log"), params or {})
        return response, response.data.get("results", [])

    def test_endpoint_requires_admin_authentication(self):
        unauthenticated = self.client.get(reverse("admin-activity-log"))
        self.assertIn(
            unauthenticated.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )

        self.client.force_authenticate(self.patient_user)
        patient_response = self.client.get(reverse("admin-activity-log"))
        self.assertEqual(patient_response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.pharmacist_user)
        pharmacist_response = self.client.get(reverse("admin-activity-log"))
        self.assertEqual(pharmacist_response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.admin_user)
        admin_response = self.client.get(reverse("admin-activity-log"))
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)

    def test_safe_response_fields_only(self):
        response, rows = self._rows(self.admin_user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        allowed_keys = {
            "id",
            "actor",
            "action",
            "action_label",
            "target_type",
            "target_id",
            "target_label",
            "pharmacy_name",
            "created_at",
            "status",
        }
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(set(row.keys()), allowed_keys)
            if row["actor"] is not None:
                self.assertEqual(set(row["actor"].keys()), {"id", "full_name", "role"})

        payload = json.dumps(response.data, ensure_ascii=False).lower()
        blocked_terms = [
            "dosage",
            "frequency",
            "duration",
            "diagnosis",
            "instructions_text",
            "transcript",
            "audio",
            "video",
            'pharmacy":',
            "phone_number",
            "activity address",
            "other address",
            "city",
            "region",
            "sensitive medicine",
            "sensitive dosage",
            "sensitive frequency",
            "sensitive duration",
            "sensitive diagnosis",
            "sensitive instructions",
            "sensitive raw transcript",
            "sensitive edited transcript",
            "sensitive approved instruction",
            "sensitive admin note",
        ]
        for term in blocked_terms:
            self.assertNotIn(term, payload)

    def test_includes_prescription_activity_safely(self):
        response, rows = self._rows(self.admin_user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(
            row
            for row in rows
            if row["action"] == "prescription_submitted"
            and row["target_id"] == self.prescription.id
        )
        self.assertEqual(row["target_type"], "prescription")
        self.assertEqual(row["target_label"], f"Prescription #{self.prescription.id}")
        self.assertEqual(row["pharmacy_name"], self.pharmacy.name)
        self.assertEqual(row["actor"]["role"], RoleChoices.PHARMACIST)
        self.assertEqual(row["actor"]["full_name"], "Activity Pharmacist")

    def test_includes_sign_quality_report_activity_safely(self):
        response, rows = self._rows(self.admin_user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(
            row
            for row in rows
            if row["action"] == "sign_quality_report_created"
            and row["target_id"] == self.report.id
        )
        self.assertEqual(row["target_type"], "sign_quality_report")
        self.assertEqual(row["target_label"], f"Sign quality report #{self.report.id}")
        self.assertEqual(row["pharmacy_name"], self.pharmacy.name)
        self.assertEqual(row["actor"]["role"], RoleChoices.PATIENT)

    def test_organization_staff_admin_only_sees_own_organization(self):
        response, rows = self._rows(self.admin_user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prescription_targets = {
            row["target_id"] for row in rows if row["target_type"] == "prescription"
        }
        self.assertIn(self.prescription.id, prescription_targets)
        self.assertNotIn(self.other_prescription.id, prescription_targets)

    def test_superuser_can_see_all_organizations(self):
        response, rows = self._rows(self.superuser)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prescription_targets = {
            row["target_id"] for row in rows if row["target_type"] == "prescription"
        }
        self.assertIn(self.prescription.id, prescription_targets)
        self.assertIn(self.other_prescription.id, prescription_targets)

    def test_filters_work(self):
        self.report.status = SignQualityReport.STATUS_RESOLVED
        self.report.save(update_fields=["status", "updated_at"])

        action_response, action_rows = self._rows(
            self.admin_user,
            {"action": "sign_quality_report_created"},
        )
        self.assertEqual(action_response.status_code, status.HTTP_200_OK)
        self.assertTrue(action_rows)
        self.assertTrue(
            all(row["action"] == "sign_quality_report_created" for row in action_rows)
        )

        target_response, target_rows = self._rows(
            self.admin_user,
            {"target_type": "prescription"},
        )
        self.assertEqual(target_response.status_code, status.HTTP_200_OK)
        self.assertTrue(target_rows)
        self.assertTrue(
            all(row["target_type"] == "prescription" for row in target_rows)
        )

        status_response, status_rows = self._rows(
            self.admin_user,
            {"status": SignQualityReport.STATUS_RESOLVED},
        )
        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        self.assertTrue(status_rows)
        self.assertTrue(
            all(
                row["status"] == SignQualityReport.STATUS_RESOLVED
                for row in status_rows
            )
        )

        date_response, date_rows = self._rows(
            self.admin_user,
            {
                "date_from": self.submitted_at.date().isoformat(),
                "date_to": self.submitted_at.date().isoformat(),
            },
        )
        self.assertEqual(date_response.status_code, status.HTTP_200_OK)
        self.assertIn(
            self.prescription.id,
            {
                row["target_id"]
                for row in date_rows
                if row["target_type"] == "prescription"
            },
        )

        search_response, search_rows = self._rows(
            self.admin_user,
            {"search": "Activity Pharmacist"},
        )
        self.assertEqual(search_response.status_code, status.HTTP_200_OK)
        self.assertTrue(search_rows)
        self.assertTrue(
            all(
                "activity pharmacist" in row["actor"]["full_name"].lower()
                for row in search_rows
            )
        )

    def test_pagination_shape(self):
        response, rows = self._rows(self.admin_user, {"page_size": 1})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(len(rows), 1)


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
            "doctor_specialty": "قلبية",
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
                    "unit_price": "1000.00",
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
            doctor_specialty="Internal Medicine",
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

    def assert_safe_prescription_nested_shapes(
        self, payload, *, include_transcription=False
    ):
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
            expected_item_fields = {
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
                "pose_file_path",
                "pose_file_url",
                "generated_video_path",
                "generated_video_url",
                "avatar_video_url",
                "sign_error_message",
                "pose_shape",
                "ai_metadata",
                "pose_generated_at",
                "generation_started_at",
                "generation_completed_at",
                "created_at",
                "updated_at",
            }
            self.assertEqual(set(payload["items"][0].keys()), expected_item_fields)
            blocked_item_fields = {
                "prescription",
                "medicine_name",
                "medicine_image",
                "instructions_text",
                "instructions_audio",
                "transcription_provider",
                "transcription_requested_at",
                "transcription_completed_at",
                "transcription_error_message",
                "instructions_transcript_raw",
                "instructions_transcript_edited",
                "is_transcript_approved",
                "sign_language_video",
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
        self.assertEqual(response.data["doctor_specialty"], "قلبية")
        self.assertEqual(response.data["patient"]["id"], self.patient.id)
        self.assertEqual(
            set(response.data["patient"].keys()),
            {"id", "full_name", "phone_number"},
        )
        self.assertNotIn("qr_code_value", response.data["patient"])
        self.assert_safe_prescription_nested_shapes(
            response.data, include_transcription=True
        )
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(
            response.data["items"][0]["sign_status"], SignStatusChoices.PENDING
        )
        prescription = Prescription.objects.get(pk=response.data["id"])
        self.assertEqual(prescription.doctor_specialty, "قلبية")

    def test_pharmacist_can_get_doctor_specialties(self):
        response = self.client.get(
            reverse("pharmacist-prescription-doctor-specialties")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(
            [option["label"] for option in response.data["results"]],
            list(DOCTOR_SPECIALTY_LABELS),
        )
        self.assertEqual(
            [option["value"] for option in response.data["results"]],
            list(DOCTOR_SPECIALTY_LABELS),
        )
        for option in response.data["results"]:
            self.assertEqual(set(option.keys()), {"value", "label"})

    def test_pharmacist_can_create_prescription_without_doctor_specialty(self):
        response = self.client.post(
            reverse("pharmacist-prescriptions"),
            self._create_payload(doctor_specialty=""),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["doctor_specialty"], "")
        prescription = Prescription.objects.get(pk=response.data["id"])
        self.assertEqual(prescription.doctor_specialty, "")

    def test_pharmacist_can_create_prescription_with_custom_doctor_specialty(self):
        response = self.client.post(
            reverse("pharmacist-prescriptions"),
            self._create_payload(doctor_specialty="اختصاص نادر"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["doctor_specialty"], "اختصاص نادر")
        prescription = Prescription.objects.get(pk=response.data["id"])
        self.assertEqual(prescription.doctor_specialty, "اختصاص نادر")

    def test_pharmacist_can_create_prescription_with_omitted_doctor_specialty(self):
        payload = self._create_payload()
        payload.pop("doctor_specialty")

        response = self.client.post(
            reverse("pharmacist-prescriptions"),
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["doctor_specialty"], "")
        prescription = Prescription.objects.get(pk=response.data["id"])
        self.assertEqual(prescription.doctor_specialty, "")

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
        own_payload = next(item for item in response.data if item["id"] == own.id)
        self.assertEqual(own_payload["item_count"], 1)
        self.assertEqual(own_payload["doctor_specialty"], "Internal Medicine")

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
        item = prescription.items.first()
        item.instructions_text = "Approved instruction"
        item.instructions_transcript_raw = "Raw transcript"
        item.instructions_transcript_edited = "Approved instruction"
        item.transcription_status = TranscriptionStatusChoices.COMPLETED
        item.transcription_provider = "gemini"
        item.transcription_completed_at = timezone.now()
        item.save(
            update_fields=[
                "instructions_text",
                "instructions_transcript_raw",
                "instructions_transcript_edited",
                "transcription_status",
                "transcription_provider",
                "transcription_completed_at",
                "updated_at",
            ]
        )

        response = self.client.get(
            reverse(
                "pharmacist-prescription-detail",
                kwargs={"prescription_id": prescription.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], prescription.id)
        self.assertEqual(response.data["doctor_specialty"], "Internal Medicine")
        self.assert_safe_prescription_nested_shapes(
            response.data, include_transcription=True
        )
        item_payload = response.data["items"][0]
        self.assertEqual(item_payload["raw_transcript"], "Raw transcript")
        self.assertEqual(
            item_payload["approved_instruction_text"], "Approved instruction"
        )
        self.assertEqual(item_payload["transcription_status"], "approved")

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
                "doctor_specialty": "عصبية",
                "diagnosis": "Updated",
                "notes": "Updated notes",
                "status": PrescriptionStatusChoices.SUBMITTED,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prescription.refresh_from_db()
        self.assertEqual(prescription.doctor_name, "Dr. Updated")
        self.assertEqual(prescription.doctor_specialty, "عصبية")
        self.assertEqual(response.data["doctor_specialty"], "عصبية")
        self.assertEqual(prescription.status, PrescriptionStatusChoices.DRAFT)

    def test_pharmacist_can_update_draft_prescription_with_custom_specialty(self):
        prescription = self._create_prescription()

        response = self.client.patch(
            reverse(
                "pharmacist-prescription-detail",
                kwargs={"prescription_id": prescription.id},
            ),
            {"doctor_specialty": "طب رياضي"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prescription.refresh_from_db()
        self.assertEqual(prescription.doctor_specialty, "طب رياضي")
        self.assertEqual(response.data["doctor_specialty"], "طب رياضي")

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
                "unit_price": "500.00",
                "quantity": "1",
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
            response.data["detail"],
            "Prescription must include at least one item before submission",
        )
        self.assertEqual(response.data["code"], "prescription_has_no_items")

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
        self.assertEqual(response.data["detail"], "Prescription submitted successfully")
        self.assertEqual(
            response.data["prescription"]["status"], PrescriptionStatusChoices.SUBMITTED
        )

    def test_confirm_submitted_prescription_succeeds(self):
        prescription = self._create_prescription()
        prescription.status = PrescriptionStatusChoices.SUBMITTED
        prescription.submitted_at = timezone.now()
        prescription.save(update_fields=["status", "submitted_at", "updated_at"])

        response = self.client.post(
            reverse(
                "pharmacist-prescription-confirm",
                kwargs={"prescription_id": prescription.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prescription.refresh_from_db()
        self.assertEqual(prescription.status, PrescriptionStatusChoices.CONFIRMED)
        self.assertEqual(response.data["detail"], "Prescription confirmed successfully")
        self.assertEqual(
            response.data["prescription"]["status"], PrescriptionStatusChoices.CONFIRMED
        )

    def test_deliver_confirmed_prescription_succeeds(self):
        prescription = self._create_prescription()
        prescription.status = PrescriptionStatusChoices.CONFIRMED
        prescription.submitted_at = timezone.now()
        prescription.save(update_fields=["status", "submitted_at", "updated_at"])

        response = self.client.post(
            reverse(
                "pharmacist-prescription-deliver",
                kwargs={"prescription_id": prescription.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prescription.refresh_from_db()
        self.assertEqual(prescription.status, PrescriptionStatusChoices.DELIVERED)
        self.assertIsNotNone(prescription.delivered_at)
        self.assertEqual(response.data["detail"], "Prescription delivered successfully")
        self.assertEqual(
            response.data["prescription"]["status"], PrescriptionStatusChoices.DELIVERED
        )

    def test_cancel_submitted_or_confirmed_prescription_succeeds(self):
        submitted = self._create_prescription()
        submitted.status = PrescriptionStatusChoices.SUBMITTED
        submitted.submitted_at = timezone.now()
        submitted.save(update_fields=["status", "submitted_at", "updated_at"])
        confirmed = self._create_prescription()
        confirmed.status = PrescriptionStatusChoices.CONFIRMED
        confirmed.submitted_at = timezone.now()
        confirmed.save(update_fields=["status", "submitted_at", "updated_at"])

        submitted_response = self.client.post(
            reverse(
                "pharmacist-prescription-cancel",
                kwargs={"prescription_id": submitted.id},
            ),
            {},
            format="json",
        )
        confirmed_response = self.client.post(
            reverse(
                "pharmacist-prescription-cancel",
                kwargs={"prescription_id": confirmed.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(submitted_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirmed_response.status_code, status.HTTP_200_OK)
        submitted.refresh_from_db()
        confirmed.refresh_from_db()
        self.assertEqual(submitted.status, PrescriptionStatusChoices.CANCELLED)
        self.assertEqual(confirmed.status, PrescriptionStatusChoices.CANCELLED)

    def test_archive_delivered_or_cancelled_prescription_succeeds(self):
        delivered = self._create_prescription()
        delivered.status = PrescriptionStatusChoices.DELIVERED
        delivered.submitted_at = timezone.now()
        delivered.delivered_at = timezone.now()
        delivered.save(
            update_fields=["status", "submitted_at", "delivered_at", "updated_at"]
        )
        cancelled = self._create_prescription()
        cancelled.status = PrescriptionStatusChoices.CANCELLED
        cancelled.submitted_at = timezone.now()
        cancelled.save(update_fields=["status", "submitted_at", "updated_at"])

        delivered_response = self.client.post(
            reverse(
                "pharmacist-prescription-archive",
                kwargs={"prescription_id": delivered.id},
            ),
            {},
            format="json",
        )
        cancelled_response = self.client.post(
            reverse(
                "pharmacist-prescription-archive",
                kwargs={"prescription_id": cancelled.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(delivered_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cancelled_response.status_code, status.HTTP_200_OK)
        delivered.refresh_from_db()
        cancelled.refresh_from_db()
        self.assertEqual(delivered.status, PrescriptionStatusChoices.ARCHIVED)
        self.assertEqual(cancelled.status, PrescriptionStatusChoices.ARCHIVED)

    def test_invalid_lifecycle_transitions_fail_with_stable_code(self):
        draft = self._create_prescription()
        delivered = self._create_prescription()
        delivered.status = PrescriptionStatusChoices.DELIVERED
        delivered.delivered_at = timezone.now()
        delivered.save(update_fields=["status", "delivered_at", "updated_at"])

        draft_response = self.client.post(
            reverse(
                "pharmacist-prescription-deliver",
                kwargs={"prescription_id": draft.id},
            ),
            {},
            format="json",
        )
        delivered_response = self.client.post(
            reverse(
                "pharmacist-prescription-cancel",
                kwargs={"prescription_id": delivered.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(draft_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(delivered_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            draft_response.data["code"], "invalid_prescription_status_transition"
        )
        self.assertEqual(draft_response.data["current_status"], "draft")
        self.assertEqual(draft_response.data["target_status"], "delivered")
        self.assertEqual(
            delivered_response.data["code"], "invalid_prescription_status_transition"
        )
        self.assertEqual(delivered_response.data["current_status"], "delivered")
        self.assertEqual(delivered_response.data["target_status"], "cancelled")

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
        item = prescription.items.first()
        item.unit_price = "1500.00"
        item.quantity = "2"
        item.save()
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
        self.assertEqual(response.data["total_price"], "3000.00")
        self.assertEqual(response.data["currency"], "SYP")
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

    def build_audio_upload(
        self, *, filename="instructions.mp3", content_type="audio/mpeg", size=128
    ):
        return SimpleUploadedFile(
            filename,
            b"a" * size,
            content_type=content_type,
        )

    def build_image_upload(self, filename="medicine.png", content_type="image/png"):
        buffer = io.BytesIO()
        image = Image.new("RGB", (1, 1), color="white")
        image.save(buffer, format="PNG")
        return SimpleUploadedFile(
            filename,
            buffer.getvalue(),
            content_type=content_type,
        )

    def test_pharmacist_can_create_item_with_json(self):
        prescription = self._create_prescription(with_item=False)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "medication_name": "Amoxicillin",
                "dosage": "500mg",
                "frequency": "Twice daily",
                "duration": "7 days",
                "instructions": "Take after food",
                "unit_price": "2500.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["medication_name"], "Amoxicillin")
        self.assertIsNone(response.data["image_url"])
        self.assertIsNone(response.data["audio_url"])
        self.assertIsNone(response.data["video_url"])

    def test_pharmacist_can_create_item_with_price_and_quantity(self):
        prescription = self._create_prescription(with_item=False)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "medication_name": "Priced Med",
                "price": "12.50",
                "quantity": 3,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["medication_name"], "Priced Med")
        self.assertEqual(response.data["price"], "12.50")
        self.assertEqual(response.data["unit_price"], "12.50")
        self.assertEqual(response.data["quantity"], "3.00")
        self.assertEqual(response.data["line_total"], "37.50")
        item = prescription.items.get(pk=response.data["id"])
        self.assertEqual(str(item.price), "12.50")
        self.assertEqual(str(item.unit_price), "12.50")
        self.assertEqual(str(item.quantity), "3.00")
        self.assertEqual(str(item.line_total), "37.50")
        prescription.refresh_from_db()
        self.assertEqual(str(prescription.total_price), "37.50")

    def test_pharmacist_can_update_item_with_price_and_quantity(self):
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.patch(
            reverse(
                "pharmacist-prescription-item-detail",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {
                "price": "8.75",
                "quantity": 2,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["price"], "8.75")
        self.assertEqual(response.data["unit_price"], "8.75")
        self.assertEqual(response.data["quantity"], "2.00")
        self.assertEqual(response.data["line_total"], "17.50")
        item.refresh_from_db()
        self.assertEqual(str(item.price), "8.75")
        self.assertEqual(str(item.unit_price), "8.75")
        self.assertEqual(str(item.quantity), "2.00")
        self.assertEqual(str(item.line_total), "17.50")
        prescription.refresh_from_db()
        self.assertEqual(str(prescription.total_price), "17.50")

    def test_nested_prescription_create_saves_item_price_and_quantity(self):
        payload = self._create_payload(
            items=[
                {
                    "medication_name": "Nested Priced Med",
                    "price": "21.00",
                    "quantity": 4,
                }
            ]
        )

        response = self.client.post(
            reverse("pharmacist-prescriptions"),
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["items"][0]["price"], "21.00")
        self.assertEqual(response.data["items"][0]["unit_price"], "21.00")
        self.assertEqual(response.data["items"][0]["quantity"], "4.00")
        self.assertEqual(response.data["items"][0]["line_total"], "84.00")
        self.assertEqual(response.data["total_price"], "84.00")
        self.assertEqual(response.data["currency"], "SYP")
        item = Prescription.objects.get(pk=response.data["id"]).items.get()
        self.assertEqual(str(item.price), "21.00")
        self.assertEqual(str(item.unit_price), "21.00")
        self.assertEqual(str(item.quantity), "4.00")
        self.assertEqual(str(item.line_total), "84.00")

    def test_create_item_with_unit_price_without_quantity_defaults_to_one(self):
        prescription = self._create_prescription(with_item=False)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "medication_name": "Default Quantity Med",
                "unit_price": "2500.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["unit_price"], "2500.00")
        self.assertEqual(response.data["quantity"], "1.00")
        self.assertEqual(response.data["line_total"], "2500.00")
        item = prescription.items.get(pk=response.data["id"])
        self.assertEqual(str(item.quantity), "1.00")
        self.assertEqual(str(item.line_total), "2500.00")

    def test_create_item_without_unit_price_or_price_fails(self):
        prescription = self._create_prescription(with_item=False)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "medication_name": "Missing Price Med",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["unit_price"][0], "This field is required.")

    def test_create_item_with_legacy_price_without_quantity_defaults_to_one(self):
        prescription = self._create_prescription(with_item=False)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "medication_name": "Legacy Price Default Quantity Med",
                "price": "1750.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["price"], "1750.00")
        self.assertEqual(response.data["unit_price"], "1750.00")
        self.assertEqual(response.data["quantity"], "1.00")
        self.assertEqual(response.data["line_total"], "1750.00")

    def test_item_line_total_is_calculated_from_unit_price_and_quantity(self):
        prescription = self._create_prescription(with_item=False)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "medication_name": "Billing Med",
                "unit_price": "2500.00",
                "quantity": "2",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["unit_price"], "2500.00")
        self.assertEqual(response.data["quantity"], "2.00")
        self.assertEqual(response.data["line_total"], "5000.00")
        item = prescription.items.get(pk=response.data["id"])
        self.assertEqual(str(item.line_total), "5000.00")

    def test_prescription_total_price_is_calculated_from_multiple_items(self):
        prescription = self._create_prescription(with_item=False)

        PrescriptionItem.objects.create(
            prescription=prescription,
            medicine_name="First Billing Med",
            unit_price="1000.00",
            quantity="2",
        )
        PrescriptionItem.objects.create(
            prescription=prescription,
            medicine_name="Second Billing Med",
            unit_price="750.50",
            quantity="3",
        )

        prescription.refresh_from_db()
        self.assertEqual(str(prescription.total_price), "4251.50")

    def test_updating_item_unit_price_recalculates_totals(self):
        prescription = self._create_prescription(with_item=False)
        item = PrescriptionItem.objects.create(
            prescription=prescription,
            medicine_name="Update Price Med",
            unit_price="10.00",
            quantity="2",
        )

        response = self.client.patch(
            reverse(
                "pharmacist-prescription-item-detail",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"unit_price": "12.50"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["line_total"], "25.00")
        prescription.refresh_from_db()
        self.assertEqual(str(prescription.total_price), "25.00")

    def test_updating_item_quantity_recalculates_totals(self):
        prescription = self._create_prescription(with_item=False)
        item = PrescriptionItem.objects.create(
            prescription=prescription,
            medicine_name="Update Quantity Med",
            unit_price="10.00",
            quantity="2",
        )

        response = self.client.patch(
            reverse(
                "pharmacist-prescription-item-detail",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"quantity": "3.5"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["quantity"], "3.50")
        self.assertEqual(response.data["line_total"], "35.00")
        prescription.refresh_from_db()
        self.assertEqual(str(prescription.total_price), "35.00")

    def test_negative_item_price_fails(self):
        prescription = self._create_prescription(with_item=False)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "medication_name": "Bad Price Med",
                "price": "-1.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("price", response.data)

    def test_negative_item_unit_price_fails(self):
        prescription = self._create_prescription(with_item=False)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "medication_name": "Bad Unit Price Med",
                "unit_price": "-1.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unit_price", response.data)

    def test_zero_item_quantity_fails(self):
        prescription = self._create_prescription(with_item=False)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "medication_name": "Zero Quantity Med",
                "quantity": "0",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quantity", response.data)

    def test_negative_item_quantity_fails(self):
        prescription = self._create_prescription(with_item=False)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "medication_name": "Bad Quantity Med",
                "quantity": -1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quantity", response.data)

    def test_patch_with_invalid_unit_price_fails(self):
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.patch(
            reverse(
                "pharmacist-prescription-item-detail",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"unit_price": "-0.01"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unit_price", response.data)

    def test_patch_with_invalid_quantity_fails(self):
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.patch(
            reverse(
                "pharmacist-prescription-item-detail",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"quantity": "0"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quantity", response.data)

    def test_medicine_name_alias_still_creates_medication_name_response(self):
        prescription = self._create_prescription(with_item=False)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "medicine_name": "Legacy Alias Med",
                "unit_price": "1000.00",
                "quantity": "1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["medication_name"], "Legacy Alias Med")
        self.assertNotIn("medicine_name", response.data)

    def test_medicine_name_alias_still_updates_medication_name_response(self):
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.patch(
            reverse(
                "pharmacist-prescription-item-detail",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"medicine_name": "Updated Legacy Alias Med"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["medication_name"], "Updated Legacy Alias Med")
        self.assertNotIn("medicine_name", response.data)
        item.refresh_from_db()
        self.assertEqual(item.medicine_name, "Updated Legacy Alias Med")

    def test_pharmacist_can_create_item_with_image_upload(self):
        prescription = self._create_prescription(with_item=False)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "medication_name": "Amoxicillin",
                "image": self.build_image_upload(),
                "unit_price": "1500.00",
                "quantity": "1",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("/media/", response.data["image_url"])
        item = prescription.items.get(pk=response.data["id"])
        self.assertTrue(item.medicine_image)

    def test_pharmacist_can_update_item_with_image_upload_alias(self):
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.patch(
            reverse(
                "pharmacist-prescription-item-detail",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"medication_image": self.build_image_upload("updated.png")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("/media/", response.data["image_url"])
        item.refresh_from_db()
        self.assertTrue(item.medicine_image)

    def test_create_item_unsupported_image_file_fails_with_stable_code(self):
        prescription = self._create_prescription(with_item=False)

        response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {
                "medication_name": "Amoxicillin",
                "image": SimpleUploadedFile(
                    "medicine.txt",
                    b"not-image",
                    content_type="text/plain",
                ),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "unsupported_image_type")

    @patch("prescriptions.views.transcribe_audio_file")
    def test_approved_pharmacist_can_transcribe_audio_for_own_draft_item(
        self, mock_transcribe
    ):
        mock_transcribe.return_value = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "transcript": "Take one tablet after food three times a day",
        }
        prescription = self._create_prescription()
        item = prescription.items.first()
        item.instructions_text = "Previously approved text"
        item.instructions_transcript_raw = "Old raw transcript"
        item.instructions_transcript_edited = "Previously approved text"
        item.save(
            update_fields=[
                "instructions_text",
                "instructions_transcript_raw",
                "instructions_transcript_edited",
                "updated_at",
            ]
        )

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"audio": self.build_audio_upload()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["item_id"], item.id)
        self.assertEqual(
            response.data["detail"],
            "Audio transcribed successfully",
        )
        item.refresh_from_db()
        self.assertEqual(item.instructions_text, "")
        self.assertEqual(
            item.instructions_transcript_raw,
            "Take one tablet after food three times a day",
        )
        self.assertEqual(item.instructions_transcript_edited, "")
        self.assertEqual(
            item.transcription_status,
            TranscriptionStatusChoices.COMPLETED,
        )
        self.assertEqual(item.transcription_provider, "gemini")
        self.assertTrue(item.instructions_audio)
        self.assertIsNone(response.data["approved_instruction_text"])
        self.assertEqual(response.data["provider"], "gemini")
        self.assertEqual(response.data["model"], "gemini-2.5-flash")
        self.assertIn("/media/", response.data["audio_url"])
        self.assertEqual(
            response.data["raw_transcript"],
            "Take one tablet after food three times a day",
        )
        mock_transcribe.assert_called_once()

    def test_approved_pharmacist_can_approve_transcript_for_own_draft_item(self):
        prescription = self._create_prescription()
        item = prescription.items.first()
        item.instructions_transcript_raw = "Raw Gemini text"
        item.instructions_transcript_edited = "Raw Gemini text"
        item.transcription_status = TranscriptionStatusChoices.COMPLETED
        item.save(
            update_fields=[
                "instructions_transcript_raw",
                "instructions_transcript_edited",
                "transcription_status",
                "updated_at",
            ]
        )

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-approve-transcript",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"approved_instruction_text": "Edited approved text"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["item_id"], item.id)
        self.assertEqual(
            response.data["detail"],
            "Transcript approved successfully",
        )
        item.refresh_from_db()
        self.assertEqual(item.instructions_transcript_raw, "Raw Gemini text")
        self.assertEqual(item.instructions_transcript_edited, "Edited approved text")
        self.assertEqual(item.instructions_text, "Take daily")
        self.assertEqual(
            item.transcription_status, TranscriptionStatusChoices.COMPLETED
        )
        self.assertEqual(
            response.data["transcription_status"],
            "approved",
        )
        self.assertEqual(response.data["raw_transcript"], "Raw Gemini text")
        self.assertEqual(
            response.data["approved_instruction_text"],
            "Edited approved text",
        )

    def test_sign_status_endpoint_returns_generation_state(self):
        prescription = self._create_prescription()
        item = prescription.items.first()
        item.supporting_text = "generated gloss"
        item.pose_file_path = "generated_outputs/gen_mock.npy"
        item.generated_video_url = "/media/generated/generated_sentence_skeleton_576.mp4"
        item.sign_status = SignStatusChoices.COMPLETED
        item.save(
            update_fields=[
                "supporting_text",
                "pose_file_path",
                "generated_video_url",
                "sign_status",
                "updated_at",
            ]
        )

        response = self.client.get(
            reverse(
                "pharmacist-prescription-item-sign-status",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["item_id"], item.id)
        self.assertEqual(response.data["sign_status"], SignStatusChoices.COMPLETED)
        self.assertEqual(response.data["gloss_text"], "generated gloss")
        self.assertEqual(
            response.data["generated_video_url"],
            "/media/generated/generated_sentence_skeleton_576.mp4",
        )

    @patch("prescriptions.views.generate_pose_from_gloss")
    @patch("prescriptions.views.generate_sign_gloss")
    def test_regenerate_sign_overwrites_old_failed_output(
        self, mock_generate_sign_gloss, mock_generate_pose_from_gloss
    ):
        mock_generate_sign_gloss.return_value = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "gloss_text": "new gloss",
        }
        mock_generate_pose_from_gloss.return_value = {
            "success": True,
            "gloss": "new gloss",
            "pose_shape": [64, 576],
            "file_path": "generated_outputs/new.npy",
            "video_path": "/media/generated/new.mp4",
            "metadata": {"model": "retrieval"},
        }
        prescription = self._create_prescription()
        item = prescription.items.first()
        item.instructions_text = "Manual instructions"
        item.sign_status = SignStatusChoices.FAILED
        item.pose_file_path = "old.npy"
        item.generated_video_url = "/media/generated/old.mp4"
        item.sign_error_message = "old error"
        item.save(
            update_fields=[
                "instructions_text",
                "sign_status",
                "pose_file_path",
                "generated_video_url",
                "sign_error_message",
                "updated_at",
            ]
        )

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-regenerate-sign",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.sign_status, SignStatusChoices.COMPLETED)
        self.assertEqual(item.supporting_text, "new gloss")
        self.assertEqual(item.pose_file_path, "generated_outputs/new.npy")
        self.assertEqual(item.generated_video_url, "/media/generated/new.mp4")
        self.assertEqual(item.sign_error_message, "")

    @patch("prescriptions.views.generate_pose_from_gloss")
    @patch("prescriptions.views.generate_sign_gloss")
    def test_generate_sign_success_when_instructions_text_exists(
        self, mock_generate_sign_gloss, mock_generate_pose_from_gloss
    ):
        mock_generate_sign_gloss.return_value = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "gloss_text": "generated gloss",
        }
        mock_generate_pose_from_gloss.return_value = {
            "success": True,
            "gloss": "generated gloss",
            "pose_shape": [128, 576],
            "file_path": "generated_outputs/gen_mock.npy",
            "metadata": {"model": "v4_bounded_offset_trimmed"},
        }
        prescription = self._create_prescription()
        item = prescription.items.first()
        item.instructions_transcript_edited = "Approved text has priority"
        item.instructions_transcript_raw = "Raw transcript text"
        item.instructions_text = "Manual instructions"
        item.save(
            update_fields=[
                "instructions_transcript_edited",
                "instructions_transcript_raw",
                "instructions_text",
                "updated_at",
            ]
        )

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-generate-sign",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["item_id"], item.id)
        self.assertEqual(response.data["gloss_text"], "generated gloss")
        self.assertEqual(response.data["sign_status"], SignStatusChoices.COMPLETED)
        self.assertIsNone(response.data["video_url"])
        self.assertEqual(
            response.data["detail"],
            "Gloss, pose, and sign media generated successfully",
        )
        item.refresh_from_db()
        self.assertEqual(item.supporting_text, "generated gloss")
        self.assertEqual(item.sign_status, SignStatusChoices.COMPLETED)
        self.assertFalse(item.sign_language_video)
        mock_generate_sign_gloss.assert_called_once_with("Approved text has priority")

    @patch("prescriptions.views.generate_pose_from_gloss")
    @patch("prescriptions.views.generate_sign_gloss")
    def test_generate_sign_falls_back_to_raw_transcript(
        self, mock_generate_sign_gloss, mock_generate_pose_from_gloss
    ):
        mock_generate_sign_gloss.return_value = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "gloss_text": "raw gloss",
        }
        mock_generate_pose_from_gloss.return_value = {
            "success": True,
            "gloss": "raw gloss",
            "pose_shape": [128, 576],
            "file_path": "generated_outputs/gen_mock.npy",
            "metadata": {},
        }
        prescription = self._create_prescription()
        item = prescription.items.first()
        item.instructions_transcript_edited = ""
        item.instructions_transcript_raw = "Raw transcript text"
        item.instructions_text = "Manual instructions"
        item.save(
            update_fields=[
                "instructions_transcript_edited",
                "instructions_transcript_raw",
                "instructions_text",
                "updated_at",
            ]
        )

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-generate-sign",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_generate_sign_gloss.assert_called_once_with("Raw transcript text")

    @patch("prescriptions.views.generate_pose_from_gloss")
    @patch("prescriptions.views.generate_sign_gloss")
    def test_generate_sign_falls_back_to_instructions(
        self, mock_generate_sign_gloss, mock_generate_pose_from_gloss
    ):
        mock_generate_sign_gloss.return_value = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "gloss_text": "instruction gloss",
        }
        mock_generate_pose_from_gloss.return_value = {
            "success": True,
            "gloss": "instruction gloss",
            "pose_shape": [128, 576],
            "file_path": "generated_outputs/gen_mock.npy",
            "metadata": {},
        }
        prescription = self._create_prescription()
        item = prescription.items.first()
        item.instructions_transcript_edited = ""
        item.instructions_transcript_raw = ""
        item.instructions_text = "Manual instructions"
        item.save(
            update_fields=[
                "instructions_transcript_edited",
                "instructions_transcript_raw",
                "instructions_text",
                "updated_at",
            ]
        )

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-generate-sign",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_generate_sign_gloss.assert_called_once_with("Manual instructions")

    @patch("prescriptions.views.generate_sign_gloss")
    def test_generate_sign_rejects_item_with_empty_instructions_text(
        self, mock_generate_sign_gloss
    ):
        prescription = self._create_prescription()
        item = prescription.items.first()
        item.instructions_text = ""
        item.save(update_fields=["instructions_text", "updated_at"])

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-generate-sign",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "No instruction text is available for gloss generation.",
        )
        self.assertEqual(response.data["code"], "missing_instruction_text")
        item.refresh_from_db()
        self.assertEqual(item.sign_status, SignStatusChoices.PENDING)
        mock_generate_sign_gloss.assert_not_called()

    @patch("prescriptions.views.generate_sign_gloss")
    def test_generate_sign_failure_sets_sign_status_failed(
        self, mock_generate_sign_gloss
    ):
        mock_generate_sign_gloss.side_effect = SignGenerationError("provider failed")
        prescription = self._create_prescription()
        item = prescription.items.first()
        item.instructions_text = "خذ قرصا واحدا يوميا"
        item.supporting_text = "old gloss"
        item.save(update_fields=["instructions_text", "supporting_text", "updated_at"])

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-generate-sign",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(
            response.data["detail"],
            "Gloss generation failed",
        )
        item.refresh_from_db()
        self.assertEqual(item.instructions_text, "خذ قرصا واحدا يوميا")
        self.assertEqual(item.supporting_text, "old gloss")
        self.assertEqual(item.sign_status, SignStatusChoices.FAILED)

    @patch("prescriptions.views.generate_sign_gloss")
    def test_unauthorized_pharmacist_cannot_generate_sign_for_another_prescription(
        self, mock_generate_sign_gloss
    ):
        prescription = self._create_prescription(pharmacist=self.other_pharmacist)
        item = prescription.items.first()
        item.instructions_text = "Foreign pharmacist text"
        item.save(update_fields=["instructions_text", "updated_at"])

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-generate-sign",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        mock_generate_sign_gloss.assert_not_called()

    @patch("prescriptions.views.generate_pose_from_gloss")
    @patch("prescriptions.views.generate_sign_gloss")
    def test_generate_sign_response_contains_required_output_fields(
        self, mock_generate_sign_gloss, mock_generate_pose_from_gloss
    ):
        mock_generate_sign_gloss.return_value = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "gloss_text": "جرعة 1 صباح",
        }
        mock_generate_pose_from_gloss.return_value = {
            "success": True,
            "gloss": "جرعة 1 صباح",
            "pose_shape": [128, 576],
            "file_path": "generated_outputs/gen_mock.npy",
            "metadata": {},
        }
        prescription = self._create_prescription()
        item = prescription.items.first()
        item.instructions_text = "خذ جرعة واحدة صباحا"
        item.save(update_fields=["instructions_text", "updated_at"])

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-generate-sign",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data.keys()),
            {
                "item_id",
                "sign_status",
                "gloss_text",
                "supporting_text",
                "video_url",
                "output_type",
                "video_generation_supported",
                "detail",
                "pose",
                "item",
            },
        )
        self.assertEqual(response.data["gloss_text"], "جرعة 1 صباح")
        self.assertEqual(response.data["sign_status"], SignStatusChoices.COMPLETED)

    @override_settings(GEMINI_API_KEY="")
    def test_generate_sign_provider_not_configured_response(self):
        prescription = self._create_prescription()
        item = prescription.items.first()
        item.instructions_transcript_edited = "Approved text"
        item.save(update_fields=["instructions_transcript_edited", "updated_at"])

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-generate-sign",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["code"], "gloss_provider_not_configured")
        item.refresh_from_db()
        self.assertEqual(item.sign_status, SignStatusChoices.FAILED)

    @patch("prescriptions.views.generate_pose_from_gloss")
    @patch("prescriptions.views.generate_sign_gloss")
    def test_generate_sign_full_pipeline_success(
        self, mock_generate_sign_gloss, mock_generate_pose_from_gloss
    ):
        mock_generate_sign_gloss.return_value = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "gloss_text": "دواء حبة الصبح قبل الاكل",
        }
        mock_generate_pose_from_gloss.return_value = {
            "success": True,
            "gloss": "دواء حبة الصبح قبل الاكل",
            "pose_shape": [128, 576],
            "file_path": "generated_outputs/gen_mock.npy",
            "video_path": "/media/generated/generated_sentence_skeleton_576.mp4",
            "metadata": {"model": "v4_bounded_offset_trimmed", "device": "cuda"},
        }
        prescription = self._create_prescription()
        item = prescription.items.first()
        item.instructions_text = "خذ حبة في الصباح قبل الطعام"
        item.save(update_fields=["instructions_text", "updated_at"])

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-generate-sign",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["item_id"], item.id)
        self.assertEqual(response.data["gloss_text"], "دواء حبة الصبح قبل الاكل")
        self.assertEqual(response.data["supporting_text"], "دواء حبة الصبح قبل الاكل")
        self.assertEqual(response.data["sign_status"], SignStatusChoices.COMPLETED)
        self.assertEqual(response.data["output_type"], "gloss_pose_and_video")
        self.assertIn(
            "/media/generated/generated_sentence_skeleton_576.mp4",
            response.data["video_url"],
        )
        self.assertTrue(response.data["pose"]["success"])
        self.assertEqual(
            response.data["pose"]["file_path"], "generated_outputs/gen_mock.npy"
        )
        self.assertEqual(response.data["pose"]["pose_shape"], [128, 576])

        # Verify DB updates
        item.refresh_from_db()
        self.assertEqual(item.supporting_text, "دواء حبة الصبح قبل الاكل")
        self.assertEqual(item.pose_file_path, "generated_outputs/gen_mock.npy")
        self.assertEqual(
            item.generated_video_path,
            "/media/generated/generated_sentence_skeleton_576.mp4",
        )
        self.assertEqual(
            item.generated_video_url,
            "/media/generated/generated_sentence_skeleton_576.mp4",
        )
        self.assertEqual(item.pose_shape, [128, 576])
        self.assertEqual(
            item.ai_metadata["pose"],
            {"model": "v4_bounded_offset_trimmed", "device": "cuda"},
        )
        self.assertEqual(item.sign_status, SignStatusChoices.COMPLETED)
        self.assertTrue(item.pose_generated_at)

        # Assert correct calls
        mock_generate_sign_gloss.assert_called_once_with("خذ حبة في الصباح قبل الطعام")
        mock_generate_pose_from_gloss.assert_called_once_with(
            "دواء حبة الصبح قبل الاكل", return_format="npy"
        )

    @patch("prescriptions.views.generate_pose_from_gloss")
    @patch("prescriptions.views.generate_sign_gloss")
    def test_generate_sign_gemini_failure_does_not_call_pose(
        self, mock_generate_sign_gloss, mock_generate_pose_from_gloss
    ):
        mock_generate_sign_gloss.side_effect = SignGenerationError("provider failed")
        prescription = self._create_prescription()
        item = prescription.items.first()
        item.instructions_text = "خذ حبة في الصباح قبل الطعام"
        item.save(update_fields=["instructions_text", "updated_at"])

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-generate-sign",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        mock_generate_pose_from_gloss.assert_not_called()
        item.refresh_from_db()
        self.assertEqual(item.sign_status, SignStatusChoices.FAILED)

    @patch("prescriptions.views.generate_pose_from_gloss")
    @patch("prescriptions.views.generate_sign_gloss")
    def test_generate_sign_pose_failure_after_gemini_success(
        self, mock_generate_sign_gloss, mock_generate_pose_from_gloss
    ):
        from ai_integration.exceptions import AIPoseGenerationError

        mock_generate_sign_gloss.return_value = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "gloss_text": "دواء حبة الصبح قبل الاكل",
        }
        mock_generate_pose_from_gloss.side_effect = AIPoseGenerationError(
            "AI service unreachable"
        )

        prescription = self._create_prescription()
        item = prescription.items.first()
        item.instructions_text = "خذ حبة في الصباح قبل الطعام"
        item.supporting_text = "old gloss"
        item.save(update_fields=["instructions_text", "supporting_text", "updated_at"])

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-generate-sign",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data["code"], "pose_generation_failed")
        self.assertEqual(
            response.data["detail"], "Gloss was generated but pose generation failed."
        )

        # Supporting text is saved, but pose fields are cleared/empty, and status is failed
        item.refresh_from_db()
        self.assertEqual(item.supporting_text, "دواء حبة الصبح قبل الاكل")
        self.assertEqual(item.pose_file_path, "")
        self.assertEqual(item.pose_shape, None)
        self.assertEqual(
            item.ai_metadata["gloss"]["model"],
            "gemini-2.5-flash",
        )
        self.assertEqual(item.sign_status, SignStatusChoices.FAILED)

    def test_archived_prescription_cannot_be_modified_or_processed(self):
        prescription = self._create_prescription()
        item = prescription.items.first()
        prescription.status = PrescriptionStatusChoices.ARCHIVED
        prescription.save(update_fields=["status", "updated_at"])

        add_response = self.client.post(
            reverse(
                "pharmacist-prescription-items",
                kwargs={"prescription_id": prescription.id},
            ),
            {"medication_name": "Blocked"},
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
        transcribe_response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"audio": self.build_audio_upload()},
            format="multipart",
        )
        approve_response = self.client.post(
            reverse(
                "pharmacist-prescription-item-approve-transcript",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"approved_instruction_text": "Approved"},
            format="json",
        )
        generate_response = self.client.post(
            reverse(
                "pharmacist-prescription-item-generate-sign",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {},
            format="json",
        )

        for response in (
            add_response,
            update_response,
            transcribe_response,
            approve_response,
            generate_response,
        ):
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(response.data["code"], "prescription_archived")

    def test_approve_transcript_requires_non_blank_text(self):
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-approve-transcript",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {"approved_instruction_text": ""},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "missing_approved_instruction_text")

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
        self.assertEqual(response.data["code"], "missing_audio_file")

    @patch("prescriptions.views.transcribe_audio_file")
    def test_transcribe_audio_accepts_common_audio_formats(self, mock_transcribe):
        mock_transcribe.return_value = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "transcript": "Audio transcript",
        }
        cases = [
            ("instructions.m4a", "audio/x-m4a"),
            ("instructions.ogg", "audio/ogg"),
            ("instructions.wav", "audio/wav"),
            ("instructions.mp3", "audio/mpeg"),
        ]

        for filename, content_type in cases:
            with self.subTest(filename=filename, content_type=content_type):
                prescription = self._create_prescription()
                item = prescription.items.first()
                response = self.client.post(
                    reverse(
                        "pharmacist-prescription-item-transcribe-audio",
                        kwargs={
                            "prescription_id": prescription.id,
                            "item_id": item.id,
                        },
                    ),
                    {
                        "audio": self.build_audio_upload(
                            filename=filename,
                            content_type=content_type,
                        )
                    },
                    format="multipart",
                )

                self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(mock_transcribe.call_count, len(cases))

    @patch("prescriptions.views.transcribe_audio_file")
    def test_transcribe_audio_accepts_octet_stream_with_audio_extension(
        self, mock_transcribe
    ):
        mock_transcribe.return_value = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "transcript": "Audio transcript",
        }
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {
                "audio": self.build_audio_upload(
                    filename="instructions.mp3",
                    content_type="application/octet-stream",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_transcribe.assert_called_once()

    @override_settings(GEMINI_API_KEY="")
    def test_transcribe_audio_provider_not_configured_response(self):
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

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["code"], "transcription_provider_not_configured")
        self.assertEqual(
            response.data["transcription_status"], TranscriptionStatusChoices.FAILED
        )
        item.refresh_from_db()
        self.assertTrue(item.instructions_audio)
        self.assertEqual(item.transcription_status, TranscriptionStatusChoices.FAILED)

    def test_transcribe_audio_rejects_unsupported_audio_extension(self):
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {
                "audio": self.build_audio_upload(
                    filename="instructions.txt",
                    content_type="application/octet-stream",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "unsupported_audio_type")

    def test_transcribe_audio_rejects_image_extension(self):
        prescription = self._create_prescription()
        item = prescription.items.first()

        response = self.client.post(
            reverse(
                "pharmacist-prescription-item-transcribe-audio",
                kwargs={"prescription_id": prescription.id, "item_id": item.id},
            ),
            {
                "audio": self.build_audio_upload(
                    filename="instructions.jpg",
                    content_type="image/jpeg",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "unsupported_audio_type")

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
        self.assertEqual(response.data["code"], "audio_too_large")

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
        item.instructions_transcript_raw = "Old raw"
        item.instructions_transcript_edited = "Existing text"
        item.save(
            update_fields=[
                "instructions_text",
                "instructions_transcript_raw",
                "instructions_transcript_edited",
                "updated_at",
            ]
        )

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
            "Audio transcription failed",
        )
        item.refresh_from_db()
        self.assertEqual(item.instructions_text, "")
        self.assertEqual(item.instructions_transcript_raw, "")
        self.assertEqual(item.instructions_transcript_edited, "")
        self.assertTrue(item.instructions_audio)
        self.assertEqual(item.transcription_status, TranscriptionStatusChoices.FAILED)
        self.assertEqual(item.transcription_provider, "gemini")
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
                "quantity": "1",
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
                "quantity": "1",
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
                        "quantity": "1",
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

    @override_settings(PRESCRIPTION_TRANSCRIPTION_BACKEND="placeholder")
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

    @override_settings(PRESCRIPTION_TRANSCRIPTION_BACKEND="failing")
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
