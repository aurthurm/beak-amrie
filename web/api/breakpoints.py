"""Breakpoint query REST endpoint."""

from __future__ import annotations

import asyncio

from nicegui import app

from amrie.breakpoint import get_applicable_breakpoints
from web.helpers import breakpoint_to_dict, build_full_test_codes
from web.models.requests import BreakpointQueryRequest
from web.models.responses import BreakpointResponse


def _query_breakpoints(req: BreakpointQueryRequest) -> BreakpointResponse:
    prioritized_guidelines = req.prioritized_guidelines if req.restrict_guidelines else None
    prioritized_years = req.prioritized_guideline_years if req.restrict_years else None
    prioritized_types = req.prioritized_breakpoint_types if req.restrict_breakpoint_types else None
    prioritized_sites = req.prioritized_sites_of_infection if req.restrict_sites else None

    prioritized_drugs = None
    if req.restrict_drugs and req.whonet_abx_code:
        prioritized_drugs = build_full_test_codes(
            req.guidelines_for_drugs,
            req.whonet_abx_code,
            req.test_method,
            req.potency,
        )

    breakpoints = get_applicable_breakpoints(
        req.organism_code,
        req.user_defined_breakpoints,
        prioritized_guidelines=prioritized_guidelines,
        prioritized_guideline_years=prioritized_years,
        prioritized_breakpoint_types=prioritized_types,
        prioritized_sites_of_infection=prioritized_sites,
        prioritized_whonet_abx_full_drug_codes=prioritized_drugs,
    )
    return BreakpointResponse(breakpoints=[breakpoint_to_dict(bp) for bp in breakpoints])


@app.post('/api/breakpoints')
async def api_breakpoints(req: BreakpointQueryRequest) -> BreakpointResponse:
    return await asyncio.to_thread(_query_breakpoints, req)
