"""JSON Schema para respuestas fundamentadas con fuentes."""

ANSWER_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "sufficient_info": {"type": "boolean"},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"chunk_id": {"type": "string"}},
                "required": ["chunk_id"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answer", "sufficient_info", "sources"],
    "additionalProperties": False,
}
