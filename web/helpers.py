"""Shared helpers for the AMRIE web UI."""

from __future__ import annotations

import re
import tempfile
from decimal import Decimal
from pathlib import Path

from amrie.antibiotic import ALL_ANTIBIOTICS
from amrie.breakpoint import Breakpoint
from amrie.config import InterpretationConfiguration, default_configuration
from amrie.expert_rule import ExpertInterpretationRule, ExpertRuleCriterion
from amrie.expected_resistance import ExpectedResistancePhenotypeRule
from amrie.io_library import generate_output_file
from amrie.parsing import VALID_ANTIBIOTIC_FIELD_NAME_REGEX

_COMBO_RE = re.compile(r'/.+$')


def build_whonet_code(
    guideline: str,
    drug_code: str,
    disk: bool,
    potency: str = '',
) -> str | None:
    code = {'CLSI': 'N', 'EUCAST': 'E', 'SFM': 'F'}.get(guideline)
    if not code:
        return None
    if disk:
        p = _COMBO_RE.sub('', potency.replace('µg', '').replace('units', '').replace('.', '_'))
        if p == '1_25':
            p = '1_2'
        return f'{drug_code}_{code}D{p}'
    return f'{drug_code}_{code}M'


def get_potency_options(drug_code: str, guidelines: list[str]) -> list[str]:
    return list(dict.fromkeys(
        a.POTENCY for a in ALL_ANTIBIOTICS
        if a.WHONET_ABX_CODE == drug_code
        and any(
            (g == 'CLSI' and a.CLSI)
            or (g == 'EUCAST' and a.EUCAST)
            or (g == 'SFM' and a.SFM)
            for g in guidelines
        )
    ))


def make_single_tab_config(
    *,
    guideline_year: int,
    include_comments: bool,
    restrict_breakpoint_types: bool,
    breakpoint_types: list[str],
    restrict_sites: bool,
    sites_of_infection: list[str],
) -> InterpretationConfiguration:
    return InterpretationConfiguration(
        include_interpretation_comments=include_comments,
        enabled_expert_interpretation_rules=None,
        guideline_year=guideline_year,
        prioritized_breakpoint_types=(
            breakpoint_types if restrict_breakpoint_types else ['Human']
        ),
        prioritized_sites_of_infection=(sites_of_infection if restrict_sites else None),
    )


def make_default_config() -> InterpretationConfiguration:
    return default_configuration()


def _decimal_str(value: Decimal) -> str:
    return str(value)


def breakpoint_to_dict(bp: Breakpoint) -> dict:
    return {
        'GUIDELINES': bp.GUIDELINES,
        'YEAR': bp.YEAR,
        'BREAKPOINT_TYPE': bp.BREAKPOINT_TYPE,
        'HOST': bp.HOST,
        'SITE_OF_INFECTION': bp.SITE_OF_INFECTION,
        'WHONET_TEST': bp.WHONET_TEST,
        'R': _decimal_str(bp.R),
        'I': bp.I,
        'S': _decimal_str(bp.S),
        'ECV_ECOFF': _decimal_str(bp.ECV_ECOFF),
        'ORGANISM_CODE': bp.ORGANISM_CODE,
        'ORGANISM_CODE_TYPE': bp.ORGANISM_CODE_TYPE,
        'COMMENTS': bp.COMMENTS,
    }


def _format_criterion(criterion: ExpertRuleCriterion) -> str:
    return f'{criterion.test_name}={criterion.test_result}'


def expert_rule_to_dict(rule: ExpertInterpretationRule) -> dict:
    return {
        'RULE_CODE': rule.RULE_CODE,
        'DESCRIPTION': rule.DESCRIPTION,
        'ORGANISM_CODE': rule.ORGANISM_CODE,
        'ORGANISM_CODE_TYPE': rule.ORGANISM_CODE_TYPE,
        'RULE_CRITERIA': '; '.join(_format_criterion(c) for c in rule.RULE_CRITERIA),
        'AFFECTED_ANTIBIOTICS': ', '.join(rule.AFFECTED_ANTIBIOTICS),
        'ANTIBIOTIC_EXCEPTIONS': ', '.join(rule.ANTIBIOTIC_EXCEPTIONS),
    }


def intrinsic_rule_to_dict(rule: ExpectedResistancePhenotypeRule) -> dict:
    return {
        'GUIDELINE': rule.GUIDELINE,
        'REFERENCE_TABLE': rule.REFERENCE_TABLE,
        'ORGANISM_CODE': rule.ORGANISM_CODE,
        'ORGANISM_CODE_TYPE': rule.ORGANISM_CODE_TYPE,
        'ABX_CODE': rule.ABX_CODE,
        'ABX_CODE_TYPE': rule.ABX_CODE_TYPE,
        'ANTIBIOTIC_EXCEPTIONS': ', '.join(rule.ANTIBIOTIC_EXCEPTIONS),
        'COMMENTS': rule.COMMENTS,
    }


def split_full_test_codes(full_test_codes: list[str]) -> tuple[list[str], list[str]]:
    antimicrobial = [c for c in full_test_codes if VALID_ANTIBIOTIC_FIELD_NAME_REGEX.match(c)]
    other = [c for c in full_test_codes if c not in antimicrobial]
    return antimicrobial, other


def build_full_test_codes(
    guidelines: list[str],
    whonet_abx_code: str,
    test_method: str,
    potency: str,
) -> list[str]:
    disk = test_method == 'disk'
    codes: list[str] = []
    for guideline in guidelines:
        code = build_whonet_code(guideline, whonet_abx_code, disk, potency if disk else '')
        if code:
            codes.append(code)
    return codes


def generate_output_str(
    config: InterpretationConfiguration,
    input_column_names: list[str],
    interpretation_results: list[tuple[dict[str, str], dict[str, str]]],
) -> str:
    with tempfile.NamedTemporaryFile(
        mode='w',
        delete=False,
        suffix='.txt',
        encoding='utf-8',
    ) as tmp:
        path = tmp.name
    try:
        generate_output_file(path, config, input_column_names, interpretation_results)
        return Path(path).read_text(encoding='utf-8')
    finally:
        Path(path).unlink(missing_ok=True)
