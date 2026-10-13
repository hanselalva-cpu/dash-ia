"""Cómo registrar consumo desde tu app tras cada llamada a un proveedor.

Ejecutar desde la raíz del proyecto:  python -m examples.record_usage_example
Requiere .env con Supabase configurado (en modo demo el insert falla a propósito).
"""

from uuid import UUID

from integrations import anthropic_adapter, elevenlabs_adapter
from integrations.usage_recorder import UsageRecorder
from models.schemas import Provider
from repositories import get_repositories

CAMPAIGN_ID = UUID("11111111-1111-1111-1111-111111111111")


def main() -> None:
    repos = get_repositories()
    recorder = UsageRecorder(repos.usage, repos.rates, repos.api_keys)

    # 1) Anthropic: pasar la respuesta del SDK (aquí simulada con dict).
    fake_response = {"id": "msg_01", "usage": {"input_tokens": 1500, "output_tokens": 420}}
    event = recorder.record(
        Provider.ANTHROPIC,
        "claude-haiku-5-5",
        anthropic_adapter.quantities_from_response(fake_response),
        campaign_id=CAMPAIGN_ID,
        external_id=fake_response["id"],
    )
    print("Anthropic:", event.cost_usd, "USD")

    # 2) ElevenLabs: se mide por el texto enviado.
    text = "Hola, le llamamos para confirmar su cita de mañana."
    event = recorder.record(
        Provider.ELEVENLABS, "eleven_multilingual_v2", elevenlabs_adapter.quantities_from_text(text),
        campaign_id=CAMPAIGN_ID,
    )
    print("ElevenLabs:", event.cost_usd, "USD")


if __name__ == "__main__":
    main()
