-- Recargas (compras de saldo prepagado) de cada proveedor, tal como las reporta su API (hoy: Deepgram).
create table provider_purchases (
    provider    text not null check (provider in ('openai', 'anthropic', 'deepgram', 'elevenlabs')),
    order_id    text not null,
    created_at  timestamptz not null,
    amount_usd  numeric(14, 4) not null,
    order_type  text,
    primary key (provider, order_id)
);

create index provider_purchases_created_idx on provider_purchases (provider, created_at);

alter table provider_purchases enable row level security;
create policy provider_purchases_read on provider_purchases for select to authenticated using (true);
