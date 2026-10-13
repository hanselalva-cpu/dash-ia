-- Catálogo de alertas: tope mensual de gasto por campaña.
-- El tope se guarda en la moneda en que se captura (USD o MXN); el gasto está en USD y se convierte al comparar.
create table budget_alerts (
    campaign_id   uuid primary key references campaigns (id) on delete cascade,
    limit_amount  numeric(14, 2) not null check (limit_amount > 0),
    currency      text not null default 'USD' check (currency in ('USD', 'MXN')),
    warning_pct   numeric(4, 3) not null default 0.8 check (warning_pct > 0 and warning_pct < 1),
    active        boolean not null default true,
    updated_at    timestamptz not null default now()
);

alter table budget_alerts enable row level security;
create policy budget_alerts_read on budget_alerts for select to authenticated using (true);

-- Migrar presupuestos existentes de campaigns (columna queda por compatibilidad, la app ya no la usa).
insert into budget_alerts (campaign_id, limit_amount, currency)
select id, monthly_budget_usd, 'USD' from campaigns where monthly_budget_usd > 0
on conflict do nothing;
