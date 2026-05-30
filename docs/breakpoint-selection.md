# Breakpoint Selection

## Overview

For any given organism / drug / guideline / year combination, multiple breakpoints may exist in the table — differing by site of infection, host, or organism specificity level. The engine must select the single most applicable breakpoint for a measurement. This document explains how that selection works.

The algorithm is implemented in `get_applicable_breakpoints()` in `breakpoint.py` and mirrors the LINQ query in the original C# `Breakpoint.GetApplicableBreakpoints`.

---

## Step 1: Filter

From the combined pool of built-in breakpoints (`BREAKPOINTS`) and any user-defined breakpoints, the engine keeps only rows that satisfy **all** of these conditions:

| Filter | Detail |
|---|---|
| **Guideline year** | `YEAR` equals the requested year, or the breakpoint is user-defined (always included) |
| **Guideline** | `GUIDELINES` matches the drug's guideline (e.g. `"CLSI"`) |
| **Breakpoint type** | `BREAKPOINT_TYPE` is in the `PrioritizedBreakpointTypes` list (if provided) |
| **Site of infection** | At least one of the breakpoint's sites matches an entry in `PrioritizedSitesOfInfection` |
| **Drug column** | `WHONET_TEST` matches the requested drug column (after E-test → MIC recode) |
| **Organism** | The breakpoint applies to the organism at some taxonomy level (see below) |

### E-test recode

E-test columns share MIC breakpoint rows in the table. Before matching, `AMP_NE` is rewritten to `AMP_NM` so that a search for an E-test column correctly finds the MIC rows.

### Organism taxonomy matching

A breakpoint matches the organism if **any** of the following is true (checked in specificity order):

```
SEROVAR_GROUP  →  exact match on serovar
WHONET_ORG_CODE →  exact match on organism code (most specific organism-level match)
SPECIES_GROUP  →  organism belongs to this species group
GENUS_CODE     →  organism belongs to this genus
GENUS_GROUP    →  organism belongs to this genus group
FAMILY_CODE    →  organism belongs to this family
ANAEROBE + SUBKINGDOM_CODE  →  anaerobe of matching Gram reaction (AN+ or AN-)
ANAEROBE       →  any anaerobe
```

Deprecated organism codes are silently remapped to their current successors before matching.

---

## Step 2: Sort

The surviving breakpoints are sorted by a 9-level key. The sort is **ascending**, so the entry with the lowest key value is most preferred.

| Priority | Key | Detail |
|---|---|---|
| 1 | Drug position | Position in the requested drug list (or alphabetical) |
| 2 | User-defined first | `0` for user-defined, `1` for built-in |
| 3 | Guideline position | Position in `PrioritizedGuidelines` (or alphabetical) |
| 4 | Year | Position in `PrioritizedGuidelineYears` (or descending year — newest first) |
| 5 | Test method | Alphabetical (`DISK` before `MIC`) |
| 6 | Breakpoint type | Position in `PrioritizedBreakpointTypes` (or Human < Animal < ECOFF) |
| 7 | Host | Alphabetical |
| 8 | Organism specificity | Serovar (1) → WHONET code (2) → Species (3) → Genus (4) → Genus group (5) → Family (6) → Anaerobe+Gram (7) → Anaerobe (8) |
| 9 | Site priority | Lowest index of any matching site in `PrioritizedSitesOfInfection` |

---

## Step 3: Select

### When `return_first_breakpoint_only=True`

Return the single top-sorted breakpoint. No grouping needed.  
This is used by the interpretation engine when looking up the breakpoint for one drug.

### When `return_first_breakpoint_only=False`

Group breakpoints by `(GUIDELINES, YEAR, BREAKPOINT_TYPE, HOST, WHONET_TEST)`.  
For each group:

1. Always include the **top** (highest-priority) breakpoint.
2. Include any additional breakpoints from the same group that have the **same** `ORGANISM_CODE` and `ORGANISM_CODE_TYPE` as the top — these differ only on site of infection.
3. Discard breakpoints from the same group that are less specific (e.g. a genus-level breakpoint when the top entry is organism-specific).

This ensures the caller receives all site-specific breakpoints for a drug without receiving genus fallbacks that were superseded by a specific match.

---

## Site of infection priority

When no `PrioritizedSitesOfInfection` is provided, the engine uses the default order from `constants.SitesOfInfection.DEFAULT_ORDER`:

```
Non-meningitis → Non-endocarditis → Parenteral → (Blank) →
Uncomplicated UTI → Infections from urinary tract →
Meningitis → Endocarditis → Endocarditis+combination →
Intravenous → Oral → Inhaled → Investigational →
Extraintestinal → Abscesses → Genital → Intestinal →
Liposomal → Mammary gland → Mastitis → Metritis →
Non-pneumonia → Other infections → Other indications →
Pneumonia → Prophylaxis → Respiratory → Screen →
Skin → Soft tissue → Wounds
```

`(Blank)` means no site is specified in the breakpoint row — this is the "general" breakpoint that applies when no more specific site matches.

A breakpoint may cover multiple sites (comma-separated in `SITE_OF_INFECTION`). Its sort position is the **lowest** index across all its sites, so a breakpoint that covers both `Skin` and `Meningitis` sorts at the same position as a `Meningitis`-only breakpoint if `Meningitis` has a lower index.

---

## User-defined breakpoints

User-defined breakpoints:

- Always sort **ahead of all built-in breakpoints** (priority key = 0 vs. 1).
- Are always included regardless of the requested year filter.
- Have their `GUIDELINES` field overwritten to `"UserDefined"` when loaded.

This makes it straightforward to override a specific organism / drug breakpoint for local QC requirements without touching the built-in table.

---

## Worked example

**Input:** *E. coli* (`eco`), `AMP_ND10`, CLSI 2026, Human breakpoints, default site order.

1. **Filter**: Keep CLSI 2026 Human breakpoints where `WHONET_TEST = "AMP_ND10"` and the organism matches *E. coli* (via `WHONET_ORG_CODE`, `GENUS_CODE`, `FAMILY_CODE`, etc.).

2. **Sort**: The most specific match is the `EBC` (Enterobacteriaceae family) breakpoint. It sorts at organism specificity rank 6 (FAMILY_CODE). No serovar or species-group breakpoint exists for *E. coli* + AMP.

3. **Select**: One breakpoint is returned: `R≤13, I=14-16, S≥17` (disk).

4. **Interpret**: Measurement `"06"` → numeric `6`. Since `6 ≤ 13 (R)` → result is `"R"`.
