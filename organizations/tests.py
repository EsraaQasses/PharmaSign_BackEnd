from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from common.choices import RoleChoices

from .models import Organization, OrganizationStaffProfile


class AdminOrganizationMeTests(APITestCase):
    def setUp(self):
        self.url = reverse("admin-organization-me")
        self.organization = Organization.objects.create(
            name="Settings Org",
            phone="011100000",
            city="Damascus",
            region="Mazza",
            address="Old address",
            description="Old description",
        )
        self.other_organization = Organization.objects.create(name="Other Org")
        self.admin_user = User.objects.create_user(
            email="org.settings.admin@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=self.admin_user,
            organization=self.organization,
            can_manage_patients=True,
            can_manage_pharmacists=True,
        )

    def test_organization_staff_admin_can_get_own_organization(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.organization.id)
        self.assertEqual(response.data["name"], self.organization.name)
        self.assertEqual(response.data["phone_number"], self.organization.phone)
        self.assertEqual(response.data["city"], self.organization.city)
        self.assertEqual(response.data["region"], self.organization.region)

    def test_organization_staff_admin_can_patch_own_organization(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.patch(
            self.url,
            {
                "name": "Updated Org",
                "phone_number": "011999999",
                "city": "Aleppo",
                "region": "Aziziyeh",
                "address": "Updated address",
                "description": "Updated description",
                "id": self.other_organization.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.organization.refresh_from_db()
        self.other_organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Updated Org")
        self.assertEqual(self.organization.phone, "011999999")
        self.assertEqual(self.organization.city, "Aleppo")
        self.assertEqual(self.organization.region, "Aziziyeh")
        self.assertEqual(self.organization.address, "Updated address")
        self.assertEqual(self.organization.description, "Updated description")
        self.assertEqual(self.other_organization.name, "Other Org")
        self.assertEqual(response.data["id"], self.organization.id)

    def test_superuser_without_organization_profile_gets_required_error(self):
        superuser = User.objects.create_superuser(
            email="org.settings.superuser@example.com",
            password="StrongPass123!",
        )
        self.client.force_authenticate(superuser)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "admin_organization_required")

    def test_admin_without_organization_profile_gets_required_error(self):
        admin_user = User.objects.create_user(
            email="org.settings.unlinked@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.patch(self.url, {"name": "No Org"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "admin_organization_required")

    def test_endpoint_requires_authenticated_admin(self):
        unauthenticated = self.client.get(self.url)
        self.assertEqual(unauthenticated.status_code, status.HTTP_401_UNAUTHORIZED)

        patient_user = User.objects.create_user(
            email="org.settings.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        self.client.force_authenticate(patient_user)

        forbidden = self.client.get(self.url)

        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)
