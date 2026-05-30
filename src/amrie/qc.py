"""Quality-control range data and interpretation.

Port of ``QualityControlRange.cs``. Loads ``resources/QC_Ranges.txt`` at import
time into :data:`QUALITY_CONTROL_RANGES` and provides two public functions:

* :func:`get_applicable_quality_control_range` — look up the most recent range
  for a reference strain / drug combination.
* :func:`get_quality_control_interpretation` — compare a measurement against that
  range and return ``"IN"``, ``"OUT"``, or ``""`` (uninterpretable).

QC interpretation follows the same modifier and rounding rules as clinical MIC
interpretation: ``>`` values are doubled before comparison, and E-test values are
rounded up to the next standard dilution when ``round_half_dilutions=True``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from amrie import constants as C
from amrie.antibiotic import TestMethods
from amrie.io_utils import get_resource_headers
from amrie.parsing import AntibioticComponents, parse_result, round_etest_half_dilutions_up
from amrie.paths import resource_path


@dataclass(frozen=True)
class QualityControlRange:
    """One row from ``resources/QC_Ranges.txt``.

    Defines the acceptable measurement range (``MINIMUM`` to ``MAXIMUM``) for a
    reference strain / drug / method combination.  If a QC measurement falls
    outside this range the associated run should be investigated.
    """
    GUIDELINE: str
    YEAR: int
    STRAIN: str
    REFERENCE_TABLE: str
    WHONET_ORG_CODE: str
    ANTIBIOTIC: str
    ABX_TEST: str
    WHONET_ABX_CODE: str
    METHOD: str
    MEDIUM: str
    MINIMUM: Decimal
    MAXIMUM: Decimal
    DATE_ENTERED: datetime
    DATE_MODIFIED: datetime
    COMMENTS: str


def _parse_decimal(value: str) -> Decimal:
    if not value or not value.strip():
        return Decimal(0)
    return Decimal(value.strip())


def _parse_int(value: str) -> int:
    if not value or not value.strip():
        return 0
    return int(value.strip())


def _parse_date(value: str) -> datetime:
    if not value or not value.strip():
        return datetime.min
    return datetime.fromisoformat(value.strip())


def load_quality_control_ranges(qc_table_file: str | Path | None = None) -> list[QualityControlRange]:
    """Load all rows from a QC ranges resource file.

    Args:
        qc_table_file: Path override for testing; defaults to the bundled
            ``QC_Ranges.txt`` resource.

    Returns:
        List of :class:`QualityControlRange` instances in file order.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(qc_table_file) if qc_table_file else resource_path("QC_Ranges.txt")
    if not path.exists():
        raise FileNotFoundError(str(path))

    df = pd.read_csv(
        path,
        sep=C.Delimiters.TAB_CHAR,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        quotechar=C.QUOTE,
    )
    header_map = get_resource_headers(list(df.columns))
    ranges: list[QualityControlRange] = []

    for _, row in df.iterrows():
        ranges.append(
            QualityControlRange(
                GUIDELINE=row.iloc[header_map["GUIDELINE"]],
                YEAR=_parse_int(row.iloc[header_map["YEAR"]]),
                STRAIN=row.iloc[header_map["STRAIN"]],
                REFERENCE_TABLE=row.iloc[header_map["REFERENCE_TABLE"]],
                WHONET_ORG_CODE=row.iloc[header_map["WHONET_ORG_CODE"]],
                ANTIBIOTIC=row.iloc[header_map["ANTIBIOTIC"]],
                ABX_TEST=row.iloc[header_map["ABX_TEST"]],
                WHONET_ABX_CODE=row.iloc[header_map["WHONET_ABX_CODE"]],
                METHOD=row.iloc[header_map["METHOD"]],
                MEDIUM=row.iloc[header_map["MEDIUM"]],
                MINIMUM=_parse_decimal(row.iloc[header_map["MINIMUM"]]),
                MAXIMUM=_parse_decimal(row.iloc[header_map["MAXIMUM"]]),
                DATE_ENTERED=_parse_date(row.iloc[header_map["DATE_ENTERED"]]),
                DATE_MODIFIED=_parse_date(row.iloc[header_map["DATE_MODIFIED"]]),
                COMMENTS=row.iloc[header_map["COMMENTS"]],
            )
        )
    return ranges


QUALITY_CONTROL_RANGES: list[QualityControlRange] = load_quality_control_ranges()


