from rest_framework.exceptions import PermissionDenied

from common.permissions import (
    user_can_view_patient_medical_data,
    user_can_view_prescription_medical_data,
)


class SensitiveMedicalDataSerializerMixin:
    """
    Sensitive medical fields are decrypted only inside the backend field layer.
    Serializers using this mixin must receive an authenticated request context
    and pass object-level authorization before touching encrypted attributes.
    """

    sensitive_patient_attr = None
    sensitive_prescription_attr = None

    def _request_user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def _sensitive_patient(self, instance):
        if self.sensitive_patient_attr:
            return getattr(instance, self.sensitive_patient_attr, None)
        return None

    def _sensitive_prescription(self, instance):
        if self.sensitive_prescription_attr:
            return getattr(instance, self.sensitive_prescription_attr, None)
        return None

    def assert_sensitive_medical_access(self, instance):
        user = self._request_user()
        prescription = self._sensitive_prescription(instance)
        if prescription is not None:
            if user_can_view_prescription_medical_data(user, prescription):
                return
            raise PermissionDenied(
                "You do not have permission to view this medical data."
            )

        patient = self._sensitive_patient(instance)
        if patient is not None and user_can_view_patient_medical_data(user, patient):
            return
        raise PermissionDenied("You do not have permission to view this medical data.")

    def to_representation(self, instance):
        self.assert_sensitive_medical_access(instance)
        return super().to_representation(instance)
