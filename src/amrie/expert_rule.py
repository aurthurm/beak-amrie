"""Expert interpretation rules (phenotypic inference rules).

Port of ``ExpertInterpretationRule.cs`` and ``ExpertRuleCriterion.cs``. Loads
``resources/ExpertInterpretationRules.txt`` at import time into
:data:`EXPERT_INTERPRETATION_RULES`.

Expert rules infer resistance to a set of antibiotics based on the observed
resistance pattern of an isolate.  For example, the ``ESBL-CONFIRMED`` rule marks
all extended-spectrum beta-lactamase–affected drugs as ``R!`` when the isolate has
a confirmed positive ESBL test.

Each rule has:

* An organism scope (resolved to ``CURRENT_ORGANISMS`` at evaluation time).
* One or more criteria (``RULE_CRITERIA``) that must each be satisfied.
* A logical operator (``AND`` / ``OR``) that combines the criteria.
* A list of antibiotics (``AFFECTED_ANTIBIOTICS``) to mark ``R!`` when the rule
  fires.

The two special rule codes ``MRS`` and ``ICR`` have their affected-antibiotic
lists computed dynamically from the antibiotic reference data rather than stored
in the resource file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from amrie import constants as C
from amrie.antibiotic import (
    CEPH3_ANTIBIOTIC_CODES,
    ICR_ANTIBIOTICS,
    MRS_ANTIBIOTICS_EXCEPT_CPT_BPR,
    short_code,
)
from amrie.io_utils import get_resource_headers, split_line
from amrie.organism import CURRENT_ORGANISMS, Organism
from amrie.parsing import VALID_ANTIBIOTIC_CODE_REGEX, VALID_ANTIBIOTIC_FIELD_NAME_REGEX
from amrie.paths import resource_path


class RuleCodes:
    """Known expert rule codes for use in ``EnabledExpertInterpretationRules`` config."""

    ESBL_CONFIRMED = "ESBL-CONFIRMED"
    ESBL_PROBABLE = "ESBL-AMPC-PROBABLE"
    BLNAR = "BLNAR-HFLU"
    MRSTAPH = "MRS"
    ICR = "ICR"
    ALL = [ESBL_CONFIRMED, ESBL_PROBABLE, BLNAR, MRSTAPH, ICR]


class PROF_CLASS:
    """Pharmacological class tokens used as special test names in rule criteria."""

    CEPH3 = "CEPH3"
    """Matches any 3rd-generation cephalosporin present on the isolate's panel."""


class RuleOperators:
    """Logical operators that combine multiple criteria within a single rule."""

    AND = "AND"
    """All criteria must be satisfied for the rule to fire."""
    OR = "OR"
    """At least one criterion must be satisfied for the rule to fire."""


@dataclass
class ExpertRuleCriterion:
    """One condition within an :class:`ExpertInterpretationRule`.

    Attributes:
        test_name: A three-letter drug code (e.g. ``"AMP"``), a
            :attr:`PROF_CLASS` token (``"CEPH3"``), or a non-antibiotic test
            column name (e.g. ``"ESBL"``).
        test_result: The expected interpretation or test value (e.g. ``"R"``,
            ``"NS"``, ``"+"``, ``"-"``).
    """

    test_name: str
    test_result: str


