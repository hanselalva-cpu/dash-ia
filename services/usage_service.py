"""Agregaciones de uso para el dashboard (pandas)."""

import pandas as pd

from models.schemas import UsageEvent

COLUMNS = ["occurred_at", "provider", "model", "agent", "campaign_id", "api_key_id", "cost_usd", "cost", "source"]


def to_dataframe(events: list[UsageEvent], display_rate: float = 1.0) -> pd.DataFrame:
    """`cost_usd` = costo original; `cost` = convertido a la moneda de visualización (× display_rate)."""
    if not events:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(
        [
            {
                "occurred_at": e.occurred_at,
                "provider": str(e.provider),
                "model": e.model,
                "campaign_id": str(e.campaign_id) if e.campaign_id else None,
                "api_key_id": str(e.api_key_id) if e.api_key_id else None,
                "cost_usd": float(e.cost_usd or 0),
                "source": str(e.source),
                # Recurso que generó el costo: agente (ElevenLabs) o API key (OpenAI).
                "agent": e.metadata.get("agent_name") or e.metadata.get("key_name"),
            }
            for e in events
        ]
    )
    df["occurred_at"] = pd.to_datetime(df["occurred_at"], utc=True)
    df["cost"] = df["cost_usd"] * display_rate
    return df[COLUMNS]


def cost_by(df: pd.DataFrame, column: str, value: str = "cost") -> pd.DataFrame:
    return df.groupby(column, dropna=False)[value].sum().reset_index().sort_values(value, ascending=False)


def daily_cost(df: pd.DataFrame, split_by: str | None = "provider", tz: str = "UTC", value: str = "cost") -> pd.DataFrame:
    """Agrupa por día local de `tz` (un evento 23:30 CDMX cae en su día, no en el siguiente UTC)."""
    keys = [df["occurred_at"].dt.tz_convert(tz).dt.date.rename("day")]
    if split_by:
        keys.append(df[split_by])
    return df.groupby(keys)[value].sum().reset_index()
