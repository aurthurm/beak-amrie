"""Antibiotic column-name parsing and numeric result parsing.

Port of ``AntibioticComponents.cs`` and ``InterpretationLibrary.cs``.

A WHONET antibiotic column name encodes the drug, guideline, and test method in a
compact form (e.g. ``"AMP_ND10"``):

* Standard drug:  ``<3-letter code>_<guideline><method>[<potency>]``
  → ``AMP_ND10`` = ampicillin, CLSI (N), disk (D), 10 µg.
* User-defined:   ``X_<number>_<guideline><method>[<potency>]``
  → ``X_1_NM`` = user-defined drug #1, CLSI (N), MIC (M).

:class:`AntibioticComponents` parses the column name into its parts.
:func:`parse_result` converts a raw measurement string into a normalised numeric
value and optional modifier (``"<"``, ``"<="`` etc.).
:func:`round_etest_half_dilutions_up` snaps a continuous E-test MIC value to the
nearest standard MIC dilution step.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from amrie import constants as C
from amrie.antibiotic import GuidelineNames, TestMethods
from amrie.io_utils import split_line, to_line

_USER_DEFINED_ANTIBIOTIC = "X"
"""Prefix that identifies a user-defined (non-WHONET) antibiotic column."""

NUMERIC_ANTIBIOTIC_RESULT_REGEX = re.compile(
    r"^(|<|>)(|=)(\d+|(|\d+)\.\d+)$",
    re.IGNORECASE,
)
"""Matches any result string that can be parsed as a numeric measurement.

