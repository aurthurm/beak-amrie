# Upstream C# Sync Tracker

This file records which commit of the upstream C# AMRIE project was used as the
basis for each change to this Python port. When the C# project is updated, start
your diff from the **"Last synced commit"** below to find only the new changes.

**Upstream repository:** https://github.com/AClark-WHONET/AMRIE

---

## Current sync state

| Field | Value |
|---|---|
| **Last synced commit** | `69de20193a5508e153631fa8bdd46c27baadcb40` |
| **Short hash** | `69de201` |
| **Date** | 2026-05-19 |
| **Author** | AClark (`aclark@whonet.org`) |
| **Commit message** | Removes EUCAST SXT and TMP breakpoints for Enterococcus spp. which have been replaced by a note. |
| **Synced on** | 2026-05-30 |
| **Synced by** | Initial Python port |

---

## How to check for upstream changes

```bash
# In the cloned C# repo:
cd /path/to/AMRIE

# Show everything after the last synced commit
git log 69de201..HEAD --oneline

# Show only changes to source files (ignore installer / CI / docs)
git log 69de201..HEAD --oneline -- \
  "Interpretation Engine/" \
  "Interpretation CLI/"

# Full diff of interpretation logic since last sync
git diff 69de201..HEAD -- \
  "Interpretation Engine/" \
  "Interpretation CLI/"
```

---

## Sync log

Each entry records what changed in the C# project and what was done in this port.

| Date | C# commit range | Summary | Python files changed |
|---|---|---|---|
| 2026-05-30 | — (initial port) | Full 1:1 port of the C# engine at `69de201` | All `src/amrie/*.py` files |

---

## Sync procedure

When upstream commits are detected, follow these steps:

### 1. Identify the relevant commits

```bash
git log 69de201..HEAD --oneline -- "Interpretation Engine/" "Interpretation CLI/"
```

Focus on files that map to Python logic (see
[C# → Python mapping](architecture.md#c--python-mapping)). Ignore:

- `AMR Interpretation Engine Windows Installer/` — no Python equivalent
- `Interpretation Interface/` — GUI only, not ported
- `.github/`, `*.yml` — CI/packaging, not ported

### 2. Apply the change

Translate the C# diff into the corresponding Python module. The
[architecture doc](architecture.md#c--python-mapping) lists which C# file maps
to which Python module.

Key things to check:

| C# change type | Python impact |
|---|---|
| New/changed breakpoint data (`Breakpoints.txt`) | Replace resource file; update `BREAKPOINT_TABLE_REVISION_YEAR` in `constants.py` |
| Organism data change (`Organisms.txt`) | Replace resource file |
| New intrinsic resistance rule | Replace `ExpectedResistancePhenotypes.txt` |
| New expert rule | Replace `ExpertInterpretationRules.txt`; may need logic change in `expert_rule.py` |
| Interpretation logic change | Update the corresponding module |
| New QC ranges | Replace `QC_Ranges.txt` |

### 3. Update tests

- Add or update test cases in `tests/test_parity.py` or `tests/test_qc.py`.
- For breakpoint data changes, regenerate the golden file:

  ```bash
  rm tests/fixtures/golden_sample_output.txt
  pytest tests/test_parity.py::TestGoldenFile -v   # creates the file
  pytest tests/test_parity.py::TestGoldenFile -v   # must pass now
  ```

### 4. Update this file

Update the **Current sync state** table at the top of this document with the new commit hash, date, and summary. Append a row to the **Sync log** table.

```markdown
| 2026-XX-XX | 69de201..NEWHASH | Brief description | e.g. breakpoint.py, constants.py |
```
