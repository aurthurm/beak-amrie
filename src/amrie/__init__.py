"""AMRIE — Antimicrobial Resistance Interpretation Engine.

Python port of the open-source C# AMRIE project.  Interprets antimicrobial
susceptibility measurements against CLSI / EUCAST / SFM / SRGA / BSAC / DIN /
NEO / AFA breakpoints and applies expert interpretation rules (ESBL, MRS, ICR,
BLNAR).

**Public API**

The three functions below cover the most common use cases:

* :func:`interpret_single` — interpret one measurement for one organism /
  antibiotic combination.
* :func:`interpret_file` — read a delimited input file and write an output file
  with interpretation columns added.
* :func:`interpret_qc_single` — evaluate a QC measurement for a reference strain.

:class:`InterpretationConfig` (alias for :class:`~amrie.config.InterpretationConfiguration`)
is the configuration object used by all three functions.  Load it from a JSON file
with :func:`~amrie.config.read_configuration` or create one programmatically.

**Example**::

    from amrie import interpret_single, InterpretationConfig
    from amrie.config import read_configuration

    config = read_configuration("my_config.json")
    result = interpret_single(config, "eco", "AMP_ND10", "8")  # "R"
"""

from __future__ import annotations

from pathlib import Path

from amrie import constants as C
from amrie.config import InterpretationConfiguration, read_configuration
from amrie.io_library import FileInterpretationParameters, interpret_data_file
from amrie.isolate import IsolateInterpretation
from amrie.qc import get_quality_control_interpretation

__version__ = "1.0.0"

InterpretationConfig = InterpretationConfiguration
"""Alias for :class:`~amrie.config.InterpretationConfiguration`."""


def interpret_single(
    config: InterpretationConfiguration | str | Path,
    organism: str,
    antibiotic: str,
    measurement: str,
) -> str:
    """Interpret a single organism / antibiotic / measurement.

    Args:
        config: An :class:`~amrie.config.InterpretationConfiguration` instance,
            or a path to a JSON configuration file.
        organism: WHONET organism code (e.g. ``"eco"``).
        antibiotic: Full WHONET antibiotic column name (e.g. ``"AMP_ND10"``).
        measurement: Raw measurement string (e.g. ``"19"``, ``"<4"``).

    Returns:
        Interpretation string such as ``"S"``, ``"I"``, ``"R"``, ``"R*"``,
        ``"R!"``, or ``""`` (uninterpretable).
    """
    if not isinstance(config, InterpretationConfiguration):
        config = read_configuration(config)
    return IsolateInterpretation.get_single_interpretation(
        config,
        organism,
        antibiotic,
        measurement,
    )


def interpret_file(
    config: InterpretationConfiguration | str | Path,
    input_file: str | Path,
    output_file: str | Path,
    delimiter: str = C.Delimiters.TAB_CHAR,
    guideline_year: int = -1,
) -> None:
    """Interpret an input file and write results to an output file.

    Args:
        config: An :class:`~amrie.config.InterpretationConfiguration` instance,
            or a path to a JSON configuration file.
        input_file: Path to the delimited input data file.
        output_file: Destination path for the output file (created or overwritten).
        delimiter: Single-character field separator used in both input and output
            files.  Defaults to tab.
        guideline_year: Override the config guideline year; ``-1`` uses the value
            from the config.
    """
    config_path = str(config) if not isinstance(config, InterpretationConfiguration) else ""
    params = FileInterpretationParameters(
        input_file=str(input_file),
        delimiter=delimiter,
        guideline_year=guideline_year,
        config_file=config_path or "",
        output_file=str(output_file),
    )
    if isinstance(config, InterpretationConfiguration):
        from amrie.io_library import generate_output_file, interpret_isolates, load_input_file

        input_column_names, row_value_sets = load_input_file(params.input_file, params.delimiter)
        interpretation_results = interpret_isolates(
            config,
            input_column_names,
            row_value_sets,
            guideline_year=params.guideline_year,
        )
        generate_output_file(
            params.output_file,
            config,
            input_column_names,
            interpretation_results,
        )
    else:
        params.config_file = str(Path(config).resolve())
        interpret_data_file(params)


def interpret_qc_single(
    organism: str,
    antibiotic: str,
    measurement: str,
    round_half_dilutions: bool = True,
) -> str:
    """Evaluate a QC measurement for a reference strain and antibiotic.

    Args:
        organism: Reference strain identifier (e.g. ``"atcc25922"``).
        antibiotic: Full WHONET antibiotic column name (e.g. ``"SAM_ND10"``).
        measurement: Raw measurement string.
        round_half_dilutions: When ``True`` (default), E-test MIC values are
            rounded to the nearest standard dilution before comparison.

    Returns:
        ``"IN"`` if within range, ``"OUT"`` if outside, or ``""`` if the
        measurement cannot be interpreted.
    """
    return get_quality_control_interpretation(
        organism,
        antibiotic,
        measurement,
        round_half_dilutions=round_half_dilutions,
    )


__all__ = [
    "InterpretationConfig",
    "InterpretationConfiguration",
    "interpret_single",
    "interpret_file",
    "interpret_qc_single",
    "__version__",
]
