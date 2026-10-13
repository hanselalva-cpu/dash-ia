"""Importación de uso desde CSV (formato en examples/usage_template.csv)."""

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

from pydantic import ValidationError

from models.schemas import Provider, UsageEvent, UsageSource, UsageUnit

REQUIRED_COLUMNS = {"occurred_at", "provider", "model"}
QUANTITY_COLUMNS = [u.value for u in UsageUnit]


@dataclass
class ImportResult:
    events: list[UsageEvent] = field(default_factory=list)
    errors: list[tuple[int, str]] = field(default_factory=list)  # (fila, mensaje); fila 2 = primera de datos

    @property
    def ok(self) -> bool:
        return not self.errors


def _parse_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value.strip())
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_row(row: dict[str, str]) -> UsageEvent:
    quantities: dict[UsageUnit, Decimal] = {}
    for col in QUANTITY_COLUMNS:
        raw = (row.get(col) or "").strip()
        if not raw:
            continue
        try:
            qty = Decimal(raw)
        except InvalidOperation:
            raise ValueError(f"{col}: '{raw}' no es número")
        if qty < 0:
            raise ValueError(f"{col}: no puede ser negativo")
        quantities[UsageUnit(col)] = qty
    if not quantities:
        raise ValueError("fila sin cantidades")

    def opt_uuid(col: str) -> UUID | None:
        raw = (row.get(col) or "").strip()
        return UUID(raw) if raw else None

    return UsageEvent(
        occurred_at=_parse_datetime(row["occurred_at"]),
        provider=Provider(row["provider"].strip().lower()),
        model=row["model"].strip(),
        quantities=quantities,
        campaign_id=opt_uuid("campaign_id"),
        api_key_id=opt_uuid("api_key_id"),
        source=UsageSource.IMPORT,
        external_id=(row.get("external_id") or "").strip() or None,
    )


def parse_usage_csv(text: str) -> ImportResult:
    result = ImportResult()
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        result.errors.append((1, f"faltan columnas: {', '.join(sorted(missing))}"))
        return result

    seen_external_ids: set[tuple[str, str]] = set()
    for line_no, row in enumerate(reader, start=2):
        try:
            event = _parse_row(row)
        except (ValueError, ValidationError, KeyError) as exc:
            result.errors.append((line_no, str(exc)))
            continue
        if event.external_id:
            key = (event.provider, event.external_id)
            if key in seen_external_ids:
                result.errors.append((line_no, f"external_id duplicado: {event.external_id}"))
                continue
            seen_external_ids.add(key)
        result.events.append(event)
    return result
