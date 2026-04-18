from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.permissions import (
    CanManagePharmacists,
    IsPharmacistRole,
)
from common.choices import RoleChoices

from .models import PharmacistProfile, Pharmacy
from .serializers import (
    PharmacistMeUpdateSerializer,
    PharmacistProfileSerializer,
    PharmacySerializer,
)


class PharmacyViewSet(viewsets.ModelViewSet):
    serializer_class = PharmacySerializer
    queryset = Pharmacy.objects.select_related('organization', 'owner_user')
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        if self.request.user.is_authenticated and self.request.user.role == RoleChoices.ADMIN:
            permission_classes = [IsAuthenticated, CanManagePharmacists]
        elif self.action == 'create':
            permission_classes = [IsAuthenticated, CanManagePharmacists]
        else:
            permission_classes = [IsAuthenticated, IsPharmacistRole]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.role == RoleChoices.PHARMACIST:
            pharmacist_profile = getattr(self.request.user, 'pharmacist_profile', None)
            if pharmacist_profile is None:
                return queryset.none()
            return queryset.filter(pk=pharmacist_profile.pharmacy_id)
        staff_profile = getattr(self.request.user, 'organization_staff_profile', None)
        if self.request.user.is_superuser or staff_profile is None:
            return queryset
        return queryset.filter(organization=staff_profile.organization)

    @action(detail=False, methods=['get'], url_path='contracted')
    def contracted(self, request):
        queryset = self.filter_queryset(
            self.get_queryset().filter(is_contracted_with_organization=True)
        )
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class PharmacistProfileViewSet(mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = PharmacistProfileSerializer
    permission_classes = [IsAuthenticated, IsPharmacistRole]
    queryset = PharmacistProfile.objects.select_related('user', 'pharmacy')
    http_method_names = ['get', 'patch', 'head', 'options']

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
