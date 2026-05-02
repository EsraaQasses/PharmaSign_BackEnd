from datetime import date

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from common.choices import (
    ApprovalStatusChoices,
    GenderChoices,
    HearingDisabilityLevelChoices,
    RoleChoices,
)
from organizations.models import Organization
from patients.models import PatientEnrollment, PatientProfile
from pharmacies.models import PharmacistProfile, Pharmacy

from .models import PhoneOTP, User


class AuthAndPatientFlowTests(APITestCase):
    def request_registration_otp(self, phone_number):
        response = self.client.post(
            reverse("accounts:patient_register_request_otp"),
            {"phone_number": phone_number},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["debug_otp"]

    def request_role_registration_otp(self, role, phone_number):
        response = self.client.post(
            reverse("accounts:register_request_otp"),
            {"role": role, "phone_number": phone_number},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["debug_otp"]

    @override_settings(DEBUG=True)
    def test_request_registration_otp_with_phone_number_returns_debug_otp(self):
        response = self.client.post(
            reverse("accounts:patient_register_request_otp"),
            {"phone_number": "5557000"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Registration OTP generated successfully.")
        self.assertEqual(response.data["expires_in_seconds"], 300)
        self.assertRegex(response.data["debug_otp"], r"^\d{6}$")
        self.assertEqual(PhoneOTP.objects.count(), 1)
        self.assertEqual(
            PhoneOTP.objects.get().purpose,
            PhoneOTP.PURPOSE_PATIENT_REGISTER,
        )
        self.assertNotIn(response.data["debug_otp"], PhoneOTP.objects.get().code_hash)

    @override_settings(DEBUG=True)
    def test_request_registration_otp_with_phone_alias_works(self):
        response = self.client.post(
            reverse("accounts:patient_register_request_otp"),
            {"phone": "5557001"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("debug_otp", response.data)

    @override_settings(DEBUG=True)
    def test_request_registration_otp_for_pharmacist_role_returns_debug_otp(self):
        response = self.client.post(
            reverse("accounts:register_request_otp"),
            {"role": "pharmacist", "phone_number": "5557021"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertRegex(response.data["debug_otp"], r"^\d{6}$")
        self.assertEqual(
            PhoneOTP.objects.get(phone_number="5557021").purpose,
            PhoneOTP.PURPOSE_PHARMACIST_REGISTER,
        )

    @override_settings(DEBUG=True)
    def test_pharmacist_specific_registration_otp_endpoint_works(self):
        response = self.client.post(
            reverse("accounts:pharmacist_register_request_otp"),
            {"phone": "5557022"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("debug_otp", response.data)

    def test_request_registration_otp_for_existing_phone_returns_400(self):
        User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557002",
            role=RoleChoices.PATIENT,
        )

        response = self.client.post(
            reverse("accounts:patient_register_request_otp"),
            {"phone_number": "5557002"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"][0], "Phone number is already registered.")

    @override_settings(DEBUG=False)
    def test_debug_false_registration_otp_response_does_not_include_debug_otp(self):
        response = self.client.post(
            reverse("accounts:patient_register_request_otp"),
            {"phone_number": "5557003"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("debug_otp", response.data)
        self.assertNotIn("code_hash", response.data)

    @override_settings(DEBUG=True)
    def test_patient_register_without_otp_fails(self):
        response = self.client.post(
            reverse("accounts:patient_register"),
            {
                "password": "StrongPass123!",
                "full_name": "Missing OTP",
                "phone_number": "5557004",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("otp", response.data)

    @override_settings(DEBUG=True)
    def test_patient_register_with_correct_otp_succeeds(self):
        otp = self.request_registration_otp("5557005")

        response = self.client.post(
            reverse("accounts:patient_register"),
            {
                "password": "StrongPass123!",
                "full_name": "Phone Patient",
                "phone_number": "5557005",
                "otp": otp,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(phone_number="5557005")
        self.assertIsNone(user.email)
        self.assertEqual(user.approval_status, ApprovalStatusChoices.PENDING)
        self.assertFalse(user.is_verified)
        self.assertEqual(response.data["user"]["email"], None)
        self.assertEqual(response.data["approval_status"], ApprovalStatusChoices.PENDING)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    @override_settings(DEBUG=True)
    def test_patient_register_with_phone_alias_and_otp_succeeds(self):
        otp = self.request_registration_otp("5557006")

        response = self.client.post(
            reverse("accounts:patient_register"),
            {
                "password": "StrongPass123!",
                "name": "Alias Patient",
                "phone": "5557006",
                "otp": otp,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(phone_number="5557006")
        self.assertEqual(user.patient_profile.full_name, "Alias Patient")

    @override_settings(DEBUG=True)
    def test_patient_register_with_optional_email_and_otp_succeeds(self):
        otp = self.request_registration_otp("5557007")

        response = self.client.post(
            reverse("accounts:patient_register"),
            {
                "email": "patient.optional@example.com",
                "password": "StrongPass123!",
                "confirm_password": "StrongPass123!",
                "full_name": "Optional Email",
                "phone_number": "5557007",
                "otp": otp,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["email"], "patient.optional@example.com")

    @override_settings(DEBUG=True)
    def test_patient_register_duplicate_email_rejected_when_email_provided(self):
        User.objects.create_user(
            email="patient.duplicate@example.com",
            password="StrongPass123!",
            phone_number="5557008",
            role=RoleChoices.PATIENT,
        )
        otp = self.request_registration_otp("5557009")

        response = self.client.post(
            reverse("accounts:patient_register"),
            {
                "email": "patient.duplicate@example.com",
                "password": "StrongPass123!",
                "full_name": "Duplicate Patient",
                "phone_number": "5557009",
                "otp": otp,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    @override_settings(DEBUG=True)
    def test_patient_register_duplicate_phone_number_fails(self):
        User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557010",
            role=RoleChoices.PATIENT,
        )
        challenge = PhoneOTP(
            phone_number="5557010",
            purpose=PhoneOTP.PURPOSE_PATIENT_REGISTER,
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )
        challenge.set_code("123456")
        challenge.save()

        response = self.client.post(
            reverse("accounts:patient_register"),
            {
                "password": "StrongPass123!",
                "full_name": "Duplicate Phone",
                "phone_number": "5557010",
                "otp": "123456",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone_number", response.data)

    @override_settings(DEBUG=True)
    def test_patient_register_wrong_otp_fails_and_increments_attempts(self):
        self.request_registration_otp("5557011")

        response = self.client.post(
            reverse("accounts:patient_register"),
            {
                "password": "StrongPass123!",
                "full_name": "Wrong OTP",
                "phone_number": "5557011",
                "otp": "000000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"][0], "Invalid OTP.")
        challenge = PhoneOTP.objects.get(phone_number="5557011")
        self.assertEqual(challenge.attempts, 1)
        self.assertIsNone(challenge.used_at)

    @override_settings(DEBUG=True)
    def test_after_five_wrong_attempts_registration_otp_becomes_unusable(self):
        self.request_registration_otp("5557012")

        response = None
        for _ in range(5):
            response = self.client.post(
                reverse("accounts:patient_register"),
                {
                    "password": "StrongPass123!",
                    "full_name": "Locked OTP",
                    "phone_number": "5557012",
                    "otp": "000000",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"][0], "Too many OTP attempts.")
        challenge = PhoneOTP.objects.get(phone_number="5557012")
        self.assertEqual(challenge.attempts, 5)
        self.assertIsNotNone(challenge.used_at)

    @override_settings(DEBUG=True)
    def test_expired_registration_otp_fails(self):
        otp = self.request_registration_otp("5557013")
        challenge = PhoneOTP.objects.get(phone_number="5557013")
        challenge.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        challenge.save(update_fields=["expires_at", "updated_at"])

        response = self.client.post(
            reverse("accounts:patient_register"),
            {
                "password": "StrongPass123!",
                "full_name": "Expired OTP",
                "phone_number": "5557013",
                "otp": otp,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"][0], "OTP has expired.")

    @override_settings(DEBUG=True)
    def test_used_registration_otp_cannot_be_reused(self):
        otp = self.request_registration_otp("5557014")
        first_response = self.client.post(
            reverse("accounts:patient_register"),
            {
                "password": "StrongPass123!",
                "full_name": "First OTP",
                "phone_number": "5557014",
                "otp": otp,
            },
            format="json",
        )
        second_response = self.client.post(
            reverse("accounts:patient_register"),
            {
                "password": "StrongPass123!",
                "full_name": "Second OTP",
                "phone_number": "5557015",
                "otp": otp,
            },
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(second_response.data["detail"][0], "Invalid OTP.")

    def test_admin_can_create_patient_account_from_enrollment_without_registration_otp(self):
        admin_user = User.objects.create_user(
            email="admin@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        organization = Organization.objects.create(name="Org One")
        enrollment = PatientEnrollment.objects.create(
            organization=organization,
            first_name="Ali",
            last_name="Test",
            birth_date=date(2000, 1, 1),
            gender=GenderChoices.MALE,
            hearing_disability_level=HearingDisabilityLevelChoices.MODERATE,
            created_by=admin_user,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.post(
            reverse("patient-enrollment-create-account", kwargs={"pk": enrollment.pk}),
            {
                "email": "linked@example.com",
                "password": "StrongPass123!",
                "record_access_pin": "1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        enrollment.refresh_from_db()
        self.assertTrue(enrollment.is_account_created)

    def test_login_does_not_require_otp_for_approved_user(self):
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557016",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
        )
        PatientProfile.objects.create(user=user, full_name="Login Patient")

        response = self.client.post(
            reverse("accounts:login"),
            {
                "phone_number": "5557016",
                "password": "StrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_login_by_email_still_works(self):
        user = User.objects.create_user(
            email="login.patient@example.com",
            password="StrongPass123!",
            phone_number="5557017",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
        )
        PatientProfile.objects.create(user=user, full_name="Login Patient")

        response = self.client.post(
            reverse("accounts:login"),
            {
                "email": "login.patient@example.com",
                "password": "StrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["phone_number"], "5557017")

    def test_login_without_identifier_fails(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"][0], "Email or phone number is required."
        )

    def test_login_wrong_password_fails(self):
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557018",
            role=RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(user=user, full_name="Wrong Password Login")

        response = self.client.post(
            reverse("accounts:login"),
            {
                "phone_number": "5557018",
                "password": "WrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"][0], "Invalid credentials.")

    def test_approved_pharmacist_with_unapproved_profile_cannot_login(self):
        user = User.objects.create_user(
            email=None,
            password="TestPass123!",
            phone_number="0987778589",
            role=RoleChoices.PHARMACIST,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
            is_active=True,
        )
        pharmacy = Pharmacy.objects.create(name="Login Pharmacy", address="Damascus")
        PharmacistProfile.objects.create(
            user=user,
            pharmacy=pharmacy,
            full_name="Approved Pharmacist",
            is_approved=False,
        )

        response = self.client.post(
            reverse("accounts:login"),
            {
                "phone_number": "0987778589",
                "password": "TestPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["approval_status"], ApprovalStatusChoices.PENDING)
        self.assertNotIn("access", response.data)

    def test_approved_pharmacist_with_approved_profile_can_login(self):
        user = User.objects.create_user(
            email=None,
            password="TestPass123!",
            phone_number="0987778590",
            role=RoleChoices.PHARMACIST,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
            is_active=True,
        )
        pharmacy = Pharmacy.objects.create(name="Approved Login Pharmacy", address="Damascus")
        PharmacistProfile.objects.create(
            user=user,
            pharmacy=pharmacy,
            full_name="Approved Pharmacist",
            is_approved=True,
        )

        response = self.client.post(
            reverse("accounts:login"),
            {
                "phone_number": "0987778590",
                "password": "TestPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["role"], RoleChoices.PHARMACIST)
        self.assertIn("access", response.data)

    def test_pending_pharmacist_login_returns_pending(self):
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557033",
            role=RoleChoices.PHARMACIST,
            approval_status=ApprovalStatusChoices.PENDING,
            is_active=True,
        )
        pharmacy = Pharmacy.objects.create(name="Pending Pharmacy", address="Damascus")
        PharmacistProfile.objects.create(
            user=user,
            pharmacy=pharmacy,
            full_name="Pending Pharmacist",
            is_approved=False,
        )

        response = self.client.post(
            reverse("accounts:login"),
            {"phone_number": "5557033", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["approval_status"], ApprovalStatusChoices.PENDING)
        self.assertNotIn("access", response.data)

    def test_rejected_pharmacist_login_returns_rejected_with_reason(self):
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557034",
            role=RoleChoices.PHARMACIST,
            approval_status=ApprovalStatusChoices.REJECTED,
            rejection_reason="Invalid license",
            is_active=True,
        )
        pharmacy = Pharmacy.objects.create(name="Rejected Pharmacy", address="Damascus")
        PharmacistProfile.objects.create(
            user=user,
            pharmacy=pharmacy,
            full_name="Rejected Pharmacist",
            is_approved=False,
        )

        response = self.client.post(
            reverse("accounts:login"),
            {"phone_number": "5557034", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["approval_status"], ApprovalStatusChoices.REJECTED)
        self.assertEqual(response.data["rejection_reason"], "Invalid license")
        self.assertNotIn("access", response.data)

    @override_settings(DEBUG=True)
    def test_pharmacist_register_with_valid_otp_creates_pending_account(self):
        otp = self.request_role_registration_otp("pharmacist", "5557019")
        response = self.client.post(
            reverse("accounts:pharmacist_register"),
            {
                "password": "StrongPass123!",
                "full_name": "Register Pharmacist",
                "phone_number": "5557019",
                "license_number": "LIC-7019",
                "pharmacy_name": "Register Pharmacy",
                "pharmacy_address": "Damascus",
                "otp": otp,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("access", response.data)
        user = User.objects.get(phone_number="5557019")
        self.assertEqual(user.approval_status, ApprovalStatusChoices.PENDING)
        self.assertFalse(user.is_verified)
        self.assertFalse(user.pharmacist_profile.is_approved)

    @override_settings(DEBUG=True)
    def test_pharmacist_register_requires_otp(self):
        response = self.client.post(
            reverse("accounts:pharmacist_register"),
            {
                "password": "StrongPass123!",
                "full_name": "Register Pharmacist",
                "phone_number": "5557023",
                "license_number": "LIC-7023",
                "pharmacy_name": "Register Pharmacy",
                "pharmacy_address": "Damascus",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("otp", response.data)

    @override_settings(DEBUG=True)
    def test_pharmacist_duplicate_license_rejected(self):
        existing_user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557024",
            role=RoleChoices.PHARMACIST,
        )
        pharmacy = Pharmacy.objects.create(name="Existing Pharmacy", address="Damascus")
        PharmacistProfile.objects.create(
            user=existing_user,
            pharmacy=pharmacy,
            full_name="Existing Pharmacist",
            license_number="LIC-DUP",
        )
        otp = self.request_role_registration_otp("pharmacist", "5557025")

        response = self.client.post(
            reverse("accounts:pharmacist_register"),
            {
                "password": "StrongPass123!",
                "full_name": "Duplicate Pharmacist",
                "phone_number": "5557025",
                "license_number": "LIC-DUP",
                "pharmacy_name": "Register Pharmacy",
                "pharmacy_address": "Damascus",
                "otp": otp,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("license_number", response.data)

    @override_settings(DEBUG=True)
    def test_pending_patient_cannot_log_in(self):
        otp = self.request_registration_otp("5557026")
        self.client.post(
            reverse("accounts:patient_register"),
            {
                "password": "StrongPass123!",
                "full_name": "Pending Patient",
                "phone_number": "5557026",
                "otp": otp,
            },
            format="json",
        )

        response = self.client.post(
            reverse("accounts:login"),
            {"phone": "5557026", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["approval_status"], ApprovalStatusChoices.PENDING)

    def test_rejected_patient_login_returns_rejected_with_reason(self):
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557027",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.REJECTED,
            rejection_reason="Invalid documents",
        )
        PatientProfile.objects.create(user=user, full_name="Rejected Patient")

        response = self.client.post(
            reverse("accounts:login"),
            {"phone_number": "5557027", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["approval_status"], ApprovalStatusChoices.REJECTED)
        self.assertEqual(response.data["rejection_reason"], "Invalid documents")

    def test_admin_can_approve_patient_user(self):
        admin_user = User.objects.create_user(
            email="approval.admin@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557028",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        PatientProfile.objects.create(user=user, full_name="Approve Patient")
        self.client.force_authenticate(admin_user)

        response = self.client.post(
            reverse("accounts:approve_user", kwargs={"pk": user.pk}),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.approval_status, ApprovalStatusChoices.APPROVED)
        self.assertTrue(user.is_verified)
        self.assertEqual(user.approved_by, admin_user)

    def test_admin_can_approve_pharmacist_and_profile(self):
        admin_user = User.objects.create_user(
            email="approval.pharmacist.admin@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557029",
            role=RoleChoices.PHARMACIST,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        pharmacy = Pharmacy.objects.create(name="Approve Pharmacy", address="Damascus")
        profile = PharmacistProfile.objects.create(
            user=user,
            pharmacy=pharmacy,
            full_name="Approve Pharmacist",
            is_approved=False,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.post(
            reverse("accounts:approve_user", kwargs={"pk": user.pk}),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertTrue(profile.is_approved)

    def test_normal_patient_cannot_approve_user(self):
        patient_user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557030",
            role=RoleChoices.PATIENT,
        )
        target = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557031",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        PatientProfile.objects.create(user=patient_user, full_name="Normal Patient")
        PatientProfile.objects.create(user=target, full_name="Target Patient")
        self.client.force_authenticate(patient_user)

        response = self.client.post(
            reverse("accounts:approve_user", kwargs={"pk": target.pk}),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_reject_user(self):
        admin_user = User.objects.create_user(
            email="reject.admin@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557032",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        PatientProfile.objects.create(user=user, full_name="Reject Patient")
        self.client.force_authenticate(admin_user)

        response = self.client.post(
            reverse("accounts:reject_user", kwargs={"pk": user.pk}),
            {"reason": "Invalid documents"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.approval_status, ApprovalStatusChoices.REJECTED)
        self.assertEqual(user.rejection_reason, "Invalid documents")

    def test_rejecting_pharmacist_clears_verification_and_profile_approval(self):
        admin_user = User.objects.create_user(
            email="reject.pharmacist.admin@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557040",
            role=RoleChoices.PHARMACIST,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
        )
        pharmacy = Pharmacy.objects.create(name="Reject Profile Pharmacy", address="Damascus")
        profile = PharmacistProfile.objects.create(
            user=user,
            pharmacy=pharmacy,
            full_name="Reject Profile",
            is_approved=True,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.post(
            reverse("accounts:reject_user", kwargs={"pk": user.pk}),
            {"reason": "Invalid license"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(user.approval_status, ApprovalStatusChoices.REJECTED)
        self.assertFalse(user.is_verified)
        self.assertFalse(profile.is_approved)

    def test_approved_user_with_jwt_can_access_me(self):
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557041",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
        )
        PatientProfile.objects.create(user=user, full_name="JWT Approved")
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get(reverse("accounts:me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["id"], user.id)

    def test_pending_user_with_jwt_cannot_access_protected_endpoint(self):
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557042",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        PatientProfile.objects.create(user=user, full_name="JWT Pending")
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get(reverse("accounts:me"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["approval_status"], ApprovalStatusChoices.PENDING)

    def test_rejected_user_with_jwt_cannot_access_protected_endpoint(self):
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557043",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.REJECTED,
            rejection_reason="Invalid documents",
        )
        PatientProfile.objects.create(user=user, full_name="JWT Rejected")
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get(reverse("accounts:me"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["approval_status"], ApprovalStatusChoices.REJECTED)
        self.assertEqual(response.data["rejection_reason"], "Invalid documents")

    def test_inactive_user_with_jwt_cannot_access_protected_endpoint(self):
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557044",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_active=False,
        )
        PatientProfile.objects.create(user=user, full_name="JWT Inactive")
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get(reverse("accounts:me"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "User account is inactive.")

    @override_settings(DEBUG=True)
    def test_public_otp_endpoint_still_works_without_auth(self):
        response = self.client.post(
            reverse("accounts:patient_register_request_otp"),
            {"phone_number": "5557045"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("debug_otp", response.data)

    def test_approved_user_can_refresh_token(self):
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557046",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
        )
        PatientProfile.objects.create(user=user, full_name="Refresh Approved")
        refresh = RefreshToken.for_user(user)

        response = self.client.post(
            reverse("accounts:token_refresh"),
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_pending_user_cannot_refresh_token(self):
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557047",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        PatientProfile.objects.create(user=user, full_name="Refresh Pending")
        refresh = RefreshToken.for_user(user)

        response = self.client.post(
            reverse("accounts:token_refresh"),
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["approval_status"], ApprovalStatusChoices.PENDING)

    def test_rejected_user_cannot_refresh_token(self):
        user = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557048",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.REJECTED,
            rejection_reason="Invalid documents",
        )
        PatientProfile.objects.create(user=user, full_name="Refresh Rejected")
        refresh = RefreshToken.for_user(user)

        response = self.client.post(
            reverse("accounts:token_refresh"),
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["approval_status"], ApprovalStatusChoices.REJECTED)

    def test_patient_manager_can_approve_patient_but_not_pharmacist(self):
        organization = Organization.objects.create(name="Patient Manager Org")
        manager = User.objects.create_user(
            email="patient.manager@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        from organizations.models import OrganizationStaffProfile

        OrganizationStaffProfile.objects.create(
            user=manager,
            organization=organization,
            can_manage_patients=True,
            can_manage_pharmacists=False,
        )
        patient = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557049",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        PatientProfile.objects.create(user=patient, full_name="Managed Patient")
        pharmacist = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557050",
            role=RoleChoices.PHARMACIST,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        pharmacy = Pharmacy.objects.create(name="Denied Pharmacy", address="Damascus")
        PharmacistProfile.objects.create(
            user=pharmacist,
            pharmacy=pharmacy,
            full_name="Denied Pharmacist",
        )
        self.client.force_authenticate(manager)

        patient_response = self.client.post(
            reverse("accounts:approve_user", kwargs={"pk": patient.pk}),
            {},
            format="json",
        )
        pharmacist_response = self.client.post(
            reverse("accounts:approve_user", kwargs={"pk": pharmacist.pk}),
            {},
            format="json",
        )

        self.assertEqual(patient_response.status_code, status.HTTP_200_OK)
        self.assertEqual(pharmacist_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            pharmacist_response.data["detail"],
            "You do not have permission to approve this user role.",
        )

    def test_pharmacist_manager_can_approve_pharmacist_but_not_patient(self):
        organization = Organization.objects.create(name="Pharmacist Manager Org")
        manager = User.objects.create_user(
            email="pharmacist.manager@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        from organizations.models import OrganizationStaffProfile

        OrganizationStaffProfile.objects.create(
            user=manager,
            organization=organization,
            can_manage_patients=False,
            can_manage_pharmacists=True,
        )
        patient = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557051",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        PatientProfile.objects.create(user=patient, full_name="Denied Patient")
        pharmacist = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557052",
            role=RoleChoices.PHARMACIST,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        pharmacy = Pharmacy.objects.create(name="Managed Pharmacy", address="Damascus")
        PharmacistProfile.objects.create(
            user=pharmacist,
            pharmacy=pharmacy,
            full_name="Managed Pharmacist",
        )
        self.client.force_authenticate(manager)

        pharmacist_response = self.client.post(
            reverse("accounts:approve_user", kwargs={"pk": pharmacist.pk}),
            {},
            format="json",
        )
        patient_response = self.client.post(
            reverse("accounts:approve_user", kwargs={"pk": patient.pk}),
            {},
            format="json",
        )

        self.assertEqual(pharmacist_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patient_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_can_approve_patient_and_pharmacist(self):
        admin_user = User.objects.create_superuser(
            email="super.approver@example.com",
            password="StrongPass123!",
        )
        patient = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557053",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        PatientProfile.objects.create(user=patient, full_name="Super Patient")
        pharmacist = User.objects.create_user(
            email=None,
            password="StrongPass123!",
            phone_number="5557054",
            role=RoleChoices.PHARMACIST,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        pharmacy = Pharmacy.objects.create(name="Super Pharmacy", address="Damascus")
        PharmacistProfile.objects.create(
            user=pharmacist,
            pharmacy=pharmacy,
            full_name="Super Pharmacist",
        )
        self.client.force_authenticate(admin_user)

        patient_response = self.client.post(
            reverse("accounts:approve_user", kwargs={"pk": patient.pk}),
            {},
            format="json",
        )
        pharmacist_response = self.client.post(
            reverse("accounts:approve_user", kwargs={"pk": pharmacist.pk}),
            {},
            format="json",
        )

        self.assertEqual(patient_response.status_code, status.HTTP_200_OK)
        self.assertEqual(pharmacist_response.status_code, status.HTTP_200_OK)

    def test_patient_qr_login_compatibility(self):
        user = User.objects.create_user(
            email="qr.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
            is_active=True,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
        )
        profile = PatientProfile.objects.create(
            user=user,
            full_name="QR Patient",
            qr_code_value="qr-login-token",
            qr_is_active=True,
        )
        profile.set_record_access_pin("1234")
        profile.save(update_fields=["record_access_pin_hash", "updated_at"])

        response = self.client.post(
            reverse("accounts:patient_qr_login"),
            {
                "qr_code_value": "qr-login-token",
                "pin": "1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_pending_patient_qr_login_is_blocked(self):
        user = User.objects.create_user(
            email="qr.pending.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
            is_active=True,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        profile = PatientProfile.objects.create(
            user=user,
            full_name="QR Pending Patient",
            qr_code_value="qr-pending-token",
            qr_is_active=True,
        )
        profile.set_record_access_pin("1234")
        profile.save(update_fields=["record_access_pin_hash", "updated_at"])

        response = self.client.post(
            reverse("accounts:patient_qr_login"),
            {
                "qr_code_value": "qr-pending-token",
                "pin": "1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["approval_status"], ApprovalStatusChoices.PENDING)

    def test_logout_and_change_password_still_work(self):
        user = User.objects.create_user(
            email="change.password@example.com",
            password="StrongPass123!",
            phone_number="5557020",
            role=RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(user=user, full_name="Password Patient")
        refresh = RefreshToken.for_user(user)
        self.client.force_authenticate(user)

        change_response = self.client.post(
            reverse("accounts:change_password"),
            {
                "current_password": "StrongPass123!",
                "new_password": "NewStrongPass123!",
                "confirm_password": "NewStrongPass123!",
            },
            format="json",
        )
        logout_response = self.client.post(
            reverse("accounts:logout"),
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(change_response.status_code, status.HTTP_200_OK)
        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)
