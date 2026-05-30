"""Breakpoint reference data and applicability selection.

Port of ``Breakpoint.cs``. Loads ``resources/Breakpoints.txt`` at import time into
:data:`BREAKPOINTS` and exposes :func:`get_applicable_breakpoints`, which is the
LINQ query from ``Breakpoint.GetApplicableBreakpoints`` translated into Python sort
+ filter operations.

The selection algorithm:

1. Filter breakpoints to those that match the requested organism (at any level of
   the taxonomy hierarchy), guideline, year, type, and site of infection.
2. Sort the survivors by specificity (most specific first):
   user-defined → guideline → year → test method → type → host →
   organism hierarchy level → site-of-infection priority index.
3. Group by ``(GUIDELINES, YEAR, BREAKPOINT_TYPE, HOST, WHONET_TEST)`` and keep
   only the most specific entry per group, plus any entries that differ only on
   site of infection (so that the caller receives all site-specific breakpoints
   for a given drug / organism combination when not requesting ``return_first_breakpoint_only``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from amrie import constants as C
from amrie.antibiotic import GuidelineNames
from amrie.io_utils import get_resource_headers, split_line
from amrie.organism import CURRENT_ORGANISMS, MERGED_ORGANISMS, Organism
from amrie.paths import resource_path


class BreakpointTypes:
    """Breakpoint category tokens stored in the ``BREAKPOINT_TYPE`` column."""

    HUMAN = "Human"
    ANIMAL = "Animal"
    ECOFF = "ECOFF"
    """Epidemiological cut-off; uses ``ECV_ECOFF`` rather than ``S`` / ``R``."""
    INTRINSIC_RESISTANCE = "Intrinsic"


@dataclass(frozen=True)
class Breakpoint:
    """A single row from ``resources/Breakpoints.txt``.

    Holds the S / I / R thresholds (or the ECOFF value) for one drug–organism–
    guideline–year–site-of-infection combination.  For disk diffusion the ``R``
    and ``S`` fields contain the breakpoint in millimetres; for MIC / E-test they
    contain mg/L.

    ``SITES_OF_INFECTION`` is a pre-split tuple derived from the raw
    ``SITE_OF_INFECTION`` string (comma-separated) for efficient membership tests.
    ``"(Blank)"`` entries are normalised to ``""`` at load time.

    All instances are frozen (immutable) so they can safely be shared between
    threads without copying.
    """

    GUIDELINES: str
    YEAR: int
    TEST_METHOD: str
    POTENCY: str
    ORGANISM_CODE: str
    ORGANISM_CODE_TYPE: str
    BREAKPOINT_TYPE: str
    HOST: str
    SITE_OF_INFECTION: str
    SITES_OF_INFECTION: tuple[str, ...]
    REFERENCE_TABLE: str
    REFERENCE_SEQUENCE: str
    WHONET_ABX_CODE: str
    WHONET_TEST: str
    R: Decimal
    I: str
    SDD: str
    S: Decimal
    ECV_ECOFF: Decimal
    ECV_ECOFF_TENTATIVE: bool
    DATE_ENTERED: datetime
    DATE_MODIFIED: datetime
    COMMENTS: str


def _parse_decimal(value: str) -> Decimal:
    """Parse a decimal string, returning ``Decimal(0)`` for blank cells."""
    if not value or not value.strip():
        return Decimal(0)
    return Decimal(value.strip())


def _parse_date(value: str) -> datetime:
    """Parse an ISO-format date string, returning :attr:`datetime.min` for blanks."""
    if not value or not value.strip():
        return datetime.min
    return datetime.fromisoformat(value.strip())


def _sites_from_field(site_of_infection: str) -> tuple[str, ...]:
    """Split and normalise the ``SITE_OF_INFECTION`` string into a tuple.

    Splits on commas, strips whitespace, and converts the literal string
    ``"(Blank)"`` to an empty string so that downstream comparisons with ``""``
    work correctly.
    """
    sites = []
    for s in split_line(site_of_infection, C.Delimiters.COMMA_CHAR):
        non_blank = s.strip()
        if non_blank == C.SitesOfInfection.BLANK:
            non_blank = ""
        sites.append(non_blank)
    return tuple(sites)


def load_breakpoints(breakpoints_table_file: str | Path, user_defined: bool = False) -> list[Breakpoint]:
    """Load breakpoints from a tab-delimited file.

    Args:
        breakpoints_table_file: Path to the breakpoints TSV file.
        user_defined: When ``True``, overrides the ``GUIDELINES`` field of every
            loaded breakpoint with ``"UserDefined"`` so that user-provided
            breakpoints always sort ahead of built-in ones.

    Returns:
        List of :class:`Breakpoint` instances in file order.

    Raises:
        FileNotFoundError: If *breakpoints_table_file* does not exist or is blank.
    """
    path = Path(breakpoints_table_file)
    if not path.exists() or not str(breakpoints_table_file).strip():
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
    breakpoints: list[Breakpoint] = []

    for _, row in df.iterrows():
        guidelines = row.iloc[header_map["GUIDELINES"]]
        if user_defined:
            guidelines = GuidelineNames.USER_DEFINED

        site_raw = row.iloc[header_map["SITE_OF_INFECTION"]]
        ecv_tentative_idx = header_map.get("ECV_ECOFF_TENTATIVE")
        ecv_tentative = (
            row.iloc[ecv_tentative_idx] == "X" if ecv_tentative_idx is not None else False
        )
        breakpoints.append(
            Breakpoint(
                GUIDELINES=guidelines,
                YEAR=int(row.iloc[header_map["YEAR"]]),
                TEST_METHOD=row.iloc[header_map["TEST_METHOD"]],
                POTENCY=row.iloc[header_map["POTENCY"]],
                ORGANISM_CODE=row.iloc[header_map["ORGANISM_CODE"]],
                ORGANISM_CODE_TYPE=row.iloc[header_map["ORGANISM_CODE_TYPE"]],
                BREAKPOINT_TYPE=row.iloc[header_map["BREAKPOINT_TYPE"]],
                HOST=row.iloc[header_map["HOST"]],
                SITE_OF_INFECTION=site_raw,
                SITES_OF_INFECTION=_sites_from_field(site_raw),
                REFERENCE_TABLE=row.iloc[header_map["REFERENCE_TABLE"]],
                REFERENCE_SEQUENCE=row.iloc[header_map["REFERENCE_SEQUENCE"]],
                WHONET_ABX_CODE=row.iloc[header_map["WHONET_ABX_CODE"]],
                WHONET_TEST=row.iloc[header_map["WHONET_TEST"]],
                R=_parse_decimal(row.iloc[header_map["R"]]),
                I=row.iloc[header_map["I"]],
                SDD=row.iloc[header_map["SDD"]],
                S=_parse_decimal(row.iloc[header_map["S"]]),
                ECV_ECOFF=_parse_decimal(row.iloc[header_map["ECV_ECOFF"]]),
                ECV_ECOFF_TENTATIVE=ecv_tentative,
                DATE_ENTERED=_parse_date(row.iloc[header_map["DATE_ENTERED"]]),
                DATE_MODIFIED=_parse_date(row.iloc[header_map["DATE_MODIFIED"]]),
                COMMENTS=row.iloc[header_map["COMMENTS"]],
            )
        )
    return breakpoints


BREAKPOINTS: list[Breakpoint] = load_breakpoints(resource_path("Breakpoints.txt"))


def _get_index(prioritized_sites: list[str], breakpoint_sites: str) -> int:
    """Return the priority index of the best-matching site in *breakpoint_sites*.

    A breakpoint may cover multiple sites (comma-separated). This function returns
    the *lowest* index found in *prioritized_sites* across all of the breakpoint's
    sites — i.e. the most-preferred site wins. Sites absent from the priority list
    are treated as least preferred (index = ``len(prioritized_sites)``).
    """
    bp_sites = [s.strip() for s in split_line(breakpoint_sites, C.Delimiters.COMMA_CHAR)]

    def min_index_for_site(this_bp_site: str) -> int:
        for x, pri_site in enumerate(prioritized_sites):
            this_prioritized = pri_site
            if this_prioritized.lower() == C.SitesOfInfection.BLANK.lower():
                this_prioritized = ""
            if this_prioritized.lower() == this_bp_site.lower():
                return x
        return len(prioritized_sites)

    return min(min_index_for_site(s) for s in bp_sites) if bp_sites else len(prioritized_sites)


def _organism_matches(bp: Breakpoint, o: Organism) -> bool:
    """Return ``True`` if *bp*'s organism code matches *o* at any taxonomy level."""
    if o.SEROVAR_GROUP and bp.ORGANISM_CODE_TYPE == "SEROVAR_GROUP" and o.SEROVAR_GROUP == bp.ORGANISM_CODE:
        return True
    if bp.ORGANISM_CODE_TYPE == "WHONET_ORG_CODE" and o.WHONET_ORG_CODE == bp.ORGANISM_CODE:
        return True
    if o.SPECIES_GROUP and bp.ORGANISM_CODE_TYPE == "SPECIES_GROUP" and o.SPECIES_GROUP == bp.ORGANISM_CODE:
        return True
    if o.GENUS_CODE and bp.ORGANISM_CODE_TYPE == "GENUS_CODE" and o.GENUS_CODE == bp.ORGANISM_CODE:
        return True
    if o.GENUS_GROUP and bp.ORGANISM_CODE_TYPE == "GENUS_GROUP" and o.GENUS_GROUP == bp.ORGANISM_CODE:
        return True
    if o.FAMILY_CODE and bp.ORGANISM_CODE_TYPE == "FAMILY_CODE" and o.FAMILY_CODE == bp.ORGANISM_CODE:
        return True
    if o.ANAEROBE and bp.ORGANISM_CODE_TYPE == C.OrganismGroups.ANAEROBE_PLUS_SUBKINGDOM_CODE:
        if o.SUBKINGDOM_CODE == C.TestResultCodes.POSITIVE and bp.ORGANISM_CODE == C.OrganismGroups.GRAM_POSITIVE_ANAEROBES:
            return True
        if o.SUBKINGDOM_CODE == C.TestResultCodes.NEGATIVE and bp.ORGANISM_CODE == C.OrganismGroups.GRAM_NEGATIVE_ANAEROBES:
            return True
    if o.ANAEROBE and bp.ORGANISM_CODE_TYPE == "ANAEROBE" and bp.ORGANISM_CODE == C.OrganismGroups.ANAEROBES:
        return True
    return False


