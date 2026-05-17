from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from common.choices import ApprovalStatusChoices, RoleChoices
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


class AdminPharmacyPhaseCApiTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Phase C Org")
        self.admin_user = User.objects.create_user(
            email="phasec.admin@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        self.patient_user = User.objects.create_user(
            email="phasec.patient@example.com",
            password="StrongPass123!",
            role=RoleChoices.PATIENT,
        )
        self.pharmacy = Pharmacy.objects.create(
            name="Phase C Pharmacy",
            address="Phase C Address",
            phone_number="0111000",
            latitude="33.513800",
            longitude="36.276500",
            organization=self.organization,
            is_contracted_with_organization=True,
        )
        self.pharmacist_user = User.objects.create_user(
            email="phasec.pharmacist@example.com",
            password="StrongPass123!",
            phone_number="0999000",
            role=RoleChoices.PHARMACIST,
            approval_status=ApprovalStatusChoices.APPROVED,
            is_verified=True,
        )
        self.pharmacist = PharmacistProfile.objects.create(
            user=self.pharmacist_user,
            pharmacy=self.pharmacy,
            full_name="Phase C Pharmacist",
            license_number="LIC-001",
            is_approved=True,
        )

    def test_admin_can_list_pharmacies(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse("admin-pharmacy-list"),
            {"search": "Phase C", "page_size": 5},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        pharmacy = response.data["results"][0]
        self.assertEqual(pharmacy["id"], self.pharmacy.id)
        self.assertEqual(pharmacy["pharmacists_count"], 1)
        self.assertIsNone(pharmacy["city"])
        self.assertIsNone(pharmacy["region"])
        self.assertIsNone(pharmacy["license_number"])
        self.assertIsNone(pharmacy["status"])
        self.assertIsNone(pharmacy["notes"])

    def test_non_admin_cannot_list_pharmacies(self):
        self.client.force_authenticate(self.patient_user)

        response = self.client.get(reverse("admin-pharmacy-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_pharmacy_with_existing_fields(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            reverse("admin-pharmacy-list"),
            {
                "name": "Created Pharmacy",
                "phone_number": "0112222",
                "address": "Created Address",
                "latitude": "33.500000",
                "longitude": "36.200000",
                "is_contracted_with_organization": True,
                "organization": self.organization.id,
                "city": "Unsupported City",
                "license_number": "UNSUPPORTED",
                "notes": "Unsupported notes",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Pharmacy.objects.get(name="Created Pharmacy")
        self.assertEqual(created.phone_number, "0112222")
        self.assertFalse(hasattr(created, "city"))
        self.assertFalse(hasattr(created, "license_number"))
        self.assertIsNone(response.data["city"])
        self.assertIsNone(response.data["license_number"])
        self.assertIsNone(response.data["notes"])

    def test_admin_can_patch_pharmacy_existing_fields(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.patch(
            reverse("admin-pharmacy-detail", kwargs={"pk": self.pharmacy.id}),
            {
                "name": "Updated Pharmacy",
                "phone_number": "0113333",
                "address": "Updated Address",
                "latitude": "34.000000",
                "longitude": "37.000000",
                "is_contracted_with_organization": False,
                "city": "Unsupported City",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pharmacy.refresh_from_db()
        self.assertEqual(self.pharmacy.name, "Updated Pharmacy")
        self.assertEqual(self.pharmacy.phone_number, "0113333")
        self.assertFalse(self.pharmacy.is_contracted_with_organization)
        self.assertFalse(hasattr(self.pharmacy, "status"))
        self.assertIsNone(response.data["city"])
        self.assertIsNone(response.data["status"])

    def test_admin_can_retrieve_pharmacy_detail(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse("admin-pharmacy-detail", kwargs={"pk": self.pharmacy.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.pharmacy.id)
        self.assertEqual(response.data["organization"]["id"], self.organization.id)
        self.assertEqual(response.data["pharmacists_count"], 1)

    def test_admin_can_delete_unlinked_pharmacy_and_blocks_linked_pharmacy(self):
        unlinked = Pharmacy.objects.create(
            name="Unlinked Pharmacy",
            address="Unlinked Address",
        )
        self.client.force_authenticate(self.admin_user)

        blocked_response = self.client.delete(
            reverse("admin-pharmacy-detail", kwargs={"pk": self.pharmacy.id})
        )
        deleted_response = self.client.delete(
            reverse("admin-pharmacy-detail", kwargs={"pk": unlinked.id})
        )

        self.assertEqual(blocked_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(blocked_response.data["code"], "pharmacy_delete_blocked")
        self.assertEqual(deleted_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Pharmacy.objects.filter(pk=unlinked.id).exists())

    def test_organization_staff_creates_contracted_pharmacy_without_organization(self):
        staff_user = User.objects.create_user(
            email="phasec.orgstaff.create@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=staff_user,
            organization=self.organization,
            can_manage_pharmacists=True,
        )
        self.client.force_authenticate(staff_user)

        response = self.client.post(
            reverse("admin-pharmacy-list"),
            {
                "name": "Org Staff Contracted Pharmacy",
                "phone_number": "0999999999",
                "address": "Damascus",
                "latitude": "33.500000",
                "longitude": "36.300000",
                "is_contracted_with_organization": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Pharmacy.objects.get(name="Org Staff Contracted Pharmacy")
        self.assertEqual(created.organization, self.organization)
        self.assertTrue(created.is_contracted_with_organization)
        self.assertEqual(response.data["organization"]["id"], self.organization.id)

    def test_organization_staff_updates_unassigned_pharmacy_to_contracted(self):
        staff_user = User.objects.create_user(
            email="phasec.orgstaff.patch@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=staff_user,
            organization=self.organization,
            can_manage_pharmacists=True,
        )
        pharmacy = Pharmacy.objects.create(
            name="Unassigned Patch Pharmacy",
            address="Damascus",
            is_contracted_with_organization=False,
        )
        self.client.force_authenticate(staff_user)

        response = self.client.patch(
            reverse("admin-pharmacy-detail", kwargs={"pk": pharmacy.id}),
            {"is_contracted_with_organization": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pharmacy.refresh_from_db()
        self.assertTrue(pharmacy.is_contracted_with_organization)
        self.assertEqual(pharmacy.organization, self.organization)
        self.assertEqual(response.data["organization"]["id"], self.organization.id)

    def test_organization_staff_cannot_assign_another_organization(self):
        other_organization = Organization.objects.create(name="Other Phase C Org")
        staff_user = User.objects.create_user(
            email="phasec.orgstaff.scope@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=staff_user,
            organization=self.organization,
            can_manage_pharmacists=True,
        )
        self.client.force_authenticate(staff_user)

        create_response = self.client.post(
            reverse("admin-pharmacy-list"),
            {
                "name": "Wrong Org Create Pharmacy",
                "address": "Damascus",
                "is_contracted_with_organization": True,
                "organization": other_organization.id,
            },
            format="json",
        )
        pharmacy = Pharmacy.objects.create(
            name="Wrong Org Patch Pharmacy",
            address="Damascus",
            is_contracted_with_organization=False,
        )
        patch_response = self.client.patch(
            reverse("admin-pharmacy-detail", kwargs={"pk": pharmacy.id}),
            {
                "is_contracted_with_organization": True,
                "organization": other_organization.id,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(create_response.data["code"], "organization_scope_mismatch")
        self.assertFalse(
            Pharmacy.objects.filter(name="Wrong Org Create Pharmacy").exists()
        )
        self.assertEqual(patch_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(patch_response.data["code"], "organization_scope_mismatch")
        pharmacy.refresh_from_db()
        self.assertIsNone(pharmacy.organization)
        self.assertFalse(pharmacy.is_contracted_with_organization)

    def test_superuser_without_organization_cannot_create_contracted_without_org(self):
        superuser = User.objects.create_superuser(
            email="phasec.superuser@example.com",
            password="StrongPass123!",
        )
        self.client.force_authenticate(superuser)

        response = self.client.post(
            reverse("admin-pharmacy-list"),
            {
                "name": "Superuser Missing Org Pharmacy",
                "address": "Damascus",
                "is_contracted_with_organization": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "admin_organization_required")
        self.assertFalse(
            Pharmacy.objects.filter(name="Superuser Missing Org Pharmacy").exists()
        )

    def test_non_contracted_pharmacy_can_be_created_without_organization(self):
        staff_user = User.objects.create_user(
            email="phasec.orgstaff.noncontracted@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=staff_user,
            organization=self.organization,
            can_manage_pharmacists=True,
        )
        self.client.force_authenticate(staff_user)

        response = self.client.post(
            reverse("admin-pharmacy-list"),
            {
                "name": "Org Staff Non Contracted Pharmacy",
                "address": "Damascus",
                "is_contracted_with_organization": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Pharmacy.objects.get(name="Org Staff Non Contracted Pharmacy")
        self.assertIsNone(created.organization)
        self.assertFalse(created.is_contracted_with_organization)
        self.assertIsNone(response.data["organization"])

    def test_organization_staff_list_is_scoped_to_own_organization(self):
        other_organization = Organization.objects.create(name="Other List Org")
        own_pharmacy = Pharmacy.objects.create(
            name="Own Scoped Pharmacy",
            address="Damascus",
            organization=self.organization,
            is_contracted_with_organization=True,
        )
        other_pharmacy = Pharmacy.objects.create(
            name="Other Scoped Pharmacy",
            address="Aleppo",
            organization=other_organization,
            is_contracted_with_organization=True,
        )
        Pharmacy.objects.create(
            name="Unassigned Scoped Pharmacy",
            address="Homs",
        )
        staff_user = User.objects.create_user(
            email="phasec.orgstaff.list@example.com",
            password="StrongPass123!",
            role=RoleChoices.ADMIN,
            is_staff=True,
        )
        OrganizationStaffProfile.objects.create(
            user=staff_user,
            organization=self.organization,
            can_manage_pharmacists=True,
        )
        self.client.force_authenticate(staff_user)

        response = self.client.get(reverse("admin-pharmacy-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pharmacy_ids = {row["id"] for row in response.data["results"]}
        self.assertIn(own_pharmacy.id, pharmacy_ids)
        self.assertIn(self.pharmacy.id, pharmacy_ids)
        self.assertNotIn(other_pharmacy.id, pharmacy_ids)
        self.assertFalse(
            any(
                row["name"] == "Unassigned Scoped Pharmacy"
                for row in response.data["results"]
            )
        )

    def test_admin_can_list_pharmacists(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse("admin-pharmacist-list"),
            {"search": "Phase C", "page_size": 5},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        pharmacist = response.data["results"][0]
        self.assertEqual(pharmacist["id"], self.pharmacist.id)
        self.assertEqual(pharmacist["pharmacy"]["id"], self.pharmacy.id)
        self.assertIsNone(pharmacist["pharmacy"]["city"])
        self.assertIsNone(pharmacist["notes"])

    def test_non_admin_cannot_list_pharmacists(self):
        self.client.force_authenticate(self.patient_user)

        response = self.client.get(reverse("admin-pharmacist-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_pharmacist(self):
        other_pharmacy = Pharmacy.objects.create(
            name="Create Pharmacist Pharmacy",
            address="Create Pharmacist Address",
            organization=self.organization,
        )
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            reverse("admin-pharmacist-list"),
            {
                "full_name": "Created Pharmacist",
                "phone_number": "0999111",
                "email": "created.pharmacist@example.com",
                "license_number": "LIC-NEW",
                "pharmacy_id": other_pharmacy.id,
                "account_status": {"approval_status": "approved"},
                "notes": "Unsupported notes",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = PharmacistProfile.objects.get(license_number="LIC-NEW")
        self.assertEqual(created.user.role, RoleChoices.PHARMACIST)
        self.assertEqual(created.pharmacy, other_pharmacy)
        self.assertTrue(created.is_approved)
        self.assertTrue(response.data["temporary_password_generated"])
        self.assertIn("temporary_password", response.data)
        self.assertFalse(hasattr(created, "notes"))
        self.assertIsNone(response.data["notes"])

    def test_admin_can_retrieve_pharmacist_detail(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(
            reverse("admin-pharmacist-detail", kwargs={"pk": self.pharmacist.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.pharmacist.id)
        self.assertEqual(response.data["pharmacy"]["name"], self.pharmacy.name)
        self.assertEqual(response.data["account_status"]["approval_status"], "approved")

    def test_admin_can_patch_pharmacist_safe_fields(self):
        other_pharmacy = Pharmacy.objects.create(
            name="Patch Pharmacist Pharmacy",
            address="Patch Pharmacist Address",
            organization=self.organization,
        )
        self.client.force_authenticate(self.admin_user)

        response = self.client.patch(
            reverse("admin-pharmacist-detail", kwargs={"pk": self.pharmacist.id}),
            {
                "full_name": "Updated Pharmacist",
                "phone_number": "0999222",
                "email": "updated.pharmacist@example.com",
                "license_number": "LIC-UPDATED",
                "pharmacy_id": other_pharmacy.id,
                "account_status": {
                    "is_active": True,
                    "approval_status": "approved",
                },
                "is_approved": True,
                "notes": "Unsupported notes",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pharmacist.refresh_from_db()
        self.pharmacist_user.refresh_from_db()
        self.assertEqual(self.pharmacist.full_name, "Updated Pharmacist")
        self.assertEqual(self.pharmacist.license_number, "LIC-UPDATED")
        self.assertEqual(self.pharmacist.pharmacy, other_pharmacy)
        self.assertEqual(self.pharmacist_user.phone_number, "0999222")
        self.assertEqual(self.pharmacist_user.email, "updated.pharmacist@example.com")
        self.assertTrue(self.pharmacist.is_approved)
        self.assertEqual(
            self.pharmacist_user.approval_status,
            ApprovalStatusChoices.APPROVED,
        )
        self.assertFalse(hasattr(self.pharmacist, "notes"))
        self.assertIsNone(response.data["notes"])

    def test_admin_delete_pharmacist_deactivates_user_without_hard_delete(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.delete(
            reverse("admin-pharmacist-detail", kwargs={"pk": self.pharmacist.id})
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.pharmacist.refresh_from_db()
        self.pharmacist_user.refresh_from_db()
        self.assertFalse(self.pharmacist_user.is_active)
        self.assertFalse(self.pharmacist.is_approved)
        self.assertTrue(
            PharmacistProfile.objects.filter(pk=self.pharmacist.id).exists()
        )
