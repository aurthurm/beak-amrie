"""Pydantic request models for REST endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SingleInterpretRequest(BaseModel):
    organism_code: str
    whonet_abx_code: str
    measurement: str
    guidelines: list[str] = Field(default_factory=lambda: ['CLSI'])
    test_method: Literal['disk', 'mic'] = 'disk'
    potency: str = ''
    guideline_year: int
    include_comments: bool = False
    restrict_breakpoint_types: bool = False
    breakpoint_types: list[str] = Field(default_factory=list)
    restrict_sites: bool = False
    sites_of_infection: list[str] = Field(default_factory=list)


class BreakpointQueryRequest(BaseModel):
    organism_code: str
    user_defined_breakpoints: list = Field(default_factory=list)
    restrict_guidelines: bool = False
    prioritized_guidelines: list[str] | None = None
    restrict_years: bool = False
    prioritized_guideline_years: list[int] | None = None
    restrict_breakpoint_types: bool = False
    prioritized_breakpoint_types: list[str] | None = None
    restrict_sites: bool = False
    prioritized_sites_of_infection: list[str] | None = None
    restrict_drugs: bool = False
    whonet_abx_code: str = ''
    test_method: Literal['disk', 'mic'] = 'disk'
    potency: str = ''
    guidelines_for_drugs: list[str] = Field(default_factory=list)


class ExpertRulesRequest(BaseModel):
    organism_code: str
    full_test_codes: list[str] = Field(default_factory=list)


class IntrinsicRulesRequest(BaseModel):
    organism_code: str
    restrict_guidelines: bool = False
    guidelines: list[str] | None = None


class QCRequest(BaseModel):
    strain: str
    antibiotic: str
    measurement: str
    round_half_dilutions: bool = True
