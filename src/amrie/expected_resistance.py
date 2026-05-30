"""Intrinsic (expected) resistance phenotype rules.

Port of ``ExpectedResistancePhenotypeRule.cs``. Loads
``resources/ExpectedResistancePhenotypes.txt`` at import time into
:data:`EXPECTED_RESISTANCE_PHENOTYPE_RULES`.

An intrinsic resistance rule declares that a particular organism (or group of
organisms) is always resistant to a drug or drug class, regardless of the
measured MIC or disk result.  When a matching rule is found,
:class:`~amrie.antibiotic_rules.AntibioticSpecificInterpretationRules` returns
``"R*"`` without evaluating breakpoints.

Rules can be expressed at any level of the organism taxonomy and can contain
organism exceptions (e.g. "all Enterobacterales except *E. coli*").  Antibiotic
matching supports both direct ``WHONET_ABX_CODE`` equality and ATC-code prefix
matching, so a single rule can cover an entire drug class.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from amrie import constants as C
from amrie.antibiotic import ALL_ANTIBIOTICS, Antibiotic
from amrie.io_utils import get_resource_headers, split_line
from amrie.organism import CURRENT_ORGANISMS, Organism
from amrie.paths import resource_path

_ALL_ORGANISMS = "ALL"


@dataclass(frozen=True)
class ExpectedResistancePhenotypeRule:
    """One row from ``resources/ExpectedResistancePhenotypes.txt``.

    Declares that organisms matching ``ORGANISM_CODE`` / ``ORGANISM_CODE_TYPE``
    are intrinsically resistant to the drug identified by ``ABX_CODE`` /
    ``ABX_CODE_TYPE``, unless the organism also matches any of the exception
    fields.

    When ``ABX_CODE_TYPE`` is ``"ATC_CODE"``, ``ABX_CODE`` is a prefix; the rule
    is expanded at query time into one entry per matching antibiotic, with
    ``ABX_CODE`` replaced by the concrete ``WHONET_ABX_CODE``.
    """

    GUIDELINE: str
    REFERENCE_TABLE: str
    ORGANISM_CODE: str
    ORGANISM_CODE_TYPE: str
    EXCEPTION_ORGANISM_CODE: str
    EXCEPTION_ORGANISM_CODE_TYPE: str
    ABX_CODE: str
    ABX_CODE_TYPE: str
    ANTIBIOTIC_EXCEPTIONS: tuple[str, ...]
    DATE_ENTERED: datetime
    DATE_MODIFIED: datetime
    COMMENTS: str


def _parse_date(value: str) -> datetime:
    if not value or not value.strip():
        return datetime.min
    return datetime.fromisoformat(value.strip())


def _load_rules(path: Path | None = None) -> list[ExpectedResistancePhenotypeRule]:
    rules_file = path or resource_path("ExpectedResistancePhenotypes.txt")
    df = pd.read_csv(
        rules_file,
        sep=C.Delimiters.TAB_CHAR,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        quotechar=C.QUOTE,
    )
    header_map = get_resource_headers(list(df.columns))
    rules: list[ExpectedResistancePhenotypeRule] = []
    for _, row in df.iterrows():
        exceptions = tuple(
            split_line(row.iloc[header_map["ANTIBIOTIC_EXCEPTIONS"]], C.Delimiters.COMMA_CHAR)
        )
        rules.append(
            ExpectedResistancePhenotypeRule(
                GUIDELINE=row.iloc[header_map["GUIDELINE"]],
                REFERENCE_TABLE=row.iloc[header_map["REFERENCE_TABLE"]],
                ORGANISM_CODE=row.iloc[header_map["ORGANISM_CODE"]],
                ORGANISM_CODE_TYPE=row.iloc[header_map["ORGANISM_CODE_TYPE"]],
                EXCEPTION_ORGANISM_CODE=row.iloc[header_map["EXCEPTION_ORGANISM_CODE"]],
                EXCEPTION_ORGANISM_CODE_TYPE=row.iloc[header_map["EXCEPTION_ORGANISM_CODE_TYPE"]],
                ABX_CODE=row.iloc[header_map["ABX_CODE"]],
                ABX_CODE_TYPE=row.iloc[header_map["ABX_CODE_TYPE"]],
                ANTIBIOTIC_EXCEPTIONS=exceptions,
                DATE_ENTERED=_parse_date(row.iloc[header_map["DATE_ENTERED"]]),
                DATE_MODIFIED=_parse_date(row.iloc[header_map["DATE_MODIFIED"]]),
                COMMENTS=row.iloc[header_map["COMMENTS"]],
            )
        )
    return rules


EXPECTED_RESISTANCE_PHENOTYPE_RULES: list[ExpectedResistancePhenotypeRule] = _load_rules()


def _exception_matches(rule: ExpectedResistancePhenotypeRule, o: Organism, whonet_organism_code: str) -> bool:
    """Return ``True`` if *o* matches the rule's organism exception, exempting it from the rule."""
    if not rule.EXCEPTION_ORGANISM_CODE.strip():
        return False
    if whonet_organism_code == _ALL_ORGANISMS:
        return False

    exc_codes = [s.strip() for s in split_line(rule.EXCEPTION_ORGANISM_CODE, C.Delimiters.COMMA_CHAR)]

    if o.SEROVAR_GROUP and rule.EXCEPTION_ORGANISM_CODE_TYPE == "SEROVAR_GROUP" and o.SEROVAR_GROUP in exc_codes:
        return True
    if rule.EXCEPTION_ORGANISM_CODE_TYPE == "WHONET_ORG_CODE" and o.WHONET_ORG_CODE in exc_codes:
        return True
    if o.SPECIES_GROUP and rule.EXCEPTION_ORGANISM_CODE_TYPE == "SPECIES_GROUP" and o.SPECIES_GROUP in exc_codes:
        return True
    if o.GENUS_CODE and rule.EXCEPTION_ORGANISM_CODE_TYPE == "GENUS_CODE" and o.GENUS_CODE in exc_codes:
        return True
    if o.GENUS_GROUP and rule.EXCEPTION_ORGANISM_CODE_TYPE == "GENUS_GROUP" and o.GENUS_GROUP in exc_codes:
        return True
    if o.FAMILY_CODE and rule.EXCEPTION_ORGANISM_CODE_TYPE == "FAMILY_CODE" and o.FAMILY_CODE in exc_codes:
        return True
    if o.SUBKINGDOM_CODE and rule.EXCEPTION_ORGANISM_CODE_TYPE == "SUBKINGDOM_CODE" and o.SUBKINGDOM_CODE in exc_codes:
        return True
    if o.ANAEROBE and rule.EXCEPTION_ORGANISM_CODE_TYPE == C.OrganismGroups.ANAEROBE_PLUS_SUBKINGDOM_CODE:
        if o.SUBKINGDOM_CODE == C.TestResultCodes.POSITIVE and C.OrganismGroups.GRAM_POSITIVE_ANAEROBES in exc_codes:
            return True
        if o.SUBKINGDOM_CODE == C.TestResultCodes.NEGATIVE and C.OrganismGroups.GRAM_NEGATIVE_ANAEROBES in exc_codes:
            return True
    if o.ANAEROBE and rule.EXCEPTION_ORGANISM_CODE_TYPE == "ANAEROBE" and C.OrganismGroups.ANAEROBES in exc_codes:
        return True
    return False


