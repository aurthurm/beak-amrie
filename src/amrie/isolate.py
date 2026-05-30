"""Single-isolate interpretation coordinator.

Port of ``IsolateInterpretation.cs``. :class:`IsolateInterpretation` accepts one
row of data (one isolate) and orchestrates the full interpretation pipeline:

1. **Expert rules** (applied first in ``__init__``): phenotypic inference rules
   that may mark certain antibiotics ``R!`` based on the presence of resistance
   markers in the same row (e.g. ESBL, MECA_PCR).  Precondition antibiotics are
   evaluated before the rule is tested.

2. **Normal interpretation** (applied in :meth:`get_all_interpretations`): for all
   remaining antibiotics, :class:`~amrie.antibiotic_rules.AntibioticSpecificInterpretationRules`
   checks intrinsic resistance rules and then breakpoints.

The static helper :meth:`IsolateInterpretation.get_single_interpretation` wraps
this for the common single-drug use case.
"""

from __future__ import annotations

from amrie import constants as C
from amrie.antibiotic import short_code
from amrie.antibiotic_rules import AntibioticSpecificInterpretationRules
from amrie.breakpoint import Breakpoint
from amrie.config import InterpretationConfiguration
from amrie.expert_rule import (
    PROF_CLASS,
    get_applicable_expert_rules,
)
from amrie.parsing import VALID_ANTIBIOTIC_CODE_REGEX, VALID_ANTIBIOTIC_FIELD_NAME_REGEX
from amrie.antibiotic import CEPH3_ANTIBIOTIC_CODES

valid_antibiotic_field_name_regex = VALID_ANTIBIOTIC_FIELD_NAME_REGEX
valid_antibiotic_code = VALID_ANTIBIOTIC_CODE_REGEX


