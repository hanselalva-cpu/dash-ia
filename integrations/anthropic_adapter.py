"""Extrae cantidades de uso de respuestas del SDK de Anthropic (Messages API)."""

from integrations._common import get_field
from models.schemas import UsageUnit


def quantities_from_response(response) -> dict[UsageUnit, int]:
    usage = get_field(response, "usage", default=None)
    # En Anthropic input_tokens ya excluye lecturas y escrituras de caché.
    return {
        UsageUnit.INPUT_TOKENS: get_field(usage, "input_tokens"),
        UsageUnit.CACHED_INPUT_TOKENS: get_field(usage, "cache_read_input_tokens"),
        UsageUnit.CACHE_WRITE_TOKENS: get_field(usage, "cache_creation_input_tokens"),
        UsageUnit.OUTPUT_TOKENS: get_field(usage, "output_tokens"),
    }