Groups: (optional ``<``/``>``)(optional ``=``)(integer or decimal).
"""

_GUIDELINE_PATTERN = "|".join(re.escape(c) for c in "NEFSDTBA")
VALID_ANTIBIOTIC_FIELD_NAME_REGEX = re.compile(
    rf"^([A-Z]{{3}}|X_\d+)_({_GUIDELINE_PATTERN})(D.*|M|E)$",
    re.IGNORECASE,
)
"""Matches a complete WHONET antibiotic column name (e.g. ``"AMP_ND10"``, ``"X_1_NM"``)."""

VALID_ANTIBIOTIC_CODE_REGEX = re.compile(
    r"^([A-Z]{3}|X_\d+)$",
    re.IGNORECASE,
)
"""Matches only the drug-code portion of a WHONET column name (e.g. ``"AMP"``)."""


class AntibioticComponents:
    """Parsed components of a WHONET antibiotic column name.

    Breaks a full column name (e.g. ``"AMP_ND10"``) into its constituent parts:
    the drug code, the guideline name, and the test method. Handles both standard
    three-letter codes and user-defined ``X_<n>`` codes.

    Attributes:
        code: Drug code (``"AMP"`` for standard; ``"X_1"`` for user-defined).
        guideline: Full guideline name (e.g. ``"CLSI"``).
        test_method: Canonical test method (``"DISK"`` or ``"MIC"``).
    """

    def __init__(self, whonet_antibiotic_full_code: str) -> None:
        """Parse *whonet_antibiotic_full_code* into its components.

        Args:
            whonet_antibiotic_full_code: A valid WHONET antibiotic column name
                (e.g. ``"AMP_ND10"``, ``"PEN_EM"``, ``"X_1_NM"``).

        Raises:
            ValueError: If the embedded guideline or test-method code is not
                recognised.
        """
        abx_components = split_line(whonet_antibiotic_full_code, C.Delimiters.UNDERSCORE)
        self.code = abx_components[0]

        if self.code == _USER_DEFINED_ANTIBIOTIC:
            self.code = to_line([abx_components[0], abx_components[1]], C.Delimiters.UNDERSCORE)
            guideline_code = abx_components[2][0]
            self.test_method = TestMethods.get_test_method_from_code(abx_components[2][1])
        else:
            guideline_code = abx_components[1][0]
            self.test_method = TestMethods.get_test_method_from_code(abx_components[1][1])

        self.guideline = GuidelineNames.get_guideline_from_code(guideline_code)


def parse_result(
    test_method: str,
    result_string: str,
) -> tuple[bool, Decimal, str | None]:
    """Parse a raw measurement string into a normalised numeric value and modifier.

    Handles common data-entry errors (swapped ``=<`` / ``=>`` ordering, Unicode
    ``≤`` / ``≥`` symbols) before parsing. For MIC / E-test results, converts
    ``<value`` to ``<= value/2`` and ``>=value`` to ``> value/2`` to align with
    the standard interpretation convention used by CLSI and EUCAST.

    Args:
        test_method: ``"DISK"`` or ``"MIC"`` (E-test is treated as MIC).
        result_string: Raw measurement from the input file (e.g. ``"19"``,
            ``"<4"``, ``">=8"``, ``"0.25"``).

    Returns:
        A 3-tuple ``(success, numeric_value, modifier)`` where:

        * *success* is ``True`` when the result was successfully parsed.
        * *numeric_value* is the normalised :class:`~decimal.Decimal` value
          (``Decimal(0)`` on failure).
        * *modifier* is the remaining operator string after normalisation
          (``None``, ``"<="`` or ``">"``) or ``None`` for disk results.
    """
    numeric_result = Decimal(0)
    modifier: str | None = None

    if not result_string or not result_string.strip():
        return False, numeric_result, modifier

    result_string = result_string.strip()

    result_string = result_string.replace(
        C.MeasurementModifiers.EQUALS_SIGN + C.MeasurementModifiers.LESS_THAN,
        C.MeasurementModifiers.LESS_THAN + C.MeasurementModifiers.EQUALS_SIGN,
    )
    result_string = result_string.replace(
        C.MeasurementModifiers.EQUALS_SIGN + C.MeasurementModifiers.GREATER_THAN,
        C.MeasurementModifiers.GREATER_THAN + C.MeasurementModifiers.EQUALS_SIGN,
    )
    result_string = result_string.replace(
        C.MeasurementModifiers.Invalid.LESS_THAN_OR_EQUAL_TO,
        C.MeasurementModifiers.LESS_THAN + C.MeasurementModifiers.EQUALS_SIGN,
    )
    result_string = result_string.replace(
        C.MeasurementModifiers.Invalid.GREATER_THAN_OR_EQUAL_TO,
        C.MeasurementModifiers.GREATER_THAN + C.MeasurementModifiers.EQUALS_SIGN,
    )

    if not NUMERIC_ANTIBIOTIC_RESULT_REGEX.match(result_string):
        return False, numeric_result, modifier

    if test_method == TestMethods.DISK:
        try:
            temp = Decimal(result_string)
        except InvalidOperation:
            return False, numeric_result, modifier
        if C.Disk.MINIMUM_DISK_MEASUREMENT <= temp <= C.Disk.MAXIMUM_DISK_MEASUREMENT:
            return True, temp, None
        return False, numeric_result, modifier

    if test_method == TestMethods.MIC:
        numeric_start_index = 0
        if result_string.startswith(C.MeasurementModifiers.LESS_THAN) or result_string.startswith(
            C.MeasurementModifiers.GREATER_THAN
        ):
            if len(result_string) > 2 and result_string[1] == C.MeasurementModifiers.EQUALS_SIGN:
                numeric_start_index = 2
            else:
                numeric_start_index = 1
            modifier = result_string[:numeric_start_index]
        elif result_string.startswith(C.MeasurementModifiers.EQUALS_SIGN):
            modifier = result_string[:1]
            numeric_start_index = 1

        numeric_part = result_string[numeric_start_index:]
        if not numeric_part or not numeric_part.strip():
            return False, numeric_result, modifier

        try:
            temp_numeric = Decimal(numeric_part)
        except InvalidOperation:
            return False, numeric_result, modifier

        if temp_numeric <= 0:
            return False, numeric_result, modifier

        if modifier in (
            None,
            "",
            C.MeasurementModifiers.EQUALS_SIGN,
            C.MeasurementModifiers.LESS_THAN + C.MeasurementModifiers.EQUALS_SIGN,
            C.MeasurementModifiers.GREATER_THAN,
        ):
            pass
        elif modifier == C.MeasurementModifiers.LESS_THAN:
            # <8 means the true MIC is below 8; per convention this is stored as <=4.
            temp_numeric /= Decimal(2)
            modifier = C.MeasurementModifiers.LESS_THAN + C.MeasurementModifiers.EQUALS_SIGN
        elif modifier == C.MeasurementModifiers.GREATER_THAN + C.MeasurementModifiers.EQUALS_SIGN:
            # >=8 means the true MIC is at or above 8; stored as >4 for comparison.
            temp_numeric /= Decimal(2)
            modifier = C.MeasurementModifiers.GREATER_THAN
        else:
            return False, numeric_result, modifier

        return True, temp_numeric, modifier

    return False, numeric_result, modifier


def round_etest_half_dilutions_up(numeric_measurement: Decimal) -> Decimal:
    """Snap an E-test MIC value to the next standard MIC dilution step.

    E-test strips can produce values that fall between standard two-fold MIC
    dilution steps (e.g. 0.19, 3, 6).  The standard practice is to round up to
    the next full dilution before comparing with breakpoints.  A small number of
    high fixed concentrations (500, 1000) used for gentamicin high-level synergy
    (GEH), streptomycin high-level synergy (STH), and kanamycin high-level
    synergy (KAH) are returned unchanged.

    Args:
        numeric_measurement: Raw MIC value from an E-test strip.

    Returns:
        The value rounded up to the nearest standard dilution step.
    """
    m = numeric_measurement
    if m in (Decimal("500"), Decimal("1000")):
        return m
    if m <= Decimal("0.001"):
        return m
    if m <= Decimal("0.002"):
        return Decimal("0.002")
    if m <= Decimal("0.004"):
        return Decimal("0.004")
    if m <= Decimal("0.008"):
        return Decimal("0.008")
    if m <= Decimal("0.015"):
        return Decimal("0.015")
    if m <= Decimal("0.016"):
        return Decimal("0.016")
    if m <= Decimal("0.03"):
        return Decimal("0.03")
    if m <= Decimal("0.032"):
        return Decimal("0.032")
    if m <= Decimal("0.06"):
        return Decimal("0.06")
    if m <= Decimal("0.064"):
        return Decimal("0.064")
    if m <= Decimal("0.12"):
        return Decimal("0.12")
    if m <= Decimal("0.125"):
        return Decimal("0.125")
    if m <= Decimal("0.25"):
        return Decimal("0.25")
    if m <= Decimal("0.5"):
        return Decimal("0.5")
    if m <= Decimal("1"):
        return Decimal("1")
    if m <= Decimal("2"):
        return Decimal("2")
    if m <= Decimal("4"):
        return Decimal("4")
    if m <= Decimal("8"):
        return Decimal("8")
    if m <= Decimal("16"):
        return Decimal("16")
    if m <= Decimal("32"):
        return Decimal("32")
    if m <= Decimal("64"):
        return Decimal("64")
    if m <= Decimal("128"):
        return Decimal("128")
    if m <= Decimal("256"):
        return Decimal("256")
    if m <= Decimal("512"):
        return Decimal("512")
    if m <= Decimal("1024"):
        return Decimal("1024")
    if m <= Decimal("2048"):
        return Decimal("2048")
    return m
