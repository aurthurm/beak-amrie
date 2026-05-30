# Data Formats

## WHONET antibiotic column naming

WHONET encodes the drug, guideline, test method, and potency in a single column name. Understanding this format is essential for constructing correct API calls and input files.

### Standard drugs

```
<drug_code>_<guideline_code><method_code>[<potency>]
```

| Part | Description | Examples |
|---|---|---|
| `drug_code` | Three uppercase letters | `AMP`, `PEN`, `CTX`, `VAN` |
| `guideline_code` | One letter (see table below) | `N`, `E`, `F` |
| `method_code` | One letter: `D` disk, `M` MIC, `E` E-test | `D`, `M`, `E` |
| `potency` | Optional disk potency or label | `10`, `5`, `30`, `300` |

**Examples:**

| Column name | Meaning |
|---|---|
| `AMP_ND10` | Ampicillin · CLSI · Disk · 10 µg |
| `PEN_EM` | Penicillin · EUCAST · MIC |
| `CTX_ND30` | Cefotaxime · CLSI · Disk · 30 µg |
| `VAN_NM` | Vancomycin · CLSI · MIC |
| `SAM_ND10` | Ampicillin/sulbactam · CLSI · Disk · 10 µg |
| `NIT_ND300` | Nitrofurantoin · CLSI · Disk · 300 µg |

### User-defined drugs

```
X_<number>_<guideline_code><method_code>[<potency>]
```

| Column name | Meaning |
|---|---|
| `X_1_NM` | User drug #1 · CLSI · MIC |
| `X_2_ED10` | User drug #2 · EUCAST · Disk · 10 µg |

### Guideline codes

| Code | Guideline |
|---|---|
| `N` | CLSI |
| `E` | EUCAST |
| `F` | SFM (France) |
| `S` | SRGA (Sweden) |
| `D` | DIN (Germany) |
| `T` | NEO |
| `B` | BSAC (UK) |
| `A` | AFA |

---

## Input file format

The input file is a delimited text file (any single-character delimiter). The first non-blank row is the header.

### Required columns

| Column | Type | Notes |
|---|---|---|
| `ORGANISM` | string | WHONET organism code (e.g. `eco`, `ent`, `sau`) |
| `<drug>_<guideline><method>...` | string | One or more antibiotic measurement columns |

### Optional columns

Any additional columns (patient metadata, specimen type, ward, etc.) are passed through unchanged to the output file.

### Measurement values

Raw measurement strings accepted for disk results:

```
19        → plain integer
06        → leading zeros are fine
```

Raw measurement strings accepted for MIC/E-test:

```
4         → plain value
0.25      → decimal
<4        → converted to <=2 (halved)
<=4       → kept as-is
>16       → doubled to 32 before comparison
>=8       → converted to >4 (halved)
≤4        → Unicode ≤ accepted, converted to <=4
≥8        → Unicode ≥ accepted, converted to >=8
```

### Sample input (pipe-delimited)

```
ORGANISM|PEN_ND10|ERY_ND15|AMK_ND30|CTX_ND30
ent|19|17||
eco|||17|20
kpn||||||
```

---

## Output file format

### Horizontal layout (default)

A `<drug>_INTERP` column is inserted immediately after each measurement column.

```
ORGANISM  PEN_ND10  PEN_ND10_INTERP  ERY_ND15  ERY_ND15_INTERP
ent       19        S                17        I
eco                                  17        I
```

### Vertical layout

Antibiotic measurement columns are removed and replaced with three fixed columns appended to the right. Each source row produces one output row per antibiotic that was present.

```
ORGANISM  ANTIBIOTIC_CODE  ANTIBIOTIC_MEASUREMENT  ANTIBIOTIC_INTERPRETATION
ent       PEN_ND10         19                      S
ent       ERY_ND15         17                      I
eco       ERY_ND15         17                      I
```

Rows with no antibiotic data produce one blank row (all three columns empty) to preserve row count.

### Interpretation suffixes

By default (`IncludeInterpretationComments: false`) suffixes are stripped from the output:

| Stored internally | Written to file |
|---|---|
| `R*` | `R` |
| `R!` | `R` |
| `S?` | `S` |

Set `IncludeInterpretationComments: true` to preserve suffixes.

---

## Configuration file format

```json
{
  "RoundHalfDilutions": true,
  "IncludeInterpretationComments": false,
  "UseIntrinsicResistanceRules": true,
  "EnabledExpertInterpretationRules": ["BLNAR-HFLU", "MRS", "ICR"],
  "GuidelineYear": 2026,
  "PrioritizedBreakpointTypes": ["Human", "Animal", "ECOFF"],
  "PrioritizedSitesOfInfection": [],
  "DisabledSitesOfInfection": [],
  "HorizontalAntibioticResults": true,
  "UserDefinedBreakpointsFile": ""
}
```

Keys starting with `_Comment` or `DISABLED_` are silently ignored — useful for documentation and temporarily disabling a setting without deleting it.

Full reference: [`configuration.md`](configuration.md)

---

## User-defined breakpoints file format

Identical column structure to the built-in `Breakpoints.txt` resource. The engine overwrites the `GUIDELINES` column with `"UserDefined"` so these breakpoints always sort ahead of built-in ones.

Minimum required columns:

```
GUIDELINES  YEAR  TEST_METHOD  POTENCY  ORGANISM_CODE  ORGANISM_CODE_TYPE
BREAKPOINT_TYPE  HOST  SITE_OF_INFECTION  REFERENCE_TABLE  REFERENCE_SEQUENCE
WHONET_ABX_CODE  WHONET_TEST  R  I  SDD  S  ECV_ECOFF  ECV_ECOFF_TENTATIVE
DATE_ENTERED  DATE_MODIFIED  COMMENTS
```

See [`resources/SampleUserDefinedBreakpoints.txt`](../src/amrie/resources/SampleUserDefinedBreakpoints.txt) for a working example.

---

## QC output JSON format

```json
{
  "ReferenceStrain": "atcc25922",
  "AntibioticCode": "SAM_ND10",
  "Measurement": "22",
  "Interpretation": "IN"
}
```

## Single interpretation output JSON format

```json
{
  "OrganismCode": "eco",
  "AntibioticCode": "AMP_ND10",
  "Measurement": "8",
  "Interpretation": "R"
}
```
