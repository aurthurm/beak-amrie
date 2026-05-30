"""Antibiotic reference data and taxonomy helpers.

Port of ``Antibiotic.cs``. Loads ``resources/Antibiotics.txt`` at import time into
:data:`ALL_ANTIBIOTICS` and derives several filtered lists used by the expert
interpretation rules (``MRS_ANTIBIOTICS_EXCEPT_CPT_BPR``, ``ICR_ANTIBIOTICS``,
``CEPH3_ANTIBIOTIC_CODES``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from amrie import constants as C
from amrie.io_utils import get_resource_headers
from amrie.paths import resource_path

_X = "X"
"""Boolean sentinel used in the resource file (``"X"`` = true, ``""`` = false)."""


class TestMethods:
    """Canonical test-method names used throughout the engine.

    E-test results share MIC breakpoints, so the engine maps ``ETEST`` to ``MIC``
    during interpretation via :meth:`get_test_method_from_code`.
    """

    DISK = "DISK"
    MIC = "MIC"
    ETEST = "ETEST"

    @staticmethod
    def get_test_method_from_code(test_method_code: str) -> str:
        """Map a single-character column-name code to a canonical test method.

        Args:
            test_method_code: One of ``"D"`` (disk), ``"M"`` (MIC), or ``"E"``
                (E-test). Case-sensitive.

        Returns:
            :attr:`DISK` for ``"D"``, :attr:`MIC` for ``"M"`` or ``"E"``.

        Raises:
            ValueError: If *test_method_code* is not a recognised code.
        """
        if test_method_code == TestMethodCodes.DISK:
            return TestMethods.DISK
        if test_method_code in (TestMethodCodes.MIC, TestMethodCodes.ETEST):
            return TestMethods.MIC
        raise ValueError(test_method_code)


class TestMethodCodes:
    """Single-character codes embedded in WHONET antibiotic column names.

    A WHONET column name like ``"AMP_ND10"`` has the form
    ``<drug>_<guideline-code><method-code>[<potency>]``. The method code is the
    second character of the suffix after the underscore.
    """

    DISK = "D"
    MIC = "M"
    ETEST = "E"


class GuidelineNames:
    """Full guideline abbreviations stored in resource files.

    These are the long forms (e.g. ``"CLSI"``) written into ``GUIDELINES`` columns
    of the breakpoint table, and expanded from single-character codes via
    :meth:`get_guideline_from_code`.
    """

    CLSI = "CLSI"
    EUCAST = "EUCAST"
    SFM = "SFM"
    SRGA = "SRGA"
    BSAC = "BSAC"
    DIN = "DIN"
    NEO = "NEO"
    AFA = "AFA"
    USER_DEFINED = "UserDefined"
    """Sentinel value written into breakpoints loaded from a user-defined file."""

    @staticmethod
    def get_guideline_from_code(guideline_code: str) -> str:
        """Expand a single-character guideline code to its full abbreviation.

        The guideline code is the first character of the WHONET column-name suffix
        (e.g. ``"N"`` → ``"CLSI"``, ``"E"`` → ``"EUCAST"``).

        Args:
            guideline_code: Single character from :class:`GuidelineCodes`.

        Returns:
            Full guideline name from this class.

        Raises:
            ValueError: If *guideline_code* is not recognised.
        """
        mapping = {
            GuidelineCodes.CLSI: GuidelineNames.CLSI,
            GuidelineCodes.EUCAST: GuidelineNames.EUCAST,
            GuidelineCodes.SFM: GuidelineNames.SFM,
            GuidelineCodes.SRGA: GuidelineNames.SRGA,
            GuidelineCodes.DIN: GuidelineNames.DIN,
            GuidelineCodes.NEO: GuidelineNames.NEO,
            GuidelineCodes.BSAC: GuidelineNames.BSAC,
            GuidelineCodes.AFA: GuidelineNames.AFA,
        }
        if guideline_code not in mapping:
            raise ValueError(guideline_code)
        return mapping[guideline_code]


class GuidelineCodes:
    """Single-character guideline codes embedded in WHONET antibiotic column names."""

    CLSI = "N"
    EUCAST = "E"
    SFM = "F"
    SRGA = "S"
    DIN = "D"
    NEO = "T"
    BSAC = "B"
    AFA = "A"
    ALL_CODES = [CLSI, EUCAST, SFM, SRGA, DIN, NEO, BSAC, AFA]
    """All valid guideline codes, used to build the antibiotic-field name regex."""


@dataclass(frozen=True)
class Antibiotic:
    """A single row from ``resources/Antibiotics.txt``.

    Each instance represents one antimicrobial agent with its cross-reference
    codes, guideline membership flags, pharmacological classification, and LOINC
    identifiers. Fields map directly to the tab-delimited column names in the
    resource file.

    Boolean fields (``CLSI``, ``EUCAST``, ``HUMAN``, etc.) are ``True`` when the
    resource file contains ``"X"`` and ``False`` when the cell is blank.
    """

    WHONET_ABX_CODE: str
    WHO_CODE: str
    DIN_CODE: str
    JAC_CODE: str
    EUCAST_CODE: str
    USER_CODE: str
    ANTIBIOTIC: str
    GUIDELINES: str
    CLSI: bool
    EUCAST: bool
    SFM: bool
    SRGA: bool
    BSAC: bool
    DIN: bool
    NEO: bool
    AFA: bool
    ABX_NUMBER: str
    POTENCY: str
    ATC_CODE: str
    CLASS: str
    SUBCLASS: str
    PROF_CLASS: str
    WHO_AWARE: str
    CIA_CATEGORY: str
    CLSI_ORDER: str
    EUCAST_ORDER: str
    HUMAN: bool
    VETERINARY: bool
    ANIMAL_GP: bool
    LOINCCOMP: str
    LOINCGEN: str
    LOINCDISK: str
    LOINCMIC: str
    LOINCETEST: str
    LOINCSLOW: str
    LOINCAFB: str
    LOINCSBT: str
    LOINCMLC: str
    DATE_ENTERED: datetime
    DATE_MODIFIED: datetime
    COMMENTS: str


def short_code(full_antibiotic_code: str) -> str:
    """Extract the three-character drug code from a full WHONET column name.

    A WHONET antibiotic column name has the form ``<3-char code>_<suffix>``
    (e.g. ``"AMP_ND10"``). This function returns just the first three characters.

    Args:
        full_antibiotic_code: Full WHONET antibiotic column name.

    Returns:
        Three-character drug code (e.g. ``"AMP"``).
    """
    return full_antibiotic_code[:3]


def _parse_date(value: str) -> datetime:
    """Parse an ISO-format date string, returning :attr:`datetime.min` for blanks."""
    if not value or not value.strip():
        return datetime.min
    return datetime.fromisoformat(value.strip())


def _load_antibiotics(path: Path | None = None) -> list[Antibiotic]:
    """Load all rows from the Antibiotics resource file.

    Args:
        path: Override path for testing; defaults to the bundled resource.

    Returns:
        List of :class:`Antibiotic` instances, one per non-header row.

    Raises:
        FileNotFoundError: If the resource file does not exist.
    """
    abx_file = path or resource_path("Antibiotics.txt")
    if not abx_file.exists():
        raise FileNotFoundError(str(abx_file))

    df = pd.read_csv(
        abx_file,
        sep=C.Delimiters.TAB_CHAR,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        quotechar=C.QUOTE,
    )
    header_map = get_resource_headers(list(df.columns))
    antibiotics: list[Antibiotic] = []

    for _, row in df.iterrows():
        antibiotics.append(
            Antibiotic(
                WHONET_ABX_CODE=row.iloc[header_map["WHONET_ABX_CODE"]],
                WHO_CODE=row.iloc[header_map["WHO_CODE"]],
                DIN_CODE=row.iloc[header_map["DIN_CODE"]],
                JAC_CODE=row.iloc[header_map["JAC_CODE"]],
                EUCAST_CODE=row.iloc[header_map["EUCAST_CODE"]],
                USER_CODE=row.iloc[header_map["USER_CODE"]],
                ANTIBIOTIC=row.iloc[header_map["ANTIBIOTIC"]],
                GUIDELINES=row.iloc[header_map["GUIDELINES"]],
                CLSI=row.iloc[header_map["CLSI"]] == _X,
                EUCAST=row.iloc[header_map["EUCAST"]] == _X,
                SFM=row.iloc[header_map["SFM"]] == _X,
                SRGA=row.iloc[header_map["SRGA"]] == _X,
                BSAC=row.iloc[header_map["BSAC"]] == _X,
                DIN=row.iloc[header_map["DIN"]] == _X,
                NEO=row.iloc[header_map["NEO"]] == _X,
                AFA=row.iloc[header_map["AFA"]] == _X,
                ABX_NUMBER=row.iloc[header_map["ABX_NUMBER"]],
                POTENCY=row.iloc[header_map["POTENCY"]],
                ATC_CODE=row.iloc[header_map["ATC_CODE"]],
                CLASS=row.iloc[header_map["CLASS"]],
                SUBCLASS=row.iloc[header_map["SUBCLASS"]],
                PROF_CLASS=row.iloc[header_map["PROF_CLASS"]],
                WHO_AWARE=row.iloc[header_map["WHO_AWARE"]],
                CIA_CATEGORY=row.iloc[header_map["CIA_CATEGORY"]],
                CLSI_ORDER=row.iloc[header_map["CLSI_ORDER"]],
                EUCAST_ORDER=row.iloc[header_map["EUCAST_ORDER"]],
                HUMAN=row.iloc[header_map["HUMAN"]] == _X,
                VETERINARY=row.iloc[header_map["VETERINARY"]] == _X,
                ANIMAL_GP=row.iloc[header_map["ANIMAL_GP"]] == _X,
                LOINCCOMP=row.iloc[header_map["LOINCCOMP"]],
                LOINCGEN=row.iloc[header_map["LOINCGEN"]],
                LOINCDISK=row.iloc[header_map["LOINCDISK"]],
                LOINCMIC=row.iloc[header_map["LOINCMIC"]],
                LOINCETEST=row.iloc[header_map["LOINCETEST"]],
                LOINCSLOW=row.iloc[header_map["LOINCSLOW"]],
                LOINCAFB=row.iloc[header_map["LOINCAFB"]],
                LOINCSBT=row.iloc[header_map["LOINCSBT"]],
                LOINCMLC=row.iloc[header_map["LOINCMLC"]],
                DATE_ENTERED=_parse_date(row.iloc[header_map["DATE_ENTERED"]]),
                DATE_MODIFIED=_parse_date(row.iloc[header_map["DATE_MODIFIED"]]),
                COMMENTS=row.iloc[header_map["COMMENTS"]],
            )
        )
    return antibiotics


ALL_ANTIBIOTICS: list[Antibiotic] = _load_antibiotics()
"""All antimicrobial agents from ``resources/Antibiotics.txt``."""

MRS_CLASSES = {
    "Penicillins",
    "Cephems",
    "Cephems-Oral",
    "Monobactams",
    "Penems",
    "Beta-lactam+Inhibitors",
    "Beta-lactamase inhibitors",
}
"""Drug classes affected by the MRS (methicillin-resistant Staphylococcus) expert rule."""

ICR_CLASSES = {"Macrolides", "Lincosamides", "Streptogramins"}
"""Drug classes affected by the ICR (inducible clindamycin resistance) expert rule."""

CEPH3_ANTIBIOTIC_CODES: list[str] = list(
    dict.fromkeys(
        a.WHONET_ABX_CODE
        for a in ALL_ANTIBIOTICS
        if a.PROF_CLASS == "CEPH3"
    )
)
"""3rd-generation cephalosporin drug codes, used by the ESBL-PROBABLE expert rule."""

MRS_ANTIBIOTICS_EXCEPT_CPT_BPR: list[str] = list(
    dict.fromkeys(
        a.WHONET_ABX_CODE
        for a in ALL_ANTIBIOTICS
        if a.CLASS in MRS_CLASSES and a.WHONET_ABX_CODE not in ("CPT", "BPR")
    )
)
"""All beta-lactam drug codes except CPT and BPR, marked R! by the MRS expert rule."""

ICR_ANTIBIOTICS: list[str] = list(
    dict.fromkeys(a.WHONET_ABX_CODE for a in ALL_ANTIBIOTICS if a.CLASS in ICR_CLASSES)
)
"""Macrolide / lincosamide / streptogramin codes marked R! by the ICR expert rule."""
