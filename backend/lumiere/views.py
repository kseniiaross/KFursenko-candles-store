# backend/lumiere/views.py
import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status, throttling

from .serializers import LumiereReplyInSerializer, LumiereReplyOutSerializer
from .services import search_candles, build_store_context, call_openai_reply

logger = logging.getLogger(__name__)


class LumiereAnonThrottle(throttling.AnonRateThrottle):
    scope = "lumiere_anon"


class LumiereUserThrottle(throttling.UserRateThrottle):
    scope = "lumiere_user"


class LumiereReplyView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [LumiereAnonThrottle, LumiereUserThrottle]

    def post(self, request):
        ser = LumiereReplyInSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        text = data["text"]
        locale = data.get("locale", "en")
        user_name = (data.get("userName") or "").strip() or None
        history = data.get("history", [])

        suggestions = search_candles(text, limit=6)
        store_context = build_store_context(suggestions)

        try:
            answer_text = call_openai_reply(
                locale=locale,
                user_name=user_name,
                user_text=text,
                store_context=store_context,
                history=history,
            )
        except Exception:
            logger.exception("Lumiere reply failed")
            answer_text = (
                "Sorry, something went wrong. Please try again."
                if locale == "en"
                else "Извини, что-то пошло не так. Попробуй ещё раз."
                if locale == "ru"
                else "Lo siento, algo salió mal. Por favor, inténtalo de nuevo."
                if locale == "es"
                else "Désolée, quelque chose s'est mal passé. Veuillez réessayer."
            )

        out = {"text": answer_text}
        if suggestions:
            out["suggestions"] = suggestions

        out_ser = LumiereReplyOutSerializer(data=out)
        out_ser.is_valid(raise_exception=True)

        return Response(out_ser.data, status=status.HTTP_200_OK)