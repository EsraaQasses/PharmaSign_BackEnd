from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.api_errors import error_response
from common.permissions import IsAdminRole

from .serializers import AdminOrganizationMeSerializer


class AdminOrganizationMeView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def _staff_organization(self, user):
        staff_profile = getattr(user, "organization_staff_profile", None)
        return getattr(staff_profile, "organization", None)

    def _organization_required_response(self):
        return error_response(
            (
                "This admin account is not linked to an organization. "
                "Use an organization-linked admin account to manage organization settings."
            ),
            "admin_organization_required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def get(self, request):
        organization = self._staff_organization(request.user)
        if organization is None:
            return self._organization_required_response()
        return Response(AdminOrganizationMeSerializer(organization).data)

    def patch(self, request):
        organization = self._staff_organization(request.user)
        if organization is None:
            return self._organization_required_response()
        serializer = AdminOrganizationMeSerializer(
            organization,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
