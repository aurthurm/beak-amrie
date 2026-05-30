"""Shared constants for the AMRIE interpretation engine.

Port of Constants.cs. All values are kept as close to the original as possible so
that cross-referencing C# source remains straightforward.
"""

from decimal import Decimal

BREAKPOINT_TABLE_REVISION_YEAR = 2026
"""Calendar year of the most recent breakpoint table revision."""

BREAKPOINT_TABLE_REVISION_MINOR_CHANGE_NUMBER = 1
"""Incremented within a year when a table correction is published."""

QUOTE = '"'
TWO_QUOTES = '""'


class Disk:
    """Valid measurement range for disk-diffusion results (millimetres)."""

    MINIMUM_DISK_MEASUREMENT = Decimal("6")
    MAXIMUM_DISK_MEASUREMENT = Decimal("80")


class MIC:
    """Valid measurement range for MIC / E-test results (mg/L)."""

    MINIMUM_MIC_MEASUREMENT = Decimal("0.0001")
    MAXIMUM_MIC_MEASUREMENT = Decimal("2048")


class MeasurementModifiers:
    """String prefixes that qualify a numeric measurement.

    A raw result string from a lab file may begin with one of these tokens before
    the numeric value (e.g. ``"<4"``, ``">=8"``).
    """

    LESS_THAN = "<"
    GREATER_THAN = ">"
    EQUALS_SIGN = "="

    class Invalid:
        """Unicode characters that are semantically equivalent to ``<=`` / ``>=``.

        These are replaced with the ASCII two-character equivalents during parsing
        so that downstream logic only has to handle one form.
        """

        LESS_THAN_OR_EQUAL_TO = "≤"   # ≤
        GREATER_THAN_OR_EQUAL_TO = "≥"  # ≥


class Delimiters:
    """Character constants used when splitting and joining delimited text."""

    TAB_PLACEHOLDER = "TAB"
    """Human-readable name accepted on the command line in place of a literal tab."""

    TAB_CHAR = "\t"
    COMMA_CHAR = ","
    UNDERSCORE = "_"
    SPACE = " "
    EQUALS_SIGN = "="


class CommandLineModes:
    """Mode tokens accepted by the CLI ``--mode`` argument."""

    FILE = "FILE"
    SINGLE_INTERPRETATION = "SINGLE_INTERPRETATION"


class KeyFields:
    """Column names that carry special meaning in the input data file."""

    ORGANISM = "ORGANISM"
    """The column that holds the WHONET organism code for each isolate row."""


class InterpretationCodes:
    """Single- or multi-character strings returned as interpretation results.

    The main category codes (S, I, R, NS, SDD) follow CLSI / EUCAST conventions.
    Modifier suffixes (``*``, ``!``, ``?``) are appended by specific rule types:

    * ``*`` — result driven by an intrinsic resistance rule.
    * ``!`` — result overridden by an expert interpretation rule.
    * ``?`` — result is uncertain due to a ``<`` or ``>`` modifier on the measurement.

    ``UNINTERPRETABLE`` (empty string) means no applicable breakpoint was found.
    """

    UNINTERPRETABLE = ""
    SUSCEPTIBLE = "S"
    SUSCEPTIBLE_DOSE_DEPENDENT = "SDD"
    NON_SUSCEPTIBLE = "NS"
    INTERMEDIATE = "I"
    RESISTANT = "R"
    ASTERISK = "*"
    EXCLAMATION_POINT = "!"
    QUESTION_MARK = "?"
    WILD_TYPE = "WT"
    NON_WILD_TYPE = "NWT"
    IN_RANGE = "IN"
    OUT_OF_RANGE = "OUT"


class TestResultCodes:
    """Gram-stain / phenotypic test result tokens used in organism matching."""

    POSITIVE = "+"
    NEGATIVE = "-"


class OrganismGroups:
    """Composite organism group codes used in breakpoint / rule matching.

    These are synthetic codes that do not appear verbatim in the resource files;
    they are built at runtime from ``TestResultCodes`` and organism field names.
    """

    GRAM_POSITIVE_ANAEROBES = "AN" + TestResultCodes.POSITIVE
    GRAM_NEGATIVE_ANAEROBES = "AN" + TestResultCodes.NEGATIVE
    ANAEROBES = "ANA"
    ANAEROBE_PLUS_SUBKINGDOM_CODE = "ANAEROBE+SUBKINGDOM_CODE"
    """Composite key used when ORGANISM_CODE_TYPE encodes both anaerobe status
    and Gram reaction (e.g. ``"ANAEROBE+SUBKINGDOM_CODE"`` maps to AN+ or AN-)."""


class SitesOfInfection:
    """Human-readable site-of-infection labels that appear in the breakpoints table.

    ``DEFAULT_ORDER`` defines the priority in which sites are evaluated when the
    caller has not provided a custom prioritised list. Sites listed earlier take
    precedence over sites listed later. This mirrors
    ``Constants.SitesOfInfection.DefaultOrder`` in the C# source.
    """

    BLANK = "(Blank)"
    ABSCESSES = "Abscesses"
    EXTRAINTESTINAL = "Extraintestinal"
    ENDOCARDITIS = "Endocarditis"
    ENDOCARDITIS_WITH_COMBINATION_TREATMENT = "Endocarditis with combination treatment"
    GENITAL = "Genital"
    INFECTIONS_ORIGINATING_FROM_THE_URINARY_TRACT = "Infections originating from the urinary tract"
    INHALED = "Inhaled"
    INTESTINAL = "Intestinal"
    INTRAVENOUS = "Intravenous"
    INVESTIGATIONAL_AGENT = "Investigational agent"
    LIPOSOMAL = "Liposomal"
    MAMMARY_GLAND = "Mammary gland"
    MASTITIS = "Mastitis"
    MENINGITIS = "Meningitis"
    METRITIS = "Metritis"
    NON_ENDOCARDITIS = "Non-endocarditis"
    NON_MENINGITIS = "Non-meningitis"
    NON_PNEUMONIA = "Non-pneumonia"
    ORAL = "Oral"
    OTHER_INDICATIONS = "Other indications"
    OTHER_INFECTIONS = "Other infections"
    PARENTERAL = "Parenteral"
    PNEUMONIA = "Pneumonia"
    PROPHYLAXIS = "Prophylaxis"
    RESPIRATORY = "Respiratory"
    SCREEN = "Screen"
    SKIN = "Skin"
    SOFT_TISSUE = "Soft tissue"
    UNCOMPLICATED_UTI = "Uncomplicated urinary tract infection"
    WOUNDS = "Wounds"

    DEFAULT_ORDER = [
        NON_MENINGITIS,
        NON_ENDOCARDITIS,
        PARENTERAL,
        BLANK,
        UNCOMPLICATED_UTI,
        INFECTIONS_ORIGINATING_FROM_THE_URINARY_TRACT,
        MENINGITIS,
        ENDOCARDITIS,
        ENDOCARDITIS_WITH_COMBINATION_TREATMENT,
        INTRAVENOUS,
        ORAL,
        INHALED,
        INVESTIGATIONAL_AGENT,
        EXTRAINTESTINAL,
        ABSCESSES,
        GENITAL,
        INTESTINAL,
        LIPOSOMAL,
        MAMMARY_GLAND,
        MASTITIS,
        METRITIS,
        NON_PNEUMONIA,
        OTHER_INFECTIONS,
        OTHER_INDICATIONS,
        PNEUMONIA,
        PROPHYLAXIS,
        RESPIRATORY,
        SCREEN,
        SKIN,
        SOFT_TISSUE,
        WOUNDS,
    ]
