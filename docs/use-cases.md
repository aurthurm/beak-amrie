# Use Cases

Practical examples covering common integration patterns.

---

## 1. Interpret a single measurement

The simplest use case — one organism, one drug, one result.

```python
from amrie import interpret_single
from amrie.config import read_configuration

config = read_configuration("src/amrie/resources/SampleConfig.json")

# Disk diffusion
print(interpret_single(config, "ent", "PEN_ND10", "19"))   # "S"
print(interpret_single(config, "ent", "PEN_ND10", "06"))   # "R"
print(interpret_single(config, "ent", "ERY_ND15", "17"))   # "I"

# MIC
print(interpret_single(config, "eco", "AMP_NM", "4"))      # "S"
print(interpret_single(config, "eco", "AMP_NM", "64"))     # "R"

# MIC with < / > modifiers
print(interpret_single(config, "eco", "AMP_NM", "<4"))     # "S"
print(interpret_single(config, "eco", "AMP_NM", ">16"))    # "R"

# Intrinsic resistance (Klebsiella is inherently resistant to ampicillin)
print(interpret_single(config, "kpn", "AMP_ND10", "20"))   # "R*"
```

---

## 2. Interpret a batch file

Read a pipe-delimited input file and write a tab-delimited output file with `_INTERP` columns added.

```python
from amrie import interpret_file
from amrie.config import read_configuration

config = read_configuration("config.json")
interpret_file(config, "input.txt", "output.txt", delimiter="|")
```

### With year override

Override the guideline year without editing the config file:

```python
interpret_file(config, "input.txt", "output.txt", delimiter="|", guideline_year=2024)
```

### Vertical output (one row per antibiotic)

```json
// config.json
{
  "HorizontalAntibioticResults": false,
  ...
}
```

```python
interpret_file(config, "input.txt", "output_vertical.txt", delimiter="|")
```

---

## 3. QC reference strain evaluation

Check that your test system is within acceptable limits for a reference strain.

```python
from amrie import interpret_qc_single

print(interpret_qc_single("atcc25922", "SAM_ND10", "22"))  # "IN"
print(interpret_qc_single("atcc25922", "SAM_ND10", "18"))  # "OUT"
print(interpret_qc_single("atcc25922", "SAM_ND10", ""))    # ""  (blank measurement)
print(interpret_qc_single("unknown",   "SAM_ND10", "22"))  # ""  (unknown strain)
```

### Access the QC range directly

```python
from amrie.qc import get_applicable_quality_control_range

qc_range = get_applicable_quality_control_range("atcc25922", "SAM_ND10")
if qc_range:
    print(f"Acceptable range: {qc_range.MINIMUM}–{qc_range.MAXIMUM} mm")
    print(f"Guideline: {qc_range.GUIDELINE} {qc_range.YEAR}")
```

---

## 4. User-defined breakpoints

Override a specific organism / drug breakpoint with your own values.

Create `my_breakpoints.txt` (same column structure as `Breakpoints.txt`):

```
GUIDELINES  YEAR  TEST_METHOD  POTENCY  ORGANISM_CODE  ORGANISM_CODE_TYPE  BREAKPOINT_TYPE  HOST  SITE_OF_INFECTION  REFERENCE_TABLE  REFERENCE_SEQUENCE  WHONET_ABX_CODE  WHONET_TEST  R  I  SDD  S  ECV_ECOFF  ECV_ECOFF_TENTATIVE  DATE_ENTERED  DATE_MODIFIED  COMMENTS
UserDefined  2026  DISK  10µg  afb  WHONET_ORG_CODE  Human  Human    Internal  1  AMP  AMP_ND10  20   21-27  28  0  2026-01-01
```

Configure the path:

```json
{
  "UserDefinedBreakpointsFile": "my_breakpoints.txt"
}
```

```python
from amrie.config import read_configuration, InterpretationConfiguration
from amrie import interpret_single

config = read_configuration("config_with_udb.json")

# User-defined breakpoint applies: S≥28, I=21-27, R≤20
print(interpret_single(config, "afb", "PEN_ND10", "19"))  # "R"
print(interpret_single(config, "afb", "PEN_ND10", "28"))  # "S"
```

---

## 5. ESBL-confirmed isolates

Enable the ESBL-CONFIRMED expert rule to automatically mark all affected beta-lactams as `R!` when the `ESBL` column is `+`.

```json
{
  "EnabledExpertInterpretationRules": ["ESBL-CONFIRMED"],
  "IncludeInterpretationComments": true
}
```

