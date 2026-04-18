from rest_framework import serializers
from .models import Organization, OrganizationStaffProfile


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = '__all__'


class OrganizationStaffProfileSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = OrganizationStaffProfile
        fields = ('id', 'user_email', 'organization_name', 'job_title', 'can_manage_patients', 'can_manage_pharmacists', 'created_at')
        read_only_fields = ('id', 'created_at')
