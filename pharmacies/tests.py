from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from common.choices import RoleChoices
from organizations.models import Organization, OrganizationStaffProfile

from .models import PharmacistProfile, Pharmacy


class PharmacyPermissionTests(APITestCase):
    def test_pharmacist_only_sees_own_pharmacy_in_list(self):
        pharmacist_user = User.objects.create_user(
            email="pharmacy.scope@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        own_pharmacy = Pharmacy.objects.create(name="Own Pharmacy", address="Damascus")
        Pharmacy.objects.create(name="Other Pharmacy", address="Aleppo")
        PharmacistProfile.objects.create(
            user=pharmacist_user,
            pharmacy=own_pharmacy,
            full_name="Own Pharmacist",
            is_approved=True,
        )

        self.client.force_authenticate(pharmacist_user)
        response = self.client.get(reverse("pharmacy-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], own_pharmacy.id)

    def test_staff_without_manage_pharmacists_cannot_list_pharmacies(self):
        organization = Organization.objects.create(name="Org Pharmacies")
        staff_user = User.objects.create_user(
            email="staff.pharmacies@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=staff_user,
            organization=organization,
            can_manage_patients=True,
            can_manage_pharmacists=False,
        )

        self.client.force_authenticate(staff_user)
        response = self.client.get(reverse("pharmacy-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_singular_pharmacist_me_rejects_patient(self):
        patient_user = User.objects.create_user(
            email="pharmacist.me.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )

        self.client.force_authenticate(patient_user)
        response = self.client.get(reverse("pharmacist-me-singular"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_pharmacist_pharmacy_endpoint_returns_and_updates_own_pharmacy(self):
        pharmacist_user = User.objects.create_user(
            email="pharmacy.me@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        pharmacy = Pharmacy.objects.create(
            name="Before Pharmacy",
            address="Before Address",
            phone_number="111",
        )
        PharmacistProfile.objects.create(
            user=pharmacist_user,
            pharmacy=pharmacy,
            full_name="Pharmacy Owner",
            is_approved=True,
        )

        self.client.force_authenticate(pharmacist_user)
        get_response = self.client.get(reverse("pharmacist-me-pharmacy"))
        patch_response = self.client.patch(
            reverse("pharmacist-me-pharmacy"),
            {
                "name": "After Pharmacy",
                "address": "After Address",
                "phone": "222",
                "lat": "33.513800",
                "lng": "36.276500",
                "has_sign_service": False,
            },
            format="json",
        )

        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        pharmacy.refresh_from_db()
        self.assertEqual(pharmacy.name, "After Pharmacy")
        self.assertEqual(pharmacy.phone_number, "222")
        self.assertEqual(patch_response.data["has_sign_service"], True)
