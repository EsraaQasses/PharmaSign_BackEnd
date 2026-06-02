from rest_framework import serializers


class AIPoseRequestSerializer(serializers.Serializer):
    gloss = serializers.CharField(
        required=True,
        allow_blank=False,
        error_messages={"blank": "Gloss text cannot be empty."}
    )
    return_format = serializers.ChoiceField(
        choices=["npy", "json"],
        default="npy",
        required=False
    )

    def validate_gloss(self, value):
        if not value.strip():
            raise serializers.ValidationError("Gloss text cannot be empty.")
        return value.strip()
