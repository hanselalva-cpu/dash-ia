-- RLS activo en todo. El backend usa service_role (salta RLS).
-- Usuarios autenticados de Supabase Auth: solo lectura. Ajustar si se agregan roles por cliente.
alter table campaigns         enable row level security;
alter table api_keys          enable row level security;
alter table rates             enable row level security;
alter table usage_events      enable row level security;
alter table provider_invoices enable row level security;

create policy campaigns_read         on campaigns         for select to authenticated using (true);
create policy rates_read             on rates             for select to authenticated using (true);
create policy usage_events_read      on usage_events      for select to authenticated using (true);
create policy provider_invoices_read on provider_invoices for select to authenticated using (true);
-- api_keys: sin policy para authenticated → solo service_role.
