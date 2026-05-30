# CLI Reference

The `amrie` command-line tool is installed as an entry point by `pyproject.toml`.

```
Usage: amrie [OPTIONS] COMMAND [ARGS]...

  AMRIE antimicrobial susceptibility interpretation engine

Options:
  --help  Show this message and exit.

Commands:
  file    Interpret an entire input file (FILE mode).
  single  Interpret a single organism/antibiotic/measurement.
  qc      Evaluate a QC measurement against reference strain ranges.
```

---

## `amrie file`

Interpret an entire delimited input file. Writes an output file with interpretation columns added.

```
Usage: amrie file [OPTIONS]

  Interpret an entire input file (FILE mode).

Options:
  -c, --config PATH       Path to JSON configuration file  [required]
  -d, --delimiter TEXT    Field delimiter ('TAB' or single character)  [required]
  -i, --input PATH        Input data file  [required]
  -o, --output PATH       Output file path  [required]
  --help                  Show this message and exit.
```

### Examples

Tab-delimited input:

```bash
amrie file \
  --config config.json \
  --delimiter TAB \
  --input data.txt \
  --output results.txt
```

Pipe-delimited input:

```bash
amrie file \
  --config config.json \
  --delimiter "|" \
  --input data.txt \
  --output results.txt
```

Comma-delimited input:

```bash
amrie file \
  --config config.json \
  --delimiter "," \
  --input data.csv \
  --output results.csv
```

### Output

Prints `Wrote interpretations to <output>` on success.

The output format (horizontal vs. vertical) is controlled by `HorizontalAntibioticResults` in the config. See [`data-formats.md`](data-formats.md) for examples.

---

## `amrie single`

Interpret one organism / antibiotic / measurement combination.

```
Usage: amrie single [OPTIONS]

  Interpret a single organism/antibiotic/measurement (SINGLE_INTERPRETATION mode).

Options:
  -c, --config PATH       Path to JSON configuration file  [required]
      --organism TEXT     WHONET organism code  [required]
      --antibiotic TEXT   Full WHONET antibiotic column code  [required]
  -m, --measurement TEXT  Numeric measurement value  [required]
  -o, --output PATH       Output JSON file path  [required]
  --help                  Show this message and exit.
```

### Examples

Disk measurement:

```bash
amrie single \
  --config config.json \
  --organism eco \
  --antibiotic AMP_ND10 \
  --measurement 8 \
  --output result.json
```

MIC with modifier:

```bash
amrie single \
  --config config.json \
  --organism kpn \
  --antibiotic CTX_NM \
  --measurement "<=0.25" \
  --output result.json
```

### Output

Prints the interpretation code (`S`, `R`, etc.) to stdout.

Writes a JSON file:

```json
{
  "OrganismCode": "eco",
  "AntibioticCode": "AMP_ND10",
  "Measurement": "8",
  "Interpretation": "R"
}
```

The `*` / `!` suffixes are included or stripped based on `IncludeInterpretationComments` in the config.

---

## `amrie qc`

Evaluate a QC reference-strain measurement against the published acceptable range.

```
Usage: amrie qc [OPTIONS]

  Evaluate a QC measurement against reference strain ranges.

Options:
      --organism TEXT                 Reference strain code (e.g. atcc25922)  [required]
      --antibiotic TEXT               Full WHONET antibiotic column code  [required]
  -m, --measurement TEXT              Numeric measurement value  [required]
  -o, --output PATH                   Optional output JSON file path
      --round-half-dilutions          Round E-test half-dilutions up (default)
      --no-round-half-dilutions       Disable E-test rounding
  --help                              Show this message and exit.
```

### Examples

Disk diffusion QC:

```bash
amrie qc \
  --organism atcc25922 \
  --antibiotic SAM_ND10 \
  --measurement 22
```

MIC QC without output file:

```bash
amrie qc \
  --organism atcc25922 \
  --antibiotic AMP_NM \
  --measurement 4
```

### Output

Prints `IN`, `OUT`, or blank (uninterpretable) to stdout.

When `--output` is provided, also writes:

```json
{
  "ReferenceStrain": "atcc25922",
  "AntibioticCode": "SAM_ND10",
  "Measurement": "22",
  "Interpretation": "IN"
}
```

---

## Delimiter handling

The `--delimiter` option accepts:

| Input | Interpreted as |
|---|---|
| `TAB` (case-insensitive) | Tab character `\t` |
| `\|` | Pipe `|` |
| `,` | Comma `,` |
| Any single character | That character |

Note: pass pipe on the shell as `"|"` or `\|` to avoid shell interpretation.

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Unhandled exception (file not found, invalid config, etc.) |