```python
from amrie.isolate import IsolateInterpretation
from amrie.config import read_configuration

config = read_configuration("esbl_config.json")

row = {
    "ORGANISM": "eco",
    "ESBL": "+",
    "MOX_ND30": "25",   # Moxalactam, measures cephalosporin resistance
}

results = IsolateInterpretation(
    row,
    list(row.keys()),
    config.enabled_expert_interpretation_rules,
    config.user_defined_breakpoints,
    guideline_year=int(config.guideline_year),
).get_all_interpretations()

print(results["MOX_ND30"])   # "R!"
```

---

## 6. Disabling intrinsic resistance rules

For research purposes you may want to see the breakpoint-based result even for drug–bug combinations that are normally flagged as intrinsically resistant.

```python
from amrie.config import InterpretationConfiguration
from amrie import interpret_single

config = InterpretationConfiguration(
    use_intrinsic_resistance_rules=False,
    guideline_year=2026,
    prioritized_breakpoint_types=["Human", "Animal", "ECOFF"],
)

# Normally R* (intrinsic), now returns S/I/R based on the breakpoint
print(interpret_single(config, "kpn", "AMP_ND10", "20"))  # "S"
print(interpret_single(config, "kpn", "AMP_ND10", "06"))  # "R"
```

---

## 7. Site-of-infection prioritisation

Use `PrioritizedSitesOfInfection` to select the most clinically relevant breakpoint when multiple site-specific breakpoints exist for the same drug.

```json
{
  "PrioritizedSitesOfInfection": ["Meningitis"],
  "GuidelineYear": 2026
}
```

```python
from amrie.config import InterpretationConfiguration
from amrie import interpret_single

config = InterpretationConfiguration(
    guideline_year=2026,
    prioritized_breakpoint_types=["Human"],
    prioritized_sites_of_infection=["Meningitis"],
)
# Penicillin S breakpoint for meningitis is lower (more stringent) than non-meningitis
result = interpret_single(config, "spn", "PEN_NM", "0.125")
```

---

## 8. Programmatic pipeline without a config file

Skip the JSON file entirely and build the configuration in code.

```python
from amrie.config import InterpretationConfiguration
from amrie.io_library import load_input_file, interpret_isolates, generate_output_file

config = InterpretationConfiguration(
    guideline_year=2026,
    prioritized_breakpoint_types=["Human"],
    include_interpretation_comments=True,
    enabled_expert_interpretation_rules=None,   # all rules
)

columns, rows = load_input_file("data.txt", delimiter="|")
results = interpret_isolates(config, columns, rows)
generate_output_file("output.txt", config, columns, results)
```

---

## 9. Sequential vs. parallel interpretation

By default `interpret_isolates` uses `ThreadPoolExecutor` for batches of two or more rows. Force sequential processing for debugging or deterministic output order:

```python
results = interpret_isolates(config, columns, rows, parallel=False)
```

Verify that both give identical results:

```python
seq = interpret_isolates(config, columns, rows, parallel=False)
par = interpret_isolates(config, columns, rows, parallel=True)
assert seq == par
```

---

## 10. Inspecting breakpoints and rules directly

```python
from amrie.breakpoint import get_applicable_breakpoints
from amrie import constants as C

# All CLSI 2026 Human breakpoints for E. coli / ampicillin disk
bps = get_applicable_breakpoints(
    "eco",
    user_defined_breakpoints=[],
    prioritized_guidelines=["CLSI"],
    prioritized_guideline_years=[2026],
    prioritized_breakpoint_types=["Human"],
    prioritized_sites_of_infection=list(C.SitesOfInfection.DEFAULT_ORDER),
    prioritized_whonet_abx_full_drug_codes=["AMP_ND10"],
)
for bp in bps:
    print(f"R≤{bp.R}  S≥{bp.S}  site={bp.SITE_OF_INFECTION!r}")
```

```python
from amrie.expected_resistance import get_applicable_expected_resistance_rules

# What is Klebsiella intrinsically resistant to?
rules = get_applicable_expected_resistance_rules("kpn", ["CLSI"])
for r in rules:
    print(r.ABX_CODE)
```

```python
from amrie.expert_rule import get_applicable_expert_rules, EXPERT_INTERPRETATION_RULES

# Which expert rules apply to E. coli when ESBL column is present?
rules = get_applicable_expert_rules(
    "eco",
    antimicrobial_codes=["CTX_ND30"],
    other_tests=["ESBL"],
    enabled_expert_interpretation_rules=None,
)
for r in rules:
    print(r.RULE_CODE, r.CriteriaOperator)
```
