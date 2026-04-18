import io
import os
import shutil
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.test import override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from common.choices import GenderChoices, RoleChoices, TranscriptionStatusChoices
from organizations.models import Organization, OrganizationStaffProfile
from patients.models import PatientProfile
from pharmacies.models import PharmacistProfile, Pharmacy

from .models import Prescription, PrescriptionAccessLog, PrescriptionItem


class PrescriptionPermissionTests(APITestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name='Org A')
        self.org_b = Organization.objects.create(name='Org B')

        self.patient_one_user = User.objects.create_user(
            email='patient.one@example.com',
            password='StrongPass123!',
            role=RoleChoices.PATIENT,
        )
        self.patient_one = PatientProfile.objects.create(
            user=self.patient_one_user,
            organization=self.org_a,
            full_name='Patient One',
            birth_date=date(1995, 1, 1),
            gender=GenderChoices.MALE,
        )

        self.patient_two_user = User.objects.create_user(
            email='patient.two@example.com',
            password='StrongPass123!',
            role=RoleChoices.PATIENT,
        )
        self.patient_two = PatientProfile.objects.create(
            user=self.patient_two_user,
            organization=self.org_b,
            full_name='Patient Two',
            birth_date=date(1996, 1, 1),
            gender=GenderChoices.FEMALE,
        )

        self.pharmacist_user = User.objects.create_user(
            email='pharmacist.allowed@example.com',
            password='StrongPass123!',
            role=RoleChoices.PHARMACIST,
        )
        self.pharmacy = Pharmacy.objects.create(
            name='Contracted Pharmacy',
            address='Damascus',
            organization=self.org_a,
            is_contracted_with_organization=True,
        )
        self.pharmacist = PharmacistProfile.objects.create(
            user=self.pharmacist_user,
            pharmacy=self.pharmacy,
            full_name='Allowed Pharmacist',
            is_approved=True,
        )

        self.prescription = Prescription.objects.create(
            patient=self.patient_two,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            doctor_name='Doctor Two',
        )

    def test_patient_cannot_access_another_patients_prescription(self):
        self.client.force_authenticate(self.patient_one_user)
        response = self.client.get(
            reverse('prescription-detail', kwargs={'pk': self.prescription.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pharmacist_can_only_create_prescription_for_allowed_patient_scope(self):
        self.client.force_authenticate(self.pharmacist_user)

        allowed_response = self.client.post(
            reverse('prescription-list'),
            {
                'patient': self.patient_one.id,
                'doctor_name': 'Doctor Allowed',
                'doctor_specialty': 'General',
            },
            format='json',
        )
        denied_response = self.client.post(
            reverse('prescription-list'),
            {
                'patient': self.patient_two.id,
                'doctor_name': 'Doctor Denied',
                'doctor_specialty': 'General',
            },
            format='json',
        )

        self.assertEqual(allowed_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(denied_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_without_manage_patients_cannot_retrieve_prescription(self):
        staff_user = User.objects.create_user(
            email='staff.no.patient.access@example.com',
            password='StrongPass123!',
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
            reverse('prescription-detail', kwargs={'pk': self.prescription.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_from_other_organization_cannot_retrieve_prescription_object(self):
        staff_user = User.objects.create_user(
            email='staff.other.org@example.com',
            password='StrongPass123!',
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
            reverse('prescription-detail', kwargs={'pk': self.prescription.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PrescriptionMediaUploadTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='Upload Org')
        self.patient_user = User.objects.create_user(
            email='upload.patient@example.com',
            password='StrongPass123!',
            role=RoleChoices.PATIENT,
        )
        self.patient = PatientProfile.objects.create(
            user=self.patient_user,
            organization=self.organization,
            full_name='Upload Patient',
            birth_date=date(1997, 3, 1),
            gender=GenderChoices.MALE,
        )
        self.pharmacist_user = User.objects.create_user(
            email='upload.pharmacist@example.com',
            password='StrongPass123!',
            role=RoleChoices.PHARMACIST,
        )
        self.pharmacy = Pharmacy.objects.create(
            name='Upload Pharmacy',
            address='Damascus',
            organization=self.organization,
            is_contracted_with_organization=True,
        )
        self.pharmacist = PharmacistProfile.objects.create(
            user=self.pharmacist_user,
            pharmacy=self.pharmacy,
            full_name='Upload Pharmacist',
            is_approved=True,
        )
        self.prescription = Prescription.objects.create(
            patient=self.patient,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            doctor_name='Upload Doctor',
        )
        self.client.force_authenticate(self.pharmacist_user)

    def _build_valid_png_upload(self, filename):
        buffer = io.BytesIO()
        image = Image.new('RGB', (1, 1), color='white')
        image.save(buffer, format='PNG')
        return SimpleUploadedFile(
            filename,
            buffer.getvalue(),
            content_type='image/png',
        )

    def test_add_item_rejects_invalid_audio_extension(self):
        invalid_audio = SimpleUploadedFile(
            'instructions.exe',
            b'not-audio',
            content_type='application/octet-stream',
        )

        response = self.client.post(
            reverse('prescription-add-item', kwargs={'pk': self.prescription.pk}),
            {
                'medicine_name': 'Test Med',
                'price': '10.00',
                'instructions_audio': invalid_audio,
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('instructions_audio', response.data)

    def test_add_item_rejects_invalid_image_binary(self):
        invalid_image = SimpleUploadedFile(
            'fake-image.png',
            b'not-a-real-image',
            content_type='image/png',
        )

        response = self.client.post(
            reverse('prescription-add-item', kwargs={'pk': self.prescription.pk}),
            {
                'medicine_name': 'Test Med',
                'price': '10.00',
                'medicine_image': invalid_image,
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('medicine_image', response.data)

    def test_add_item_stores_media_with_generated_filename(self):
        media_root = os.path.abspath('test_media_storage')
        os.makedirs(media_root, exist_ok=True)
        try:
            with override_settings(
                MEDIA_ROOT=media_root,
                FILE_UPLOAD_PERMISSIONS=None,
                FILE_UPLOAD_DIRECTORY_PERMISSIONS=None,
            ):
                valid_image = self._build_valid_png_upload('unsafe original name.png')

                response = self.client.post(
                    reverse('prescription-add-item', kwargs={'pk': self.prescription.pk}),
                    {
                        'medicine_name': 'Stored Med',
                        'price': '15.00',
                        'medicine_image': valid_image,
                    },
                    format='multipart',
                )

                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                item_id = response.data['id']
                item = Prescription.objects.get(pk=self.prescription.pk).items.get(pk=item_id)
                self.assertTrue(
                    item.medicine_image.name.startswith(
                        f'prescriptions/{self.prescription.pk}/images/'
                    )
                )
                self.assertNotIn('unsafe original name', item.medicine_image.name)
                item.medicine_image.delete(save=False)
        finally:
            shutil.rmtree(media_root, ignore_errors=True)


class PrescriptionTranscriptionPipelineTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='Transcription Org')
        self.patient_user = User.objects.create_user(
            email='transcription.patient@example.com',
            password='StrongPass123!',
            role=RoleChoices.PATIENT,
        )
        self.patient = PatientProfile.objects.create(
            user=self.patient_user,
            organization=self.organization,
            full_name='Transcription Patient',
            birth_date=date(1997, 4, 1),
            gender=GenderChoices.MALE,
        )
        self.pharmacist_user = User.objects.create_user(
            email='transcription.pharmacist@example.com',
            password='StrongPass123!',
            role=RoleChoices.PHARMACIST,
        )
        self.pharmacy = Pharmacy.objects.create(
            name='Transcription Pharmacy',
            address='Damascus',
            organization=self.organization,
            is_contracted_with_organization=True,
        )
        self.pharmacist = PharmacistProfile.objects.create(
            user=self.pharmacist_user,
            pharmacy=self.pharmacy,
            full_name='Transcription Pharmacist',
            is_approved=True,
        )
        self.prescription = Prescription.objects.create(
            patient=self.patient,
            pharmacist=self.pharmacist,
            pharmacy=self.pharmacy,
            doctor_name='Transcription Doctor',
        )
        self.audio_file = SimpleUploadedFile(
            'instructions.mp3',
            b'fake-audio-content',
            content_type='audio/mpeg',
        )
        self.item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine_name='Transcription Med',
            price='20.00',
            instructions_audio=self.audio_file,
        )
        self.client.force_authenticate(self.pharmacist_user)

    @override_settings(PHARMASIGN_TRANSCRIPTION_PROVIDER='placeholder')
    def test_owner_pharmacist_can_transcribe_item(self):
        response = self.client.post(
            reverse('prescription-item-transcribe', kwargs={'pk': self.item.pk}),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.item.refresh_from_db()
        self.assertEqual(
            self.item.transcription_status,
            TranscriptionStatusChoices.COMPLETED,
        )
        self.assertEqual(self.item.transcription_provider, 'placeholder')
        self.assertTrue(self.item.instructions_transcript_raw)
        self.assertEqual(
            self.item.instructions_transcript_edited,
            self.item.instructions_transcript_raw,
        )
        self.assertTrue(
            PrescriptionAccessLog.objects.filter(
                prescription=self.prescription,
                accessed_by=self.pharmacist_user,
                access_type='transcribe',
            ).exists()
        )

    def test_transcribe_rejects_item_without_audio(self):
        item_without_audio = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine_name='No Audio Med',
            price='11.00',
        )

        response = self.client.post(
            reverse('prescription-item-transcribe', kwargs={'pk': item_without_audio.pk}),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['detail'],
            'Cannot transcribe an item without instructions audio.',
        )

    @override_settings(PHARMASIGN_TRANSCRIPTION_PROVIDER='failing')
    def test_transcription_failure_marks_item_failed(self):
        response = self.client.post(
            reverse('prescription-item-transcribe', kwargs={'pk': self.item.pk}),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.item.refresh_from_db()
        self.assertEqual(
            self.item.transcription_status,
            TranscriptionStatusChoices.FAILED,
        )
        self.assertEqual(self.item.transcription_provider, 'failing')
        self.assertTrue(self.item.transcription_error_message)

    def test_other_pharmacist_cannot_transcribe_foreign_item(self):
        other_user = User.objects.create_user(
            email='transcription.other@example.com',
            password='StrongPass123!',
            role=RoleChoices.PHARMACIST,
        )
        other_pharmacy = Pharmacy.objects.create(name='Other Pharmacy', address='Aleppo')
        PharmacistProfile.objects.create(
            user=other_user,
            pharmacy=other_pharmacy,
            full_name='Other Pharmacist',
            is_approved=True,
        )

        self.client.force_authenticate(other_user)
        response = self.client.post(
            reverse('prescription-item-transcribe', kwargs={'pk': self.item.pk}),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
