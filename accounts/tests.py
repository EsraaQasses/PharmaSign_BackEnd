from datetime import date

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from common.choices import GenderChoices, HearingDisabilityLevelChoices, RoleChoices
from organizations.models import Organization
from patients.models import PatientEnrollment, PatientProfile

from .models import User


class AuthAndPatientFlowTests(APITestCase):
    def test_patient_self_register_creates_profile_and_qr(self):
        response = self.client.post(
            reverse('accounts:patient_self_register'),
            {
                'email': 'patient@example.com',
                'password': 'StrongPass123!',
                'full_name': 'Patient One',
                'phone_number': '5551000',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email='patient@example.com')
        self.assertEqual(user.role, RoleChoices.PATIENT)
        profile = user.patient_profile
        self.assertTrue(profile.qr_is_active)
        self.assertTrue(profile.qr_code_value)

    def test_admin_can_create_patient_account_from_enrollment(self):
        admin_user = User.objects.create_user(
            email='admin@example.com',
            password='StrongPass123!',
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        organization = Organization.objects.create(name='Org One')
        enrollment = PatientEnrollment.objects.create(
            organization=organization,
            first_name='Ali',
            last_name='Test',
            birth_date=date(2000, 1, 1),
            gender=GenderChoices.MALE,
            hearing_disability_level=HearingDisabilityLevelChoices.MODERATE,
            created_by=admin_user,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.post(
            reverse('patient-enrollment-create-account', kwargs={'pk': enrollment.pk}),
            {
                'email': 'linked@example.com',
                'password': 'StrongPass123!',
                'record_access_pin': '1234',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        enrollment.refresh_from_db()
        self.assertTrue(enrollment.is_account_created)
        self.assertIsNotNone(enrollment.patient_profile)
        self.assertTrue(enrollment.patient_profile.qr_is_active)

    def test_patient_can_login_with_qr_and_pin(self):
        user = User.objects.create_user(
            email='qr.patient@example.com',
            password='StrongPass123!',
            role=RoleChoices.PATIENT,
            is_active=True,
        )
        profile = PatientProfile.objects.create(
            user=user,
            full_name='QR Patient',
            qr_code_value='qr-login-token',
            qr_is_active=True,
        )
        profile.set_record_access_pin('1234')
        profile.save(update_fields=['record_access_pin_hash', 'updated_at'])

        response = self.client.post(
            reverse('accounts:patient_qr_login'),
            {
                'qr_code_value': 'qr-login-token',
                'pin': '1234',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['email'], user.email)

    def test_patient_qr_login_rejects_invalid_pin(self):
        user = User.objects.create_user(
            email='qr.invalid@example.com',
            password='StrongPass123!',
            role=RoleChoices.PATIENT,
            is_active=True,
        )
        profile = PatientProfile.objects.create(
            user=user,
            full_name='QR Invalid',
            qr_code_value='qr-invalid-token',
            qr_is_active=True,
        )
        profile.set_record_access_pin('1234')
        profile.save(update_fields=['record_access_pin_hash', 'updated_at'])

        response = self.client.post(
            reverse('accounts:patient_qr_login'),
            {
                'qr_code_value': 'qr-invalid-token',
                'pin': '9999',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'][0], 'Invalid QR code or PIN.')
