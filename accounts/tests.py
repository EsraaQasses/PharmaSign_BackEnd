from datetime import date
from unittest.mock import Mock, patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from common.choices import (
    ApprovalStatusChoices,
    GenderChoices,
    HearingConditionTypeChoices,
    HearingDisabilityLevelChoices,
    RoleChoices,
)
from organizations.models import Organization, OrganizationStaffProfile
from patients.models import PatientEnrollment, PatientProfile
from pharmacies.models import PharmacistProfile, Pharmacy
from prescriptions.models import Prescription, PrescriptionItem, SignQualityReport

from .models import PhoneOTP, User
from .otp_delivery import send_otp_code


class OTPDeliveryTests(APITestCase):
    @override_settings(
        OTP_DELIVERY_CHANNEL="telegram",
        OTP_TELEGRAM_ENABLED=True,
        TELEGRAM_BOT_TOKEN="test-token",
        TELEGRAM_DEFAULT_CHAT_ID="895444257",
        TELEGRAM_REQUEST_TIMEOUT_SECONDS=10,
    )
    @patch("accounts.otp_delivery.requests.post")
    def test_telegram_send_success(self, mock_post):
        response = Mock(status_code=200)
        response.json.return_value = {"ok": True}
        mock_post.return_value = response

        result = send_otp_code("5557000", PhoneOTP.PURPOSE_PATIENT_REGISTER, "123456")

        self.assertEqual(result, {"channel": "telegram", "sent": True, "error": None})
        mock_post.assert_called_once()
        _url, kwargs = mock_post.call_args
        self.assertEqual(kwargs["timeout"], 10)
        self.assertEqual(kwargs["json"]["chat_id"], "895444257")
        self.assertIn("PharmaSign OTP code: 123456", kwargs["json"]["text"])

    @override_settings(
        OTP_DELIVERY_CHANNEL="telegram",
        OTP_TELEGRAM_ENABLED=True,
        TELEGRAM_BOT_TOKEN="test-token",
        TELEGRAM_DEFAULT_CHAT_ID="895444257",
        TELEGRAM_REQUEST_TIMEOUT_SECONDS=10,
    )
    @patch("accounts.otp_delivery.requests.post")
    def test_telegram_send_failure(self, mock_post):
        response = Mock(status_code=200)
        response.json.return_value = {"ok": False, "description": "secret detail"}
        mock_post.return_value = response

        result = send_otp_code("5557000", PhoneOTP.PURPOSE_PATIENT_REGISTER, "123456")

        self.assertEqual(result["channel"], "telegram")
        self.assertFalse(result["sent"])
        self.assertEqual(result["error"], "Telegram OTP delivery failed.")
        self.assertNotIn("secret detail", result["error"])


