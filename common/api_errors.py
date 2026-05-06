from rest_framework import status
from rest_framework.response import Response


def error_response(
    detail, code, *, fields=None, status_code=status.HTTP_400_BAD_REQUEST
):
    payload = {
        "detail": detail,
        "code": code,
    }
    if fields is not None:
        payload["fields"] = fields
    return Response(payload, status=status_code)


def validation_error_payload(errors, *, default_code="missing_required_field"):
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        errors = errors[0]
    if (
        isinstance(errors, dict)
        and "non_field_errors" in errors
        and errors["non_field_errors"]
        and isinstance(errors["non_field_errors"][0], dict)
    ):
        errors = errors["non_field_errors"][0]
    fields = {}
    for field, messages in errors.items():
        if field in {"detail", "code", "fields"}:
            continue
        fields[field] = messages

    detail = "Invalid request."
    code = default_code
    if isinstance(errors, dict):
        detail_value = errors.get("detail")
        code_value = errors.get("code")
        fields_value = errors.get("fields")
        if detail_value:
            detail = detail_value[0] if isinstance(detail_value, list) else detail_value
        if code_value:
            code = code_value[0] if isinstance(code_value, list) else code_value
        if fields_value and isinstance(fields_value, dict):
            fields.update(fields_value)
    if fields and code == default_code and detail == "Invalid request.":
        detail = "Missing or invalid required fields."
    payload = {
        "detail": str(detail),
        "code": str(code),
        "fields": fields,
    }
    for field, messages in fields.items():
        payload[field] = messages
    return payload
