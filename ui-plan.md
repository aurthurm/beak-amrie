Plan: AMRIE Web UI — NiceGUI + REST API

 Context

 The existing Python AMRIE engine (src/amrie/) is a complete, tested port of the C#
 interpretation engine. The C# project also ships a Windows Forms GUI that exposes four
 interactive capabilities: single-drug interpretation, batch file mode, breakpoint inspection,
 and intrinsic/expert rule inspection. This plan adds a NiceGUI web application that ports
 those four capabilities as a browser-accessible server tool, served from the same Python
 process as a set of FastAPI REST endpoints — all via NiceGUI's internal FastAPI app
 object. The engine is not touched.

 ---
 Folder Structure

 Add web/ at the project root — sibling to src/ and tests/. The engine is only ever
 imported; no engine file is edited.

 AMRIE-py/
 ├── src/amrie/              ← engine — UNTOUCHED
 ├── tests/                  ← existing tests — UNTOUCHED
 ├── docs/                   ← existing docs
 │
 ├── web/                    ← NEW — entire web application
 │   ├── __init__.py         ← makes `web` an importable package (needed for `import web`)
 │   ├── main.py             ← ui.run() entry point; imports pages + api to register routes
 │   ├── state.py            ← module-level shared READ-ONLY lookup tables built at startup
 │   ├── helpers.py          ← build_whonet_code(), get_potency_options(), make_single_tab_config(), generate_output_str(), dataclass→dict helpers
 │   │
 │   ├── models/             ← Pydantic request/response models
 │   │   ├── __init__.py
 │   │   ├── requests.py     ← SingleInterpretRequest, BreakpointQueryRequest, ExpertRulesRequest, IntrinsicRulesRequest, QCRequest
 │   │   └── responses.py    ← SingleInterpretResponse, BreakpointResponse, RuleResponse, QCResponse, OrganismItem, AntibioticItem
 │   │
 │   ├── api/                ← FastAPI REST routes on nicegui.app
 │   │   ├── __init__.py
 │   │   ├── interpret.py    ← POST /api/interpret/single, POST /api/interpret/file
 │   │   ├── breakpoints.py  ← POST /api/breakpoints
 │   │   ├── rules.py        ← POST /api/expert-rules, POST /api/intrinsic-rules
 │   │   ├── qc.py           ← POST /api/qc
 │   │   └── reference.py    ← GET  /api/organisms, /api/antibiotics, /api/guidelines
 │   │
 │   ├── pages/              ← @ui.page handlers (one file per tab/major view)
 │   │   ├── __init__.py
 │   │   ├── single.py       ← /  — single interpretation + three resource popups
 │   │   ├── file_mode.py    ← /file — batch file upload → interpret → download
 │   │   └── qc.py           ← /qc  — QC reference strain evaluation
 │   │
 │   └── components/         ← reusable @ui.refreshable functions and dialog classes
 │       ├── __init__.py
 │       ├── header.py       ← shared header with tab navigation
 │       ├── filters.py      ← guidelines checklist, year spinner, bp types, sites
 │       ├── breakpoint_dialog.py   ← ui.dialog() + ui.table() for breakpoints
 │       ├── expert_dialog.py       ← ui.dialog() + ui.table() for expert rules
 │       └── intrinsic_dialog.py    ← ui.dialog() + ui.table() for intrinsic rules
 │
 ├── Dockerfile              ← NEW
 ├── docker-compose.yml      ← NEW
 └── pyproject.toml          ← declare web package + optional [web] extra (nicegui, httpx)

 ---
 pyproject.toml changes

 The project is library-first and uses a src-layout: setuptools discovers packages with
 `where = ["src"]`, so the new top-level web/ package is NOT auto-discovered. Two
 consequences:

 - Do NOT add nicegui / httpx to [project].dependencies. Keep them in an optional extra
 ONLY (the engine library must stay dependency-light). httpx is currently unused — it is
 listed for possible future integrations only. Avoid the earlier redundancy of listing the
 same deps in both [project].dependencies and the [web] extra.

 Add optional group:
 [project.optional-dependencies]
 web = ["nicegui>=2.0", "httpx>=0.27"]

 Entry point — the `amrie-web = "web.main:start"` console script will NOT work unless web is
 declared as a package, because src-layout discovery never sees a top-level web/. Pick ONE:
 - Recommended: declare web (and web.api, web.pages, web.components, web.models) as explicit
 packages in setuptools (e.g. extend the discovered packages / package-dir) so the script
 resolves, then keep:
 [project.scripts]
 amrie-web = "web.main:start"
 - Or: drop [project.scripts] entirely and run `python web/main.py` with the project root on
 PYTHONPATH.

 ---
 Key design decisions

 1. Session isolation (multi-user)

 Per the nicegui-llms.txt: module-level variables are shared across all users.

 - Shared (OK, read-only): ORGANISM_OPTIONS, ANTIBIOTIC_OPTIONS,
 GUIDELINE_OPTIONS, BREAKPOINT_TYPES, SITES_OF_INFECTION — pre-built in
 web/state.py at import time from the engine's constants. These never mutate.
 - Per-user: All selection state lives as local variables inside @ui.page,
 bound to UI elements via NiceGUI's binding system. No app.storage needed for the
 interactive state — local variables suffice because the page is rebuilt per visitor.
 - Engine caches (_breakpoint_cache, _intrinsic_cache in antibiotic_rules.py)
 are already thread-safe via threading.Lock; shared across users is intentional and
 beneficial (cache warms up for all).

 2. Never block the event loop

 All engine calls that take > a few ms run in a thread:
 # For batch file interpretation:
 result = await asyncio.to_thread(interpret_isolates, config, columns, rows)

 # For preheat:
 await asyncio.to_thread(preheat_breakpoint_cache, ...)

 Single-drug calls (interpret_single) are fast enough to run inline.

 Use background_tasks.create() — not asyncio.create_task() — for any fire-and-forget.

 3. FastAPI routes live on the NiceGUI app object

 from nicegui import app, ui

 @app.post('/api/interpret/single')
 async def api_single(req: SingleInterpretRequest) -> SingleInterpretResponse:
     ...
 /docs enabled via ui.run(fastapi_docs=True) (verify against the installed NiceGUI
 version). Same process, same port, no mounting.

 4. File mode flow (no temp files written to server disk)

 1. ui.upload() receives bytes in memory via e.content.read()
 2. Write to tempfile.NamedTemporaryFile (auto-deleted) for the engine's file-path API
 3. Config is a REQUIRED external JSON upload, parsed via read_configuration — it is NOT
 built from the single-tab filter controls. A guideline_year field is also REQUIRED on the
 page (C# requires YearCheckbox + passes GuidelineYearUpDown into the batch).
 4. Run interpretation in thread: results = await asyncio.to_thread(interpret_isolates, ...)
 5. generate_output_str() (temp-file wrapper) returns the TSV — output is ALWAYS
 tab-delimited regardless of the input delimiter.
 6. ui.download(output.encode(), 'interpretations.txt') sends the file to the browser
 (verify ui.download(bytes, filename) against the installed NiceGUI version)
 7. Progress: a ui.linear_progress bound to a local counter updated from within the thread
 via loop.call_soon_threadsafe and polled by a ui.timer.
 8. Cancel = REAL cooperative cancellation: a flag checked between row batches INSIDE the
 asyncio.to_thread work — not merely disabling a button. C# uses a BackgroundWorker
 (WorkerSupportsCancellation) and checks CancellationPending during load, parallel
 interpret, and write. The Python interpret_isolates has NO cancel token, so cooperative
 cancellation requires chunking the rows yourself; do not claim mid-batch cancel if only
 the button is disabled.
 9. Optionally call preheat_breakpoint_cache for performance (interpret_isolates already
 preheats internally).

 5. Popup tables (three modal dialogs)

 Each is a reusable class inheriting ui.dialog (verify ui.dialog subclassing against the
 installed NiceGUI version):
 class BreakpointDialog(ui.dialog):
     def __init__(self, breakpoints: list[Breakpoint]):
         super().__init__()
         with self, ui.card().classes('w-full max-w-6xl'):
             ui.label(f'Matching breakpoints: {len(breakpoints)}').classes('text-h6')
             columns = [{'name': f, 'label': f, 'field': f} for f in BP_DISPLAY_FIELDS]
             rows = [bp_to_dict(bp) for bp in breakpoints]
             ui.table(columns=columns, rows=rows).classes('w-full') \
                 .props('flat bordered dense')
             ui.button('Close', on_click=self.close)

 6. Searchable dropdowns for 2978 organisms / 565 antibiotics

 ui.select(options, with_input=True) handles client-side filtering natively (verify
 with_input against the installed NiceGUI version). Pre-build option dicts as module-level
 constants in web/state.py. This is intentional shared state — it never mutates. The
 organism options are sourced from ALL_ORGANISMS (matching the C# combo, which binds to
 Organism.AllOrganisms). The C# GUI also has a dedicated search box — see C# parity gaps.

 7. Potency auto-population (port of AntibioticChanged + DiskContentComboBox)

 Implemented in web/helpers.py:
 def get_potency_options(drug_code: str, guidelines: list[str]) -> list[str]:
     return list(dict.fromkeys(
         a.POTENCY for a in ALL_ANTIBIOTICS
         if a.WHONET_ABX_CODE == drug_code
         and any((g == 'CLSI' and a.CLSI) or (g == 'EUCAST' and a.EUCAST)
                 or (g == 'SFM' and a.SFM) for g in guidelines)
     ))
 Called whenever antibiotic selection or guidelines checklist changes. Result sets options
 on the potency ui.select via .set_options(). The antibiotic select binds to the 3-letter
 WHONET_ABX_CODE (value); the full test code is only built at action time via
 build_whonet_code. Disk is the default test method; the potency select is disabled unless
 Disk is selected. MIC and Etest share one MIC path (radio labelled 'MIC / Etest').

 8. WHONET code builder (port of Create_FullTestCode)

 Implemented in web/helpers.py:
 import re
 _COMBO_RE = re.compile(r'/.+$')

 def build_whonet_code(guideline: str, drug_code: str, disk: bool, potency: str = '') -> str | None:
     code = {'CLSI': 'N', 'EUCAST': 'E', 'SFM': 'F'}.get(guideline)
     if not code:
         return None
     if disk:
         p = _COMBO_RE.sub('', potency.replace('µg','').replace('units','').replace('.','_'))
         if p == '1_25': p = '1_2'
         return f'{drug_code}_{code}D{p}'
     return f'{drug_code}_{code}M'

 9. Single-tab configuration built fresh from the UI (port of GetInerpretationsButton_Click)

 The real engine signature is interpret_single(config, organism, antibiotic, measurement)
 -> str (returns a plain string like 'S' / 'R' / 'R*' / ''). It REQUIRES a full
 InterpretationConfiguration; there is no guideline_year parameter on the function — the
 year lives on the config (InterpretationConfiguration.guideline_year).

 The single tab does NOT load a default config or JSON. On every run it builds an
 InterpretationConfiguration from the UI controls (mirroring C#):
 def make_single_tab_config(*, guideline_year, include_comments,
                            restrict_breakpoint_types, breakpoint_types,
                            restrict_sites, sites_of_infection) -> InterpretationConfiguration:
     return InterpretationConfiguration(
         include_interpretation_comments=include_comments,        # from a checkbox
         enabled_expert_interpretation_rules=None,                # None = all rules
         guideline_year=guideline_year,                           # mandatory (year control)
         prioritized_breakpoint_types=(breakpoint_types if restrict_breakpoint_types
                                       else ['Human']),           # default Human
         prioritized_sites_of_infection=(sites_of_infection if restrict_sites else None),
     )

 Guidelines are NOT stored on the config — they are encoded into full WHONET test codes via
 build_whonet_code (port of Create_FullTestCode). Never pass a bare 3-letter abx code or a
 lone guideline_year to interpret_single. make_default_config() is retained only for
 file-mode / JSON docs.

 ---
 Files to create (implementation order)

 Phase 1 — Foundation

 1. web/state.py — Pre-build ORGANISM_OPTIONS (from ALL_ORGANISMS — 2978 entries, matching
 the C# combo which binds to Organism.AllOrganisms), ANTIBIOTIC_OPTIONS, GUIDELINE_OPTIONS,
 BREAKPOINT_TYPE_OPTIONS, SITES_OPTIONS from engine constants. Organism / antibiotic option
 label = '{name} - ({code})', value = WHONET code. Sites come from
 SitesOfInfection.DEFAULT_ORDER (includes a blank site entry). Also imports
 InterpretationConfiguration.
 2. web/helpers.py — build_whonet_code(), get_potency_options(),
 breakpoint_to_dict(), expert_rule_to_dict(), intrinsic_rule_to_dict(),
 make_single_tab_config() (builds the single-tab config fresh from UI controls — see design
 decision 9), generate_output_str() (temp-file wrapper around generate_output_file), and
 make_default_config() (retained for file-mode / JSON docs only).
 3. web/models/requests.py — Pydantic request models. Note the breakpoint / expert /
 intrinsic requests differ (mirroring C#):
   - SingleInterpretRequest: organism_code, whonet_abx_code (3-letter), measurement,
 guidelines[], test_method ('disk'|'mic'), potency (required for disk), guideline_year,
 include_comments, restrict_breakpoint_types + breakpoint_types[], restrict_sites +
 sites_of_infection[]. (The full WHONET test code is built server-side via build_whonet_code
 — one per selected guideline.)
   - BreakpointQueryRequest: organism_code, user_defined_breakpoints (usually []), and
 nullable filters gated by "Restrict …" toggles: prioritized_guidelines,
 prioritized_guideline_years, prioritized_breakpoint_types, prioritized_sites_of_infection,
 prioritized_whonet_abx_full_drug_codes (full test codes from build_whonet_code, one per
 checked guideline). An unchecked restrict toggle => that arg is None (no filter).
   - ExpertRulesRequest: organism_code + full_test_codes[] (server splits into
 antimicrobial_codes vs other_tests, same logic as C#). enabled_expert_interpretation_rules
 is set to ALL expert rule codes (C# RuleCodes.All) — not None, not from JSON.
   - IntrinsicRulesRequest: organism_code + optional guidelines[] ONLY when "Restrict
 guidelines" is on. No year / types / sites / drug list.
   - BatchInterpretRequest (file mode): handled as a multipart upload (data file + config
 JSON) + guideline_year, not an inline-JSON body.
   - QCRequest: strain, antibiotic code, measurement.
 4. web/models/responses.py — Pydantic: SingleInterpretResponse (an ARRAY — one entry per
 guideline, e.g. {"results": [{"whonet_test": "PEN_ND10", "interpretation": "S"}, ...]}),
 BreakpointResponse, RuleResponse, QCResponse, OrganismItem, AntibioticItem.

 Phase 2 — REST API

 5. web/api/reference.py — GET /api/organisms, GET /api/antibiotics,
 GET /api/guidelines, GET /api/breakpoint-types, GET /api/sites.
 Returns pre-built lists from state.py.
 6. web/api/interpret.py — POST /api/interpret/single builds a full config via
 make_single_tab_config and one full WHONET test code per guideline via build_whonet_code,
 then calls interpret_single ONCE per code, returning an array of {whonet_test,
 interpretation}. POST /api/interpret/file (multipart upload → thread → returns TSV as
 StreamingResponse; output always tab-delimited).
 7. web/api/breakpoints.py — POST /api/breakpoints calls get_applicable_breakpoints() with
 organism_code, user_defined_breakpoints, and the nullable Restrict-gated filters
 (prioritized_guidelines / _guideline_years / _breakpoint_types / _sites_of_infection /
 _whonet_abx_full_drug_codes). An unchecked restrict toggle => None.
 8. web/api/rules.py — POST /api/expert-rules calls get_applicable_expert_rules() with
 organism_code, antimicrobial_codes vs other_tests (split from full_test_codes[]), and
 enabled_expert_interpretation_rules = ALL expert rule codes (RuleCodes.All). POST
 /api/intrinsic-rules calls get_applicable_expected_resistance_rules() with organism_code
 and optional guidelines[] (only when "Restrict guidelines" is on).
 9. web/api/qc.py — POST /api/qc calls get_quality_control_interpretation().

 Phase 3 — UI Components

 10. web/components/header.py — Shared header with app title and tab links for /,
 /file, /qc. Uses ui.header() with ui.tabs().
 11. web/components/filters.py — filters_panel(guidelines_state, year_state, bp_types_state, sites_state) as a @ui.refreshable that renders the four filter
 groups. Returns bound state objects.
 12. web/components/breakpoint_dialog.py — BreakpointDialog(ui.dialog) class.
 Columns: GUIDELINES, YEAR, BREAKPOINT_TYPE, HOST, SITE_OF_INFECTION, WHONET_TEST, R, I, S,
 ECV_ECOFF, ORGANISM_CODE, ORGANISM_CODE_TYPE, COMMENTS.
 13. web/components/expert_dialog.py — ExpertRuleDialog(ui.dialog).
 Columns: RULE_CODE, DESCRIPTION, ORGANISM_CODE, ORGANISM_CODE_TYPE, RULE_CRITERIA,
 AFFECTED_ANTIBIOTICS, ANTIBIOTIC_EXCEPTIONS.
 14. web/components/intrinsic_dialog.py — IntrinsicRuleDialog(ui.dialog).
 Columns: GUIDELINE, REFERENCE_TABLE, ORGANISM_CODE, ORGANISM_CODE_TYPE, ABX_CODE,
 ABX_CODE_TYPE, ANTIBIOTIC_EXCEPTIONS, COMMENTS.

 Phase 4 — Pages

 15. web/pages/single.py — @ui.page('/'). Ports the Single Interpretation tab:
   - Left panel: organism select (searchable, bound to the WHONET org code; source =
 ALL_ORGANISMS, label '{name} - ({code})'), antibiotic select (searchable, bound to the
 3-letter WHONET_ABX_CODE, label '{name} - ({code})'), test method radio (Disk /
 'MIC / Etest'; Disk is the default), potency select (auto-populated via get_potency_options,
 enabled only for Disk; MIC and Etest share one MIC path), measurement input.
   - Middle panel: guidelines checkboxes (CLSI checked by default, EUCAST, SFM), year number
 (mandatory), "Restrict breakpoint types" + types checkboxes (default Human when
 unrestricted), "Restrict sites" + sites checklist (from SitesOfInfection.DEFAULT_ORDER,
 includes a blank entry).
   - Right panel: include-comments checkbox (maps to
 InterpretationConfiguration.include_interpretation_comments; when false, comments are
 stripped like C# RemoveComments), four action buttons:
 "Get interpretations" → builds the config via make_single_tab_config and one full WHONET
 test code per selected guideline (build_whonet_code), calls interpret_single ONCE per
 guideline, and shows one notification/line per result (fullCode: interpretation), matching
 C# which loops GetFullTestCodes() and shows one line per code,
 "Applicable breakpoints" → opens BreakpointDialog,
 "Applicable expert rules" → opens ExpertRuleDialog,
 "Applicable intrinsic rules" → opens IntrinsicRuleDialog.
   - Never pass a raw 3-letter code to interpret_single; always the full WHONET test code.
   - All state is local to the page function (per-user).
   - Engine calls run inline for single interpretation; dialog data fetched inline
 (fast enough, < 50ms).
 16. web/pages/file_mode.py — @ui.page('/file'). Ports the File Mode tab:
   - ui.upload() for input file
   - ui.select() for input delimiter — only |, ,, ;, TAB
   - ui.upload() for the REQUIRED config JSON (parsed via read_configuration) — NOT built
 from the single-tab filter controls
   - a REQUIRED guideline_year field (C# requires YearCheckbox + GuidelineYearUpDown)
   - ui.linear_progress() bound to a local progress counter
   - Interpret button → background_tasks.create(run_interpretation()):
 async def run_interpretation():
     columns, rows = await asyncio.to_thread(load_input_file, tmp_path, delim)
     config = read_configuration(config_path)             # external JSON, required
     results = await asyncio.to_thread(interpret_isolates, config, columns, rows)
     output = await asyncio.to_thread(generate_output_str, config, columns, results)
     ui.download(output.encode(), 'interpretations.txt')  # always TAB-delimited
   - Cancel: a REAL cooperative cancellation flag checked between row batches inside the
 thread (chunk the work). interpret_isolates has no cancel token, so disabling the button
 alone is not cancellation — see design decision 4.
 17. web/pages/qc.py — @ui.page('/qc'). Simple form:
 strain input, antibiotic code input, measurement input → result badge.
 (NEW — the C# WinForms GUI has no QC tab; /qc is an extension, not a port.)

 Phase 5 — Entry Point & Docker

 18. web/main.py — Imports all pages and api modules (triggering registration),
 then:
 def start():
     ui.run(host='0.0.0.0', port=8080, title='AMRIE Web',
            storage_secret=os.environ.get('STORAGE_SECRET', 'amrie-dev-secret'),
            fastapi_docs=True, show=False, reload=False)

 if __name__ == '__main__':
     start()
 19. Dockerfile — copy the package sources + metadata BEFORE the editable install (an
 editable install needs the package sources, and the README referenced by metadata, to be
 present):
 FROM python:3.11-slim
 WORKDIR /app
 COPY pyproject.toml README.md ./
 COPY src/ src/
 COPY web/ web/
 RUN pip install -e ".[web]"
 EXPOSE 8080
 CMD ["python", "web/main.py"]
 20. docker-compose.yml
 services:
   amrie-web:
     build: .
     ports: ["8080:8080"]
     environment:
       - STORAGE_SECRET=change-me-in-production
     restart: unless-stopped

 ---
 API Surface (REST)

 ┌────────┬───────────────────────┬──────────────────────────────────────────────┐
 │ Method │         Path          │                   Purpose                    │
 ├────────┼───────────────────────┼──────────────────────────────────────────────┤
 │ GET    │ /api/organisms        │ All organisms (ALL_ORGANISMS; code, name)    │
 ├────────┼───────────────────────┼──────────────────────────────────────────────┤
 │ GET    │ /api/antibiotics      │ All antibiotics (code, name, potencies)      │
 ├────────┼───────────────────────┼──────────────────────────────────────────────┤
 │ GET    │ /api/guidelines       │ Available guidelines                         │
 ├────────┼───────────────────────┼──────────────────────────────────────────────┤
 │ GET    │ /api/breakpoint-types │ Human / Animal / ECOFF                       │
 ├────────┼───────────────────────┼──────────────────────────────────────────────┤
 │ GET    │ /api/sites            │ All sites of infection in default order      │
 ├────────┼───────────────────────┼──────────────────────────────────────────────┤
 │ POST   │ /api/interpret/single │ One interpret_single call per guideline      │
 ├────────┼───────────────────────┼──────────────────────────────────────────────┤
 │ POST   │ /api/interpret/file   │ Multipart: data file + config → TSV download │
 ├────────┼───────────────────────┼──────────────────────────────────────────────┤
 │ POST   │ /api/breakpoints      │ Applicable breakpoints for organism + drug   │
 ├────────┼───────────────────────┼──────────────────────────────────────────────┤
 │ POST   │ /api/expert-rules     │ Applicable expert rules                      │
 ├────────┼───────────────────────┼──────────────────────────────────────────────┤
 │ POST   │ /api/intrinsic-rules  │ Applicable intrinsic resistance rules        │
 ├────────┼───────────────────────┼──────────────────────────────────────────────┤
 │ POST   │ /api/qc               │ QC range evaluation                          │
 └────────┴───────────────────────┴──────────────────────────────────────────────┘

 OpenAPI docs at /docs (enabled via fastapi_docs=True).

 ---
 Engine functions reused (no changes to engine)

 ┌────────────────────────────────────────────────────────────────────┬──────────────────────────────────────┐
 │                          Engine function                           │               Used by                │
 ├────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
 │ amrie.interpret_single                                             │ api/interpret.py, pages/single.py    │
 ├────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
 │ amrie.io_library.load_input_file                                   │ pages/file_mode.py, api/interpret.py │
 ├────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
 │ amrie.io_library.interpret_isolates                                │ pages/file_mode.py, api/interpret.py │
 ├────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
 │ amrie.io_library.generate_output_file                              │ pages/file_mode.py                   │
 ├────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
 │ amrie.breakpoint.get_applicable_breakpoints                        │ pages/single.py, api/breakpoints.py  │
 ├────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
 │ amrie.expert_rule.get_applicable_expert_rules                      │ pages/single.py, api/rules.py        │
 ├────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
 │ amrie.expected_resistance.get_applicable_expected_resistance_rules │ pages/single.py, api/rules.py        │
 ├────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
 │ amrie.qc.get_quality_control_interpretation                        │ pages/qc.py, api/qc.py               │
 ├────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
 │ amrie.organism.ALL_ORGANISMS, CURRENT_ORGANISMS                    │ web/state.py                         │
 ├────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
 │ amrie.antibiotic.ALL_ANTIBIOTICS                                   │ web/state.py, web/helpers.py         │
 ├────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
 │ amrie.constants.SitesOfInfection.DEFAULT_ORDER                     │ web/state.py                         │
 ├────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
 │ amrie.config.InterpretationConfiguration                           │ web/helpers.py, pages                │
 ├────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
 │ amrie.config.read_configuration                                    │ pages/file_mode.py                   │
 └────────────────────────────────────────────────────────────────────┴──────────────────────────────────────┘

 ---
 Verification

 # 1. Install with web extras
 pip install -e ".[dev,web]"

 # 2. Start server
 python web/main.py
 # → http://localhost:8080         (Single interp UI)
 # → http://localhost:8080/file    (File mode UI)
 # → http://localhost:8080/qc      (QC UI)
 # → http://localhost:8080/docs    (REST API docs)

 # 3. Smoke test REST API
 #    A full config is built server-side and a full WHONET test code (e.g. PEN_ND10) is
 #    derived from abx code + guideline + disk + potency — not passed as a bare code.
 curl -s -X POST http://localhost:8080/api/interpret/single \
   -H 'Content-Type: application/json' \
   -d '{"organism_code": "eco", "whonet_abx_code": "PEN", "measurement": "19",
        "guidelines": ["CLSI"], "test_method": "disk", "potency": "10",
        "guideline_year": 2026, "include_comments": false,
        "restrict_breakpoint_types": false, "breakpoint_types": [],
        "restrict_sites": false, "sites_of_infection": []}' \
   | python -m json.tool
 # expected: {"results": [{"whonet_test": "PEN_ND10", "interpretation": "S"}]}

 # 4. Verify multi-user isolation by opening two browser tabs
 #    Each tab maintains independent organism/drug/measurement selections.

 # 5. File mode: upload SampleInputFile.txt with "|" delimiter and SampleConfig.json
 #    Verify download returns a TSV with _INTERP columns.

 # 6. Run existing engine tests (must still pass — engine untouched)
 pytest tests/ -q

 ---
 Notes

 - nicegui-llms.txt specifies single quotes for Python strings; follow throughout web/
 - Use background_tasks.create() not asyncio.create_task()
 - Use await asyncio.to_thread(fn, *args) for all engine calls in async context
 - ui.select(options, with_input=True) handles the organism list client-side; no
 server-side dynamic filtering needed (but also port the C# search-box parity — see below)
 - Progress bar for file mode: pass a threading.Event or shared counter into the thread;
 update ui.linear_progress via a ui.timer that checks the counter
 - The potency ui.select is disabled when MIC/Etest radio is selected; re-enabled on Disk
 (Disk is the default, matching C#)
 - generate_output_file only writes to a filesystem path and always emits TAB-delimited
 output regardless of input delimiter; add a generate_output_str() helper (temp-file
 wrapper) in web/helpers.py

 ---
 C# parity gaps & intentional deviations

 - Organism / antibiotic search-box parity: C# has dedicated search boxes, not just a combo.
 ui.select(..., with_input=True) covers client-side filtering, but port the explicit
 search-box behaviour for full parity.
 - Add a placeholder '[Select a value]' option on both the organism and antibiotic combos.
 - "Restrict …" checkbox pattern: an unchecked Restrict toggle means null/None filters for
 the breakpoint / expert / intrinsic lookups (no filtering), not empty lists.
 - C# calls AntibioticSpecificInterpretationRules.ClearBreakpoints() (or an equivalent
 breakpoint-cache clear) before each single interpret — verify whether the Python engine
 needs an equivalent breakpoint-cache clear before single interpret before asserting it
 does.
 - /qc is a NEW addition, not a port: the C# WinForms GUI has no QC tab (QC is engine/CLI
 only).
 - Several NiceGUI APIs used in this plan are unverified against the bundled
 nicegui-llms.txt: ui.select(with_input=True), ui.download(bytes, filename),
 ui.run(fastapi_docs=True), and subclassing ui.dialog — verify each against the installed
 NiceGUI version.