@override_settings(OTP_DELIVERY_CHANNEL="debug")
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
        self.assertEqual(response.data["detail"], "OTP sent successfully.")
        self.assertEqual(response.data["expires_in_seconds"], 300)
        self.assertEqual(response.data["delivery"], {"channel": "debug", "sent": True})
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
        self.assertEqual(response.data["detail"], "Phone number is already registered.")
        self.assertEqual(response.data["code"], "duplicate_phone")

    @override_settings(DEBUG=False, OTP_DELIVERY_PROVIDER_CONFIGURED=False)
    def test_debug_false_registration_otp_without_provider_returns_clear_error(self):
        response = self.client.post(
            reverse("accounts:patient_register_request_otp"),
            {"phone_number": "5557003"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"], "OTP delivery provider is not configured"
        )
        self.assertEqual(response.data["code"], "otp_provider_not_configured")
        self.assertNotIn("debug_otp", response.data)

    @override_settings(
        DEBUG=False,
        OTP_DELIVERY_CHANNEL="telegram",
        OTP_TELEGRAM_ENABLED=True,
        TELEGRAM_BOT_TOKEN="test-token",
        TELEGRAM_DEFAULT_CHAT_ID="895444257",
        TELEGRAM_REQUEST_TIMEOUT_SECONDS=10,
    )
    @patch("accounts.otp_delivery.requests.post")
    def test_otp_request_endpoint_calls_telegram_delivery(self, mock_post):
        telegram_response = Mock(status_code=200)
        telegram_response.json.return_value = {"ok": True}
        mock_post.return_value = telegram_response

        response = self.client.post(
            reverse("accounts:patient_register_request_otp"),
            {"phone_number": "5557030"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "OTP sent successfully.")
        self.assertEqual(
            response.data["delivery"],
            {"channel": "telegram", "sent": True},
        )
        self.assertNotIn("debug_otp", response.data)
        mock_post.assert_called_once()
        self.assertEqual(
            PhoneOTP.objects.get(phone_number="5557030").purpose,
            PhoneOTP.PURPOSE_PATIENT_REGISTER,
        )

    @override_settings(
        DEBUG=False,
        OTP_DELIVERY_CHANNEL="telegram",
        OTP_TELEGRAM_ENABLED=True,
        TELEGRAM_BOT_TOKEN="test-token",
        TELEGRAM_DEFAULT_CHAT_ID="895444257",
        TELEGRAM_REQUEST_TIMEOUT_SECONDS=10,
    )
    @patch("accounts.otp_delivery.requests.post")
    def test_production_otp_response_does_not_include_raw_otp(self, mock_post):
        telegram_response = Mock(status_code=200)
        telegram_response.json.return_value = {"ok": True}
        mock_post.return_value = telegram_response

        response = self.client.post(
            reverse("accounts:patient_register_request_otp"),
            {"phone_number": "5557031"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("debug_otp", response.data)
        self.assertNotIn("otp", response.data)
        sent_text = mock_post.call_args.kwargs["json"]["text"]
        challenge = PhoneOTP.objects.get(phone_number="5557031")
        self.assertNotIn(
            sent_text.splitlines()[0].rsplit(" ", 1)[-1],
            challenge.code_hash,
        )

    @override_settings(
        DEBUG=False,
        OTP_DELIVERY_CHANNEL="telegram",
        OTP_TELEGRAM_ENABLED=True,
        TELEGRAM_BOT_TOKEN="super-secret-token",
        TELEGRAM_DEFAULT_CHAT_ID="895444257",
        TELEGRAM_REQUEST_TIMEOUT_SECONDS=10,
    )
    @patch("accounts.otp_delivery.requests.post")
    def test_bot_token_is_never_exposed_in_api_response(self, mock_post):
        telegram_response = Mock(status_code=500)
        telegram_response.json.return_value = {"ok": False}
        mock_post.return_value = telegram_response

        response = self.client.post(
            reverse("accounts:patient_register_request_otp"),
            {"phone_number": "5557032"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["code"], "otp_delivery_failed")
        self.assertNotIn("super-secret-token", str(response.data))

    @override_settings(
        DEBUG=False,
        OTP_DELIVERY_CHANNEL="telegram",
        OTP_TELEGRAM_ENABLED=True,
        TELEGRAM_BOT_TOKEN="test-token",
        TELEGRAM_DEFAULT_CHAT_ID="895444257",
        TELEGRAM_REQUEST_TIMEOUT_SECONDS=10,
    )
    @patch("accounts.otp_delivery.requests.post")
    def test_telegram_delivery_failure_returns_safe_response(self, mock_post):
        telegram_response = Mock(status_code=200)
        telegram_response.json.return_value = {
            "ok": False,
            "description": "raw api detail",
        }
        mock_post.return_value = telegram_response

        response = self.client.post(
            reverse("accounts:patient_register_request_otp"),
            {"phone_number": "5557033"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["detail"], "OTP delivery failed.")
        self.assertEqual(response.data["code"], "otp_delivery_failed")
        self.assertEqual(
            response.data["delivery"],
            {
                "channel": "telegram",
                "sent": False,
                "error": "Telegram OTP delivery failed.",
            },
        )
        self.assertNotIn("raw api detail", str(response.data))

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
        self.assertEqual(
            response.data["approval_status"], ApprovalStatusChoices.PENDING
        )
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
        self.assertEqual(response.data["detail"], "Invalid OTP.")
        self.assertEqual(response.data["code"], "invalid_otp")
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
        self.assertEqual(response.data["detail"], "Too many OTP attempts.")
        self.assertEqual(response.data["code"], "otp_max_attempts_exceeded")
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
        self.assertEqual(response.data["detail"], "OTP has expired.")
        self.assertEqual(response.data["code"], "expired_otp")

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
        self.assertEqual(second_response.data["detail"], "Invalid OTP.")
        self.assertEqual(second_response.data["code"], "invalid_otp")

    def test_admin_can_create_patient_account_from_enrollment_without_registration_otp(
        self,
    ):
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
        self.assertIn("refresh", response.data)
        self.assertEqual(
            set(response.data["user"].keys()),
            {
                "id",
                "email",
                "phone_number",
                "role",
                "is_active",
                "is_verified",
                "approval_status",
            },
        )
        self.assertIn("profile", response.data)

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
        self.assertEqual(response.data["detail"], "Email or phone number is required.")
        self.assertEqual(response.data["code"], "missing_required_field")

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
        self.assertEqual(response.data["detail"], "Invalid credentials.")
        self.assertEqual(response.data["code"], "invalid_credentials")

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
        self.assertEqual(
            response.data["approval_status"], ApprovalStatusChoices.PENDING
        )
        self.assertEqual(response.data["code"], "approval_pending")
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
        pharmacy = Pharmacy.objects.create(
            name="Approved Login Pharmacy", address="Damascus"
        )
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
        self.assertEqual(
            response.data["approval_status"], ApprovalStatusChoices.PENDING
        )
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
        self.assertEqual(
            response.data["approval_status"], ApprovalStatusChoices.REJECTED
        )
        self.assertEqual(response.data["code"], "approval_rejected")
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
    def test_pharmacist_register_with_pharmacy_id_links_existing_pharmacy(self):
        organization = Organization.objects.create(name="Registration Pharmacy Org")
        pharmacy = Pharmacy.objects.create(
            name="Existing Contracted Pharmacy",
            address="Damascus",
            organization=organization,
            is_contracted_with_organization=True,
        )
        otp = self.request_role_registration_otp("pharmacist", "5557040")
        pharmacy_count = Pharmacy.objects.count()

        response = self.client.post(
            reverse("accounts:pharmacist_register"),
            {
                "password": "StrongPass123!",
                "full_name": "Register Pharmacist By Pharmacy",
                "phone_number": "5557040",
                "license_number": "LIC-7040",
                "pharmacy_id": pharmacy.id,
                "otp": otp,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Pharmacy.objects.count(), pharmacy_count)
        user = User.objects.get(phone_number="5557040")
        self.assertEqual(user.pharmacist_profile.pharmacy_id, pharmacy.id)
        pharmacy.refresh_from_db()
        self.assertIsNone(pharmacy.owner_user)

    @override_settings(DEBUG=True)
    def test_pharmacist_register_invalid_pharmacy_id_fails(self):
        otp = self.request_role_registration_otp("pharmacist", "5557041")

        response = self.client.post(
            reverse("accounts:pharmacist_register"),
            {
                "password": "StrongPass123!",
                "full_name": "Invalid Pharmacy Pharmacist",
                "phone_number": "5557041",
                "license_number": "LIC-7041",
                "pharmacy_id": 999999,
                "otp": otp,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "pharmacy_not_found")
        self.assertEqual(response.data["detail"], "Selected pharmacy was not found.")

    @override_settings(DEBUG=True)
    def test_pharmacist_register_non_contracted_pharmacy_id_fails(self):
        pharmacy = Pharmacy.objects.create(
            name="Non Contracted Registration Pharmacy",
            address="Damascus",
            is_contracted_with_organization=False,
        )
        otp = self.request_role_registration_otp("pharmacist", "5557042")

        response = self.client.post(
            reverse("accounts:pharmacist_register"),
            {
                "password": "StrongPass123!",
                "full_name": "Non Contracted Pharmacist",
                "phone_number": "5557042",
                "license_number": "LIC-7042",
                "pharmacy_id": pharmacy.id,
                "otp": otp,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "pharmacy_not_contracted")
        self.assertEqual(
            response.data["detail"], "Selected pharmacy is not contracted."
        )

    @override_settings(DEBUG=True)
    def test_pharmacist_register_without_pharmacy_id_or_legacy_fields_fails(self):
        otp = self.request_role_registration_otp("pharmacist", "5557043")

        response = self.client.post(
            reverse("accounts:pharmacist_register"),
            {
                "password": "StrongPass123!",
                "full_name": "Missing Pharmacy Pharmacist",
                "phone_number": "5557043",
                "license_number": "LIC-7043",
                "otp": otp,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "missing_required_field")
        self.assertEqual(response.data["detail"], "pharmacy_id is required.")
        self.assertEqual(
            response.data["fields"]["pharmacy_id"],
            "This field is required.",
        )

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
        self.assertEqual(
            response.data["approval_status"], ApprovalStatusChoices.PENDING
        )

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
        self.assertEqual(
            response.data["approval_status"], ApprovalStatusChoices.REJECTED
        )
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
        pharmacy = Pharmacy.objects.create(
            name="Reject Profile Pharmacy", address="Damascus"
        )
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
        self.assertEqual(
            response.data["approval_status"], ApprovalStatusChoices.PENDING
        )

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
        self.assertEqual(
            response.data["approval_status"], ApprovalStatusChoices.REJECTED
        )
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
        self.assertEqual(
            response.data["approval_status"], ApprovalStatusChoices.PENDING
        )

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
        self.assertEqual(
            response.data["approval_status"], ApprovalStatusChoices.REJECTED
        )

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
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)
        self.assertIn("profile", response.data)
        self.assertIn("must_set_password", response.data)
        self.assertFalse(response.data["must_set_password"])

    def test_patient_qr_login_with_unusable_password_requires_password_setup(self):
        user = User.objects.create_user(
            email="qr.no.password.patient@example.com",
            password=None,
            role=RoleChoices.PATIENT,
            is_active=True,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
        )
        profile = PatientProfile.objects.create(
            user=user,
            full_name="QR No Password Patient",
            qr_code_value="qr-no-password-token",
            qr_is_active=True,
        )
        profile.set_record_access_pin("1234")
        profile.save(update_fields=["record_access_pin_hash", "updated_at"])

        response = self.client.post(
            reverse("accounts:patient_qr_login"),
            {
                "qr_code_value": "qr-no-password-token",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertTrue(response.data["must_set_password"])

    def test_patient_qr_login_ignores_legacy_pin_when_qr_code_value_is_valid(self):
        user = User.objects.create_user(
            email="qr.wrong.pin.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
            is_active=True,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
        )
        profile = PatientProfile.objects.create(
            user=user,
            full_name="QR Wrong PIN Patient",
            qr_code_value="qr-wrong-pin-token",
            qr_is_active=True,
        )
        profile.set_record_access_pin("1234")
        profile.save(update_fields=["record_access_pin_hash", "updated_at"])

        response = self.client.post(
            reverse("accounts:patient_qr_login"),
            {
                "qr_code_value": "qr-wrong-pin-token",
                "pin": "wrong-pin",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertFalse(response.data["must_set_password"])

    def test_disabled_static_qr_cannot_login(self):
        user = User.objects.create_user(
            email="qr.disabled.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
            is_active=True,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
        )
        PatientProfile.objects.create(
            user=user,
            full_name="QR Disabled Patient",
            qr_code_value="qr-disabled-token",
            qr_is_active=False,
        )

        response = self.client.post(
            reverse("accounts:patient_qr_login"),
            {"qr_code_value": "qr-disabled-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"][0], "Invalid QR code.")
        self.assertEqual(response.data["code"][0], "invalid_qr_code")

    def test_invalid_static_qr_cannot_login(self):
        response = self.client.post(
            reverse("accounts:patient_qr_login"),
            {"qr_code_value": "not-a-valid-static-qr"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"][0], "Invalid QR code.")
        self.assertEqual(response.data["code"][0], "invalid_qr_code")

    def test_inactive_patient_user_cannot_login_with_static_qr(self):
        user = User.objects.create_user(
            email="qr.inactive.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
            is_active=False,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
        )
        PatientProfile.objects.create(
            user=user,
            full_name="QR Inactive Patient",
            qr_code_value="qr-inactive-token",
            qr_is_active=True,
        )

        response = self.client.post(
            reverse("accounts:patient_qr_login"),
            {"qr_code_value": "qr-inactive-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"][0], "Invalid QR code.")
        self.assertEqual(response.data["code"][0], "invalid_qr_code")

    def test_patient_with_unusable_password_can_set_initial_password(self):
        user = User.objects.create_user(
            email="initial.password.patient@example.com",
            password=None,
            phone_number="5557060",
            role=RoleChoices.PATIENT,
            is_active=True,
            approval_status=ApprovalStatusChoices.APPROVED,
        )
        PatientProfile.objects.create(user=user, full_name="Initial Password Patient")
        self.client.force_authenticate(user)

        response = self.client.post(
            reverse("accounts:patient_set_initial_password"),
            {
                "new_password": "InitialStrongPass123!",
                "confirm_password": "InitialStrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"detail": "Password set successfully."})
        user.refresh_from_db()
        self.assertTrue(user.check_password("InitialStrongPass123!"))

        self.client.force_authenticate(None)
        login_response = self.client.post(
            reverse("accounts:login"),
            {
                "phone_number": "5557060",
                "password": "InitialStrongPass123!",
            },
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", login_response.data)

    def test_set_initial_password_validation_and_permissions(self):
        user = User.objects.create_user(
            email="initial.validation.patient@example.com",
            password=None,
            role=RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(user=user, full_name="Initial Validation Patient")
        self.client.force_authenticate(user)

        mismatch = self.client.post(
            reverse("accounts:patient_set_initial_password"),
            {"new_password": "StrongPass123!", "confirm_password": "OtherPass123!"},
            format="json",
        )
        weak = self.client.post(
            reverse("accounts:patient_set_initial_password"),
            {"new_password": "123", "confirm_password": "123"},
            format="json",
        )
        self.assertEqual(mismatch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(mismatch.data["code"], "passwords_do_not_match")
        self.assertEqual(weak.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(weak.data["code"], "password_too_weak")

        user.set_password("AlreadyStrongPass123!")
        user.save(update_fields=["password", "updated_at"])
        already_set = self.client.post(
            reverse("accounts:patient_set_initial_password"),
            {"new_password": "StrongPass123!", "confirm_password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(already_set.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(already_set.data["code"], "password_already_set")

        admin_user = User.objects.create_user(
            email="initial.password.admin@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        pharmacist_user = User.objects.create_user(
            email="initial.password.pharmacist@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        pharmacy = Pharmacy.objects.create(
            name="Initial Password Pharmacy",
            address="Damascus",
        )
        PharmacistProfile.objects.create(
            user=pharmacist_user,
            pharmacy=pharmacy,
            full_name="Initial Password Pharmacist",
        )
        for forbidden_user in (admin_user, pharmacist_user):
            self.client.force_authenticate(forbidden_user)
            response = self.client.post(
                reverse("accounts:patient_set_initial_password"),
                {
                    "new_password": "StrongPass123!",
                    "confirm_password": "StrongPass123!",
                },
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(response.data["code"], "patient_access_required")

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
        self.assertEqual(
            response.data["approval_status"], ApprovalStatusChoices.PENDING
        )

    def test_rejected_patient_qr_login_is_blocked(self):
        user = User.objects.create_user(
            email="qr.rejected.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
            is_active=True,
            approval_status=ApprovalStatusChoices.REJECTED,
            rejection_reason="Rejected for test",
        )
        PatientProfile.objects.create(
            user=user,
            full_name="QR Rejected Patient",
            qr_code_value="qr-rejected-token",
            qr_is_active=True,
        )

        response = self.client.post(
            reverse("accounts:patient_qr_login"),
            {"qr_code_value": "qr-rejected-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["approval_status"], ApprovalStatusChoices.REJECTED
        )

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
        self.assertEqual(
            change_response.data["detail"], "Password changed successfully"
        )
        self.assertEqual(logout_response.data["detail"], "Logged out successfully")

    @override_settings(DEBUG=True)
    def test_patient_password_reset_otp_request_and_confirm(self):
        user = User.objects.create_user(
            email="reset.patient@example.com",
            password="OldStrongPass123!",
            phone_number="5557061",
            role=RoleChoices.PATIENT,
            is_active=True,
            approval_status=ApprovalStatusChoices.APPROVED,
        )
        PatientProfile.objects.create(user=user, full_name="Reset Patient")

        request_response = self.client.post(
            reverse("accounts:password_reset_request_otp"),
            {"phone_number": "5557061", "role": "patient"},
            format="json",
        )

        self.assertEqual(request_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            request_response.data["detail"],
            "If the account exists, a password reset code has been sent.",
        )
        self.assertIn("debug_otp", request_response.data)
        challenge = PhoneOTP.objects.get(phone_number="5557061")
        self.assertEqual(challenge.purpose, PhoneOTP.PURPOSE_PATIENT_PASSWORD_RESET)
        self.assertEqual(challenge.user_id, user.id)

        confirm_response = self.client.post(
            reverse("accounts:password_reset_confirm"),
            {
                "phone_number": "5557061",
                "role": "patient",
                "otp": request_response.data["debug_otp"],
                "new_password": "NewResetStrongPass123!",
                "confirm_password": "NewResetStrongPass123!",
            },
            format="json",
        )

        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            confirm_response.data,
            {"detail": "Password reset successfully."},
        )
        user.refresh_from_db()
        self.assertFalse(user.check_password("OldStrongPass123!"))
        self.assertTrue(user.check_password("NewResetStrongPass123!"))
        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.used_at)

        login_response = self.client.post(
            reverse("accounts:login"),
            {
                "phone_number": "5557061",
                "password": "NewResetStrongPass123!",
            },
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

    @override_settings(DEBUG=True)
    def test_pharmacist_password_reset_otp_request_and_confirm(self):
        user = User.objects.create_user(
            email="reset.pharmacist@example.com",
            password="OldStrongPass123!",
            phone_number="5557062",
            role=RoleChoices.PHARMACIST,
            is_active=True,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
        )
        pharmacy = Pharmacy.objects.create(name="Reset Pharmacy", address="Damascus")
        PharmacistProfile.objects.create(
            user=user,
            pharmacy=pharmacy,
            full_name="Reset Pharmacist",
            is_approved=True,
        )

        request_response = self.client.post(
            reverse("accounts:password_reset_request_otp"),
            {"phone_number": "5557062", "role": "pharmacist"},
            format="json",
        )
        confirm_response = self.client.post(
            reverse("accounts:password_reset_confirm"),
            {
                "phone_number": "5557062",
                "role": "pharmacist",
                "otp": request_response.data["debug_otp"],
                "new_password": "NewResetStrongPass123!",
                "confirm_password": "NewResetStrongPass123!",
            },
            format="json",
        )

        self.assertEqual(request_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            PhoneOTP.objects.get(phone_number="5557062").purpose,
            PhoneOTP.PURPOSE_PHARMACIST_PASSWORD_RESET,
        )
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewResetStrongPass123!"))

    @override_settings(DEBUG=True)
    def test_password_reset_request_does_not_reveal_missing_or_admin_accounts(self):
        admin_user = User.objects.create_user(
            email="reset.admin@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            phone_number="5557063",
            is_staff=True,
        )

        missing_response = self.client.post(
            reverse("accounts:password_reset_request_otp"),
            {"phone_number": "5557999", "role": "patient"},
            format="json",
        )
        admin_as_patient_response = self.client.post(
            reverse("accounts:password_reset_request_otp"),
            {"phone_number": "5557063", "role": "patient"},
            format="json",
        )

        self.assertEqual(missing_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_as_patient_response.status_code, status.HTTP_200_OK)
        self.assertNotIn("debug_otp", missing_response.data)
        self.assertNotIn("debug_otp", admin_as_patient_response.data)
        self.assertFalse(PhoneOTP.objects.filter(phone_number="5557999").exists())
        self.assertFalse(PhoneOTP.objects.filter(user=admin_user).exists())

    @override_settings(DEBUG=True)
    def test_password_reset_confirm_validation_errors(self):
        user = User.objects.create_user(
            email="reset.errors.patient@example.com",
            password="OldStrongPass123!",
            phone_number="5557064",
            role=RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(user=user, full_name="Reset Errors Patient")
        request_response = self.client.post(
            reverse("accounts:password_reset_request_otp"),
            {"phone_number": "5557064", "role": "patient"},
            format="json",
        )

        wrong_otp = self.client.post(
            reverse("accounts:password_reset_confirm"),
            {
                "phone_number": "5557064",
                "role": "patient",
                "otp": "000000",
                "new_password": "NewResetStrongPass123!",
                "confirm_password": "NewResetStrongPass123!",
            },
            format="json",
        )
        mismatch = self.client.post(
            reverse("accounts:password_reset_confirm"),
            {
                "phone_number": "5557064",
                "role": "patient",
                "otp": request_response.data["debug_otp"],
                "new_password": "NewResetStrongPass123!",
                "confirm_password": "DifferentResetStrongPass123!",
            },
            format="json",
        )
        weak = self.client.post(
            reverse("accounts:password_reset_confirm"),
            {
                "phone_number": "5557064",
                "role": "patient",
                "otp": request_response.data["debug_otp"],
                "new_password": "123",
                "confirm_password": "123",
            },
            format="json",
        )

        self.assertEqual(wrong_otp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(wrong_otp.data["code"], "invalid_otp")
        self.assertEqual(mismatch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(mismatch.data["code"], "passwords_do_not_match")
        self.assertEqual(weak.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(weak.data["code"], "password_too_weak")

    @override_settings(DEBUG=True)
    def test_password_reset_expired_locked_and_reused_otp(self):
        expired_user = User.objects.create_user(
            email="reset.expired.patient@example.com",
            password="OldStrongPass123!",
            phone_number="5557065",
            role=RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(
            user=expired_user,
            full_name="Reset Expired Patient",
        )
        expired_request = self.client.post(
            reverse("accounts:password_reset_request_otp"),
            {"phone_number": "5557065", "role": "patient"},
            format="json",
        )
        expired_challenge = PhoneOTP.objects.get(phone_number="5557065")
        expired_challenge.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        expired_challenge.save(update_fields=["expires_at", "updated_at"])
        expired_response = self.client.post(
            reverse("accounts:password_reset_confirm"),
            {
                "phone_number": "5557065",
                "role": "patient",
                "otp": expired_request.data["debug_otp"],
                "new_password": "NewResetStrongPass123!",
                "confirm_password": "NewResetStrongPass123!",
            },
            format="json",
        )

        locked_user = User.objects.create_user(
            email="reset.locked.patient@example.com",
            password="OldStrongPass123!",
            phone_number="5557066",
            role=RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(
            user=locked_user, full_name="Reset Locked Patient"
        )
        self.client.post(
            reverse("accounts:password_reset_request_otp"),
            {"phone_number": "5557066", "role": "patient"},
            format="json",
        )
        locked_response = None
        for _ in range(5):
            locked_response = self.client.post(
                reverse("accounts:password_reset_confirm"),
                {
                    "phone_number": "5557066",
                    "role": "patient",
                    "otp": "000000",
                    "new_password": "NewResetStrongPass123!",
                    "confirm_password": "NewResetStrongPass123!",
                },
                format="json",
            )

        reused_user = User.objects.create_user(
            email="reset.reused.patient@example.com",
            password="OldStrongPass123!",
            phone_number="5557067",
            role=RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(
            user=reused_user, full_name="Reset Reused Patient"
        )
        reused_request = self.client.post(
            reverse("accounts:password_reset_request_otp"),
            {"phone_number": "5557067", "role": "patient"},
            format="json",
        )
        reset_payload = {
            "phone_number": "5557067",
            "role": "patient",
            "otp": reused_request.data["debug_otp"],
            "new_password": "NewResetStrongPass123!",
            "confirm_password": "NewResetStrongPass123!",
        }
        first_use = self.client.post(
            reverse("accounts:password_reset_confirm"),
            reset_payload,
            format="json",
        )
        second_use = self.client.post(
            reverse("accounts:password_reset_confirm"),
            reset_payload,
            format="json",
        )

        self.assertEqual(expired_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(expired_response.data["code"], "otp_expired")
        self.assertEqual(locked_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(locked_response.data["code"], "otp_locked")
        self.assertEqual(first_use.status_code, status.HTTP_200_OK)
        self.assertEqual(second_use.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(second_use.data["code"], "invalid_otp")

    @override_settings(DEBUG=True)
    def test_password_reset_role_isolation(self):
        pharmacist_user = User.objects.create_user(
            email="reset.role.pharmacist@example.com",
            password="OldStrongPass123!",
            phone_number="5557068",
            role=RoleChoices.PHARMACIST,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
        )
        pharmacy = Pharmacy.objects.create(
            name="Reset Role Pharmacy",
            address="Damascus",
        )
        PharmacistProfile.objects.create(
            user=pharmacist_user,
            pharmacy=pharmacy,
            full_name="Reset Role Pharmacist",
            is_approved=True,
        )

        request_response = self.client.post(
            reverse("accounts:password_reset_request_otp"),
            {"phone_number": "5557068", "role": "patient"},
            format="json",
        )
        confirm_response = self.client.post(
            reverse("accounts:password_reset_confirm"),
            {
                "phone_number": "5557068",
                "role": "patient",
                "otp": "123456",
                "new_password": "NewResetStrongPass123!",
                "confirm_password": "NewResetStrongPass123!",
            },
            format="json",
        )

        self.assertEqual(request_response.status_code, status.HTTP_200_OK)
        self.assertNotIn("debug_otp", request_response.data)
        self.assertEqual(confirm_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(confirm_response.data["code"], "invalid_otp")
        pharmacist_user.refresh_from_db()
        self.assertTrue(pharmacist_user.check_password("OldStrongPass123!"))


class AdminPhaseAApiTests(APITestCase):
    def create_user(self, email, role, password="StrongPass123!", **extra_fields):
        return User.objects.create_user(
            email=email,
            password=password,
            role=role,
            **extra_fields,
        )

    def test_admin_user_can_login_through_admin_auth_login(self):
        organization = Organization.objects.create(name="Admin Login Org")
        admin_user = self.create_user(
            "admin.phasea@example.com",
            RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=admin_user,
            organization=organization,
            job_title="Coordinator",
            can_manage_patients=True,
            can_manage_pharmacists=True,
        )

        response = self.client.post(
            reverse("accounts:admin_login"),
            {"email": "admin.phasea@example.com", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["role"], RoleChoices.ADMIN)
        self.assertTrue(response.data["user"]["is_staff"])
        self.assertFalse(response.data["user"]["is_superuser"])
        self.assertEqual(
            response.data["profile"]["organization"]["id"], organization.id
        )
        self.assertTrue(response.data["profile"]["can_manage_patients"])
        self.assertTrue(response.data["profile"]["can_manage_pharmacists"])
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_patient_user_cannot_login_through_admin_auth_login(self):
        patient_user = self.create_user(
            "admin.login.patient@example.com",
            RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(user=patient_user, full_name="Patient Login")

        response = self.client.post(
            reverse("accounts:admin_login"),
            {
                "email": "admin.login.patient@example.com",
                "password": "StrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "admin_access_required")

    def test_pharmacist_user_cannot_login_through_admin_auth_login(self):
        pharmacist_user = self.create_user(
            "admin.login.pharmacist@example.com",
            RoleChoices.PHARMACIST,
        )
        pharmacy = Pharmacy.objects.create(name="Rejected Admin Login", address="City")
        PharmacistProfile.objects.create(
            user=pharmacist_user,
            pharmacy=pharmacy,
            full_name="Pharmacist Login",
            is_approved=True,
        )

        response = self.client.post(
            reverse("accounts:admin_login"),
            {
                "email": "admin.login.pharmacist@example.com",
                "password": "StrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "admin_access_required")

    def test_admin_user_can_call_admin_auth_me(self):
        organization = Organization.objects.create(name="Admin Me Org")
        admin_user = self.create_user(
            "admin.me@example.com",
            RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=admin_user,
            organization=organization,
            job_title="Manager",
            can_manage_patients=True,
            can_manage_pharmacists=False,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.get(reverse("accounts:admin_me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["id"], admin_user.id)
        self.assertEqual(
            response.data["profile"]["organization"]["name"], organization.name
        )
        self.assertTrue(response.data["profile"]["can_manage_patients"])
        self.assertFalse(response.data["profile"]["can_manage_pharmacists"])

    def test_non_admin_user_cannot_call_admin_auth_me(self):
        patient_user = self.create_user(
            "admin.me.patient@example.com",
            RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(user=patient_user, full_name="Me Patient")
        self.client.force_authenticate(patient_user)

        response = self.client.get(reverse("accounts:admin_me"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "admin_access_required")

    def test_admin_can_change_password_through_admin_endpoint(self):
        admin_user = self.create_user(
            "admin.change.password@example.com",
            RoleChoices.ADMIN,
            password="OldStrongPass123!",
            is_staff=True,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.post(
            reverse("accounts:admin_change_password"),
            {
                "current_password": "OldStrongPass123!",
                "new_password": "NewStrongPass123!",
                "confirm_password": "NewStrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"detail": "Password changed successfully."})
        admin_user.refresh_from_db()
        self.assertFalse(admin_user.check_password("OldStrongPass123!"))
        self.assertTrue(admin_user.check_password("NewStrongPass123!"))
        self.assertNotIn("user", response.data)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        self.assertNotIn("password", response.data)

    def test_superuser_can_change_password_through_admin_endpoint(self):
        superuser = User.objects.create_superuser(
            email="admin.change.superuser@example.com",
            password="OldStrongPass123!",
        )
        self.client.force_authenticate(superuser)

        response = self.client.post(
            reverse("accounts:admin_change_password"),
            {
                "current_password": "OldStrongPass123!",
                "new_password": "NewStrongPass123!",
                "confirm_password": "NewStrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        superuser.refresh_from_db()
        self.assertTrue(superuser.check_password("NewStrongPass123!"))

    def test_patient_and_pharmacist_cannot_use_admin_change_password(self):
        patient_user = self.create_user(
            "admin.change.patient@example.com",
            RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(user=patient_user, full_name="Change Patient")
        pharmacist_user = self.create_user(
            "admin.change.pharmacist@example.com",
            RoleChoices.PHARMACIST,
        )
        pharmacy = Pharmacy.objects.create(name="Change Pharmacy", address="Damascus")
        PharmacistProfile.objects.create(
            user=pharmacist_user,
            pharmacy=pharmacy,
            full_name="Change Pharmacist",
            is_approved=True,
        )

        for user in (patient_user, pharmacist_user):
            self.client.force_authenticate(user)
            response = self.client.post(
                reverse("accounts:admin_change_password"),
                {
                    "current_password": "StrongPass123!",
                    "new_password": "NewStrongPass123!",
                    "confirm_password": "NewStrongPass123!",
                },
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(response.data["code"], "admin_access_required")

    def test_admin_change_password_rejects_incorrect_current_password(self):
        admin_user = self.create_user(
            "admin.change.incorrect@example.com",
            RoleChoices.ADMIN,
            password="OldStrongPass123!",
            is_staff=True,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.post(
            reverse("accounts:admin_change_password"),
            {
                "current_password": "WrongStrongPass123!",
                "new_password": "NewStrongPass123!",
                "confirm_password": "NewStrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "current_password_incorrect")

    def test_admin_change_password_rejects_password_mismatch(self):
        admin_user = self.create_user(
            "admin.change.mismatch@example.com",
            RoleChoices.ADMIN,
            password="OldStrongPass123!",
            is_staff=True,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.post(
            reverse("accounts:admin_change_password"),
            {
                "current_password": "OldStrongPass123!",
                "new_password": "NewStrongPass123!",
                "confirm_password": "DifferentStrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "passwords_do_not_match")

    def test_admin_change_password_rejects_weak_password(self):
        admin_user = self.create_user(
            "admin.change.weak@example.com",
            RoleChoices.ADMIN,
            password="OldStrongPass123!",
            is_staff=True,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.post(
            reverse("accounts:admin_change_password"),
            {
                "current_password": "OldStrongPass123!",
                "new_password": "123",
                "confirm_password": "123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "password_too_weak")
        self.assertIn("new_password", response.data["fields"])

    def test_admin_change_password_rejects_same_password(self):
        admin_user = self.create_user(
            "admin.change.same@example.com",
            RoleChoices.ADMIN,
            password="OldStrongPass123!",
            is_staff=True,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.post(
            reverse("accounts:admin_change_password"),
            {
                "current_password": "OldStrongPass123!",
                "new_password": "OldStrongPass123!",
                "confirm_password": "OldStrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "password_same_as_old")

    def test_admin_user_can_call_dashboard_stats_with_expected_keys(self):
        admin_user = self.create_user(
            "dashboard.admin@example.com",
            RoleChoices.ADMIN,
            is_staff=True,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.get(reverse("accounts:admin_dashboard_stats"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data.keys()),
            {
                "patients_count",
                "pharmacists_count",
                "pharmacies_count",
                "prescriptions_count",
                "active_qr_count",
                "pending_approvals_count",
                "sign_quality_follow_up_count",
                "gender_distribution",
                "hearing_severity_distribution",
                "hearing_condition_type_distribution",
                "age_groups",
                "patients_by_city",
                "recent_patients",
                "recent_approval_requests",
            },
        )
        self.assertEqual(response.data["patients_by_city"], [])

    def test_dashboard_stats_patients_by_city_groups_location_and_counts(self):
        admin_user = self.create_user(
            "dashboard.city.admin@example.com",
            RoleChoices.ADMIN,
            is_staff=True,
        )
        city = "دمشق"
        region_mazza = "المزة"
        region_baramkeh = "البرامكة"

        for index in range(5):
            user = self.create_user(
                f"dashboard.city.mazza.{index}@example.com",
                RoleChoices.PATIENT,
            )
            PatientProfile.objects.create(
                user=user,
                full_name=f"Sensitive Mazza Patient {index}",
                city=city,
                region=region_mazza,
                gender=GenderChoices.MALE if index < 2 else GenderChoices.FEMALE,
                qr_is_active=index < 4,
            )
        for index in range(2):
            user = self.create_user(
                f"dashboard.city.baramkeh.{index}@example.com",
                RoleChoices.PATIENT,
            )
            PatientProfile.objects.create(
                user=user,
                full_name=f"Sensitive Baramkeh Patient {index}",
                city=city,
                region=region_baramkeh,
                gender=GenderChoices.FEMALE,
                qr_is_active=index == 0,
            )
        unspecified_user = self.create_user(
            "dashboard.city.unspecified@example.com",
            RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(
            user=unspecified_user,
            full_name="Sensitive Unspecified Patient",
            city="",
            region="",
            gender=GenderChoices.MALE,
            qr_is_active=False,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.get(reverse("accounts:admin_dashboard_stats"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        groups = {
            (row["city"], row["region"]): row
            for row in response.data["patients_by_city"]
        }
        self.assertEqual(groups[(city, region_mazza)]["patients_count"], 5)
        self.assertEqual(groups[(city, region_mazza)]["male_count"], 2)
        self.assertEqual(groups[(city, region_mazza)]["female_count"], 3)
        self.assertEqual(groups[(city, region_mazza)]["active_qr_count"], 4)
        self.assertEqual(groups[(city, region_baramkeh)]["patients_count"], 2)
        self.assertEqual(groups[(city, region_baramkeh)]["male_count"], 0)
        self.assertEqual(groups[(city, region_baramkeh)]["female_count"], 2)
        self.assertEqual(groups[(city, region_baramkeh)]["active_qr_count"], 1)
        self.assertEqual(groups[("غير محدد", "غير محدد")]["patients_count"], 1)
        self.assertEqual(groups[("غير محدد", "غير محدد")]["male_count"], 1)
        self.assertEqual(groups[("غير محدد", "غير محدد")]["female_count"], 0)
        self.assertEqual(groups[("غير محدد", "غير محدد")]["active_qr_count"], 0)
        self.assertEqual(
            [(row["city"], row["region"]) for row in response.data["patients_by_city"]],
            [
                (city, region_mazza),
                (city, region_baramkeh),
                ("غير محدد", "غير محدد"),
            ],
        )
        self.assertIn("hearing_severity_distribution", response.data)
        self.assertIn("hearing_condition_type_distribution", response.data)
        self.assertIn("patients_count", response.data)
        for row in response.data["patients_by_city"]:
            self.assertEqual(
                set(row.keys()),
                {
                    "city",
                    "region",
                    "patients_count",
                    "male_count",
                    "female_count",
                    "active_qr_count",
                },
            )
            self.assertNotIn("full_name", row)
            self.assertNotIn("phone_number", row)
            self.assertNotIn("medical_info", row)
            self.assertNotIn("prescription", row)

    def test_non_admin_user_cannot_call_dashboard_stats(self):
        patient_user = self.create_user(
            "dashboard.patient@example.com",
            RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(user=patient_user, full_name="Stats Patient")
        self.client.force_authenticate(patient_user)

        response = self.client.get(reverse("accounts:admin_dashboard_stats"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "admin_access_required")

    def test_dashboard_stats_are_scoped_to_staff_organization(self):
        scoped_org = Organization.objects.create(name="Scoped Org")
        other_org = Organization.objects.create(name="Other Org")
        admin_user = self.create_user(
            "dashboard.scoped.admin@example.com",
            RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=admin_user,
            organization=scoped_org,
            can_manage_patients=True,
            can_manage_pharmacists=True,
        )

        scoped_patient_user = self.create_user(
            "scoped.patient@example.com",
            RoleChoices.PATIENT,
            phone_number="900001",
        )
        scoped_patient = PatientProfile.objects.create(
            user=scoped_patient_user,
            organization=scoped_org,
            full_name="Scoped Patient",
            phone_number="900001",
            birth_date=date(1990, 1, 1),
            gender=GenderChoices.FEMALE,
            hearing_disability_level=HearingDisabilityLevelChoices.SEVERE,
            hearing_condition_type=HearingConditionTypeChoices.HARD_OF_HEARING,
            qr_is_active=True,
        )
        other_patient_user = self.create_user(
            "other.patient@example.com",
            RoleChoices.PATIENT,
        )
        PatientProfile.objects.create(
            user=other_patient_user,
            organization=other_org,
            full_name="Other Patient",
            gender=GenderChoices.MALE,
            hearing_condition_type=HearingConditionTypeChoices.DEAF_FROM_BIRTH,
            qr_is_active=True,
        )

        scoped_pharmacy = Pharmacy.objects.create(
            name="Scoped Pharmacy",
            address="Scoped Address",
            organization=scoped_org,
        )
        other_pharmacy = Pharmacy.objects.create(
            name="Other Pharmacy",
            address="Other Address",
            organization=other_org,
        )
        scoped_pharmacist_user = self.create_user(
            "scoped.pharmacist@example.com",
            RoleChoices.PHARMACIST,
        )
        scoped_pharmacist = PharmacistProfile.objects.create(
            user=scoped_pharmacist_user,
            pharmacy=scoped_pharmacy,
            full_name="Scoped Pharmacist",
            is_approved=True,
        )
        other_pharmacist_user = self.create_user(
            "other.pharmacist@example.com",
            RoleChoices.PHARMACIST,
        )
        PharmacistProfile.objects.create(
            user=other_pharmacist_user,
            pharmacy=other_pharmacy,
            full_name="Other Pharmacist",
            is_approved=True,
        )

        prescription = Prescription.objects.create(
            patient=scoped_patient,
            pharmacist=scoped_pharmacist,
            pharmacy=scoped_pharmacy,
            doctor_name="Scoped Doctor",
        )
        item = PrescriptionItem.objects.create(
            prescription=prescription,
            medicine_name="Scoped Medicine",
        )
        SignQualityReport.objects.create(
            patient=scoped_patient,
            prescription=prescription,
            prescription_item=item,
            medicine_name=item.medicine_name,
            status=SignQualityReport.STATUS_OPEN,
        )

        other_prescription = Prescription.objects.create(
            patient=PatientProfile.objects.get(user=other_patient_user),
            pharmacist=PharmacistProfile.objects.get(user=other_pharmacist_user),
            pharmacy=other_pharmacy,
            doctor_name="Other Doctor",
        )
        other_item = PrescriptionItem.objects.create(
            prescription=other_prescription,
            medicine_name="Other Medicine",
        )
        SignQualityReport.objects.create(
            patient=other_prescription.patient,
            prescription=other_prescription,
            prescription_item=other_item,
            medicine_name=other_item.medicine_name,
            status=SignQualityReport.STATUS_OPEN,
        )

        pending_scoped_user = self.create_user(
            "pending.scoped@example.com",
            RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        PatientProfile.objects.create(
            user=pending_scoped_user,
            organization=scoped_org,
            full_name="Pending Scoped",
        )
        pending_other_user = self.create_user(
            "pending.other@example.com",
            RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        PatientProfile.objects.create(
            user=pending_other_user,
            organization=other_org,
            full_name="Pending Other",
        )

        self.client.force_authenticate(admin_user)
        response = self.client.get(reverse("accounts:admin_dashboard_stats"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["patients_count"], 2)
        self.assertEqual(response.data["pharmacies_count"], 1)
        self.assertEqual(response.data["pharmacists_count"], 1)
        self.assertEqual(response.data["prescriptions_count"], 1)
        self.assertEqual(response.data["active_qr_count"], 1)
        self.assertEqual(response.data["pending_approvals_count"], 1)
        self.assertEqual(response.data["sign_quality_follow_up_count"], 1)
        self.assertEqual(
            response.data["patients_by_city"],
            [
                {
                    "city": "غير محدد",
                    "region": "غير محدد",
                    "patients_count": 2,
                    "male_count": 0,
                    "female_count": 1,
                    "active_qr_count": 1,
                }
            ],
        )
        condition_counts = {
            row["value"]: row
            for row in response.data["hearing_condition_type_distribution"]
        }
        self.assertEqual(
            condition_counts[HearingConditionTypeChoices.HARD_OF_HEARING]["count"],
            1,
        )
        self.assertEqual(
            condition_counts[HearingConditionTypeChoices.DEAF_FROM_BIRTH]["count"],
            0,
        )
        self.assertEqual(
            condition_counts[HearingConditionTypeChoices.DEAF_DUE_TO_ACCIDENT]["count"],
            0,
        )
        self.assertEqual(condition_counts[""]["count"], 1)
        self.assertTrue(
            condition_counts[HearingConditionTypeChoices.HARD_OF_HEARING]["label"]
        )
        self.assertIn("hearing_severity_distribution", response.data)
        self.assertEqual(len(response.data["recent_approval_requests"]), 1)
        self.assertEqual(
            response.data["recent_approval_requests"][0]["id"],
            pending_scoped_user.id,
        )


class AdminApprovalPhaseDApiTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="phase.d.admin@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        self.patient_user = User.objects.create_user(
            email="phase.d.patient@example.com",
            password="StrongPass123!",
            phone_number="9100001",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        self.patient_profile = PatientProfile.objects.create(
            user=self.patient_user,
            full_name="Phase D Patient",
            phone_number="9100001",
            birth_date=date(2001, 1, 2),
            gender=GenderChoices.FEMALE,
            address="Patient Address",
            hearing_disability_level=HearingDisabilityLevelChoices.MODERATE,
        )
        self.rejected_patient_user = User.objects.create_user(
            email="phase.d.rejected@example.com",
            password="StrongPass123!",
            phone_number="9100002",
            role=RoleChoices.PATIENT,
            approval_status=ApprovalStatusChoices.REJECTED,
            rejection_reason="Old reason",
        )
        PatientProfile.objects.create(
            user=self.rejected_patient_user,
            full_name="Rejected Phase D Patient",
            phone_number="9100002",
        )
        self.pharmacy = Pharmacy.objects.create(
            name="Phase D Pharmacy",
            address="Pharmacy Address",
        )
        self.pharmacist_user = User.objects.create_user(
            email="phase.d.pharmacist@example.com",
            password="StrongPass123!",
            phone_number="9100003",
            role=RoleChoices.PHARMACIST,
            approval_status=ApprovalStatusChoices.PENDING,
        )
        self.pharmacist_profile = PharmacistProfile.objects.create(
            user=self.pharmacist_user,
            pharmacy=self.pharmacy,
            full_name="Phase D Pharmacist",
            license_number="PHASE-D-LIC",
            is_approved=False,
        )

    def test_admin_can_list_approval_requests(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(reverse("accounts:admin_approval_request_list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 3)
        row = response.data["results"][0]
        self.assertIn("user_id", row)
        self.assertIn(row["type"], [RoleChoices.PATIENT, RoleChoices.PHARMACIST])
        self.assertIsNone(row["city"])
        self.assertIsNone(row["region"])

    def test_non_admin_cannot_list_approval_requests(self):
        self.client.force_authenticate(self.patient_user)

        response = self.client.get(reverse("accounts:admin_approval_request_list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_supports_type_filter(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse("accounts:admin_approval_request_list"),
            {"type": RoleChoices.PHARMACIST},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["results"])
        self.assertTrue(
            all(
                row["type"] == RoleChoices.PHARMACIST
                for row in response.data["results"]
            )
        )

    def test_list_supports_status_filter(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse("accounts:admin_approval_request_list"),
            {"status": ApprovalStatusChoices.REJECTED},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["results"])
        self.assertTrue(
            all(
                row["status"] == ApprovalStatusChoices.REJECTED
                for row in response.data["results"]
            )
        )

    def test_list_supports_search(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse("accounts:admin_approval_request_list"),
            {"search": "PHASE-D-LIC"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.pharmacist_user.id)
        self.assertEqual(
            response.data["results"][0]["pharmacist_license_number"],
            "PHASE-D-LIC",
        )

    def test_admin_can_retrieve_patient_approval_detail(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse(
                "accounts:admin_approval_request_detail",
                kwargs={"pk": self.patient_user.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.patient_user.id)
        self.assertEqual(response.data["type"], RoleChoices.PATIENT)
        self.assertEqual(
            response.data["details"]["patient_profile_id"],
            self.patient_profile.id,
        )
        self.assertIsNone(response.data["city"])
        self.assertIsNone(response.data["region"])

    def test_admin_can_retrieve_pharmacist_approval_detail(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse(
                "accounts:admin_approval_request_detail",
                kwargs={"pk": self.pharmacist_user.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], RoleChoices.PHARMACIST)
        self.assertEqual(response.data["selected_pharmacy_id"], self.pharmacy.id)
        self.assertEqual(response.data["pharmacist_license_number"], "PHASE-D-LIC")
        self.assertEqual(
            response.data["details"]["pharmacy"]["name"], self.pharmacy.name
        )
        self.assertEqual(response.data["details"]["pharmacy"]["city"], "")
        self.assertEqual(response.data["details"]["pharmacy"]["region"], "")

    def test_admin_can_approve_patient_request(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            reverse(
                "accounts:admin_approval_request_approve",
                kwargs={"pk": self.patient_user.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.patient_user.refresh_from_db()
        self.assertEqual(
            self.patient_user.approval_status,
            ApprovalStatusChoices.APPROVED,
        )
        self.assertTrue(self.patient_user.is_verified)
        self.assertEqual(
            response.data["request"]["status"], ApprovalStatusChoices.APPROVED
        )

    def test_admin_can_reject_patient_request_with_reason(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            reverse(
                "accounts:admin_approval_request_reject",
                kwargs={"pk": self.patient_user.id},
            ),
            {"reason": "Missing documents"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.patient_user.refresh_from_db()
        self.assertEqual(
            self.patient_user.approval_status,
            ApprovalStatusChoices.REJECTED,
        )
        self.assertEqual(self.patient_user.rejection_reason, "Missing documents")
        self.assertEqual(
            response.data["request"]["rejection_reason"], "Missing documents"
        )

    def test_admin_can_approve_pharmacist_request_and_profile(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            reverse(
                "accounts:admin_approval_request_approve",
                kwargs={"pk": self.pharmacist_user.id},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pharmacist_user.refresh_from_db()
        self.pharmacist_profile.refresh_from_db()
        self.assertEqual(
            self.pharmacist_user.approval_status,
            ApprovalStatusChoices.APPROVED,
        )
        self.assertTrue(self.pharmacist_profile.is_approved)
        self.assertTrue(response.data["request"]["details"]["is_approved"])

    def test_admin_can_reject_pharmacist_request_and_profile(self):
        self.pharmacist_profile.is_approved = True
        self.pharmacist_profile.save(update_fields=["is_approved", "updated_at"])
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            reverse(
                "accounts:admin_approval_request_reject",
                kwargs={"pk": self.pharmacist_user.id},
            ),
            {"reason": "Invalid license"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pharmacist_user.refresh_from_db()
        self.pharmacist_profile.refresh_from_db()
        self.assertEqual(
            self.pharmacist_user.approval_status,
            ApprovalStatusChoices.REJECTED,
        )
        self.assertFalse(self.pharmacist_profile.is_approved)
        self.assertFalse(response.data["request"]["details"]["is_approved"])

    def test_old_existing_approval_endpoint_still_works(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            reverse("accounts:approve_user", kwargs={"pk": self.patient_user.id}),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.patient_user.refresh_from_db()
        self.assertEqual(
            self.patient_user.approval_status,
            ApprovalStatusChoices.APPROVED,
        )