def _organism_rule_matches(rule: ExpectedResistancePhenotypeRule, o: Organism, whonet_organism_code: str) -> bool:
    """Return ``True`` if *o* falls under the rule's target organism scope."""
    if whonet_organism_code == _ALL_ORGANISMS:
        return True
    if o.SEROVAR_GROUP and rule.ORGANISM_CODE_TYPE == "SEROVAR_GROUP" and o.SEROVAR_GROUP == rule.ORGANISM_CODE:
        return True
    if rule.ORGANISM_CODE_TYPE == "WHONET_ORG_CODE" and o.WHONET_ORG_CODE == rule.ORGANISM_CODE:
        return True
    if o.SPECIES_GROUP and rule.ORGANISM_CODE_TYPE == "SPECIES_GROUP" and o.SPECIES_GROUP == rule.ORGANISM_CODE:
        return True
    if o.GENUS_CODE and rule.ORGANISM_CODE_TYPE == "GENUS_CODE" and o.GENUS_CODE == rule.ORGANISM_CODE:
        return True
    if o.GENUS_GROUP and rule.ORGANISM_CODE_TYPE == "GENUS_GROUP" and o.GENUS_GROUP == rule.ORGANISM_CODE:
        return True
    if o.FAMILY_CODE and rule.ORGANISM_CODE_TYPE == "FAMILY_CODE" and o.FAMILY_CODE == rule.ORGANISM_CODE:
        return True
    if o.SUBKINGDOM_CODE and rule.ORGANISM_CODE_TYPE == "SUBKINGDOM_CODE" and o.SUBKINGDOM_CODE == rule.ORGANISM_CODE:
        return True
    if o.ANAEROBE and rule.ORGANISM_CODE_TYPE == C.OrganismGroups.ANAEROBE_PLUS_SUBKINGDOM_CODE:
        if o.SUBKINGDOM_CODE == C.TestResultCodes.POSITIVE and rule.ORGANISM_CODE == C.OrganismGroups.GRAM_POSITIVE_ANAEROBES:
            return True
        if o.SUBKINGDOM_CODE == C.TestResultCodes.NEGATIVE and rule.ORGANISM_CODE == C.OrganismGroups.GRAM_NEGATIVE_ANAEROBES:
            return True
    if o.ANAEROBE and rule.ORGANISM_CODE_TYPE == "ANAEROBE" and rule.ORGANISM_CODE == C.OrganismGroups.ANAEROBES:
        return True
    return False


