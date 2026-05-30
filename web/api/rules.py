"""Expert and intrinsic rule REST endpoints."""

from __future__ import annotations

import asyncio

from nicegui import app

from amrie.expert_rule import RuleCodes, get_applicable_expert_rules
from amrie.expected_resistance import get_applicable_expected_resistance_rules
from web.helpers import expert_rule_to_dict, intrinsic_rule_to_dict, split_full_test_codes
from web.models.requests import ExpertRulesRequest, IntrinsicRulesRequest
from web.models.responses import RuleResponse


def _query_expert_rules(req: ExpertRulesRequest) -> RuleResponse:
    antimicrobial_codes, other_tests = split_full_test_codes(req.full_test_codes)
    rules = get_applicable_expert_rules(
        req.organism_code,
        antimicrobial_codes,
        other_tests,
        RuleCodes.ALL,
    )
    return RuleResponse(rules=[expert_rule_to_dict(r) for r in rules])


def _query_intrinsic_rules(req: IntrinsicRulesRequest) -> RuleResponse:
    prioritized_guidelines = req.guidelines if req.restrict_guidelines else None
    rules = get_applicable_expected_resistance_rules(
        req.organism_code,
        prioritized_guidelines=prioritized_guidelines,
    )
    return RuleResponse(rules=[intrinsic_rule_to_dict(r) for r in rules])


@app.post('/api/expert-rules')
async def api_expert_rules(req: ExpertRulesRequest) -> RuleResponse:
    return await asyncio.to_thread(_query_expert_rules, req)


@app.post('/api/intrinsic-rules')
async def api_intrinsic_rules(req: IntrinsicRulesRequest) -> RuleResponse:
    return await asyncio.to_thread(_query_intrinsic_rules, req)
