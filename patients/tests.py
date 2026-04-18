from datetime import date

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from common.choices import GenderChoices, HearingDisabilityLevelChoices, RoleChoices
from organizations.models import Organization, OrganizationStaffProfile
from patients.models import PatientMedicalInfo, PatientProfile, PatientSession
from pharmacies.models import PharmacistProfile, Pharmacy


class PatientSessionFlowTests(APITestCase):
    def test_start_by_qr_creates_patient_session_record(self):
        organization = Organization.objects.create(name='Org Session')
        patient_user = User.objects.create_user(
            email='patient.session@example.com',
            password='StrongPass123!',
            role=RoleChoices.PATIENT,
        )
        patient_profile = PatientProfile.objects.create(
            user=patient_user,
            organization=organization,
            full_name='Patient Session',
            birth_date=date(1998, 5, 10),
            gender=GenderChoices.FEMALE,
            hearing_disability_level=HearingDisabilityLevelChoices.MODERATE,
            qr_code_value='session-qr-token',
            qr_is_active=True,
        )
        PatientMedicalInfo.objects.create(
            patient=patient_profile,
            allergies='Penicillin',
            chronic_conditions='Asthma',
        )

        pharmacist_user = User.objects.create_user(
            email='pharmacist.session@example.com',
            password='StrongPass123!',
            role=RoleChoices.PHARMACIST,
        )
        pharmacy = Pharmacy.objects.create(
            name='Session Pharmacy',
            address='Damascus',
            organization=organization,
            is_contracted_with_organization=True,
        )
        PharmacistProfile.objects.create(
            user=pharmacist_user,
            pharmacy=pharmacy,
            full_name='Pharmacist Session',
            is_approved=True,
        )

        self.client.force_authenticate(pharmacist_user)
        response = self.client.post(
            reverse('patient-session-start-by-qr'),
            {'qr_code_value': 'session-qr-token'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('session', response.data)
        self.assertIn('patient_summary', response.data)
        self.assertEqual(PatientSession.objects.count(), 1)
        session = PatientSession.objects.get()
        self.assertEqual(session.patient, patient_profile)
        self.assertEqual(session.pharmacist.user, pharmacist_user)
        self.assertEqual(session.pharmacy, pharmacy)

    def test_unapproved_pharmacist_cannot_start_patient_session(self):
        organization = Organization.objects.create(name='Org Unapproved')
        patient_user = User.objects.create_user(
            email='patient.unapproved@example.com',
            password='StrongPass123!',
            role=RoleChoices.PATIENT,
        )
        patient_profile = PatientProfile.objects.create(
            user=patient_user,
            organization=organization,
            full_name='Patient Unapproved',
            qr_code_value='unapproved-qr-token',
            qr_is_active=True,
        )
        PatientMedicalInfo.objects.create(patient=patient_profile)

        pharmacist_user = User.objects.create_user(
            email='pharmacist.unapproved@example.com',
            password='StrongPass123!',
            role=RoleChoices.PHARMACIST,
        )
        pharmacy = Pharmacy.objects.create(name='Unapproved Pharmacy', address='Damascus')
        PharmacistProfile.objects.create(
            user=pharmacist_user,
            pharmacy=pharmacy,
            full_name='Unapproved Pharmacist',
            is_approved=False,
        )

        self.client.force_authenticate(pharmacist_user)
        response = self.client.post(
            reverse('patient-session-start-by-qr'),
            {'qr_code_value': 'unapproved-qr-token'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(PatientSession.objects.count(), 0)

    def test_pharmacist_cannot_start_session_for_patient_outside_contracted_scope(self):
        patient_org = Organization.objects.create(name='Patient Org')
        pharmacy_org = Organization.objects.create(name='Pharmacy Org')

        patient_user = User.objects.create_user(
            email='patient.scope@example.com',
            password='StrongPass123!',
            role=RoleChoices.PATIENT,
        )
        patient_profile = PatientProfile.objects.create(
            user=patient_user,
            organization=patient_org,
            full_name='Patient Scope',
            qr_code_value='scope-qr-token',
            qr_is_active=True,
        )
        PatientMedicalInfo.objects.create(patient=patient_profile)

        pharmacist_user = User.objects.create_user(
            email='pharmacist.scope@example.com',
            password='StrongPass123!',
            role=RoleChoices.PHARMACIST,
        )
        pharmacy = Pharmacy.objects.create(
            name='Scoped Pharmacy',
            address='Damascus',
            organization=pharmacy_org,
            is_contracted_with_organization=True,
        )
        PharmacistProfile.objects.create(
            user=pharmacist_user,
            pharmacy=pharmacy,
            full_name='Scoped Pharmacist',
            is_approved=True,
        )

        self.client.force_authenticate(pharmacist_user)
        response = self.client.post(
            reverse('patient-session-start-by-qr'),
            {'qr_code_value': 'scope-qr-token'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(PatientSession.objects.count(), 0)


class OrganizationStaffPermissionTests(APITestCase):
    def test_staff_without_manage_patients_cannot_list_enrollments(self):
        organization = Organization.objects.create(name='Org Staff Patients')
        staff_user = User.objects.create_user(
            email='staff.patients@example.com',
            password='StrongPass123!',
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
        response = self.client.get(reverse('patient-enrollment-list'))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_cannot_generate_qr_for_patient_outside_organization(self):
        staff_org = Organization.objects.create(name='Staff Org')
        patient_org = Organization.objects.create(name='Patient Org Other')

        staff_user = User.objects.create_user(
            email='staff.scope@example.com',
            password='StrongPass123!',
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=staff_user,
            organization=staff_org,
            can_manage_patients=True,
        )

        patient_user = User.objects.create_user(
            email='patient.otherorg@example.com',
            password='StrongPass123!',
            role=RoleChoices.PATIENT,
        )
        patient_profile = PatientProfile.objects.create(
            user=patient_user,
            organization=patient_org,
            full_name='Other Org Patient',
        )

        self.client.force_authenticate(staff_user)
        response = self.client.post(
            reverse('patient-generate-qr', kwargs={'pk': patient_profile.pk}),
            {'regenerate': True},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
