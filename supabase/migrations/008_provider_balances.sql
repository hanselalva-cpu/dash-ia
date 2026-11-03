-- Saldo prepagado de cada proveedor, capturado en cada sincronización (hoy: Deepgram).
create table provider_balances (
    provider     text not null check (provider in ('openai', 'anthropic', 'deepgram', 'elevenlabs')),
    captured_at  timestamptz not null default now(),
    amount_usd   numeric(14, 4) not null,
    primary key (provider, captured_at)
);

alter table provider_balances enable row level security;
create policy provider_balances_read on provider_balances for select to authenticated using (true);