def _site_matches(bp: Breakpoint, prioritized_sites: list[str]) -> bool:
    """Return ``True`` if any of *bp*'s sites of infection appear in *prioritized_sites*."""
    for requested_site in prioritized_sites:
        for site_from_bp in bp.SITES_OF_INFECTION:
            if requested_site == C.SitesOfInfection.BLANK and not site_from_bp.strip():
                return True
            if requested_site.lower() == site_from_bp.lower():
                return True
    return False


def _organism_specificity_rank(bp: Breakpoint) -> int:
    """Return a numeric rank for *bp*'s organism specificity (lower = more specific)."""
    mapping = {
        "SEROVAR_GROUP": 1,
        "WHONET_ORG_CODE": 2,
        "SPECIES_GROUP": 3,
        "GENUS_CODE": 4,
        "GENUS_GROUP": 5,
        "FAMILY_CODE": 6,
        C.OrganismGroups.ANAEROBE_PLUS_SUBKINGDOM_CODE: 7,
        "ANAEROBE": 8,
    }
    return mapping.get(bp.ORGANISM_CODE_TYPE, 9)


def _breakpoint_type_rank(bp: Breakpoint) -> int:
    """Return a numeric rank for *bp*'s breakpoint type (lower = higher priority)."""
    if bp.BREAKPOINT_TYPE == BreakpointTypes.HUMAN:
        return 1
    if bp.BREAKPOINT_TYPE == BreakpointTypes.ANIMAL:
        return 2
    if bp.BREAKPOINT_TYPE == BreakpointTypes.ECOFF:
        return 3
    return 4


