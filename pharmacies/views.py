from django.db.models import Count, Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from common.api_errors import validation_error_payload
from common.choices import RoleChoices
from common.permissions import CanManagePharmacists, IsPatientRole, IsPharmacistRole

from .models import PharmacistProfile, Pharmacy
from .serializers import (
    AdminPharmacistSerializer,
    AdminPharmacistWriteSerializer,
    AdminPharmacySerializer,
    AdminPharmacyWriteSerializer,
    PharmacistMeUpdateSerializer,
    PharmacistProfileSerializer,
    PharmacyCompatSerializer,
    PharmacySerializer,
    SafePharmacySerializer,
)


class AdminPageNumberPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100


class PharmacyViewSet(viewsets.ModelViewSet):
    serializer_class = PharmacySerializer
    queryset = Pharmacy.objects.select_related("organization", "owner_user")
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        if (
            self.request.user.is_authenticated
            and self.request.user.role == RoleChoices.ADMIN
        ):
            permission_classes = [IsAuthenticated, CanManagePharmacists]
        elif self.action == "create":
            permission_classes = [IsAuthenticated, CanManagePharmacists]
        else:
            permission_classes = [IsAuthenticated, IsPharmacistRole]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.role == RoleChoices.PHARMACIST:
            pharmacist_profile = getattr(self.request.user, "pharmacist_profile", None)
            if pharmacist_profile is None:
                return queryset.none()
            return queryset.filter(pk=pharmacist_profile.pharmacy_id)
        staff_profile = getattr(self.request.user, "organization_staff_profile", None)
        if self.request.user.is_superuser or staff_profile is None:
            return queryset
        return queryset.filter(organization=staff_profile.organization)

    @action(detail=False, methods=["get"], url_path="contracted")
    def contracted(self, request):
        queryset = self.filter_queryset(
            self.get_queryset().filter(is_contracted_with_organization=True)
        )
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class AdminPharmacyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, CanManagePharmacists]
    pagination_class = AdminPageNumberPagination
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.action in {"create", "partial_update"}:
            return AdminPharmacyWriteSerializer
        return AdminPharmacySerializer

    def get_queryset(self):
        queryset = (
            Pharmacy.objects.select_related("organization", "owner_user")
            .annotate(pharmacists_count=Count("pharmacists"))
            .order_by("-created_at", "-id")
        )
        staff_profile = getattr(self.request.user, "organization_staff_profile", None)
        if not self.request.user.is_superuser and staff_profile is not None:
            if self.action == "partial_update":
                queryset = queryset.filter(
                    Q(organization=staff_profile.organization)
                    | Q(organization__isnull=True)
                )
            else:
                queryset = queryset.filter(organization=staff_profile.organization)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(phone_number__icontains=search)
                | Q(address__icontains=search)
            )

        contracted = self.request.query_params.get("is_contracted_with_organization")
        if contracted is not None:
            normalized = str(contracted).strip().lower()
            if normalized in {"1", "true", "yes"}:
                queryset = queryset.filter(is_contracted_with_organization=True)
            elif normalized in {"0", "false", "no"}:
                queryset = queryset.filter(is_contracted_with_organization=False)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                validation_error_payload(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )
        pharmacy = serializer.save()
        return Response(
            AdminPharmacySerializer(pharmacy).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        pharmacy = self.get_object()
        serializer = self.get_serializer(
            pharmacy,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(
                validation_error_payload(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )
        pharmacy = serializer.save()
        return Response(AdminPharmacySerializer(pharmacy).data)

    def destroy(self, request, *args, **kwargs):
        pharmacy = self.get_object()
        if (
            pharmacy.pharmacists.exists()
            or pharmacy.prescriptions.exists()
            or pharmacy.patient_sessions.exists()
        ):
            return Response(
                {
                    "detail": (
                        "Pharmacy cannot be deleted because related pharmacists, "
                        "prescriptions, or patient sessions exist."
                    ),
                    "code": "pharmacy_delete_blocked",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        pharmacy.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminPharmacistViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, CanManagePharmacists]
    serializer_class = AdminPharmacistSerializer
    pagination_class = AdminPageNumberPagination
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.action in {"create", "partial_update"}:
            return AdminPharmacistWriteSerializer
        return AdminPharmacistSerializer

    def get_queryset(self):
        queryset = PharmacistProfile.objects.select_related(
            "user",
            "pharmacy",
            "pharmacy__organization",
        ).order_by("-created_at", "-id")
        staff_profile = getattr(self.request.user, "organization_staff_profile", None)
        if not self.request.user.is_superuser and staff_profile is not None:
            queryset = queryset.filter(
                pharmacy__organization=staff_profile.organization
            )

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search)
                | Q(user__phone_number__icontains=search)
                | Q(user__email__icontains=search)
                | Q(license_number__icontains=search)
                | Q(pharmacy__name__icontains=search)
            )

        pharmacy_id = self.request.query_params.get("pharmacy_id")
        if pharmacy_id:
            queryset = queryset.filter(pharmacy_id=pharmacy_id)

        approval_status = self.request.query_params.get("approval_status")
        if approval_status:
            queryset = queryset.filter(user__approval_status=approval_status)

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            normalized = str(is_active).strip().lower()
            if normalized in {"1", "true", "yes"}:
                queryset = queryset.filter(user__is_active=True)
            elif normalized in {"0", "false", "no"}:
                queryset = queryset.filter(user__is_active=False)

        is_approved = self.request.query_params.get("is_approved")
        if is_approved is not None:
            normalized = str(is_approved).strip().lower()
            if normalized in {"1", "true", "yes"}:
                queryset = queryset.filter(is_approved=True)
            elif normalized in {"0", "false", "no"}:
                queryset = queryset.filter(is_approved=False)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        pharmacist = serializer.save()
        payload = dict(AdminPharmacistSerializer(pharmacist).data)
        payload["temporary_password_generated"] = getattr(
            serializer,
            "temporary_password_generated",
            False,
        )
        temporary_password = getattr(serializer, "temporary_password", None)
        if temporary_password:
            payload["temporary_password"] = temporary_password
        return Response(payload, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        pharmacist = self.get_object()
        serializer = self.get_serializer(
            pharmacist,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        pharmacist = serializer.save()
        return Response(AdminPharmacistSerializer(pharmacist).data)

    def destroy(self, request, *args, **kwargs):
        pharmacist = self.get_object()
        user = pharmacist.user
        user.is_active = False
        user.save(update_fields=["is_active", "updated_at"])
        pharmacist.is_approved = False
        pharmacist.save(update_fields=["is_approved", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublicContractedPharmacyViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = SafePharmacySerializer
    permission_classes = [AllowAny]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        return Pharmacy.objects.filter(is_contracted_with_organization=True).order_by(
            "name"
        )


class PatientPharmacyViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = SafePharmacySerializer
    permission_classes = [IsAuthenticated, IsPatientRole]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        return Pharmacy.objects.filter(is_contracted_with_organization=True).order_by(
            "name"
        )


class PharmacistProfileViewSet(mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = PharmacistProfileSerializer
    permission_classes = [IsAuthenticated, IsPharmacistRole]
    queryset = PharmacistProfile.objects.select_related("user", "pharmacy")
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user.pharmacist_profile

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        profile = self.get_object()
        serializer = PharmacistMeUpdateSerializer(
            profile,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(PharmacistProfileSerializer(profile).data)


class PharmacistPharmacyViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsPharmacistRole]

    def _get_pharmacy(self):
        return self.request.user.pharmacist_profile.pharmacy

    def retrieve(self, request):
        serializer = PharmacyCompatSerializer(self._get_pharmacy())
        return Response(serializer.data)

    def partial_update(self, request):
        pharmacy = self._get_pharmacy()
        serializer = PharmacyCompatSerializer(
            pharmacy,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(PharmacyCompatSerializer(pharmacy).data)
