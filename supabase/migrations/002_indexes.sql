create index usage_events_occurred_at_idx on usage_events (occurred_at);
create index usage_events_campaign_occurred_idx on usage_events (campaign_id, occurred_at);
create index usage_events_provider_occurred_idx on usage_events (provider, occurred_at);
create index usage_events_api_key_idx on usage_events (api_key_id);
create index rates_lookup_idx on rates (provider, unit, model, effective_from desc);
