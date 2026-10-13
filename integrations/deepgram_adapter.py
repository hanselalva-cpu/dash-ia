"""Extrae duración de audio de respuestas de transcripción pre-grabada de Deepgram."""

from integrations._common import get_field
from models.schemas import UsageUnit


def quantities_from_response(response) -> dict[UsageUnit, float]:
    return {UsageUnit.AUDIO_SECONDS: float(get_field(response, "metadata", "duration"))}
