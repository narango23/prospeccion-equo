# Prospección Équo

Script local en Python que enriquece prospectos desde un Google Sheet, busca contexto en LinkedIn + web + noticias, y redacta un correo personalizado en nombre de Lina González (CEO de Équo) usando Claude.

## Flujo

```
Google Sheet (leads)
    ├── LinkedIn URL ──► RapidAPI (perfil + posts últimos 6 meses)
    ├── Company Website ──► Firecrawl (resumen)
    ├── Company Name ──► Claude web_search (noticias recientes)
    └─► Claude (Opus 4.7) con prompt de Lina/Équo
              └─► Email Subject + Email Body + Fecha Procesado + Status
```

## Setup (una sola vez)

### 1. Service account de Google

Ya tienes uno: `claude-code-equo@n8n-gmail-489402.iam.gserviceaccount.com`.

- Descarga el JSON desde Google Cloud Console → IAM → Cuentas de servicio → Claves
- Guárdalo en la raíz del proyecto como `service_account.json`
- Asegúrate de haber compartido la hoja con ese email (permiso **Editor**)

### 2. Variables de entorno

```bash
cp .env.example .env
```

Edita `.env` y rellena:
- `ANTHROPIC_API_KEY` → de [console.anthropic.com](https://console.anthropic.com/settings/keys)
- El resto ya está prerellenado con las claves del flujo de n8n (rótalas si las quieres seguras)

### 3. Entorno de Python

```powershell
cd C:\Users\nicol\prospeccion-equo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Ejecución

```powershell
python main.py
```

Procesa 20 leads pendientes (filas con `Email Body` vacío) por corrida. Para cambiar el batch, edita `BATCH_SIZE` en `.env`.

## Output en la hoja

Por cada lead procesado se llenan 4 columnas:

| Columna | Contenido |
|---|---|
| **Email Subject** | Subject line personalizado |
| **Email Body** | Cuerpo completo del correo + nota de approach al final |
| **Fecha Procesado** | Timestamp `YYYY-MM-DD HH:MM:SS` |
| **Status** | `ok` / `no_info` / `incompleto` / `exception` + breve diagnóstico de cada paso |

Ejemplos de Status:
- `ok | linkedin:ok(posts=4) / firecrawl:ok / news:ok` → todo bien
- `no_info | linkedin:vacio / firecrawl:ok / news:vacio` → Claude no tuvo info para personalizar
- `ok | linkedin:fail(403) / firecrawl:ok / news:ok` → se generó correo aunque LinkedIn falló

## Costos estimados (Claude Opus 4.7 con prompt caching)

- Por lead: ~5-8K tokens de input (mucho viene de cache) + ~600 output
- Aprox. **$0.05-0.08 USD por correo** (más barato si usas Sonnet 4.6)
- 20 leads ≈ $1-1.60 USD por corrida

Para cambiar a Sonnet 4.6, edita `CLAUDE_MODEL=claude-sonnet-4-6` en `.env`.

## Estructura

```
prospeccion-equo/
├── main.py                  # Orquestador
├── config.py                # Carga de .env
├── sheets_client.py         # Lectura/escritura de Google Sheets
├── linkedin_scraper.py      # RapidAPI
├── firecrawl_scraper.py     # Firecrawl
├── claude_client.py         # Claude para noticias + correo
├── prompts.py               # Prompt de Lina/Équo (sistema cacheado)
├── requirements.txt
├── .env.example             # plantilla — copia a .env
├── service_account.json     # gitignored — debes ponerlo tú
└── README.md
```

## Próximos pasos sugeridos

1. **Validar 5-10 correos** en la hoja, ajustar el prompt si hace falta
2. Cuando estés conforme, agregar nodo de **Gmail draft** (otra columna `gmail_draft_id`)
3. Más adelante: agregar columna `enviado` y un script que envíe + agende seguimiento
