-- Facturas abiertas (sin pagar) que reporta cada proveedor, reemplazadas en cada sincronización (hoy: ElevenLabs).
-- La API de ElevenLabs no da id ni fecha de factura: se identifican por proveedor + posición + monto.
create table provider_open_invoices (
    provider        text not null check (provider in ('openai', 'anthropic', 'deepgram', 'elevenlabs')),
    invoice_key     text not null,
    amount_usd      numeric(14, 2) not null,
    payment_status  text,          -- estado del cobro según el proveedor (p. ej. requires_confirmation)
    account_status  text,          -- estado de la suscripción (p. ej. past_due)
    captured_at     timestamptz not null default now(),
    paid_order_id   text,          -- pago manual en provider_purchases con que se marcó como pagada
    primary key (provider, invoice_key)
);

alter table provider_open_invoices enable row level security;
create policy provider_open_invoices_read on provider_open_invoices for select to authenticated using (true);
