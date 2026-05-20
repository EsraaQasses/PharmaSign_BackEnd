from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.utils import IntegrityError
from django.utils.text import Truncator
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.api_errors import error_response
from common.permissions import IsAdminRole

from .models import Organization, OrganizationStaffProfile
from .serializers import AdminOrganizationMeSerializer


class AdminOrganizationMeView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def _staff_profile(self, user):
        return getattr(user, "organization_staff_profile", None)

    def _staff_organization(self, user):
        staff_profile = getattr(user, "organization_staff_profile", None)
        return getattr(staff_profile, "organization", None)

    def _initialization_failed_response(self):
        return error_response(
            "Admin organization profile could not be initialized.",
            "admin_organization_initialization_failed",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def _organization_name_identifier(self, user):
        full_name = getattr(user, "full_name", "")
        if full_name:
            return full_name
        if user.email:
            return user.email
        if user.phone_number:
            return user.phone_number
        return "My Organization"

    def _default_organization_name(self, user):
        base_name = f"Organization for {self._organization_name_identifier(user)}"
        base_name = Truncator(base_name).chars(255)
        if not Organization.objects.filter(name=base_name).exists():
            return base_name

        fallback = f"Organization for admin #{user.id}"
        fallback = Truncator(fallback).chars(255)
        if not Organization.objects.filter(name=fallback).exists():
            return fallback

        suffix = 2
        while True:
            candidate = Truncator(f"{fallback} ({suffix})").chars(255)
            if not Organization.objects.filter(name=candidate).exists():
                return candidate
            suffix += 1

    @transaction.atomic
    def _get_or_initialize_organization(self, user):
        staff_profile = self._staff_profile(user)
        if staff_profile is not None:
            return staff_profile.organization

        organization = Organization.objects.create(
            name=self._default_organization_name(user),
            phone=user.phone_number or "",
            city="",
            region="",
            address="",
            description="",
        )
        OrganizationStaffProfile.objects.create(
            user=user,
            organization=organization,
            job_title="Organization Admin",
            can_manage_patients=True,
            can_manage_pharmacists=True,
        )
        return organization

    def get(self, request):
        try:
            organization = self._get_or_initialize_organization(request.user)
        except (DjangoValidationError, IntegrityError):
            return self._initialization_failed_response()
        return Response(AdminOrganizationMeSerializer(organization).data)

    def patch(self, request):
        try:
            organization = self._get_or_initialize_organization(request.user)
        except (DjangoValidationError, IntegrityError):
            return self._initialization_failed_response()
        serializer = AdminOrganizationMeSerializer(
            organization,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
