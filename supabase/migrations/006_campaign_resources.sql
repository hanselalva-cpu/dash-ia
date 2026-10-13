-- Catálogo de recursos de proveedores (API keys de OpenAI/Deepgram, agentes de ElevenLabs)
-- y su asignación a campañas. Un recurso pertenece a una sola campaña (o a ninguna).
-- El costo se atribuye al leer: evento → recurso (resource_key) → campaign_id. Reasignar es retroactivo.
create table provider_resources (
    id              uuid primary key default gen_random_uuid(),
    provider        text not null check (provider in ('openai', 'anthropic', 'deepgram', 'elevenlabs')),
    kind            text not null check (kind in ('api_key', 'agent')),
    -- Clave con la que se cruza contra usage_events.metadata:
    --   openai → openai_api_key_id · deepgram → deepgram_api_key_id · elevenlabs → agent_name
    resource_key    text not null,
    name            text not null,
    provider_ref    text,          -- id del proveedor si difiere de resource_key (ej. agent_id de ElevenLabs)
    group_name      text,          -- proyecto de OpenAI / proyecto de Deepgram
    campaign_id     uuid references campaigns (id) on delete set null,
    active          boolean not null default true,
    last_synced_at  timestamptz not null default now(),
    created_at      timestamptz not null default now(),
    unique (provider, resource_key)
);

create index provider_resources_campaign_idx on provider_resources (campaign_id);

alter table provider_resources enable row level security;
create policy provider_resources_read on provider_resources for select to authenticated using (true);
