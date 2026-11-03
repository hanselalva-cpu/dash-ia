-- Pagos registrados a mano (OpenAI, ElevenLabs: sus APIs no exponen historial de pagos) junto a las
-- recargas que llegan solas por API (Deepgram). amount_usd se usa para el cuadre; el monto original queda guardado.
alter table provider_purchases
    add column if not exists source text not null default 'api' check (source in ('api', 'manual')),
    add column if not exists currency text not null default 'USD' check (currency in ('USD', 'MXN')),
    add column if not exists amount_original numeric(14, 4),
    add column if not exists note text;
