"""Command-line interface for the AMRIE interpretation engine.

Port of ``Interpretation CLI/Program.cs``. Provides three sub-commands:

* ``file``   — interpret an entire delimited input file (FILE mode).
* ``single`` — interpret one organism / antibiotic / measurement triple.
* ``qc``     — evaluate a QC measurement against reference strain ranges.

Built with `Typer <https://typer.tiangolo.com/>`_.  The entry point
``amrie`` is registered by the ``pyproject.toml`` ``[project.scripts]`` table.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import orjson
import typer

from amrie import constants as C
from amrie.config import read_configuration
from amrie.io_library import FileInterpretationParameters, interpret_data_file
from amrie.isolate import IsolateInterpretation
from amrie.qc import get_quality_control_interpretation

app = typer.Typer(add_completion=False, help="AMRIE antimicrobial susceptibility interpretation engine")


def _resolve_delimiter(delimiter: str) -> str:
    """Normalise a CLI delimiter argument to a single character.

    Accepts the special token ``"TAB"`` (case-insensitive) as an alias for a
    literal tab character.  Any other value has its first character used, so
    passing ``"pipe"`` is the same as passing ``"|"``.

    Args:
        delimiter: Raw value from the ``--delimiter`` option.

    Returns:
        A single-character delimiter string.
    """
    if delimiter.upper() == C.Delimiters.TAB_PLACEHOLDER:
        return C.Delimiters.TAB_CHAR
    return delimiter[0]


@app.command("file")
def file_mode(
    config: Path = typer.Option(..., "--config", "-c", help="Path to JSON configuration file"),
    delimiter: str = typer.Option(..., "--delimiter", "-d", help="Field delimiter ('TAB' or single character)"),
    input: Path = typer.Option(..., "--input", "-i", help="Input data file"),
    output: Path = typer.Option(..., "--output", "-o", help="Output file path"),
) -> None:
    """Interpret an entire input file (FILE mode)."""
    params = FileInterpretationParameters(
        input_file=str(input),
        delimiter=_resolve_delimiter(delimiter),
        guideline_year=-1,
        config_file=str(config.resolve()),
        output_file=str(output),
    )
    interpret_data_file(params)
    typer.echo(f"Wrote interpretations to {output}")


@app.command("qc")
def qc_mode(
    organism: str = typer.Option(..., "--organism", help="Reference strain code (e.g. atcc25922)"),
    antibiotic: str = typer.Option(..., "--antibiotic", help="Full WHONET antibiotic column code"),
    measurement: str = typer.Option(..., "--measurement", "-m", help="Numeric measurement value"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Optional output JSON file path"),
    round_half_dilutions: bool = typer.Option(True, "--round-half-dilutions/--no-round-half-dilutions"),
) -> None:
    """Evaluate a QC measurement against reference strain ranges."""
    interpretation = get_quality_control_interpretation(
        organism,
        antibiotic,
        measurement,
        round_half_dilutions=round_half_dilutions,
    )
    typer.echo(interpretation)

    if output is not None:
        result = {
            "ReferenceStrain": organism,
            "AntibioticCode": antibiotic,
            "Measurement": measurement,
            "Interpretation": interpretation,
        }
        with open(output, "wb") as f:
            f.write(orjson.dumps(result, option=orjson.OPT_INDENT_2))
            f.write(b"\n")


@app.command("single")
def single_mode(
    config: Path = typer.Option(..., "--config", "-c", help="Path to JSON configuration file"),
    organism: str = typer.Option(..., "--organism", help="WHONET organism code"),
    antibiotic: str = typer.Option(..., "--antibiotic", help="Full WHONET antibiotic column code"),
    measurement: str = typer.Option(..., "--measurement", "-m", help="Numeric measurement value"),
    output: Path = typer.Option(..., "--output", "-o", help="Output JSON file path"),
) -> None:
    """Interpret a single organism/antibiotic/measurement (SINGLE_INTERPRETATION mode)."""
    interpretation_config = read_configuration(config.resolve())
    interpretation = IsolateInterpretation.get_single_interpretation(
        interpretation_config,
        organism,
        antibiotic,
        measurement,
    )

    if not interpretation_config.include_interpretation_comments:
        interpretation = IsolateInterpretation.remove_comments(interpretation)

    result = {
        "OrganismCode": organism,
        "AntibioticCode": antibiotic,
        "Measurement": measurement,
        "Interpretation": interpretation,
    }

    typer.echo(interpretation)
    with open(output, "wb") as f:
        f.write(orjson.dumps(result, option=orjson.OPT_INDENT_2))
        f.write(b"\n")


if __name__ == "__main__":
    app()
