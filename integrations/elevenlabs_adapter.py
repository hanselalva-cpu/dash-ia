"""ElevenLabs TTS cobra por caracteres del texto enviado; la respuesta (audio) no trae uso."""

from models.schemas import UsageUnit


def quantities_from_text(text: str) -> dict[UsageUnit, int]:
    return {UsageUnit.CHARACTERS: len(text)}