def _sort_key(
    bp: Breakpoint,
    recoded_drug_codes: list[str] | None,
    prioritized_guidelines: list[str] | None,
    prioritized_guideline_years: list[int] | None,
    prioritized_breakpoint_types: list[str] | None,
    prioritized_sites: list[str],
) -> tuple:
    """Build the multi-level sort key that orders breakpoints from most to least preferred.

    The sort order (ascending, so lower = more preferred) mirrors the C# LINQ
    ``orderby`` chain in ``Breakpoint.GetApplicableBreakpoints``:

    1. Drug code position in *recoded_drug_codes* (or alphabetical if ``None``).
    2. User-defined first (0) vs. built-in (1).
    3. Guideline position in *prioritized_guidelines* (or alphabetical).
    4. Year position (or descending year when no list is given).
    5. Test method (alphabetical).
    6. Breakpoint type position (or default Human < Animal < ECOFF).
    7. Host (alphabetical).
    8. Organism specificity rank (serovar = most specific).
    9. Site-of-infection priority index.
    """
    if recoded_drug_codes is None:
        drug_key = bp.WHONET_TEST
    else:
        drug_key = str(recoded_drug_codes.index(bp.WHONET_TEST) if bp.WHONET_TEST in recoded_drug_codes else -1)

    user_defined_key = 0 if bp.GUIDELINES == GuidelineNames.USER_DEFINED else 1

    if prioritized_guidelines is None:
        guideline_key = bp.GUIDELINES
    else:
        guideline_key = str(
            prioritized_guidelines.index(bp.GUIDELINES)
            if bp.GUIDELINES in prioritized_guidelines
            else -1
        )

    if prioritized_guideline_years is None:
        year_key = -bp.YEAR
    else:
        year_key = (
            prioritized_guideline_years.index(bp.YEAR)
            if bp.YEAR in prioritized_guideline_years
            else -1
        )

    if prioritized_breakpoint_types is None:
        type_key = _breakpoint_type_rank(bp)
    else:
        type_key = (
            prioritized_breakpoint_types.index(bp.BREAKPOINT_TYPE)
            if bp.BREAKPOINT_TYPE in prioritized_breakpoint_types
            else -1
        )

    site_key = _get_index(prioritized_sites, bp.SITE_OF_INFECTION)

    return (
        drug_key,
        user_defined_key,
        guideline_key,
        year_key,
        bp.TEST_METHOD,
        type_key,
        bp.HOST,
        _organism_specificity_rank(bp),
        site_key,
    )