@dataclass
class ExpertInterpretationRule:
    """One row from ``resources/ExpertInterpretationRules.txt``.

    Represents a phenotypic inference rule that marks a set of antibiotics as
    resistant (``R!``) when the isolate's measured / interpreted results meet all
    defined criteria.

    Attributes:
        RULE_CODE: Unique identifier (see :class:`RuleCodes`).
        DESCRIPTION: Human-readable description of the rule.
        ORGANISM_CODE: The organism code this rule applies to.
        ORGANISM_CODE_TYPE: The taxonomy level of ``ORGANISM_CODE``
            (e.g. ``"WHONET_ORG_CODE"``, ``"GENUS_CODE"``).
        RULE_CRITERIA: Ordered list of conditions that must be met.
        CriteriaOperator: ``"AND"`` or ``"OR"`` (see :class:`RuleOperators`).
        AFFECTED_ANTIBIOTICS: Drug codes to mark ``R!`` when the rule fires.
        ANTIBIOTIC_EXCEPTIONS: Drug codes excluded from ``AFFECTED_ANTIBIOTICS``.
    """

    RULE_CODE: str
    DESCRIPTION: str
    ORGANISM_CODE: str
    ORGANISM_CODE_TYPE: str
    RULE_CRITERIA: list[ExpertRuleCriterion]
    CriteriaOperator: str
    AFFECTED_ANTIBIOTICS: list[str]
    ANTIBIOTIC_EXCEPTIONS: list[str]

    def evaluate_criteria(
        self,
        row_values: dict[str, str],
        result_interpretations: dict[str, str],
    ) -> bool:
        """Evaluate whether this rule's criteria are satisfied for a given isolate.

        Organism matching has already been performed before this method is called.
        This method only needs to check the measurement / interpretation criteria.

        For antibiotic criteria (drug code or ``CEPH3``), the criterion is
        satisfied when at least one matching antibiotic in *result_interpretations*
        meets the expected result (``"R"`` or ``"NS"``).  For non-antibiotic tests
        (e.g. ``"ESBL"``, ``"MECA_PCR"``), the raw value in *row_values* must
        match exactly.

        Args:
            row_values: The isolate's column values from the input file.
            result_interpretations: Already-computed interpretations keyed by
                full WHONET column name (e.g. ``{"AMP_ND10": "R"}``).

        Returns:
            ``True`` if the rule fires (all/any criteria met per the operator).
        """
        rule_results: list[bool] = []

        for criterion in self.RULE_CRITERIA:
            if VALID_ANTIBIOTIC_CODE_REGEX.match(criterion.test_name) or criterion.test_name == PROF_CLASS.CEPH3:
                matching = [
                    abx
                    for abx in row_values
                    if (
                        VALID_ANTIBIOTIC_FIELD_NAME_REGEX.match(abx) and abx.startswith(criterion.test_name)
                    )
                    or (
                        criterion.test_name == PROF_CLASS.CEPH3
                        and any(ceph3 == abx[:3] for ceph3 in CEPH3_ANTIBIOTIC_CODES)
                    )
                ]

                criterion_satisfied = False
                for abx in matching:
                    if abx not in result_interpretations:
                        continue
                    interp = result_interpretations[abx]
                    if criterion.test_result == C.InterpretationCodes.NON_SUSCEPTIBLE:
                        if interp in (
                            C.InterpretationCodes.RESISTANT,
                            C.InterpretationCodes.INTERMEDIATE,
                        ):
                            criterion_satisfied = True
                            break
                    elif criterion.test_result == C.InterpretationCodes.RESISTANT:
                        if interp == C.InterpretationCodes.RESISTANT:
                            criterion_satisfied = True
                            break
                rule_results.append(criterion_satisfied)
            else:
                if criterion.test_name in row_values:
                    rule_results.append(row_values[criterion.test_name] == criterion.test_result)
                else:
                    rule_results.append(False)

        if self.CriteriaOperator == RuleOperators.AND:
            return len(rule_results) > 0 and all(rule_results)
        if self.CriteriaOperator == RuleOperators.OR:
            return len(rule_results) > 0 and any(rule_results)
        return False


def _load_expert_rules(path: Path | None = None) -> list[ExpertInterpretationRule]:
    rules_file = path or resource_path("ExpertInterpretationRules.txt")
    df = pd.read_csv(
        rules_file,
        sep=C.Delimiters.TAB_CHAR,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        quotechar=C.QUOTE,
    )
    header_map = get_resource_headers(list(df.columns))
    all_rules: list[ExpertInterpretationRule] = []

    for _, row in df.iterrows():
        rule_criteria: list[ExpertRuleCriterion] = []
        rule_op = RuleOperators.AND

        for token in split_line(row.iloc[header_map["RULE_CRITERIA"]], C.Delimiters.SPACE):
            if not token:
                continue
            if C.Delimiters.EQUALS_SIGN in token:
                parts = split_line(token, C.Delimiters.EQUALS_SIGN)
                rule_criteria.append(ExpertRuleCriterion(parts[0], parts[1]))
            elif token in (RuleOperators.AND, RuleOperators.OR):
                rule_op = token
            else:
                raise ValueError(f"Invalid rule criteria token: {token}")

        rule_code = row.iloc[header_map["RULE_CODE"]]
        if rule_code == RuleCodes.MRSTAPH:
            affected = list(MRS_ANTIBIOTICS_EXCEPT_CPT_BPR)
        elif rule_code == RuleCodes.ICR:
            affected = list(ICR_ANTIBIOTICS)
        else:
            affected = split_line(row.iloc[header_map["AFFECTED_ANTIBIOTICS"]], C.Delimiters.COMMA_CHAR)

        exceptions = split_line(row.iloc[header_map["ANTIBIOTIC_EXCEPTIONS"]], C.Delimiters.COMMA_CHAR)

        all_rules.append(
            ExpertInterpretationRule(
                RULE_CODE=rule_code,
                DESCRIPTION=row.iloc[header_map["DESCRIPTION"]],
                ORGANISM_CODE=row.iloc[header_map["ORGANISM_CODE"]],
                ORGANISM_CODE_TYPE=row.iloc[header_map["ORGANISM_CODE_TYPE"]],
                RULE_CRITERIA=rule_criteria,
                CriteriaOperator=rule_op,
                AFFECTED_ANTIBIOTICS=affected,
                ANTIBIOTIC_EXCEPTIONS=exceptions,
            )
        )
    return all_rules


