from decimal import Decimal

from models.schemas import Provider, UsageSource, UsageUnit
from services.import_service import parse_usage_csv

HEADER = "occurred_at,provider,model,campaign_id,input_tokens,output_tokens,audio_seconds,external_id\n"


def test_valid_row():
    r = parse_usage_csv(HEADER + "2026-10-01T10:00:00,OpenAI,gpt-4o-mini,,100,20,,req1\n")
    assert r.ok
    e = r.events[0]
    assert e.provider == Provider.OPENAI
    assert e.quantities == {UsageUnit.INPUT_TOKENS: Decimal(100), UsageUnit.OUTPUT_TOKENS: Decimal(20)}
    assert e.occurred_at.tzinfo is not None
    assert e.source == UsageSource.IMPORT


def test_missing_columns():
    r = parse_usage_csv("provider,model\nopenai,x\n")
    assert r.errors == [(1, "faltan columnas: occurred_at")]


def test_row_errors_do_not_stop_import():
    csv = HEADER + (
        "2026-10-01T10:00:00,openai,m,,abc,,,\n"      # número inválido
        "2026-10-01T10:00:00,mistral,m,,1,,,\n"       # proveedor desconocido
        "2026-10-01T10:00:00,openai,m,,,,,\n"         # sin cantidades
        "2026-10-01T10:00:00,deepgram,nova-3,,,,30,\n"  # válida
    )
    r = parse_usage_csv(csv)
    assert [row for row, _ in r.errors] == [2, 3, 4]
    assert len(r.events) == 1


def test_negative_quantity_rejected():
    r = parse_usage_csv(HEADER + "2026-10-01T10:00:00,openai,m,,-5,,,\n")
    assert not r.events and "negativo" in r.errors[0][1]


def test_duplicate_external_id_in_file():
    row = "2026-10-01T10:00:00,openai,m,,1,,,dup\n"
    r = parse_usage_csv(HEADER + row + row)
    assert len(r.events) == 1 and r.errors[0][0] == 3


def test_bom_tolerated():
    r = parse_usage_csv("﻿" + HEADER + "2026-10-01T10:00:00,openai,m,,1,,,\n")
    assert r.ok
