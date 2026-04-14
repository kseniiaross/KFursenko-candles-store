from rest_framework import serializers


class LumiereMessageSerializer(serializers.Serializer):
    """Single message in the conversation history."""
    role = serializers.ChoiceField(choices=["user", "assistant"])
    text = serializers.CharField(max_length=4000)


class LumiereReplyInSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=2000)
    locale = serializers.ChoiceField(choices=["en", "ru", "es", "fr"], default="en")
    userName = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    page = serializers.CharField(required=False, allow_blank=True, default="")
    # Last N messages so the model remembers the conversation
    history = LumiereMessageSerializer(many=True, required=False, default=list)


class LumiereSuggestionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.CharField()
    price = serializers.CharField()
    in_stock = serializers.BooleanField()


class LumiereReplyOutSerializer(serializers.Serializer):
    text = serializers.CharField()
    suggestions = LumiereSuggestionSerializer(many=True, required=False)