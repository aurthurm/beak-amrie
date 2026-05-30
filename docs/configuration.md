# Configuration Reference

All configuration is stored in a JSON file passed via `--config` on the CLI or `read_configuration(path)` in the API.

See [`resources/SampleConfig.json`](../src/amrie/resources/SampleConfig.json) for a complete annotated example.

---

## Complete option reference

### `GuidelineYear`

| | |
|---|---|
| **Type** | integer |
| **Default** | `2026` (current breakpoint table revision year) |

The breakpoint table year to apply. Only breakpoints with this `YEAR` value are considered (user-defined breakpoints are always included regardless of year).

```json
"GuidelineYear": 2026
```

To use the latest year, omit the key or leave it as the default.

---

### `PrioritizedBreakpointTypes`

| | |
|---|---|
| **Type** | array of strings, or `null` / `[]` |
| **Default** | `null` (all types) |
| **Valid values** | `"Human"`, `"Animal"`, `"ECOFF"` |

Controls which breakpoint categories are considered and in what priority order.

```json
"PrioritizedBreakpointTypes": ["Human"]
```

```json
"PrioritizedBreakpointTypes": ["Human", "Animal", "ECOFF"]
```

An empty array or `null` allows all types; the built-in default order is Human → Animal → ECOFF.

---

### `EnabledExpertInterpretationRules`

| | |
|---|---|
| **Type** | array of strings, or `null` / `[]` |
| **Default** | `null` (all rules enabled) |
| **Valid values** | `"ESBL-CONFIRMED"`, `"ESBL-AMPC-PROBABLE"`, `"BLNAR-HFLU"`, `"MRS"`, `"ICR"` |

Whitelist of expert rule codes to apply. Rules not in this list are silently skipped.

```json
"EnabledExpertInterpretationRules": ["MRS", "ICR"]
```

```json
"EnabledExpertInterpretationRules": ["ESBL-CONFIRMED", "BLNAR-HFLU", "MRS", "ICR"]
```

Pass `null` or omit the key to enable all rules. Pass `[]` to disable all rules.

See [`expert-rules.md`](expert-rules.md) for a description of each rule.

---

### `PrioritizedSitesOfInfection`

| | |
|---|---|
| **Type** | array of strings, or `null` / `[]` |
| **Default** | `null` → the full default order is used |

Ordered list of site-of-infection labels. The first site in the list that matches a breakpoint's `SITE_OF_INFECTION` field takes priority over later sites. When `null` or `[]`, the [full default order](../src/amrie/constants.py) applies.

Use this to prioritise a specific clinical context:

```json
"PrioritizedSitesOfInfection": ["Meningitis"]
```

Any default-order sites not listed are automatically appended at the end (after `update_sites_of_infection` runs), so they remain available as fallbacks.

---

### `DisabledSitesOfInfection`

| | |
|---|---|
| **Type** | array of strings, or `null` / `[]` |
| **Default** | `null` |

Sites to exclude entirely, even if they appear in the default order. Useful when you want to block e.g. veterinary breakpoints.

```json
"DisabledSitesOfInfection": ["Mastitis", "Metritis", "Mammary gland"]
```

---

### `HorizontalAntibioticResults`

| | |
|---|---|
| **Type** | boolean |
| **Default** | `true` |

Controls the output layout:

- `true` — horizontal: a `<drug>_INTERP` column is inserted after each measurement column in the original column order.
- `false` — vertical: antibiotic columns are removed and each measurement becomes a separate row with `ANTIBIOTIC_CODE`, `ANTIBIOTIC_MEASUREMENT`, `ANTIBIOTIC_INTERPRETATION` columns appended.

```json
"HorizontalAntibioticResults": false
```

See [`data-formats.md`](data-formats.md) for output examples.

---

### `IncludeInterpretationComments`

| | |
|---|---|
| **Type** | boolean |
| **Default** | `false` |

When `false`, the `*` (intrinsic resistance) and `!` (expert rule) suffixes are stripped from interpretation strings before writing to the output file. The base category code (`S`, `R`, etc.) is always written.

```json
"IncludeInterpretationComments": true
```

---

### `UseIntrinsicResistanceRules`

| | |
|---|---|
| **Type** | boolean |
| **Default** | `true` |

When `false`, intrinsic (expected) resistance rules are bypassed and the breakpoint-based result is always returned. Use this when you want to see the MIC-based interpretation for drug–organism pairs that are normally intrinsically resistant.

```json
"UseIntrinsicResistanceRules": false
```

---

### `RoundHalfDilutions`

| | |
|---|---|
| **Type** | boolean |
| **Default** | `true` |

When `true`, E-test MIC values that fall between standard two-fold dilution steps are rounded up to the next standard step before comparison with breakpoints. This is the standard laboratory practice.

```json
"RoundHalfDilutions": false
```

---

### `UserDefinedBreakpointsFile`

| | |
|---|---|
| **Type** | string (file path) |
| **Default** | `""` (disabled) |

Path to a user-defined breakpoints TSV file. Relative paths are resolved relative to the package root (the directory containing `amrie/`). User-defined breakpoints sort ahead of all built-in breakpoints.

```json
"UserDefinedBreakpointsFile": "my_custom_breakpoints.txt"
```

See [`data-formats.md`](data-formats.md) for the required file structure.

---

## Annotation conventions

The engine ignores JSON keys that start with `_Comment` or `DISABLED_`, allowing in-file documentation and temporarily disabled settings:

```json
{
  "GuidelineYear": 2026,
  "_Comment_Year": "Change to 2024 for legacy data",

  "EnabledExpertInterpretationRules": ["MRS", "ICR"],
  "_Comment_IgnoredExpertRules": ["ESBL-CONFIRMED", "ESBL-AMPC-PROBABLE"],

  "DISABLED_UserDefinedBreakpointsFile": "path/to/file.txt"
}
```

---

## Creating a configuration programmatically

```python
from amrie.config import InterpretationConfiguration, default_configuration
from amrie.breakpoint import BreakpointTypes
from amrie.expert_rule import RuleCodes
from amrie import constants as C

# Minimal — defaults apply for everything else
config = InterpretationConfiguration(
    guideline_year=2026,
    prioritized_breakpoint_types=["Human"],
)

# Full control
config = InterpretationConfiguration(
    round_half_dilutions=True,
    include_interpretation_comments=True,
    use_intrinsic_resistance_rules=True,
    enabled_expert_interpretation_rules=[
        RuleCodes.MRSTAPH,
        RuleCodes.BLNAR,
        RuleCodes.ICR,
    ],
    guideline_year=2026,
    prioritized_breakpoint_types=[BreakpointTypes.HUMAN],
    prioritized_sites_of_infection=list(C.SitesOfInfection.DEFAULT_ORDER),
    horizontal_antibiotic_results=True,
)

# Opinionated defaults (MRS + BLNAR + ICR, Human breakpoints, all sites)
config = default_configuration()
```