def get_applicable_quality_control_range(
    reference_strain: str,
    whonet_abx_full_drug_code: str,
    qc_ranges: list[QualityControlRange] | None = None,
) -> QualityControlRange | None:
    """Look up the most recent QC range for a strain / drug combination.

    Matches on strain code, drug code, guideline, and test method (case-
    insensitive).  When multiple entries match (different years), the one with
    the highest year is returned.

    Args:
        reference_strain: Reference strain identifier (e.g. ``"atcc25922"``).
        whonet_abx_full_drug_code: Full WHONET column name (e.g. ``"SAM_ND10"``).
        qc_ranges: Override the default :data:`QUALITY_CONTROL_RANGES` for
            testing.

    Returns:
        The most recent matching :class:`QualityControlRange`, or ``None`` if
        no match is found.
    """
    this_antibiotic = AntibioticComponents(whonet_abx_full_drug_code)
    strain_upper = reference_strain.upper()
    code_upper = this_antibiotic.code.upper()
    guideline_upper = this_antibiotic.guideline.upper()
    disk_method = TestMethods.DISK.upper()
    method_upper = (
        disk_method
        if this_antibiotic.test_method.upper() == disk_method
        else TestMethods.MIC.upper()
    )

    source = qc_ranges if qc_ranges is not None else QUALITY_CONTROL_RANGES
    matching = [
        qc
        for qc in source
        if qc.STRAIN.upper() == strain_upper
        and qc.WHONET_ABX_CODE.upper() == code_upper
        and qc.GUIDELINE.upper() == guideline_upper
        and qc.METHOD.upper() == method_upper
    ]
    if not matching:
        return None
    return max(matching, key=lambda qc: qc.YEAR)


def get_quality_control_interpretation(
    reference_strain: str,
    whonet_abx_full_drug_code: str,
    measurement: str,
    round_half_dilutions: bool = True,
) -> str:
    """Compare a QC measurement against the applicable range and return IN / OUT.

    Args:
        reference_strain: Reference strain code (e.g. ``"atcc25922"``).
        whonet_abx_full_drug_code: Full WHONET column name.
        measurement: Raw measurement string (e.g. ``"22"``, ``">16"``).
        round_half_dilutions: When ``True`` (default), E-test MIC values are
            rounded to the nearest standard dilution before comparison.

    Returns:
        ``"IN"`` if the measurement is within the acceptable range, ``"OUT"`` if
        outside, or ``""`` (uninterpretable) if the measurement cannot be parsed,
        the strain is unknown, or the drug has no QC range on file.
    """
    if not measurement or not measurement.strip():
        return C.InterpretationCodes.UNINTERPRETABLE

    matching_range = get_applicable_quality_control_range(reference_strain, whonet_abx_full_drug_code)
    if matching_range is None:
        return C.InterpretationCodes.UNINTERPRETABLE

    this_antibiotic = AntibioticComponents(whonet_abx_full_drug_code)
    parsed, numeric_result, modifier = parse_result(this_antibiotic.test_method, measurement)
    if not parsed:
        return C.InterpretationCodes.UNINTERPRETABLE

    if this_antibiotic.test_method == TestMethods.DISK:
        if numeric_result < matching_range.MINIMUM or numeric_result > matching_range.MAXIMUM:
            return C.InterpretationCodes.OUT_OF_RANGE
        return C.InterpretationCodes.IN_RANGE

    if this_antibiotic.test_method == TestMethods.MIC:
        temp_numeric = (
            round_etest_half_dilutions_up(numeric_result)
            if round_half_dilutions
            else numeric_result
        )

        if not modifier:
            if temp_numeric < matching_range.MINIMUM or temp_numeric > matching_range.MAXIMUM:
                return C.InterpretationCodes.OUT_OF_RANGE
            return C.InterpretationCodes.IN_RANGE

        if modifier.startswith(C.MeasurementModifiers.GREATER_THAN):
            temp_numeric *= Decimal(2)
            if temp_numeric < matching_range.MINIMUM or temp_numeric > matching_range.MAXIMUM:
                return C.InterpretationCodes.OUT_OF_RANGE
            return C.InterpretationCodes.IN_RANGE

        if temp_numeric < matching_range.MINIMUM or temp_numeric > matching_range.MAXIMUM:
            return C.InterpretationCodes.OUT_OF_RANGE
        return C.InterpretationCodes.IN_RANGE

    return C.InterpretationCodes.UNINTERPRETABLE
