# AMRIE-py

**Antimicrobial Resistance Interpretation Engine — Python port**

A faithful Python implementation of the [AMRIE](https://github.com/rlabinc/AMRIE) C# engine. Interprets antimicrobial susceptibility measurements (disk diffusion, MIC, E-test) against CLSI, EUCAST, SFM, SRGA, BSAC, DIN, NEO, and AFA breakpoints, and applies expert interpretation rules (ESBL, MRS, ICR, BLNAR).

---

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
  - [CLI — batch file](#cli--batch-file)
  - [CLI — single interpretation](#cli--single-interpretation)
  - [CLI — QC evaluation](#cli--qc-evaluation)
  - [Python API](#python-api)
- [Interpretation results](#interpretation-results)
- [Configuration](#configuration)
- [Web UI & REST API](#web-ui--rest-api)
- [Running tests](#running-tests)
- [Documentation](#documentation)

---

## Requirements

- Python ≥ 3.10
- Dependencies: `pandas`, `typer`, `orjson`

---

## Installation

```bash
# From source (editable, includes dev dependencies)
pip install -e ".[dev]"

# Production install from source
pip install .

# Web UI + REST API (NiceGUI)
pip install -e ".[web]"
```

---

## Quick Start

### CLI — batch file

Interpret an entire delimited input file and write results with added `_INTERP` columns:

```bash
amrie file \
  --config src/amrie/resources/SampleConfig.json \
  --delimiter "|" \
  --input src/amrie/resources/SampleInputFile.txt \
  --output output.txt
```

Use `--delimiter TAB` for tab-delimited files.

### CLI — single interpretation

Interpret one organism / antibiotic / measurement combination:

```bash
amrie single \
  --config src/amrie/resources/SampleConfig.json \
  --organism eco \
  --antibiotic AMP_ND10 \
  --measurement 8 \
  --output result.json
```

Prints the result (`R`) to stdout and writes a JSON record to `result.json`.

### CLI — QC evaluation

Check whether a QC reference-strain measurement falls within the acceptable range:

```bash
amrie qc \
  --organism atcc25922 \
  --antibiotic SAM_ND10 \
  --measurement 22 \
  --output qc.json
```

Returns `IN`, `OUT`, or blank (uninterpretable) on stdout.

### Python API

```python
from amrie import interpret_single, interpret_file, interpret_qc_single
from amrie.config import read_configuration

config = read_configuration("src/amrie/resources/SampleConfig.json")

# Single measurement
print(interpret_single(config, "ent", "PEN_ND10", "19"))   # "S"
print(interpret_single(config, "eco", "AMP_NM",  "64"))   # "R"
print(interpret_single(config, "kpn", "AMP_ND10", "20"))  # "R*"  (intrinsic)

# QC reference strain
print(interpret_qc_single("atcc25922", "SAM_ND10", "22"))  # "IN"
print(interpret_qc_single("atcc25922", "SAM_ND10", "18"))  # "OUT"

# Batch file processing
interpret_file(config, "input.txt", "output.txt", delimiter="|")
```

---

## Interpretation results

| Code | Meaning |
|------|---------|
| `S`   | Susceptible |
| `I`   | Intermediate |
| `SDD` | Susceptible, dose-dependent |
| `R`   | Resistant |
| `NS`  | Non-susceptible (no R breakpoint defined) |
| `WT`  | Wild-type (ECOFF breakpoint) |
| `NWT` | Non-wild-type (ECOFF breakpoint) |
| `R*`  | Resistant — intrinsic resistance rule |
| `R!`  | Resistant — expert interpretation rule (e.g. ESBL) |
| `S?` / `R?` | Uncertain due to a `<` or `>` modifier on the measurement |
| *(blank)* | Uninterpretable — no applicable breakpoint found |

---

## Configuration

Create a JSON configuration file to control which guidelines, breakpoint types, sites of infection, and expert rules are applied. See [`resources/SampleConfig.json`](src/amrie/resources/SampleConfig.json) for a complete example.

Key options:

| JSON key | Type | Default | Purpose |
|---|---|---|---|
| `GuidelineYear` | integer | 2026 | Breakpoint table year |
| `PrioritizedBreakpointTypes` | list | `null` | `"Human"`, `"Animal"`, `"ECOFF"` |
| `EnabledExpertInterpretationRules` | list | `null` (all) | `"ESBL-CONFIRMED"`, `"MRS"`, etc. |
| `HorizontalAntibioticResults` | bool | `true` | `true` = `_INTERP` columns; `false` = vertical |
| `IncludeInterpretationComments` | bool | `false` | Include `*` / `!` suffixes in output |
| `UseIntrinsicResistanceRules` | bool | `true` | Apply intrinsic resistance rules |
| `UserDefinedBreakpointsFile` | string | `""` | Path to custom breakpoints file |

Full reference: [`docs/configuration.md`](docs/configuration.md)

---

## Web UI & REST API

A browser-based interface and REST API wrap the same interpretation engine as the CLI.

```bash
pip install -e ".[web]"
amrie-web          # or: python web/main.py
```

Open `http://localhost:8080` for the UI (Single, File Mode, QC tabs). Interactive API docs are at `/docs`.

```bash
# Example REST call — Enterococcus, penicillin disk → "S"
curl -s -X POST http://localhost:8080/api/interpret/single \
  -H "Content-Type: application/json" \
  -d '{"organism_code":"ent","whonet_abx_code":"PEN","measurement":"19",
       "guidelines":["CLSI"],"test_method":"disk","potency":"10units","guideline_year":2026}'
```

Docker: `docker compose up --build` (port 8080, set `STORAGE_SECRET` in production).

Full guide: [`docs/web.md`](docs/web.md)

---

## Running tests

```bash
pytest                   # All tests
pytest -v                # Verbose
pytest tests/test_qc.py  # One file
```

34 tests covering: single interpretation, batch file, golden-file regression, CLI, parallel vs sequential parity, user-defined breakpoints, expert rules, QC, and the `UseIntrinsicResistanceRules` flag.

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Module structure, data flow, caching, threading |
| [`docs/data-formats.md`](docs/data-formats.md) | WHONET column naming, input/output file formats |
| [`docs/configuration.md`](docs/configuration.md) | All configuration options with examples |
| [`docs/cli-reference.md`](docs/cli-reference.md) | Full CLI command reference |
| [`docs/breakpoint-selection.md`](docs/breakpoint-selection.md) | How the most applicable breakpoint is chosen |
| [`docs/expert-rules.md`](docs/expert-rules.md) | Expert interpretation rules guide |
| [`docs/use-cases.md`](docs/use-cases.md) | Practical examples and integration patterns |
| [`docs/development.md`](docs/development.md) | Dev setup, contributing, updating data files |
| [`docs/upstream-sync.md`](docs/upstream-sync.md) | C# upstream commit tracker — where to start diffing for new changes |
| [`docs/web.md`](docs/web.md) | Web UI, REST API, Docker deployment |
