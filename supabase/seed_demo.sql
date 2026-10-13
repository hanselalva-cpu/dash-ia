-- Datos demo. Precios ILUSTRATIVOS: verificar con cada proveedor antes de usar en producción.
insert into campaigns (id, name, client, monthly_budget_usd) values
    ('11111111-1111-1111-1111-111111111111', 'Cobranza Q4', 'Banco Demo', 150),
    ('22222222-2222-2222-2222-222222222222', 'Soporte Voz', 'Telco Demo', 40)
on conflict do nothing;

insert into rates (provider, model, unit, price_usd, per_units, effective_from) values
    ('openai',     'gpt-4o-mini',      'input_tokens',  0.15,   1000000, '2026-01-01'),
    ('openai',     'gpt-4o-mini',      'output_tokens', 0.60,   1000000, '2026-01-01'),
    ('anthropic',  'claude-haiku-5-5', 'input_tokens',  1.00,   1000000, '2026-01-01'),
    ('anthropic',  'claude-haiku-5-5', 'output_tokens', 5.00,   1000000, '2026-01-01'),
    ('deepgram',   '*',                'audio_seconds', 0.0043, 60,      '2026-01-01'),
    ('elevenlabs', '*',                'characters',    0.30,   1000,    '2026-01-01')
on conflict do nothing;
