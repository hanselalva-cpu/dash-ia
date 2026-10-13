from decimal import Decimal

from models.schemas import Provider
from services.reconciliation_service import ReconciliationStatus, reconcile


def by_provider(lines):
    return {line.provider: line for line in lines}


def test_within_tolerance_matches():
    lines = by_provider(reconcile({Provider.OPENAI: Decimal(100)}, {Provider.OPENAI: Decimal("101.5")}))
    assert lines[Provider.OPENAI].status == ReconciliationStatus.MATCH
    assert lines[Provider.OPENAI].diff_usd == Decimal("1.5")


def test_over_tolerance_mismatch():
    lines = by_provider(reconcile({Provider.OPENAI: Decimal(100)}, {Provider.OPENAI: Decimal(110)}))
    assert lines[Provider.OPENAI].status == ReconciliationStatus.MISMATCH
    assert lines[Provider.OPENAI].diff_pct == Decimal("0.1")


def test_missing_invoice_and_missing_usage():
    lines = by_provider(reconcile({Provider.DEEPGRAM: Decimal(5)}, {Provider.ELEVENLABS: Decimal(3)}))
    assert lines[Provider.DEEPGRAM].status == ReconciliationStatus.MISSING_INVOICE
    assert lines[Provider.ELEVENLABS].status == ReconciliationStatus.MISSING_USAGE


def test_both_zero_match():
    lines = reconcile({Provider.OPENAI: Decimal(0)}, {Provider.OPENAI: Decimal(0)})
    assert lines[0].status == ReconciliationStatus.MATCH
