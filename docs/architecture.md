# Architecture

## Overview

AMRIE-py is a Python port of the C# [AMRIE](https://github.com/rlabinc/AMRIE) engine. The codebase is intentionally structured to map 1:1 to the original C# source so that logic changes in the upstream project can be applied without needing to re-architect the port.

---

## Module map

```
src/amrie/
├── __init__.py              Public API (interpret_single, interpret_file, interpret_qc_single)
├── cli.py                   Typer CLI app — file / single / qc commands
│
├── constants.py             All shared constants (interpretation codes, modifiers, delimiters)
├── messages.py              English user-facing strings
├── paths.py                 Resource directory resolution (replaces C# SystemRootPath)
│
├── antibiotic.py            Antibiotic reference data (ALL_ANTIBIOTICS, CEPH3 / MRS / ICR lists)
├── organism.py              Organism taxonomy (CURRENT_ORGANISMS, MERGED_ORGANISMS)
├── breakpoint.py            Breakpoint data + applicability selection algorithm
├── expected_resistance.py   Intrinsic (expected) resistance phenotype rules
├── expert_rule.py           Expert interpretation rules (ESBL, MRS, ICR, BLNAR)
├── qc.py                    Quality-control range data and interpretation
│
├── parsing.py               WHONET column-name parser + numeric result parser
├── io_utils.py              CSV split / join utilities (quote-aware)
├── antibiotic_rules.py      Per-antibiotic interpretation engine + breakpoint cache
├── isolate.py               Single-isolate interpretation coordinator
├── config.py                InterpretationConfiguration (loads JSON config file)
├── io_library.py            Batch file pipeline (load → interpret → generate output)
│
└── resources/
    ├── Antibiotics.txt
    ├── Breakpoints.txt
    ├── ExpectedResistancePhenotypes.txt
    ├── ExpertInterpretationRules.txt
    ├── Organisms.txt
    ├── QC_Ranges.txt
    ├── SampleConfig.json
    ├── SampleInputFile.txt
    └── SampleUserDefinedBreakpoints.txt
```

---

## Layer diagram

```
┌─────────────────────────────────────────────────┐
│  Public API  (__init__.py)                       │
│  CLI         (cli.py)                            │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│  Batch pipeline   (io_library.py)                │
│    load_input_file → interpret_isolates          │
│                   → generate_output_file         │
└────────────────────┬────────────────────────────┘
                     │ one row at a time
┌────────────────────▼────────────────────────────┐
│  Isolate coordinator  (isolate.py)               │
│    1. Apply expert rules                         │
│    2. Apply breakpoints / intrinsic resistance   │
└──────┬────────────────────────┬─────────────────┘
       │ per drug               │ organism filter
┌──────▼──────────┐   ┌────────▼────────────────┐
│ AntibioticRules │   │ Expert / Intrinsic rules │
│ (antibiotic_    │   │ (expert_rule.py,         │
│  rules.py)      │   │  expected_resistance.py) │
└──────┬──────────┘   └─────────────────────────┘
       │ lookup
┌──────▼──────────────────────────────────────────┐
│  Reference data (loaded once at import time)     │
│    Breakpoints, Organisms, Antibiotics, Rules    │
└─────────────────────────────────────────────────┘
```

---

## Data flow — file mode

```
Input file (.txt / .tsv)
        │
        ▼
load_input_file()
  Parses header row; builds list of {column → value} dicts.
        │
        ▼
_collect_distinct_interpretation_keys()
  Collects unique (organism, guideline, drug_column) triples across all rows.
        │
        ▼
preheat_breakpoint_cache()
  Populates _breakpoint_cache for every key in parallel
  (ThreadPoolExecutor). Eliminates lock contention during main loop.
        │
        ▼
interpret_isolates()          ← parallel (ThreadPoolExecutor)
  For each row:
    IsolateInterpretation(row, ...)
      ├── _get_expert_interpretations()   ← expert rules fire first
      └── get_all_interpretations()       ← breakpoint / intrinsic rules
        │
        ▼
generate_output_file()
  Writes horizontal (_INTERP columns) or vertical (3 fixed columns) TSV.
        │
        ▼
Output file (.txt / .tsv)
```

---

