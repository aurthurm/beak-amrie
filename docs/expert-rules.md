# Expert Interpretation Rules

## What are expert rules?

Expert interpretation rules (sometimes called "phenotypic inference rules") infer resistance to a **set of antibiotics** based on an observed resistance pattern in the same isolate. When a rule fires, all antibiotics in its `AFFECTED_ANTIBIOTICS` list are marked `R!` — resistant with the exclamation-point suffix indicating that the result was driven by a rule rather than a direct breakpoint comparison.

Expert rules are applied **before** breakpoint interpretation. Once a drug has been marked `R!` by an expert rule, it is not re-interpreted by normal breakpoints.

---

## Processing sequence

For each isolate row:

1. Find applicable expert rules (organism scope + fields present).
2. For each applicable rule, ensure all **precondition antibiotics** have a breakpoint-based interpretation (so the rule can evaluate resistance patterns).
3. Evaluate the rule's criteria against the computed interpretations.
4. If the criteria are satisfied, mark all `AFFECTED_ANTIBIOTICS` as `R!`.
5. Continue with normal breakpoint interpretation for any remaining antibiotics.

---

## Available rules

### `ESBL-CONFIRMED`

| | |
|---|---|
| **Code** | `ESBL-CONFIRMED` |
| **Organisms** | *Enterobacterales* |
| **Trigger** | `ESBL` column = `"+"` |
| **Operator** | AND |
| **Effect** | Marks all penicillins, cephalosporins, monobactams, penems, and beta-lactam+inhibitor combinations as `R!` |

Used when a laboratory has confirmed ESBL production via a phenotypic or genotypic confirmatory test and has entered `+` in the `ESBL` column.

**Config to enable:**

```json
"EnabledExpertInterpretationRules": ["ESBL-CONFIRMED"]
```

**Input requirement:** The input file must include an `ESBL` column.

---

### `ESBL-AMPC-PROBABLE`

| | |
|---|---|
| **Code** | `ESBL-AMPC-PROBABLE` |
| **Organisms** | *Enterobacterales* |
| **Trigger** | Any **3rd-generation cephalosporin** (CEPH3 class) interpretation = `R` or `NS` |
| **Operator** | AND |
| **Effect** | Marks all ESBL-affected drugs as `R!` |

Infers probable ESBL/AmpC production when at least one 3rd-generation cephalosporin is resistant, even without a confirmatory test. The CEPH3 drugs are identified by the `PROF_CLASS = "CEPH3"` field in `Antibiotics.txt`.

---

### `BLNAR-HFLU`

| | |
|---|---|
| **Code** | `BLNAR-HFLU` |
| **Organisms** | *Haemophilus influenzae* |
| **Trigger** | Ampicillin (`AMP`) interpretation = `R` AND `BETA_LACT` column = `"-"` (beta-lactamase negative) |
| **Operator** | AND |
| **Effect** | Marks ampicillin, amoxicillin, amoxicillin+clavulanate, and other beta-lactams as `R!` |

Identifies beta-lactamase–negative ampicillin-resistant (BLNAR) *H. influenzae*. Both fields (`AMP` disk/MIC result and `BETA_LACT`) must be present in the input file.

---

### `MRS` (Methicillin-Resistant Staphylococcus)

| | |
|---|---|
| **Code** | `MRS` |
| **Organisms** | *Staphylococcus* |
| **Trigger** | Oxacillin (`OXA`) or Cefoxitin (`FOX`) or `MECA_PCR` column = `"+"` interpretation = `R` |
| **Operator** | OR |
| **Effect** | Marks **all beta-lactam classes** as `R!` (except CPT and BPR) |

The affected drug list is computed dynamically from `Antibiotics.txt` — any drug in the Penicillins, Cephems, Cephems-Oral, Monobactams, Penems, Beta-lactam+Inhibitors, or Beta-lactamase inhibitors class is affected, except ceftaroline (CPT) and brilacidin (BPR).

---

### `ICR` (Inducible Clindamycin Resistance)

| | |
|---|---|
| **Code** | `ICR` |
| **Organisms** | *Staphylococcus*, *Streptococcus* |
| **Trigger** | Erythromycin (`ERY`) or another macrolide interpretation = `R` AND clindamycin or another lincosamide interpretation = `S` |
| **Operator** | AND |
| **Effect** | Marks all macrolides, lincosamides, and streptogramins as `R!` |

The D-zone test inferring constitutive MLSB resistance. The affected drug list covers the Macrolides, Lincosamides, and Streptogramins classes.

---

## Enabling and disabling rules

### Enable specific rules

```json
{
  "EnabledExpertInterpretationRules": ["MRS", "ICR"]
}
```

### Enable all rules

```json
{
  "EnabledExpertInterpretationRules": null
}
```

Or omit the key entirely.

### Disable all rules

```json
{
  "EnabledExpertInterpretationRules": []
}
```

### In the Python API

```python
from amrie.config import InterpretationConfiguration
from amrie.expert_rule import RuleCodes

# Enable specific rules
config = InterpretationConfiguration(
    enabled_expert_interpretation_rules=[
        RuleCodes.MRSTAPH,
        RuleCodes.BLNAR,
        RuleCodes.ICR,
    ]
)

# Disable all expert rules
config = InterpretationConfiguration(
    enabled_expert_interpretation_rules=[]
)

# Enable all expert rules
config = InterpretationConfiguration(
    enabled_expert_interpretation_rules=None
)
```

---

## Input file requirements

| Rule | Required columns |
|---|---|
| `ESBL-CONFIRMED` | `ORGANISM`, `ESBL`, at least one beta-lactam column |
| `ESBL-AMPC-PROBABLE` | `ORGANISM`, at least one CEPH3 drug column |
| `BLNAR-HFLU` | `ORGANISM`, `AMP_*` column, `BETA_LACT` column |
| `MRS` | `ORGANISM`, `OXA_*` and/or `FOX_*` column |
| `ICR` | `ORGANISM`, macrolide column (`ERY_*` etc.), lincosamide column (`CLI_*` etc.) |

Rules for which the required fields are absent are automatically removed from consideration before evaluation.

---

## Reading the output

When `IncludeInterpretationComments: true`:

```
AMP_ND10_INTERP → R!
```

When `IncludeInterpretationComments: false` (default):

```
AMP_ND10_INTERP → R
```

The `!` suffix identifies results driven by expert rules; it is only meaningful when looking at the raw interpretation data, not in final clinical reports.
