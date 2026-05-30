# Web Application

AMRIE-py includes a browser-based UI and REST API built with [NiceGUI](https://nicegui.io/) on top of FastAPI. Both run in a **single Python process** — NiceGUI mounts the UI routes and API endpoints on the same server.

The web layer wraps the existing engine in `src/amrie/`; it imports `amrie` but never modifies engine code. For engine internals, see [`architecture.md`](architecture.md).

---

## Folder structure

```
web/
├── main.py                 Entry point — `ui.run()` on port 8080
├── state.py                Shared read-only lookup tables (import time)
├── helpers.py              Config builders, WHONET code helpers, serializers
├── api/                    FastAPI REST endpoints (registered via NiceGUI `app`)
│   ├── interpret.py        Single + batch interpretation
│   ├── breakpoints.py      Applicable breakpoint query
│   ├── rules.py            Expert + intrinsic rule queries
│   ├── qc.py               QC range evaluation
│   └── reference.py        Organism / antibiotic / filter option lists
├── pages/                  NiceGUI page routes
│   ├── single.py           `/` — single-drug interpretation
│   ├── file_mode.py        `/file` — batch file processing
│   └── qc.py               `/qc` — QC reference strain check
├── components/             Reusable UI pieces
│   ├── header.py           Tab navigation
│   ├── filters.py          Guideline / year / breakpoint-type / site filters
│   ├── breakpoint_dialog.py
│   ├── expert_dialog.py
│   └── intrinsic_dialog.py
└── models/
    ├── requests.py         Pydantic request bodies
    └── responses.py        Pydantic response shapes
```

Side-effect imports in `main.py` register all API routes and page handlers before `ui.run()` starts.

---

## Architecture

### Single-process NiceGUI + FastAPI

NiceGUI embeds a FastAPI application. API modules register routes with `from nicegui import app` and `@app.post(...)` / `@app.get(...)`. The UI uses `@ui.page(...)` decorators for HTML pages served alongside the API.

Interactive OpenAPI docs are enabled (`fastapi_docs=True`) at **`/docs`** when the server is running.

### State model

| Layer | Scope | Contents |
|---|---|---|
| `web/state.py` | Process-wide, read-only | Organism/antibiotic option maps, guideline lists, site-of-infection options — built once from `amrie` reference data at import time |
| `FilterState` (single tab) | Per browser session / page instance | Selected guidelines, year, breakpoint types, sites of infection |
| File mode page locals | Per page instance | Uploaded file bytes, progress, cancel flag |

There is no shared mutable interpretation state between users. Each request builds an `InterpretationConfiguration` (or loads one from JSON) and calls engine functions directly.

### Engine boundary

```
Browser  →  NiceGUI pages / REST API  →  web/helpers.py  →  amrie.*
```

- **Single tab & REST `/api/interpret/single`:** `make_single_tab_config()` builds config from UI/API fields.
- **File mode & REST `/api/interpret/file`:** `read_configuration()` loads a full JSON config file (same format as the CLI).
- **QC tab & REST `/api/qc`:** calls `amrie.qc.get_quality_control_interpretation` directly (no JSON config file).

Blocking engine work runs in `asyncio.to_thread()` so the event loop stays responsive during interpretation.

---

## Installation

```bash
# Web UI + REST API dependencies (NiceGUI, httpx)
pip install -e ".[web]"

# Editable install with both dev tools and web extras
pip install -e ".[dev,web]"
```

The `[web]` optional extra adds `nicegui>=2.0` and `httpx>=0.27`. Core engine dependencies (`pandas`, `typer`, `orjson`) are always installed.

---

## Running the server

### Direct

```bash
python web/main.py
```

### Console script

After `pip install -e ".[web]"`:

```bash
amrie-web
```

Both start the server on **`http://0.0.0.0:8080`**.

| URL | Purpose |
|---|---|
| `/` | Single interpretation tab |
| `/file` | Batch file mode |
| `/qc` | QC evaluation |
| `/docs` | Interactive OpenAPI (Swagger) |
| `/api/*` | REST endpoints |

### Docker

```bash
docker compose up --build
```

Or build and run manually:

```bash
docker build -t amrie-web .
docker run -p 8080:8080 -e STORAGE_SECRET=your-secret amrie-web
```

See [Deployment](#deployment) for production settings.

---

## Web UI usage

### Single interpretation (`/`)

Interpret one organism / antibiotic / measurement combination — equivalent to `amrie single` with UI-driven config.

1. Select **Organism** and **Antibiotic** from searchable dropdowns.
2. Choose **Disk** or **MIC / Etest**. Disk mode requires a **Potency** (options depend on selected antibiotic and active guidelines).
3. Enter the **Measurement** (zone diameter or MIC value).
4. Set **Filters**: active guidelines (CLSI, EUCAST, SFM), guideline year, optional breakpoint-type and site-of-infection restrictions.
5. Click **Get interpretations** to see one result per generated WHONET test code (e.g. `PEN_ND10: S`).

Additional actions (same selections required):

- **Applicable breakpoints** — dialog listing matching breakpoint rows
- **Applicable expert rules** — ESBL, MRS, ICR, BLNAR, etc.
- **Applicable intrinsic rules** — expected resistance phenotype rules

Optional checkboxes control breakpoint filtering for the dialog actions and whether interpretation comment suffixes (`*`, `!`) appear in results.

### File mode (`/file`)

Batch-process a delimited input file — equivalent to `amrie file`.

1. Upload the **input data file**.
2. Select the **delimiter** (pipe, comma, semicolon, or tab).
3. Upload a **configuration JSON** file (required — same schema as CLI `--config`; see [`configuration.md`](configuration.md)).
4. Set the **Guideline year** for breakpoint lookup during the run.
5. Click **Interpret**. Progress is shown in batches of 50 rows; **Cancel** stops between batches.
6. On completion, `interpretations.txt` downloads automatically.

Input/output column conventions match [`data-formats.md`](data-formats.md).

### Quality control (`/qc`)

Evaluate whether a reference-strain measurement falls within the QC acceptable range — equivalent to `amrie qc`.

> **Note:** QC evaluation is a Python-port extension. It is not present in the original C# AMRIE desktop GUI, but uses the bundled `QC_Ranges.txt` data and the same `interpret_qc_single` / `get_quality_control_interpretation` logic as the CLI.

1. Enter **Reference strain** (e.g. `atcc25922`).
2. Enter **Antibiotic** as a full WHONET code (e.g. `SAM_ND10`).
3. Enter the **Measurement**.
4. Click **Evaluate** — result is `IN`, `OUT`, or blank (uninterpretable).

---

## REST API

Full request/response schemas are available at **`http://localhost:8080/docs`** when the server is running.

### Endpoint summary

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/interpret/single` | Interpret one organism/antibiotic/measurement |
| `POST` | `/api/interpret/file` | Batch file interpretation (multipart upload) |
| `POST` | `/api/breakpoints` | Query applicable breakpoints |
| `POST` | `/api/expert-rules` | Query applicable expert interpretation rules |
| `POST` | `/api/intrinsic-rules` | Query applicable intrinsic resistance rules |
| `POST` | `/api/qc` | QC range evaluation |
| `GET` | `/api/organisms` | All organisms (code + name) |
| `GET` | `/api/antibiotics` | All antibiotics (code, name, potencies) |
| `GET` | `/api/guidelines` | Available guideline names |
| `GET` | `/api/breakpoint-types` | Breakpoint type options |
| `GET` | `/api/sites` | Sites of infection options |

### `POST /api/interpret/single`

**Request body** (`SingleInterpretRequest`):

| Field | Type | Default | Description |
|---|---|---|---|
| `organism_code` | string | — | WHONET organism code (e.g. `ent`) |
| `whonet_abx_code` | string | — | Base antibiotic code (e.g. `PEN`) |
| `measurement` | string | — | Zone diameter or MIC value |
| `guidelines` | string[] | `["CLSI"]` | Active guidelines |
| `test_method` | `"disk"` \| `"mic"` | `"disk"` | Test method |
| `potency` | string | `""` | Disk potency (required for disk; e.g. `10units`) |
| `guideline_year` | integer | — | Breakpoint table year |
| `include_comments` | boolean | `false` | Include `*` / `!` suffixes |
| `restrict_breakpoint_types` | boolean | `false` | Limit to `breakpoint_types` |
| `breakpoint_types` | string[] | `[]` | e.g. `["Human"]` |
| `restrict_sites` | boolean | `false` | Limit to `sites_of_infection` |
| `sites_of_infection` | string[] | `[]` | Site filter values |

**Response** (`SingleInterpretResponse`):

```json
{
  "results": [
    { "whonet_test": "PEN_ND10", "interpretation": "S" }
  ]
}
```

**Example** — *Enterococcus* (`ent`), penicillin disk 10 units, measurement 19 mm → susceptible (`S`):

```bash
curl -s -X POST http://localhost:8080/api/interpret/single \
  -H "Content-Type: application/json" \
  -d '{
    "organism_code": "ent",
    "whonet_abx_code": "PEN",
    "measurement": "19",
    "guidelines": ["CLSI"],
    "test_method": "disk",
    "potency": "10units",
    "guideline_year": 2026
  }'
```

### `POST /api/interpret/file`

Multipart form upload:

| Field | Type | Description |
|---|---|---|
| `data_file` | file | Input delimited data file |
| `config_file` | file | Configuration JSON |
| `delimiter` | string | `\|`, `,`, `;`, or `TAB` |
| `guideline_year` | integer | Breakpoint year for the run |

Returns the interpreted output file as `text/tab-separated-values` with `Content-Disposition: attachment; filename=interpretations.txt`.

### `POST /api/qc`

**Request:**

| Field | Type | Default | Description |
|---|---|---|---|
| `strain` | string | — | Reference strain code |
| `antibiotic` | string | — | Full WHONET antibiotic code |
| `measurement` | string | — | Measured value |
| `round_half_dilutions` | boolean | `true` | Round half-dilution MIC values |

**Response:** `{ "result": "IN" }` (or `"OUT"` / `""`).

### `POST /api/breakpoints`, `/api/expert-rules`, `/api/intrinsic-rules`

See field definitions in `web/models/requests.py` and the `/docs` schema. Responses wrap lists of breakpoint or rule dictionaries.

### Reference `GET` endpoints

Return JSON arrays used to populate UI dropdowns programmatically:

- `/api/organisms` → `[{ "code": "ent", "name": "Enterococcus spp." }, ...]`
- `/api/antibiotics` → `[{ "code": "PEN", "name": "Penicillin G", "potencies": ["10units", ...] }, ...]`
- `/api/guidelines`, `/api/breakpoint-types`, `/api/sites` → string arrays

---

## Configuration

The web app uses two configuration paths, matching the CLI modes:

### Single tab — `make_single_tab_config()`

Used by the Single UI tab and `/api/interpret/single`. Builds an `InterpretationConfiguration` in memory from filter controls:

| UI / API field | Config mapping |
|---|---|
| Guideline year | `guideline_year` |
| Include interpretation comments | `include_interpretation_comments` |
| Restrict breakpoint types + selected types | `prioritized_breakpoint_types` (defaults to `["Human"]` when unrestricted) |
| Restrict sites + selected sites | `prioritized_sites_of_infection` (`None` when unrestricted) |
| — | `enabled_expert_interpretation_rules=None` (all rules enabled) |

Guideline selection (CLSI / EUCAST / SFM) affects which WHONET test codes are generated via `build_full_test_codes()`, not the JSON config file.

### File mode — `read_configuration()`

Used by the File UI tab and `/api/interpret/file`. Loads a full JSON config file with the same keys documented in [`configuration.md`](configuration.md) (`GuidelineYear`, `PrioritizedBreakpointTypes`, `EnabledExpertInterpretationRules`, `HorizontalAntibioticResults`, etc.).

Use [`src/amrie/resources/SampleConfig.json`](../src/amrie/resources/SampleConfig.json) as a starting point.

### QC

No configuration file. QC uses bundled `QC_Ranges.txt` data directly.

---

## Deployment

### Dockerfile

The included `Dockerfile`:

1. Uses `python:3.11-slim`
2. Copies `pyproject.toml`, `src/`, and `web/`
3. Runs `pip install -e ".[web]"`
4. Exposes port **8080**
5. Starts with `python web/main.py`

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `STORAGE_SECRET` | `amrie-dev-secret` | NiceGUI session storage signing key — **set a strong random value in production** |

Example `docker-compose.yml`:

```yaml
services:
  amrie-web:
    build: .
    ports:
      - "8080:8080"
    environment:
      - STORAGE_SECRET=change-me-in-production
    restart: unless-stopped
```

### Production notes

- Place a reverse proxy (nginx, Caddy, etc.) in front of the container for TLS termination.
- The server binds to `0.0.0.0:8080` inside the container.
- Engine reference data is bundled in the package; no external database is required.
- For high-volume batch API use, consider the CLI (`amrie file`) or Python API (`interpret_file`) to avoid HTTP upload overhead.

---

## Related documentation

| Document | Contents |
|---|---|
| [`configuration.md`](configuration.md) | JSON config file reference (file mode) |
| [`data-formats.md`](data-formats.md) | Input/output file column conventions |
| [`cli-reference.md`](cli-reference.md) | Equivalent CLI commands |
| [`architecture.md`](architecture.md) | Engine module structure and data flow |
| [`use-cases.md`](use-cases.md) | Python API examples |

Implementation plan (developer reference, not user guide): [`ui-plan.md`](../ui-plan.md).