def get_applicable_breakpoints(
    whonet_organism_code: str,
    user_defined_breakpoints: list[Breakpoint],
    prioritized_guidelines: list[str] | None = None,
    prioritized_guideline_years: list[int] | None = None,
    prioritized_breakpoint_types: list[str] | None = None,
    prioritized_sites_of_infection: list[str] | None = None,
    prioritized_whonet_abx_full_drug_codes: list[str] | None = None,
    return_first_breakpoint_only: bool = False,
) -> list[Breakpoint]:
    """Return the ordered, filtered list of breakpoints applicable to a drug–organism pair.

    This is the Python equivalent of the LINQ query in
    ``Breakpoint.GetApplicableBreakpoints``.  When *return_first_breakpoint_only*
    is ``True``, only the single highest-priority breakpoint is returned.

    E-test columns are automatically recoded to their MIC equivalents before
    matching (``"AMP_NE"`` → ``"AMP_NM"``) because both share the same row in the
    breakpoints table.

    Deprecated organism codes are silently remapped to their successors via
    :data:`~amrie.organism.MERGED_ORGANISMS`.

    Args:
        whonet_organism_code: WHONET organism code for the isolate.
        user_defined_breakpoints: Additional breakpoints from a user-defined file;
            these sort ahead of built-in breakpoints.
        prioritized_guidelines: Restrict to these guideline names; ``None`` allows any.
        prioritized_guideline_years: Restrict to these years; ``None`` allows any
            (user-defined breakpoints are always included regardless).
        prioritized_breakpoint_types: Restrict to these types (e.g. ``["Human"]``);
            ``None`` allows any.
        prioritized_sites_of_infection: Ordered list that controls site priority.
            Defaults to :attr:`~amrie.constants.SitesOfInfection.DEFAULT_ORDER`.
        prioritized_whonet_abx_full_drug_codes: Restrict to these column codes;
            ``None`` returns breakpoints for all drugs.
        return_first_breakpoint_only: When ``True``, skip grouping and return only
            the top-sorted breakpoint.  Requires at most one drug in
            *prioritized_whonet_abx_full_drug_codes*.

    Returns:
        Ordered list of applicable :class:`Breakpoint` instances, most specific
        first.  Returns an empty list if the organism is unknown or no matching
        breakpoint exists.

    Raises:
        ValueError: If *return_first_breakpoint_only* is ``True`` and more than
            one drug code is supplied.
    """
    if (
        prioritized_whonet_abx_full_drug_codes is not None
        and len(prioritized_whonet_abx_full_drug_codes) > 1
        and return_first_breakpoint_only
    ):
        raise ValueError(
            "There must be exactly one drug specified when only the first breakpoint is requested."
        )

    if whonet_organism_code not in CURRENT_ORGANISMS:
        if whonet_organism_code in MERGED_ORGANISMS:
            merged = MERGED_ORGANISMS[whonet_organism_code]
            if merged in CURRENT_ORGANISMS:
                whonet_organism_code = merged
            else:
                return []
        else:
            return []

    if prioritized_sites_of_infection is None:
        prioritized_sites_of_infection = list(C.SitesOfInfection.DEFAULT_ORDER)

    o = CURRENT_ORGANISMS[whonet_organism_code]

    recoded_drug_codes: list[str] | None = None
    if prioritized_whonet_abx_full_drug_codes is not None:
        from amrie.parsing import VALID_ANTIBIOTIC_FIELD_NAME_REGEX

        recoded_drug_codes = []
        seen: set[str] = set()
        for abx in prioritized_whonet_abx_full_drug_codes:
            if VALID_ANTIBIOTIC_FIELD_NAME_REGEX.match(abx) and abx.endswith("E"):
                recoded = abx[:-1] + "M"
            else:
                recoded = abx
            if recoded not in seen:
                seen.add(recoded)
                recoded_drug_codes.append(recoded)

    all_bps = list(BREAKPOINTS) + list(user_defined_breakpoints)
    filtered: list[Breakpoint] = []

    for bp in all_bps:
        if prioritized_guideline_years is not None:
            if bp.YEAR not in prioritized_guideline_years and bp.GUIDELINES != GuidelineNames.USER_DEFINED:
                continue
        if prioritized_guidelines is not None:
            if bp.GUIDELINES not in prioritized_guidelines and bp.GUIDELINES != GuidelineNames.USER_DEFINED:
                continue
        if prioritized_breakpoint_types is not None:
            if bp.BREAKPOINT_TYPE not in prioritized_breakpoint_types:
                continue
        if not _site_matches(bp, prioritized_sites_of_infection):
            continue
        if recoded_drug_codes is not None and bp.WHONET_TEST not in recoded_drug_codes:
            continue
        if not _organism_matches(bp, o):
            continue
        filtered.append(bp)

    relevant = sorted(
        filtered,
        key=lambda bp: _sort_key(
            bp,
            recoded_drug_codes,
            prioritized_guidelines,
            prioritized_guideline_years,
            prioritized_breakpoint_types,
            prioritized_sites_of_infection,
        ),
    )

    applicable: list[Breakpoint] = []

    if return_first_breakpoint_only:
        if relevant:
            applicable.append(relevant[0])
        return applicable

    from itertools import groupby

    def group_key(bp: Breakpoint) -> tuple:
        return (bp.GUIDELINES, bp.YEAR, bp.BREAKPOINT_TYPE, bp.HOST, bp.WHONET_TEST)

    for _, group in groupby(relevant, key=group_key):
        group_list = list(group)
        top = group_list[0]
        applicable.append(top)
        if len(group_list) > 1:
            for remaining in group_list[1:]:
                if (
                    top.ORGANISM_CODE == remaining.ORGANISM_CODE
                    and top.ORGANISM_CODE_TYPE == remaining.ORGANISM_CODE_TYPE
                ):
                    applicable.append(remaining)

    return applicable