def _organism_rank(rule: ExpectedResistancePhenotypeRule) -> int:
    mapping = {
        "SEROVAR_GROUP": 1,
        "WHONET_ORG_CODE": 2,
        "SPECIES_GROUP": 3,
        "GENUS_CODE": 4,
        "GENUS_GROUP": 5,
        "FAMILY_CODE": 6,
        "SUBKINGDOM_CODE": 7,
        C.OrganismGroups.ANAEROBE_PLUS_SUBKINGDOM_CODE: 8,
        "ANAEROBE": 9,
    }
    return mapping.get(rule.ORGANISM_CODE_TYPE, 10)


def _abx_rank(rule: ExpectedResistancePhenotypeRule) -> int:
    if rule.ABX_CODE_TYPE == "WHONET_ABX_CODE":
        return 1
    if rule.ABX_CODE_TYPE == "ATC_CODE":
        return 2
    return 3


def get_applicable_expected_resistance_rules(
    whonet_organism_code: str,
    prioritized_guidelines: list[str] | None = None,
    antimicrobial_codes: list[str] | None = None,
) -> list[ExpectedResistancePhenotypeRule]:
    """Return intrinsic resistance rules applicable to a given organism and drug set.

    Filters :data:`EXPECTED_RESISTANCE_PHENOTYPE_RULES` to rules that:

    * Match the guideline (if *prioritized_guidelines* is given).
    * Do **not** match an organism exception.
    * Match the organism at some taxonomy level.
    * Match at least one of *antimicrobial_codes* (or any drug if ``None``).

    ATC-code rules are expanded: each matching antibiotic produces a separate
    result entry with its concrete ``WHONET_ABX_CODE`` substituted in.  The
    result is deduplicated on ``(GUIDELINE, ABX_CODE)``, keeping only the
    most-specific rule for each pair.

    Args:
        whonet_organism_code: WHONET organism code for the isolate, or ``"ALL"``
            to retrieve rules regardless of organism.
        prioritized_guidelines: Restrict to these guideline names; ``None`` allows
            any.
        antimicrobial_codes: Restrict to these three-letter drug codes; ``None``
            returns rules for all drugs.

    Returns:
        Sorted, deduplicated list of applicable :class:`ExpectedResistancePhenotypeRule`
        instances.  Returns an empty list for unknown organisms.
    """
    if whonet_organism_code in CURRENT_ORGANISMS:
        o = CURRENT_ORGANISMS[whonet_organism_code]
    elif whonet_organism_code == _ALL_ORGANISMS:
        o = Organism(
            WHONET_ORG_CODE=whonet_organism_code,
            ORGANISM="",
            TAXONOMIC_STATUS="",
            COMMON=False,
            COMMON_COMMENSAL=False,
            ORGANISM_TYPE="",
            ANAEROBE=False,
            MORPHOLOGY="",
            SUBKINGDOM_CODE="",
            FAMILY_CODE="",
            GENUS_GROUP="",
            GENUS_CODE="",
            SPECIES_GROUP="",
            SEROVAR_GROUP="",
            SCT_CODE="",
            SCT_TEXT="",
            GBIF_TAXON_ID="",
            GBIF_DATASET_ID="",
            GBIF_TAXONOMIC_STATUS="",
            KINGDOM="",
            PHYLUM="",
            CLASS="",
            ORDER="",
            FAMILY="",
            GENUS="",
        )
    else:
        return []

    results: list[ExpectedResistancePhenotypeRule] = []

    for rule in EXPECTED_RESISTANCE_PHENOTYPE_RULES:
        if prioritized_guidelines is not None and rule.GUIDELINE not in prioritized_guidelines:
            continue
        if _exception_matches(rule, o, whonet_organism_code):
            continue
        if not _organism_rule_matches(rule, o, whonet_organism_code):
            continue

        for abx in ALL_ANTIBIOTICS:
            if antimicrobial_codes is not None and abx.WHONET_ABX_CODE not in antimicrobial_codes:
                continue
            if rule.ABX_CODE_TYPE == "WHONET_ABX_CODE" and rule.ABX_CODE == abx.WHONET_ABX_CODE:
                pass
            elif rule.ABX_CODE_TYPE == "ATC_CODE" and abx.ATC_CODE.startswith(rule.ABX_CODE):
                pass
            else:
                continue
            if abx.WHONET_ABX_CODE in rule.ANTIBIOTIC_EXCEPTIONS:
                continue

            substituted = replace(rule, ABX_CODE=abx.WHONET_ABX_CODE)
            results.append(substituted)

    results.sort(
        key=lambda r: (
            r.GUIDELINE,
            _organism_rank(r),
            _abx_rank(r),
            r.ABX_CODE,
        )
    )

    seen: set[tuple[str, str]] = set()
    unique: list[ExpectedResistancePhenotypeRule] = []
    for r in results:
        key = (r.GUIDELINE, r.ABX_CODE)
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique
