# Dash IA

Dashboard de costos de APIs de IA (OpenAI, Anthropic, Deepgram, ElevenLabs) por campaña, con presupuestos,
importación CSV y conciliación contra facturas. Streamlit + Supabase.

## Arranque rápido

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Sin `.env` corre en **modo demo** (lee `examples/usage_demo.csv`, solo lectura).

## Conectar Supabase

1. Copiar `.env.example` → `.env`, completar `SUPABASE_URL` y `SUPABASE_KEY` (service role, solo server-side).
2. Ejecutar en el SQL editor, en orden: `supabase/migrations/001..004`, luego `supabase/seed_demo.sql` (opcional).
3. Cargar tarifas reales en `rates` (los precios del seed son ilustrativos).

## Registrar consumo desde tus apps

```python
from integrations import anthropic_adapter
from integrations.usage_recorder import UsageRecorder
from repositories import get_repositories

repos = get_repositories()
recorder = UsageRecorder(repos.usage, repos.rates, repos.api_keys)
recorder.record("anthropic", "claude-haiku-5-5",
                anthropic_adapter.quantities_from_response(response),
                campaign_id=..., external_id=response.id)
```

Ver `examples/record_usage_example.py`.

## Conceptos

- **Tarifa**: `price_usd` por `per_units` unidades, vigente `[effective_from, effective_to)`. `model='*'` = comodín.
- **Atribución**: campaña explícita del evento > campaña por defecto de la API key > sin campaña.
- **Tarifa faltante**: el evento se guarda igual, con costo parcial y `metadata.missing_rates`.
- **Idempotencia**: `(provider, external_id)` único; reimportar un CSV no duplica.

## Estructura

| Carpeta | Rol |
|---|---|
| `pages/` | UI Streamlit (navegación en `app.py`) |
| `services/` | Lógica pura: precios, presupuestos, import, conciliación |
| `repositories/` | Acceso a Supabase + variantes demo |
| `integrations/` | `UsageRecorder` + adapters que extraen uso de respuestas SDK |
| `supabase/` | Migraciones SQL y seed |

## Tests

```powershell
pytest
```

## Pendiente

- Página de conciliación (servicio listo en `services/reconciliation_service.py`, falta UI + tabla `provider_invoices`).
- Login por usuario dentro de la app (hoy: lista de correos de Streamlit Cloud + `APP_PASSWORD` opcional).

## Publicar en Streamlit Community Cloud

Arquitectura: el **dashboard** corre en Streamlit Cloud y solo lee/escribe Supabase. La **sincronización**
(keys de admin de OpenAI, Deepgram y ElevenLabs) sigue en la PC con la tarea programada `DashIA - Sync costos`,
así esas keys nunca salen de la máquina.

1. Subir este repo a GitHub como **privado** (`.env`, `logs/` y `.venv/` están en `.gitignore`).
2. En https://share.streamlit.io → *Create app* → elegir el repo, rama `main`, archivo `app.py`,
   Python 3.12.
3. *Advanced settings → Secrets*: pegar `.streamlit/secrets.example.toml` con los valores reales de Supabase.
4. Deploy. Luego *Share* → agregar los correos de las personas que pueden verlo (entran con Google o GitHub).
   La app de un repo privado es privada por defecto: sin invitación no se puede abrir.

Si cambia el tipo de cambio, editar `USD_MXN_RATE` en Secrets (la app se reinicia sola).
