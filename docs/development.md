# Development Guide

## Setup

```bash
git clone <repo-url>
cd AMRIE-py

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate         # Windows

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

---

## Running tests

```bash
# All tests
pytest

# Verbose with timings
pytest -v

# One test file
pytest tests/test_qc.py -v

# One test class
pytest tests/test_parity.py::TestSingleInterpretation -v

# One test
pytest tests/test_parity.py::TestSingleInterpretation::test_eco_amp_mic_susceptible -v

# Stop on first failure
pytest -x
```

### Test suite structure

| File | Tests |
|---|---|
| `tests/test_parity.py` | Single interpretation, file-mode batch, golden-file regression, CLI, library API, vertical output, user-defined breakpoints, parallel parity, `UseIntrinsicResistanceRules`, expert rules, IO validation |
| `tests/test_qc.py` | QC range lookup, IN/OUT/blank results, CLI QC command |

### Golden file

`tests/fixtures/golden_sample_output.txt` is a committed reference output generated from `resources/SampleInputFile.txt` with `resources/SampleConfig.json`.

The golden file captures Python-to-Python regressions. Because the upstream C# CLI is Windows/.NET-only and cannot run in Linux CI, it cannot be automatically verified against C# output.

To regenerate the golden file (e.g. after a deliberate interpretation change):

```bash
rm tests/fixtures/golden_sample_output.txt
pytest tests/test_parity.py::TestGoldenFile -v
# The file is created on first run; the test skips with a "created" message.
# Run again to verify it now passes.
pytest tests/test_parity.py::TestGoldenFile -v
```

---

## Project structure

```
AMRIE-py/
├── README.md
├── pyproject.toml
├── docs/                       ← documentation (this folder)
│   ├── architecture.md
│   ├── breakpoint-selection.md
│   ├── cli-reference.md
│   ├── configuration.md
│   ├── data-formats.md
│   ├── development.md          ← this file
│   ├── expert-rules.md
│   └── use-cases.md
├── src/
│   └── amrie/
│       ├── resources/          ← bundled data files (shipped with the package)
│       │   ├── Antibiotics.txt
│       │   ├── Breakpoints.txt
│       │   ├── ExpectedResistancePhenotypes.txt
│       │   ├── ExpertInterpretationRules.txt
│       │   ├── Organisms.txt
│       │   ├── QC_Ranges.txt
│       │   ├── SampleConfig.json
│       │   ├── SampleInputFile.txt
│       │   └── SampleUserDefinedBreakpoints.txt
│       ├── __init__.py         ← public API
│       ├── antibiotic.py
│       ├── antibiotic_rules.py ← core interpretation engine
│       ├── breakpoint.py
│       ├── cli.py
│       ├── config.py
│       ├── constants.py
│       ├── expected_resistance.py
│       ├── expert_rule.py
│       ├── io_library.py
│       ├── io_utils.py
│       ├── isolate.py
│       ├── messages.py
│       ├── organism.py
│       ├── parsing.py
│       ├── paths.py
│       └── qc.py
└── tests/
    ├── fixtures/
    │   ├── esbl_config.json
    │   ├── golden_sample_output.txt
    │   ├── vertical_config.json
    │   └── vertical_udb_config.json
    ├── test_parity.py
    └── test_qc.py
```

---

## Updating resource files

The bundled resource files mirror those distributed with the C# AMRIE project. When a new version of AMRIE is released:

### 1. Breakpoints.txt

Download the updated file from the upstream C# repository and replace `src/amrie/resources/Breakpoints.txt`.

Update `BREAKPOINT_TABLE_REVISION_YEAR` (and optionally `BREAKPOINT_TABLE_REVISION_MINOR_CHANGE_NUMBER`) in `constants.py`.

Regenerate the golden file (it will change if interpretations changed):

```bash
rm tests/fixtures/golden_sample_output.txt
pytest tests/test_parity.py::TestGoldenFile -v
pytest tests/test_parity.py::TestGoldenFile -v
```

Verify that the hand-checked tests in `TestSingleInterpretation` still match the published breakpoints; update their expected values if the breakpoints changed.

### 2. Other resource files

Replace the relevant file in `src/amrie/resources/`. If column structure changed, update the corresponding load function.

| Changed file | Load function to check |
|---|---|
| `Organisms.txt` | `organism._load_all_organisms` |
| `Antibiotics.txt` | `antibiotic._load_antibiotics` |
| `ExpectedResistancePhenotypes.txt` | `expected_resistance._load_rules` |
| `ExpertInterpretationRules.txt` | `expert_rule._load_expert_rules` |
| `QC_Ranges.txt` | `qc.load_quality_control_ranges` |

---

## Porting changes from C\#

When the upstream C# engine changes, apply the equivalent change in Python:

1. Identify the changed `.cs` file(s) using the [C# → Python mapping](architecture.md#c--python-mapping).
2. Apply the logic change to the corresponding `.py` module.
3. Add or update tests to cover the change.
4. Regenerate the golden file if batch output changes.

---

## Adding user-defined breakpoints for testing

Place a custom breakpoints TSV next to your config file:

```
my_config.json
my_breakpoints.txt
```

Reference it in your config:

```json
{
  "UserDefinedBreakpointsFile": "my_breakpoints.txt"
}
```

Or load it at runtime:

```python
from amrie.breakpoint import load_breakpoints
from amrie.config import InterpretationConfiguration

user_bps = load_breakpoints("my_breakpoints.txt", user_defined=True)
config = InterpretationConfiguration(user_defined_breakpoints=user_bps)
```

---

## Cache lifecycle

The two module-level caches (`_intrinsic_cache`, `_breakpoint_cache` in `antibiotic_rules.py`) persist for the lifetime of the Python process. This is intentional — the resource data does not change between calls.

For tests that change the resource data or configuration mid-run, clear the breakpoint cache explicitly:

```python
from amrie.antibiotic_rules import clear_breakpoints, _intrinsic_cache

clear_breakpoints()     # clears _breakpoint_cache
_intrinsic_cache.clear()  # clears _intrinsic_cache
```

---

## Dependencies

| Package | Purpose | Min version |
|---|---|---|
| `pandas` | Loading TSV resource files | 2.0 |
| `typer` | CLI framework | 0.9 |
| `orjson` | Fast JSON serialisation for output files | 3.9 |

### Development only

| Package | Purpose |
|---|---|
| `pytest` | Test runner |

---

## Python version support

The codebase targets Python ≥ 3.10 for:

- `match`/`case` could be used in future (not currently used).
- `X | Y` union type hints (`str | None`).
- `list[str]` and `dict[str, str]` as built-in generic aliases.

The `from __future__ import annotations` import at the top of each module enables PEP 563 postponed evaluation for these hints on Python 3.10.
