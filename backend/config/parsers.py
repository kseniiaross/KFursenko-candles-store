from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser


class ObjectJSONParser(JSONParser):
    """JSON, but only a JSON object.

    Views read request.data like a dict. A list or a bare string parsed
    fine and then crashed the view with a 500.
    """

    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type, parser_context)

        if not isinstance(data, dict):
            raise ParseError("Expected a JSON object.")

        return data