EXPERT_INTERPRETATION_RULES: list[ExpertInterpretationRule] = _load_expert_rules()


def _organism_matches_rule(rule: ExpertInterpretationRule, o: Organism) -> bool:
    """Return ``True`` if *o* falls within the rule's organism scope."""
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
    if o.ANAEROBE and rule.ORGANISM_CODE_TYPE == C.OrganismGroups.ANAEROBE_PLUS_SUBKINGDOM_CODE:
        if o.SUBKINGDOM_CODE == C.TestResultCodes.POSITIVE and rule.ORGANISM_CODE == C.OrganismGroups.GRAM_POSITIVE_ANAEROBES:
            return True
        if o.SUBKINGDOM_CODE == C.TestResultCodes.NEGATIVE and rule.ORGANISM_CODE == C.OrganismGroups.GRAM_NEGATIVE_ANAEROBES:
            return True
    if o.ANAEROBE and rule.ORGANISM_CODE_TYPE == "ANAEROBE" and rule.ORGANISM_CODE == C.OrganismGroups.ANAEROBES:
        return True
    return False


def get_applicable_expert_rules(
    whonet_organism_code: str,
    antimicrobial_codes: list[str],
    other_tests: list[str],
    enabled_expert_interpretation_rules: list[str] | None,
) -> list[ExpertInterpretationRule]:
    """Return the expert rules that are applicable to a given isolate.

    First restricts to rules that match the organism and are enabled, then removes
    rules whose required fields are absent from the isolate's data:

    * ``AND`` rules (other than ``ESBL_PROBABLE``): all criteria fields must be
      present.
    * ``ESBL_PROBABLE``: at least one CEPH3 drug must be present.
    * ``OR`` rules: at least one criteria field must be present.

    Args:
        whonet_organism_code: WHONET organism code for the isolate.
        antimicrobial_codes: Full WHONET column names of antibiotics present in
            the isolate row (e.g. ``["AMP_ND10", "CTX_ND30"]``).
        other_tests: Non-antibiotic column names present in the row
            (e.g. ``["ESBL", "MECA_PCR"]``).
        enabled_expert_interpretation_rules: Whitelist of rule codes; pass
            ``None`` to enable all rules.

    Returns:
        List of applicable :class:`ExpertInterpretationRule` instances. Returns
        an empty list if the organism is unknown.
    """
    if whonet_organism_code not in CURRENT_ORGANISMS:
        return []

    o = CURRENT_ORGANISMS[whonet_organism_code]
    return_list = [
        rule
        for rule in EXPERT_INTERPRETATION_RULES
        if (enabled_expert_interpretation_rules is None or rule.RULE_CODE in enabled_expert_interpretation_rules)
        and _organism_matches_rule(rule, o)
    ]

    iteration_list = list(return_list)
    for this_rule in iteration_list:
        if this_rule.CriteriaOperator == RuleOperators.AND:
            if this_rule.RULE_CODE == RuleCodes.ESBL_PROBABLE:
                if not any(
                    ceph3 in short_code(a) for ceph3 in CEPH3_ANTIBIOTIC_CODES for a in antimicrobial_codes
                ):
                    return_list.remove(this_rule)
            else:
                if not all(
                    (
                        any(t.test_name == short_code(a) for a in antimicrobial_codes)
                        if VALID_ANTIBIOTIC_CODE_REGEX.match(t.test_name)
                        else t.test_name in other_tests
                    )
                    for t in this_rule.RULE_CRITERIA
                ):
                    return_list.remove(this_rule)
        else:
            if not any(
                (
                    any(t.test_name == short_code(a) for a in antimicrobial_codes)
                    if VALID_ANTIBIOTIC_CODE_REGEX.match(t.test_name)
                    else t.test_name in other_tests
                )
                for t in this_rule.RULE_CRITERIA
            ):
                return_list.remove(this_rule)

    return return_list
