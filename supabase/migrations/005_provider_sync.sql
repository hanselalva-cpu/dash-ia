-- Eventos descargados de la API del proveedor (costo reportado por el proveedor, no calculado con `rates`).
alter table usage_events drop constraint if exists usage_events_source_check;
alter table usage_events add constraint usage_events_source_check
    check (source in ('sdk', 'import', 'provider_sync'));

-- Reportes por agente (ElevenLabs) y por API key (OpenAI).
create index if not exists usage_events_agent_idx on usage_events ((metadata ->> 'agent_name'))
    where provider = 'elevenlabs';
create index if not exists usage_events_key_name_idx on usage_events ((metadata ->> 'key_name'))
    where provider = 'openai';
