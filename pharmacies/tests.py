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

    def test_public_contracted_pharmacies_succeeds_without_auth_and_filters(self):
        organization = Organization.objects.create(name="Public Contract Org")
        contracted = Pharmacy.objects.create(
            name="Contracted Selector Pharmacy",
            address="Damascus Address",
            phone_number="0111234567",
            latitude="33.515200",
            longitude="36.291200",
            organization=organization,
            is_contracted_with_organization=True,
        )
        Pharmacy.objects.create(
            name="Hidden Non Contracted Pharmacy",
            address="Hidden Address",
        )

        response = self.client.get(reverse("public-contracted-pharmacies"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 1)
        payload = response.data[0]
        self.assertEqual(payload["id"], contracted.id)
        self.assertEqual(payload["name"], contracted.name)
        self.assertEqual(payload["city"], "")
        self.assertEqual(payload["region"], "")
        self.assertEqual(payload["address"], contracted.address)
        self.assertEqual(payload["phone_number"], contracted.phone_number)
        self.assertEqual(payload["latitude"], 33.5152)
        self.assertEqual(payload["longitude"], 36.2912)
        self.assertTrue(payload["is_contracted_with_organization"])
        self.assertNotIn("owner_user", payload)
        self.assertNotIn("organization", payload)
        self.assertNotIn("created_at", payload)
        self.assertNotIn("updated_at", payload)

    def test_patient_pharmacies_requires_patient_auth_and_filters(self):
        organization = Organization.objects.create(name="Patient Pharmacy Org")
        patient_user = User.objects.create_user(
            email="patient.map@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        contracted = Pharmacy.objects.create(
            name="Patient Map Pharmacy",
            address="Map Address",
            latitude="33.515200",
            longitude="36.291200",
            organization=organization,
            is_contracted_with_organization=True,
        )
        Pharmacy.objects.create(
            name="Non Contracted Map Pharmacy",
            address="Hidden Address",
        )

        unauthenticated_response = self.client.get(reverse("patient-pharmacies"))
        self.client.force_authenticate(patient_user)
        response = self.client.get(reverse("patient-pharmacies"))

        self.assertEqual(
            unauthenticated_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], contracted.id)
        self.assertEqual(response.data[0]["latitude"], 33.5152)
        self.assertEqual(response.data[0]["longitude"], 36.2912)
