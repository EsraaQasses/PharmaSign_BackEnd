from rest_framework.permissions import BasePermission

from common.choices import RoleChoices


def get_staff_profile(user):
    return getattr(user, "organization_staff_profile", None)


def is_admin_role(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.role == RoleChoices.ADMIN)
    )


def is_pharmacist_role(user):
    return bool(user and user.is_authenticated and user.role == RoleChoices.PHARMACIST)


def is_patient_role(user):
    return bool(user and user.is_authenticated and user.role == RoleChoices.PATIENT)


def get_staff_organization(user):
    profile = get_staff_profile(user)
    return getattr(profile, "organization", None)


def has_patient_management_access(user):
    if not is_admin_role(user):
        return False
    profile = get_staff_profile(user)
    return profile is None or profile.can_manage_patients


def has_pharmacist_management_access(user):
    if not is_admin_role(user):
        return False
    profile = get_staff_profile(user)
    return profile is None or profile.can_manage_pharmacists


def get_pharmacist_profile(user):
    return getattr(user, "pharmacist_profile", None)


def is_approved_pharmacist(user):
    if not is_pharmacist_role(user):
        return False
    profile = get_pharmacist_profile(user)
    return bool(profile and profile.is_approved)


def pharmacist_can_access_patient(user, patient_profile):
    pharmacist_profile = get_pharmacist_profile(user)
    if not pharmacist_profile or not pharmacist_profile.is_approved:
        return False

    if patient_profile.organization_id is None:
        return True

    pharmacy = pharmacist_profile.pharmacy
    return bool(
        pharmacy.is_contracted_with_organization
        and pharmacy.organization_id == patient_profile.organization_id
    )


def admin_can_access_patient(user, patient_profile):
    if not has_patient_management_access(user):
        return False
    profile = get_staff_profile(user)
    return bool(
        user.is_superuser
        or profile is None
        or patient_profile.organization_id == profile.organization_id
    )


def user_can_view_patient_medical_data(user, patient_profile):
    if not user or not user.is_authenticated or patient_profile is None:
        return False
    if admin_can_access_patient(user, patient_profile):
        return True
    if is_patient_role(user):
        return getattr(patient_profile, "user_id", None) == user.id
    return pharmacist_can_access_patient(user, patient_profile)


def user_can_view_prescription_medical_data(user, prescription):
    patient_profile = getattr(prescription, "patient", None)
    if not user_can_view_patient_medical_data(user, patient_profile):
        return False
    if is_pharmacist_role(user):
        pharmacist_profile = get_pharmacist_profile(user)
        return bool(
            pharmacist_profile
            and pharmacist_profile.is_approved
            and (
                getattr(prescription, "pharmacist_id", None) == pharmacist_profile.id
                or pharmacist_can_access_patient(user, patient_profile)
            )
        )
    return True


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return is_admin_role(request.user)


class IsPharmacistRole(BasePermission):
    def has_permission(self, request, view):
        return is_pharmacist_role(request.user)


class IsPatientRole(BasePermission):
    def has_permission(self, request, view):
        return is_patient_role(request.user)


class CanManagePatients(BasePermission):
    def has_permission(self, request, view):
        return has_patient_management_access(request.user)


class CanManagePharmacists(BasePermission):
    def has_permission(self, request, view):
        return has_pharmacist_management_access(request.user)


class IsAdminOrPharmacistRole(BasePermission):
    def has_permission(self, request, view):
        return is_admin_role(request.user) or is_pharmacist_role(request.user)


class IsApprovedPharmacistRole(BasePermission):
    message = "Pharmacist account is not approved."

    def has_permission(self, request, view):
        return is_approved_pharmacist(request.user)
