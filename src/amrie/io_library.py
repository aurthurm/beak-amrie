"""Batch file interpretation pipeline.

Port of the private ``IO_Library`` methods in ``IO_Library.cs``:
``LoadInputFile``, ``InterpretIsolates``, and ``GenerateOutputFile``.

The public entry point for file-mode interpretation is :func:`interpret_data_file`.
The individual steps are also exported so callers (including tests) can compose
them independently:

1. :func:`load_input_file` — parse the input TSV / delimited file into row
   dictionaries.
2. :func:`interpret_isolates` — interpret all rows, optionally in parallel.
3. :func:`generate_output_file` — write results to a delimited output file in
   horizontal or vertical layout.

**Horizontal layout** (``HorizontalAntibioticResults = true``): the output keeps
the same column order as the input, with a ``<drug>_INTERP`` column inserted
immediately after each measurement column.

**Vertical layout** (``HorizontalAntibioticResults = false``): antibiotic columns
are removed from the output and replaced with three fixed columns
(``ANTIBIOTIC_CODE``, ``ANTIBIOTIC_MEASUREMENT``, ``ANTIBIOTIC_INTERPRETATION``),
with one output row produced per antibiotic measurement.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from amrie import constants as C
from amrie.antibiotic_rules import preheat_breakpoint_cache
from amrie.config import InterpretationConfiguration, read_configuration
from amrie.io_utils import split_line, to_line
from amrie.isolate import IsolateInterpretation
from amrie.parsing import VALID_ANTIBIOTIC_FIELD_NAME_REGEX, AntibioticComponents


class OutputAntibioticColumns:
    """Column name constants for vertical-layout output files."""
    ANTIBIOTIC_CODE = "ANTIBIOTIC_CODE"
    ANTIBIOTIC_MEASUREMENT = "ANTIBIOTIC_MEASUREMENT"
    ANTIBIOTIC_INTERPRETATION = "ANTIBIOTIC_INTERPRETATION"
    VERTICAL_ANTIBIOTIC_FIELDS = [
        ANTIBIOTIC_CODE,
        ANTIBIOTIC_MEASUREMENT,
        ANTIBIOTIC_INTERPRETATION,
    ]


@dataclass
class FileInterpretationParameters:
    """Parameters for a single file-mode interpretation job.

    Attributes:
        input_file: Path to the input delimited data file.
        delimiter: Single-character field separator (e.g. ``"|"`` or ``"\\t"``).
        guideline_year: Override the config year; pass ``-1`` to use the value
            from the config file.
        config_file: Path to the JSON configuration file.
        output_file: Destination path for the output file.
    """
    input_file: str
    delimiter: str
    guideline_year: int
    config_file: str
    output_file: str


def load_input_file(
    input_file: str,
    delimiter: str,
) -> tuple[list[str], list[dict[str, str]]]:
    """Parse a delimited data file into column names and row dictionaries.

    Locates the first non-blank line and treats it as the header.  Subsequent
    lines are parsed into dictionaries keyed by column name; blank-value fields
    are omitted from each dictionary.

    Args:
        input_file: Path to the input file.
        delimiter: Single-character field separator.

    Returns:
        A 2-tuple ``(column_names, rows)`` where *column_names* is the ordered
        list of header fields and *rows* is a list of non-blank data rows, each
        represented as a ``{column_name: value}`` dictionary.
    """
    input_column_names: list[str] = []
    row_value_sets: list[dict[str, str]] = []
    headers: dict[int, str] = {}

    with open(input_file, encoding="utf-8", newline="") as f:
        lines = f.read().splitlines()

    if not lines:
        return input_column_names, row_value_sets

    data_start = 0
    for i, line in enumerate(lines):
        fields = split_line(line, delimiter)
        if any(not f.isspace() and f for f in fields):
            for x, name in enumerate(fields):
                headers[x] = name
            data_start = i + 1
            break

    input_column_names = list(headers.values())
    num_columns = len(input_column_names)

    for line in lines[data_start:]:
        values = split_line(line, delimiter)
        if len(values) >= num_columns and any(v.strip() for v in values):
            row_values: dict[str, str] = {}
            for x in range(len(values)):
                if x in headers and values[x].strip():
                    row_values[headers[x]] = values[x]
            row_value_sets.append(row_values)

    return input_column_names, row_value_sets


def _collect_distinct_interpretation_keys(
    row_value_sets: list[dict[str, str]],
) -> list[tuple[str, str, str]]:
    """Collect unique ``(organism, guideline, drug_column)`` keys across all rows.

    Used to pre-populate the breakpoint cache before parallel processing begins,
    so that worker threads never need to compute breakpoints (and contend on the
    cache lock) during the main interpretation loop.
    """
    keys: set[tuple[str, str, str]] = set()
    for row in row_value_sets:
        antibiotic_fields = [k for k in row if VALID_ANTIBIOTIC_FIELD_NAME_REGEX.match(k)]
        if C.KeyFields.ORGANISM not in row or not antibiotic_fields:
            continue
        organism = row[C.KeyFields.ORGANISM].strip()
        for drug in antibiotic_fields:
            abx = AntibioticComponents(drug)
            keys.add((organism, abx.guideline, drug))
    return list(keys)


def _interpret_row(
    row: dict[str, str],
    input_column_names: list[str],
    interpretation_config: InterpretationConfiguration,
    year: int,
) -> tuple[dict[str, str], dict[str, str]]:
    """Interpret a single data row and return ``(original_row, interpretations)``."""
    interp = IsolateInterpretation(
        row,
        input_column_names,
        interpretation_config.enabled_expert_interpretation_rules,
        interpretation_config.user_defined_breakpoints,
        guideline_year=year,
        use_intrinsic_resistance_rules=interpretation_config.use_intrinsic_resistance_rules,
        prioritized_breakpoint_types=interpretation_config.prioritized_breakpoint_types,
        prioritized_sites_of_infection=interpretation_config.prioritized_sites_of_infection,
    ).get_all_interpretations()
    return row, interp


def interpret_isolates(
    interpretation_config: InterpretationConfiguration,
    input_column_names: list[str],
    row_value_sets: list[dict[str, str]],
    guideline_year: int = -1,
    parallel: bool = True,
) -> list[tuple[dict[str, str], dict[str, str]]]:
    """Interpret all isolate rows, with optional parallel processing.

    Pre-heats the breakpoint cache before dispatching rows to a
    :class:`~concurrent.futures.ThreadPoolExecutor` (when ``parallel=True`` and
    there are at least two rows).  Results are returned in the same order as
    *row_value_sets*.

    Args:
        interpretation_config: Engine configuration.
        input_column_names: Ordered list of header column names.
        row_value_sets: List of row dictionaries from :func:`load_input_file`.
        guideline_year: Override the config year; ``-1`` uses the config value.
        parallel: When ``True`` (default), rows are interpreted concurrently.

    Returns:
        List of ``(original_row, interpretations)`` 2-tuples in input order.
    """
    year = (
        guideline_year
        if guideline_year != -1
        else int(interpretation_config.guideline_year)
    )

    distinct_keys = _collect_distinct_interpretation_keys(row_value_sets)
    preheat_breakpoint_cache(
        interpretation_config.user_defined_breakpoints,
        year,
        interpretation_config.prioritized_breakpoint_types,
        interpretation_config.prioritized_sites_of_infection,
        distinct_keys,
    )

    if not row_value_sets:
        return []

    if not parallel or len(row_value_sets) < 2:
        return [
            _interpret_row(row, input_column_names, interpretation_config, year)
            for row in row_value_sets
        ]

    max_workers = min(32, (os.cpu_count() or 1) + 4, len(row_value_sets))
    results: list[tuple[dict[str, str], dict[str, str]] | None] = [None] * len(row_value_sets)

    def _process_index(index: int) -> None:
        results[index] = _interpret_row(
            row_value_sets[index],
            input_column_names,
            interpretation_config,
            year,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(_process_index, range(len(row_value_sets))))

    return [r for r in results if r is not None]


def generate_output_file(
    output_file: str,
    interpretation_config: InterpretationConfiguration,
    input_column_names: list[str],
    interpretation_results: list[tuple[dict[str, str], dict[str, str]]],
) -> None:
    """Write interpretation results to a tab-delimited output file.

    **Horizontal mode** (``interpretation_config.horizontal_antibiotic_results``
    is ``True``): a ``<drug>_INTERP`` column is inserted immediately after each
    measurement column.

    **Vertical mode**: antibiotic measurement columns are removed; one output row
    is produced per antibiotic with three appended columns — ``ANTIBIOTIC_CODE``,
    ``ANTIBIOTIC_MEASUREMENT``, and ``ANTIBIOTIC_INTERPRETATION``.  Rows with no
    antibiotic data produce one blank row.

    When ``interpretation_config.include_interpretation_comments`` is ``False``,
    ``"*"`` and ``"!"`` suffixes are stripped from all interpretation values
    before writing.

    Args:
        output_file: Destination file path (overwritten if it exists).
        interpretation_config: Controls layout and comment stripping.
        input_column_names: Header columns from the original input file.
        interpretation_results: Output of :func:`interpret_isolates`.
    """
    interp_suffix = "_INTERP"

    interpretation_headers = list(
        dict.fromkeys(k for _, interps in interpretation_results for k in interps)
    )

    output_headers = list(input_column_names)
    antibiotic_fields: list[str] | None = None

    if interpretation_config.horizontal_antibiotic_results:
        for interp_header in interpretation_headers:
            for x, h in enumerate(output_headers):
                if h == interp_header:
                    output_headers.insert(x + 1, interp_header + interp_suffix)
                    break
    else:
        antibiotic_fields = [h for h in output_headers if VALID_ANTIBIOTIC_FIELD_NAME_REGEX.match(h)]
        output_headers = [
            h for h in output_headers if h not in antibiotic_fields
        ] + OutputAntibioticColumns.VERTICAL_ANTIBIOTIC_FIELDS

    with open(output_file, "w", encoding="utf-8", newline="") as writer:
        writer.write(to_line(output_headers, C.Delimiters.TAB_CHAR) + "\n")

        for row, interps in interpretation_results:
            if interpretation_config.horizontal_antibiotic_results:
                this_row: list[str] = []
                for h in output_headers:
                    if h in row:
                        this_row.append(row[h])
                    elif h.endswith(interp_suffix):
                        drug_code = h[: -len(interp_suffix)]
                        if drug_code in interps:
                            interp = interps[drug_code]
                            if not interpretation_config.include_interpretation_comments:
                                interp = IsolateInterpretation.remove_comments(interp)
                            this_row.append(interp)
                        else:
                            this_row.append("")
                    else:
                        this_row.append("")
                writer.write(to_line(this_row, C.Delimiters.TAB_CHAR) + "\n")
            else:
                repeated: list[str] = []
                for h in output_headers[:-3]:
                    repeated.append(row.get(h, ""))
                repeated_str = to_line(repeated, C.Delimiters.TAB_CHAR)

                assert antibiotic_fields is not None
                if not any(a in row for a in antibiotic_fields):
                    blank = to_line(["", "", ""], C.Delimiters.TAB_CHAR)
                    writer.write(repeated_str + C.Delimiters.TAB_CHAR + blank + "\n")
                else:
                    for antibiotic in antibiotic_fields:
                        if antibiotic not in row:
                            continue
                        abx_row = [antibiotic, row[antibiotic]]
                        if antibiotic in interps:
                            interp = interps[antibiotic]
                            if not interpretation_config.include_interpretation_comments:
                                interp = IsolateInterpretation.remove_comments(interp)
                            abx_row.append(interp)
                        else:
                            abx_row.append("")
                        writer.write(
                            repeated_str
                            + C.Delimiters.TAB_CHAR
                            + to_line(abx_row, C.Delimiters.TAB_CHAR)
                            + "\n"
                        )


def interpret_data_file(params: FileInterpretationParameters) -> None:
    """Run the complete file-mode interpretation pipeline.

    Convenience wrapper that calls :func:`load_input_file`,
    :func:`interpret_isolates`, and :func:`generate_output_file` in sequence
    using the configuration read from *params.config_file*.

    Args:
        params: Job parameters including input/output paths, delimiter, and
            config file path.
    """
    interpretation_config = read_configuration(params.config_file)
    input_column_names, row_value_sets = load_input_file(params.input_file, params.delimiter)
    interpretation_results = interpret_isolates(
        interpretation_config,
        input_column_names,
        row_value_sets,
        guideline_year=params.guideline_year,
    )
    generate_output_file(
        params.output_file,
        interpretation_config,
        input_column_names,
        interpretation_results,
    )
