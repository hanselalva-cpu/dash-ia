"""Extrae cantidades de uso de respuestas del SDK de OpenAI (Chat Completions y Responses API)."""

from integrations._common import get_field
from models.schemas import UsageUnit


def quantities_from_response(response) -> dict[UsageUnit, int]:
    usage = get_field(response, "usage", default=None)
    # Chat Completions usa prompt/completion_tokens; Responses API usa input/output_tokens.
    prompt = get_field(usage, "prompt_tokens") or get_field(usage, "input_tokens")
    completion = get_field(usage, "completion_tokens") or get_field(usage, "output_tokens")
    cached = get_field(usage, "prompt_tokens_details", "cached_tokens") or get_field(
        usage, "input_tokens_details", "cached_tokens"
    )
    # Los tokens cacheados vienen incluidos en prompt: se separan para no cobrarlos dos veces.
    return {
        UsageUnit.INPUT_TOKENS: prompt - cached,
        UsageUnit.CACHED_INPUT_TOKENS: cached,
        UsageUnit.OUTPUT_TOKENS: completion,
    }
