create extension if not exists pgcrypto;

create table campaigns (
    id                  uuid primary key default gen_random_uuid(),
    name                text not null unique,
    client              text,
    monthly_budget_usd  numeric(14, 4) check (monthly_budget_usd is null or monthly_budget_usd >= 0),
    status              text not null default 'active' check (status in ('active', 'paused', 'archived')),
    created_at          timestamptz not null default now()
);

-- Nunca se guarda la key en claro: solo hash (identificación) y pista (últimos 4).
create table api_keys (
    id                   uuid primary key default gen_random_uuid(),
    provider             text not null check (provider in ('openai', 'anthropic', 'deepgram', 'elevenlabs')),
    label                text not null,
    key_hint             text not null,
    key_hash             text not null unique,
    default_campaign_id  uuid references campaigns (id) on delete set null,
    active               boolean not null default true,
    created_at           timestamptz not null default now()
);

-- price_usd por cada per_units unidades. model = '*' aplica a todo el proveedor. effective_to exclusivo.
create table rates (
    id              uuid primary key default gen_random_uuid(),
    provider        text not null check (provider in ('openai', 'anthropic', 'deepgram', 'elevenlabs')),
    model           text not null,
    unit            text not null check (unit in ('input_tokens', 'output_tokens', 'cached_input_tokens',
                                                  'cache_write_tokens', 'audio_seconds', 'characters', 'requests')),
    price_usd       numeric(18, 8) not null check (price_usd >= 0),
    per_units       integer not null default 1 check (per_units > 0),
    effective_from  date not null,
    effective_to    date,
    created_at      timestamptz not null default now(),
    check (effective_to is null or effective_to > effective_from),
    unique (provider, model, unit, effective_from)
);

create table usage_events (
    id           uuid primary key default gen_random_uuid(),
    occurred_at  timestamptz not null,
    provider     text not null check (provider in ('openai', 'anthropic', 'deepgram', 'elevenlabs')),
    model        text not null,
    quantities   jsonb not null default '{}'::jsonb,
    cost_usd     numeric(18, 8) not null default 0,
    campaign_id  uuid references campaigns (id) on delete set null,
    api_key_id   uuid references api_keys (id) on delete set null,
    source       text not null default 'sdk' check (source in ('sdk', 'import')),
    external_id  text,
    metadata     jsonb not null default '{}'::jsonb,
    created_at   timestamptz not null default now(),
    -- Idempotencia de importaciones. NULLs no chocan entre sí.
    unique (provider, external_id)
);

create table provider_invoices (
    id            uuid primary key default gen_random_uuid(),
    provider      text not null check (provider in ('openai', 'anthropic', 'deepgram', 'elevenlabs')),
    period_month  date not null check (extract(day from period_month) = 1),
    amount_usd    numeric(14, 4) not null,
    notes         text,
    created_at    timestamptz not null default now(),
    unique (provider, period_month)
);
