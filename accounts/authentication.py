from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import APIException, AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import Token

from common.choices import ApprovalStatusChoices


PENDING_ACCOUNT_DETAIL = "حسابك قيد مراجعة المنظمة. سيتم تفعيله بعد الموافقة."
REJECTED_ACCOUNT_DETAIL = "تم رفض طلب إنشاء الحساب. يرجى مراجعة المنظمة."


class AccountApprovalFailed(APIException):
    status_code = 403
    default_code = "account_not_approved"


def build_account_block_payload(user):
    if not user.is_active:
        return {"detail": "User account is inactive."}
    if user.approval_status == ApprovalStatusChoices.PENDING:
        return {
            "detail": PENDING_ACCOUNT_DETAIL,
            "approval_status": ApprovalStatusChoices.PENDING,
        }
    if user.approval_status == ApprovalStatusChoices.REJECTED:
        return {
            "detail": REJECTED_ACCOUNT_DETAIL,
            "approval_status": ApprovalStatusChoices.REJECTED,
            "rejection_reason": user.rejection_reason,
        }
    return None


def enforce_account_approval(user):
    if user.is_superuser or user.is_staff:
        return
    block_payload = build_account_block_payload(user)
    if block_payload:
        raise AccountApprovalFailed(block_payload)


class ApprovalAwareJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token: Token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError:
            raise AuthenticationFailed(
                _("Token contained no recognizable user identification")
            )

        try:
            user = self.user_model.objects.get(**{api_settings.USER_ID_FIELD: user_id})
        except self.user_model.DoesNotExist:
            raise AuthenticationFailed(_("User not found"), code="user_not_found")

        enforce_account_approval(user)
        return user