## Data flow — single interpretation

```
interpret_single(config, organism, antibiotic, measurement)
        │
        ▼
IsolateInterpretation.get_single_interpretation(config, ...)
        │
        ▼
IsolateInterpretation(row={ORGANISM:..., antibiotic:measurement}, ...)
  ├── _get_expert_interpretations()
  └── _get_single_interp(antibiotic)
        │
        ▼
AntibioticSpecificInterpretationRules.get_interpretation()
  ├── _apply_intrinsic_resistance_rules()   → "R*" if rule matches
  └── _apply_breakpoints()                  → S / I / R / SDD / NS / WT / NWT
```

---

## Caching strategy

Two module-level caches live in `antibiotic_rules.py`. Both are populated lazily and survive for the lifetime of the Python process.

### `_intrinsic_cache`

```
{organism_code: {guideline: {drug_code: ExpectedResistancePhenotypeRule | None}}}
```

- Keyed on the **3-letter drug code** (not the full column name) because intrinsic resistance applies regardless of potency or method.
- Protected by `_intrinsic_cache_lock` (one lock for the whole dict).
- Computation (`get_applicable_expected_resistance_rules`) is fast (list iteration), so it is performed inside the lock.

### `_breakpoint_cache`

```
{organism_code: {guideline: {year: {full_drug_column: Breakpoint | None}}}}
```

- Keyed on the **full column name** because the potency affects which breakpoint row matches.
- Uses **double-checked locking**:
  1. Fast lockless read — returns immediately on a hit.
  2. Expensive computation (`get_applicable_breakpoints`) outside the lock.
  3. Write under `_breakpoint_cache_lock` with a second check to avoid overwriting a concurrent write.
- A `None` entry means "no applicable breakpoint exists" — this is also cached to prevent repeated lookups.

### Thread safety

Both caches are safe for concurrent access in CPython because individual `dict` operations are atomic under the GIL. The locks exist to protect multi-step read-check-write sequences that must not be interleaved.

---

## Parallelism

| Location | Mechanism | Purpose |
|---|---|---|
| `preheat_breakpoint_cache` | `ThreadPoolExecutor` | Warm up breakpoint cache before batch run |
| `interpret_isolates` | `ThreadPoolExecutor` | Interpret multiple rows concurrently |
| `_breakpoint_cache` | Double-checked lock | Thread-safe cache writes during preheat |

Worker count defaults to `min(32, cpu_count + 4, len(items))`, matching the pattern used throughout the batch pipeline.

---

## C# → Python mapping

| C# file | Python module(s) |
|---|---|
| `Constants.cs` | `constants.py` |
| `Antibiotic.cs` + `AntibioticComponents.cs` | `antibiotic.py`, `parsing.py` |
| `Organism.cs` | `organism.py` |
| `Breakpoint.cs` | `breakpoint.py` |
| `ExpectedResistancePhenotypeRule.cs` | `expected_resistance.py` |
| `ExpertInterpretationRule.cs` + `ExpertRuleCriterion.cs` | `expert_rule.py` |
| `QualityControlRange.cs` | `qc.py` |
| `InterpretationLibrary.cs` | `parsing.py` |
| `AntibioticSpecificInterpretationRules.cs` | `antibiotic_rules.py` |
| `IsolateInterpretation.cs` | `isolate.py` |
| `InterpretationConfiguration.cs` | `config.py` |
| `IO_Library.cs` | `io_library.py`, `io_utils.py` |
| `FileInterpretationParameters.cs` | `io_library.py` |
| `Interpretation CLI/Program.cs` | `cli.py` |
| `Translations/Resources.resx` | `messages.py` (English only) |

---

## Web layer

The [`web/`](../web/) package provides a NiceGUI browser UI and REST API. It runs in the same process as FastAPI (via NiceGUI's `app` object) and calls the public `amrie` API — never modifying engine modules under `src/amrie/`.

```
Browser / HTTP client
        │
        ▼
web/pages/*  +  web/api/*
        │
        ▼
web/helpers.py  (config builders, serializers)
        │
        ▼
amrie.*  (interpret_single, interpret_isolates, read_configuration, …)
```

See [`web.md`](web.md) for installation, routes, endpoint reference, and deployment.
