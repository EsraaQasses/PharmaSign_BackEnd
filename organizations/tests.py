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

    def test_admin_without_organization_profile_can_get_and_auto_initialize(self):
        admin_user = User.objects.create_user(
            email="org.settings.unlinked@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
            phone_number="099100100",
        )
        self.client.force_authenticate(admin_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = OrganizationStaffProfile.objects.get(user=admin_user)
        organization = profile.organization
        self.assertEqual(response.data["id"], organization.id)
        self.assertEqual(
            response.data["name"],
            "Organization for org.settings.unlinked@example.com",
        )
        self.assertEqual(response.data["phone_number"], "099100100")
        self.assertEqual(response.data["city"], "")
        self.assertEqual(response.data["region"], "")
        self.assertEqual(response.data["address"], "")
        self.assertEqual(response.data["description"], "")
        self.assertEqual(profile.job_title, "Organization Admin")
        self.assertTrue(profile.can_manage_patients)
        self.assertTrue(profile.can_manage_pharmacists)

    def test_admin_without_organization_profile_can_patch_and_auto_initialize(self):
        admin_user = User.objects.create_user(
            email="org.settings.patch.unlinked@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.patch(
            self.url,
            {
                "name": "New Org",
                "phone_number": "011111111",
                "city": "Damascus",
                "region": "Mazza",
                "address": "Address",
                "description": "Description",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = OrganizationStaffProfile.objects.get(user=admin_user)
        organization = profile.organization
        organization.refresh_from_db()
        self.assertEqual(organization.name, "New Org")
        self.assertEqual(organization.phone, "011111111")
        self.assertEqual(organization.city, "Damascus")
        self.assertEqual(organization.region, "Mazza")
        self.assertEqual(organization.address, "Address")
        self.assertEqual(organization.description, "Description")
        self.assertEqual(response.data["id"], organization.id)
        self.assertEqual(response.data["phone_number"], "011111111")

    def test_existing_organization_staff_profile_still_uses_existing_organization(self):
        self.client.force_authenticate(self.admin_user)
        before_count = Organization.objects.count()

        get_response = self.client.get(self.url)
        patch_response = self.client.patch(
            self.url,
            {"name": "Existing Org Updated"},
            format="json",
        )

        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["id"], self.organization.id)
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Existing Org Updated")
        self.assertEqual(Organization.objects.count(), before_count)

    def test_superuser_without_organization_profile_can_get_and_auto_initialize(self):
        superuser = User.objects.create_superuser(
            email="org.settings.superuser@example.com",
            password="StrongPass123!",
            phone_number="099200200",
        )
        self.client.force_authenticate(superuser)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = OrganizationStaffProfile.objects.get(user=superuser)
        self.assertEqual(response.data["id"], profile.organization_id)
        self.assertEqual(response.data["phone_number"], "099200200")

    def test_superuser_without_organization_profile_can_patch_and_auto_initialize(self):
        superuser = User.objects.create_superuser(
            email="org.settings.superuser.patch@example.com",
            password="StrongPass123!",
        )
        self.client.force_authenticate(superuser)

        response = self.client.patch(
            self.url,
            {"name": "Super Org", "phone_number": "011222333"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = OrganizationStaffProfile.objects.get(user=superuser)
        profile.organization.refresh_from_db()
        self.assertEqual(profile.organization.name, "Super Org")
        self.assertEqual(profile.organization.phone, "011222333")

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

        pharmacist_user = User.objects.create_user(
            email="org.settings.pharmacist@example.com",
            password="StrongPass123!",
            role=RoleChoices.PHARMACIST,
        )
        self.client.force_authenticate(pharmacist_user)

        forbidden = self.client.get(self.url)

        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

    def test_auto_initialize_does_not_attach_to_random_existing_organization(self):
        unrelated = Organization.objects.create(name="Unrelated Existing Org")
        admin_user = User.objects.create_user(
            email="org.settings.random@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        self.client.force_authenticate(admin_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = OrganizationStaffProfile.objects.get(user=admin_user)
        self.assertNotEqual(profile.organization_id, unrelated.id)
        self.assertEqual(response.data["id"], profile.organization_id)

    def test_pharmacy_auto_assignment_uses_auto_initialized_admin_organization(self):
        admin_user = User.objects.create_user(
            email="org.settings.pharmacy.admin@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        self.client.force_authenticate(admin_user)
        init_response = self.client.get(self.url)
        profile = OrganizationStaffProfile.objects.get(user=admin_user)

        response = self.client.post(
            reverse("admin-pharmacy-list"),
            {
                "name": "Auto Init Pharmacy",
                "phone_number": "011333444",
                "address": "Auto Init Address",
                "is_contracted_with_organization": True,
            },
            format="json",
        )

        self.assertEqual(init_response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["organization"]["id"], profile.organization_id)
