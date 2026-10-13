create or replace view v_daily_cost
with (security_invoker = true) as
select
    (occurred_at at time zone 'UTC')::date as day,
    provider,
    model,
    campaign_id,
    sum(cost_usd)  as cost_usd,
    count(*)       as events
from usage_events
group by 1, 2, 3, 4;

create or replace view v_campaign_month_spend
with (security_invoker = true) as
select
    c.id                                                     as campaign_id,
    c.name,
    c.monthly_budget_usd,
    date_trunc('month', now() at time zone 'UTC')::date      as period_month,
    coalesce(sum(u.cost_usd), 0)                             as spent_usd
from campaigns c
left join usage_events u
    on u.campaign_id = c.id
   and u.occurred_at >= date_trunc('month', now() at time zone 'UTC') at time zone 'UTC'
group by c.id, c.name, c.monthly_budget_usd;

create or replace view v_provider_month_cost
with (security_invoker = true) as
select
    provider,
    date_trunc('month', occurred_at at time zone 'UTC')::date as period_month,
    sum(cost_usd)                                            as recorded_usd
from usage_events
group by 1, 2;