class IsolateInterpretation:
    """Interpretation context for a single isolate row.

    Constructed once per data row; :meth:`get_all_interpretations` returns the
    complete result dictionary. All expert-rule evaluations happen during
    construction so that :meth:`get_all_interpretations` only needs to fill in
    the drugs that were not touched by expert rules.
    """

    def __init__(
        self,
        data_row_values: dict[str, str],
        column_names: list[str],
        enabled_expert_interpretation_rules: list[str] | None,
        user_defined_breakpoints: list[Breakpoint],
        guideline_year: int = -1,
        use_intrinsic_resistance_rules: bool = True,
        prioritized_breakpoint_types: list[str] | None = None,
        prioritized_sites_of_infection: list[str] | None = None,
    ) -> None:
        """Prepare the interpretation context for one data row.

        Builds :attr:`applicable_rules` for every antibiotic field found in
        *data_row_values*, then immediately evaluates expert interpretation rules
        so their results are available when :meth:`get_all_interpretations` runs.

        Args:
            data_row_values: Column-name → raw value mapping for one data row.
                Only columns with non-empty values should be included.
            column_names: Ordered list of all column names in the input file
                (including those without a value in this row).  Used to determine
                which affected antibiotics should receive expert-rule results.
            enabled_expert_interpretation_rules: Whitelist of rule codes to apply;
                ``None`` enables all rules.
            user_defined_breakpoints: Extra breakpoints from the config.
            guideline_year: Requested year; ``-1`` defers to the config year.
            use_intrinsic_resistance_rules: When ``False``, intrinsic resistance
                rules are skipped for all antibiotics in this row.
            prioritized_breakpoint_types: Breakpoint type filter.
            prioritized_sites_of_infection: Site priority list.
        """
        self.data_row_values = data_row_values
        self.column_names = column_names
        self.result_interpretations: dict[str, str] = {}
        self.applicable_rules: dict[str, AntibioticSpecificInterpretationRules] = {}

        if C.KeyFields.ORGANISM in data_row_values and data_row_values[C.KeyFields.ORGANISM].strip():
            self.organism_code = data_row_values[C.KeyFields.ORGANISM].strip()
        else:
            self.organism_code = ""

        self.antibiotic_fields = [
            k for k in data_row_values if VALID_ANTIBIOTIC_FIELD_NAME_REGEX.match(k)
        ]

        for field_name in self.antibiotic_fields:
            self.applicable_rules[field_name] = AntibioticSpecificInterpretationRules(
                self.organism_code,
                field_name,
                data_row_values[field_name],
                user_defined_breakpoints,
                guideline_year=guideline_year,
                use_intrinsic_resistance_rules=use_intrinsic_resistance_rules,
                prioritized_breakpoint_types=prioritized_breakpoint_types,
                prioritized_sites_of_infection=prioritized_sites_of_infection,
            )

        self._get_expert_interpretations(enabled_expert_interpretation_rules)

    def get_all_interpretations(self) -> dict[str, str]:
        """Return interpretations for all antibiotic fields in the data row.

        Antibiotics already assigned a result by expert rules during construction
        are not re-evaluated.  Antibiotics listed in the header but absent from
        the row's values (no measurement) are also skipped.

        Returns:
            Dictionary mapping WHONET column name → interpretation string for
            every drug that was present and could be interpreted.
        """
        pending = set(self.antibiotic_fields) - set(self.result_interpretations.keys())
        pending -= set(self.column_names) - set(self.data_row_values.keys())

        for field_name in pending:
            self.result_interpretations[field_name] = self.applicable_rules[field_name].get_interpretation()

        return self.result_interpretations

    def _get_single_interp(self, antibiotic_full_code: str) -> str:
        """Return the interpretation for one antibiotic, computing and caching it if needed."""
        if antibiotic_full_code not in self.result_interpretations:
            self.result_interpretations[antibiotic_full_code] = self.applicable_rules[
                antibiotic_full_code
            ].get_interpretation()
        return self.result_interpretations[antibiotic_full_code]

    def _get_expert_interpretations(
        self, enabled_expert_interpretation_rules: list[str] | None
    ) -> None:
        """Evaluate applicable expert rules and store their results.

        For each applicable rule, first ensures that any precondition antibiotics
        (including CEPH3 drugs when relevant) have been individually interpreted.
        If the rule's criteria are then satisfied, all affected antibiotics
        listed in the header are marked ``"R!"``.  An existing ``"R!"`` is never
        downgraded.
        """
        abx_keys = [k for k in self.data_row_values if VALID_ANTIBIOTIC_FIELD_NAME_REGEX.match(k)]
        other_keys = [k for k in self.data_row_values if not VALID_ANTIBIOTIC_FIELD_NAME_REGEX.match(k)]

        applicable = get_applicable_expert_rules(
            self.organism_code,
            abx_keys,
            other_keys,
            enabled_expert_interpretation_rules,
        )
        if not applicable:
            return

        for rule in applicable:
            unevaluated = [
                c.test_name
                for c in rule.RULE_CRITERIA
                if VALID_ANTIBIOTIC_CODE_REGEX.match(c.test_name)
                and any(k.startswith(c.test_name) for k in self.data_row_values)
            ]

            if any(c.test_name == PROF_CLASS.CEPH3 for c in rule.RULE_CRITERIA):
                ceph3_tested = [
                    c
                    for c in CEPH3_ANTIBIOTIC_CODES
                    if any(
                        VALID_ANTIBIOTIC_FIELD_NAME_REGEX.match(k) and short_code(k) == c
                        for k in self.data_row_values
                    )
                ]
                unevaluated = list(unevaluated) + ceph3_tested

            already = {k[:3] for k in self.result_interpretations}
            unevaluated = list(dict.fromkeys(x for x in unevaluated if x not in already))

            for abx_code in unevaluated:
                for full_code in self.data_row_values:
                    if full_code.startswith(abx_code):
                        self._get_single_interp(full_code)

            if rule.evaluate_criteria(self.data_row_values, self.result_interpretations):
                r_excl = C.InterpretationCodes.RESISTANT + C.InterpretationCodes.EXCLAMATION_POINT
                affected = [
                    k
                    for k in self.column_names
                    if VALID_ANTIBIOTIC_FIELD_NAME_REGEX.match(k)
                    and short_code(k) in rule.AFFECTED_ANTIBIOTICS
                ]
                for affected_code in affected:
                    if affected_code in self.result_interpretations:
                        if self.result_interpretations[affected_code] != r_excl:
                            self.result_interpretations[affected_code] = r_excl
                    elif affected_code in self.data_row_values:
                        self.result_interpretations[affected_code] = r_excl

    @staticmethod
    def get_single_interpretation(
        interpretation_config: InterpretationConfiguration,
        organism_code: str,
        antibiotic_code: str,
        measurement: str,
    ) -> str:
        """Interpret a single organism / antibiotic / measurement combination.

        Convenience wrapper that constructs a minimal synthetic data row and
        returns the interpretation for *antibiotic_code*.

        Args:
            interpretation_config: Configuration controlling guidelines, expert
                rules, and breakpoint preferences.
            organism_code: WHONET organism code (e.g. ``"eco"``).
            antibiotic_code: Full WHONET column name (e.g. ``"AMP_ND10"``).
            measurement: Raw measurement string (e.g. ``"19"``, ``"<4"``).

        Returns:
            Interpretation string (e.g. ``"S"``, ``"R"``, ``"R*"``, ``""``).
        """
        sample_row = {
            C.KeyFields.ORGANISM: organism_code,
            antibiotic_code: measurement,
        }
        interp = IsolateInterpretation(
            sample_row,
            list(sample_row.keys()),
            interpretation_config.enabled_expert_interpretation_rules,
            interpretation_config.user_defined_breakpoints,
            guideline_year=int(interpretation_config.guideline_year),
            use_intrinsic_resistance_rules=interpretation_config.use_intrinsic_resistance_rules,
            prioritized_breakpoint_types=interpretation_config.prioritized_breakpoint_types,
            prioritized_sites_of_infection=interpretation_config.prioritized_sites_of_infection,
        )
        return interp._get_single_interp(antibiotic_code)

    @staticmethod
    def remove_comments(interpretation: str) -> str:
        """Strip modifier suffixes from an interpretation string.

        Removes ``"*"`` (intrinsic resistance) and ``"!"`` (expert rule) suffixes,
        leaving only the base category code (e.g. ``"R*"`` → ``"R"``).

        Args:
            interpretation: Raw interpretation string that may contain suffixes.

        Returns:
            Base interpretation string without modifier characters.
        """
        return interpretation.replace(C.InterpretationCodes.EXCLAMATION_POINT, "").replace(
            C.InterpretationCodes.ASTERISK, ""
        )
