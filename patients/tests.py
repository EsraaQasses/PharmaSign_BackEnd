from datetime import date

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from common.choices import (
    GenderChoices,
    HearingDisabilityLevelChoices,
    PrescriptionStatusChoices,
    RoleChoices,
)
from organizations.models import Organization, OrganizationStaffProfile
from patients.models import (
    PatientMedicalInfo,
    PatientProfile,
    PatientSession,
    PatientSessionQR,
)
from pharmacies.models import PharmacistProfile, Pharmacy
from prescriptions.models import Prescription, PrescriptionItem


class PatientSessionFlowTests(APITestCase):
    def test_start_by_qr_creates_patient_session_record(self):
        organization = Organization.objects.create(name="Org Session")
        patient_user = User.objects.create_user(
            email="patient.session@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        patient_profile = PatientProfile.objects.create(
            user=patient_user,
            organization=organization,
            full_name="Patient Session",
            birth_date=date(1998, 5, 10),
            gender=GenderChoices.FEMALE,
            hearing_disability_level=HearingDisabilityLevelChoices.MODERATE,
            qr_code_value="session-qr-token",
            qr_is_active=True,
        )
        PatientMedicalInfo.objects.create(
            patient=patient_profile,
            allergies="Penicillin",
            chronic_conditions="Asthma",
        )

        pharmacist_user = User.objects.create_user(
            email="pharmacist.session@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        pharmacy = Pharmacy.objects.create(
            name="Session Pharmacy",
            address="Damascus",
            organization=organization,
            is_contracted_with_organization=True,
        )
        PharmacistProfile.objects.create(
            user=pharmacist_user,
            pharmacy=pharmacy,
            full_name="Pharmacist Session",
            is_approved=True,
        )

        self.client.force_authenticate(pharmacist_user)
        response = self.client.post(
            reverse("patient-session-start-by-qr"),
            {"qr_code_value": "session-qr-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("session", response.data)
        self.assertIn("patient_summary", response.data)
        self.assertEqual(PatientSession.objects.count(), 1)
        session = PatientSession.objects.get()
        self.assertEqual(session.patient, patient_profile)
        self.assertEqual(session.pharmacist.user, pharmacist_user)
        self.assertEqual(session.pharmacy, pharmacy)

    def test_unapproved_pharmacist_cannot_start_patient_session(self):
        organization = Organization.objects.create(name="Org Unapproved")
        patient_user = User.objects.create_user(
            email="patient.unapproved@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        patient_profile = PatientProfile.objects.create(
            user=patient_user,
            organization=organization,
            full_name="Patient Unapproved",
            qr_code_value="unapproved-qr-token",
            qr_is_active=True,
        )
        PatientMedicalInfo.objects.create(patient=patient_profile)

        pharmacist_user = User.objects.create_user(
            email="pharmacist.unapproved@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        pharmacy = Pharmacy.objects.create(
            name="Unapproved Pharmacy", address="Damascus"
        )
        PharmacistProfile.objects.create(
            user=pharmacist_user,
            pharmacy=pharmacy,
            full_name="Unapproved Pharmacist",
            is_approved=False,
        )

        self.client.force_authenticate(pharmacist_user)
        response = self.client.post(
            reverse("patient-session-start-by-qr"),
            {"qr_code_value": "unapproved-qr-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(PatientSession.objects.count(), 0)

    def test_patient_me_rejects_pharmacist(self):
        pharmacist_user = User.objects.create_user(
            email="patient.me.pharmacist@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        pharmacy = Pharmacy.objects.create(name="Patient Me Reject", address="Damascus")
        PharmacistProfile.objects.create(
            user=pharmacist_user,
            pharmacy=pharmacy,
            full_name="Wrong Role",
            is_approved=True,
        )

        self.client.force_authenticate(pharmacist_user)
        response = self.client.get(reverse("patient-me"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patient_me_patch_persists_blood_type(self):
        patient_user = User.objects.create_user(
            email="patient.blood.patch@example.com",
            password="StrongPass123!",
            phone_number="0984201534",
            role=RoleChoices.PATIENT,
        )
        patient = PatientProfile.objects.create(
            user=patient_user,
            full_name="Old Patient Name",
            phone_number="0984201534",
        )
        PatientMedicalInfo.objects.create(patient=patient)

        self.client.force_authenticate(patient_user)
        response = self.client.patch(
            reverse("patient-me"),
            {
                "full_name": "ام حبيب",
                "phone": "0984201534",
                "blood_type": "A_POS",
                "allergies": "الحليب، اللحمة، الدهون",
                "chronic_conditions": "سكري، ضغط، القلب",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["blood_type"], "A_POS")
        patient.medical_info.refresh_from_db()
        self.assertEqual(patient.medical_info.blood_type, "A_POS")
        self.assertEqual(response.data["full_name"], "ام حبيب")
        self.assertEqual(response.data["phone"], "0984201534")
        self.assertEqual(response.data["allergies"], "الحليب، اللحمة، الدهون")
        self.assertEqual(response.data["chronic_conditions"], "سكري، ضغط، القلب")

    def test_patient_me_get_returns_saved_blood_type_after_patch(self):
        patient_user = User.objects.create_user(
            email="patient.blood.get@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(user=patient_user, full_name="Blood GET Patient")

        self.client.force_authenticate(patient_user)
        patch_response = self.client.patch(
            reverse("patient-me"),
            {"blood_type": "A_POS"},
            format="json",
        )
        get_response = self.client.get(reverse("patient-me"))

        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["blood_type"], "A_POS")

    def test_patient_me_accepts_all_valid_blood_type_choices(self):
        patient_user = User.objects.create_user(
            email="patient.blood.choices@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(
            user=patient_user,
            full_name="Blood Choices Patient",
        )
        valid_choices = (
            "A_POS",
            "A_NEG",
            "B_POS",
            "B_NEG",
            "AB_POS",
            "AB_NEG",
            "O_POS",
            "O_NEG",
        )

        self.client.force_authenticate(patient_user)
        for blood_type in valid_choices:
            with self.subTest(blood_type=blood_type):
                response = self.client.patch(
                    reverse("patient-me"),
                    {"blood_type": blood_type},
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data["blood_type"], blood_type)

    def test_patient_me_rejects_invalid_blood_type(self):
        patient_user = User.objects.create_user(
            email="patient.blood.invalid@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        patient = PatientProfile.objects.create(
            user=patient_user,
            full_name="Invalid Blood Patient",
        )
        PatientMedicalInfo.objects.create(patient=patient, blood_type="A_POS")

        self.client.force_authenticate(patient_user)
        response = self.client.patch(
            reverse("patient-me"),
            {"blood_type": "A_PLUS"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("blood_type", response.data)
        patient.medical_info.refresh_from_db()
        self.assertEqual(patient.medical_info.blood_type, "A_POS")

    def test_patient_settings_persist_after_patch_then_get(self):
        patient_user = User.objects.create_user(
            email="patient.settings@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(
            user=patient_user,
            full_name="Settings Patient",
        )

        self.client.force_authenticate(patient_user)
        patch_response = self.client.patch(
            reverse("patient-settings"),
            {
                "notifications_enabled": False,
                "prescription_reminders": False,
                "dark_mode": True,
                "use_biometrics": True,
            },
            format="json",
        )
        get_response = self.client.get(reverse("patient-settings"))

        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertFalse(get_response.data["notifications_enabled"])
        self.assertFalse(get_response.data["prescription_reminders"])
        self.assertTrue(get_response.data["dark_mode"])
        self.assertTrue(get_response.data["use_biometrics"])

    def test_admin_can_create_patient_account_without_email(self):
        admin_user = User.objects.create_user(
            email="admin.create.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.post(
            reverse("admin-patient-create-account"),
            {
                "full_name": "Created By Admin",
                "phone_number": "5555000",
                "date_of_birth": "1999-01-01",
                "gender": GenderChoices.FEMALE,
                "blood_type": "A_POS",
                "allergies": "Penicillin",
                "chronic_conditions": "Asthma",
                "regular_medications": "Vitamin D",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["user"]["email"])
        self.assertEqual(response.data["user"]["phone_number"], "5555000")
        self.assertTrue(response.data["temporary_password_generated"])
        self.assertIn("temporary_password", response.data)
        self.assertFalse(
            User.objects.get(phone_number="5555000").password
            == response.data["temporary_password"]
        )

    def test_patient_cannot_create_admin_patient_account(self):
        patient_user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5555001",
            role=RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(user=patient_user, full_name="Normal Patient")
        self.client.force_authenticate(patient_user)

        response = self.client.post(
            reverse("admin-patient-create-account"),
            {
                "full_name": "Blocked Patient",
                "phone_number": "5555002",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_generate_patient_login_qr(self):
        admin_user = User.objects.create_user(
            email="admin.qr@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        patient_user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5555003",
            role=RoleChoices.PATIENT,
        )
        patient = PatientProfile.objects.create(
            user=patient_user,
            full_name="QR Patient",
        )
        self.client.force_authenticate(admin_user)

        response = self.client.post(
            reverse("admin-patient-login-qr", kwargs={"patient_id": patient.id}),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["patient_id"], patient.id)
        self.assertTrue(response.data["qr_token"])
        self.assertEqual(response.data["qr_token"], response.data["qr_payload"])
        self.assertNotIn("token_hash", response.data)

    def test_patient_can_login_using_qr_token(self):
        admin_user = User.objects.create_user(
            email="admin.qr.login@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        patient_user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5555004",
            role=RoleChoices.PATIENT,
        )
        patient = PatientProfile.objects.create(
            user=patient_user,
            full_name="QR Login Patient",
        )
        self.client.force_authenticate(admin_user)
        qr_response = self.client.post(
            reverse("admin-patient-login-qr", kwargs={"patient_id": patient.id}),
            {},
            format="json",
        )
        self.client.force_authenticate(None)

        login_response = self.client.post(
            reverse("accounts:patient_qr_login"),
            {"qr_token": qr_response.data["qr_token"]},
            format="json",
        )

        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertEqual(login_response.data["user"]["role"], RoleChoices.PATIENT)
        self.assertEqual(login_response.data["user"]["phone_number"], "5555004")
        self.assertIn("access", login_response.data)
        self.assertIn("refresh", login_response.data)

    def test_revoked_qr_token_cannot_login(self):
        admin_user = User.objects.create_user(
            email="admin.qr.revoke@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        patient_user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5555005",
            role=RoleChoices.PATIENT,
        )
        patient = PatientProfile.objects.create(
            user=patient_user,
            full_name="QR Revoke Patient",
        )
        self.client.force_authenticate(admin_user)
        qr_response = self.client.post(
            reverse("admin-patient-login-qr", kwargs={"patient_id": patient.id}),
            {},
            format="json",
        )
        self.client.post(
            reverse("admin-patient-login-qr-revoke", kwargs={"patient_id": patient.id}),
            {},
            format="json",
        )
        self.client.force_authenticate(None)

        login_response = self.client.post(
            reverse("accounts:patient_qr_login"),
            {"qr_token": qr_response.data["qr_token"]},
            format="json",
        )

        self.assertEqual(login_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(login_response.data["detail"][0], "QR token has been revoked.")

    def test_pharmacist_cannot_start_session_for_patient_outside_contracted_scope(self):
        patient_org = Organization.objects.create(name="Patient Org")
        pharmacy_org = Organization.objects.create(name="Pharmacy Org")

        patient_user = User.objects.create_user(
            email="patient.scope@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        patient_profile = PatientProfile.objects.create(
            user=patient_user,
            organization=patient_org,
            full_name="Patient Scope",
            qr_code_value="scope-qr-token",
            qr_is_active=True,
        )
        PatientMedicalInfo.objects.create(patient=patient_profile)

        pharmacist_user = User.objects.create_user(
            email="pharmacist.scope@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        pharmacy = Pharmacy.objects.create(
            name="Scoped Pharmacy",
            address="Damascus",
            organization=pharmacy_org,
            is_contracted_with_organization=True,
        )
        PharmacistProfile.objects.create(
            user=pharmacist_user,
            pharmacy=pharmacy,
            full_name="Scoped Pharmacist",
            is_approved=True,
        )

        self.client.force_authenticate(pharmacist_user)
        response = self.client.post(
            reverse("patient-session-start-by-qr"),
            {"qr_code_value": "scope-qr-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(PatientSession.objects.count(), 0)


class OrganizationStaffPermissionTests(APITestCase):
    def test_staff_without_manage_patients_cannot_list_enrollments(self):
        organization = Organization.objects.create(name="Org Staff Patients")
        staff_user = User.objects.create_user(
            email="staff.patients@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=staff_user,
            organization=organization,
            can_manage_patients=False,
            can_manage_pharmacists=False,
        )

        self.client.force_authenticate(staff_user)
        response = self.client.get(reverse("patient-enrollment-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_cannot_generate_qr_for_patient_outside_organization(self):
        staff_org = Organization.objects.create(name="Staff Org")
        patient_org = Organization.objects.create(name="Patient Org Other")

        staff_user = User.objects.create_user(
            email="staff.scope@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=staff_user,
            organization=staff_org,
            can_manage_patients=True,
        )

        patient_user = User.objects.create_user(
            email="patient.otherorg@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        patient_profile = PatientProfile.objects.create(
            user=patient_user,
            organization=patient_org,
            full_name="Other Org Patient",
        )

        self.client.force_authenticate(staff_user)
        response = self.client.post(
            reverse("patient-generate-qr", kwargs={"pk": patient_profile.pk}),
            {"regenerate": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PatientSessionQRFlowTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Session QR Org")
        self.patient_user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5558000",
            role=RoleChoices.PATIENT,
        )
        self.patient = PatientProfile.objects.create(
            user=self.patient_user,
            organization=self.organization,
            full_name="Session QR Patient",
            phone_number="5558000",
            birth_date=date(2000, 1, 1),
            gender=GenderChoices.FEMALE,
        )
        PatientMedicalInfo.objects.create(
            patient=self.patient,
            allergies="Penicillin",
            chronic_conditions="Asthma",
            notes="Vitamin D",
            is_pregnant=False,
            is_breastfeeding=True,
        )
        self.pharmacist_user = User.objects.create_user(
            email="approved.session@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        self.pharmacy = Pharmacy.objects.create(
            name="Approved Pharmacy",
            address="Damascus",
            organization=self.organization,
            is_contracted_with_organization=True,
        )
        self.pharmacist = PharmacistProfile.objects.create(
            user=self.pharmacist_user,
            pharmacy=self.pharmacy,
            full_name="Approved Pharmacist",
            is_approved=True,
        )
        self.other_patient_user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5558001",
            role=RoleChoices.PATIENT,
        )
        self.other_patient = PatientProfile.objects.create(
            user=self.other_patient_user,
            organization=self.organization,
            full_name="Other Session QR Patient",
            phone_number="5558001",
        )

    def generate_qr(self):
        self.client.force_authenticate(self.patient_user)
        response = self.client.post(reverse("patient-session-qr"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("qr_payload", response.data)
        self.assertIn("expires_at", response.data)
        self.assertEqual(response.data["expires_in_seconds"], 300)
        return response.data["qr_token"]

    def create_submitted_prescription(self, patient, submitted_at, doctor_name):
        prescription = Prescription.objects.create(
            patient=patient,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            doctor_name=doctor_name,
            diagnosis="Flu",
            notes="Take medicines after food",
            status=PrescriptionStatusChoices.SUBMITTED,
            submitted_at=submitted_at,
        )
        PrescriptionItem.objects.create(
            prescription=prescription,
            medicine_name="Paracetamol",
            dosage="500mg",
            frequency="3 times daily",
            duration="5 days",
            instructions_text="Take one tablet after food three times a day",
        )
        return prescription

    def test_patient_can_generate_session_qr(self):
        token = self.generate_qr()

        self.assertTrue(token)
        self.assertEqual(PatientSessionQR.objects.count(), 1)
        self.assertNotIn(
            "token_hash",
            self.client.post(reverse("patient-session-qr"), {}, format="json").data,
        )

    def test_pharmacist_cannot_generate_patient_session_qr(self):
        self.client.force_authenticate(self.pharmacist_user)

        response = self.client.post(reverse("patient-session-qr"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_cannot_generate_session_qr(self):
        response = self.client.post(reverse("patient-session-qr"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_approved_pharmacist_can_start_session_using_valid_qr(self):
        token = self.generate_qr()
        self.client.force_authenticate(self.pharmacist_user)

        response = self.client.post(
            reverse("pharmacist-session-start-by-qr"),
            {"qr_token": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data["session"]["status"], PatientSession.STATUS_ACTIVE
        )
        self.assertEqual(response.data["patient"]["id"], self.patient.id)
        self.assertIn("started_at", response.data["session"])
        self.assertIn("expires_at", response.data["session"])
        self.assertEqual(response.data["pharmacist"]["id"], self.pharmacist.id)
        self.assertEqual(response.data["pharmacy"]["id"], self.pharmacy.id)
        self.assertEqual(PatientSession.objects.count(), 1)
        session = PatientSession.objects.get()
        self.assertEqual(session.patient, self.patient)
        self.assertEqual(session.pharmacist, self.pharmacist)
        self.assertEqual(session.pharmacy, self.pharmacy)

    def test_start_session_response_includes_clinical_context(self):
        now = timezone.now()
        draft = Prescription.objects.create(
            patient=self.patient,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            doctor_name="Draft Doctor",
            diagnosis="Draft",
            status=PrescriptionStatusChoices.DRAFT,
        )
        newest = self.create_submitted_prescription(
            self.patient, now - timezone.timedelta(hours=1), "Doctor Newest"
        )
        second = self.create_submitted_prescription(
            self.patient, now - timezone.timedelta(hours=2), "Doctor Second"
        )
        third = self.create_submitted_prescription(
            self.patient, now - timezone.timedelta(hours=3), "Doctor Third"
        )
        fourth = self.create_submitted_prescription(
            self.patient, now - timezone.timedelta(hours=4), "Doctor Fourth"
        )
        other_patient_prescription = self.create_submitted_prescription(
            self.other_patient, now, "Doctor Other Patient"
        )
        token = self.generate_qr()
        self.client.force_authenticate(self.pharmacist_user)

        response = self.client.post(
            reverse("pharmacist-session-start-by-qr"),
            {"qr_token": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("medical_info", response.data)
        self.assertIn("recent_prescriptions", response.data)
        self.assertEqual(response.data["patient"]["gender"], "female")
        self.assertEqual(response.data["patient"]["birth_date"], date(2000, 1, 1))
        self.assertIn("hearing_disability_level", response.data["patient"])
        self.assertEqual(response.data["medical_info"]["allergies"], "Penicillin")
        self.assertEqual(response.data["medical_info"]["chronic_conditions"], "Asthma")
        self.assertEqual(response.data["medical_info"]["notes"], "Vitamin D")
        self.assertEqual(
            response.data["medical_info"]["regular_medications"], "Vitamin D"
        )
        self.assertFalse(response.data["medical_info"]["is_pregnant"])
        self.assertTrue(response.data["medical_info"]["is_breastfeeding"])
        recent_ids = [item["id"] for item in response.data["recent_prescriptions"]]
        self.assertEqual(recent_ids, [newest.id, second.id, third.id])
        self.assertNotIn(fourth.id, recent_ids)
        self.assertNotIn(draft.id, recent_ids)
        self.assertNotIn(other_patient_prescription.id, recent_ids)
        self.assertEqual(
            response.data["recent_prescriptions"][0]["items"][0]["medicine_name"],
            "Paracetamol",
        )
        self.assertNotIn("qr_code_value", response.data["patient"])
        self.assertNotIn("qr_is_active", response.data["patient"])
        self.assertNotIn("token_hash", response.data)

    def test_start_session_accepts_qr_payload_alias(self):
        token = self.generate_qr()
        self.client.force_authenticate(self.pharmacist_user)

        response = self.client.post(
            reverse("pharmacist-session-start-by-qr"),
            {"qr_payload": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_unapproved_pharmacist_cannot_start_session(self):
        token = self.generate_qr()
        unapproved_user = User.objects.create_user(
            email="unapproved.session@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        PharmacistProfile.objects.create(
            user=unapproved_user,
            pharmacy=self.pharmacy,
            full_name="Unapproved",
            is_approved=False,
        )
        self.client.force_authenticate(unapproved_user)

        response = self.client.post(
            reverse("pharmacist-session-start-by-qr"),
            {"qr_token": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Pharmacist account is not approved.")

    def test_unapproved_pharmacist_cannot_list_sessions(self):
        unapproved_user = User.objects.create_user(
            email="unapproved.list.session@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        PharmacistProfile.objects.create(
            user=unapproved_user,
            pharmacy=self.pharmacy,
            full_name="Unapproved List",
            is_approved=False,
        )
        self.client.force_authenticate(unapproved_user)

        response = self.client.get(reverse("pharmacist-sessions"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Pharmacist account is not approved.")

    def test_unapproved_pharmacist_cannot_end_session(self):
        session = PatientSession.objects.create(
            patient=self.patient,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            status=PatientSession.STATUS_ACTIVE,
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )
        unapproved_user = User.objects.create_user(
            email="unapproved.end.session@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        PharmacistProfile.objects.create(
            user=unapproved_user,
            pharmacy=self.pharmacy,
            full_name="Unapproved End",
            is_approved=False,
        )
        self.client.force_authenticate(unapproved_user)

        response = self.client.post(
            reverse("pharmacist-session-end", kwargs={"session_id": session.id}),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Pharmacist account is not approved.")

    def test_patient_cannot_start_session_by_qr(self):
        token = self.generate_qr()
        self.client.force_authenticate(self.patient_user)

        response = self.client.post(
            reverse("pharmacist-session-start-by-qr"),
            {"qr_token": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_qr_rejected(self):
        self.client.force_authenticate(self.pharmacist_user)

        response = self.client.post(
            reverse("pharmacist-session-start-by-qr"),
            {"qr_token": "not-valid"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Invalid QR token")
        self.assertEqual(response.data["code"], "qr_invalid")

    def test_missing_qr_token_rejected(self):
        self.client.force_authenticate(self.pharmacist_user)

        response = self.client.post(
            reverse("pharmacist-session-start-by-qr"),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "missing_required_field")
        self.assertIn("qr_token", response.data["fields"])

    def test_expired_qr_rejected(self):
        token = self.generate_qr()
        qr = PatientSessionQR.objects.get()
        qr.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        qr.save(update_fields=["expires_at", "updated_at"])
        self.client.force_authenticate(self.pharmacist_user)

        response = self.client.post(
            reverse("pharmacist-session-start-by-qr"),
            {"qr_token": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "QR token has expired")
        self.assertEqual(response.data["code"], "qr_expired")

    def test_used_qr_rejected_on_second_scan(self):
        token = self.generate_qr()
        self.client.force_authenticate(self.pharmacist_user)
        first = self.client.post(
            reverse("pharmacist-session-start-by-qr"),
            {"qr_token": token},
            format="json",
        )
        second = self.client.post(
            reverse("pharmacist-session-start-by-qr"),
            {"qr_token": token},
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            second.data["detail"],
            "QR token has already been used",
        )
        self.assertEqual(second.data["code"], "qr_used")

    def test_revoked_qr_rejected(self):
        token = self.generate_qr()
        qr = PatientSessionQR.objects.get()
        qr.revoke()
        self.client.force_authenticate(self.pharmacist_user)

        response = self.client.post(
            reverse("pharmacist-session-start-by-qr"),
            {"qr_token": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "QR token has been revoked")
        self.assertEqual(response.data["code"], "qr_revoked")

    def test_pharmacist_can_list_only_own_sessions_and_filter_active(self):
        token = self.generate_qr()
        self.client.force_authenticate(self.pharmacist_user)
        self.client.post(
            reverse("pharmacist-session-start-by-qr"),
            {"qr_token": token},
            format="json",
        )
        other_user = User.objects.create_user(
            email="other.session@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        other_pharmacy = Pharmacy.objects.create(
            name="Other Pharmacy", address="Aleppo"
        )
        other_pharmacist = PharmacistProfile.objects.create(
            user=other_user,
            pharmacy=other_pharmacy,
            full_name="Other Pharmacist",
            is_approved=True,
        )
        PatientSession.objects.create(
            patient=self.patient,
            pharmacist=other_pharmacist,
            pharmacy=other_pharmacy,
            status=PatientSession.STATUS_ACTIVE,
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )

        response = self.client.get(reverse("pharmacist-sessions"))
        active_response = self.client.get(
            reverse("pharmacist-sessions"),
            {"status": PatientSession.STATUS_ACTIVE},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(active_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(active_response.data), 1)
        self.assertEqual(response.data[0]["patient"]["id"], self.patient.id)

    def test_pharmacist_can_end_own_session(self):
        token = self.generate_qr()
        self.client.force_authenticate(self.pharmacist_user)
        start_response = self.client.post(
            reverse("pharmacist-session-start-by-qr"),
            {"qr_token": token},
            format="json",
        )
        session_id = start_response.data["session"]["id"]

        response = self.client.post(
            reverse("pharmacist-session-end", kwargs={"session_id": session_id}),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Session ended successfully")
        self.assertEqual(response.data["session"]["id"], session_id)
        self.assertEqual(response.data["session"]["status"], "ended")
        self.assertIn("ended_at", response.data["session"])
        session = PatientSession.objects.get(pk=session_id)
        self.assertEqual(session.status, PatientSession.STATUS_COMPLETED)
        self.assertIsNotNone(session.ended_at)

    def test_pharmacist_cannot_end_another_pharmacists_session(self):
        other_user = User.objects.create_user(
            email="owner.session@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        other_pharmacy = Pharmacy.objects.create(name="Owner Pharmacy", address="Homs")
        other_pharmacist = PharmacistProfile.objects.create(
            user=other_user,
            pharmacy=other_pharmacy,
            full_name="Owner Pharmacist",
            is_approved=True,
        )
        session = PatientSession.objects.create(
            patient=self.patient,
            pharmacist=other_pharmacist,
            pharmacy=other_pharmacy,
            status=PatientSession.STATUS_ACTIVE,
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )
        self.client.force_authenticate(self.pharmacist_user)

        response = self.client.post(
            reverse("pharmacist-session-end", kwargs={"session_id": session.id}),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
